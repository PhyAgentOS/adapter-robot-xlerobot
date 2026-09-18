# 脚本

## 常规使用

| 脚本 | 作用 |
|------|------|
| `verify_mjcf.py` | 校验 MJCF 可加载并打印关节摘要 |
| `build_glb_robot_asset_pipeline.sh` | 调用 `robot_asset_pipeline` 输出到 `assets/glb/`（`Xlerobot.glb`、`Xlerobot.xml`、`meshes/`；默认 `--skip-preview`） |

## 历史导入工具

以下脚本用于追溯或必要时重新导入外部资产。当前 Xlerobot 资产已经落盘到本仓，常规开发、CI 与仿真示例不再依赖 `robot-mj-model` 仓库。

| 脚本 | 作用 |
|------|------|
| `sync_mjcf_from_robot_mj_model.sh` | 从 `robot-mj-model/models/Xlerobot` 导入到 `assets/mjcf/`（排除 `*.glb`，protect `README.md`） |
| `sync_glb_from_upstream.sh` | 从外部 Xlerobot 资产源拷贝所有 `*.glb` 到 `assets/glb/`（保持相对路径；源目录用 `ELFIN5L_MJCF_SRC`） |

打包、部署脚本可在接入 Forge 后补充（例如调用各仓已有 PyInstaller / Docker 流程）。
