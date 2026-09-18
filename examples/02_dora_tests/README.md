# 02 — Dora 节点测试

本构型未单独保留 Dora 节点级 dataflow。真机节点为标准 driver（
`robots_xlerobot run --config ... --follower`），由上层 skill 通过 `task_robot`
驱动；仿真链路位于 `examples/03_workflows/simulation/mujoco_Xlerobot/`。

如后续增加独立的节点启停、Topic 或多 `robot_id` 测试，请在本目录登记入口和复现命令。
