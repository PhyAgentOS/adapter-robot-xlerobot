"""Offline tests for :mod:`robots_xlerobot.driver`.

These exercise the Forge joint and locomotion bridges against an in-memory SDK
injected after construction, so they never open a serial port. They skip cleanly
when the local Forge packages are not installed.
"""

from __future__ import annotations

import math
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest

forge_msgs = pytest.importorskip("forge_msgs")
forge_robot = pytest.importorskip("forge_robot")

from forge_msgs import JointCommand, JointState, LocomotionCommand

from robots_xlerobot.config import WHEEL_ORDER, build_robot_config
from robots_xlerobot.driver import XLeRobotDriver, locomotion_to_wheel_speeds_raw


class FakeSDK:
    """In-memory SDK exposing exactly the surface the driver consumes."""

    def __init__(self, config):
        self.config = config
        self.connected = False
        self.torque_writes: list[tuple] = []
        self.position_writes: list[tuple] = []
        self.wheel_torque_writes: list[bool] = []
        self.wheel_speed_writes: list[tuple[dict[str, int], int | None]] = []
        self.wheel_speed_read_error = False
        self.stuck_motor: tuple | None = None
        self._state = {
            (motor.bus, motor.id): SimpleNamespace(
                present_position_ticks=2048,
                speed_ticks=0,
                position_min_ticks=0,
                position_max_ticks=4095,
            )
            for motor in config.motors
        }
        self._motion_keys = {
            (motor.bus, motor.id) for motor in config.motors if motor.motion_enabled
        }

    def connect(self):
        self.connected = True

    def disconnect(self):
        self.connected = False

    def read_motion_positions(self):
        return {
            key: (self._state[key].present_position_ticks, self._state[key].speed_ticks)
            for key in self._motion_keys
        }

    def preflight_position(self, bus, motor_id, ticks, speed, acceleration):
        state = self._state[(bus, motor_id)]
        if not state.position_min_ticks <= ticks <= state.position_max_ticks:
            raise RuntimeError("target outside live limits")
        return SimpleNamespace(target_ticks=ticks)

    def enable_torque(self, bus, motor_id, enabled):
        self.torque_writes.append((bus, motor_id, enabled))

    def move_position(self, bus, motor_id, target_ticks, speed, acceleration):
        if self.stuck_motor != (bus, motor_id):
            self._state[(bus, motor_id)].present_position_ticks = target_ticks
        self.position_writes.append((bus, motor_id, target_ticks))

    def set_wheel_speeds_raw(self, speeds, acceleration_raw=None):
        self.wheel_speed_writes.append((dict(speeds), acceleration_raw))

    def read_wheel_speeds_raw(self):
        if self.wheel_speed_read_error:
            raise RuntimeError("simulated wheel feedback failure")
        return dict(self.wheel_speed_writes[-1][0])

    def stop_wheels(self, acceleration_raw=None):
        self.set_wheel_speeds_raw(
            {name: 0 for name in WHEEL_ORDER}, acceleration_raw
        )

    def enable_wheel_torque(self, enabled):
        self.wheel_torque_writes.append(enabled)


def build_driver(*, follower: bool = False) -> tuple[XLeRobotDriver, FakeSDK]:
    config = build_robot_config("/dev/fake_left", "/dev/fake_right")
    driver = XLeRobotDriver(config, is_follower=follower, auto_connect=False)
    sdk = FakeSDK(config)
    driver._sdk = sdk
    return driver, sdk


def test_joint_order_is_the_twelve_motion_actuators() -> None:
    driver, _ = build_driver()
    assert len(driver.joint_order) == 12
    assert driver.joint_order[0] == "left_arm_shoulder_pan"
    assert driver.joint_order[-1] == "right_arm_gripper"


def test_get_state_reads_only_and_reports_radians() -> None:
    driver, sdk = build_driver()
    driver.connect()
    state = driver.get_state()
    assert isinstance(state, JointState)
    assert state.name == driver.joint_order
    assert len(state.position) == 12
    assert sdk.position_writes == [] and sdk.torque_writes == []
    # 2048 ticks == pi radians
    assert all(abs(p - math.pi) < 1e-9 for p in state.position)


def test_follower_connect_captures_startup_and_enables_torque() -> None:
    driver, sdk = build_driver(follower=True)
    driver.connect()
    assert sdk.connected
    assert len(sdk.torque_writes) == 12
    assert all(enabled is True for (_bus, _id, enabled) in sdk.torque_writes)
    # Startup pose captured from the reported positions.
    assert driver._startup_ticks["left_arm_shoulder_pan"] == 2048
    assert sdk.wheel_torque_writes == [True]
    assert sdk.wheel_speed_writes[0][0] == {name: 0 for name in WHEEL_ORDER}
    driver.disconnect()


def test_leader_connect_does_not_enable_torque() -> None:
    driver, sdk = build_driver(follower=False)
    driver.connect()
    assert sdk.connected
    assert sdk.torque_writes == []
    assert driver._startup_ticks == {}


def test_set_command_writes_only_the_sparse_update() -> None:
    driver, sdk = build_driver()
    driver.connect()
    command = JointCommand(name=["left_arm_shoulder_pan"], position=[0.0])
    driver.set_command(command)
    assert sdk.position_writes == [("left_bus", 1, 0)]


def test_set_command_rejects_non_position_mode() -> None:
    driver, sdk = build_driver()
    driver.connect()
    command = JointCommand(name=["left_arm_shoulder_pan"], mode="velocity", velocity=[0.1])
    with pytest.raises(ValueError, match="only position"):
        driver.set_command(command)
    assert sdk.position_writes == []


