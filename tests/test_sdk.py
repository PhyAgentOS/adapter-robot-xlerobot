"""Offline tests for :mod:`robots_xlerobot.sdk`.

Every test runs against a fake ``PortHandler`` / ``sms_sts``, so no serial port
is opened during collection or execution. The fake records every read and write
so arm position gates, wheel velocity-mode gates, compensation stops, and torque
release behavior are asserted rather than assumed.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

import robots_xlerobot.sdk as sdk_mod
from robots_xlerobot.config import WHEEL_ORDER, build_robot_config
from robots_xlerobot.sdk import (
    SDKCommunicationError,
    SDKError,
    SDKNotConnectedError,
    XLeRobotSDK,
    radians_to_ticks,
    ticks_to_radians,
)

_LEFT_PORT = "/dev/fake_left"
_RIGHT_PORT = "/dev/fake_right"


class FakeBus:
    """Stands in for one bus's ``PortHandler`` plus its ``sms_sts`` client."""

    MODE = 33
    TORQUE_ENABLE = 40
    MIN_LIMIT = 9
    MAX_LIMIT = 11
    OFFSET = 31

    def __init__(self, port: str) -> None:
        self.port = port
        self.baudrate = 1_000_000
        self.opened = False
        self.closed = False
        self.motors: dict[int, dict[str, int]] = {}
        self.reads: list[tuple] = []
        self.writes: list[tuple] = []
        self.comm = 0
        self.err = 0

    # PortHandler surface
    def openPort(self) -> bool:
        self.opened = True
        return True

    def closePort(self) -> None:
        self.closed = True
        self.opened = False

    # sms_sts surface
    def _state(self, motor_id: int) -> dict[str, int]:
        if motor_id not in self.motors:
            self.motors[motor_id] = {
                "position": 2048,
                "speed": 0,
                "mode": 1 if self.port == _RIGHT_PORT and motor_id in (7, 8, 9) else 0,
                "torque": 0,
                "min": 1000,
                "max": 3000,
                "offset": 0,
            }
        return self.motors[motor_id]

    def ReadPosSpeed(self, motor_id: int):
        self.reads.append(("ReadPosSpeed", motor_id))
        s = self._state(motor_id)
        return s["position"], s["speed"], self.comm, self.err

    def ReadSpeed(self, motor_id: int):
        self.reads.append(("ReadSpeed", motor_id))
        return self._state(motor_id)["speed"], self.comm, self.err

    def read1ByteTxRx(self, motor_id: int, address: int):
        self.reads.append(("read1", motor_id, address))
        s = self._state(motor_id)
        value = s["mode"] if address == self.MODE else s["torque"] if address == self.TORQUE_ENABLE else 0
        return value, self.comm, self.err

    def read2ByteTxRx(self, motor_id: int, address: int):
        self.reads.append(("read2", motor_id, address))
        s = self._state(motor_id)
        value = {
            self.MIN_LIMIT: s["min"],
            self.MAX_LIMIT: s["max"],
            self.OFFSET: s["offset"],
        }.get(address, 0)
        return value, self.comm, self.err

    @staticmethod
    def scs_tohost(value: int, bits: int) -> int:
        return value if not (value & (1 << bits)) else -(value & ~(1 << bits))

    def WritePosEx(self, motor_id: int, position: int, speed: int, acc: int):
        self.writes.append(("WritePosEx", motor_id, position, speed, acc))
        self._state(motor_id)["position"] = position
        return self.comm, self.err

    def WriteSpec(self, motor_id: int, speed: int, acc: int):
        self.writes.append(("WriteSpec", motor_id, speed, acc))
        self._state(motor_id)["speed"] = speed
        return self.comm, self.err

    def write1ByteTxRx(self, motor_id: int, address: int, value: int):
        self.writes.append(("write1", motor_id, address, value))
        self._state(motor_id)["torque"] = value
        return self.comm, self.err


