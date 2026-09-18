#!/usr/bin/env python3
"""Minimal hold/nudge action source for XLeRobot bring-up.

Reads the first state message, then sends a single position command that holds
every joint at that captured value, optionally nudging one joint by a small
delta, then stays silent so the servos finish the move without re-commanding.
Every target is derived from the live reported state, so it never commands an
arbitrary absolute pose.
"""

from __future__ import annotations

import argparse
import sys

from dora import Node
from forge_msgs import JointCommand, JointState


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="XLeRobot hold/nudge action source")
    parser.add_argument(
        "--nudge-joint",
        default=None,
        help="joint to nudge (default: none, hold only)",
    )
    parser.add_argument(
        "--nudge-rad",
        type=float,
        default=0.0,
        help="nudge delta in radians (default 0.0 = hold only)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    node = Node()
    baseline: JointState | None = None
    sent = 0

    for event in node:
        if event.get("type") != "INPUT":
            continue
        input_id = event.get("id")

        if input_id == "state" and baseline is None:
            try:
                baseline = JointState.from_arrow(event.get("value"))
            except Exception as exc:  # noqa: BLE001
                print(f"[action_source] bad state: {exc}", file=sys.stderr)
                continue
            print(
                f"[action_source] captured baseline: {len(baseline.name)} joints",
                file=sys.stderr,
            )
            continue

        if input_id != "tick" or baseline is None:
            continue

        if sent > 0:
            continue  # already commanded; hold without re-sending

        positions = list(baseline.position)
        if args.nudge_joint is not None:
            if args.nudge_joint not in baseline.name:
                print(
                    f"[action_source] unknown nudge joint {args.nudge_joint!r}",
                    file=sys.stderr,
                )
                return 2
            idx = baseline.name.index(args.nudge_joint)
            positions[idx] += args.nudge_rad

        command = JointCommand(
            name=list(baseline.name), mode="position", position=positions
        )
        node.send_output("action", command.to_arrow())
        sent += 1
        print(
            f"[action_source] sent command "
            f"nudge_joint={args.nudge_joint} nudge_rad={args.nudge_rad}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
