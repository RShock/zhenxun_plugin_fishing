"""
钓鱼菜单指令 handler — 展示常用指令快捷菜单。

QQ官方Bot群聊中发送 Markdown + 消息按钮(Keyboard)，玩家点击按钮即可自动发送对应指令；
OneBot等其他适配器回退为纯文本菜单。
还提供每小时定时向活跃群推送菜单的定时任务入口。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import asyncio

from nonebot import get_bot, logger
from nonebot.adapters import Event
from nonebot.matcher import Matcher
from nonebot_plugin_alconna import UniMessage

from ..matchers import fishing_menu_matcher
from ..models import FishingActiveGroup
from ..utils import _is_official_qq_group_event, _send_text

if TYPE_CHECKING:
    from nonebot_plugin_alconna.uniseg.segment import Button, Keyboard, Text

# ─────────────────────────────────────────────────────────────────────────────
# 菜单数据 — 按功能分组，每组5条指令
# label: 按钮显示文字（QQ客户端按钮宽度有限，中文限2字否则截断）
# command: 点击后自动发送的指令（enter 模式）
# QQ API 限制：最多 5 行 × 5 个按钮 = 25 个
# ─────────────────────────────────────────────────────────────────────────────
_MENU_BUTTONS: tuple[tuple[str, str], ...] = (
    # 第1行 — 核心
    ("钓鱼", "钓鱼"),
    ("收杆", "收杆"),
    ("状态", "钓鱼状态"),
    ("背包", "背包"),
    ("图鉴", "图鉴"),
    # 第2行 — 经济
    ("卖鱼", "卖鱼"),
    ("鱼店", "鱼店"),
    ("兑换", "钓鱼币兑换"),
    ("打窝", "打窝"),
    ("展示", "升级展示栏"),
    # 第3行 — 强化
    ("鱼竿", "升级钓竿"),
    ("鱼钩", "升级鱼钩"),
    ("黑商", "黑商交换"),
    ("白商", "白商"),
    ("撤回", "黑商撤回"),
    # 第4行 — 交易
    ("赠送", "赠送"),
    ("锁鱼", "锁鱼"),
    ("自卖", "自动卖鱼"),
    ("自锁", "自动锁鱼"),
    ("天气", "天气"),
    # 第5行 — 星空
    ("排行", "星空排行"),
    ("展馆", "星空鱼展馆"),
    ("星艇", "建设星空艇"),
    ("猫园", "建设猫猫乐园"),
    ("改名", "钓鱼改名"),
)


def _build_menu_text() -> str:
    """构建纯文本菜单，用于 OneBot 回退和定时推送。"""
    lines = ["🎣 钓鱼菜单"]
    # 每行5个按钮，按 5 分组输出
    for i in range(0, len(_MENU_BUTTONS), 5):
        row_labels = " | ".join(label for label, _ in _MENU_BUTTONS[i : i + 5])
        lines.append(row_labels)
    return "\n".join(lines)


def _build_menu_keyboard() -> "Keyboard":
    """构建 QQ 官方 Bot 消息按钮键盘。

    25个按钮分5行×5列；每个按钮使用 enter 模式（点击后自动发送指令）。
    """
    from nonebot_plugin_alconna.uniseg.segment import Button, Keyboard

    buttons: list[Button] = []
    for label, command in _MENU_BUTTONS:
        buttons.append(
            Button(
                flag="enter",
                label=label,
                text=command,
                style="blue",
                permission="all",
            )
        )
    # row=5: 每行5个按钮，共5行（QQ限制最多5行×5个）
    return Keyboard(buttons=buttons, row=5)


def _build_markdown_text() -> "Text":
    """构建 QQ 官方 Bot 的 Markdown 文本（作为按钮的载体消息）。"""
    from nonebot_plugin_alconna.uniseg.segment import Text

    text = Text("🎣 钓鱼菜单")
    # 标记为 markdown 样式，QQ 适配器导出时会生成 MessageSegment.markdown
    text.mark(None, None, "markdown")
    return text


@fishing_menu_matcher.handle()
async def _(event: Event, matcher: Matcher):
    """处理"钓鱼菜单"指令。

    QQ官方Bot群聊：发送 Markdown + Keyboard 按钮菜单；
    其他适配器(OneBot等)：发送纯文本菜单。
    若 Markdown+按钮发送失败（如未开通权限），自动回退为纯文本。
    """
    user_id = event.get_user_id()

    # 检测是否为 QQ 官方 Bot 群聊事件
    if not _is_official_qq_group_event(event):
        # OneBot 等适配器：直接发文本菜单
        await _send_text(matcher, _build_menu_text(), user_id)
        return

    # QQ 官方 Bot：尝试发送 Markdown + 按钮菜单
    try:
        msg = UniMessage(_build_markdown_text()) + UniMessage(_build_menu_keyboard())
        await msg.send()
        await matcher.finish()
    except Exception:
        # Markdown 权限未开通或发送失败时回退为纯文本
        # 特性：不是所有 QQ 官方 Bot 都有自定义 Markdown 权限，
        # 未开通时 msg_type=2 的消息会被拒绝，此时回退为普通文本。
        await _send_text(matcher, _build_menu_text(), user_id)


# ─────────────────────────────────────────────────────────────────────────────
# 定时推送菜单 — 供 scheduler.py 调用
# ─────────────────────────────────────────────────────────────────────────────
async def broadcast_menu_to_active_groups() -> tuple[int, int]:
    """向所有活跃群推送钓鱼菜单（纯文本版本）。

    独立于公告服务，不加"钓鱼公告"前缀。
    定时推送无触发事件上下文，无法发送按钮（QQ官Bot主动消息需msg_id），
    因此使用纯文本通过 route2 桥接覆盖所有群。

    Returns:
        (success_count, fail_count)
    """
    group_ids = await FishingActiveGroup.get_active_group_ids()
    if not group_ids:
        logger.info("[钓鱼菜单] 没有活跃群，跳过推送")
        return 0, 0

    try:
        bot = get_bot()
    except Exception:
        logger.warning("[钓鱼菜单] 无法获取 bot 实例，跳过推送")
        return 0, len(group_ids)

    menu_text = _build_menu_text()
    success = 0
    fail = 0

    for idx, group_id in enumerate(group_ids):
        try:
            result = await bot.call_api(
                "send_group_msg",
                group_id=int(group_id),
                message=menu_text,
            )
            if result is None:
                logger.warning(
                    f"[钓鱼菜单] 群 {group_id} 发送返回 None（路由拒绝/不可用）"
                )
                fail += 1
            else:
                success += 1
        except Exception as e:
            logger.warning(f"[钓鱼菜单] 发送到群 {group_id} 失败: {e}")
            fail += 1

        if idx < len(group_ids) - 1:
            await asyncio.sleep(0.3)

    logger.info(f"[钓鱼菜单] 推送完成: 成功 {success} 个群, 失败 {fail} 个群")
    return success, fail