@pytest.fixture
def hardware(monkeypatch):
    """Patch the vendored classes with fakes and expose the created buses."""
    buses: list[FakeBus] = []

    def make_port(port: str) -> FakeBus:
        bus = FakeBus(port)
        buses.append(bus)
        return bus

    def make_servo(port_handler: FakeBus) -> FakeBus:
        return port_handler

    monkeypatch.setattr(sdk_mod, "PortHandler", make_port)
    monkeypatch.setattr(sdk_mod, "_SMS_STS", make_servo)
    return buses


def make_sdk() -> XLeRobotSDK:
    config = build_robot_config(_LEFT_PORT, _RIGHT_PORT)
    return XLeRobotSDK(config)


def bus_for(hardware: list[FakeBus], name: str) -> FakeBus:
    port = build_robot_config(_LEFT_PORT, _RIGHT_PORT).buses[name].port
    return next(b for b in hardware if b.port == port)


def test_construct_and_import_do_not_open_ports(hardware) -> None:
    make_sdk()
    assert hardware == []


def test_connect_opens_ports_without_any_read_or_write(hardware) -> None:
    sdk = make_sdk()
    sdk.connect()
    assert len(hardware) == 2
    assert all(bus.opened and not bus.closed for bus in hardware)
    assert all(bus.reads == [] and bus.writes == [] for bus in hardware)


def test_disconnect_closes_ports_without_writes(hardware) -> None:
    sdk = make_sdk()
    sdk.connect()
    sdk.disconnect()
    assert all(bus.closed for bus in hardware)
    assert all(bus.writes == [] for bus in hardware)


def test_read_motor_returns_state_and_never_writes(hardware) -> None:
    sdk = make_sdk()
    sdk.connect()
    state = sdk.read_motor("left_bus", 1)
    assert state.present_position_ticks == 2048
    assert state.position_ticks == 2048
    assert state.speed_ticks == 0
    assert state.position_min_ticks == 1000
    assert state.position_max_ticks == 3000
    assert all(bus.writes == [] for bus in hardware)


def test_read_all_covers_seventeen_devices(hardware) -> None:
    sdk = make_sdk()
    sdk.connect()
    states = sdk.read_all()
    assert len(states) == 17
    assert set(states) == {(m.bus, m.id) for m in sdk.config.motors}


def test_read_requires_connection(hardware) -> None:
    sdk = make_sdk()
    with pytest.raises(SDKNotConnectedError):
        sdk.read_motor("left_bus", 1)


def test_comm_failure_raises_instead_of_fabricating_state(hardware) -> None:
    sdk = make_sdk()
    sdk.connect()
    bus_for(hardware, "left_bus").comm = -6  # COMM_RX_TIMEOUT
    with pytest.raises(SDKCommunicationError):
        sdk.read_motor("left_bus", 1)


def test_servo_error_flag_raises(hardware) -> None:
    sdk = make_sdk()
    sdk.connect()
    bus_for(hardware, "left_bus").err = 0x20  # overload bit
    with pytest.raises(SDKCommunicationError):
        sdk.read_motor("left_bus", 1)


def test_unknown_bus_or_id_is_rejected(hardware) -> None:
    sdk = make_sdk()
    sdk.connect()
    with pytest.raises(SDKError):
        sdk.read_motor("no_such_bus", 1)
    with pytest.raises(SDKError):
        sdk.read_motor("left_bus", 99)


def test_write_requires_connection(hardware) -> None:
    sdk = make_sdk()
    with pytest.raises(SDKNotConnectedError):
        sdk.move_position("left_bus", 1, 2048, 10, 5)


def test_move_position_and_enable_torque(hardware) -> None:
    sdk = make_sdk()
    sdk.connect()
    left = bus_for(hardware, "left_bus")
    sdk.enable_torque("left_bus", 1, True)
    sdk.move_position("left_bus", 1, 2100, 10, 5)
    assert ("write1", 1, 40, 1) in left.writes
    assert ("WritePosEx", 1, 2100, 10, 5) in left.writes


