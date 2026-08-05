"""
钓鱼菜单指令 handler — 展示常用指令快捷菜单。

QQ官方Bot群聊中发送 Markdown + 消息按钮(Keyboard)，玩家点击按钮即可自动发送对应指令；
OneBot等其他适配器回退为纯文本菜单。
还提供每小时定时向有QQ官方Bot的活跃群推送按钮菜单的定时任务入口。
"""

from __future__ import annotations

import asyncio

from nonebot import get_bots, logger
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
    """向有 QQ 官方 Bot 的活跃群推送钓鱼按钮菜单。

    仅通过 route2 桥接查找有 QQ 官方 Bot 映射的群，
    只发送带按钮的菜单，不发送纯文本，不做任何说明。
    没有 QQ 官方 Bot 的群直接跳过。

    Returns:
        (success_count, fail_count)
    """
    group_ids = await FishingActiveGroup.get_active_group_ids()
    if not group_ids:
        logger.info("[钓鱼菜单] 没有活跃群，跳过推送")
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
        logger.info("[钓鱼菜单] route2 桥接不可用，跳过推送")
        return 0, 0

    bots = get_bots()
    qq_keyboard_msg = None  # 延迟构造，只在首次需要时创建
    success = 0
    fail = 0
    seq = 0

    for group_id in group_ids:
        # 仅向有 QQ 官方 Bot 映射的群发送
        target = bridge.get_target(group_id)
        if not target or target.bot_id not in bots:
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
        except Exception as e:
            logger.warning(f"[钓鱼菜单] 群 {group_id} 按钮推送失败: {e}")
            fail += 1

        await asyncio.sleep(0.3)

    logger.info(f"[钓鱼菜单] 推送完成: 成功 {success} 个群, 失败 {fail} 个群")
    return success, fail
