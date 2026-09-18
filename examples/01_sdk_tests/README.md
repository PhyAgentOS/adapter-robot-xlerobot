# 01 — SDK / 底层最小测试

本目录中的脚本不依赖 Forge/Dora，直接访问两条 FTServo 串口。

| 脚本 | 作用 | 是否写硬件 |
|------|------|------------|
| `read_state.py` | 读取 17 个电机的状态、限位和扭矩，可保存 JSON | 否 |
| `release_torque.py` | 底盘写零速并释放 12 个机械臂和 3 个轮子扭矩 | 是（零速、扭矩关） |

## 环境与配置

在仓库根目录安装包，并确认 `config/robot.example.yaml` 中的左右串口路径正确：

```bash
python3 -m pip install -e .
```

不要同时运行 Dora 节点、厂商工具或其他串口客户端。

## 只读状态

```bash
python3 examples/01_sdk_tests/read_state.py \
  --config config/robot.example.yaml
```

需要保存完整结果时增加 `--output state.json`。该脚本只发送读取指令，不使能电机。

关节位置命令通过标准 Dora 节点下发：

```bash
robots_xlerobot run --config config/robot.example.yaml --follower
```

## 释放扭矩

follower 的 `disconnect()` 会先停止并释放底盘，再尝试回到双臂启动位姿，最后逐一释放机械臂扭矩。
`release_torque.py` 用于以下情况：

- follower 回位、复检或自动释放过程出现错误时的兜底释放；
- leader（只读）模式或其它需要显式释放的场景。

```bash
python3 examples/01_sdk_tests/release_torque.py \
  --config config/robot.example.yaml
```
