"""Thin, write-gated wrapper around the vendored FTServo ``scservo_sdk``.

This module is the only place in the package that touches ``PortHandler`` /
``sms_sts``, so it owns serial-port lifetime and every hardware write.

Safety contract:

* ``connect`` only opens configured serial ports. It never enables torque, changes
  a mode, writes EEPROM, resets a servo, or sends a target.
* Reads are side-effect free after ``connect``.
* Arm and wheel writes require a live connection and validate hardware raw ranges.
  Torque changes and goals are explicit, separate calls ordered by the driver.
* Every transaction checks both the communication result and servo error byte.
* Arm position writes are limited to IDs 1--6. Head slots stay read-only; the
  three wheel slots accept signed velocity/torque operations only after mode 1
  is verified.

Positions are reported encoder ticks (4096 ticks/rev); ``ticks_to_radians`` and
``radians_to_ticks`` convert with ``2*pi/4096``. ``Homing_Offset`` is applied by
servo firmware, so the reported position is already offset and must not be
applied a second time.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import wraps
from threading import RLock
from time import sleep
from typing import Callable, Mapping

from ._vendor.scservo_sdk.port_handler import PortHandler
from ._vendor.scservo_sdk.scservo_def import (
    COMM_RX_CORRUPT,
    COMM_RX_FAIL,
    COMM_RX_TIMEOUT,
    COMM_SUCCESS,
    COMM_TX_FAIL,
)
from ._vendor.scservo_sdk.sms_sts import (
    SMS_STS_MAX_ANGLE_LIMIT_L,
    SMS_STS_MIN_ANGLE_LIMIT_L,
    SMS_STS_MODE,
    SMS_STS_MODEL_L,
    SMS_STS_OFS_L,
    SMS_STS_TORQUE_ENABLE,
    sms_sts as _SMS_STS,
)

from .config import WHEEL_ORDER, MotorConfig, RobotConfig

__all__ = [
    "MotorState",
    "MotionPlan",
    "XLeRobotSDK",
    "SDKError",
    "SDKNotConnectedError",
    "SDKCommunicationError",
    "ticks_to_radians",
    "radians_to_ticks",
]

TICKS_PER_REVOLUTION = 4096
POSITION_MAX_TICKS = 4095  # STS3215 position register full scale (15-bit)
_TRANSIENT_WRITE_COMM_RESULTS = frozenset({
    COMM_TX_FAIL,
    COMM_RX_FAIL,
    COMM_RX_TIMEOUT,
    COMM_RX_CORRUPT,
})
_WRITE_ATTEMPTS = 3
_WRITE_RETRY_DELAY_S = 0.02  # Allow the half-duplex bus to settle before resending.


def _serialized(method):
    """Serialize transactions because the watchdog shares the right serial bus."""

    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._io_lock:
            return method(self, *args, **kwargs)

    return wrapper


def ticks_to_radians(ticks: float | int) -> float:
    """Convert reported encoder ticks to radians (4096 ticks per revolution)."""
    return float(ticks) * (2.0 * math.pi / TICKS_PER_REVOLUTION)


def radians_to_ticks(radians: float | int) -> float:
    """Convert radians back to encoder ticks (4096 ticks per revolution)."""
    return float(radians) * (TICKS_PER_REVOLUTION / (2.0 * math.pi))


class SDKError(RuntimeError):
    """Base class for physical-access failures from this module."""


class SDKNotConnectedError(SDKError):
    """A read or write was requested before ``connect`` succeeded."""


class SDKCommunicationError(SDKError):
    """A bus transaction failed or the servo reported a non-zero error flag."""


@dataclass(frozen=True, slots=True)
class MotorState:
    """Fresh, decoded state of one motor as reported by the servo.

    ``present_position_ticks`` and ``speed_ticks`` are signed (the SDK already
    applied the 15-bit two's-complement decode).  ``position_min_ticks`` and
    ``position_max_ticks`` are the raw, unsigned EEPROM limits.  ``position_ticks``
    is an alias so callers may read either spelling.
    """

    bus: str
    motor_id: int
    present_position_ticks: int
    speed_ticks: int
    position_min_ticks: int | None
    position_max_ticks: int | None
    model: int | None = None
    mode: int | None = None
    torque_enabled: bool | None = None
    homing_offset_ticks: int | None = None

    @property
    def position_ticks(self) -> int:
        return self.present_position_ticks


@dataclass(frozen=True, slots=True)
class MotionPlan:
    """A preflight-approved target for one motor; carries no write authority."""

    bus: str
    motor_id: int
    target_ticks: int
    minimum_ticks: int
    maximum_ticks: int
    speed_raw: int
    acceleration_raw: int


class XLeRobotSDK:
    """Own the FTServo ports and gate every hardware write.

    Constructing an instance, importing this module, or calling ``--help`` must
    not open a serial port; only ``connect`` does that.
    """

    def __init__(self, config: RobotConfig) -> None:
        self.config = config
        self._ports: dict[str, PortHandler] = {}
        self._servos: dict[str, _SMS_STS] = {}
        self._connected = False
        self._io_lock = RLock()

    # ------------------------------------------------------------------ ports

    @_serialized
    def connect(self) -> None:
        """Open the configured buses only; no enable, mode, EEPROM or target write."""
        if self._connected:
            return
        opened: list[str] = []
        try:
            for name, bus in self.config.buses.items():
                port = PortHandler(bus.port)
                port.baudrate = bus.baudrate
                try:
                    opened_ok = port.openPort()
                except OSError as exc:  # missing device / permission denied
                    raise SDKError(f"bus {name!r}: cannot open {bus.port!r}: {exc}") from exc
                if not opened_ok:
                    raise SDKError(f"bus {name!r}: failed to open {bus.port!r}")
                self._ports[name] = port
                self._servos[name] = _SMS_STS(port)
                opened.append(name)
        except BaseException:
            # A partially-opened set of ports must be torn back down so a later
            # connect retry starts from a clean state.
            for name in reversed(opened):
                try:
                    self._ports[name].closePort()
                except Exception:
                    pass
            self._ports.clear()
            self._servos.clear()
            raise
        self._connected = True

    @_serialized
    def disconnect(self) -> None:
        """Close every port without issuing a target, reset, or disable write."""
        for name in list(self._ports):
            try:
                self._ports[name].closePort()
            except Exception:
                pass
        self._ports.clear()
        self._servos.clear()
        self._connected = False

    # ------------------------------------------------------------- addressing

    def _servo(self, bus: str) -> _SMS_STS:
        if not self._connected:
            raise SDKNotConnectedError("SDK is not connected; call connect() explicitly")
        try:
            return self._servos[bus]
        except KeyError:
            raise SDKError(f"unknown bus {bus!r}") from None

    def _require_address(self, bus: str, motor_id: int) -> None:
        bus_config = self.config.buses.get(bus)
        if bus_config is None:
            raise SDKError(f"unknown bus {bus!r}")
        if motor_id not in bus_config.motor_ids:
            raise SDKError(f"motor ID {motor_id} is not configured on bus {bus!r}")

    def _require_motion_motor(self, bus: str, motor_id: int) -> None:
        """Require a configured position-mode arm for arm motion or torque writes."""
        self._require_address(bus, motor_id)
        try:
            motor = self.config.motor(bus, motor_id)
        except KeyError:
            raise SDKError(f"unknown motor {bus}:{motor_id}") from None
        if not motor.motion_enabled:
            raise SDKError(
                f"{bus}:{motor_id} is not a position-mode arm; refusing arm motion write"
            )

    def _velocity_motors(self) -> list[MotorConfig]:
        motors = [
            motor for motor in self.config.motors if motor.control_mode == "velocity"
        ]
        if tuple(motor.name for motor in motors) != WHEEL_ORDER:
            raise SDKError(
                f"velocity-mode motors must be configured as {list(WHEEL_ORDER)!r}"
            )
        return motors

    # ------------------------------------------------------------------ reads

    @staticmethod
    def _check(bus: str, motor_id: int, comm_result: int, error: int, context: str) -> None:
        if comm_result != COMM_SUCCESS:
            raise SDKCommunicationError(
                f"{bus}:{motor_id} {context} failed (comm result {comm_result})"
            )
        if error:
            raise SDKCommunicationError(
                f"{bus}:{motor_id} {context} servo error flag {error:#x}"
            )

    def _read_raw_state(self, bus: str, motor_id: int) -> MotorState:
        servo = self._servo(bus)
        position, speed, comm, err = servo.ReadPosSpeed(motor_id)
        self._check(bus, motor_id, comm, err, "read position/speed")
        model, comm, err = servo.read2ByteTxRx(motor_id, SMS_STS_MODEL_L)
        self._check(bus, motor_id, comm, err, "read model")
        mode, comm, err = servo.read1ByteTxRx(motor_id, SMS_STS_MODE)
        self._check(bus, motor_id, comm, err, "read mode")
        torque, comm, err = servo.read1ByteTxRx(motor_id, SMS_STS_TORQUE_ENABLE)
        self._check(bus, motor_id, comm, err, "read torque enable")
        minimum, comm, err = servo.read2ByteTxRx(motor_id, SMS_STS_MIN_ANGLE_LIMIT_L)
        self._check(bus, motor_id, comm, err, "read min angle limit")
        maximum, comm, err = servo.read2ByteTxRx(motor_id, SMS_STS_MAX_ANGLE_LIMIT_L)
        self._check(bus, motor_id, comm, err, "read max angle limit")
        offset, comm, err = servo.read2ByteTxRx(motor_id, SMS_STS_OFS_L)
        self._check(bus, motor_id, comm, err, "read homing offset")
        return MotorState(
            bus=bus,
            motor_id=motor_id,
            present_position_ticks=position,
            speed_ticks=speed,
            position_min_ticks=minimum,
            position_max_ticks=maximum,
            model=model,
            mode=mode,
            torque_enabled=bool(torque),
            homing_offset_ticks=servo.scs_tohost(offset, 15),
        )

    @_serialized
    def read_motor(self, bus: str, motor_id: int) -> MotorState:
        """Read one configured motor with no write side effect."""
        self._require_address(bus, motor_id)
        return self._read_raw_state(bus, motor_id)

    @_serialized
    def read_all(self) -> dict[tuple[str, int], MotorState]:
        """Read all seventeen configured motors without write side effects."""
        if not self._connected:
            raise SDKNotConnectedError("SDK is not connected; call connect() explicitly")
        return {
            (motor.bus, motor.id): self._read_raw_state(motor.bus, motor.id)
            for motor in self.config.motors
        }

    @_serialized
    def read_motion_positions(self) -> dict[tuple[str, int], tuple[int, int]]:
        """Read position+speed for the twelve motion motors (one transaction each).

        Unlike :meth:`read_all`, this skips model/mode/torque/limits/offset, so it
        is ~10x lighter on the half-duplex bus.  Use it on the hot path so the
        servos are not stuttered by heavy polling while they move.
        """
        if not self._connected:
            raise SDKNotConnectedError("SDK is not connected; call connect() explicitly")
        result: dict[tuple[str, int], tuple[int, int]] = {}
        for motor in self.config.motors:
            if not motor.motion_enabled:
                continue
            servo = self._servo(motor.bus)
            position, speed, comm, err = servo.ReadPosSpeed(motor.id)
            self._check(motor.bus, motor.id, comm, err, "read position/speed")
            result[(motor.bus, motor.id)] = (position, speed)
        return result

    # ---------------------------------------------------------------- writers

    @staticmethod
    def _validate_position(value: object, bus: str, motor_id: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= POSITION_MAX_TICKS:
            raise SDKError(
                f"{bus}:{motor_id} target position must be an integer in 0..{POSITION_MAX_TICKS}"
            )
        return value

    @staticmethod
    def _validate_speed(value: object, bus: str, motor_id: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 0xFFFF:
            raise SDKError(f"{bus}:{motor_id} speed raw must be a positive 16-bit integer")
        return value

    @staticmethod
    def _validate_acceleration(value: object, bus: str, motor_id: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 0xFF:
            raise SDKError(f"{bus}:{motor_id} acceleration raw must be a positive byte")
        return value

    @_serialized
    def preflight_position(
        self,
        bus: str,
        motor_id: int,
        ticks: int,
        speed_raw: int | None = None,
        acceleration_raw: int | None = None,
    ) -> MotionPlan:
        """Check a target against live limits before any write is allowed.

        This is read-only: it never opens a motion session.  A target outside the
        freshly read EEPROM limits, or outside the STS3215 hardware range, is a
        hard error.  ``speed_raw`` / ``acceleration_raw`` default to the config
        values and must be positive (zero is never treated as "slowest").
        """
        self._require_motion_motor(bus, motor_id)
        ticks = self._validate_position(ticks, bus, motor_id)
        speed = self._validate_speed(
            speed_raw if speed_raw is not None else self.config.move_speed_raw, bus, motor_id
        )
        acceleration = self._validate_acceleration(
            acceleration_raw if acceleration_raw is not None else self.config.move_acceleration_raw,
            bus,
            motor_id,
        )
        state = self._read_raw_state(bus, motor_id)
        minimum = state.position_min_ticks
        maximum = state.position_max_ticks
        if minimum is None or maximum is None:
            raise SDKError(f"{bus}:{motor_id} live position limits are unavailable")
        if not minimum <= ticks <= maximum:
            raise SDKError(
                f"{bus}:{motor_id} target {ticks} is outside live limits {minimum}..{maximum}"
            )
        return MotionPlan(
            bus=bus,
            motor_id=motor_id,
            target_ticks=ticks,
            minimum_ticks=minimum,
            maximum_ticks=maximum,
            speed_raw=speed,
            acceleration_raw=acceleration,
        )

    def _write_with_retry(
        self,
        bus: str,
        motor_id: int,
        context: str,
        operation: Callable[[], tuple[int, int]],
    ) -> None:
        """Retry an idempotent write after transient transport failures."""

        for attempt in range(1, _WRITE_ATTEMPTS + 1):
            comm, err = operation()
            if comm == COMM_SUCCESS:
                self._check(bus, motor_id, comm, err, context)
                return
            if comm not in _TRANSIENT_WRITE_COMM_RESULTS or attempt == _WRITE_ATTEMPTS:
                suffix = f" after {attempt} attempts" if attempt > 1 else ""
                self._check(bus, motor_id, comm, err, context + suffix)
            sleep(_WRITE_RETRY_DELAY_S)

    @_serialized
    def move_position(
        self,
        bus: str,
        motor_id: int,
        target_ticks: int,
        speed_raw: int,
        acceleration_raw: int,
    ) -> None:
        """Write one position goal for one motion motor.

        The caller is responsible for preflighting the target and for enabling
        torque when needed.  This only enforces the arm-slot restriction and the
        hardware raw ranges.
        """
        self._require_motion_motor(bus, motor_id)
        target_ticks = self._validate_position(target_ticks, bus, motor_id)
        speed = self._validate_speed(speed_raw, bus, motor_id)
        acceleration = self._validate_acceleration(acceleration_raw, bus, motor_id)
        servo = self._servo(bus)
        self._write_with_retry(
            bus,
            motor_id,
            "write position",
            lambda: servo.WritePosEx(motor_id, target_ticks, speed, acceleration),
        )

    @_serialized
    def enable_torque(self, bus: str, motor_id: int, enabled: bool) -> None:
        """Explicitly set torque enable for one motion motor."""
        self._require_motion_motor(bus, motor_id)
        if not isinstance(enabled, bool):
            raise SDKError("enabled must be a boolean")
        servo = self._servo(bus)
        self._write_with_retry(
            bus,
            motor_id,
            "write torque enable",
            lambda: servo.write1ByteTxRx(
                motor_id, SMS_STS_TORQUE_ENABLE, 1 if enabled else 0
            ),
        )

    def _verify_wheel_modes(self) -> list[MotorConfig]:
        """Read all wheel modes before a batch; never changes EEPROM mode."""
        motors = self._velocity_motors()
        for motor in motors:
            servo = self._servo(motor.bus)
            mode, comm, err = servo.read1ByteTxRx(motor.id, SMS_STS_MODE)
            self._check(motor.bus, motor.id, comm, err, "read wheel mode")
            if mode != 1:
                raise SDKError(
                    f"{motor.name} ({motor.bus}:{motor.id}) mode is {mode}; "
                    "expected velocity mode 1, refusing write"
                )
        return motors

    @staticmethod
    def _validate_wheel_speed(value: object, motor: MotorConfig, ceiling: int) -> int:
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not -ceiling <= value <= ceiling
        ):
            raise SDKError(
                f"{motor.name} speed raw must be an integer in {-ceiling}..{ceiling}"
            )
        return value

    def _write_wheel_speed_unchecked(
        self, motor: MotorConfig, speed_raw: int, acceleration_raw: int
    ) -> None:
        servo = self._servo(motor.bus)
        self._write_with_retry(
            motor.bus,
            motor.id,
            "write wheel speed",
            lambda: servo.WriteSpec(motor.id, speed_raw, acceleration_raw),
        )

    def _best_effort_stop_wheels(
        self, motors: list[MotorConfig], acceleration_raw: int
    ) -> list[str]:
        errors: list[str] = []
        for motor in motors:
            try:
                self._write_wheel_speed_unchecked(motor, 0, acceleration_raw)
            except Exception as exc:  # noqa: BLE001 - preserve every stop attempt.
                errors.append(f"{motor.name}: {exc}")
        return errors

    @_serialized
    def read_wheel_speeds_raw(self) -> dict[str, int]:
        """Read signed present speeds for the three configured wheels."""
        result: dict[str, int] = {}
        for motor in self._velocity_motors():
            speed, comm, err = self._servo(motor.bus).ReadSpeed(motor.id)
            self._check(motor.bus, motor.id, comm, err, "read wheel speed")
            result[motor.name] = int(speed)
        return result

    @_serialized
    def set_wheel_speeds_raw(
        self, speeds: Mapping[str, int], acceleration_raw: int | None = None
    ) -> None:
        """Write one complete three-wheel batch after validating every value/mode."""
        if set(speeds) != set(WHEEL_ORDER) or len(speeds) != len(WHEEL_ORDER):
            raise SDKError(f"wheel speeds must contain exactly {list(WHEEL_ORDER)!r}")
        acceleration = self._validate_acceleration(
            acceleration_raw
            if acceleration_raw is not None
            else self.config.wheel_acceleration_raw,
            "wheels",
            0,
        )
        motors = self._velocity_motors()
        validated = {
            motor.name: self._validate_wheel_speed(
                speeds[motor.name], motor, self.config.wheel_max_speed_raw
            )
            for motor in motors
        }
        # Validate all three modes before the first velocity write. A mode
        # mismatch is a hard error because WriteSpec in position mode is unsafe.
        self._verify_wheel_modes()
        try:
            for motor in motors:
                self._write_wheel_speed_unchecked(
                    motor, validated[motor.name], acceleration
                )
        except BaseException as exc:
            stop_errors = self._best_effort_stop_wheels(motors, acceleration)
            if stop_errors and hasattr(exc, "add_note"):
                exc.add_note("wheel stop compensation also failed: " + "; ".join(stop_errors))
            raise

    @_serialized
    def stop_wheels(self, acceleration_raw: int | None = None) -> None:
        """Command a verified zero speed to every wheel."""
        self.set_wheel_speeds_raw(
            {name: 0 for name in WHEEL_ORDER}, acceleration_raw=acceleration_raw
        )

    def _write_wheel_torque(self, motor: MotorConfig, enabled: bool) -> None:
        servo = self._servo(motor.bus)
        self._write_with_retry(
            motor.bus,
            motor.id,
            "write wheel torque enable",
            lambda: servo.write1ByteTxRx(
                motor.id, SMS_STS_TORQUE_ENABLE, 1 if enabled else 0
            ),
        )

    @_serialized
    def enable_wheel_torque(self, enabled: bool) -> None:
        """Enable/disable all wheel motors without changing their EEPROM mode."""
        if not isinstance(enabled, bool):
            raise SDKError("enabled must be a boolean")
        motors = self._verify_wheel_modes() if enabled else self._velocity_motors()
        if enabled:
            try:
                for motor in motors:
                    self._write_wheel_torque(motor, True)
            except BaseException as exc:
                release_errors: list[str] = []
                for motor in motors:
                    try:
                        self._write_wheel_torque(motor, False)
                    except Exception as release_exc:  # noqa: BLE001
                        release_errors.append(f"{motor.name}: {release_exc}")
                if release_errors and hasattr(exc, "add_note"):
                    exc.add_note(
                        "wheel torque rollback also failed: " + "; ".join(release_errors)
                    )
                raise
            return

        # Releasing torque is fail-safe: a failure on one ID must not skip the
        # remaining wheels. Report only after all three attempts have completed.
        errors: list[str] = []
        for motor in motors:
            try:
                self._write_wheel_torque(motor, False)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{motor.name}: {exc}")
        if errors:
            raise SDKCommunicationError(
                "one or more wheel torque releases failed: " + "; ".join(errors)
            )
