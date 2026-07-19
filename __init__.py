"""
钓鱼插件 — 核心入口模块。

架构分层（重构后）：
- constants.py:    游戏设计常量（稀有度表、概率分布、天气数据）
- config.py:       配置管理（Pydantic 模型 + JSON 加载）
- core/:           钓鱼核心逻辑（引擎、场景、鱼饵、猫、药水、结果处理）
- shop/:           商店子系统（购买、升级、打窝、药水、皮肤、兑换）
- backpack/:       背包子系统（鱼获选择、卖鱼、赠送、锁定、图鉴）
- models/:         数据模型（user/buff/weather）
- services/:       服务层（成就/buff/展示/用户）
- render/:         Jinja2 模板渲染
- matchers.py:     所有 on_regex() Matcher 定义
- handlers/:       bot 命令 handler 函数（按功能拆分）
- gm.py:           GM 调试命令
- scheduler.py:    定时任务（天气/Buff/备份/Web）
- web/:            Web API + WebSocket 服务器
"""

from nonebot import require
from nonebot.plugin import PluginMetadata

require("nonebot_plugin_apscheduler")
require("nonebot_plugin_session")

from zhenxun.configs.utils import Command, PluginCdBlock, PluginExtraData

__plugin_meta__ = PluginMetadata(
    name="钓鱼",
    description="钓鱼模拟游戏，抛竿垂钓，收集图鉴",
    usage="""
    指令列表：
        钓鱼/抛竿 [地点编号]       开始钓鱼
        收杆                      收杆查看结果
        钓鱼状态                   查看当前状态
        背包                      查看鱼获背包
        卖鱼 [稀有度/鱼ID]        卖出鱼获
        锁鱼 [稀有度/鱼ID]        锁定鱼获防止卖出
        解锁 [稀有度/鱼ID]        解锁鱼获
        赠送/送鱼 [鱼ID]          赠送鱼获给群友
        自动卖鱼 [稀有度]          设置自动卖出
        自动锁鱼 [通配符]          设置自动锁定
        鱼店                      浏览商店
        鱼店购买 [物品] [数量]     购买商品
        升级钓竿                   升级鱼竿
        升级鱼钩                   升级鱼钩
        升级展示栏               扩充展示位/强化展示位
        打窝 [次数]                使用玉米打窝
        钓鱼使用 猫猫框 [数量]     在11-20图使用猫猫框打窝
        钓鱼图鉴/图鉴/图鉴2       查看图鉴
        钓鱼币兑换 [数量]          兑换钓鱼币
        钓鱼改名 [名称]            修改钓鱼昵称
        更换皮肤 [皮肤ID]          更换皮肤
        天气预报/天气              查看天气
        黑商/白商                 黑商交换与白商逆交换
        钓鱼公告 [内容]            (超管)向活跃群广播公告
    """.strip(),
    extra=PluginExtraData(
        author="",
        version="1.0.0",
        commands=[
            Command(command="钓鱼"),
            Command(command="抛竿"),
            Command(command="收杆"),
            Command(command="钓鱼状态"),
            Command(command="背包"),
            Command(command="卖鱼"),
            Command(command="锁鱼"),
            Command(command="解锁"),
            Command(command="赠送"),
            Command(command="送鱼"),
            Command(command="自动卖鱼"),
            Command(command="自动锁鱼"),
            Command(command="黑商交换"),
            Command(command="白商"),
            Command(command="白商交换"),
            Command(command="钓鱼使用"),
            Command(command="鱼店"),
            Command(command="鱼币商店"),
            Command(command="钓鱼商店"),
            Command(command="鱼店购买"),
            Command(command="升级钓竿"),
            Command(command="升级鱼竿"),
            Command(command="升级鱼钩"),
            Command(command="升级展示栏"),
            Command(command="增加展示栏位"),
            Command(command="强化展示栏位"),
            Command(command="打窝"),
            Command(command="钓鱼图鉴"),
            Command(command="图鉴"),
            Command(command="查看图鉴"),
            Command(command="流星鱼展馆"),
            Command(command="钓鱼币兑换"),
            Command(command="钓鱼改名"),
            Command(command="更换皮肤"),
            Command(command="天气预报"),
            Command(command="钓鱼天气"),
            Command(command="天气"),
            Command(command="天气状态"),
            Command(command="建设猫猫乐园"),
            Command(command="建设星空艇"),
            Command(command="钓鱼公告"),
        ],
        limits=[PluginCdBlock()],
    ).to_dict(),
)

