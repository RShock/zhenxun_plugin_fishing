from zhenxun.plugins.zhenxun_plugin_fishing.render.fishing_result import (
    _attach_starry_rewards,
)


def test_duplicate_starry_fish_only_show_their_own_draw_rewards():
    cards = [
        {"id": "123456", "catch_index": 0},
        {"id": "123456", "catch_index": 1},
    ]
    rewards = [
        {
            "fish_id": "123456",
            "catch_index": 0,
            "name": "多多药水",
            "count": 1,
            "granted": True,
        },
        {
            "fish_id": "123456",
            "catch_index": 1,
            "name": "幸运药水",
            "count": 1,
            "granted": True,
        },
    ]

    _attach_starry_rewards(cards, rewards)

    assert cards[0]["reward_text"] == "多多药水×1"
    assert cards[1]["reward_text"] == "幸运药水×1"
    assert len(cards[0]["rewards"]) == 1
    assert len(cards[1]["rewards"]) == 1


def test_fragment_upgrade_stays_with_the_triggering_starry_fish():
    cards = [
        {"id": "123456", "catch_index": 0},
        {"id": "123456", "catch_index": 1},
    ]
    rewards = [
        {
            "fish_id": "123456",
            "catch_index": 0,
            "name": "高级抽奖碎片",
            "count": 1,
            "granted": True,
        },
        {
            "fish_id": "123456",
            "catch_index": 0,
            "name": "闪光药水",
            "count": 1,
            "upgrade_from": "高级抽奖碎片",
            "granted": True,
        },
        {
            "fish_id": "123456",
            "catch_index": 1,
            "name": "幸运药水",
            "count": 1,
            "granted": True,
        },
    ]

    _attach_starry_rewards(cards, rewards)

    assert len(cards[0]["rewards"]) == 2
    assert "闪光药水×1(碎片升级)" in cards[0]["reward_text"]
    assert cards[1]["reward_text"] == "幸运药水×1"
