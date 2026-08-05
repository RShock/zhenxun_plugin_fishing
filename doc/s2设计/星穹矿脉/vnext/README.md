# S2 vNext：星穹矿脉模拟实验室

这里是推翻旧 S2 方案后的独立实验区。旧版 `GAME_DESIGN*.md`、网页 Demo 和主程序全部保留，vNext 包含命令行模拟器、数值记录和独立浏览器原型，暂不接入 NoneBot 或数据库。

## 运行

在项目根目录执行：

```powershell
.venv\Scripts\python.exe zhenxun/plugins/zhenxun_plugin_fishing/doc/s2设计/星穹矿脉/vnext/s2_mining_simulator.py scenario --days 45 --target-log10 11
.venv\Scripts\python.exe zhenxun/plugins/zhenxun_plugin_fishing/doc/s2设计/星穹矿脉/vnext/s2_mining_simulator.py repl --target-log10 11
```

`scenario` 是阶段一长线压力测试，仍保留早期的宽松策略，主要用于观察重生、节点覆盖和特殊效果，不能替代前十天体验验收。`repl` 支持 `挖矿`、`升级 镐子=2 矿车=1`、`模拟 3`、`状态`。

当前基础工程的首级价格为矿镐 500、矿车 750、矿石精炼 1100、洞穴勘探 1500 矿币。这个价格带有意把第一天拉成长为“先选一条主线、再等自动采购”的节奏；网页原型与模拟器共用这组数值。

前十天固定序列使用 10 分钟步进，自动采购也在每个 10 分钟块结算；活跃玩家默认每小时查看一次，但每天最多只能发送三条成功升级消息。运行 `s2_first_ten_days.py --days 10` 会输出每日摘要，并生成 `FIRST_TEN_DAYS_TRACE.md`，记录所有查看、手动升级和自动采购时点。

资源不是展示值：矿币用于全部本地科技；锡矿、铜矿、紫晶、金猫锭和虹核晶分别承担基础、工业、电力、现代、未来及行星科技的材料成本。浏览器原型顶部提供带确认提示的“删档”按钮，便于反复测试本地缓存流程。

## 当前文档

- [GAME_DESIGN_VNEXT.md](./GAME_DESIGN_VNEXT.md)：规则、升级树、玩家体验和外推方法。
- [DESIGN_INTENT.md](./DESIGN_INTENT.md)：不可回归的交互约束、时代节奏和模拟验收标准。
- [NEXT_THREAD_HANDOFF.md](./NEXT_THREAD_HANDOFF.md)：新对话应先阅读的当前状态、未解决问题和下一步顺序。
- [s2_mining_simulator.py](./s2_mining_simulator.py)：可重复的固定时间步模拟器。
- [FIRST_TEN_DAYS_TRACE.md](./FIRST_TEN_DAYS_TRACE.md)：固定 seed=42 的前十天手动与自动升级明细。
- [test_s2_mining_simulator.py](./test_s2_mining_simulator.py)：硬约束、特殊效果和多 seed 阶段一集成测试。
- [tools/APPLY_PATCH_WINDOWS.md](../../../../tools/APPLY_PATCH_WINDOWS.md)：Windows Codex 多行补丁兼容工具说明。

目标深度参数默认使用 `11` 档，对应校准后的约 `6×10^11` 深度作为可在普通电脑上观察的阶段一曲线；阶段二的 `10^308` 外推暂时冻结，等阶段一签收后再恢复。这个目标只是开发观测线，正式数值仍可继续向 `10^308` 扩展，通关天数不设硬限制。
