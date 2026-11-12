# adapter-robot-xlerobot

[English](README.md) | [简体中文](README_zh.md)

## BREAKING CHANGE: Forge 2.x / Dora 1.x migration

This migration from Forge 1.x / Dora 0.4.x requires coordinated deployment. Align the Forge packages, Dora CLI/coordinator/daemon, this node and its peer nodes before connecting a dataflow; replacing only one node in a Forge 1.x deployment is unsupported. Rebuild and redeploy executable artifacts with the matching environment. Keep `stable/1.x` for deployments that still use the previous stack.

The validated Python baseline is `forge-msgs==2.1.0`, `Pillow==13.0.0`, `forge-common==2.1.0`, the applicable `forge-robot` / `forge-policy` / `forge-kinematics` / `forge-tool` packages at `2.0.0`, and `dora-rs==1.0.1`. Respect this repository's Python and SDK platform requirements. Forge package families have independent versions. Rust nodes retain the published `forge_msgs` crate `2.0.0` with Dora `1.0.1`; Python Msgs `2.1.0` does not require a nonexistent Rust `2.1.0` release. The `forge_msgs.v1` message namespace remains unchanged.

This notice describes the deployment break from the previous stack; it does not declare hardware, real-model or sustained-run acceptance complete. See [this round's verification report](migration/msgs-2.1.0-report.json) for actual tests and outstanding gates.

Safe FTServo access for the XLeRobot dual arms and omni base

## Installation

Use Python 3.12 and install the frozen project environment:

```bash
uv sync --frozen
```

Install the project-specific optional SDK or test extras when needed. Hardware SDK and device configuration requirements remain applicable.

## Entrypoints

- `robots-xlerobot`: `robots_xlerobot.main:main`.

Use each entrypoint's `--help` to inspect its options. Review the supplied configurations and robot limits before enabling hardware. Existing assets, workflow examples, calibration and device setup details are preserved in the [Chinese guide](README_zh.md) and repository documentation.

## Validation

Unit tests and simulated backends cover software contracts. Device motion, native SDK operation, model inference and release-artifact validation require their declared environments. A successful build alone does not establish hardware acceptance.

## Forge 2.x migration

This branch prepares node version `2.0.0` for Dora 1.x, frozen to Dora `1.0.1` for migration validation. It uses the official Forge 2.x distributions; Common is at least `2.1.0`. Regenerated locks and all executable entrypoints are part of the change.

Every change report must list repository, changes and test evidence, including per-node `dora run` records and a chained test containing `adapter-forge-gateway`. Unavailable hardware/model checks remain pending. Source PRs do not publish stable releases or synchronize GitLab; synchronization follows full acceptance.
