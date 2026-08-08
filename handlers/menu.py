"""
钓鱼菜单指令 handler — 展示常用指令快捷菜单。

QQ官方Bot群聊中发送 Markdown（内嵌 qqbot-cmd-enter / qqbot-cmd-input 标签），
玩家点击链接即可直接发送指令或插入输入框；
OneBot等其他适配器回退为纯文本菜单。
定时推送采用智能防刷策略：仅向有QQ官方Bot的活跃群推送，且要求该群累计消息>20条
（说明上一次公告已被刷走）且距上次推送超过1小时，才会再次推送。

支持两种群类型：
1. 共享群（OneBot + QQ官方Bot同时在场）：通过 route2 桥接映射查找
2. QQ官方Bot独有群（无OneBot）：group_id 即 group_openid，直接用任意已连接的QQ官方Bot发送
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from urllib.parse import quote

from nonebot import get_bots, logger, on_message
from nonebot.adapters import Bot, Event
from nonebot.matcher import Matcher

from ..matchers import fishing_menu_matcher
from ..models import FishingActiveGroup
from ..utils import (
    _get_group_context_id,
    _is_official_qq_group_event,
    _send_text,
)

# ─────────────────────────────────────────────────────────────────────────────
# 菜单数据 — 智能排版，按标签长度分组
#
# QQ官方Bot按钮在同一行内等宽分配，行内按钮越多每个越窄。
# 2字标签放4个一行（每个1/4屏宽，2字轻松放下）；
# 4字标签放3个一行（每个1/3屏宽，4字不会被截断）。
# 冷门指令（如建设星空艇、升级展示栏、黑商交换）不设按钮，玩家手动输入即可。
#
# 每个按钮三元组：(label, command, enter)
# enter=True  → 点击后直接自动发送（适用于无参数指令）
# enter=False → 仅插入输入框，待玩家补充参数后手动发送
# ─────────────────────────────────────────────────────────────────────────────
_MENU_ROWS: tuple[tuple[tuple[str, str, bool], ...], ...] = (
    # 第1行 — 核心操作（4个×2字）
    (("钓鱼", "钓鱼", False), ("收杆", "收杆", True), ("背包", "背包", True), ("卖鱼", "卖鱼", False)),
    # 第2行 — 常用功能（4个×2字）
    (("鱼店", "鱼店", True), ("图鉴", "图鉴", False), ("天气", "天气", False), ("打窝", "打窝", False)),
    # 第3行 — 交易设置（3个×2字）
    (("锁鱼", "锁鱼", False), ("白商", "白商", False), ("赠送", "赠送", False)),
    # 第4行 — 状态自动（3个×4字）
    (("钓鱼状态", "钓鱼状态", True), ("自动卖鱼", "自动卖鱼", False), ("自动锁鱼", "自动锁鱼", False)),
    # 第5行 — 升级排行（3个×4字）
    (("升级钓竿", "升级钓竿", True), ("升级鱼钩", "升级鱼钩", True), ("星空排行", "星空排行", True)),
)

# ─────────────────────────────────────────────────────────────────────────────
# 消息计数器 — 用于防刷屏推送判断
#
# 统计所有有QQ官方Bot在场的群消息：
# - 共享群：OneBot 事件触发计数（route2 放行 OneBot 事件），key 为数字群号
# - QQ官方Bot独有群：QQ 事件触发计数（route2 不拦截），key 为 group_openid
# 推送条件：累计消息 > _PUSH_MSG_THRESHOLD 且距上次推送 > _PUSH_TIME_THRESHOLD
# ─────────────────────────────────────────────────────────────────────────────
_group_msg_counter: dict[str, dict] = {}
_PUSH_MSG_THRESHOLD = 20
_PUSH_TIME_THRESHOLD = timedelta(hours=1)


def _get_event_group_id(event: Event) -> str:
    """提取与玩法记录一致的群标识，避免共享群被拆成两套计数。"""
    return _get_group_context_id(event) or ""


def _is_countable_group_msg(event: Event, bot: Bot) -> bool:
    """Rule: 事件是群消息且该群有 QQ 官方 Bot 在场。

    共享群（OneBot + QQ官方Bot）：OneBot 事件通过 bridge.get_target 查到映射 → 计数
    QQ官方Bot独有群（无OneBot）：QQ 事件直接计数（bot 本身就是 QQ 官方 Bot）
    """
    gid = _get_event_group_id(event)
    if not gid:
        return False
    try:
        from zhenxun.plugins.zhenxun_plugin_route2.official_bridge import (
            official_route_bridge as bridge,
        )

        # 共享群：group_id 是 OneBot 数字群号，bridge 直接能查到
        if bridge.get_target(gid):
            return True
        # QQ官方Bot独有群：bot 本身就是 QQ 官方 Bot，事件直接到达
        # 此时 group_id 即 group_openid，无需 route2 映射
        if str(bot.self_id) in bridge.official_bot_ids:
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
        labels = " | ".join(label for label, _, _ in row)
        lines.append(labels)
    return "\n".join(lines)


def _build_qq_markdown_content() -> str:
    """构建含 qqbot-cmd-enter / qqbot-cmd-input 标签的 Markdown 内容。

    qqbot-cmd-enter：点击后直接发送指令（适用于无参数指令）
    qqbot-cmd-input：点击后插入输入框，待玩家补充参数后手动发送
    text/show 参数需 urlencode，QQ 客户端会自动解码显示原文。
    """
    lines = ["🎣 钓鱼菜单", ""]
    for row_buttons in _MENU_ROWS:
        parts = []
        for label, command, enter in row_buttons:
            encoded_cmd = quote(command)
            if enter:
                # 点击后直接自动发送，无需 show 参数（客户端展示解码后的 text）
                parts.append(f'<qqbot-cmd-enter text="{encoded_cmd}" />')
            else:
                # 仅插入输入框，show 设为标签文本便于玩家识别
                encoded_label = quote(label)
                parts.append(
                    f'<qqbot-cmd-input text="{encoded_cmd}" show="{encoded_label}" />'
                )
        lines.append(" ".join(parts))
        lines.append("")  # 空行分隔每行
    return "\n".join(lines)


def _build_qq_markdown_message():
    """构造仅含 Markdown（内嵌指令链接）的 QQ Message 对象。"""
    from nonebot.adapters.qq import Message as QQMessage
    from nonebot.adapters.qq import MessageSegment as QQMessageSegment

    return QQMessage(QQMessageSegment.markdown(_build_qq_markdown_content()))


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
        for label, command, enter in row_buttons:
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
                        enter=enter,  # True=点击后直接自动发送，False=仅插入输入框
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

    QQ官方Bot群聊：发送含 qqbot-cmd-enter 指令链接的 Markdown 菜单；
    共享群中 OneBot 事件跳过（由 QQ 官方 Bot 统一发送，避免双发）；
    其他适配器(OneBot等)：发送纯文本菜单。
    若 Markdown 发送失败，回退为键盘按钮，再回退为纯文本。
    """
    user_id = event.get_user_id()

    if not _is_official_qq_group_event(event):
        # OneBot 事件：共享群中 QQ 官方 Bot 会发送指令链接菜单，OneBot 不重复发送纯文本
        gid = _get_event_group_id(event)
        if gid:
            try:
                from zhenxun.plugins.zhenxun_plugin_route2.official_bridge import (
                    official_route_bridge as bridge,
                )
                if bridge.get_target(gid):
                    return  # QQ 官方 Bot 会处理，跳过避免双发
            except Exception:
                pass
        await _send_text(matcher, _build_menu_text(), user_id)
        return

    # QQ 官方 Bot：优先发送含指令链接的 Markdown（点击即发送/插入输入框）
    try:
        msg = _build_qq_markdown_message()
        await bot.send(event, msg)
        await matcher.finish()
    except Exception:
        # Markdown 发送失败时回退为键盘按钮
        try:
            msg = _build_qq_keyboard_message()
            await bot.send(event, msg)
            await matcher.finish()
        except Exception:
            await _send_text(matcher, _build_menu_text(), user_id)


