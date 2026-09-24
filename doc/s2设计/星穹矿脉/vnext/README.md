# S2 vNext：星穹矿脉模拟实验室

这里是 S2 独立实验区，暂不接 NoneBot 或数据库。当前是 schema v3 转生版，内容版本 `prestige-2`，可试玩首星通关、核心强化、连续换星和百万星球终局，并接续十天、旧三十天及 `prestige-1` 存档。

## 运行

```powershell
.venv\Scripts\python.exe zhenxun/plugins/zhenxun_plugin_fishing/doc/s2设计/星穹矿脉/vnext/s2_first_ten_days.py --days 10 --seed 42 --output HELPER_TEN_DAYS_TRACE.md

.venv\Scripts\python.exe zhenxun/plugins/zhenxun_plugin_fishing/doc/s2设计/星穹矿脉/vnext/s2_thirty_days.py --matrix --output

$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
.venv\Scripts\python.exe -m pytest zhenxun/plugins/zhenxun_plugin_fishing/doc/s2设计/星穹矿脉/vnext/test_s2_mining_simulator.py zhenxun/plugins/zhenxun_plugin_fishing/doc/s2设计/星穹矿脉/vnext/test_s2_thirty_days.py zhenxun/plugins/zhenxun_plugin_fishing/doc/s2设计/星穹矿脉/vnext/test_s2_prestige.py -q -p no:cacheprovider

node --test zhenxun/plugins/zhenxun_plugin_fishing/doc/s2设计/星穹矿脉/vnext/s2_engine.test.mjs zhenxun/plugins/zhenxun_plugin_fishing/doc/s2设计/星穹矿脉/vnext/s2_late_factors.test.mjs zhenxun/plugins/zhenxun_plugin_fishing/doc/s2设计/星穹矿脉/vnext/s2_descriptions.test.mjs zhenxun/plugins/zhenxun_plugin_fishing/doc/s2设计/星穹矿脉/vnext/s2_prestige.test.mjs

node zhenxun/plugins/zhenxun_plugin_fishing/doc/s2设计/星穹矿脉/vnext/s2_prestige_replay.mjs --seed 42 --planets 12 --profile daily
node zhenxun/plugins/zhenxun_plugin_fishing/doc/s2设计/星穹矿脉/vnext/s2_prestige_replay.mjs --seed 42 --planets 12 --profile absent --core-route none
.venv\Scripts\python.exe zhenxun/plugins/zhenxun_plugin_fishing/doc/s2设计/星穹矿脉/vnext/s2_mining_simulator.py --seed 42 --planets 12 --profile daily --core-route balanced

.venv\Scripts\python.exe -m http.server 8766 --bind 127.0.0.1 --directory zhenxun/plugins/zhenxun_plugin_fishing/web/static/s2-vnext
```

以上命令从机器人项目根目录运行；端口占用时换用空闲端口。网页与 Python 共用 `game_data.json`，不是两套数值。用时间控制台推进模拟日，不会根据现实关页时长自动补算。

## v3 规则摘要

- 本地货币为矿币；挖穿星球获得星球核心，用于永久科技。
- 一次命令可购买多项多级；网页先显示清单，确认后建设。
- 首星共同完成科技的 3 个调试等级后，本星自动化。每次换星门槛减 1，最低为 0；科技等级、调试与自动线全部清空，须重新付费建设。
- 笨助手默认开启，每个游戏日 00:00 购买便宜的未自动化等级，支付矿币、不留预算；关闭后恢复不补班。
- 首星自动采购每小时最多一级，保护当前最便宜的 3 个调试等级预算。第二、三颗星球每十分钟采购，预算随永久速度提高；第四颗起资金与前置满足即连续采购。零调试门槛从零级自动购买，仍检查矿币、深度、时代与前置科技。
- 每日 3-6 级只是软参考，不设每日上限；等级数、命令数、查看次数分开审计。
- D10 每日一次和全托管画像均应进入电气时代，前三十天经济保留。
- 原始、工业、电气、计算机、未来时代依次换代。D11-D20 延伸电气与计算机设备，D21-D30 建设未来矿场；共 43 项活动科技，`reserve` 不进入试玩建设列表。
- 旧设备满级后保留贡献，由更强新设备接棒。同乘区贡献相加、速度设备分别复乘，不再增加矿网、热回收、级联等复杂公式。
- 批量预览显示矿币收益、挖矿深度提升，回放可选 10/20/30 天；后期大数使用科学计数显示。
- 科技说明解释实际开采作用，用 `**专有名词**` 安全加粗属性与科技引用；不解析 HTML。同类倍率相加与速度逐级复乘分别说明，不把内部加成误写成总收益百分比。
- 首星以未来时代收尾，固定深度目标 `2.4e19`。全部 333 级升满后仍挖约五天，抵达深度才通关；不是满级通关或固定倒计时。
- 转生不再赠送产速。首颗核心可购买行星开采引擎，总倍率 ×1 → ×2；下一级花 3 核心变成 ×3。七项科技共同强化全局产速、速度/收入/深度设备、综合设备与自动线联动；购买永久科技不会免费赠送本地等级。
- 首星完成后停产等待手动启程；之后可自动换星，也可关闭。核心只在挖穿时奖励一次，奖励为 `1 + floor(已转生次数/5)`。核心托管默认关闭，可显式选择均衡或速度路线。
- 第四颗星起连续采购、期望生产；相同永久研究复用航程，买核心科技时从真实边界重算。百万星球完成后停产，未实现超出双精度的大数与正式主游戏奖励。

