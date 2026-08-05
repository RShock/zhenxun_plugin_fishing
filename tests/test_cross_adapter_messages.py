"""Outgoing fishing messages must stay adapter-neutral."""

import ast
from pathlib import Path

from zhenxun.plugins.zhenxun_plugin_fishing.utils import (
    _build_image_message,
    _build_text_message,
    _get_at_display_name,
    _get_at_list,
    _get_nickname,
    _outgoing_recipient,
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


def test_image_message_can_show_name_when_mention_is_unavailable():
    message = _build_image_message(
        b"image-bytes",
        "result",
        is_private=False,
        display_name="FinalLone.",
    )

    assert list(message) == [
        ("text", "FinalLone.，\n"),
        ("image", b"image-bytes"),
        ("text", "\nresult"),
    ]


def test_private_text_message_does_not_prepend_at():
    message = _build_text_message(
        "done", user_id="user-open-id", is_private=True
    )

    assert list(message) == [("text", "done")]


def test_text_message_prefers_real_mention_over_name_fallback():
    message = _build_text_message(
        "done",
        user_id="user-open-id",
        is_private=False,
        display_name="FinalLone.",
    )

    assert list(message) == [("at", "user-open-id"), ("text", "done")]


def test_text_message_can_show_name_when_mention_is_unavailable():
    message = _build_text_message(
        "done", is_private=False, display_name="FinalLone."
    )

    assert list(message) == [("text", "FinalLone.，"), ("text", "done")]


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


def test_qq_mention_display_name_is_preserved():
    event = type(
        "QQEvent",
        (),
        {
            "get_message": lambda _self: [
                type(
                    "Segment",
                    (),
                    {
                        "type": "mention_user",
                        "data": {
                            "user_id": "legacy-qq-id",
                            "username": "échouer",
                        },
                    },
                )()
            ]
        },
    )()

    assert _get_at_display_name(event) == "échouer"


def test_official_group_reply_uses_name_even_when_author_id_exists():
    event = type(
        "QQEvent",
        (),
        {
            "group_openid": "group-open-id",
            "author": type(
                "Author",
                (),
                {
                    "id": "mention-open-id",
                    "member_openid": "member-open-id",
                    "username": "天天开心",
                },
            )(),
            "_route2_original_user_id": "member-open-id",
        },
    )()

    assert _outgoing_recipient("953368178", event) == ("", "天天开心")


def test_official_group_reply_never_falls_back_to_member_openid():
    event = type(
        "QQEvent",
        (),
        {
            "group_openid": "group-open-id",
            "author": type(
                "Author",
                (),
                {
                    "id": "",
                    "member_openid": "member-open-id",
                    "username": "天天开心",
                },
            )(),
            "_route2_original_user_id": "member-open-id",
        },
    )()

    assert _outgoing_recipient("953368178", event) == ("", "天天开心")
    assert list(
        _build_text_message(
            "钓鱼成功",
            user_id="",
            is_private=False,
            display_name="天天开心",
        )
    ) == [("text", "天天开心，"), ("text", "钓鱼成功")]


def test_malformed_onebot_card_falls_back_to_sender_nickname():
    event = type(
        "OneBotEvent",
        (),
        {
            "sender": type(
                "Sender",
                (),
                {
                    "card": "\x07$ÿĀ\x1c\x18\n\x08\x12\x06朽翁\x10\x00",
                    "nickname": "酒肉穿肠做朽翁",
                },
            )()
        },
    )()

    assert _get_nickname(event) == "酒肉穿肠做朽翁"


def test_nickname_is_limited_to_database_field_length():
    event = type(
        "OneBotEvent",
        (),
        {"sender": type("Sender", (), {"card": "猫" * 300, "nickname": ""})()},
    )()

    assert _get_nickname(event) == "猫" * 255
