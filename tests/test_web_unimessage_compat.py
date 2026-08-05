"""Regression coverage for the web command bridge after UniMessage migration."""

from types import SimpleNamespace

import pytest

from zhenxun.plugins.zhenxun_plugin_fishing import utils
from zhenxun.plugins.zhenxun_plugin_fishing.web.command_router import CommandRouter
from zhenxun.plugins.zhenxun_plugin_fishing.web.fake_objects import FakeWebBot


@pytest.mark.asyncio
async def test_web_bot_collects_unimessage_without_adapter(monkeypatch):
    bot = object.__new__(FakeWebBot)
    bot._responses = []
    monkeypatch.setattr(utils.current_bot, "get", lambda: bot)
    message = utils._build_text_message("web reply")

    await utils._deliver_universal_message(message)

    assert bot.responses == [message]


@pytest.mark.asyncio
async def test_web_collector_preserves_finish_semantics(monkeypatch):
    bot = object.__new__(FakeWebBot)
    bot._responses = []
    monkeypatch.setattr(utils.current_bot, "get", lambda: bot)
    message = utils._build_text_message("done")

    with pytest.raises(utils.FinishedException):
        await utils._deliver_universal_message(message, finish=True)

    assert bot.responses == [message]


def test_web_formatter_accepts_unimessage_segment_data():
    messages = [
        [
            SimpleNamespace(type="at", data={"target": "official-open-id"}),
            SimpleNamespace(type="text", data={"text": "ok"}),
            SimpleNamespace(type="image", data={"raw": b"image-bytes"}),
        ]
    ]

    result = CommandRouter.__new__(CommandRouter)._format_responses(messages)

    assert result == [
        {"type": "at", "user_id": "official-open-id"},
        {"type": "text", "content": "ok"},
        {"type": "image", "data": b"image-bytes"},
    ]
