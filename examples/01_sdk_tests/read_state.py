#!/usr/bin/env python3
"""Read every configured XLeRobot motor over the two FTServo buses.

This script is strictly read-only: it opens the serial ports, reads all 17
motors (twelve arm slots plus head and wheel peripherals), prints a table and
optionally saves a JSON report.  It never enables torque, changes a mode, writes
EEPROM, resets a servo or sends a target.

Usage::

    python read_state.py            # print the table to stdout
    python read_state.py --output state.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running this script directly from a source checkout before the package
# is installed.  Installed package users do not need this.
_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from robots_xlerobot.config import build_robot_config, config_from_file
from robots_xlerobot.sdk import SDKError, XLeRobotSDK


def _row(sdk: XLeRobotSDK, motor) -> dict:
    state = sdk.read_motor(motor.bus, motor.id)
    return {
        "name": motor.name,
        "bus": motor.bus,
        "id": motor.id,
        "motion_enabled": motor.motion_enabled,
        "model": state.model,
        "position_ticks": state.present_position_ticks,
        "speed_ticks": state.speed_ticks,
        "position_min_ticks": state.position_min_ticks,
        "position_max_ticks": state.position_max_ticks,
        "mode": state.mode,
        "torque_enabled": state.torque_enabled,
        "homing_offset_ticks": state.homing_offset_ticks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read all XLeRobot motors (no writes).")
    parser.add_argument("--config", help="YAML/JSON config file (see config/robot.example.yaml)")
    parser.add_argument("--left-port", help="left-arm serial device path (by-id recommended)")
    parser.add_argument("--right-port", help="right-arm serial device path (by-id recommended)")
    parser.add_argument("--output", type=Path, help="save the full report as JSON")
    args = parser.parse_args(argv)

    if args.config and (args.left_port or args.right_port):
        parser.error("--config is mutually exclusive with --left-port/--right-port")
    if args.config:
        config = config_from_file(args.config)
    elif args.left_port and args.right_port:
        config = build_robot_config(args.left_port, args.right_port)
    else:
        parser.error("provide --config <file> or --left-port/--right-port (see config/robot.example.yaml)")

    sdk = XLeRobotSDK(config)
    try:
        sdk.connect()
        rows = [_row(sdk, motor) for motor in config.motors]
    except SDKError as exc:
        print(f"read failed: {exc}", file=sys.stderr)
        return 1
    finally:
        sdk.disconnect()

    header = f"{'name':28} {'bus':10} {'id':>3} {'model':>5} {'pos':>6} {'min':>6} {'max':>6} {'mode':>4} {'torque':>6} {'offset':>6}"
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{row['name']:28} {row['bus']:10} {row['id']:3d} {row['model']:5d} "
            f"{row['position_ticks']:6d} {row['position_min_ticks']:6d} {row['position_max_ticks']:6d} "
            f"{row['mode']:4d} {str(row['torque_enabled']):>6} {row['homing_offset_ticks']:6d}"
        )

    if args.output:
        report = {
            "readonly": True,
            "instructions": ["READ"],
            "motors": rows,
        }
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\nreport saved to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
