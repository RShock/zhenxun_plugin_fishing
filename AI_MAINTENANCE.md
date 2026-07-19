# 钓鱼插件 AI 维护文档

> **用途**：AI 编码助手在修改此插件前/后的必读参考。
> **维护规则**：添加新功能或修改业务逻辑后，必须同步更新本文档。
> **通用备注**：每次修改项目均需要同时同步到网页端 `web/static/help.html`，以及文档 `doc.md`。只需要语法检查。

---

## 文档维护规范（强制）

### 单一事实源（SSOT）
- **本文件（`AI_MAINTENANCE.md`）是 AI 维护的唯一权威入口**。
- 其他文档（`DESIGN.md` / `PLAY_GUIDE.md` / `doc/` 等）可以存在，但**不得与本文件冲突**。
- 若发现冲突：以代码与本文件为准，并立刻修正过时文档。

### 何时必须更新文档
完成任何代码改动后，如果触及以下任一项，**必须同步更新文档**（同一次提交内完成）：
1. 命令入口 / 匹配规则变化
2. 数值、概率、掉落、价格、限制变化
3. 结算链路或状态机变化
4. 数据模型字段变化
5. 已知坑点 / 回归点变化
6. 目录结构或关键文件职责变化

### 文档更新最小清单
每次改动至少检查并更新：
1. `AI_MAINTENANCE.md`（本文件）对应章节
2. 如影响玩家可见行为：`PLAY_GUIDE.md`
3. 如影响设计口径：`DESIGN.md` 或 `doc/` 中对应设计文档
4. 如修复历史坑点：把“坑点 + 正确做法”写回本文件

## Git 仓库同步（强制）

> **每次修改完成后，必须将改动提交并 push 到 GitHub 仓库。**  
> 仓库：`https://github.com/RShock/zhenxun_plugin_fishing`  
> 本地仓库根目录即本插件目录：`zhenxun/plugins/zhenxun_plugin_fishing/`

### 适用范围
- 代码、配置、资源、测试、文档、CI 配置等**任何会落盘的改动**
- 包括“只改文档”“只改测试”“只删文件”等看似很小的变更
- **禁止**只改本地、不上传；**禁止**攒一批改动很久才 push

### 标准流程（每次任务结束前执行）
1. 确认改动范围：`git status`
2. 只 stage 本插件相关文件：`git add ...`（遵守 `.gitignore`）
3. 写清楚的 commit message（说明“改了什么 / 为什么”）
4. `git commit`
5. `git push origin main`（或当前工作分支）
6. 一般小改动在本地运行 Python 编译检查即可；push 后无需等待或核验远端 GitHub Actions

### 验证等级
- **一般小改动**：运行 `python -m compileall`，确认编译成功后 commit + push；不等待、不查询远端 CI。
- **较大或高风险改动**：涉及数据库结构、核心结算链路、概率算法、大范围重构，或用户明确要求时，再运行相关 pytest；必要时检查远端 CI。
- 无论采用哪一级验证，commit + push 都是任务完成前的必需步骤。

### 提交信息建议
- 功能：`feat: ...`
- 修复：`fix: ...`
- 文档：`docs: ...`
- 测试/CI：`test:` / `ci:`
- 重构：`refactor: ...`

### 失败兜底
- 若 `git push` 因网络/协议失败：优先重试；仍失败时可用 GitHub API 同步（保持远程与本地一致）
- 仅在本次任务明确要求检查 CI 时，CI 失败才需要继续修复或记录阻塞原因

### AI 执行约定
- 用户未特别声明“先别推”时，**默认改完即 commit + push**
- 一般小改动 push 完成后，在回复中给出提交摘要与本地编译检查结果；不主动查询远端 CI

## CI / GitHub Actions（免费）

> 本仓库已配置**免费** GitHub Actions，用于在每次 push / PR 时自动跑插件内全部 pytest。

### 能力与边界
- **能跑**：`tests/` 下插件单元测试 / 回归测试（轻量 NoneBot 桩，不启动真实 bot）
- **不跑**：完整 bot 仓 `tests/integration`（需要真实 NoneBot + Playwright + 全量依赖；仍在 bot 仓本地/另配 CI 验证）
- **费用**：公开仓库的 GitHub Actions 分钟数免费；私有仓有免费额度，超出才计费

### 关键文件
| 路径 | 作用 |
|------|------|
| `.github/workflows/tests.yml` | CI 工作流：checkout → Python 3.11 → 装依赖 → 准备导入路径 → collect → 跑全量测试 |
| `requirements-ci.txt` | CI 最小依赖（pytest / pydantic / Jinja2 / Pillow / aiohttp / tortoise-orm） |
| `pytest.ini` | `pythonpath` + `confcutdir=.`，防止污染完整 bot 仓 conftest |
| `conftest.py`（仓库根） | 导入前安装 `ci/support/nonebot_stub.py` |
| `ci/setup_path.py` | 构造 `zhenxun.plugins.zhenxun_plugin_fishing` 导入布局 |
| `ci/support/nonebot_stub.py` | 独立仓用轻量 NoneBot / Zhenxun 桩 |

### 触发条件
- `push` 到 `main` / `master`
- 任意 `pull_request`
- 手动 `workflow_dispatch`

