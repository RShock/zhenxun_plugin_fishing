# S2 vNext：星穹矿脉模拟实验室

这里是推翻旧 S2 方案后的独立实验区。旧版 `GAME_DESIGN*.md`、网页 Demo 和主程序全部保留，vNext 只包含命令行模拟器与数值记录，暂不接入 NoneBot、数据库或 UI。

## 运行

在项目根目录执行：

```powershell
.venv\Scripts\python.exe zhenxun/plugins/zhenxun_plugin_fishing/doc/s2设计/星穹矿脉/vnext/s2_mining_simulator.py scenario --days 60 --target-log10 9
.venv\Scripts\python.exe zhenxun/plugins/zhenxun_plugin_fishing/doc/s2设计/星穹矿脉/vnext/s2_mining_simulator.py repl --target-log10 9
```

`scenario` 使用一个保守的每日策略并输出 D1/D2/D3/D7/D11/D15/D20/D25/D30/D37/D45/D50 等观察点。`repl` 支持 `挖矿`、`升级 镐子=2 矿车=1`、`模拟 3`、`外推 308`、`状态`。

## 当前文档

- [GAME_DESIGN_VNEXT.md](./GAME_DESIGN_VNEXT.md)：规则、升级树、玩家体验和外推方法。
- [s2_mining_simulator.py](./s2_mining_simulator.py)：可重复的固定时间步模拟器。
- [test_s2_mining_simulator.py](./test_s2_mining_simulator.py)：四条硬约束与首轮体验窗口测试。

目标深度默认使用 `10^9` 作为可在普通电脑上观察的开发曲线；`10^308` 只进入对数外推，不会申请一个巨大的 Python 整数或循环 `10^308` 次。
