# -*- mode: python ; coding: utf-8 -*-
# ruff: noqa: F821
# pyright: reportUndefinedVariable=false, reportMissingModuleSource=false
# 在本包根目录执行：./scripts/build_pyinstaller.sh
# 或：uv run --extra pyinstaller pyinstaller --noconfirm --clean scripts/robots_xlerobot.spec

from __future__ import annotations

import os

from PyInstaller.utils.hooks import copy_metadata

_spec_dir = os.path.dirname(os.path.abspath(SPEC))
_package_dir = os.path.dirname(_spec_dir)
_src_dir = os.path.join(_package_dir, "src")

a = Analysis(
    [os.path.join(_src_dir, "robots_xlerobot", "main.py")],
    pathex=[_src_dir, _package_dir],
    binaries=[],
    datas=copy_metadata("robots-xlerobot"),
    hiddenimports=[
        "robots_xlerobot",
        "robots_xlerobot.config",
        "robots_xlerobot.driver",
        "robots_xlerobot.sdk",
        "robots_xlerobot._vendor.scservo_sdk",
        "robots_xlerobot._vendor.scservo_sdk.port_handler",
        "robots_xlerobot._vendor.scservo_sdk.protocol_packet_handler",
        "robots_xlerobot._vendor.scservo_sdk.scservo_def",
        "robots_xlerobot._vendor.scservo_sdk.sms_sts",
        "robots_xlerobot._vendor.scservo_sdk.scscl",
        "robots_xlerobot._vendor.scservo_sdk.group_sync_read",
        "robots_xlerobot._vendor.scservo_sdk.group_sync_write",
        "typer",
        "click",
        "yaml",
        "pyarrow",
        "numpy",
        "serial",
        "serial.tools.list_ports",
        "forge_common",
        "forge_msgs",
        "forge_robot",
        "forge_robot.node_runner",
        "forge_robot.robot_protocol",
        "forge_robot.actuator_spec",
        "forge_robot.arrow_validation",
        "dora",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="robots_xlerobot",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
