"""
钓鱼菜单指令 handler — 展示常用指令快捷菜单。

QQ官方Bot群聊中发送 Markdown + 消息按钮(Keyboard)，玩家点击按钮即可自动发送对应指令；
OneBot等其他适配器回退为纯文本菜单。
定时推送采用智能防刷策略：仅向有QQ官方Bot的活跃群推送，且要求该群累计消息>20条
（说明上一次公告已被刷走）且距上次推送超过1小时，才会再次推送。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from nonebot import get_bots, logger, on_message
from nonebot.adapters import Bot, Event
from nonebot.matcher import Matcher

from ..matchers import fishing_menu_matcher
from ..models import FishingActiveGroup
from ..utils import _is_official_qq_group_event, _send_text

# ─────────────────────────────────────────────────────────────────────────────
# 菜单数据 — 智能排版，按标签长度分组
#
# QQ官方Bot按钮在同一行内等宽分配，行内按钮越多每个越窄。
# 2字标签放4个一行（每个1/4屏宽，2字轻松放下）；
# 4字标签放3个一行（每个1/3屏宽，4字不会被截断）。
# 冷门指令（如建设星空艇、升级展示栏）不设按钮，玩家手动输入即可。
# ─────────────────────────────────────────────────────────────────────────────
_MENU_ROWS: tuple[tuple[tuple[str, str], ...], ...] = (
    # 第1行 — 核心操作（4个×2字）
    (("钓鱼", "钓鱼"), ("收杆", "收杆"), ("背包", "背包"), ("卖鱼", "卖鱼")),
    # 第2行 — 常用功能（4个×2字）
    (("鱼店", "鱼店"), ("图鉴", "图鉴"), ("天气", "天气"), ("打窝", "打窝")),
    # 第3行 — 交易设置（3个×2字）
    (("锁鱼", "锁鱼"), ("白商", "白商"), ("赠送", "赠送")),
    # 第4行 — 状态自动（3个×4字）
    (("钓鱼状态", "钓鱼状态"), ("自动卖鱼", "自动卖鱼"), ("自动锁鱼", "自动锁鱼")),
    # 第5行 — 升级交换（3个×4字）
    (("升级钓竿", "升级钓竿"), ("升级鱼钩", "升级鱼钩"), ("黑商交换", "黑商交换")),
)

# ─────────────────────────────────────────────────────────────────────────────
# 消息计数器 — 用于防刷屏推送判断
#
# 仅统计有QQ官方Bot映射的群消息（共享群通过OneBot事件计数，
# QQ官方Bot独有群通过QQ事件计数），key 与 FishingActiveGroup.group_id 一致。
# 推送条件：累计消息 > _PUSH_MSG_THRESHOLD 且距上次推送 > _PUSH_TIME_THRESHOLD
# ─────────────────────────────────────────────────────────────────────────────
_group_msg_counter: dict[str, dict] = {}
_PUSH_MSG_THRESHOLD = 20
_PUSH_TIME_THRESHOLD = timedelta(hours=1)


def _get_event_group_id(event: Event) -> str:
    """从事件中提取群标识（OneBot group_id 或 QQ group_openid）。"""
    gid = str(getattr(event, "group_id", "") or "")
    if gid:
        return gid
    return str(getattr(event, "group_openid", "") or "")


def _is_countable_group_msg(event: Event, bot: Bot) -> bool:
    """Rule: 事件是群消息且有 QQ 官方 Bot 映射。

    共享群通过 OneBot 事件触发（route2 放行 OneBot 事件）；
    QQ官方Bot独有群通过 QQ 事件触发（route2 不拦截）。
    """
    gid = _get_event_group_id(event)
    if not gid:
        return False
    try:
        from zhenxun.plugins.zhenxun_plugin_route2.official_bridge import (
            official_route_bridge as bridge,
        )

        # 共享群：group_id 是 OneBot 群号，bridge 直接能查到
        if bridge.get_target(gid):
            return True
        # QQ官方Bot独有群：group_id 实际是 group_openid，
        # 反查 OneBot 群号后再正向确认
        mapped = bridge.get_group_id_for_official(str(bot.self_id), gid)
        if mapped and bridge.get_target(mapped):
            return True
        return False
    except Exception:
        return False


# 非阻塞消息计数器：priority=1 确保在其他 matcher 之前运行，block=False 不影响其他处理
_msg_counter_matcher = on_message(rule=_is_countable_group_msg, priority=1, block=False)


@_msg_counter_matcher.handle()
async def _count_group_msg(event: Event):
    """累计群消息计数，用于判断公告是否已被刷走。"""
    gid = _get_event_group_id(event)
    if not gid:
        return
    entry = _group_msg_counter.get(gid)
    if entry is None:
        _group_msg_counter[gid] = {"count": 1, "last_push": None}
    else:
        entry["count"] += 1


def _build_menu_text() -> str:
    """构建纯文本菜单，用于 OneBot 回退。"""
    lines = []
    for row in _MENU_ROWS:
        labels = " | ".join(label for label, _ in row)
        lines.append(labels)
    return "\n".join(lines)


def _build_qq_keyboard_message(markdown_text: str = "🎣 钓鱼菜单"):
    """直接构造 QQ 官方 Bot 的 Message 对象（含 Markdown + Keyboard）。

    使用 InlineKeyboardRow 为每行按钮创建独立行，确保智能排版：
    短标签多放、长标签少放，避免文字被截断。
    """
    from nonebot.adapters.qq import Message as QQMessage
    from nonebot.adapters.qq import MessageSegment as QQMessageSegment
    from nonebot.adapters.qq.models.common import (
        Action,
        Button,
        InlineKeyboard,
        InlineKeyboardRow,
        MessageKeyboard,
        Permission,
        RenderData,
    )

    # QQ API 要求 markdown 必填，不支持仅下发键盘消息
    msg = QQMessage(QQMessageSegment.markdown(markdown_text))

    rows = []
    for row_buttons in _MENU_ROWS:
        buttons = []
        for label, command in row_buttons:
            buttons.append(
                Button(
                    render_data=RenderData(
                        label=label,
                        visited_label=label,
                        style=1,  # 蓝色线框
                    ),
                    action=Action(
                        type=2,  # 指令按钮：自动在输入框插入 @bot data
                        data=command,
                        enter=True,  # 点击后直接自动发送
                        permission=Permission(type=2),  # 所有人可操作
                        unsupport_tips="请升级至最新版本",
                    ),
                )
            )
        rows.append(InlineKeyboardRow(buttons=buttons))

    keyboard = MessageKeyboard(content=InlineKeyboard(rows=rows))
    msg.append(QQMessageSegment.keyboard(keyboard))
    return msg


@fishing_menu_matcher.handle()
async def _(bot: Bot, event: Event, matcher: Matcher):
    """处理"钓鱼菜单"指令。

    QQ官方Bot群聊：直接构造并发送 Markdown + Keyboard 按钮菜单；
    其他适配器(OneBot等)：发送纯文本菜单。
    若 Markdown+按钮发送失败（如未开通权限），自动回退为纯文本。
    """
    user_id = event.get_user_id()

    if not _is_official_qq_group_event(event):
        await _send_text(matcher, _build_menu_text(), user_id)
        return

    # QQ 官方 Bot：直接构造 QQ 原生 Message 并通过 bot.send 发送
    # 特性：不用 UniMessage/Alconna 导出器，直接构造 InlineKeyboardRow
    # 确保每行按钮独立排版，避免导出器合并行导致文字截断
    try:
        msg = _build_qq_keyboard_message()
        await bot.send(event, msg)
        await matcher.finish()
    except Exception:
        # Markdown 权限未开通或发送失败时回退为纯文本
        await _send_text(matcher, _build_menu_text(), user_id)


# ─────────────────────────────────────────────────────────────────────────────
# 定时推送菜单 — 供 scheduler.py 调用
# ─────────────────────────────────────────────────────────────────────────────
async def broadcast_menu_to_active_groups() -> tuple[int, int]:
    """向有 QQ 官方 Bot 的活跃群推送钓鱼按钮菜单（智能防刷）。

    仅通过 route2 桥接查找有 QQ 官方 Bot 映射的群，
    且要求该群自上次推送后累计消息 > 20 条（公告已被刷走）且距上次推送 > 1 小时。
    两个条件同时满足才推送，推送后重置计数器。
    没有 QQ 官方 Bot 的群直接跳过。

    Returns:
        (success_count, fail_count)
    """
    group_ids = await FishingActiveGroup.get_active_group_ids()
    if not group_ids:
        return 0, 0

    # route2 桥接提供 OneBot 群号 → QQ 官方 Bot 群映射
    bridge = None
    try:
        from zhenxun.plugins.zhenxun_plugin_route2.official_bridge import (
            official_route_bridge as bridge,
        )
    except Exception:
        pass

    if bridge is None:
        return 0, 0

    bots = get_bots()
    qq_keyboard_msg = None  # 延迟构造，只在首次需要时创建
    success = 0
    fail = 0
    seq = 0
    now = datetime.now()

    for group_id in group_ids:
        # 仅向有 QQ 官方 Bot 映射的群发送
        target = bridge.get_target(group_id)
        if not target or target.bot_id not in bots:
            continue

        # 防刷屏判断：累计消息 > 阈值 且 距上次推送 > 时间阈值
        entry = _group_msg_counter.get(group_id)
        if entry is None:
            # 该群从未有消息计数（可能刚启动），跳过
            continue
        if entry["count"] <= _PUSH_MSG_THRESHOLD:
            # 消息不够多，公告还没被刷走
            continue
        last_push = entry.get("last_push")
        if last_push is not None and now - last_push < _PUSH_TIME_THRESHOLD:
            # 距上次推送不足1小时
            continue

        seq += 1
        try:
            if qq_keyboard_msg is None:
                qq_keyboard_msg = _build_qq_keyboard_message("🎣")
            qq_bot = bots[target.bot_id]
            await qq_bot.send_to_group(
                group_openid=target.group_openid,
                message=qq_keyboard_msg,
                msg_seq=seq,
            )
            success += 1
            # 推送成功：重置计数器，记录推送时间
            entry["count"] = 0
            entry["last_push"] = now
        except Exception as e:
            logger.warning(f"[钓鱼菜单] 群 {group_id} 按钮推送失败: {e}")
            fail += 1

        await asyncio.sleep(0.3)

    if success > 0 or fail > 0:
        logger.info(f"[钓鱼菜单] 推送完成: 成功 {success} 个群, 失败 {fail} 个群")
    return success, fail
