# 钓鱼插件复杂度结论复核

## 修正后的结论

建议对核心热点分阶段重构，但不支持“项目整体强烈需要重构”或“大范围拆包”的表述。

更准确的评级是：**重构必要性中高，范围应聚焦在少数高风险函数和接口；其余代码保持渐进治理。**

## 标准工具交叉验证

分析范围保持为 89 个生产 Python 文件，排除 tests、doc、模拟和分析脚本。

| 指标 | 原自定义结果 | Radon | Lizard | 复核判断 |
|---|---:|---:|---:|---|
| 函数数 | 694 | 688 | 697 | 工具对匿名/嵌套结构口径不同 |
| 平均 CC | 5.26 | 5.26 | 5.13 | 原结论可靠 |
| 最大 CC | 65 | 65 | 57 | 热点明确，工具定义有差异 |
| CC ≥ 10 | 104 | 102 | 101 | 约 15%，可靠 |
| CC ≥ 20 | 23 | 23 | 22 | 约 3.3%，可靠 |
| CC ≥ 30 | 10 | 10 | 8 | 数量很少但风险高 |
| CC ≥ 50 | 2 | 2 | 1 | `simulate_fishing_loop` 和渲染场景是首要热点 |

Radon Top 结果：

1. `core/engine.py:simulate_fishing_loop` — CC 65
2. `render/fishing_scene.py:render_fishing_scene` — CC 57
3. `status_api.py:_get_status_json` — CC 48
4. `gm.py:gm_add_item` — CC 45
5. `core/actions.py:_apply_stop_settlement_writes` — CC 42
6. `weather_service.py:generate_daily_weather` — CC 35
7. `render/fishing_status.py:render_fishing_status` — CC 33
8. `core/engine.py:_catch_fish_with_buffs` — CC 30
9. `core/potion.py:use_time_potion_settle` — CC 30
10. `render/fishing_result.py:render_fishing_result` — CC 30

## 原报告存在的问题

### 1. “强烈建议重构”过度概括

项目约 85% 的函数 CC 小于 10，只有约 3.3% 达到 CC 20。风险呈明显的热点集中，而不是全局失控。因此应说“核心热点强烈建议重构”，不能推导成“整个插件强烈需要重构”。

### 2. SLOC 计算不标准

原报告用“总行数减空行和整行注释”估算 SLOC，得到 17,514。Radon 的标准 raw metrics 得到 16,697。原数字不宜用于正式比较。

### 3. 个别函数 CC 被自定义算法高估

原算法会把嵌套函数的控制流算进外层函数，并将 `assert` 计入复杂度。标准 Radon 显示：

- `gm_add_item`：48 应修正为 45
- `_catch_fish_with_buffs`：32 应修正为 30

主排序基本不变，但正式门禁应以 Radon/Lizard 为准。

### 4. 原 MI 不可采用

原报告的 MI 是以 SLOC 近似 Halstead Volume 的自制代理值，不能称为标准可维护性指数。标准 Radon MI 也受文件大小强烈影响，只适合作为筛选信号，不宜拿 40/65 作为绝对质量线。

### 5. 重复代码检测证据不足

原检测是固定 10 行滑窗的文本归一化，只能发现 Type-1 近似克隆。结果主要命中 `__all__`、常量和 Meta，不足以证明业务逻辑重复。该指标应从结论依据中移除；如要正式判断，应使用 CPD/jscpd，并人工确认候选。

### 6. 耦合统计不够准确

原 fan-in/fan-out 通过 AST 相对导入近似推算，没有解析 re-export、运行时导入和真正的包级依赖图。因此“`core.actions` fan-out 19”只能作线索，不能直接证明架构违规。

### 7. 多 return 不是天然坏味道

`gm_add_item` 有 26 个 return，确实与命令分支过多同时出现；但提前返回本身常用于降低嵌套。应关注“分支数、职责数和修改频率”的组合，而不是设定 return≤5 的硬门禁。

### 8. 参数数量需要区分位置参数与关键字上下文

渲染函数的 16—28 个参数确实影响演进，但 DTO 化可能隐藏依赖、形成过大的 ViewModel。更合适的是按 `player/status/weather/assets` 分组，而不是机械压到 3 个参数。

### 9. God File 不能只按行数判定

`models/user.py` 1169 行但平均复杂度较低，且大量方法可能只是持久化接口。它是“拆分候选”，不是 P0。相比之下，`core/engine.py` 同时具备高 CC、长函数和核心业务风险，优先级明显更高。

## 对原重构方向的修正

### 保留并提高优先级

- 拆解 `simulate_fishing_loop`，但先提取纯计算步骤和结果对象，不先拆文件。
- 为 `simulate_fishing_loop`、`_catch_fish_with_buffs`、`_apply_stop_settlement_writes` 建立行为测试和属性测试。
- 把 9 元组返回值改成具名结果对象；代码已有 `FishingContext` 和 `StepResult`，应扩展现有模型，而不是重复创建 `CatchContext`。
- 重构 `gm_add_item` 为物品类型解析器/处理器注册表。
- 将渲染输入按稳定业务块分组，减少调用点参数漂移。

### 降低优先级

- 不应仅因 `models/user.py` 超过 1000 行就立即拆分。
- 不应把整个 `core/actions.py` 按 start/stop/status/sign 机械拆文件；先确认修改原因和依赖方向。
- 不需要优先治理启发式重复代码和近似 fan-out。
- `use_time_potion_settle` 已经复用 `simulate_fishing_loop`，原报告所说“两套结算逻辑”不准确；真正问题是两阶段结果合并、状态继承和 9 元组解包复杂。

## 建议优先次序

1. `simulate_fishing_loop`：先补测试，再拆内部阶段，目标 CC 15—20；不要求一次降到 10。
2. `SimulationResult`：替换 9 元组，随后简化 `actions.py` 和 `potion.py`。
3. `_apply_stop_settlement_writes`：把数据库写入步骤和领域计算分开，保持单一事务边界。
4. `render_fishing_scene` 与 `_get_status_json`：分别拆为数据准备、条件选择和最终输出。
5. `gm_add_item`：注册表替代大型命令分支。
6. 其余 CC 20—30 函数结合缺陷率和修改频率再决定，不按指标统一拆分。

## 测试保护情况

测试目录可以收集到 449 个测试，但当前存在 1 个收集错误：`test_miracle_success_rate.py` 直接加载 `starry_system.py` 时相对导入失败。说明测试资产较丰富，但在正式重构前应先修复测试收集，使测试套件能够完整运行。

## 最终评级

- 全局代码质量：中等，可维护但热点明显
- 局部复杂度风险：高
- 全局重写必要性：低
- 分阶段热点重构必要性：中高
- 第一优先事项：测试可运行 + 引擎结果对象化 + 拆 `simulate_fishing_loop`
