"""
钓鱼菜单指令 handler — 展示常用指令快捷菜单。

QQ官方Bot群聊中发送一条带快捷按钮的菜单卡片，点击按钮直接发送对应基础指令；
OneBot等其他适配器回退为纯文本菜单。
QQ 群聊不支持官方 Markdown 指令标签，因此群聊不尝试发送 qqbot-cmd-enter。
定时推送采用智能防刷策略：仅向有QQ官方Bot的活跃群推送，且要求该群累计消息>20条
（说明上一次公告已被刷走）且距上次推送超过1小时，才会再次推送。

支持两种群类型：
1. 共享群（OneBot + QQ官方Bot同时在场）：通过 route2 桥接映射查找
2. QQ官方Bot独有群（无OneBot）：group_id 即 group_openid，
   直接用任意已连接的QQ官方Bot发送
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

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
# 每个按钮都直接提交对应基础指令；需要参数的命令由原有 handler 返回提示，
# 避免用户停留在输入框却没有发送。
# ─────────────────────────────────────────────────────────────────────────────
_MENU_ROWS: tuple[tuple[tuple[str, str], ...], ...] = (
    # 第1行 — 核心操作（4个×2字）
    (
        ("钓鱼", "钓鱼"),
        ("收杆", "收杆"),
        ("背包", "背包"),
        ("卖鱼", "卖鱼"),
    ),
    # 第2行 — 常用功能（4个×2字）
    (
        ("鱼店", "鱼店"),
        ("图鉴", "图鉴"),
        ("天气", "天气"),
        ("打窝", "打窝"),
    ),
    # 第3行 — 交易设置（3个×2字）
    (("锁鱼", "锁鱼"), ("白商", "白商"), ("赠送", "赠送")),
    # 第4行 — 状态与快捷操作（3个×4字）
    (
        ("钓鱼状态", "钓鱼状态"),
        ("钓鱼使用", "钓鱼使用"),
        ("鱼店购买", "鱼店购买"),
    ),
    # 第5行 — 升级排行（3个×4字）
    (
        ("升级钓竿", "升级钓竿"),
        ("升级鱼钩", "升级鱼钩"),
        ("星空排行", "星空排行"),
    ),
)

# ─────────────────────────────────────────────────────────────────────────────
# 消息计数器 — 用于防刷屏推送判断
#
# 统计所有有QQ官方Bot在场的群消息：
# - 共享群：无论消息来自 OneBot 还是 QQ 官方 Bot，key 都归一为数字群号
# - QQ官方Bot独有群：保留 group_openid 作为 key
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
        labels = " | ".join(label for label, _ in row)
        lines.append(labels)
    return "\n".join(lines)


def _build_qq_keyboard_message(markdown_text: str = "🎣 钓鱼菜单"):
    """构建 QQ 官方 Bot 群聊可用的 Markdown + Keyboard 消息。

    群聊不支持 qqbot-cmd-enter/qqbot-cmd-input，因此按钮使用 QQ Keyboard
    的 enter=True，让点击操作直接提交按钮中的基础指令。
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

    # QQ API 要求 Markdown 字段，键盘则提供可点击的按钮。
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
                        type=2,  # 指令按钮：data 是要发送的指令
                        data=command,
                        enter=True,  # 点击后直接发送，不只写入输入框
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
    """处理“钓鱼菜单”指令。"""
    user_id = event.get_user_id()

    if not _is_official_qq_group_event(event):
        # 共享群由 QQ 官方 Bot 发送，OneBot 事件不重复发送纯文本。
        gid = _get_event_group_id(event)
        if gid:
            try:
                from zhenxun.plugins.zhenxun_plugin_route2.official_bridge import (
                    official_route_bridge as bridge,
                )

                if bridge.get_target(gid):
                    return
            except Exception:
                pass
        await _send_text(matcher, _build_menu_text(), user_id)
        return

    try:
        menu = _build_qq_keyboard_message()
        group_openid = str(getattr(event, "group_openid", "") or "")
        send_to_group = getattr(bot, "send_to_group", None)
        if not group_openid or not callable(send_to_group):
            raise RuntimeError("当前 QQ Bot 不支持群聊主动发送接口")
        # 使用群聊主动发送接口，不依赖入站消息的回复窗口；这也是任意发送权限的用法。
        await send_to_group(group_openid=group_openid, message=menu)
    except Exception as e:
        logger.warning(f"[钓鱼菜单] QQ群卡片发送失败，回退纯文本: {e}")
        await _send_text(matcher, _build_menu_text(), user_id)
    # 不调用 matcher.finish()：finish 会抛出控制流异常，不能被发送失败回退逻辑捕获。


def _find_qq_bot_for_group(group_id: str, bridge, bots: dict) -> tuple[Bot, str] | None:
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
    - QQ官方Bot独有群（无OneBot）：group_id 即 group_openid，
      直接用已连接的 QQ 官方 Bot 发送

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
                qq_menu_msg = _build_qq_keyboard_message()
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
