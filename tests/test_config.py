"""Offline tests for :mod:`robots_xlerobot.config`."""

from __future__ import annotations

from pathlib import Path

import pytest

from robots_xlerobot.config import (
    JOINT_ORDER,
    WHEEL_ORDER,
    XLEROBOT_ACTUATOR_ORDER,
    XLEROBOT_ACTUATOR_SPECS,
    RobotConfig,
    build_robot_config,
    config_from_file,
    config_from_mapping,
)


def test_build_robot_config_layout() -> None:
    config = build_robot_config("/dev/left", "/dev/right")
    assert config.buses["left_bus"].port == "/dev/left"
    assert config.buses["right_bus"].port == "/dev/right"
    assert len([m for m in config.motors if m.motion_enabled]) == 12
    assert [m.name for m in config.motors if m.motion_enabled] == list(JOINT_ORDER)
    # Heads remain diagnostic; wheels are explicitly velocity-controlled.
    heads = {m.name for m in config.motors if not m.motion_enabled and m.bus == "left_bus"}
    wheels = {m.name for m in config.motors if m.control_mode == "velocity"}
    assert heads == {"left_head_1", "left_head_2"}
    assert tuple(m.name for m in config.motors if m.control_mode == "velocity") == WHEEL_ORDER
    assert wheels == set(WHEEL_ORDER)
    assert [config.motor_named(name).id for name in WHEEL_ORDER] == [7, 8, 9]


def test_config_from_mapping_tolerates_redundant_bus_name() -> None:
    data = {
        "buses": {
            "left_bus": {"name": "left_bus", "port": "/dev/left", "motor_ids": [1, 2, 3, 4, 5, 6, 7, 8]},
            "right_bus": {"name": "right_bus", "port": "/dev/right", "motor_ids": [1, 2, 3, 4, 5, 6, 7, 8, 9]},
        },
        "motors": [
            {"name": "left_arm_shoulder_pan", "bus": "left_bus", "id": 1, "motion_enabled": True},
            {"name": "right_arm_shoulder_pan", "bus": "right_bus", "id": 1, "motion_enabled": True},
        ],
    }
    config = config_from_mapping(data)
    assert isinstance(config, RobotConfig)
    assert config.buses["left_bus"].port == "/dev/left"
    assert all(m.control_mode == "position" for m in config.motors if m.motion_enabled)


def test_config_from_file_loads_example_yaml() -> None:
    pytest.importorskip("yaml")
    example = Path(__file__).resolve().parents[1] / "config" / "robot.example.yaml"
    if not example.exists():
        pytest.skip("config/robot.example.yaml not present")
    config = config_from_file(example)
    assert len([m for m in config.motors if m.motion_enabled]) == 12
    assert tuple(m.name for m in config.motors if m.control_mode == "velocity") == WHEEL_ORDER


def test_actuator_specs_match_joint_order() -> None:
    assert XLEROBOT_ACTUATOR_ORDER == list(JOINT_ORDER)
    assert [spec.name for spec in XLEROBOT_ACTUATOR_SPECS] == list(JOINT_ORDER)
    assert all(spec.kind == "revolute" for spec in XLEROBOT_ACTUATOR_SPECS)
    # Static limits stay None until a real calibration lands; the SDK still
    # enforces the hardware 0..4095-tick range on every write.
    assert all(spec.min_position is None for spec in XLEROBOT_ACTUATOR_SPECS)
    assert all(spec.max_position is None for spec in XLEROBOT_ACTUATOR_SPECS)
