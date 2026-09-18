# 配置与标定

| 文件 | 作用 |
|------|------|
| `robot.example.yaml` | 两条 FTServo 总线、17 个电机和运动参数示例 |
| `calibration/robot_calibration_20260908.json` | 现场标定结果备份 |
| `vr_calibration.yaml.example` | VR / 同构标定模板 |

## 真机配置

优先使用稳定的 `/dev/serial/by-id/...` 路径，并现场确认左右总线：

- `left_bus`：左臂 ID 1–6，头部 ID 7–8；
- `right_bus`：右臂 ID 1–6，底盘轮子 ID 7–9。

在其他机器人上运行时，复制 `robot.example.yaml` 后修改串口路径和运动参数。不要通过
放宽软件限位来掩盖 EEPROM 限位、机械装配或标定问题。驱动默认只读，只有显式传入
`--follower` 才会使能扭矩并执行命令。

## 标定备份

`robot_calibration_20260908.json` 来自官方 XLeRobot 标定流程，覆盖左右臂、夹爪、
头部和轮子共 17 个电机。恢复到 LeRobot 时，应复制为：

`~/.cache/huggingface/lerobot/calibration/robots/xlerobot/my_xlerobot.json`

文件名必须与机器人 `id="my_xlerobot"` 一致。头部第二个电机的 homing offset 接近
有符号回卷边界；使用头部前需单独确认中位方向。机械臂基础 workflow 只控制双臂和
夹爪；头部仍不控制，底盘使用 `real_basic_locomotion` workflow。
