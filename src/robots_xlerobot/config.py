"""Small, validated configuration objects for the physical XLeRobot.

The arm layout follows the official XLeRobot wiring: the left-arm bus also
carries the two position-mode head motors (IDs 7-8), the right-arm bus also
carries the three velocity-mode base wheels (IDs 7-9).  The two serial device
paths are supplied per-robot (via ``build_robot_config`` or ``config_from_file``)
and are never hardcoded here.  Hardware limits are read live before a motion is
planned; no historical probe limit is promoted to a generic safe default here.

The twelve motion actuators are also exposed as ``forge_robot.ActuatorSpec``
entries so the driver can route commands through the standard
``clip_and_validate_position_command`` helper.  ``min_position`` / ``max_position``
are intentionally ``None``: XLeRobot has no calibrated static limits yet, and the
SDK still rejects any target outside the hardware 0..4095-tick range on every
write.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Any, Literal, Mapping

from forge_robot import ActuatorSpec


JOINT_ORDER: tuple[str, ...] = (
    "left_arm_shoulder_pan",
    "left_arm_shoulder_lift",
    "left_arm_elbow_flex",
    "left_arm_wrist_flex",
    "left_arm_wrist_roll",
    "left_arm_gripper",
    "right_arm_shoulder_pan",
    "right_arm_shoulder_lift",
    "right_arm_elbow_flex",
    "right_arm_wrist_flex",
    "right_arm_wrist_roll",
    "right_arm_gripper",
)

# Official XLeRobot right-bus wheel mapping (IDs 7, 8, 9).  The names and
# order are part of the chassis kinematics contract, not generic joint names.
WHEEL_ORDER: tuple[str, ...] = (
    "base_left_wheel",
    "base_back_wheel",
    "base_right_wheel",
)

# Driver-facing actuator metadata.  Static limits stay ``None`` on purpose: the
# servo's authoritative range is read live from EEPROM, and the SDK already
# enforces the hardware 0..4095-tick range on every write.
XLEROBOT_ACTUATOR_SPECS: tuple[ActuatorSpec, ...] = tuple(
    ActuatorSpec(name=name, kind="revolute") for name in JOINT_ORDER
)
XLEROBOT_ACTUATOR_ORDER: list[str] = [spec.name for spec in XLEROBOT_ACTUATOR_SPECS]


def _positive_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


@dataclass(frozen=True, slots=True)
class BusConfig:
    name: str
    port: str
    baudrate: int = 1_000_000
    motor_ids: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("bus name must not be empty")
        if not self.port or not Path(self.port).is_absolute():
            raise ValueError(f"bus {self.name!r} port must be an absolute path")
        _positive_int(self.baudrate, "baudrate")
        if len(set(self.motor_ids)) != len(self.motor_ids):
            raise ValueError(f"bus {self.name!r} has duplicate motor IDs")
        for motor_id in self.motor_ids:
            if isinstance(motor_id, bool) or not isinstance(motor_id, int) or not 1 <= motor_id <= 252:
                raise ValueError(f"bus {self.name!r} has invalid motor ID {motor_id!r}")


@dataclass(frozen=True, slots=True)
class MotorConfig:
    name: str
    bus: str
    id: int
    position_min_ticks: int | None = None
    position_max_ticks: int | None = None
    motion_enabled: bool = False
    control_mode: Literal["position", "velocity", "diagnostic"] | None = None

    def __post_init__(self) -> None:
        if not self.name or not self.bus:
            raise ValueError("motor name and bus must not be empty")
        if isinstance(self.id, bool) or not isinstance(self.id, int) or not 1 <= self.id <= 252:
            raise ValueError(f"invalid motor ID {self.id!r}")
        if not isinstance(self.motion_enabled, bool):
            raise ValueError("motion_enabled must be a boolean")
        # Backward compatibility for existing arm-only configuration files:
        # motion_enabled=True meant a position-controlled arm motor, while
        # False meant read-only diagnostics. Wheels must opt in explicitly.
        if self.control_mode is None:
            object.__setattr__(
                self,
                "control_mode",
                "position" if self.motion_enabled else "diagnostic",
            )
        if self.control_mode not in {"position", "velocity", "diagnostic"}:
            raise ValueError(
                "control_mode must be 'position', 'velocity', or 'diagnostic'"
            )
        if self.motion_enabled != (self.control_mode == "position"):
            raise ValueError(
                "motion_enabled must be true exactly for position-mode arm motors"
            )
        if self.position_min_ticks is not None and not isinstance(self.position_min_ticks, int):
            raise ValueError("position_min_ticks must be an integer or null")
        if self.position_max_ticks is not None and not isinstance(self.position_max_ticks, int):
            raise ValueError("position_max_ticks must be an integer or null")
        if (self.position_min_ticks is not None and self.position_max_ticks is not None
                and self.position_min_ticks > self.position_max_ticks):
            raise ValueError("position_min_ticks must not exceed position_max_ticks")


@dataclass(frozen=True, slots=True)
class RobotConfig:
    buses: Mapping[str, BusConfig]
    motors: tuple[MotorConfig, ...]
    move_speed_raw: int = 100
    move_acceleration_raw: int = 10
    command_timeout_s: float = 2.0
    feedback_timeout_s: float = 2.0
    # Loaded joints can settle tens of ticks from the commanded midpoint.
    homing_tolerance_ticks: int = 40
    wheel_radius_m: float = 0.05
    base_radius_m: float = 0.125
    locomotion_max_vx_mps: float = 0.05
    locomotion_max_vy_mps: float = 0.05
    locomotion_max_wz_radps: float = 0.4
    wheel_max_speed_raw: int = 1000
    wheel_acceleration_raw: int = 10
    locomotion_command_timeout_s: float = 0.25

    def __post_init__(self) -> None:
        if not self.buses:
            raise ValueError("at least one bus is required")
        if set(self.buses) != {bus.name for bus in self.buses.values()}:
            raise ValueError("bus mapping keys must equal BusConfig.name")
        for value, name in (
            (self.move_speed_raw, "move_speed_raw"),
            (self.move_acceleration_raw, "move_acceleration_raw"),
            (self.homing_tolerance_ticks, "homing_tolerance_ticks"),
            (self.wheel_max_speed_raw, "wheel_max_speed_raw"),
            (self.wheel_acceleration_raw, "wheel_acceleration_raw"),
        ):
            _positive_int(value, name)
        for value, name in (
            (self.command_timeout_s, "command_timeout_s"),
            (self.feedback_timeout_s, "feedback_timeout_s"),
            (self.wheel_radius_m, "wheel_radius_m"),
            (self.base_radius_m, "base_radius_m"),
            (self.locomotion_max_vx_mps, "locomotion_max_vx_mps"),
            (self.locomotion_max_vy_mps, "locomotion_max_vy_mps"),
            (self.locomotion_max_wz_radps, "locomotion_max_wz_radps"),
            (self.locomotion_command_timeout_s, "locomotion_command_timeout_s"),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be a finite positive number")
        seen_names: set[str] = set()
        seen_addresses: set[tuple[str, int]] = set()
        for motor in self.motors:
            if motor.bus not in self.buses:
                raise ValueError(f"motor {motor.name!r} names unknown bus {motor.bus!r}")
            if motor.id not in self.buses[motor.bus].motor_ids:
                raise ValueError(f"motor {motor.name!r} is absent from bus {motor.bus!r} motor_ids")
            if motor.name in seen_names or (motor.bus, motor.id) in seen_addresses:
                raise ValueError(f"duplicate motor {motor.name!r} or address {(motor.bus, motor.id)!r}")
            seen_names.add(motor.name)
            seen_addresses.add((motor.bus, motor.id))
        if self.wheel_max_speed_raw > 0x7FFF:
            raise ValueError("wheel_max_speed_raw must not exceed 32767")
        if self.wheel_acceleration_raw > 0xFF:
            raise ValueError("wheel_acceleration_raw must not exceed 255")
        wheel_names = tuple(
            motor.name for motor in self.motors if motor.control_mode == "velocity"
        )
        if wheel_names and wheel_names != WHEEL_ORDER:
            raise ValueError(
                f"velocity-mode motors must be exactly {list(WHEEL_ORDER)!r} in order"
            )

    def motor(self, bus: str, motor_id: int) -> MotorConfig:
        for motor in self.motors:
            if (motor.bus, motor.id) == (bus, motor_id):
                return motor
        raise KeyError(f"unknown motor {bus}:{motor_id}")

    def motor_named(self, name: str) -> MotorConfig:
        for motor in self.motors:
            if motor.name == name:
                return motor
        raise KeyError(f"unknown motor {name!r}")


def build_robot_config(left_port: str, right_port: str) -> RobotConfig:
    """Build the standard 17-device layout from two serial device paths.

    This is the reusable factory: the two device paths are parameters, so no
    hardware-specific serial number is baked into the code.  Following the
    official XLeRobot wiring, the left-arm bus also carries the two position-mode
    head motors (IDs 7--8) and the right-arm bus carries the three velocity-mode
    base wheels (IDs 7--9).

    The caller is responsible for telling the code which physical arm each path
    corresponds to (for this robot, by wiring the head onto the left-arm bus and
    the wheels onto the right-arm bus).
    """
    buses = {
        "left_bus": BusConfig("left_bus", left_port, motor_ids=tuple(range(1, 9))),
        "right_bus": BusConfig("right_bus", right_port, motor_ids=tuple(range(1, 10))),
    }
    left = tuple(
        MotorConfig(name, "left_bus", index, motion_enabled=True, control_mode="position")
        for index, name in enumerate(JOINT_ORDER[:6], 1)
    )
    right = tuple(
        MotorConfig(name, "right_bus", index, motion_enabled=True, control_mode="position")
        for index, name in enumerate(JOINT_ORDER[6:], 1)
    )
    peripherals = (
        MotorConfig("left_head_1", "left_bus", 7, control_mode="diagnostic"),
        MotorConfig("left_head_2", "left_bus", 8, control_mode="diagnostic"),
        MotorConfig(WHEEL_ORDER[0], "right_bus", 7, control_mode="velocity"),
        MotorConfig(WHEEL_ORDER[1], "right_bus", 8, control_mode="velocity"),
        MotorConfig(WHEEL_ORDER[2], "right_bus", 9, control_mode="velocity"),
    )
    return RobotConfig(buses=buses, motors=left + right + peripherals)


def config_from_file(path: str | Path) -> RobotConfig:
    """Load a :class:`RobotConfig` from a YAML or JSON file.

    See ``config/robot.example.yaml`` for the expected schema.  YAML parsing needs
    ``pyyaml``; JSON works with the standard library.
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("loading YAML requires 'pyyaml' (pip install pyyaml)") from exc
        data = yaml.safe_load(text)
    else:
        import json

        data = json.loads(text)
    if not isinstance(data, Mapping):
        raise ValueError(f"configuration file {path} must contain a mapping at the top level")
    return config_from_mapping(data)


