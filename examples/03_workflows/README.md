# 03 — Forge 端到端 workflow

| 类型 | 入口 | 说明 |
|------|------|------|
| 仿真 | `simulation/mujoco_Xlerobot/` | MuJoCo、TaskRobot 和测试动作源 |
| 真机机械臂 | `real_basic_motion/` | 标准节点 + hold/nudge 动作源 |
| 真机底盘 | `real_basic_locomotion/` | 标准节点 + 低速前进后停车的 `LocomotionCommand` 示例 |

## 仿真

仿真模型使用本仓 `assets/mjcf/scene.xml`，模型前缀为 `item_1/`。配置、运行方式和
检查记录见：

- `simulation/mujoco_Xlerobot/README.md`
- `simulation/SIMULATION_INTEGRATION.md`
- `simulation/JOINT_SWEEP_CHECKLIST.md`

## 真机

真机驱动已统一为标准 `robots_xlerobot run` 节点（`BaseRobotDriver` + 标准 Dora
循环），默认只读，`--follower` 才使能扭矩并执行命令。动作编排由 `task_robot` 与
action source 在上层 skill 中完成。

`real_basic_motion/` 提供机械臂最小闭环；`real_basic_locomotion/` 提供底盘低速前进后停车的
标准 `LocomotionCommand` 示例。分别见各目录的 `README.md`。
