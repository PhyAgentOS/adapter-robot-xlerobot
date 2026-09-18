"""Forge driver for the XLeRobot dual-arm, three-omni-wheel platform.

The driver implements the existing Forge joint and locomotion protocols. A follower
captures and enables the twelve arm motors, verifies the three wheel servos are
already in velocity mode, and accepts body-frame ``LocomotionCommand`` values.
Disconnect stops/releases the base before returning/releasing the arms; a leader
never writes.

Arm coordinates are servo-reported radians: zero is register position zero and a
positive value means an increasing register value. They are not claimed to match
MJCF/URDF coordinates. Grippers use the same angular coordinate.
"""

from __future__ import annotations

import math
import threading
import time

from forge_common import get_logger
from forge_msgs import JointCommand, JointState, LocomotionCommand
from forge_robot import (
    BaseRobotDriver,
    LocomotionSpec,
    clip_and_validate_locomotion_command,
    clip_and_validate_position_command,
    specs_by_name,
)

from .config import WHEEL_ORDER, XLEROBOT_ACTUATOR_SPECS, RobotConfig
from .sdk import XLeRobotSDK, radians_to_ticks, ticks_to_radians

logger = get_logger(__name__)

_SPECS = specs_by_name(XLEROBOT_ACTUATOR_SPECS)
_WHEEL_DRIVE_ANGLES_RAD = tuple(math.radians(degrees) for degrees in (150.0, -90.0, 30.0))
# The installed wheel orientation requires the opposite X-axis motor sign from
# the geometric roller projection. This convention is local to XLeRobot.
_PHYSICAL_VX_SIGN = -1.0


def locomotion_to_wheel_speeds_raw(
    command: LocomotionCommand,
    *,
    wheel_radius_m: float,
    base_radius_m: float,
    max_speed_raw: int,
) -> dict[str, int]:
    """Convert body-frame m/s and rad/s to the official three-omni wheel order."""
    raw_per_rad_s = 4096.0 / (2.0 * math.pi)
    raw = [
        (
            _PHYSICAL_VX_SIGN * math.cos(angle) * command.vx
            + math.sin(angle) * command.vy
            + base_radius_m * command.wz
        )
        / wheel_radius_m
        * raw_per_rad_s
        for angle in _WHEEL_DRIVE_ANGLES_RAD
    ]
    peak = max(abs(value) for value in raw)
    if peak > max_speed_raw:
        scale = max_speed_raw / peak
        raw = [value * scale for value in raw]
    return {name: int(round(value)) for name, value in zip(WHEEL_ORDER, raw, strict=True)}



