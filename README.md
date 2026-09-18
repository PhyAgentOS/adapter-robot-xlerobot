# XLeRobot（Forge 机器人交付包）

[查看机器人构型说明](description.md)

## 交付内容

| 内容 | 路径 |
|------|------|
| **MJCF + meshes** | `assets/mjcf/`，仿真入口为 `scene.xml`，主模型为 `xlerobot.xml` |
| **GLB / 可视化资产** | `assets/glb/xlerobot.glb`，由 `robot_asset_pipeline` 生成 |
| **仿真配置示例** | `examples/03_workflows/simulation/mujoco_Xlerobot/` |
| **真机机器人节点** | `src/robots_xlerobot/` |
| **真机机械臂基础动作** | `examples/03_workflows/real_basic_motion/` |
| **真机底盘最小动作** | `examples/03_workflows/real_basic_locomotion/` |
| **配置与标定** | `config/` |

`forge_runtime` 当前没有内置 XLeRobot 专用 MuJoCo 示例。本仓提供的仿真 workflow
直接使用 `assets/mjcf/scene.xml`；真机节点为标准 driver，通过 `task_robot`
交换标准关节状态和动作消息。

## 真机机器人契约

- 两条 FTServo 串口总线共识别 17 个电机：左右臂及夹爪各 6 个位置模式电机，2 个头部
  电机只读诊断，右总线 ID 7/8/9 是可控的三全向轮。
- Forge 侧的 12 个运动关节顺序由 `src/robots_xlerobot/config.py` 中的
  `JOINT_ORDER` 定义。
- STS3215 的位置单位为一圈 4096 ticks；节点转换为弧度时使用“寄存器值增加为正方向”。
  该坐标不等同于已对齐的 URDF/MJCF 零位，夹爪位置也不是米制开口。
- 底层串口实现基于随包 vendor 的飞特 `scservo_sdk`；来源和版本见
  `src/robots_xlerobot/_vendor/SOURCE.md`。

### 移动底盘合同

节点接受标准 Forge `locomotion_command` 输入（`forge_msgs.LocomotionCommand`）：
`vx`、`vy` 分别为机体坐标系的前向和横向速度（m/s），`wz` 为角速度（rad/s）。
三轮顺序固定为 `base_left_wheel`、`base_back_wheel`、`base_right_wheel`；正 `vx`
对应机器人向前，驱动按三全向轮模型换算为有符号原始轮速。

命令先经过 Forge 限速，再按 `wheel_max_speed_raw` 整体等比例缩放。驱动不会修改轮子
EEPROM 模式；三个轮子必须预先处于 velocity mode 1。非零命令由 watchdog 监控，
显式零命令和 `disconnect()` 都会向三轮写零速并释放轮子扭矩。

## 目录结构

| 路径 | 说明 |
|------|------|
| `assets/mjcf/` | MJCF、mesh、`scene.xml` 和模型图片 |
| `assets/glb/` | Web / 可视化 GLB |
| `assets/urdf/` | URDF 预留目录；当前未提供可用 URDF 模型 |
| `config/` | 真机串口配置、标定备份和 VR 标定模板 |
| `examples/01_sdk_tests/` | 不依赖 Forge/Dora 的串口只读与基础运动脚本 |
| `examples/02_dora_tests/` | Dora 节点级测试占位说明 |
| `examples/03_workflows/` | Forge/Dora 仿真与真机 workflow |
| `src/robots_xlerobot/` | SDK、驱动和 Dora 节点源码 |
| `scripts/` | 资产校验、生成和历史导入工具 |

## 资产状态

XLeRobot 的 MJCF、mesh 与 GLB 已落盘到本仓，常规仿真不依赖外部
`robot-mj-model` 仓库：

- `assets/mjcf/scene.xml`：MuJoCo 场景入口，模型前缀为 `item_1/`；
- `assets/mjcf/xlerobot.xml`：机器人主体模型；
- `assets/glb/xlerobot.glb`：Web / 可视化资产；
- `assets/urdf/`：当前仅保留目录说明。

## 仿真接入流程

仿真配置位于 `examples/03_workflows/simulation/mujoco_Xlerobot/`，其
`simulator.yaml` 指向本仓 `assets/mjcf/scene.xml`。分步说明和检查记录见：

- `examples/03_workflows/simulation/SIMULATION_INTEGRATION.md`
- `examples/03_workflows/simulation/JOINT_SWEEP_CHECKLIST.md`

## `src/` 与 Forge 节点

Python 包名为 `robots_xlerobot`。其中 `sdk.py` 管理串口和寄存器读写，
`driver.py` 实现标准 `BaseRobotDriver` 协议（关节消息与 `LocomotionCommand` 桥接），`main.py` 提供 Dora
节点入口（标准 `run_dora_robot_node` 循环）。真机 workflow 的动作源只收发 Dora
消息，不直接访问串口。

安装、模块职责和离线测试命令见 `src/README.md`。直连 SDK 用法见
`examples/01_sdk_tests/README.md`；真机节点运行：
`robots_xlerobot run --config config/robot.example.yaml --follower`；机械臂最小真机闭环见
`examples/03_workflows/real_basic_motion/README.md`；底盘最小链路验证见
`examples/03_workflows/real_basic_locomotion/README.md`。

## 功能范围

- 支持 17 个电机的状态读取和 12 个机械臂/夹爪关节的位置命令；
- 支持通过标准 `LocomotionCommand` 控制三全向轮底盘；
- 提供机械臂和底盘的最小真机 workflow；
- 相机、遥操/同构、VR、VLA、录制与回放不在当前基础接入范围内。