### 本地复现 CI
```powershell
cd <本插件根目录>
python -m venv .ci_venv
.\.ci_venv\Scripts\python.exe -m pip install -r requirements-ci.txt
.\.ci_venv\Scripts\python.exe ci\setup_path.py
$env:PYTHONPATH = "$PWD\ci\runtime;$PWD\ci;$PWD"
$env:ZX_LIGHTWEIGHT_NONEBOT_STUBS = "1"
.\.ci_venv\Scripts\python.exe -m pytest tests --confcutdir=.
```

### CI 失败处理
1. 在 GitHub → Actions 查看失败日志
2. 本地按「本地复现 CI」复现
3. 修到绿后再次 commit + push（遵循上文「Git 仓库同步」）

## 一、测试文件位置清单

修改代码前，AI 必须先查出所有相关测试并运行验证。以下为全部测试文件位置：

### 1.1 插件内单元测试（纯逻辑、不依赖渲染）

```
r:\zhenxun_bot\zhenxun\plugins\fishing\tests\
├── conftest.py                    # mock fixture：DB 模型、nonebot、logger、Playwright
├── mock_db.py                     # 内存 SQLite 模拟数据库
├── test_config_and_logic.py       # 稀有度概率、_apply_duoduo、_cap_rarity、_catch_fish_with_buffs
├── test_backpack.py               # 背包模块（卖鱼、赠送等）
├── test_fishing.py                # 钓鱼流程（start/stop/status）
├── test_shop.py                   # 商店模块
├── test_fixes.py                  # 回归修复验证
├── test_regex_patterns.py         # 正则匹配模式测试
├── test_fish_selection.py         # 鱼获选择解析（parse_fish_selection）
├── test_achievement_gold.py       # 成就和金币系统
├── test_lost_wind.py              # 迷途风天气逻辑
└── cat_park_sim/simulation.py     # 猫公园模拟测试
```

**运行方式（完整 bot 仓库）**：
```powershell
cd C:\Users\Administrator\Desktop\zhenxun_bot-420
.venv\Scripts\python.exe -m pytest zhenxun\plugins\zhenxun_plugin_fishing\tests -q
```

**运行方式（独立插件仓库 / 与 GitHub CI 一致）**：
```powershell
cd C:\Users\Administrator\Desktop\zhenxun_bot-420\zhenxun\plugins\zhenxun_plugin_fishing
python ci\setup_path.py
$env:PYTHONPATH = "$PWD\ci\runtime;$PWD\ci;$PWD"
$env:ZX_LIGHTWEIGHT_NONEBOT_STUBS = "1"
python -m pytest tests -q
```

> 注意：插件内单元测试默认使用轻量 NoneBot 桩，不启动真实 NoneBot。  
> - 完整 bot 仓：根 `tests/support/nonebot_stub.py`  
> - 独立插件仓 / CI：本仓 `ci/support/nonebot_stub.py`（`tests/conftest.py` 会自动回退）  
> 真实 NoneBot 行为仍放在 bot 仓 `tests/integration` 验证，不在本插件仓 CI 内。

### 1.2 集成测试（真实环境，fishing 文件夹外）

```
r:\zhenxun_bot\tests\integration\
├── test_fishing.py                # ⭐ 钓鱼集成测试（6个场景，见下文）
├── test_sign_in.py                # 签到流程测试
├── runner.py                      # 集成测试运行器脚本
├── conftest.py                    # 集成测试 fixture（真实 NoneBot + Playwright + SQLite :memory:）
└── test_data/
    ├── __init__.py
    └── seeds.py                   # 数据库预播种数据
```

**运行方式**：
```powershell
# 全部集成测试
uv run pytest tests/integration/ -s -v

# 单个测试场景
uv run pytest tests/integration/test_fishing.py::test_cat_weather_scenario -s -v
uv run pytest tests/integration/test_fishing.py::test_rollback_potion -s -v
uv run pytest tests/integration/test_fishing.py::test_lucky_potion_double_roll -s -v

# 通过 runner.py
uv run python tests/integration/runner.py
```

### 1.3 全局测试配置

```
r:\zhenxun_bot\tests\
├── conftest.py                    # 全局 conftest（nonebot.init + onebot v11 adapter + logger mock）
├── config.py                      # 测试用户/群/Bot ID 常量
├── utils.py                       # 测试工具函数
└── pyproject.toml / pytest.ini   # pytest 配置
```

### 1.4 集成测试场景清单 (`tests/integration/test_fishing.py`)

| 场景 | 函数名 | 测试内容 |
|------|--------|----------|
| 场景1 | `test_scenario_1_create_account` | 创建钓鱼账号 → 验证初始属性 |
| 场景2 | `test_scenario_2_add_time_potions` | gm_add_item 塞入10瓶时光药水 |
| 场景3 | `test_scenario_3_use_time_potion` | 出竿 → 时光药水模拟3小时 → 验证鱼获 |
| 场景4 | `test_scenario_4_stop_fishing` | 出竿 → GM模式收杆 → 验证鱼获 |
| 场景5 | `test_scenario_5_verify_backpack` | 完整流程：创建→出竿→药水→收杆→验证 |
| 猫天气 | `test_cat_weather_scenario` | 1h猫天气 + 25瓶药水(200h) → 验证猫吃鱼、猫猫框保底 |
| 回档药水 | `test_rollback_potion` | 钓鱼→药水积累→回档→验证清空 |
| 幸运药水 | `test_lucky_potion_double_roll` | 使用幸运药水→验证双次结算buff→回档不消除buff |
| 天气预报 | `test_weather_forecast_matcher` | 正则匹配 + 渲染验证 |

