# XLeRobot 真机基础动作

通过标准 driver 节点（`BaseRobotDriver` + `run_dora_robot_node`）验证真机链路：
使能扭矩、读取状态，并可让单个关节做小幅位置微动。动作源只收发 Dora 消息，不直接
访问串口。

## 效果

1. 节点以 `--follower` 启动，`connect()` 记录启动位姿、使能 12 个机械臂电机，并确认三轮模式后写零速和使能轮子扭矩；
2. 动作源捕获首个状态（12 关节），随后只下发一次「保持当前 + 单关节微动」命令，之后保持静默不再重发；
3. 节点收到 `JointCommand`，`set_command` 裁剪后写入舵机，关节按命令到位。

`--nudge-rad 0.0` 时只 hold 不动（零位移），是验证全链路最安全的第一步。

## 快速运行

```bash
cd robots/xlerobot/examples/03_workflows/real_basic_motion
dora run dataflow.yaml --uv
```

`--uv` 会以本目录的 `pyproject.toml` 为项目根，用 `uv` 自动构建隔离的节点运行环境
（首次运行会自动解析依赖并生成 `.venv`），无需手动激活 venv 或配置绝对路径。
本目录已提交 `uv.lock` 锁定依赖版本；依赖变更后可用 `uv sync` 重新生成。

运行正常后按一次 `Ctrl+C` 停止。节点退出时会**自动停车并释放轮子扭矩，再回到双臂启动位姿、读反馈复检和释放
机械臂扭矩**，无需手动释放。

## 调整微动幅度

编辑 `dataflow.yaml` 中动作源的 `--nudge-rad`（单位弧度），例如：

- `0.0`：只 hold 不动；
- `0.2`：约 11.5° 的可见微动。

`--nudge-joint` 指定要动的关节，默认 `left_arm_shoulder_pan`。幅度必须落在该关节的
实时 EEPROM 限位内（可用 `examples/01_sdk_tests/read_state.py` 查看 min/max）。

## 注意事项

- 必须有人现场值守，托稳双臂，确保完整运动包络净空，并准备好急停或断电手段。
- 运行前确认 `--config` 指向的串口与左右机械臂对应正确；建议复制
  `config/robot.example.yaml` 为 `config/robot.yaml` 后修改路径。
- 不要同时运行 SDK 测试、厂商工具或其他串口客户端。
- 停止 dora 后，follower 会**先停车/释放轮子，再回到双臂启动位姿、复检并释放机械臂扭矩**；若回位/复检失败，
  节点会**保留扭矩**并告警，此时请现场处置（可手动运行
  `examples/01_sdk_tests/release_torque.py` 兜底释放）。
