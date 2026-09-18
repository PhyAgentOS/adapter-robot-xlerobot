# xlerobot 构型说明

## 构型概览

> 当前仓库在 `assets/mjcf/` 和 `assets/glb/` 中未发现可直接用于 Markdown 的机器人预览图。

XLeRobot 双臂移动操作平台，由轮式底盘、双机械臂和夹爪组成。

- **构型类别**：移动操作机器人

## 支持引擎

| 引擎 | 支持情况 | 依据 |
|---|---|---|
| 真机 | 暂未支持 | 未发现可用的真机驱动或真机工作流 |
| MuJoCo | 支持 | `assets/mjcf/scene.xml` |
| Isaac Sim / Isaac Lab | 暂未支持 | 未发现 Isaac Sim 或 Isaac Lab 工作流 |

## 模型资产

- [`assets/mjcf/scene.xml`](assets/mjcf/scene.xml)
- [`assets/mjcf/xlerobot.xml`](assets/mjcf/xlerobot.xml)
- [`assets/glb/xlerobot.glb`](assets/glb/xlerobot.glb)
- [`assets/glb/xlerobot_robot_mj_model.glb`](assets/glb/xlerobot_robot_mj_model.glb)

> “支持”仅表示仓库中存在对应驱动、模型或可执行工作流；实际运行仍需满足硬件、SDK 与运行环境要求。
