#!/usr/bin/env python3
"""Finite low-speed locomotion source for the XLeRobot hardware workflow."""

from __future__ import annotations

import argparse
import math
import sys
import time

from dora import Node
from forge_msgs import LocomotionCommand


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Move XLeRobot base briefly, then stop")
    parser.add_argument("--vx", type=float, default=0.05, help="forward speed in m/s")
    parser.add_argument("--duration-s", type=float, default=2.0, help="motion duration")
    parser.add_argument("--warmup-s", type=float, default=1.0, help="zero-speed warmup")
    args = parser.parse_args()
    for name in ("vx", "duration_s", "warmup_s"):
        value = getattr(args, name)
        if not math.isfinite(value):
            parser.error(f"--{name.replace('_', '-')} must be finite")
    if args.duration_s <= 0.0 or args.warmup_s < 0.0:
        parser.error("--duration-s must be positive and --warmup-s must be non-negative")
    return args


def main() -> int:
    args = parse_args()
    node = Node()
    started_at: float | None = None
    moving_logged = False
    stopped_logged = False

    for event in node:
        if event.get("type") != "INPUT" or event.get("id") != "tick":
            continue
        now = time.monotonic()
        if started_at is None:
            started_at = now
        elapsed = now - started_at

        if elapsed < args.warmup_s:
            vx = 0.0
        elif elapsed < args.warmup_s + args.duration_s:
            vx = args.vx
            if not moving_logged:
                print(
                    f"[locomotion_source] moving vx={args.vx:.3f} m/s "
                    f"for {args.duration_s:.3f}s",
                    file=sys.stderr,
                )
                moving_logged = True
        else:
            vx = 0.0
            if not stopped_logged:
                print("[locomotion_source] zero-speed stop sent", file=sys.stderr)
                stopped_logged = True

        # Keep refreshing the command. During motion this satisfies the driver's
        # watchdog; afterwards repeated zeroes make the stopped state explicit.
        command = LocomotionCommand(vx=vx, vy=0.0, wz=0.0)
        node.send_output("locomotion_command", command.to_arrow())
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