def test_follower_disconnect_returns_to_startup_and_releases() -> None:
    driver, sdk = build_driver(follower=True)
    driver.connect()  # startup = 2048, torque enabled
    driver.set_command(JointCommand(name=["left_arm_shoulder_pan"], position=[0.0]))
    sdk.torque_writes.clear()
    sdk.position_writes.clear()

    driver.disconnect()

    assert ("left_bus", 1, 2048) in sdk.position_writes
    release_writes = [w for w in sdk.torque_writes if w[2] is False]
    assert len(release_writes) == 12
    assert driver._startup_ticks == {}
    assert sdk.wheel_speed_writes[-1][0] == {name: 0 for name in WHEEL_ORDER}
    assert sdk.wheel_torque_writes[-1] is False


def test_leader_disconnect_never_writes() -> None:
    driver, sdk = build_driver(follower=False)
    driver.connect()
    sdk.torque_writes.clear()
    sdk.position_writes.clear()
    driver.disconnect()
    assert sdk.torque_writes == [] and sdk.position_writes == []
    assert sdk.connected is False


def test_disconnect_return_timeout_still_releases_all_arm_torque() -> None:
    driver, sdk = build_driver(follower=True)
    driver.connect()
    driver.set_command(JointCommand(name=["left_arm_shoulder_pan"], position=[0.0]))
    sdk.stuck_motor = ("left_bus", 1)  # return cannot converge
    driver.config = replace(driver.config, feedback_timeout_s=0.001)
    sdk.torque_writes.clear()

    driver.disconnect()

    release_writes = [w for w in sdk.torque_writes if w[2] is False]
    assert len(release_writes) == 12
    assert sdk.connected is False  # serial still closed


def test_disconnect_preflight_failure_still_releases_all_arm_torque() -> None:
    driver, sdk = build_driver(follower=True)
    driver.connect()
    sdk._state[("left_bus", 4)].position_max_ticks = 2000
    sdk.torque_writes.clear()
    sdk.position_writes.clear()

    driver.disconnect()

    assert sdk.position_writes == []
    release_writes = [w for w in sdk.torque_writes if w[2] is False]
    assert len(release_writes) == 12


def test_three_omni_kinematics_matches_official_wheel_order() -> None:
    forward = locomotion_to_wheel_speeds_raw(
        LocomotionCommand(vx=0.05, vy=0.0, wz=0.0),
        wheel_radius_m=0.05,
        base_radius_m=0.125,
        max_speed_raw=1000,
    )
    assert forward["base_left_wheel"] > 0
    assert forward["base_back_wheel"] == 0
    assert forward["base_right_wheel"] < 0
    assert abs(forward["base_left_wheel"]) == abs(forward["base_right_wheel"])

    rotate = locomotion_to_wheel_speeds_raw(
        LocomotionCommand(vx=0.0, vy=0.0, wz=0.4),
        wheel_radius_m=0.05,
        base_radius_m=0.125,
        max_speed_raw=1000,
    )
    assert len(set(rotate.values())) == 1
    assert next(iter(rotate.values())) > 0


def test_locomotion_command_routes_through_forge_interface() -> None:
    driver, sdk = build_driver(follower=True)
    driver.connect()
    sdk.wheel_speed_writes.clear()

    driver.set_locomotion_command(LocomotionCommand(vx=0.03, vy=0.0, wz=0.0))

    speeds, acceleration = sdk.wheel_speed_writes[-1]
    assert speeds["base_right_wheel"] < 0 < speeds["base_left_wheel"]
    assert speeds["base_back_wheel"] == 0
    assert acceleration == driver.config.wheel_acceleration_raw
    driver.disconnect()


def test_locomotion_feedback_failure_compensates_with_zero() -> None:
    driver, sdk = build_driver(follower=True)
    driver.connect()
    sdk.wheel_speed_writes.clear()
    sdk.wheel_speed_read_error = True

    with pytest.raises(RuntimeError, match="feedback failure"):
        driver.set_locomotion_command(LocomotionCommand(vx=0.03, vy=0.0, wz=0.0))

    assert sdk.wheel_speed_writes[-1][0] == {name: 0 for name in WHEEL_ORDER}
    assert not driver._locomotion_active
    sdk.wheel_speed_read_error = False
    driver.disconnect()


def test_locomotion_watchdog_stops_stale_nonzero_command() -> None:
    config = replace(
        build_robot_config("/dev/fake_left", "/dev/fake_right"),
        locomotion_command_timeout_s=0.03,
    )
    driver = XLeRobotDriver(config, is_follower=True, auto_connect=False)
    sdk = FakeSDK(config)
    driver._sdk = sdk
    driver.connect()
    sdk.wheel_speed_writes.clear()

    driver.set_locomotion_command(LocomotionCommand(vx=0.03, vy=0.0, wz=0.0))
    deadline = time.monotonic() + 0.5
    while not driver.locomotion_timeout_latched and time.monotonic() < deadline:
        time.sleep(0.01)

    assert driver.locomotion_timeout_latched
    assert sdk.wheel_speed_writes[-1][0] == {name: 0 for name in WHEEL_ORDER}
    driver.disconnect()


def test_leader_rejects_locomotion_without_writes() -> None:
    driver, sdk = build_driver(follower=False)
    driver.connect()
    with pytest.raises(RuntimeError, match="follower"):
        driver.set_locomotion_command(LocomotionCommand(vx=0.01, vy=0.0, wz=0.0))
    assert sdk.wheel_speed_writes == []
    driver.disconnect()