---

## 二、功能清单与实现映射

### 2.1 用户命令 → Handler → 业务逻辑对照

> 所有用户输入通过 `matchers.py` 的正则匹配，分发到 `handlers/` 各自处理，最终调用业务逻辑层。

| 用户命令 | Matcher 变量 | Handler 文件 | 业务逻辑入口 |
|----------|-------------|-------------|-------------|
| `钓鱼 [编号]` / `抛竿` | `fishing_matcher` | `handlers/fishing.py` | `core/actions.py` → `start_fishing` |
| `收杆` / `收线` | `stop_fishing_matcher` | `handlers/fishing.py` | `core/actions.py` → `stop_fishing` |
| `钓鱼状态` | `status_matcher` | `handlers/fishing.py` | `core/actions.py` → `check_fishing_status` |
| `背包` | `backpack_matcher` | `handlers/backpack.py` | `backpack/view.py` → `get_backpack_image` |
| `卖鱼 [参数]` | `sell_fish_matcher` | `handlers/backpack.py` | `backpack/sell.py` → `sell_fish` |
| `锁鱼 [参数]` | `lock_fish_matcher` | `handlers/backpack.py` | `backpack/lock.py` → `lock_fish` |
| `解锁 [参数]` | `unlock_fish_matcher` | `handlers/backpack.py` | `backpack/lock.py` → `unlock_fish` |
| `赠送 [参数]` / `送鱼` | `gift_fish_matcher` | `handlers/backpack.py` | `backpack/gift.py` → `gift_fish` |
| `自动卖鱼 [参数]` | `auto_sell_matcher` | `handlers/backpack.py` | 自动卖鱼设置 |
| `鱼店` / `鱼币商店` | `shop_matcher` | `handlers/shop.py` | `shop/view.py` → `get_shop_image` |
| `鱼店购买 [物品] [数量]` | `buy_matcher` | `handlers/shop.py` | `shop/purchase.py` → `buy_item` |
| `升级钓竿` / `升级鱼竿` | `upgrade_rod_matcher` | `handlers/shop.py` | `shop/purchase.py` → `upgrade_rod` |
| `升级鱼钩` / `升级钓钩` | `upgrade_hook_matcher` | `handlers/shop.py` | `shop/purchase.py` → `upgrade_hook` |
| `升级展示栏` / `增加展示栏位` / `强化展示栏位` | `display_slot_matcher` | `handlers/shop.py` | `shop/purchase.py` → `upgrade_display_slots` |
| `打窝 [次数]` | `nest_matcher` | `handlers/shop.py` | `shop/nest.py` → `do_nest` |
| `钓鱼币兑换 [数量]` | `exchange_matcher` | `handlers/shop.py` | `shop/misc.py` → `exchange_to_gold` |
| `钓鱼改名 [名字]` | `rename_matcher` | `handlers/shop.py` | `shop/misc.py` → `rename_fishing_user` |
| `更换皮肤 [皮肤ID]` | `skin_matcher` | `handlers/shop.py` | `shop/misc.py` → `change_skin` |
| `钓鱼图鉴` / `图鉴` / `查看图鉴` | `collection_matcher` | `handlers/backpack.py` | `backpack/view.py` → `get_collection_image` |
| `天气预报` / `钓鱼天气` / `天气` / `天气状态` | `weather_forecast_matcher` | `handlers/misc.py` | `render/` → `render_weather_forecast` |
| `钓鱼使用 [物品] [数量]` | `use_item_matcher` | `handlers/shop.py` | 药水使用分发 |
| `gm收杆` | `gm_force_stop_matcher` | `handlers/gm.py` | `core/actions.py` → `stop_fishing(gm_mode=True)` |
| `gm钱钱` | `gm_money_matcher` | `handlers/gm.py` | gm 添加金币 |
| `gm发钱 [数量]` | `gm_give_gold_matcher` | `handlers/gm.py` | gm 添加金币 |
| `gm添加皮肤 [名称]` | `gm_add_skin_matcher` | `handlers/gm.py` | gm 皮肤管理 |
| `gm添加 [物品] [数量] [QQ/全服/@]` | `gm_add_item_matcher` | `handlers/gm.py` | `gm.gm_add_item`（支持 QQ 批量，无需@） |
| `gm设定金钱 [用户] [数量]` | `gm_set_gold_matcher` | `handlers/gm.py` | gm 设定金币 |
| `gm发鱼 [数量]` | `gm_give_fish_matcher` | `handlers/gm.py` | gm 发放鱼 |
| `gm回退鱼竿 [编号]` | `gm_rollback_rod_matcher` | `handlers/gm.py` | gm 降级鱼竿 |
| `gm回退鱼钩 [编号]` | `gm_rollback_hook_matcher` | `handlers/gm.py` | gm 降级鱼钩 |
| `gm天气` | `gm_weather_info_matcher` | `handlers/gm.py` | gm 天气信息 |
| `gm天气重置` | `gm_weather_reset_matcher` | `handlers/gm.py` | gm 重置天气 |
| `gm限流开启` | `gm_limit_on_matcher` | `handlers/gm.py` | 开启群聊收杆/钓鱼状态每日限流 |
| `gm限流关闭` | `gm_limit_off_matcher` | `handlers/gm.py` | 关闭群聊收杆/钓鱼状态每日限流（无限次） |
| `清空钓鱼数据 [用户]` | `gm_reset_matcher` | `handlers/gm.py` | gm 数据重置 |
| `测试渲染 [参数]` | `test_render_matcher` | `handlers/gm.py` | 渲染测试 |
| `钓鱼调试 [开关]` | `debug_render_matcher` | `handlers/gm.py` | 调试模式开关 |

