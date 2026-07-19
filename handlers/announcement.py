"""
公告指令 handler — 钓鱼公告广播。

SUPERUSER 专用，向所有活跃群（最近2天内有人收杆的群）广播消息。
"""

from nonebot.adapters import Event
from nonebot.matcher import Matcher
from nonebot.params import RegexGroup

from ..matchers import fishing_announcement_matcher
from ..services import broadcast_to_active_groups
from ..utils import _send_text


@fishing_announcement_matcher.handle()
async def _(event: Event, matcher: Matcher, group: tuple = RegexGroup()):
    content = group[0].strip() if group and group[0] else ""

    if not content:
        await _send_text(
            matcher,
            "请输入公告内容，格式：钓鱼公告 [内容]",
            event.get_user_id(),
        )
        return

    success, fail = await broadcast_to_active_groups(content)

    total = success + fail
    if total == 0:
        reply = "没有活跃群（最近2天无人收杆），公告未发送。"
    elif fail == 0:
        reply = f"公告发送完成！成功 {success} 个群。"
    else:
        reply = (
            f"公告发送完成！\n成功: {success} 个群\n失败: {fail} 个群"
            f"\n（失败可能因路由去重/Bot不在群/限额，详见日志 [公告]/[Route]）"
        )
    await _send_text(matcher, reply, event.get_user_id())
