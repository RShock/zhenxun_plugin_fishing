# S2 vNext：星穹矿脉模拟实验室

这里是 S2 独立实验区，暂不接 NoneBot 或数据库。当前是 schema v3 夜班笨助手版，内容版本 `thirty-day-1`，可试玩首星前三十天，并接续十天助手版存档。

## 运行

```powershell
.venv\Scripts\python.exe zhenxun/plugins/zhenxun_plugin_fishing/doc/s2设计/星穹矿脉/vnext/s2_first_ten_days.py --days 10 --seed 42 --output HELPER_TEN_DAYS_TRACE.md

.venv\Scripts\python.exe zhenxun/plugins/zhenxun_plugin_fishing/doc/s2设计/星穹矿脉/vnext/s2_thirty_days.py --matrix --output

$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
.venv\Scripts\python.exe -m pytest zhenxun/plugins/zhenxun_plugin_fishing/doc/s2设计/星穹矿脉/vnext/test_s2_mining_simulator.py zhenxun/plugins/zhenxun_plugin_fishing/doc/s2设计/星穹矿脉/vnext/test_s2_thirty_days.py -q

node --test zhenxun/plugins/zhenxun_plugin_fishing/doc/s2设计/星穹矿脉/vnext/s2_engine.test.mjs zhenxun/plugins/zhenxun_plugin_fishing/doc/s2设计/星穹矿脉/vnext/s2_late_factors.test.mjs

.venv\Scripts\python.exe -m http.server 8766 --bind 127.0.0.1 --directory zhenxun/plugins/zhenxun_plugin_fishing/web/static/s2-vnext
```

以上命令从机器人项目根目录运行；端口占用时换用空闲端口。网页与 Python 共用 `game_data.json`，不是两套数值。用时间控制台推进模拟日，不会根据现实关页时长自动补算。

## v3 规则摘要

- 唯一资源是矿币。
- 一次命令可购买多项多级；网页先显示清单，确认后建设。
- 玩家与助手共同完成科技的 3 个调试等级后永久自动化。
- 笨助手默认开启，每个游戏日 00:00 购买便宜的未自动化等级，支付矿币、不留预算；关闭后恢复不补班。
- 自动采购使用全局队列，每小时最多一级，保护当前最便宜的 3 个调试等级预算。
- 每日 3-6 级只是软参考，不设每日上限；等级数、命令数、查看次数分开审计。
- D10 每日一次和全托管画像均应进入电气时代；首星通关与第二阶段还未实现。
- D11-D20 延伸电气与现代工程，D21-D30 引入未来联动；共 43 项活动科技，`reserve` 不进入试玩建设列表。
- 批量预览显示收入、钻进提升，回放可选 10/20/30 天；后期大数使用科学计数显示。

## 当前验证

固定 seed=42、每天 20:00 操作的手动等级为 `6/2/3/3/3/3/3/3/5/3`，共 34 级；助手 17 级，自动采购 79 级。网页实际十次批量采购与模拟经济结果相同，逐级回放的命令数为 34，网页批量仅 10 条，不能混为一个指标。

三十天每日一次基准累计手动 84、助手 45、自动 191 级。实际网页访问 30 次、批量成交 29 次；D11 无手动采购。D11 后常见每日 2-4 级，D12 为 6 级；五 seed/四路线高频机会峰值 9 级，没有每日限购。每日一次 D15 进入现代、D22 进入未来，全托管约为 D17、D26。

助手版使用独立存档键，原版 v2 存档不套用。十天助手版先备份、再补新增科技继续玩；`?sandbox=1` 使用独立验收矿井。当前只验证有限路线与前三十天，不代表四个月数值已平衡。托管到未来阶段约晚四天，仍需后续观察。

离线调参工具 `calibrate_thirty_days.mjs` 默认只输出，显式 `--write` 才写入共享数据。价格一经写入就是固定价格，不随玩家当前收入变化。迁移回归用固定历史提交 `25f9313`，运行测试的克隆需保留该历史对象。

现行要求见 `DESIGN_INTENT.md`，本轮结果见 `THIRTY_DAYS_PLAYTEST.md`，逐日审计见 `THIRTY_DAYS_TRACE.md`。`HELPER_PLAYTEST.md` 和 `HELPER_TEN_DAYS_TRACE.md` 保留十天基线；`GAME_DESIGN_VNEXT.md`、`FIRST_TEN_DAYS_TRACE.md`、`NEXT_THREAD_HANDOFF.md` 是更早方案，不作为现行验收标准。
