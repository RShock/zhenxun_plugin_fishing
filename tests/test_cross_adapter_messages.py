"""Outgoing fishing messages must stay adapter-neutral."""

import ast
from pathlib import Path

from zhenxun.plugins.zhenxun_plugin_fishing.utils import (
    _build_image_message,
    _build_text_message,
    _get_at_list,
    _transport_user_id,
)


def test_image_message_uses_universal_segments():
    message = _build_image_message(
        b"image-bytes", "result", user_id="user-open-id", is_private=False
    )

    assert list(message) == [
        ("at", "user-open-id"),
        ("image", b"image-bytes"),
        ("text", "\nresult"),
    ]


def test_private_text_message_does_not_prepend_at():
    message = _build_text_message(
        "done", user_id="user-open-id", is_private=True
    )

    assert list(message) == [("text", "done")]


def test_route_binding_keeps_official_openid_for_mentions():
    event = type(
        "BoundOfficialEvent",
        (),
        {"_route2_original_user_id": "official-open-id"},
    )()

    assert _transport_user_id("legacy-qq-id", event) == "official-open-id"


def test_qq_mention_user_segment_is_recognized():
    event = type(
        "QQEvent",
        (),
        {
            "get_message": lambda _self: [
                type(
                    "Segment",
                    (),
                    {"type": "mention_user", "data": {"user_id": "open-id"}},
                )()
            ]
        },
    )()

    assert _get_at_list(event) == ["open-id"]


def test_runtime_senders_do_not_construct_onebot_messages():
    plugin_root = Path(__file__).parents[1]
    for relative_path in ("utils.py", "handlers/player.py"):
        tree = ast.parse((plugin_root / relative_path).read_text(encoding="utf-8"))
        imported_modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert "nonebot.adapters.onebot.v11" not in imported_modules
