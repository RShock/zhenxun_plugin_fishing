import base64
import hashlib
import re
import traceback
from contextlib import contextmanager
from typing import Any

from nonebot.consts import REGEX_MATCHED
from nonebot.exception import (
    FinishedException,
    PausedException,
    RejectedException,
    SkippedException,
)
from nonebot.internal.matcher import current_bot, current_event, current_matcher
from nonebot.matcher import Matcher

from ..render.base import pop_cached_html
from .fake_objects import FakeWebBot, FakeWebEvent

# ── 资源路径重写 ──────────────────────────────────────────────────────

_RESOURCES_PATTERN = re.compile(
    r'((?:file:///[^\s"\'<>]*?/resources/)|((?:"|\')?)[A-Za-z]:[/\\][^\s"\'<>]*?[/\\]resources[/\\])',
    re.IGNORECASE,
)


def _rewrite_resource_urls(html: str) -> str:
    """将 file:// 或 Windows 绝对路径中的 resources 替换为 /api/resource/"""

    def _replace(m: re.Match) -> str:
        matched = m.group(0)
        if matched.startswith("file:///"):
            return "/api/resource/"
        prefix = m.group(2) or ""
        return f"{prefix}/api/resource/"

    return _RESOURCES_PATTERN.sub(_replace, html)


# ── 指令表 ────────────────────────────────────────────────────────────

_COMMAND_TABLE: list[tuple[re.Pattern, Matcher, str]] = []


def _import_matchers():
    """延迟导入所有 matcher 并构建指令表。"""
    from ..commands import get_command_pattern
    from ..matchers import (
        auto_lock_matcher,
        auto_sell_matcher,
        backpack_matcher,
        black_market_matcher,
        build_starry_ship_matcher,
        buy_matcher,
        cat_park_build_matcher,
        collection_matcher,
        display_slot_matcher,
        exchange_matcher,
        fishing_matcher,
        gift_fish_matcher,
        lock_fish_matcher,
        nest_matcher,
        rename_matcher,
        sell_fish_matcher,
        shop_matcher,
        starry_exhibition_matcher,
        skin_matcher,
        status_matcher,
        stop_fishing_matcher,
        unlock_fish_matcher,
        upgrade_hook_matcher,
        upgrade_rod_matcher,
        use_item_matcher,
        weather_forecast_matcher,
        white_market_exchange_matcher,
        white_market_matcher,
    )

    matcher_map = {
        "钓鱼": fishing_matcher,
        "收杆": stop_fishing_matcher,
        "背包": backpack_matcher,
        "卖鱼": sell_fish_matcher,
        "鱼店": shop_matcher,
        "升级钓竿": upgrade_rod_matcher,
        "升级鱼钩": upgrade_hook_matcher,
        "购买": buy_matcher,
        "升级展示栏": display_slot_matcher,
        "钓鱼状态": status_matcher,
        "打窝": nest_matcher,
        "图鉴": collection_matcher,
        "星空鱼展馆": starry_exhibition_matcher,
        "兑换": exchange_matcher,
        "黑商交换": black_market_matcher,
        "白商": white_market_matcher,
        "白商交换": white_market_exchange_matcher,
        "锁鱼": lock_fish_matcher,
        "解锁": unlock_fish_matcher,
        "赠送": gift_fish_matcher,
        "自动卖鱼": auto_sell_matcher,
        "自动锁鱼": auto_lock_matcher,
        "改名": rename_matcher,
        "更换皮肤": skin_matcher,
        "使用物品": use_item_matcher,
        "天气": weather_forecast_matcher,
        "建设猫猫乐园": cat_park_build_matcher,
        "建设星空艇": build_starry_ship_matcher,
    }

    _table: list[tuple[re.Pattern, Matcher, str]] = []
    for name, matcher in matcher_map.items():
        compiled = re.compile(f"^{get_command_pattern(name)}$")
        _table.append((compiled, matcher, name))

    _COMMAND_TABLE.clear()
    _COMMAND_TABLE.extend(_table)


