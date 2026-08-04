"""Shared lightweight stubs for plugin unit tests that do not need NoneBot.

Some plugin tests target pure business logic but still import modules inside a
NoneBot plugin package. Importing the package normally can call require(), load
scheduler plugins and initialize driver state before pytest fixtures run. These
stubs provide enough of the NoneBot surface for import-time registration while
keeping the tests independent from a running bot.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
import sys
from types import ModuleType, SimpleNamespace
from typing import ClassVar
from unittest.mock import AsyncMock, MagicMock


class DummyMatcher:
    handlers: ClassVar[list] = []

    @classmethod
    def handle(cls, *args, **kwargs):
        def decorator(func):
            cls.handlers.append(func)
            return func

        return decorator

    @classmethod
    def got(cls, *args, **kwargs):
        def decorator(func):
            cls.handlers.append(func)
            return func

        return decorator

    @classmethod
    def receive(cls, *args, **kwargs):
        def decorator(func):
            cls.handlers.append(func)
            return func

        return decorator

    @classmethod
    async def send(cls, *args, **kwargs):
        return None

    @classmethod
    async def finish(cls, *args, **kwargs):
        return None

    @classmethod
    async def pause(cls, *args, **kwargs):
        return None

    @classmethod
    async def reject(cls, *args, **kwargs):
        return None


class DummyScheduler:
    def scheduled_job(self, *args, **kwargs):
        def decorator(func):
            return func

        return decorator


@dataclass
class DummyPluginMetadata:
    name: str = ""
    description: str = ""
    usage: str = ""
    extra: object | None = None


class DummyDriver:
    def __init__(self):
        self._bot_connection_hook = []
        self.config = SimpleNamespace(superusers=set())

    def on_startup(self, func=None, *args, **kwargs):
        if func is None:
            return lambda wrapped: wrapped
        return func

    def on_shutdown(self, func=None, *args, **kwargs):
        if func is None:
            return lambda wrapped: wrapped
        return func

    def register_adapter(self, *args, **kwargs):
        return None


class DummyMessage(str):
    pass


class DummyMessageSegment:
    @staticmethod
    def image(*args, **kwargs):
        return "[image]"

    @staticmethod
    def text(value=""):
        return str(value)

    @staticmethod
    def at(value=""):
        return f"@{value}"


class DummyUniMessage(list):
    @classmethod
    def at(cls, user_id: str):
        return cls([("at", user_id)])

    @classmethod
    def image(cls, *, raw: bytes | None = None, **kwargs):
        return cls([("image", raw)])

    @classmethod
    def text(cls, text: str):
        return cls([("text", text)])

    async def send(self, *args, **kwargs):
        return None

    async def finish(self, *args, **kwargs):
        return None


class DummyEvent:
    def get_user_id(self) -> str:
        return "test_user"

    def get_session_id(self) -> str:
        return "test_session"

    def get_message(self):
        return DummyMessage("")

    def is_tome(self) -> bool:
        return False


class DummyBot:
    self_id = "test_bot"

    async def send(self, *args, **kwargs):
        return None

    async def call_api(self, *args, **kwargs):
        return None


class DummyModel:
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    @classmethod
    async def create(cls, **kwargs):
        return cls(**kwargs)

    @classmethod
    async def get_or_create(cls, **kwargs):
        return cls(**kwargs), True

    @classmethod
    def filter(cls, *args, **kwargs):
        query = MagicMock()
        query.first = AsyncMock(return_value=None)
        query.all = AsyncMock(return_value=[])
        query.count = AsyncMock(return_value=0)
        query.exists = AsyncMock(return_value=False)
        query.filter = MagicMock(return_value=query)
        query.exclude = MagicMock(return_value=query)
        query.order_by = MagicMock(return_value=query)
        return query

    @classmethod
    async def all(cls):
        return []

    async def save(self, *args, **kwargs):
        return None

    async def delete(self):
        return None


def _module(name: str, *, force: bool = False) -> ModuleType:
    """Get or create a module. force=True always installs a fresh stub module."""
    existing = sys.modules.get(name)
    if isinstance(existing, ModuleType) and not force:
        # If a real package was already imported, replace it with a clean stub.
        # Keep the same module object only when it looks like our stub (no __file__
        # under site-packages) and already has our markers.
        file_name = getattr(existing, "__file__", "") or ""
        if "site-packages" in file_name.replace("\\", "/"):
            force = True
        elif getattr(existing, "__zx_stub__", False):
            return existing
        else:
            force = True
    if force or not isinstance(existing, ModuleType):
        module = ModuleType(name)
        module.__zx_stub__ = True  # type: ignore[attr-defined]
        # Empty __path__ makes it a package and blocks loading real submodules from site-packages.
        if "." not in name or name.count(".") >= 0:
            module.__path__ = []  # type: ignore[attr-defined]
        sys.modules[name] = module
        return module
    return existing


def _install_nonebot() -> None:
    # Force-replace real nonebot packages if present (critical for CI / polluted envs).
    nonebot = _module("nonebot", force=True)
    nonebot.__path__ = []  # type: ignore[attr-defined]
    nonebot.require = lambda *args, **kwargs: MagicMock()
    nonebot.get_driver = lambda: DummyDriver()
    nonebot.get_bot = lambda *args, **kwargs: DummyBot()
    nonebot.get_bots = lambda: {}
    nonebot.get_adapter = lambda *args, **kwargs: MagicMock()
    nonebot.on_regex = lambda *args, **kwargs: DummyMatcher
    nonebot.on_command = lambda *args, **kwargs: DummyMatcher
    nonebot.load_plugin = lambda *args, **kwargs: MagicMock()
    nonebot.load_plugins = lambda *args, **kwargs: []
    nonebot.logger = MagicMock()

    plugin = _module("nonebot.plugin", force=True)
    plugin.__path__ = []  # type: ignore[attr-defined]
    plugin.PluginMetadata = DummyPluginMetadata
    plugin.require = nonebot.require
    plugin.load_plugin = nonebot.load_plugin
    plugin.load_plugins = nonebot.load_plugins

    permission = _module("nonebot.permission", force=True)
    permission.SUPERUSER = MagicMock(name="SUPERUSER")

    matcher = _module("nonebot.matcher", force=True)
    matcher.Matcher = DummyMatcher
    matcher.current_event = ContextVar("current_event")

    params = _module("nonebot.params", force=True)
    params.Arg = lambda *args, **kwargs: None
    params.RegexGroup = lambda *args, **kwargs: ()
    params.CommandArg = lambda *args, **kwargs: DummyMessage("")

    adapters = _module("nonebot.adapters", force=True)
    adapters.Event = DummyEvent
    adapters.Message = DummyMessage
    adapters.Bot = DummyBot

    onebot = _module("nonebot.adapters.onebot", force=True)
    onebot_v11 = _module("nonebot.adapters.onebot.v11", force=True)
    onebot_v11.Bot = DummyBot
    onebot_v11.Event = DummyEvent
    onebot_v11.Message = DummyMessage
    onebot_v11.MessageSegment = DummyMessageSegment
    onebot.v11 = onebot_v11

    compat = _module("nonebot.compat", force=True)
    compat.PYDANTIC_V2 = True

    internal_adapter = _module("nonebot.internal.adapter", force=True)
    internal_adapter.Bot = DummyBot
    internal_adapter.Event = DummyEvent

    internal_matcher = _module("nonebot.internal.matcher", force=True)
    internal_matcher.current_bot = MagicMock()
    internal_matcher.current_event = MagicMock()
    internal_matcher.current_matcher = MagicMock()

    consts = _module("nonebot.consts", force=True)
    consts.REGEX_MATCHED = "regex_matched"

    exception = _module("nonebot.exception", force=True)
    for name in [
        "FinishedException",
        "IgnoredException",
        "PausedException",
        "RejectedException",
        "SkippedException",
    ]:
        setattr(exception, name, type(name, (Exception,), {}))

    log = _module("nonebot.log", force=True)
    log.logger = MagicMock()


def _install_nonebot_plugins() -> None:
    apscheduler = _module("nonebot_plugin_apscheduler")
    apscheduler.scheduler = DummyScheduler()

    htmlrender = _module("nonebot_plugin_htmlrender")
    htmlrender.html_to_pic = AsyncMock(return_value=b"FAKE_IMAGE_BYTES")

    _module("nonebot_plugin_session")

    alconna = _module("nonebot_plugin_alconna")
    alconna.UniMessage = DummyUniMessage


def _install_zhenxun_shims() -> None:
    services = _module("zhenxun.services")
    services.__path__ = []

    log = _module("zhenxun.services.log")
    log.logger = MagicMock()

    db_context = _module("zhenxun.services.db_context")
    db_context.Model = DummyModel
    db_context.init = AsyncMock()
    db_context.disconnect = AsyncMock()

    configs = _module("zhenxun.configs")
    configs.__path__ = []

    utils = _module("zhenxun.configs.utils")
    utils.Command = lambda *args, **kwargs: {"command": kwargs.get("command", "")}
    utils.PluginCdBlock = lambda *args, **kwargs: {"cd": True}

    class PluginExtraData:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def to_dict(self):
            return dict(self.kwargs)

    utils.PluginExtraData = PluginExtraData

    config = _module("zhenxun.configs.config")
    config.BotConfig = SimpleNamespace(db_url="sqlite://:memory:")

    models = _module("zhenxun.models")
    models.__path__ = []

    user_console = _module("zhenxun.models.user_console")
    user_console.UserConsole = MagicMock()


def install_lightweight_nonebot_stubs() -> None:
    _install_nonebot()
    _install_nonebot_plugins()
    _install_zhenxun_shims()
