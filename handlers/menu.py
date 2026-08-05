"""
钓鱼菜单指令 handler — 展示常用指令快捷菜单。

QQ官方Bot群聊中发送 Markdown + 消息按钮(Keyboard)，玩家点击按钮即可自动发送对应指令；
OneBot等其他适配器回退为纯文本菜单。
还提供每小时定时向活跃群推送菜单的定时任务入口。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from nonebot.adapters import Event
from nonebot.matcher import Matcher
from nonebot_plugin_alconna import UniMessage

from ..matchers import fishing_menu_matcher
from ..utils import _is_official_qq_group_event, _send_text

if TYPE_CHECKING:
    from nonebot_plugin_alconna.uniseg.segment import Button, Keyboard, Text

# ─────────────────────────────────────────────────────────────────────────────
# 菜单数据 — 按功能分组，每组最多4条指令
# label: 按钮显示文字（≤6个中文字符）；command: 点击后自动发送的指令
# ─────────────────────────────────────────────────────────────────────────────
_MENU_GROUPS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    ("核心", (
        ("钓鱼", "钓鱼"),
        ("收杆", "收杆"),
        ("钓鱼状态", "钓鱼状态"),
        ("背包", "背包"),
    )),
    ("经济", (
        ("卖鱼", "卖鱼"),
        ("鱼店", "鱼店"),
        ("兑换", "钓鱼币兑换"),
        ("图鉴", "图鉴"),
    )),
    ("强化", (
        ("升级钓竿", "升级钓竿"),
        ("升级鱼钩", "升级鱼钩"),
        ("打窝", "打窝"),
        ("升级展示栏", "升级展示栏"),
    )),
    ("交易", (
        ("黑商", "黑商交换"),
        ("白商", "白商"),
        ("赠送", "赠送"),
        ("锁鱼", "锁鱼"),
    )),
    ("星空", (
        ("星空排行", "星空排行"),
        ("星空展馆", "星空鱼展馆"),
        ("建设星空艇", "建设星空艇"),
        ("天气", "天气"),
    )),
)


def _build_menu_text() -> str:
    """构建纯文本菜单，用于 OneBot 回退和定时推送。"""
    lines = ["🎣 钓鱼菜单"]
    lines.append("点击对应指令即可使用\n")
    for group_name, commands in _MENU_GROUPS:
        cmds = " | ".join(cmd for _, cmd in commands)
        lines.append(f"【{group_name}】{cmds}")
    lines.append('\n💡 如"钓鱼 1"可指定地图，"卖鱼 SSR"可按稀有度卖出')
    return "\n".join(lines)


def _build_menu_keyboard() -> "Keyboard":
    """构建 QQ 官方 Bot 消息按钮键盘。

    每组4个按钮，共5行；每个按钮使用 enter 模式（点击后自动发送指令）。
    """
    from nonebot_plugin_alconna.uniseg.segment import Button, Keyboard

    buttons: list[Button] = []
    for _, commands in _MENU_GROUPS:
        for label, command in commands:
            buttons.append(
                Button(
                    flag="enter",
                    label=label,
                    text=command,
                    style="blue",
                    permission="all",
                )
            )
    # row=4: 每行4个按钮，共5行（QQ限制最多5行×5个）
    return Keyboard(buttons=buttons, row=4)


def _build_markdown_text() -> "Text":
    """构建 QQ 官方 Bot 的 Markdown 文本（作为按钮的载体消息）。"""
    from nonebot_plugin_alconna.uniseg.segment import Text

    lines = ["# 🎣 钓鱼菜单"]
    lines.append("点击下方按钮快速执行指令\n")
    for group_name, commands in _MENU_GROUPS:
        labels = " | ".join(label for label, _ in commands)
        lines.append(f"**【{group_name}】** {labels}")
    lines.append("\n> 💡 按钮点击后自动发送对应指令")
    text = Text("\n".join(lines))
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

    定时任务每小时调用一次。使用纯文本而非按钮，因为：
    1. 定时推送无触发事件上下文，无法确定每个群的适配器类型；
    2. 纯文本通过 route2 桥接可同时覆盖 OneBot 群和 QQ 官方 Bot 群；
    3. 避免高频 Markdown 消息触发 QQ 审核机制。

    Returns:
        (success_count, fail_count)
    """
    from ..services import broadcast_to_active_groups

    menu_text = _build_menu_text()
    # broadcast_to_active_groups 会自动添加 "🎣 钓鱼公告" 前缀，
    # 此处直接传入菜单文本，利用其广播基础设施
    success, fail = await broadcast_to_active_groups(menu_text)
    return success, fail