### 2.2 天气系统

**类型常量**（`constants.py` → `WEATHER_EMOJI` / `WEATHER_NAME` / `WEATHER_EFFECT_DESC`）：

| 类型 | 中文名 | 图标 | 效果 | 实现位置 |
|------|--------|------|------|---------|
| `sunny` | 晴天 | ☀️ | 无特殊效果 | — |
| `rain` | 雨天 | 🌧️ | 上鱼速度+10% | `FishingBuffCalculator.get_effects_at_time` → `weather_speed_multiplier=1.1` |
| `meteor` | 流星 | 🌠 | 最高稀有度+2% | `apply_meteor_effect()` — 最高非零稀有度概率+2%，次高-2% |
| `storm` | 暴雨 | ⛈️ | 鱼饵消耗减半 | `weather_half_bait=True` — 每次消耗50%概率 |
| `lost_wind` | 迷途风 | 🌀 | 有概率UTR | `weather_lost_wind=True` — UTR 0.85%概率，150抽保底 |
| `cat` | 猫！ | 🐱 | 随机吃鱼 | `weather_cat_eat=True` — 15%概率猫吃鱼(CAT_EAT_CHANCE=0.15) |

**关键文件**：
- 定义：`constants.py`（常量）、`weather_service.py`（生成逻辑）、`models/weather.py`（数据模型）
- 效果计算：`models/buff.py` → `FishingBuffCalculator.get_effects_at_time`
- 天气生成：`weather_service.py` → `generate_daily_weather`、`ensure_weather_generated`
- 定时生成：`scheduler.py` → `_scheduled_weather_generation`（cron 每日 0:00）

**迷途风互斥可见性**：迷途风状态下，仅已解锁迷途风的玩家能看到其他已解锁玩家，未解锁玩家只能看到未解锁玩家。实现于 `core/scene.py` → `render_scene`。

### 2.3 猫天气系统

**触发条件**：天气类型为 `cat` 时，鱼被吃概率 `CAT_EAT_CHANCE = 0.15`（15%）。

**猫礼物概率**（`core/cat.py` → `process_cat_gift`）：

| 结果 | 概率 | 产物 |
|------|------|------|
| 金币 | 30% | 鱼的价格一半等值金币 |
| 猫猫框保底 | 满15次 | 1个猫猫框（`CAT_FRAME_PITY_THRESHOLD=15`） |
| 猫猫框 | 15%（非保底） | 1个猫猫框 |
| 鱼饵 | 15% | 3个当前鱼饵 |
| 香甜玉米 | 30% | 1个玉米 |
| 送鱼 | ~10% | 随机送一条未收集的鱼（优先）或最贵的鱼 |

> 累计获得猫猫框概率：吃鱼概率(15%) × 猫猫框概率(15%) = 2.25%

**猫猫框用途**：强化展示栏，使该栏位收益3倍。强化消耗表见 `constants.py` → `UPGRADE_DISPLAY_COSTS`。

**关键文件**：`core/cat.py`、`core/engine.py` → `_append_fish`（猫吃鱼流程）

### 2.4 展示栏木框保底系统

| 保底类型 | 触发条件 | 产物 | 计数器 |
|----------|---------|------|--------|
| 展示木框保底 | 每150次捕获 | 展示木框（用于扩展展示栏） | `frame_pity_counter` |
| 猫猫框保底 | 猫每吃12条鱼 | 猫猫框（用于强化展示栏） | `cat_frame_pity_counter` |
| 迷途风UTR保底 | 迷途风每150次 | UTR稀有度鱼 | `utr_pity_counter` |

保底计数器持久化在 `FishingUser` 模型和 `fishing_status` 状态字典中，收杆后合并。

### 2.5 鱼饵系统

**鱼饵自动切换**：钓鱼过程中，当前鱼饵消耗完后，自动从背包选择价格最高的可用鱼饵。实现于 `core/engine.py` → `simulate_fishing_loop` 主循环内。

**鱼饵信息**由 `shop.json` 定义，`ConfigManager` 加载：

| ID | 名称 | 速度加成 | 价格 |
|----|------|---------|------|
| 1 | 蚯蚓鱼饵 | +20% | 2 |
| 2 | 虾米鱼饵 | +40% | 5 |
| 3 | 拟饵 | +60% | 10 |
| 4 | 黄金鱼饵 | +80% | 18 |
| 5 | 魔法鱼饵 | +100% | 30 |
| 6 | 传说鱼饵 | +120% | 50 |