def test_position_write_retries_corrupt_status_packet(hardware) -> None:
    sdk = make_sdk()
    sdk.connect()
    left = bus_for(hardware, "left_bus")
    results = iter((-7, -7, 0))
    attempts: list[int] = []

    def flaky_write(motor_id: int, position: int, speed: int, acc: int):
        attempts.append(motor_id)
        return next(results), 0

    left.WritePosEx = flaky_write
    sdk.move_position("left_bus", 1, 2100, 10, 5)

    assert attempts == [1, 1, 1]


def test_position_write_still_raises_after_three_corrupt_responses(hardware) -> None:
    sdk = make_sdk()
    sdk.connect()
    left = bus_for(hardware, "left_bus")
    left.comm = -7

    with pytest.raises(SDKCommunicationError, match="after 3 attempts"):
        sdk.move_position("left_bus", 1, 2100, 10, 5)

    writes = [entry for entry in left.writes if entry[0] == "WritePosEx"]
    assert len(writes) == 3


def test_motion_write_rejects_diagnostic_head_and_wheel_ids(hardware) -> None:
    sdk = make_sdk()
    sdk.connect()
    with pytest.raises(SDKError, match="not a position-mode"):
        sdk.move_position("right_bus", 7, 2048, 10, 5)  # base_left_wheel
    with pytest.raises(SDKError, match="not a position-mode"):
        sdk.enable_torque("left_bus", 8, True)  # left_head_2


def test_preflight_rejects_out_of_range_and_zero_speed(hardware) -> None:
    sdk = make_sdk()
    sdk.connect()
    with pytest.raises(SDKError, match="outside live limits"):
        sdk.preflight_position("left_bus", 1, 3999, 10, 5)  # within 0..4095, beyond live 3000
    with pytest.raises(SDKError, match="positive"):
        sdk.preflight_position("left_bus", 1, 2048, 0, 5)


def test_preflight_returns_a_plan_inside_limits(hardware) -> None:
    sdk = make_sdk()
    sdk.connect()
    plan = sdk.preflight_position("left_bus", 1, 2048, 10, 5)
    assert plan.target_ticks == 2048
    assert plan.minimum_ticks == 1000
    assert plan.maximum_ticks == 3000
    assert all(bus.writes == [] for bus in hardware)


def test_partial_connect_failure_closes_opened_ports(hardware, monkeypatch) -> None:
    sdk = make_sdk()
    real_open = FakeBus.openPort
    second_port = build_robot_config(_LEFT_PORT, _RIGHT_PORT).buses["right_bus"].port  # iterated after left_bus
    calls = 0

    def flaky_open(self: FakeBus) -> bool:
        nonlocal calls
        calls += 1
        if self.port == second_port:
            return False
        return real_open(self)

    monkeypatch.setattr(FakeBus, "openPort", flaky_open)
    with pytest.raises(SDKError):
        sdk.connect()
    assert calls == 2
    opened = [b for b in hardware if b.port != second_port]
    assert opened and all(b.closed for b in opened)
    assert sdk._connected is False


def test_ticks_radians_roundtrip() -> None:
    for ticks in (0, 1024, 2048, 4095):
        assert abs(radians_to_ticks(ticks_to_radians(ticks)) - ticks) < 1e-9


def test_reported_position_is_not_double_offset(hardware) -> None:
    sdk = make_sdk()
    sdk.connect()
    left = bus_for(hardware, "left_bus")
    left._state(1)  # populate the lazy per-motor record
    left.motors[1]["offset"] = 0x8FFF  # signed 15-bit: -(0x0FFF) == -4095
    left.motors[1]["position"] = 2048
    state = sdk.read_motor("left_bus", 1)
    # Homing offset is decoded and reported separately, never re-applied to position.
    assert state.homing_offset_ticks == -4095
    assert state.present_position_ticks == 2048


