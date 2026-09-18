#!/usr/bin/env python3
"""Unified XLeRobot entrypoint: the ``run`` dora node.

The node is read-only by default.  Pass ``--follower`` to enable torque and
command execution, mirroring the SO101 / Agilex Piper driver contract.  All
planning, trajectory, and orchestration live outside this node; it only bridges
``JointCommand``, ``JointState`` and ``LocomotionCommand`` with the FTServo buses.
"""

from __future__ import annotations

import sys

import typer
from forge_common import get_logger
from forge_robot.node_runner import run_dora_robot_node

from robots_xlerobot.config import build_robot_config, config_from_file
from robots_xlerobot.driver import XLeRobotDriver

logger = get_logger(__name__)

app = typer.Typer(
    name="robots_xlerobot",
    help="XLeRobot dual-arm omni-base dora node. Read-only by default; pass --follower "
    "to enable torque and command execution.",
    no_args_is_help=False,
)


def _resolve_config(
    config_path: str | None,
    left_port: str | None,
    right_port: str | None,
):
    if config_path and (left_port or right_port):
        typer.echo("--config is mutually exclusive with --left-port/--right-port", err=True)
        raise typer.Exit(1)
    if config_path:
        return config_from_file(config_path)
    if left_port and right_port:
        return build_robot_config(left_port, right_port)
    typer.echo("provide --config <file> or --left-port/--right-port", err=True)
    raise typer.Exit(1)


def _run_node(config, *, is_follower: bool, debug: bool) -> int:
    driver = XLeRobotDriver(config, is_follower=is_follower, auto_connect=True)
    return run_dora_robot_node(
        driver,
        joint_order=driver.joint_order,
        is_follower=is_follower,
        debug=debug,
    )


@app.callback(invoke_without_command=True)
def _main(
    ctx: typer.Context,
    config: str | None = typer.Option(None, "--config", help="YAML/JSON robot config (see config/robot.example.yaml)"),
    left_port: str | None = typer.Option(None, "--left-port", help="left-arm serial device path (by-id recommended)"),
    right_port: str | None = typer.Option(None, "--right-port", help="right-arm serial device path (by-id recommended)"),
    follower: bool = typer.Option(False, "--follower", help="enable torque and execute commands (default read-only)"),
    debug: bool = typer.Option(False, "--debug", help="log action/state samples"),
) -> None:
    """Run the XLeRobot dora node (no subcommand)."""
    if ctx.invoked_subcommand is not None:
        return
    robot = _resolve_config(config, left_port, right_port)
    sys.exit(_run_node(robot, is_follower=follower, debug=debug))


@app.command()
def run(
    config: str | None = typer.Option(None, "--config", help="YAML/JSON robot config (see config/robot.example.yaml)"),
    left_port: str | None = typer.Option(None, "--left-port", help="left-arm serial device path (by-id recommended)"),
    right_port: str | None = typer.Option(None, "--right-port", help="right-arm serial device path (by-id recommended)"),
    follower: bool = typer.Option(False, "--follower", help="enable torque and execute commands (default read-only)"),
    debug: bool = typer.Option(False, "--debug", help="log action/state samples"),
) -> None:
    """Run the XLeRobot dora node."""
    robot = _resolve_config(config, left_port, right_port)
    sys.exit(_run_node(robot, is_follower=follower, debug=debug))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
