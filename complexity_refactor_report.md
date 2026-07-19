# 钓鱼插件代码复杂度与重构指标报告

- 分析范围: `zhenxun_plugin_fishing` 生产代码（排除 tests/doc/模拟脚本等）
- 文件数: **89**
- 函数/方法数: **694**
- 总行数 LOC: **20981** / SLOC: **17514**
- 平均函数圈复杂度: **5.26**
- 平均函数行数: **23.2**
- 最大圈复杂度: **65**
- 综合判定: **强烈建议重构**（urgency=high）

## 1. 圈复杂度分布

| 等级 | 范围 | 数量 | 占比 |
|---|---|---:|---:|
| A | 1-5 | 491 | 70.7% |
| B | 6-10 | 112 | 16.1% |
| C | 11-20 | 70 | 10.1% |
| D | 21-50 | 19 | 2.7% |
| F | >50 | 2 | 0.3% |

### 阈值命中

| 指标 | 数量 | 说明 |
|---|---:|---|
| CC ≥ 10 | 104 | 应考虑拆分 |
| CC ≥ 15 | 52 | 明显复杂 |
| CC ≥ 20 | 23 | 高风险 |
| CC ≥ 30 | 10 | 优先重构 |
| CC ≥ 50 | 2 | 严重 |
| 函数 LOC ≥ 80 | 35 | 过长 |
| 函数 LOC ≥ 100 | 22 | 很长 |
| 嵌套深度 ≥ 4 | 57 | 可读性差 |
| 参数个数 ≥ 5 | 55 | 参数列表过长 |
| return 点 ≥ 5 | 31 | 多出口 |

## 2. 包/目录级统计

| 包 | 文件 | LOC | 函数 | 平均CC | 高CC函数(≥10) |
|---|---:|---:|---:|---:|---:|
| `core` | 17 | 4938 | 108 | 8.24 | 34 |
| `(root)` | 15 | 4304 | 132 | 5.61 | 23 |
| `render` | 9 | 2763 | 61 | 7.87 | 13 |
| `models` | 8 | 2717 | 176 | 2.55 | 3 |
| `handlers` | 9 | 1620 | 57 | 5.0 | 6 |
| `backpack` | 7 | 1539 | 42 | 8.24 | 14 |
| `shop` | 7 | 1114 | 38 | 4.61 | 5 |
| `web` | 7 | 1086 | 53 | 3.21 | 2 |
| `services` | 7 | 529 | 20 | 4.75 | 4 |
| `avatar_system` | 2 | 268 | 7 | 2.71 | 0 |
| `config` | 1 | 103 | 0 | 0 | 0 |

## 3. Top 圈复杂度函数

