# 机器人节点源码（`src/robots_xlerobot/`）

Python 包名为 `robots_xlerobot`，负责 XLeRobot 双臂、夹爪和三全向轮底盘的 FTServo 接入。

| 模块 | 职责 |
|------|------|
| `config.py` | 总线、电机、关节/轮子顺序、运动学参数、`ActuatorSpec` 和 YAML/JSON 配置 |
| `sdk.py` | 串口生命周期、状态与限位读取、位置/轮速受控写入、失败补偿、ticks 与弧度转换 |
| `driver.py` | 标准 `BaseRobotDriver` 协议：关节状态/位置命令与 `LocomotionCommand` |
| `main.py` | Dora 节点入口，走标准 `run_dora_robot_node` 循环 |
| `_vendor/scservo_sdk/` | 随包提供的飞特 SDK |

## 单位与硬件范围

STS3215 一圈为 4096 ticks，Forge 侧使用弧度。零点和正方向按电机报告寄存器定义，不代表
已经与 URDF/MJCF 坐标对齐。12 个关节状态只包含左右臂和夹爪；头部只读。底盘使用 `vx/vy`（m/s）、`wz`
（rad/s），由驱动转换为右总线 ID 7/8/9 的有符号原始轮速。

## 安装与测试

```bash
python3 -m pip install -e .
python3 -m pytest tests/
```

测试默认使用 FakeSDK，不会自动打开串口。Dora/Forge 适配依赖本地
`forge_msgs`、`forge_robot` 和 `dora`。

## 生命周期

驱动默认为只读（leader）。`--follower` 时，`connect()` 会记录启动位姿并打开串口、
使能 12 个机械臂电机扭矩，并在确认三轮已经是 velocity mode 1 后写零速再使能轮子扭矩；
`disconnect()` 会先停车并释放轮子扭矩，再尝试回到双臂启动位姿并读反馈复检。无论
回位是否成功，驱动都会逐一尝试释放全部机械臂扭矩并报告失败项。leader 全程只读、不写。
非零底盘命令超过配置超时未刷新时，看门狗自动写三轮零速。所有
规划与轨迹编排由上层完成，本节点只做标准消息桥接。