def _find_qq_bot_for_group(
    group_id: str, bridge, bots: dict
) -> tuple[Bot, str] | None:
    """查找可向指定群发送消息的 QQ 官方 Bot 及其 group_openid。

    返回 (bot, group_openid) 或 None。

    两种群类型：
    1. 共享群：group_id 是 OneBot 数字群号，通过 bridge.get_target 查找
    2. QQ官方Bot独有群：group_id 即 group_openid（非纯数字），用任意已连接QQ官方Bot发送

    特性：共享群在 OneBot 临时离线时，QQ官方Bot事件不被 route2 拦截，
    会导致活跃群表同时存在数字群号和 group_openid 两条记录。
    此函数对已映射到 OneBot 群号的 group_openid 返回 None，避免重复发送。
    """
    # 1. 共享群：通过 route2 映射查找
    target = bridge.get_target(group_id)
    if target and target.bot_id in bots:
        bot = bots[target.bot_id]
        if hasattr(bot, "send_to_group"):
            return bot, target.group_openid

    # 2. QQ官方Bot独有群：group_id 是 group_openid（非纯数字字符串）
    if not group_id.isdigit():
        # 去重：如果该 group_openid 已在 route2 映射中（即共享群），
        # 说明数字群号那条记录会处理推送，此处跳过避免重复发送
        for bot_id in bridge.official_bot_ids:
            if bridge.get_group_id_for_official(bot_id, group_id):
                return None
        # 真正的 QQ官方Bot独有群，用任意已连接的 QQ 官方 Bot 发送
        for bot_id in bridge.preferred_bot_ids or bridge.official_bot_ids:
            if bot_id in bots:
                bot = bots[bot_id]
                if hasattr(bot, "send_to_group"):
                    return bot, group_id

    return None


