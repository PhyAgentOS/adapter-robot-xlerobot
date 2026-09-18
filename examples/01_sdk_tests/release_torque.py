#!/usr/bin/env python3
"""Stop the base and disable torque on all arms and wheels.

Run this after a ``--follower`` dora run to return the robot to the safe,
pre-test state (torque off).  Only disable torque while the arms are supported:
releasing torque lets gravity take over.

Usage::

    python release_torque.py --config config/robot.yaml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running this script directly from a source checkout before the package
# is installed.  Installed package users do not need this.
_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from robots_xlerobot.config import build_robot_config, config_from_file
from robots_xlerobot.sdk import SDKError, XLeRobotSDK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stop XLeRobot wheels and disable all arm/wheel torque.")
    parser.add_argument("--config", help="YAML/JSON config file (see config/robot.example.yaml)")
    parser.add_argument("--left-port", help="left-arm serial device path (by-id recommended)")
    parser.add_argument("--right-port", help="right-arm serial device path (by-id recommended)")
    args = parser.parse_args(argv)

    if args.config and (args.left_port or args.right_port):
        parser.error("--config is mutually exclusive with --left-port/--right-port")
    if bool(args.left_port) != bool(args.right_port):
        parser.error("--left-port and --right-port must be provided together")
    if args.config:
        config = config_from_file(args.config)
    elif args.left_port and args.right_port:
        config = build_robot_config(args.left_port, args.right_port)
    else:
        parser.error("provide --config <file> or --left-port/--right-port (see config/robot.example.yaml)")

    sdk = XLeRobotSDK(config)
    errors: list[str] = []
    try:
        sdk.connect()
        try:
            sdk.stop_wheels()
        except SDKError as exc:
            errors.append(f"wheel zero command: {exc}")
        try:
            # This remains safe even when the mode check above failed.
            sdk.enable_wheel_torque(False)
        except SDKError as exc:
            errors.append(f"wheel torque release: {exc}")

        released = 0
        for motor in config.motors:
            if not motor.motion_enabled:
                continue
            try:
                sdk.enable_torque(motor.bus, motor.id, False)
                released += 1
            except SDKError as exc:
                errors.append(f"{motor.name} torque release: {exc}")
    except SDKError as exc:
        print(f"release failed: {exc}", file=sys.stderr)
        return 1
    finally:
        sdk.disconnect()

    if errors:
        print("release incomplete: " + "; ".join(errors), file=sys.stderr)
        return 1
    print(f"已释放 {released} 个机械臂电机和 3 个底盘轮子扭矩")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
