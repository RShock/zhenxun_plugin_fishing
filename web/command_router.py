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
    """按公开指令注册表延迟装配 Web 路由，不维护第二份指令清单。"""
    from ..commands import iter_web_commands
    from .. import matchers

    _table: list[tuple[re.Pattern, Matcher, str]] = []
    for command in iter_web_commands():
        matcher = getattr(matchers, command.matcher)
        compiled = re.compile(f"^{command.pattern}$")
        _table.append((compiled, matcher, command.name))

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