class XLeRobotDriver(BaseRobotDriver):
    """Expose the twelve motion joints as sparse ``JointCommand`` / ``JointState`` I/O."""

    def __init__(
        self,
        config: RobotConfig,
        *,
        is_follower: bool = False,
        auto_connect: bool = True,
    ) -> None:
        self.config = config
        self.is_follower = is_follower
        self._sdk = XLeRobotSDK(config)
        self._motors = {motor.name: motor for motor in config.motors}
        self._order = [motor.name for motor in config.motors if motor.motion_enabled]
        if len(self._order) != 12 or len(set(self._order)) != len(self._order):
            raise ValueError("RobotConfig must expose exactly twelve unique motion joints")
        self._startup_ticks: dict[str, int] = {}
        # Per-joint last written goal (in ticks).  Rewriting an unchanged goal
        # restarts the servo's internal trapezoidal profile and makes the motion
        # stutter, so ``set_command`` skips joints whose target has not moved.
        self._last_target_ticks: dict[str, int] = {}
        self._wheels = {
            motor.name: motor
            for motor in config.motors
            if motor.control_mode == "velocity"
        }
        if tuple(self._wheels) != WHEEL_ORDER:
            raise ValueError(
                f"RobotConfig must expose velocity wheels as {list(WHEEL_ORDER)!r}"
            )
        self._locomotion_spec = LocomotionSpec(
            max_vx=config.locomotion_max_vx_mps,
            max_vy=config.locomotion_max_vy_mps,
            max_wz=config.locomotion_max_wz_radps,
            allow_lateral=True,
        )
        self._locomotion_lock = threading.RLock()
        self._watchdog_stop = threading.Event()
        self._watchdog_thread: threading.Thread | None = None
        self._last_locomotion_command_at: float | None = None
        self._locomotion_active = False
        self._locomotion_timeout_latched = False
        self._wheels_armed = False
        self._disconnecting = False
        if auto_connect:
            self.connect()

    @property
    def joint_order(self) -> list[str]:
        return list(self._order)

    def connect(self) -> None:
        """Open buses and arm position/velocity motors only for a follower."""
        self._sdk.connect()
        if not self.is_follower:
            return
        enabled_arms = []
        try:
            self._startup_ticks = self._capture_startup_ticks()
            for name in self._order:
                motor = self._motors[name]
                self._sdk.enable_torque(motor.bus, motor.id, True)
                enabled_arms.append(motor)
            # Program a zero goal before enabling wheel torque, but never alter
            # EEPROM mode. Mode 1 must already be present on all three wheels.
            self._sdk.stop_wheels(self.config.wheel_acceleration_raw)
            self._sdk.enable_wheel_torque(True)
            self._wheels_armed = True
            self._start_locomotion_watchdog()
        except BaseException:
            try:
                self._sdk.enable_wheel_torque(False)
            except Exception:
                pass
            for motor in reversed(enabled_arms):
                try:
                    self._sdk.enable_torque(motor.bus, motor.id, False)
                except Exception:
                    pass
            self._startup_ticks = {}
            self._sdk.disconnect()
            raise

    def disconnect(self) -> None:
        """Stop/release the base, return/release arms, then close both buses."""
        with self._locomotion_lock:
            self._disconnecting = True
        self._stop_locomotion_watchdog()
        if self.is_follower and self._wheels_armed:
            try:
                self.stop_locomotion()
            except Exception as exc:  # noqa: BLE001 - torque-off is the fallback.
                logger.critical("XLeRobot wheel zero command failed: %s", exc)
            try:
                self._sdk.enable_wheel_torque(False)
            except Exception as exc:  # noqa: BLE001 - still close the serial bus.
                logger.critical("XLeRobot wheel torque release failed: %s", exc)
            self._wheels_armed = False
        if self.is_follower and self._startup_ticks:
            try:
                self.return_to_startup_and_release()
            except Exception as exc:  # noqa: BLE001 - keep arm semantics unchanged.
                logger.warning(
                    "XLeRobot return-to-startup/release encountered errors; "
                    "verify the arms are torque-free: %s",
                    exc,
                )
        self._sdk.disconnect()
        with self._locomotion_lock:
            self._last_locomotion_command_at = None
            self._locomotion_active = False
            self._disconnecting = False

    def get_state(self) -> JointState:
        """Read the twelve motion joints without any write side effect."""
        states = self._sdk.read_motion_positions()
        position: list[float] = []
        velocity: list[float] = []
        for name in self._order:
            motor = self._motors[name]
            position_ticks, speed_ticks = states[(motor.bus, motor.id)]
            position.append(float(ticks_to_radians(position_ticks)))
            velocity.append(float(ticks_to_radians(speed_ticks)))
        return JointState(name=self.joint_order, position=position, velocity=velocity, effort=[])

    def set_command(self, command: JointCommand) -> None:
        """Clip and write a sparse position command; unnamed joints keep their target.

        A joint is written only when its target actually changes: rewriting the
        same goal restarts the servo's trapezoidal profile and makes the motion
        stutter, so unchanged targets are skipped and the servo is left to finish
        its current move uninterrupted.
        """
        if getattr(command, "mode", "position") != "position":
            raise ValueError("XLeRobot accepts only position commands")
        safe = clip_and_validate_position_command(command, _SPECS)
        if not safe.position:
            raise ValueError("XLeRobot requires a position JointCommand")
        for name, radians in zip(safe.name, safe.position, strict=True):
            motor = self._motors[name]
            ticks = int(radians_to_ticks(radians))
            if self._last_target_ticks.get(name) == ticks:
                continue  # unchanged target: don't restart the servo's move
            self._sdk.move_position(
                motor.bus,
                motor.id,
                ticks,
                self.config.move_speed_raw,
                self.config.move_acceleration_raw,
            )
            self._last_target_ticks[name] = ticks

    def set_locomotion_command(self, command: LocomotionCommand) -> None:
        """Validate a Forge body twist and command all three omni wheels."""
        if not self.is_follower:
            raise RuntimeError("locomotion commands require a follower driver")
        safe = clip_and_validate_locomotion_command(command, self._locomotion_spec)
        speeds = locomotion_to_wheel_speeds_raw(
            safe,
            wheel_radius_m=self.config.wheel_radius_m,
            base_radius_m=self.config.base_radius_m,
            max_speed_raw=self.config.wheel_max_speed_raw,
        )
        with self._locomotion_lock:
            if self._disconnecting or not self._wheels_armed:
                raise RuntimeError("XLeRobot wheels are not armed")
            self._sdk.set_wheel_speeds_raw(
                speeds, acceleration_raw=self.config.wheel_acceleration_raw
            )
            try:
                self._sdk.read_wheel_speeds_raw()
            except BaseException as exc:
                # The nonzero write may have succeeded. Stop immediately; if
                # that also fails, leave the watchdog armed for another attempt.
                self._last_locomotion_command_at = (
                    time.monotonic() - self.config.locomotion_command_timeout_s
                )
                self._locomotion_active = any(speeds.values())
                try:
                    self._sdk.stop_wheels(self.config.wheel_acceleration_raw)
                except Exception as stop_exc:
                    if hasattr(exc, "add_note"):
                        exc.add_note(f"wheel stop after feedback failure also failed: {stop_exc}")
                else:
                    self._last_locomotion_command_at = None
                    self._locomotion_active = False
                raise
            self._last_locomotion_command_at = time.monotonic()
            self._locomotion_active = any(speeds.values())
            self._locomotion_timeout_latched = False

    def stop_locomotion(self) -> None:
        """Synchronously command and confirm the local write path to zero speed."""
        with self._locomotion_lock:
            if not self._wheels_armed:
                raise RuntimeError("XLeRobot wheels are not armed")
            self._sdk.stop_wheels(self.config.wheel_acceleration_raw)
            self._last_locomotion_command_at = None
            self._locomotion_active = False

    @property
    def locomotion_timeout_latched(self) -> bool:
        with self._locomotion_lock:
            return self._locomotion_timeout_latched

    def _start_locomotion_watchdog(self) -> None:
        if self._watchdog_thread is not None and self._watchdog_thread.is_alive():
            return
        self._watchdog_stop.clear()
        self._watchdog_thread = threading.Thread(
            target=self._locomotion_watchdog_loop,
            name="xlerobot-locomotion-watchdog",
            daemon=True,
        )
        self._watchdog_thread.start()

    def _stop_locomotion_watchdog(self) -> None:
        self._watchdog_stop.set()
        thread = self._watchdog_thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=max(1.0, self.config.locomotion_command_timeout_s * 2.0))
        self._watchdog_thread = None

    def _locomotion_watchdog_loop(self) -> None:
        timeout = self.config.locomotion_command_timeout_s
        interval = min(0.05, timeout / 2.0)
        while not self._watchdog_stop.wait(interval):
            with self._locomotion_lock:
                last = self._last_locomotion_command_at
                if (
                    self._disconnecting
                    or not self._wheels_armed
                    or not self._locomotion_active
                    or last is None
                    or time.monotonic() - last < timeout
                ):
                    continue
                try:
                    self._sdk.stop_wheels(self.config.wheel_acceleration_raw)
                except Exception as exc:  # noqa: BLE001 - retry on next watchdog pass.
                    logger.critical("XLeRobot watchdog could not stop wheels: %s", exc)
                    continue
                self._last_locomotion_command_at = None
                self._locomotion_active = False
                self._locomotion_timeout_latched = True
                logger.warning(
                    "XLeRobot locomotion command timed out after %.3fs; wheels stopped",
                    timeout,
                )

    # -------------------------------------------------------------- shutdown

    def _capture_startup_ticks(self) -> dict[str, int]:
        states = self._sdk.read_motion_positions()
        return {
            name: int(states[(self._motors[name].bus, self._motors[name].id)][0])
            for name in self._order
        }

    def return_to_startup_and_release(self) -> None:
        """Try to return to startup, then always attempt every arm torque release."""
        if not self._startup_ticks:
            raise RuntimeError("no startup pose captured")
        motion_error: Exception | None = None
        try:
            speed = self.config.move_speed_raw
            acceleration = self.config.move_acceleration_raw
            for name in self._order:
                motor = self._motors[name]
                self._sdk.preflight_position(
                    motor.bus, motor.id, self._startup_ticks[name], speed, acceleration
                )
            for name in self._order:
                motor = self._motors[name]
                self._sdk.move_position(
                    motor.bus, motor.id, self._startup_ticks[name], speed, acceleration
                )
            self._wait_until_at_startup()
        except Exception as exc:  # release remains mandatory
            motion_error = exc

        release_errors: list[str] = []
        for name in self._order:
            motor = self._motors[name]
            try:
                self._sdk.enable_torque(motor.bus, motor.id, False)
            except Exception as exc:  # do not skip remaining IDs
                release_errors.append(f"{name}: {exc}")
        self._startup_ticks = {}

        if motion_error or release_errors:
            details = []
            if motion_error:
                details.append(f"return to startup failed: {motion_error}")
            if release_errors:
                details.append("arm torque release failed: " + "; ".join(release_errors))
            raise RuntimeError("; ".join(details))

    def _wait_until_at_startup(self) -> None:
        tolerance = self.config.homing_tolerance_ticks
        deadline = time.monotonic() + float(self.config.feedback_timeout_s)
        while True:
            states = self._sdk.read_motion_positions()
            drifted: list[str] = []
            for name in self._order:
                motor = self._motors[name]
                position_ticks, _speed = states[(motor.bus, motor.id)]
                if abs(int(position_ticks) - self._startup_ticks[name]) > tolerance:
                    drifted.append(name)
            if not drifted:
                return
            if time.monotonic() >= deadline:
                raise RuntimeError("return to startup timed out: " + "; ".join(drifted))
            time.sleep(0.05)
