# -*- coding: utf-8 -*-
"""gm添加 多物品解析测试。"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from zhenxun.plugins.zhenxun_plugin_fishing import gm
from zhenxun.plugins.zhenxun_plugin_fishing.gm import (
    _parse_item_input,
    parse_gm_add_body,
    parse_gm_item_specs,
)

# GM 已改为 on_command 前缀匹配：首 token 精确等于命令名
GM_ADD_CMDS = {"gm添加", "gm赠送"}
GM_SKIN_CMD = "gm添加皮肤"


def _first_token(text: str) -> str:
    return (text or "").strip().split(None, 1)[0] if (text or "").strip() else ""


def _matches_gm_add(text: str) -> bool:
    return _first_token(text) in GM_ADD_CMDS


def _matches_gm_skin(text: str) -> bool:
    return _first_token(text) == GM_SKIN_CMD


class TestParseItemInputSpecials:
    """特殊道具应识别为对应 kind，而不是要求稀有度的鱼。"""

    def test_utr_select_aliases(self):
        for name in ["UTR自选券", "utr自选券", "UTR券", "utr券", "utr_select_ticket"]:
            item_id, kind = _parse_item_input(name)
            assert item_id == "utr_select_ticket"
            assert kind == "ticket"

    def test_potion_aliases_not_in_shop_or_alias(self):
        cases = {
            "闪光药水": ("闪光药水", "potion"),
            "回档药水": ("回档药水", "potion"),
            "回溯药水": ("回档药水", "potion"),
            "重置药水": ("回档药水", "potion"),
            "时光药水": ("time_potion", "potion"),
            "时间药水": ("time_potion", "potion"),
            "幸运药水": ("幸运药水", "potion"),
            "真多多药水": ("真多多药水", "potion"),
            "多多药水": ("真多多药水", "potion"),
            "许愿药水": ("许愿药水", "potion"),
        }
        for name, expected in cases.items():
            assert _parse_item_input(name) == expected, name

    def test_corn_and_tickets_and_fragments(self):
        assert _parse_item_input("香甜玉米") == ("corn", "corn")
        assert _parse_item_input("玉米") == ("corn", "corn")
        assert _parse_item_input("黑商额外兑换券") == (
            "black_market_extra_ticket",
            "ticket",
        )
        assert _parse_item_input("抽奖碎片") == ("lottery_fragment_low", "fragment")
        assert _parse_item_input("中级抽奖碎片") == (
            "lottery_fragment_low",
            "fragment",
        )
        assert _parse_item_input("高级抽奖碎片") == (
            "lottery_fragment_mid",
            "fragment",
        )
        assert _parse_item_input("究极抽奖碎片") == (
            "lottery_fragment_high",
            "fragment",
        )

    def test_frames(self):
        assert _parse_item_input("猫猫框") == ("cat_frame", "cat_frame")
        assert _parse_item_input("展示木框") == ("display_frame", "display_frame")
        assert _parse_item_input("木框") == ("display_frame", "display_frame")

    def test_fish_utr_suffix_still_works(self):
        fish_name, rarity = _parse_item_input("小鲫鱼utr")
        assert fish_name == "小鲫鱼"
        assert rarity == "UTR"


class TestParseGmItemSpecs:
    def test_multi_comma_merge_same(self):
        specs = parse_gm_item_specs(
            "真多多药水,幸运药水,时光药水,时光药水,时光药水", default_count=1
        )
        assert specs == [
            ("真多多药水", 1),
            ("幸运药水", 1),
            ("时光药水", 3),
        ]


class TestGmAddItemIntegration:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("item", "count", "category", "display", "expected_call"),
        [
            ("时光药水", 3, "potion", "时光药水", ("time_potion", "potion", 3)),
            (
                "UTR自选券",
                2,
                "ticket",
                "UTR自选券",
                ("utr_select_ticket", "ticket", 2),
            ),
            (
                "抽奖碎片",
                4,
                "fragment",
                "中级抽奖碎片",
                ("lottery_fragment_low", "fragment", 4),
            ),
        ],
    )
    async def test_inventory_categories(
        self, monkeypatch, item, count, category, display, expected_call
    ):
        add_item = AsyncMock()
        monkeypatch.setattr(gm.FishingUser, "add_item", add_item)

        ok, message = await gm.gm_add_item("10001", item, count)

        assert ok is True
        unit = {"potion": "瓶", "ticket": "张", "fragment": "个"}[category]
        assert message == f"已给用户 10001 添加 {count}{unit}{display}！"
        add_item.assert_awaited_once_with("10001", *expected_call)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("item", "count", "method", "message"),
        [
            ("猫猫框", 5, "add_cat_frames", "已给用户 10001 添加 5 个猫猫框！"),
            ("展示木框", 4, "add_display_frames", "已给用户 10001 添加 4 个展示木框！"),
            ("玉米", 6, "add_corn", "已给用户 10001 添加 6 个香甜玉米！"),
        ],
    )
    async def test_counter_categories(self, monkeypatch, item, count, method, message):
        operation = AsyncMock()
        monkeypatch.setattr(gm.FishingUser, method, operation)

        assert await gm.gm_add_item("10001", item, count) == (True, message)
        operation.assert_awaited_once_with("10001", count)

    @pytest.mark.asyncio
    async def test_bait_uses_resolved_id(self, monkeypatch):
        bait = SimpleNamespace(id=7, name="测试鱼饵")
        monkeypatch.setattr(gm.ConfigManager, "get_bait", lambda _: bait)
        add_item = AsyncMock()
        monkeypatch.setattr(gm.FishingUser, "add_item", add_item)

        result = await gm.gm_add_item("10001", "测试鱼饵", 8)

        assert result == (True, "已给用户 10001 添加 8 个测试鱼饵！")
        add_item.assert_awaited_once_with("10001", "7", "bait", 8)

    @pytest.mark.asyncio
    async def test_regular_fish_batch_count_and_messages(self, monkeypatch):
        fish = SimpleNamespace(name="小鲫鱼")
        location = SimpleNamespace(id="1", fish_pool=["小鲫鱼"])
        monkeypatch.setattr(gm.ConfigManager, "get_fish", lambda _: fish)
        monkeypatch.setattr(gm.ConfigManager, "get_locations", lambda: [location])
        add_fish = AsyncMock(
            return_value={
                "messages": ["收藏提示"],
                "achievement_messages": ["成就提示"],
            }
        )
        monkeypatch.setattr(gm, "add_fish_to_user", add_fish)

        ok, message = await gm.gm_add_item("10001", "小鲫鱼sr", 10)

        assert ok is True
        assert message == "已给用户 10001 添加 10 条 小鲫鱼(SR)！\n收藏提示\n成就提示"
        fish_entries = add_fish.await_args.args[1]
        assert fish_entries == [("小鲫鱼", "SR", fish_entries[0][2], 10)]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("item", "expected_method", "expected_args"),
        [
            ("流星鱼123", "add_starry_fish", ("10001", "123", "GM")),
            ("流星鱼1234567", "add_item", ("10001", "1234567", "meteor_fish", 1)),
        ],
    )
    async def test_meteor_fish_batch(
        self, monkeypatch, item, expected_method, expected_args
    ):
        operation = AsyncMock()
        monkeypatch.setattr(gm.FishingUser, expected_method, operation)

        result = await gm.gm_add_item("10001", item, 3)

        assert result[0] is True
        assert operation.await_count == 3
        operation.assert_awaited_with(*expected_args)

    @pytest.mark.asyncio
    async def test_unknown_item_and_invalid_count_do_not_mutate(self, monkeypatch):
        add_item = AsyncMock()
        monkeypatch.setattr(gm.FishingUser, "add_item", add_item)

        unknown = await gm.gm_add_item("10001", "不存在的东西", 1)
        invalid = await gm.gm_add_item("10001", "时光药水", "3")

        assert unknown[0] is False
        assert unknown[1].startswith("未识别的物品或未指定稀有度！")
        assert invalid == (False, "请输入有效的数量！")
        add_item.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_multi_item_batch_keeps_summary_and_counts(self, monkeypatch):
        add_item = AsyncMock()
        monkeypatch.setattr(gm.FishingUser, "add_item", add_item)

        result = await gm.gm_add_items(
            "10001", [("时光药水", 3), ("UTR自选券", 2)]
        )

        assert result == (
            True,
            "已给用户 10001 添加：时光药水×3、UTR自选券×2",
        )
        assert add_item.await_args_list[0].args == (
            "10001", "time_potion", "potion", 3
        )
        assert add_item.await_args_list[1].args == (
            "10001", "utr_select_ticket", "ticket", 2
        )

    def test_suffix_x(self):
        specs = parse_gm_item_specs("时光药水x3,真多多药水", default_count=1)
        assert specs == [("时光药水", 3), ("真多多药水", 1)]

    def test_suffix_star_and_global(self):
        # 有 xN 的不套用全局数量；无后缀的用全局
        specs = parse_gm_item_specs("时光药水*2,幸运药水", default_count=5)
        assert specs == [("时光药水", 2), ("幸运药水", 5)]

    def test_chinese_comma(self):
        specs = parse_gm_item_specs("猫猫框，展示木框", default_count=2)
        assert specs == [("猫猫框", 2), ("展示木框", 2)]

    def test_single(self):
        assert parse_gm_item_specs("时光药水", 1) == [("时光药水", 1)]


class TestParseGmAddBody:
    def test_user_compensation_command(self):
        """用户目标写法：多药水 + 全局1 + QQ。"""
        specs, target = parse_gm_add_body(
            "真多多药水,幸运药水,时光药水,时光药水,时光药水 1 3086773658"
        )
        assert specs == [
            ("真多多药水", 1),
            ("幸运药水", 1),
            ("时光药水", 3),
        ]
        assert "3086773658" in target

    def test_single_item_count_qq(self):
        specs, target = parse_gm_add_body("时光药水 2 1922570420")
        assert specs == [("时光药水", 2)]
        assert "1922570420" in target

    def test_item_only_qq_default_count(self):
        specs, target = parse_gm_add_body("时光药水 1922570420")
        assert specs == [("时光药水", 1)]
        assert "1922570420" in target

    def test_all_server(self):
        specs, target = parse_gm_add_body("小鲫鱼sr 10 全服")
        assert specs == [("小鲫鱼sr", 10)]
        assert "全服" in target

    def test_multi_no_global_count(self):
        specs, target = parse_gm_add_body(
            "真多多药水,幸运药水,时光药水,时光药水,时光药水"
        )
        assert specs == [
            ("真多多药水", 1),
            ("幸运药水", 1),
            ("时光药水", 3),
        ]
        assert target == ""

    def test_batch_qq(self):
        specs, target = parse_gm_add_body("猫猫框 5 1922570420,3404193303")
        assert specs == [("猫猫框", 5)]
        assert "1922570420" in target
        assert "3404193303" in target


class TestGmAddCommandPrefix:
    """on_command 前缀匹配：按首 token 精确匹配命令名。"""

    def test_multi_item_matches(self):
        text = "gm添加 真多多药水,幸运药水,时光药水,时光药水,时光药水 1"
        assert _matches_gm_add(text)

    def test_skin_not_match_item(self):
        text = "gm添加皮肤 1"
        assert not _matches_gm_add(text)
        assert _matches_gm_skin(text)

    def test_gift_alias(self):
        assert _matches_gm_add("gm赠送 时光药水 1 3086773658")

    def test_user_live_command_form(self):
        """线上失败过的写法：多物品 + 全局数量 + @（@ 不在纯文本里时 body 仍可解析）。"""
        text = "gm添加 真多多药水,幸运药水,时光药水,时光药水,时光药水 1"
        assert _matches_gm_add(text)
        body = text.split(None, 1)[1]
        specs, target = parse_gm_add_body(body)
        assert specs == [
            ("真多多药水", 1),
            ("幸运药水", 1),
            ("时光药水", 3),
        ]