# ═══════════════════════════════════════════════════════════════════════════════
# 【临时迁移代码 — 确认旧数据修复后删除此段】
# 修复旧版展示木框 buff：将 BUFF_TYPE_NEST + TARGET_TYPE_LOCATION 中
# description 包含"展示木框"的记录转换为 BUFF_TYPE_FRAME + TARGET_TYPE_GLOBAL
# ═══════════════════════════════════════════════════════════════════════════════
from datetime import datetime

from nonebot import get_driver

from . import handlers  # noqa: F401 — 触发 handler 装饰器注册
from . import scheduler  # noqa: F401 — 触发定时任务注册
from .matchers import auto_sell_matcher  # noqa: F401 — 导出给外部引用
from .matchers import (
    backpack_matcher,
    black_market_matcher,
    build_starry_ship_matcher,
    buy_matcher,
    cat_park_build_matcher,
    collection_matcher,
    debug_render_matcher,
    display_slot_matcher,
    exchange_matcher,
    fishing_announcement_matcher,
    fishing_matcher,
    gift_fish_matcher,
    gm_add_item_matcher,
    gm_add_skin_matcher,
    gm_check_achievements_matcher,
    gm_force_stop_matcher,
    gm_give_fish_matcher,
    gm_give_gold_matcher,
    gm_limit_off_matcher,
    gm_limit_on_matcher,
    gm_money_matcher,
    gm_reset_matcher,
    gm_rollback_hook_matcher,
    gm_rollback_rod_matcher,
    gm_set_gold_matcher,
    gm_weather_info_matcher,
    gm_weather_reset_matcher,
    lock_fish_matcher,
    nest_matcher,
    rename_matcher,
    sell_fish_matcher,
    shop_matcher,
    starry_exhibition_matcher,
    skin_matcher,
    status_matcher,
    stop_fishing_matcher,
    test_render_matcher,
    test_scene_render_matcher,
    unlock_fish_matcher,
    upgrade_hook_matcher,
    upgrade_rod_matcher,
    weather_forecast_matcher,
    white_market_exchange_matcher,
    white_market_matcher,
)
from .models import FishingBuff, FishingUser


@get_driver().on_startup
async def _migrate_frame_buffs():
    from .models import BuffEffect

    old_buffs = await FishingBuff.filter(
        buff_type=BuffEffect.BUFF_TYPE_NEST,
        target_type=BuffEffect.TARGET_TYPE_LOCATION,
        description__contains="展示木框",
        end_time__gt=datetime.now(),
    ).all()
    if not old_buffs:
        return
    for buff in old_buffs:
        buff.buff_type = BuffEffect.BUFF_TYPE_FRAME
        buff.target_type = BuffEffect.TARGET_TYPE_GLOBAL
        buff.target_id = ""
        buff.description = "展示木框效果，1-10图与S1钓鱼速度+5%"
        await buff.save(
            update_fields=["buff_type", "target_type", "target_id", "description"]
        )
    logger.info(
        f"[迁移] 已修复 {len(old_buffs)} 条旧版展示木框 buff（NEST→FRAME, LOCATION→GLOBAL）"
    )


@get_driver().on_startup
async def _init_dragon_boat_buff():
    """端午活动：启动时检查并创建全局Buff（6.19 00:00 ~ 6.22 00:00）。"""
    from .models import BuffEffect

    existing = await FishingBuff.check_dragon_boat_buff()
    if not existing:
        await FishingBuff.create_dragon_boat_buff()
        logger.info("[端午活动] 已创建端午全局Buff（6.19 00:00 ~ 6.22 00:00）")


# ═══════════════════════════════════════════════════════════════════════════════
# 【临时迁移代码结束】
# ═══════════════════════════════════════════════════════════════════════════════