| 文件 | 函数 | 行号 | CC | LOC | 嵌套 | 参数 | returns |
|---|---|---:|---:|---:|---:|---:|---:|
| `core/engine.py` | `simulate_fishing_loop` | 830 | **65** (F) | 315 | 7 | 6 | 1 |
| `render/fishing_scene.py` | `render_fishing_scene` | 342 | **57** (F) | 276 | 4 | 16 | 2 |
| `status_api.py` | `_get_status_json` | 354 | **48** (D) | 204 | 6 | 0 | 3 |
| `gm.py` | `gm_add_item` | 421 | **48** (D) | 168 | 5 | 3 | 27 |
| `core/actions.py` | `_apply_stop_settlement_writes` | 462 | **42** (D) | 272 | 6 | 9 | 1 |
| `weather_service.py` | `generate_daily_weather` | 230 | **35** (D) | 143 | 4 | 0 | 2 |
| `render/fishing_status.py` | `render_fishing_status` | 235 | **33** (D) | 192 | 4 | 28 | 1 |
| `core/engine.py` | `_catch_fish_with_buffs` | 322 | **32** (D) | 165 | 2 | 21 | 9 |
| `core/potion.py` | `use_time_potion_settle` | 38 | **30** (D) | 284 | 3 | 2 | 4 |
| `render/fishing_result.py` | `render_fishing_result` | 106 | **30** (D) | 122 | 4 | 18 | 1 |
| `render/fishing_status.py` | `_build_buff_timeline` | 94 | **29** (D) | 139 | 4 | 4 | 4 |
| `models/user.py` | `_repair_user_fields` | 114 | **29** (D) | 62 | 5 | 1 | 1 |
| `backpack/black_market.py` | `black_market_exchange` | 442 | **26** (D) | 100 | 3 | 2 | 10 |
| `render/misc.py` | `render_location_select` | 14 | **25** (D) | 127 | 4 | 3 | 1 |
| `core/starry_system.py` | `score_starry_fish` | 361 | **25** (D) | 109 | 4 | 1 | 1 |
| `backpack/view.py` | `get_backpack_image` | 169 | **25** (D) | 97 | 3 | 1 | 1 |
| `core/actions.py` | `check_fishing_status` | 288 | **23** (D) | 152 | 3 | 3 | 4 |
| `core/engine.py` | `_lucky_select` | 233 | **23** (D) | 82 | 4 | 5 | 7 |
| `render/base.py` | `_find_fish_image_path` | 146 | **22** (D) | 64 | 3 | 2 | 8 |
| `render/base.py` | `build_fish_list_data` | 349 | **21** (D) | 102 | 3 | 4 | 1 |
| `backpack/view.py` | `get_collection_image` | 268 | **21** (D) | 78 | 5 | 2 | 1 |
| `backpack/lock.py` | `_toggle_fish_lock` | 48 | **20** (C) | 73 | 2 | 3 | 7 |
| `core/starry_system.py` | `_mitm_exact_indices` | 601 | **20** (C) | 52 | 2 | 3 | 4 |
| `core/stop_mutations.py` | `apply_check_all_achievements_on_user` | 214 | **19** (C) | 79 | 3 | 2 | 1 |
| `backpack/black_market.py` | `render_white_market_records` | 279 | **18** (C) | 161 | 3 | 1 | 2 |
| `cat_park.py` | `render_cat_park_image` | 398 | **18** (C) | 122 | 4 | 2 | 1 |
| `shop/nest.py` | `do_nest` | 14 | **18** (C) | 94 | 2 | 4 | 7 |
| `services/achievement_service.py` | `check_achievements_for_location` | 45 | **18** (C) | 84 | 2 | 2 | 2 |
| `handlers/fishing.py` | `_` | 161 | **18** (C) | 72 | 5 | 2 | 1 |
| `core/scene.py` | `render_scene` | 57 | **17** (C) | 139 | 4 | 4 | 1 |

## 4. 综合风险 Top（CC + 长度 + 嵌套 + 参数 + 多出口）