def config_from_mapping(data: Mapping[str, Any]) -> RobotConfig:
    """Parse the intentionally small YAML/JSON-compatible configuration form."""
    allowed = {
        "buses",
        "motors",
        "move_speed_raw",
        "move_acceleration_raw",
        "command_timeout_s",
        "feedback_timeout_s",
        "homing_tolerance_ticks",
        "wheel_radius_m",
        "base_radius_m",
        "locomotion_max_vx_mps",
        "locomotion_max_vy_mps",
        "locomotion_max_wz_radps",
        "wheel_max_speed_raw",
        "wheel_acceleration_raw",
        "locomotion_command_timeout_s",
    }
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"unknown configuration fields: {sorted(unknown)!r}")
    raw_buses = data.get("buses")
    raw_motors = data.get("motors")
    if not isinstance(raw_buses, Mapping) or not isinstance(raw_motors, (list, tuple)):
        raise ValueError("buses mapping and motors list are required")
    buses = {}
    for name, value in raw_buses.items():
        if isinstance(value, Mapping):
            fields = dict(value)
            fields.pop("name", None)  # the bus name comes from the mapping key
            buses[str(name)] = BusConfig(name=str(name), **fields)
    if len(buses) != len(raw_buses):
        raise ValueError("every bus must be a mapping")
    motors = tuple(MotorConfig(**dict(value)) for value in raw_motors if isinstance(value, Mapping))
    if len(motors) != len(raw_motors):
        raise ValueError("every motor must be a mapping")
    kwargs = {name: data[name] for name in allowed - {"buses", "motors"} if name in data}
    return RobotConfig(buses=buses, motors=motors, **kwargs)