## 当前验证

固定 seed=42、每天 20:00 操作的手动等级为 `6/2/3/3/3/3/3/3/5/3`，共 34 级；助手 17 级，自动采购 79 级。网页实际十次批量采购与模拟经济结果相同，逐级回放的命令数为 34，网页批量仅 10 条，不能混为一个指标。

三十天每日一次基准累计手动 85、助手 44、自动 186 级。实际网页访问 30 次、批量成交 29 次；D11 无手动采购。D11 后常见每日 2-4 级，D12 为 6 级、D13 为 5 级；五 seed/四路线高频机会峰值 9 级，没有每日限购。每日一次 D15 进入计算机时代、D22 进入未来，全托管约为 D18、D26。

助手版使用独立存档键，原版 v2 存档不套用。十天及旧三十天助手版先备份、补转生字段与目标后继续玩，保留本地状态、随机数与采购时钟。`?sandbox=1` 使用独立验收矿井，不推进用户原页。新存档损坏不能伪装成旧版自动补字段。

- 时间控制区提供“重置测试进度”按钮；确认后会先将当前存档备份到带时间戳的本地键，再用 Seed 输入框开新局。备份失败时取消重置，避免测试操作覆盖当前进度。

离线调参工具 `calibrate_thirty_days.mjs` 默认只输出，显式 `--write` 才写入共享数据。价格一经写入就是固定价格，不随玩家当前收入变化。迁移回归用固定历史提交 `25f9313`，运行测试的克隆需保留该历史对象。

独立测试必须禁用 pytest 插件自动加载，否则 nonebug 会要求正式机器人环境；保留插件 `pytest.ini` 的 `support.pytest_plugin`，不要用空 `addopts` 覆盖，否则测试收集会导入正式 NoneBot 插件。说明测试检查安全渲染、引用名称、数值口径和作用域；转生测试覆盖奖励、清空、自动化、存档、多星步进等价与双端对照。既有早期暴击率封顶造成的末级收益饱和暂保留，避免改动已认可的前十天。

首星历史实验见 `PRESTIGE_PLAYTEST.md`：五 seed 下，每日一次首星约 39.4-40.3 个完整日、助手路线约 43.9 日挖穿，满级后的真实采矿约五日。该报告的转生免费倍率和后续航程数据已被替代，以 `GALAXY_PLAYTEST.md` 为当前版本验收报告。

新增连续航程验收（从项目根目录运行）：

```powershell
node --test zhenxun/plugins/zhenxun_plugin_fishing/doc/s2设计/星穹矿脉/vnext/s2_voyage.test.mjs
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
.venv\Scripts\python.exe -m pytest zhenxun/plugins/zhenxun_plugin_fishing/doc/s2设计/星穹矿脉/vnext/test_s2_voyage.py -q -p no:cacheprovider
node zhenxun/plugins/zhenxun_plugin_fishing/doc/s2设计/星穹矿脉/vnext/s2_galaxy_replay.mjs --profile daily --route balanced
node zhenxun/plugins/zhenxun_plugin_fishing/doc/s2设计/星穹矿脉/vnext/s2_galaxy_replay.mjs --profile absent --route balanced
```

回放从零开始，首星完成后在每日 20:00 确认首次启程并启用核心托管；`absent` 不进行手动本地建设，仍需要这一次人为启程授权。完全不花核心可用 `--route off` 对照。

现行要求见 `DESIGN_INTENT.md`。`THIRTY_DAYS_PLAYTEST.md`、`THIRTY_DAYS_TRACE.md`、`READABLE_TECH_PLAYTEST.md`、`HELPER_PLAYTEST.md` 和 `HELPER_TEN_DAYS_TRACE.md` 保留历史基线；`GAME_DESIGN_VNEXT.md`、`FIRST_TEN_DAYS_TRACE.md`、`NEXT_THREAD_HANDOFF.md` 是更早方案，不作为现行验收标准。