**鱼饵消耗**：正常每捕获1条鱼消耗1个鱼饵。暴雨天气有50%概率不消耗。无鱼饵模式（no_bait_mode）下纯靠鱼钩速度。实现于 `core/engine.py` → `_try_catch_in_remaining_time`。

### 2.6 药水系统

| 药水名 | 效果 | 持续时间 | 实现文件 |
|--------|------|----------|---------|
| 时光药水 | 每瓶模拟8小时钓鱼 | — | `core/potion.py` → `use_time_potion_settle` |
| 回档药水 | 清空当前钓鱼进度（鱼获归零） | — | `shop/potion_use.py` → `use_rollback_potion` |
| 幸运药水 | 双次结算，取最好稀有度 | 12h | `shop/potion_use.py` → `use_lucky_potion` |
| 许愿药水 | 50%概率替换为未收集鱼种 | 10h | `models/buff.py` → `BUFF_TYPE_WISH` |

**时光药水关键特性**：
- 使用 `freeze_buff_time` 参数冻结 buff 判定在起始时刻，确保当前天气/buff 全程生效
- 不会因天气过期而丢失效果
- 配合猫天气测试：1h 猫 buff → 200h 药水全程猫效果生效

### 2.7 Buff 系统

所有 buff 类型定义在 `models/buff.py` → `BuffEffect` 类：

| Buff 类型常量 | 效果 | 来源 |
|-------------|------|------|
| `BUFF_TYPE_SPEED_BOOST` | 速度加成 | 药水、展示木框 |
| `BUFF_TYPE_DOUBLE_CATCH` | 双倍捕获 | 药水 |
| `BUFF_TYPE_LUCK_BOOST` | 幸运加成 | 药水 |
| `BUFF_TYPE_DUODUO` | 多多buff（降稀有度翻倍数量） | 药水 |
| `BUFF_TYPE_LUCKY_DOUBLE` | 幸运双次结算 | 幸运药水 |
| `BUFF_TYPE_WISH` | 许愿（优先未收集） | 许愿药水 |
| `BUFF_TYPE_WEEKEND_BONUS` | 周末奖励 | 定时任务自动生成 |
| `BUFF_TYPE_WEATHER_CAT` | 猫天气 | 天气系统 |
| `BUFF_TYPE_NEST` | 打窝速度加成（5%/层, 上限10层） | 打窝系统 |
| `BUFF_TYPE_FRAME` | 展示木框全图加成（5%/层, 上限10层） | 使用展示木框 |

**Buff 目标类型**（`TARGET_TYPE_*`）：`GLOBAL`（全图）、`LOCATION`（指定地点）、`USER`（指定用户）。

**关键方法**：
- `FishingBuff.get_active_buffs_for_fishing(user_id, location_id, start, end)` — 获取时段内活跃 buff
- `FishingBuffCalculator.get_effects_at_time(buffs, time, rod, speed, difficulty)` — 计算时刻效果

### 2.8 打窝系统

- 使用1个香甜玉米打1层，消耗1次每日打窝次数
- 每层 +5% 速度，上限10层（50%）
- 持续时间：`shop.json` → `nest_duration_hours`（默认8小时）
- 效果对所有同地图玩家生效
- 每日限制：`DAILY_NEST_LIMIT = 2` 次
- 实现于 `shop/nest.py` → `do_nest`

### 2.9 展示系统

| 栏位号 | 1-3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|--------|-----|---|---|---|---|---|---|---|
| 所需展示木框 | 免费 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |

**展示收益**：
- 普通栏位：鱼价格 × 2 /天
- 强化栏位（猫猫框强化后）：鱼价格 × 3 /天
- 展示栏位上限：10个
- 强化栏位上限：10个（`UPGRADE_DISPLAY_COSTS`）

**自动展示**：收杆后自动将最高价值的鱼展示到空位（`core/result.py` → `auto_display_fish`）

### 2.10 每日系统

| 行为 | 每日上限 | 常量 |
|------|---------|------|
| 收杆 | 3次 | `DAILY_ACTION_LIMIT` |
| 卖鱼 | 3次 | `DAILY_SELL_LIMIT` |
| 打窝 | 2次 | `DAILY_NEST_LIMIT` |
| 赠送 | 1次 | `DAILY_GIFT_LIMIT` |

每日计数器存储在 `FishingUser` 模型中，通过 `increment_*_count` 方法自增和检查。

### 2.11 成就系统

**横向成就**：收集某地点所有鱼的某稀有度 → 奖励 = 该地点该稀有度所有鱼总价格的3倍
**纵向成就**：收集所有地点的某稀有度鱼 → 奖励 = 所有地点该稀有度鱼总价格的3倍
- 每个成就只能完成一次
- 赠送鱼获也会触发目标用户的成就检查
- 实现于 `services/achievement_service.py` → `check_achievements_for_location`

### 2.12 鱼获选择解析

用户输入 `卖鱼 SR, SSR, **3, 鱼ID, 全部` → `parse_fish_selection` 解析为 `FishSelection` 对象。