def test_wheel_speed_batch_uses_signed_write_spec_without_mode_writes(hardware) -> None:
    sdk = make_sdk()
    sdk.connect()
    right = bus_for(hardware, "right_bus")

    speeds = dict(zip(WHEEL_ORDER, (120, -80, 0), strict=True))
    sdk.set_wheel_speeds_raw(speeds, acceleration_raw=7)

    assert [entry for entry in right.writes if entry[0] == "WriteSpec"] == [
        ("WriteSpec", 7, 120, 7),
        ("WriteSpec", 8, -80, 7),
        ("WriteSpec", 9, 0, 7),
    ]
    assert not any(
        entry[0] == "write1" and entry[2] == FakeBus.MODE
        for entry in right.writes
    )


def test_wheel_mode_mismatch_fails_before_speed_write(hardware) -> None:
    sdk = make_sdk()
    sdk.connect()
    right = bus_for(hardware, "right_bus")
    right._state(8)["mode"] = 0

    with pytest.raises(SDKError, match="expected velocity mode 1"):
        sdk.stop_wheels()

    assert not any(entry[0] == "WriteSpec" for entry in right.writes)


def test_partial_wheel_batch_failure_attempts_zero_on_all_wheels(hardware) -> None:
    sdk = make_sdk()
    sdk.connect()
    right = bus_for(hardware, "right_bus")
    calls: list[tuple[int, int, int]] = []

    def flaky_write(motor_id: int, speed: int, acc: int):
        calls.append((motor_id, speed, acc))
        if motor_id == 8 and speed != 0:
            return -7, 0
        return 0, 0

    right.WriteSpec = flaky_write
    speeds = dict(zip(WHEEL_ORDER, (120, -80, 40), strict=True))
    with pytest.raises(SDKCommunicationError):
        sdk.set_wheel_speeds_raw(speeds, acceleration_raw=7)

    assert calls[-3:] == [(7, 0, 7), (8, 0, 7), (9, 0, 7)]


def test_wheel_torque_is_separate_and_velocity_gated(hardware) -> None:
    sdk = make_sdk()
    sdk.connect()
    right = bus_for(hardware, "right_bus")

    sdk.enable_wheel_torque(True)
    sdk.enable_wheel_torque(False)

    torque = [entry for entry in right.writes if entry[0] == "write1"]
    assert torque == [
        ("write1", 7, FakeBus.TORQUE_ENABLE, 1),
        ("write1", 8, FakeBus.TORQUE_ENABLE, 1),
        ("write1", 9, FakeBus.TORQUE_ENABLE, 1),
        ("write1", 7, FakeBus.TORQUE_ENABLE, 0),
        ("write1", 8, FakeBus.TORQUE_ENABLE, 0),
        ("write1", 9, FakeBus.TORQUE_ENABLE, 0),
    ]


def test_wheel_torque_disable_remains_available_on_mode_mismatch(hardware) -> None:
    sdk = make_sdk()
    sdk.connect()
    right = bus_for(hardware, "right_bus")
    right._state(8)["mode"] = 0

    sdk.enable_wheel_torque(False)

    assert [entry[1] for entry in right.writes if entry[0] == "write1"] == [7, 8, 9]


def test_wheel_torque_release_attempts_all_ids_after_one_failure(hardware) -> None:
    sdk = make_sdk()
    sdk.connect()
    right = bus_for(hardware, "right_bus")
    calls: list[int] = []

    def flaky_torque(motor_id: int, address: int, value: int):
        calls.append(motor_id)
        if motor_id == 8:
            return -7, 0
        return 0, 0

    right.write1ByteTxRx = flaky_torque
    with pytest.raises(SDKCommunicationError, match="torque releases failed"):
        sdk.enable_wheel_torque(False)

    assert 7 in calls and 8 in calls and 9 in calls
    assert calls.index(9) > calls.index(8)


def test_read_wheel_speeds_returns_signed_values(hardware) -> None:
    sdk = make_sdk()
    sdk.connect()
    right = bus_for(hardware, "right_bus")
    for motor_id, speed in zip((7, 8, 9), (20, -30, 0), strict=True):
        right._state(motor_id)["speed"] = speed

    assert sdk.read_wheel_speeds_raw() == dict(
        zip(WHEEL_ORDER, (20, -30, 0), strict=True)
    )
