# S2 vNext：星穹矿脉模拟实验室

这里是推翻旧 S2 方案后的独立实验区。旧版 `GAME_DESIGN*.md`、网页 Demo 和主程序全部保留，vNext 只包含命令行模拟器与数值记录，暂不接入 NoneBot、数据库或 UI。

## 运行

在项目根目录执行：

```powershell
.venv\Scripts\python.exe zhenxun/plugins/zhenxun_plugin_fishing/doc/s2设计/星穹矿脉/vnext/s2_mining_simulator.py scenario --days 45 --target-log10 11
.venv\Scripts\python.exe zhenxun/plugins/zhenxun_plugin_fishing/doc/s2设计/星穹矿脉/vnext/s2_mining_simulator.py repl --target-log10 11
```

`scenario` 当前只审查阶段一：每天分三个 8 小时窗口，每个窗口最多发送一条升级消息，并输出 D1/D2/D3/D7/D11/D15/D20/D25/D30/D37/D45 等观察点。`repl` 支持 `挖矿`、`升级 镐子=2 矿车=1`、`模拟 3`、`状态`。

当前基础工程的首级价格为矿镐 500、矿车 750、矿石精炼 1100、洞穴勘探 1500 矿币。这个价格带有意把第一天拉成长为“先选一条主线、再等自动采购”的节奏；网页原型与模拟器共用这组数值。

前十天固定序列使用 10 分钟步进，自动采购也在每个 10 分钟块结算；玩家每小时作一次批量升级决策。运行 `s2_first_ten_days.py --days 10` 可查看每天的资源、时代、手动购买和科技等级。

## 当前文档

- [GAME_DESIGN_VNEXT.md](./GAME_DESIGN_VNEXT.md)：规则、升级树、玩家体验和外推方法。
- [s2_mining_simulator.py](./s2_mining_simulator.py)：可重复的固定时间步模拟器。
- [test_s2_mining_simulator.py](./test_s2_mining_simulator.py)：硬约束、特殊效果和多 seed 阶段一集成测试（按仓库规则不纳入 Git）。

目标深度参数默认使用 `11` 档，对应校准后的约 `6×10^11` 深度作为可在普通电脑上观察的阶段一曲线；阶段二的 `10^308` 外推暂时冻结，等阶段一签收后再恢复。这个目标只是开发观测线，正式数值仍可继续向 `10^308` 扩展。
