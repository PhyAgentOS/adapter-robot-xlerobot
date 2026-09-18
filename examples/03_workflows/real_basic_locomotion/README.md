# XLeRobot 底盘基础运动

该 workflow 通过标准 Forge `LocomotionCommand` 连接 Dora、XLeRobot driver、飞特 SDK
和三全向轮。示例先保持零速 1 秒，再以 `0.05 m/s` 前进 2 秒，随后持续发送零速。

## 接口约定

- `vx`、`vy` 的单位为 m/s，`wz` 的单位为 rad/s；
- 正 `vx` 表示机器人向前，对应左轮正转、右轮反转，后轮保持近似静止；
- 三轮顺序为 `base_left_wheel`、`base_back_wheel`、`base_right_wheel`；
- 速度先按 Forge 配置限幅，再由驱动转换为飞特电机的原始轮速。

## 运行

核对 `config/robot.example.yaml` 中的串口路径，确认右总线 ID 7、8、9 分别对应三只
底盘轮子，并确保它们处于 velocity mode 1。运行前保持机器人周围无障碍，并准备好
可直接切断电源的方式。

```bash
cd examples/03_workflows/real_basic_locomotion
dora run dataflow.yaml --uv
```

示例的理论直线位移为 10 cm；实际距离会受有效轮径、地面摩擦和轮胎打滑影响。
按 `Ctrl+C` 退出后，驱动会再次写入三轮零速并释放轮子扭矩。

## 安全行为

- 驱动不调用 `WheelMode`，不会修改 EEPROM；轮子模式不匹配时拒绝写入；
- 非零命令超过 `locomotion_command_timeout_s` 未刷新时，watchdog 自动停车；
- 三轮批量写入中任一项失败时，SDK 会尝试向全部轮子补偿写零；
- `--follower` 会使能机械臂扭矩并记录启动位姿。退出时先处理底盘，再尝试机械臂回位；
  无论回位是否成功，都会逐一尝试释放全部机械臂扭矩。
