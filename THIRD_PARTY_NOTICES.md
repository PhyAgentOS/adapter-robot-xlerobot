# Third-party notices

The repository's original Python code, configuration, workflows, and
documentation are licensed under Apache License 2.0 unless a file or directory
states otherwise. The following bundled assets and vendored code retain their
upstream licenses.

## XLeRobot model assets

- Paths: `assets/mjcf/`, `assets/glb/`
- Source: [XLeRobot](https://github.com/Vector-Wangel/XLeRobot), commit
  `3d14695e40c9c68229c0aacffca6053c75cd3eb6`
- License: Apache-2.0

The GLB files are converted forms of the MuJoCo model and retain the same
upstream attribution. Local changes include control semantics, cameras,
relative paths, and format conversion; see the README files in each asset
directory for details.

## SCServo SDK (vendored)

- Paths: `src/robots_xlerobot/_vendor/scservo_sdk/`
- Source: [FT-Feetech SCServo SDK](https://github.com/FT-Feetech/SCServo_SDK)
- Copyright: Copyright (c) 2024 ftservo
- License: MIT

The license text is available at
`src/robots_xlerobot/_vendor/scservo_sdk/LICENSE`.

## Runtime dependencies

Python dependencies are not vendored into this repository. Their licenses are
provided by their respective distributions, including:

- `dora-rs`: MIT (according to the installed PyPI distribution metadata)
- `forge-common`, `forge-msgs`, `forge-robot`: see their PyPI distributions
- `pyserial`: BSD-3-Clause
- `PyYAML`: MIT
- `Typer`: MIT