| 风险分 | 文件 | 函数 | CC | LOC | 嵌套 | 参数 | returns |
|---:|---|---|---:|---:|---:|---:|---:|
| 352.5 | `core/engine.py` | `simulate_fishing_loop` | 65 | 315 | 7 | 6 | 1 |
| 317.0 | `render/fishing_scene.py` | `render_fishing_scene` | 57 | 276 | 4 | 16 | 2 |
| 264.0 | `core/actions.py` | `_apply_stop_settlement_writes` | 42 | 272 | 6 | 9 | 1 |
| 250.5 | `gm.py` | `gm_add_item` | 48 | 168 | 5 | 3 | 27 |
| 238.0 | `status_api.py` | `_get_status_json` | 48 | 204 | 6 | 0 | 3 |
| 227.0 | `render/fishing_status.py` | `render_fishing_status` | 33 | 192 | 4 | 28 | 1 |
| 212.0 | `core/potion.py` | `use_time_potion_settle` | 30 | 284 | 3 | 2 | 4 |
| 200.0 | `core/engine.py` | `_catch_fish_with_buffs` | 32 | 165 | 2 | 21 | 9 |
| 163.0 | `render/fishing_result.py` | `render_fishing_result` | 30 | 122 | 4 | 18 | 1 |
| 160.5 | `weather_service.py` | `generate_daily_weather` | 35 | 143 | 4 | 0 | 2 |
| 158.5 | `render/shop.py` | `render_shop` | 16 | 217 | 3 | 15 | 1 |
| 140.5 | `render/fishing_status.py` | `_build_buff_timeline` | 29 | 139 | 4 | 4 | 4 |
| 125.0 | `core/actions.py` | `check_fishing_status` | 23 | 152 | 3 | 3 | 4 |
| 122.5 | `render/misc.py` | `render_location_select` | 25 | 127 | 4 | 3 | 1 |
| 117.0 | `backpack/black_market.py` | `black_market_exchange` | 26 | 100 | 3 | 2 | 10 |
| 114.5 | `backpack/black_market.py` | `render_white_market_records` | 18 | 161 | 3 | 1 | 2 |
| 113.5 | `core/starry_system.py` | `score_starry_fish` | 25 | 109 | 4 | 1 | 1 |
| 106.0 | `models/user.py` | `_repair_user_fields` | 29 | 62 | 5 | 1 | 1 |
| 106.0 | `web/api.py` | `get_state` | 16 | 148 | 4 | 2 | 1 |
| 104.5 | `core/scene.py` | `render_scene` | 17 | 139 | 4 | 4 | 1 |
| 103.5 | `backpack/view.py` | `get_backpack_image` | 25 | 97 | 3 | 1 | 1 |
| 100.5 | `core/engine.py` | `_lucky_select` | 23 | 82 | 4 | 5 | 7 |
| 99.0 | `cat_park.py` | `render_cat_park_image` | 18 | 122 | 4 | 2 | 1 |
| 94.0 | `render/base.py` | `build_fish_list_data` | 21 | 102 | 3 | 4 | 1 |
| 91.5 | `core/engine.py` | `_catch_fish_at_interval` | 15 | 97 | 3 | 13 | 1 |

## 5. 最长函数 / 最深嵌套 / 最多参数

### 最长函数

| 文件 | 函数 | LOC | CC |
|---|---|---:|---:|
| `core/engine.py` | `simulate_fishing_loop` | 315 | 65 |
| `core/potion.py` | `use_time_potion_settle` | 284 | 30 |
| `render/fishing_scene.py` | `render_fishing_scene` | 276 | 57 |
| `core/actions.py` | `_apply_stop_settlement_writes` | 272 | 42 |
| `render/shop.py` | `render_shop` | 217 | 16 |
| `status_api.py` | `_get_status_json` | 204 | 48 |
| `render/fishing_status.py` | `render_fishing_status` | 192 | 33 |
| `gm.py` | `gm_add_item` | 168 | 48 |
| `core/engine.py` | `_catch_fish_with_buffs` | 165 | 32 |
| `backpack/black_market.py` | `render_white_market_records` | 161 | 18 |
| `core/actions.py` | `check_fishing_status` | 152 | 23 |
| `web/api.py` | `get_state` | 148 | 16 |

### 最深嵌套

| 文件 | 函数 | 嵌套 | CC | LOC |
|---|---|---:|---:|---:|
| `core/engine.py` | `simulate_fishing_loop` | 7 | 65 | 315 |
| `status_api.py` | `_get_status_json` | 6 | 48 | 204 |
| `core/actions.py` | `_apply_stop_settlement_writes` | 6 | 42 | 272 |
| `core/engine.py` | `_append_fish` | 6 | 16 | 53 |
| `core/cat.py` | `process_cat_gift` | 6 | 14 | 54 |
| `status_api.py` | `_content_type_for` | 6 | 10 | 24 |
| `web/command_router.py` | `CommandRouter._format_responses` | 6 | 9 | 21 |
| `render/base.py` | `render_html` | 6 | 6 | 35 |
| `gm.py` | `gm_add_item` | 5 | 48 | 168 |
| `models/user.py` | `_repair_user_fields` | 5 | 29 | 62 |

### 参数最多

| 文件 | 函数 | 参数 | CC |
|---|---|---:|---:|
| `render/fishing_status.py` | `render_fishing_status` | 28 | 33 |
| `core/engine.py` | `_catch_fish_with_buffs` | 21 | 32 |
| `render/fishing_result.py` | `render_fishing_result` | 18 | 30 |
| `core/engine.py` | `_try_catch_in_remaining_time` | 17 | 2 |
| `render/fishing_scene.py` | `render_fishing_scene` | 16 | 57 |
| `render/backpack.py` | `render_backpack` | 16 | 9 |
| `render/shop.py` | `render_shop` | 15 | 16 |
| `core/engine.py` | `_catch_fish_at_interval` | 13 | 15 |
| `core/engine.py` | `_append_fish` | 12 | 16 |
| `render/base.py` | `build_fish_item_data` | 12 | 12 |

