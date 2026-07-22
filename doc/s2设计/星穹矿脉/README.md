# S2 · 猫猫挖矿（星穹矿脉）

> 状态：**v4 分层无限** · 命令行调参通过 · 网页 Demo 同步
> **完全独立**：不消耗鱼竿，不读写钓鱼金币；无天气/鱼饵/UTR/乐园。

## 一句话

外观与信息结构同构猫猫钓鱼，内核是 **分层矿物 + 各矿独立无限升级 + 3~5 级自动化 + 挖穿重置 + 二阶无限通关**。

## 定案约束

| 项 | 值 |
|----|----|
| 循环 | 挖矿 / 结束挖矿 / 挖矿状态 |
| 手动升级 | 每日最多 3 次，不阻断跨日 |
| 自动升级 | 各矿 Lv.3~5 自动解锁，无需另购 |
| 里程 | 深度达到 `1e28` 挖穿并自动重置 |
| ∞ | 挖穿累积一阶；一阶累计 `1e308` 凝聚二阶 |
| 目标节奏 | 基准策略第 36 日通关 |

## 目录

| 文件 | 说明 |
|------|------|
| [GAME_DESIGN_V4.md](./GAME_DESIGN_V4.md) | v4 权威玩法、数值与 UI 设计（含“无限1 + 无限2”的路线、继承/重置规则、稳定态单循环批量外推与平衡表） |
| [GAME_DESIGN.md](./GAME_DESIGN.md) | v1~v3 历史方案，保留作迁移对照 |
| [demo/sim_v12_layered.py](./demo/sim_v12_layered.py) | v4 命令行模拟与扫参 |
| [demo/sim_v12_result.json](./demo/sim_v12_result.json) | 20 轮、D35 基准结果 |
| [demo/web/](./demo/web/) | 与 v4 参数同步的网页交互 Demo |

## 网页 Demo

```powershell
# 随钓鱼网页端 4159 静态目录访问（已挂隐秘路径）
# http://127.0.0.1:4159/_lab/xqkm/index.html

# 或单独起静态服（可选）
python ".\demo\web\serve.py"
```

源文件与挂载副本：

- 源：`demo/web/{index.html,game_v4.js,style.css}`
- 挂载：`zhenxun_plugin_fishing/web/static/_lab/xqkm/`

## 与旧版

v0.x「破界指数轮回」及 v3 的 16 项公共采购不再作为权威。合理旧内容——三指令、五档矿物、log10 大数和批量结算——已吸收到 v4。

## 与 S1

S1 索引见 `doc/S1设计/README.md`（猫猫乐园）。S2 与钓鱼经济 **零联动**。