# ─────────────────────────────────────────────────────────────────────────────
# 定时推送菜单 — 供 scheduler.py 调用
# ─────────────────────────────────────────────────────────────────────────────
async def broadcast_menu_to_active_groups() -> tuple[int, int]:
    """向有 QQ 官方 Bot 的活跃群推送钓鱼按钮菜单（智能防刷）。

    支持两种群类型：
    - 共享群（OneBot + QQ官方Bot）：通过 route2 映射查找 QQ 官方 Bot
    - QQ官方Bot独有群（无OneBot）：group_id 即 group_openid，直接用已连接的 QQ 官方 Bot 发送

    推送条件：累计消息 > 20 条（公告已被刷走）且距上次推送 > 1 小时。
    推送后重置计数器。没有 QQ 官方 Bot 的群直接跳过。

    Returns:
        (success_count, fail_count)
    """
    group_ids = await FishingActiveGroup.get_active_group_ids()
    if not group_ids:
        return 0, 0

    # route2 桥接提供 QQ 官方 Bot 配置和群映射
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
    qq_menu_msg = None  # 延迟构造，只在首次需要时创建
    success = 0
    fail = 0
    seq = 0
    now = datetime.now()
    sent_openids: set[str] = set()  # 已推送的 group_openid 集合，防止重复发送

    for group_id in group_ids:
        # 查找可向该群发送的 QQ 官方 Bot
        result = _find_qq_bot_for_group(group_id, bridge, bots)
        if result is None:
            continue
        qq_bot, group_openid = result

        # 去重：同一 group_openid 只发送一次（防止共享群双ID记录导致重复）
        if group_openid in sent_openids:
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
            if qq_menu_msg is None:
                qq_menu_msg = _build_qq_markdown_message()
            await qq_bot.send_to_group(
                group_openid=group_openid,
                message=qq_menu_msg,
                msg_seq=seq,
            )
            success += 1
            # 推送成功：重置计数器，记录推送时间，标记已发送
            entry["count"] = 0
            entry["last_push"] = now
            sent_openids.add(group_openid)
        except Exception as e:
            logger.warning(f"[钓鱼菜单] 群 {group_id} 推送失败: {e}")
            fail += 1

        await asyncio.sleep(0.3)

    if success > 0 or fail > 0:
        logger.info(f"[钓鱼菜单] 推送完成: 成功 {success} 个群, 失败 {fail} 个群")
    return success, fail