## 6. 文件级指标

### 最大文件（God File 候选）

| 文件 | LOC | 函数数 | max CC | 高CC函数 | avg CC |
|---|---:|---:|---:|---:|---:|
| `models/user.py` | 1169 | 99 | 29 | 1 | 2.51 |
| `core/engine.py` | 1144 | 18 | 65 | 7 | 12.39 |
| `gm.py` | 868 | 26 | 48 | 6 | 8.04 |
| `core/actions.py` | 821 | 12 | 42 | 3 | 9.5 |
| `core/starry_system.py` | 706 | 33 | 25 | 4 | 5.18 |
| `status_api.py` | 686 | 14 | 48 | 8 | 10.5 |
| `render/fishing_scene.py` | 655 | 20 | 57 | 2 | 7.9 |
| `models/user_mutations.py` | 645 | 43 | 10 | 1 | 2.91 |
| `core/stop_mutations.py` | 640 | 12 | 19 | 8 | 11.08 |
| `cat_park.py` | 622 | 28 | 18 | 4 | 4.54 |
| `backpack/black_market.py` | 601 | 17 | 26 | 4 | 7.12 |
| `models/buff.py` | 569 | 20 | 13 | 1 | 2.7 |
| `render/base.py` | 498 | 16 | 22 | 3 | 6.38 |
| `weather_service.py` | 471 | 11 | 35 | 3 | 8.36 |
| `handlers/gm.py` | 444 | 17 | 11 | 1 | 4.12 |

### 可维护性指数 MI 最低（越低越难维护，近似）

| 文件 | MI | SLOC | avg CC | max CC |
|---|---:|---:|---:|---:|
| `models/user.py` | 8.8 | 1028 | 2.51 | 29 |
| `gm.py` | 15.6 | 723 | 8.04 | 48 |
| `status_api.py` | 15.6 | 600 | 10.5 | 48 |
| `core/stop_mutations.py` | 16.1 | 561 | 11.08 | 19 |
| `core/starry_system.py` | 18.2 | 597 | 5.18 | 25 |
| `render/fishing_scene.py` | 18.3 | 571 | 7.9 | 57 |
| `core/engine.py` | 19.3 | 910 | 12.39 | 65 |
| `cat_park.py` | 19.6 | 530 | 4.54 | 18 |
| `core/actions.py` | 19.8 | 664 | 9.5 | 42 |
| `render/base.py` | 20.3 | 424 | 6.38 | 22 |
| `models/user_mutations.py` | 20.4 | 513 | 2.91 | 10 |
| `render/misc.py` | 20.9 | 313 | 5.75 | 25 |

## 7. 耦合（内部 fan-in / fan-out）

| 模块 | fan-in | fan-out | 主要依赖 |
|---|---:|---:|---|
| `config` | 41 | 1 | `constants` |
| `models` | 39 | 0 | - |
| `core.actions` | 4 | 19 | `backpack`, `cat_park`, `config`, `core.bait`, `core.cat_gift`, `core.context` |
| `starry` | 20 | 2 | `models`, `services` |
| `services` | 19 | 0 | - |
| `cat_park` | 16 | 3 | `config`, `models`, `render.base` |
| `core.potion` | 2 | 13 | `cat_park`, `config`, `core.actions`, `core.bait`, `core.cat_gift`, `core.context` |
| `render.base` | 12 | 2 | `config`, `core.starry_system` |
| `render` | 12 | 0 | - |
| `weather_service` | 8 | 4 | `cat_park`, `config`, `models`, `starry` |
| `core.engine` | 4 | 8 | `cat_park`, `config`, `constants`, `core.cat`, `core.context`, `core.starry_system` |
| `core.result` | 6 | 5 | `cat_park`, `config`, `core.context`, `models`, `services` |
| `shop.potion_use` | 2 | 9 | `backpack.black_market`, `config`, `core.actions`, `core.cat_gift`, `core.potion`, `core.result` |
| `matchers` | 9 | 1 | `commands` |
| `utils` | 8 | 2 | `render`, `services` |

