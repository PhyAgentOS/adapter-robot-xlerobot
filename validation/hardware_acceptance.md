# XLeRobot 真机硬件验收记录

> 本文件是**待填写的现场记录模板**。空项表示尚未在真机上完成，不要据此推断为已通过。
> 只记录实际发生、有反馈证据的结果；计划、dry-run 和命令发送成功都不算运动通过。

记录时间：_（现场填写）_　操作人：_（现场填写）_

## 0. 现场前置确认（运动前必须逐项打勾）

- [ ] 已确认两条总线的稳定 by-id 路径与 `/dev/ttyACM*` 的对应，且权限可读可写。
- [ ] 已现场确认 **left_bus / right_bus 分别对应哪一侧机械臂**，及每个电机 ID 对应哪个关节/夹爪。
- [ ] 手臂处于受支撑姿态，不会在运动或释放扭矩时下坠；现场有可用的断电/急停方式。
- [ ] 已复核当前限位与零位；对越界电机有明确处置，未为了通过而静默放宽限位或覆写零位。

## 1. 只读通信

- [ ] `python examples/01_sdk_tests/read_state.py --output state_<date>.json` 成功，退出码 0。
- [ ] 17 个电机均有有效返回，型号、模式与扭矩使能读数合理。
- [ ] 与历史探针记录对照：位置、限位和零位差异已记录并解释。

保存文件：_（路径）_　差异备注：_（填写）_

## 2. 关节位置命令执行

以 follower 模式启动标准节点（扭矩使能，等待上层 action source 下发命令）：

```bash
robots_xlerobot run --config config/robot.yaml --follower
```

- [ ] 节点以 `--follower` 启动后 12 个运动电机扭矩已使能；不加 `--follower`（默认只读）时扭矩保持关闭。
- [ ] 通过 action source 下发小幅度关节位置命令，各关节按命令到位。
- [ ] 命令与反馈的关节顺序与 `JOINT_ORDER` 一致（左右臂各 6 关节，含夹爪）。
- [ ] 节点停止后 `disconnect` 仅关闭串口，不隐式回位或释放扭矩；现场按需处置。

| 关节 | 命令值 | 反馈值 | 结论/备注 |
|---|---:|---:|---|
| left_arm_shoulder_pan | | | |
| left_arm_shoulder_lift | | | |
| left_arm_elbow_flex | | | |
| left_arm_wrist_flex | | | |
| left_arm_wrist_roll | | | |
| left_arm_gripper | | | |
| right_arm_shoulder_pan | | | |
| right_arm_shoulder_lift | | | |
| right_arm_elbow_flex | | | |
| right_arm_wrist_flex | | | |
| right_arm_wrist_roll | | | |
| right_arm_gripper | | | |

## 3. 已知未做 / 待现场

- [ ] 标定有效性复核与（如需）重标定。
- [ ] 左右臂/夹爪与总线、电机 ID 的机械侧最终确认。
- [ ] 适合首次低速试验的速度/加速度原始值确认。
- [ ] Forge/Dora 真机闭环动作（P4，拟实现）。

## 备注

- 通信丢失时软件无法保证停止；现场人员必须能切断电源。
- 断开串口不是急停。释放扭矩可能使手臂下坠，释放扭矩前务必确保手臂受支撑。