**语法**（`backpack/selection.py`）：
- `SR`、`R`、`SSR` → 卖出该稀有度及以下所有鱼
- `**3`（双星号+数字）→ 仅卖出该稀有度等级的鱼
- `12345`（数字ID）→ 卖出指定编号的鱼
- `全部` / `all` / `所有` → 卖出所有未锁定鱼
- 多个参数用 `,` `;` `，` `；` 空格分隔
- 支持混合：`SR, 12345, **3`

### 2.13 兑换系统

- 钓鱼币 → 系统金币：`exchange_to_gold`，汇率见 `shop.json` → `exchange_rate`（默认1:1）
- 调用 `zhenxun.models.user_console.UserConsole.add_gold` 写入系统金币

### 2.14 Web 功能

| 功能 | 端口 | 实现 |
|------|------|------|
| 状态 API | 4158 | `status_api.py` |
| WebSocket 网页 | 4159 | `web/websocket_server.py` |
| 网页渲染模板 | — | `templates/` → Jinja2 模板 |

网页提供：背包查看、收藏图鉴、商店浏览、钓鱼场景、钓鱼状态、搜索结果等。

**状态页概率与鱼饵展示**：
- 状态页概率展示必须走：
  - `core/probability.py::calculate_display_probabilities(...)`
- 返回值是 `DisplayProbabilities`，兼容 `dict`，但额外带：
    - `quantity_multiplier`
    - `independent_mechanics`
- 状态页必须复用 `DisplayProbabilities` 的完整新概率语义，并横向换行展示：
  - 鱼稀有度概率；
  - 多多数量倍率；
  - `independent_mechanics` 中的数值概率（材料、展示木框、流星鱼、迷途风 UTR 等）；
  - 不要在模板内另算或复制概率，布尔开关不作为概率展示。
- 状态及收杆页会展示当前鱼饵剩余数，剩余为 `0` 时将“剩余 0 个”整体标红。
- 状态页还展示：
  - 木框/UTR/猫框保底；
  - Buff 时间轴；
  - 天气与速度明细。

**Web 认证流程**（`web/websocket_server.py` → `_ws_handler` / `_handle_auth`，`handlers/web.py` → `register_key_matcher`）:
- 用户在QQ私聊发送 `注册网页端` → 服务端自动生成8位随机数字密钥，绑定到QQ号 → 存储到数据库表 `fishing_web_key`
- 也支持自定义密钥：`注册网页端 mykey123`
- 前端输入密钥 → WebSocket `/ws` → `{type:"auth", secret:"密钥"}`
- 服务端 `await KeyManager().authenticate(secret)` → 查询 `fishing_web_key` → 查数据库获取用户 → `{type:"auth_ok", nickname:"..."}`
- 密钥只持久化在数据库表，重启不丢失；密钥通过 localStorage 缓存在浏览器端
- Web 端不可自助生成密钥（`/api/get-key` 已废弃），必须通过QQ私聊获取，确保绑定QQ号
- **重要**: 认证错误消息类型必须为 `auth_error`（前端只监听该类型），字段名为 `message`（非 `content`）
- **重要**: `_handle_auth` 被 try/except 包裹，防止数据库异常导致 WebSocket 静默崩溃
- HTTP API 端点也通过 `key_manager.py` 做 secret 认证（`api.py` → `_require_auth`）

**前端响应式布局**（`web/static/index.html`）:
- 快速操作按钮通过 `quickBtns` 数组统一管理（钓鱼/收杆/状态/鱼店/背包/天气）
- 使用 `ResizeObserver` 监听容器宽度：空间足够时显示所有按钮，不足时折叠为「操作 ▾」下拉框
- **重要**: ResizeObserver 必须在 `connected=true` 后（即 DOM 已渲染）才通过 `watch(connected)` 初始化
- 页面高度使用 `100dvh`，底部输入栏设置 `flex-shrink: 0`
- 移动端侧栏（背包/状态）为 drawer 模式，通过 header 按钮切换

**场景渲染缩放**:
- 通过 `naturalW` 区分页面类型：≤350px 为钓鱼场景(330px)，>350px 为其它页面(400px+)
- **钓鱼场景**: 始终填满容器宽度（桌面放大/手机缩小），`transform: scale()` 同步缩放 iframe 内容
- **其它页面（状态/商店/背包等）**: 桌面保持自然尺寸，手机端仅当溢出时才缩小到 `containerW`
- `result-wrap` 设 `overflow-y: auto`，内容过高时区域内滚动；`bottom-bar` 为兄弟节点设 `flex-shrink:0`，始终固定在底部
- `.result-image` 不能设 `max-width`，宽度完全由 JS 控制

### 2.15 调度器定时任务

| 任务 | 触发器 | 功能 | 文件 |
|------|--------|------|------|
| 周末奖励 | cron 0:05 每天 | 检查是否为周末，生成周末 buff | `scheduler.py` |
| 天气生成 | cron 0:00 每天 | 自动生成今日天气 | `scheduler.py` |
| Buff 清理 | interval 1h | 清除过期 buff | `scheduler.py` |
| 数据库备份 | interval 12h | 备份 SQLite 数据库，保留3天 | `scheduler.py` |
| Web 服务器启动 | date +1min | 延迟启动 Web 服务器 | `scheduler.py` |

---

## 三、重构后文件架构

