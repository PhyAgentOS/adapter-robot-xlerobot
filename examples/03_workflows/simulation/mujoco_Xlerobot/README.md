# MuJoCo + Xlerobot （Forge / dora-rs）

本目录放在 **`examples/03_workflows/simulation/`**，与 Xlerobot 资产、仿真说明同一套工作流；配置对应本仓 **`assets/mjcf/scene.xml`**（`attach` 前缀 `item_1/`）。

## 布局约定

- **`simulator.yaml`** 中 `model_path` 相对本目录指向 **`../../../../assets/mjcf/scene.xml`**（仅依赖本仓，不依赖工作区根）。
- **`dataflow*.yaml`** 里运行时节点（mujoco / task_robot / test_action_source）的 `path` 使用
  **`${FORGE_RUNTIME_ROOT}/packages/nodes/...`** 环境变量引用；运行前需 `export FORGE_RUNTIME_ROOT=<forge_runtime 工作区根>`，
  并已在该根目录执行 `uv sync --all-packages`（与 Forge 框架其他适配仓一致）。

## 约定摘要

- **18 个执行器**：虚拟底盘 3 个 velocity + 六轴机械臂左右各 6 个 position + 底部轮子 3 个 velocity。
- **Action / Proprio 的关节名**：与 MuJoCo joint 名一致（`slide_joint_*`、`hinge_joint_z`、`Rotation_*`、`Pitch_*`、`Elbow_*`、`Wrist_Pitch_*`、`Wrist_Roll_*`、`Jaw_*`、`ST3215_Servo_Motor*`）。

## 运行（test_action_source）

在 **`forge_runtime` 根目录**已执行 `uv sync --all-packages` 的前提下：

```bash
export FORGE_RUNTIME_ROOT=/path/to/forge_runtime
cd examples/03_workflows/simulation/mujoco_Xlerobot
dora build dataflow.test_action_source.yaml --uv
dora run dataflow.test_action_source.yaml --uv
```

（若当前目录已在 `mujoco_Xlerobot` 内，则无需再 `cd`。）

`--joint-order` 须与 `simulator.yaml` / `task_robot.yaml` 中 **joints 列表顺序**一致。

## 与 policy 端到端

可参照本目录 dataflow 自行复制并改 policy 节点、图像边与关节维；policy 侧需 **21** 维并与本目录命名约定一致。