## 8. 疑似重复代码块（≥10 行相似窗口，启发式）

共检测到约 **40** 组重复候选（前 15 组）：

1. **7 处** — `backpack/__init__.py:23`; `backpack.py:18`; `models/__init__.py:19`; `render/__init__.py:44`; `services/__init__.py:15`
   - 预览: `__all__ = [ / '',`
2. **6 处** — `backpack/__init__.py:24`; `models/__init__.py:20`; `render/__init__.py:45`; `services/__init__.py:16`; `shop.py:28`
   - 预览: `__all__ = [ / '',`
3. **5 处** — `constants.py:138`; `constants.py:151`; `constants.py:164`; `core/starry_system.py:94`; `gm.py:145`
   - 预览: `'': '', / '': '',`
4. **5 处** — `constants.py:139`; `constants.py:152`; `constants.py:165`; `core/starry_system.py:96`; `gm.py:150`
   - 预览: `'': '', / '': '',`
5. **5 处** — `constants.py:140`; `constants.py:153`; `constants.py:166`; `core/starry_system.py:97`; `gm.py:151`
   - 预览: `'': '', / '': '',`
6. **4 处** — `__init__.py:62`; `__init__.py:72`; `__init__.py:82`; `__init__.py:92`
   - 预览: `Command(command=''), / Command(command=''),`
7. **3 处** — `models/announcement.py:26`; `models/exchange.py:34`; `models/web_key.py:16`
   - 预览: `class Meta: / table = ''`
8. **3 处** — `models/announcement.py:27`; `models/exchange.py:35`; `models/web_key.py:17`
   - 预览: `class Meta: / table = ''`
9. **3 处** — `models/announcement.py:28`; `models/exchange.py:36`; `models/web_key.py:18`
   - 预览: `table = '' / table_description = ''`
10. **3 处** — `render/shop.py:72`; `render/shop.py:116`; `render/shop.py:149`
   - 预览: `frame_rows.append( / {`
11. **3 处** — `render/shop.py:73`; `render/shop.py:117`; `render/shop.py:150`
   - 预览: `{ / '': '',`
12. **3 处** — `render/shop.py:74`; `render/shop.py:118`; `render/shop.py:151`
   - 预览: `'': '', / '': '',`
13. **3 处** — `render/shop.py:75`; `render/shop.py:119`; `render/shop.py:152`
   - 预览: `'': '', / '': '',`
14. **3 处** — `shop/purchase.py:155`; `shop/purchase.py:184`; `shop/purchase.py:209`
   - 预览: `logger.info( / f''`
15. **3 处** — `shop/purchase.py:156`; `shop/purchase.py:185`; `shop/purchase.py:210`
   - 预览: `logger.info( / f''`

## 9. 重构判定与方向

**结论：强烈建议重构**

### 判定依据

- 最大 CC = 65；CC≥20 占比 3.3%；CC≥10 占比 15.0%
- 超长函数(LOC≥80) 占比 5.0%
- 超大文件: ≥500 行 12 个，≥800 行 4 个
- 低 MI 文件: 51 个

### 建议优先级

1. **P0 拆分高 CC 热点函数**（CC≥20）：把分支按业务阶段切成小函数/策略表
2. **P0 消化 God File**：>500 行模块按职责切分（handler / service / domain / render）
3. **P1 降低嵌套**：guard clause、提前返回、策略字典替代深层 if/elif
4. **P1 收敛参数列表**：引入 context/dataclass，避免 5+ 参数线程
5. **P2 消除重复块**：抽公共工具/模板方法
6. **P2 解耦核心模块**：降低 fan-out，避免 core 与 handlers/render 互相渗透
7. **P3 补测试保护网**：优先给高风险函数加单测后再重构

---
*由 AST 自定义分析生成（McCabe 近似：if/for/while/except/assert/and-or/comprehension/match/ifexp）*