```
fishing/
├── __init__.py          # 插件元数据 + import handlers/scheduler（薄层）
├── constants.py         # ★ NEW：不可变游戏设计数据
├── config.py            # ConfigManager（Pydantic + JSON 加载）+ re-export constants
├── scheduler.py         # ★ NEW：所有定时任务
├── matchers.py          # 所有 on_regex() Matcher
├── gm.py                # GM 调试命令
├── weather_service.py   # 天气生成服务
├── utils.py             # 工具函数
│
├── core/                # ★ NEW：钓鱼核心业务逻辑（从 fishing.py 拆分）
│   ├── context.py       #   FishingContext, StepResult, ser/deser
│   ├── engine.py        #   钓鱼模拟循环 + 捕获判定
│   ├── probability.py   #   概率计算
│   ├── cat.py           #   猫天气系统
│   ├── bait.py          #   鱼饵管理
│   ├── scene.py         #   场景渲染组装
│   ├── actions.py       #   外部入口（start/stop/check/settle）
│   ├── result.py        #   鱼获结果处理
│   └── potion.py        #   时光药水结算
│
├── shop/                # ★ NEW：商店子系统（从 shop.py 拆分）
│   ├── view.py          #   渲染
│   ├── purchase.py      #   购买 + 升级
│   ├── nest.py          #   打窝
│   ├── potion_use.py    #   药水使用
│   └── misc.py          #   兑换/签到/改名/皮肤
│
├── backpack/            # ★ NEW：背包子系统（从 backpack.py 拆分）
│   ├── view.py          #   渲染
│   ├── sell.py          #   卖鱼
│   ├── gift.py          #   赠送
│   ├── lock.py          #   锁定/解锁
│   └── selection.py     #   鱼获选择解析
│
├── fishing.py           # 门面：re-export from core/
├── shop.py              # 门面：re-export from shop/
├── backpack.py          # 门面：re-export from backpack/
│
├── models/              # 数据模型（未变）
│   ├── user.py          #   FishingUser
│   ├── buff.py          #   FishingBuff, BuffEffect, FishingBuffCalculator
│   └── weather.py       #   FishingWeather
│
├── services/            # 服务层（未变）
│   ├── user_service.py
│   ├── buff_service.py
│   ├── achievement_service.py
│   └── display_service.py
│
├── render/              # 渲染层（未变）
├── handlers/            # 命令 handler（未变）
├── web/                 # Web API（未变）
└── templates/           # Jinja2 模板（未变）
```

---

## 四、常见修改场景指南

### 新增鱼种/钓场
1. 编辑 `config/fish.json` 添加鱼种
2. 编辑 `config/locations.json` 添加钓场及其鱼池
3. 添加鱼种图片 `resources/images/fish/`
4. 添加钓场图片 `resources/images/scenes/`
5. 更新 `GAME_DESIGN.md` 的鱼种/地点表格

### 新增稀有度等级
1. `constants.py`：更新 `RARITY_INDEX`、`RARITY_ORDER`、`RARITY_COLORS`、`RARITY_NAMES`、`RARITY_MIN_LEVEL`、`RARITY_MULTIPLIER`、`_RARITY_KEYS`
2. `constants.py`：扩展 `RARITY_DISTRIBUTION` 表
3. `core/probability.py`：更新概率函数
4. 运行 `test_config_and_logic.py` 验证

### 新增天气类型
1. `constants.py`：添加 `WEATHER_EMOJI`、`WEATHER_NAME`、`WEATHER_EFFECT_DESC`
2. `models/buff.py`：添加对应 `BUFF_TYPE_*` 常量
3. `core/engine.py`：在 `_catch_fish_with_buffs`、`simulate_fishing_loop` 处理新天气效果
4. `models/buff.py` → `FishingBuffCalculator.get_effects_at_time` 计算新效果
5. 运行 `test_cat_weather_scenario` 风格的集成测试

### 新增药水类型
1. `config/shop.json`：添加药水配置
2. `models/buff.py`：添加对应 `BUFF_TYPE_*` 和 `_POTION_EFFECT_MAP`
3. `shop/potion_use.py`：添加 `use_xxx_potion` 函数
4. `core/engine.py`：在 `_catch_fish_with_buffs` 处理新药水效果
5. 创建集成测试（参照 `test_lucky_potion_double_roll`）

### 新增 Buff 效果
1. `models/buff.py` → `BuffEffect` 添加 `BUFF_TYPE_*` 常量
2. `models/buff.py` → `FishingBuffCalculator.get_effects_at_time` 实现效果计算
3. `core/engine.py` → `_catch_fish_with_buffs` 应用效果
4. `shop/purchase.py` → `_POTION_EFFECT_MAP`（如为药水）

---

## 五、注意事项

1. **时光药水 `freeze_buff_time`**：瞬间结算药水时，buff 判定冻在起始时刻。修改钓鱼模拟循环时注意此参数。

2. **保底计数器双存储**：`frame_pity_counter` 等既存 `FishingUser` 模型又存 `fishing_status` 字典，收杆时需要合并。

3. **向后兼容门面模式**：`fishing.py`、`shop.py`、`backpack.py` 为 thin facade，仅 re-export。新增逻辑必须放入 `core/`、`shop/`、`backpack/` 子包。

