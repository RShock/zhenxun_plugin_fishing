# zhenxun_plugin_fishing

真寻 Bot 的钓鱼小游戏插件，包含普通钓鱼、背包与商店、天气、猫猫乐园、星空钓鱼、网页端和 GM 管理能力。

## 目录结构

| 路径 | 职责 |
|---|---|
| `handlers/` | NoneBot 命令适配与消息发送 |
| `web/` | WebSocket、HTTP API、网页命令适配与静态页面 |
| `core/` | 钓鱼模拟、概率、结算、药水与场景编排 |
| `backpack/` | 背包、出售、赠送、锁鱼与黑白商 |
| `shop/` | 商店、升级、打窝、药水与账户操作 |
| `services/` | 用户、成就、展示、公告和限流服务 |
| `models/` | ORM 模型与持久化状态变更 |
| `render/` | 页面数据准备和 HTML/图片渲染 |
| `templates/` | Jinja2 页面模板 |
| `config/` | 鱼、地点和商店数据配置 |
| `resources/` | 字体、鱼图、场景、人物和活动资源 |
| `tests/` | 单元测试与回归测试 |
| `ci/` | 独立插件测试所需的轻量运行环境 |
| `tools/` | 不参与运行时导入的模拟、素材和打包工具 |
| `doc/` | 历史设计、数值研究和原型档案，整理时必须保留 |

`fishing.py` 是旧 API 兼容入口；新代码应直接从 `core/` 导入。`backpack/` 和 `shop/` 的公开接口统一由各自 `__init__.py` 导出。

## 本地测试

```powershell
python ci/setup_path.py
$env:PYTHONPATH = "$PWD\ci\runtime;$PWD\ci;$PWD"
$env:ZX_LIGHTWEIGHT_NONEBOT_STUBS = "1"
python -m pytest tests -q --confcutdir=.
```

## 文档入口

- `AI_MAINTENANCE.md`：维护流程、架构规则和修改检查表
- 运行时技术约束：就近写在对应模块、类与函数注释中
- `web/static/help.html`：面向玩家的玩法帮助，保持手工维护
- `DESIGN.md`：设计入口
- `doc/`：历史设计与研究档案