# ── 图片数据提取 ──────────────────────────────────────────────────────


def _extract_image_data(seg_data: dict) -> bytes | None:
    """从消息段数据中提取图片字节。"""
    file_val = seg_data.get("file")
    if not file_val:
        return None
    if isinstance(file_val, bytes):
        return file_val
    if file_val.startswith("base64://"):
        try:
            return base64.b64decode(file_val[len("base64://") :])
        except Exception:
            traceback.print_exc()
            return None
    if file_val.startswith("http://") or file_val.startswith("https://"):
        return None
    return file_val.encode("utf-8")


# ── Matcher 上下文管理 ────────────────────────────────────────────────


@contextmanager
def _matcher_context(bot: FakeWebBot, event: FakeWebEvent, matcher: Matcher):
    """临时设置 nonebot 的 current_bot/current_event/current_matcher 上下文。"""
    b_t = current_bot.set(bot)
    e_t = current_event.set(event)
    m_t = current_matcher.set(matcher)
    try:
        yield
    finally:
        current_bot.reset(b_t)
        current_event.reset(e_t)
        current_matcher.reset(m_t)


# ── CommandRouter ─────────────────────────────────────────────────────


class CommandRouter:
    def __init__(self):
        if not _COMMAND_TABLE:
            _import_matchers()

    def find_matcher(
        self, command_text: str
    ) -> tuple[Matcher, re.Match | None, str] | None:
        """根据指令文本匹配 matcher。"""
        for pattern, matcher, name in _COMMAND_TABLE:
            matched = pattern.match(command_text)
            if matched:
                return matcher, matched, name
        return None

    async def route_command(
        self, user_id: str, nickname: str, command_text: str
    ) -> list[dict]:
        """路由并执行一条指令，返回格式化后的响应列表。"""
        result = self.find_matcher(command_text)
        if result is None:
            return [{"type": "text", "content": "未知指令，请输入钓鱼相关命令"}]

        matcher_cls, matched, _ = result

        event = FakeWebEvent(
            user_id=user_id,
            message_text=command_text,
            sender={"nickname": nickname},
        )
        bot = FakeWebBot()
        matcher_instance = matcher_cls()

        state: dict[str, Any] = {}
        if matched:
            state[REGEX_MATCHED] = matched
        matcher_instance.state.update(state)

        try:
            with _matcher_context(bot, event, matcher_instance):
                await self._execute_handlers(matcher_instance, bot, event)
        except FinishedException:
            pass
        except RejectedException:
            pass
        except PausedException:
            pass
        except Exception:
            traceback.print_exc()
            raise

        return self._format_responses(bot.responses)

    async def _execute_handlers(
        self, matcher: Matcher, bot: FakeWebBot, event: FakeWebEvent
    ):
        """依次执行 matcher 的所有 handler。"""
        while matcher.remain_handlers:
            handler = matcher.remain_handlers.pop(0)
            try:
                await handler(
                    matcher=matcher,
                    bot=bot,
                    event=event,
                    state=matcher.state,
                    stack=None,
                    dependency_cache=None,
                )
            except SkippedException:
                continue

    def _format_responses(self, messages: list) -> list[dict]:
        """将 FakeWebBot 收集的消息列表格式化为前端可渲染的结构。"""
        result = []
        for msg in messages:
            for seg in msg:
                if seg.type == "text":
                    text = seg.data.get("text", "")
                    if text.strip():
                        result.append({"type": "text", "content": text})
                elif seg.type == "image":
                    image_bytes = _extract_image_data(seg.data)
                    if image_bytes:
                        h = hashlib.md5(image_bytes, usedforsecurity=False).hexdigest()
                        cached_html = pop_cached_html(h)
                        if cached_html:
                            result.append({"type": "html", "content": cached_html})
                        else:
                            result.append({"type": "image", "data": image_bytes})
                elif seg.type == "at":
                    result.append({"type": "at", "user_id": seg.data.get("qq", "")})
        return result


router = CommandRouter()