4. **config.py 的 re-export**：所有常量从 `constants.py` 导入并通过 `config.py` 重新导出。旧代码仍可 `from .config import RARITY_INDEX`。

5. **NoneBot 测试要求**：测试需要完整 NoneBot 运行时。不能直接在 `fishing/tests/` 下 `pytest` 裸跑。正确方式：`uv run pytest tests/integration/test_fishing.py -s -v`。

6. **展示木框机制**：展示木框以 `FishData(id="展示木框", base_price=0)` 伪鱼形式存在于鱼获列表中，在 `save_fish_to_backpack` 时特殊处理。

7. **UTR 自动消耗**：第一条 UTR 鱼会自动消耗用于解锁图鉴（不进入背包），剩余 UTR 鱼正常入背包。

8. **赠送与交换链路**：
- 赠送逻辑支持背包 / 展示框 / 流星鱼来源，并通过数值 ID 精确定位。
- UTR 首次解锁赠送不计普通每日赠送次数，并按双倍 UTR 价值奖励赠送者。
- 黑商交换允许消耗锁定鱼；若来源鱼已锁定，实际获得鱼（包括黑商随机替换后的目标）必须留在背包并继承锁定，在成功消息目标鱼后追加“（已自动锁定）”。
- 白商逆交换继续复用 `add_fish_to_user(...)`，保持自动展示、收藏与成就语义；不要把黑商锁继承扩散到白商接口。
- 展示框中的鱼已从背包移除，鱼锁仅防止误卖，不阻止赠送或交换。
- 自动售卖、手动售卖、钓鱼结算不是同一条链路，修改时必须逐条确认。


---

## 六、本地 Shell 与编码约定（Windows）

> **目标**：减少 PowerShell heredoc / 中文路径 / 控制台 GBK 导致的踩坑。  
> **结论**：本机已安装 Git Bash，**优先用 Git Bash 做脚本、批量替换、pytest、git 与含中文内容的读写**；PowerShell 仍可用于简单文件列举与需要原生 Windows cmdlet 的场景。

### 6.1 可用路径

| 程序 | 路径 |
|------|------|
| Git Bash（推荐非交互） | `C:\Program Files\Git\bin\bash.exe` |
| Git Bash 窗口 | `C:\Program Files\Git\git-bash.exe` |
| git | `C:\Program Files\Git\cmd\git.exe` |

本仓库实测（2026-07-15）：

```text
MINGW64 ... x86_64 Msys
LANG=zh_CN.UTF-8
UTF8-test: 流星鱼 星空祈愿   # 可正常打印
cwd: /c/Users/Administrator/Desktop/zhenxun_bot-420
```

### 6.2 AI / 维护者调用方式

从 PowerShell 调 Git Bash（非交互、适合自动化）：

```powershell
& "C:\Program Files\Git\bin\bash.exe" -lc "cd /c/Users/Administrator/Desktop/zhenxun_bot-420 && <命令>"
```

直接在 Git Bash 里：

```bash
cd /c/Users/Administrator/Desktop/zhenxun_bot-420
export LANG=zh_CN.UTF-8 LC_ALL=zh_CN.UTF-8
export PYTHONIOENCODING=utf-8
.venv/Scripts/python.exe -m pytest zhenxun/plugins/zhenxun_plugin_fishing/tests -q
```

含中文/多行 Python 补丁时，**优先**在 Bash 里用 heredoc，避免 PowerShell here-string + 编码翻车：

```bash
.venv/Scripts/python.exe - <<'PY'
from pathlib import Path
p = Path("zhenxun/plugins/zhenxun_plugin_fishing/doc.md")
print("星空祈愿" in p.read_text(encoding="utf-8"))
PY
```

### 6.3 仍需注意的兼容性 / 编码问题

1. **不等于没有编码问题**：部分终端管道、Windows 控制台 code page、错误的 `PYTHONIOENCODING`、用系统 `python` 而非 `.venv` 仍可能乱码或 `UnicodeEncodeError`。
2. **读写源码/HTML 一律 `encoding="utf-8"`**；不要依赖控制台默认 GBK 打印结果来判断中文是否写对——以文件内容为准。
3. **路径写法**：Bash 用 `/c/Users/...`；PowerShell 用 `C:\Users\...`。混用时注意转义。
4. **pytest / 依赖**：统一用仓库虚拟环境  
   - Bash: `.venv/Scripts/python.exe -m pytest ...`  
   - PowerShell: `.venv\Scripts\python.exe -m pytest ...`
5. **何时仍用 PowerShell**：`Get-ChildItem`、已批准的 Windows 专用诊断、以及当前会话默认 shell 仅方便跑一条简单命令时。涉及中文补丁、批量检索/替换、`python - <<'PY'` 时切 Git Bash。

### 6.4 简要决策

| 任务 | 推荐 |
|------|------|
| 中文文案批量替换、多行 Python 补丁 | Git Bash + UTF-8 |
| 跑插件单测 | 任一 shell + `.venv` Python |
| 仅列文件 / 看进程端口 | PowerShell 即可 |
| 写文件后自检中文 | 读文件内容，勿只信控制台回显 |


---

*最后更新：2026-07-15 — 补充 Windows 下优先使用 Git Bash 的约定与编码注意*
