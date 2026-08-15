import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from zhenxun.plugins.zhenxun_plugin_fishing.starry import (
    STARRY_SHIP_ITEM_ID,
    STARRY_SHIP_ITEM_TYPE,
)
from zhenxun.plugins.zhenxun_plugin_fishing.shop import (
    upgrade_rod,
    upgrade_hook,
    buy_item,
    upgrade_display_slots,
    do_cat_frame_nest,
    do_nest,
    check_sign,
    exchange_to_gold,
)
from zhenxun.plugins.zhenxun_plugin_fishing.items import use_display_frame_buff
from zhenxun.plugins.zhenxun_plugin_fishing.fishing import start_fishing, stop_fishing
from zhenxun.plugins.zhenxun_plugin_fishing.models import BuffEffect, FishingBuff
from zhenxun.plugins.zhenxun_plugin_fishing.render.shop import render_shop


USER_ID = "test_user_001"


class TestShopRenderStarryFrame:
    """鱼店渲染：星空展示框升级仅在已建星空艇后展示。"""

    async def _capture_frame_rows(self, **kwargs):
        captured = {}

        def fake_render_template(name, **ctx):
            captured["frame_upgrade"] = ctx.get("frame_upgrade")
            return "<html></html>"

        with (
            patch(
                "zhenxun.plugins.zhenxun_plugin_fishing.render.shop.render_template",
                side_effect=fake_render_template,
            ),
            patch(
                "zhenxun.plugins.zhenxun_plugin_fishing.render.shop.render_html",
                new_callable=AsyncMock,
                return_value=b"img",
            ),
            patch(
                "zhenxun.plugins.zhenxun_plugin_fishing.starry.has_starry_ship",
                new_callable=AsyncMock,
                return_value=kwargs.get("has_starry_ship", False),
            ),
        ):
            await render_shop(
                baits=[],
                potions=[],
                rod_level=kwargs.get("rod_level", 10),
                rod_upgrade_price=1000,
                hook_level=0,
                hook_upgrade_price=100,
                display_slots=3,
                display_frames=0,
                cat_frames=0,
                upgraded_display_count=0,
                gold=0,
                user_id=USER_ID,
                starry_frames=0,
                has_starry_ship=kwargs.get("has_starry_ship", False),
                star_frames=5,
            )
        rows = (captured.get("frame_upgrade") or {}).get("rows") or []
        return rows

    async def test_starry_frame_hidden_before_ship(self):
        rows = await self._capture_frame_rows(has_starry_ship=False, rod_level=10)
        assert not any(r.get("key") == "starry" for r in rows)

    async def test_starry_frame_visible_after_ship(self):
        rows = await self._capture_frame_rows(has_starry_ship=True, rod_level=10)
        assert any(r.get("key") == "starry" for r in rows)

    async def test_starry_frame_hidden_before_ship_low_rod(self):
        # 低竿等级同样不应展示星空展示框
        rows = await self._capture_frame_rows(has_starry_ship=False, rod_level=5)
        assert not any(r.get("key") == "starry" for r in rows)

    async def test_rod_section_shows_ship_when_bonus_tops_above_10(self, monkeypatch):
        """总等级 11（基础 10）未建艇时，鱼店入口仍是建设星空艇。"""
        from zhenxun.plugins.zhenxun_plugin_fishing.render import shop as shop_render
        from zhenxun.plugins.zhenxun_plugin_fishing.starry import STARRY_SHIP_COST

        captured = {}

        def _capture_template(name, **kwargs):
            captured.update(kwargs)
            return "<html>fake</html>"

        monkeypatch.setattr(shop_render, "render_template", _capture_template)
        await shop_render.render_shop(
            [],
            [],
            rod_level=11,
            rod_upgrade_price=100,
            hook_level=1,
            hook_upgrade_price=50,
            user_id=USER_ID,
            has_starry_ship=False,
            base_rod_level=10,
        )
        rod = captured.get("rod_section") or {}
        assert rod.get("cmd") == "建设星空艇"
        assert rod.get("price") == STARRY_SHIP_COST

    async def test_rod_section_uses_base_level_for_max_check(self, monkeypatch):
        """有效等级 20、基础等级 19 时，鱼店仍应显示升级入口。"""
        from zhenxun.plugins.zhenxun_plugin_fishing.render import shop as shop_render

        captured = {}

        def _capture_template(name, **kwargs):
            captured.update(kwargs)
            return "<html>fake</html>"

        monkeypatch.setattr(shop_render, "render_template", _capture_template)
        await shop_render.render_shop(
            [],
            [],
            rod_level=20,
            rod_upgrade_price=8300000,
            hook_level=1,
            hook_upgrade_price=50,
            user_id=USER_ID,
            has_starry_ship=True,
            base_rod_level=19,
        )

        rod = captured.get("rod_section") or {}
        assert rod.get("is_max") is False
        assert rod.get("cmd") == "升级钓竿"
        assert rod.get("price") == 8300000


class TestUpgradeRod:
    async def test_upgrade_rod_success(self, db):
        user = await db.user_get(USER_ID)
        user.gold = 10000
        ok, msg = await upgrade_rod(USER_ID)
        assert ok is True
        user_after = await db.user_get(USER_ID)
        assert user_after.rod_level == 1

    async def test_upgrade_rod_no_gold(self, db):
        user = await db.user_get(USER_ID)
        user.gold = 0
        ok, msg = await upgrade_rod(USER_ID)
        assert ok is False
        assert "不足" in msg

    async def test_upgrade_rod_max_level(self, db):
        user = await db.user_get(USER_ID)
        user.rod_level = 20
        user.gold = 999999999
        ok, msg = await upgrade_rod(USER_ID)
        assert ok is False
        assert "最高" in msg

    async def test_upgrade_rod_base_19_with_bonus_can_reach_effective_21(self, db):
        """雕像加成不得让总等级 20 提前触发满级；基础 19 仍可升到 20。"""
        from zhenxun.plugins.zhenxun_plugin_fishing.config import ConfigManager

        user = await db.user_get(USER_ID)
        user.rod_level = 20
        user.bonus_rod_level = 1
        await db.items_add(USER_ID, STARRY_SHIP_ITEM_ID, STARRY_SHIP_ITEM_TYPE, 1)
        expected_price = ConfigManager.get_rod_upgrade_price(19)
        user.gold = expected_price

        ok, msg = await upgrade_rod(USER_ID)

        assert ok is True, msg
        user_after = await db.user_get(USER_ID)
        assert user_after.base_rod_level == 20
        assert user_after.rod_level == 21
        assert user_after.gold == 0

    async def test_upgrade_rod_base_20_with_bonus_is_max(self, db):
        user = await db.user_get(USER_ID)
        user.rod_level = 21
        user.bonus_rod_level = 1
        user.gold = 999999999

        ok, msg = await upgrade_rod(USER_ID)

        assert ok is False
        assert "最高" in msg
        assert user.gold == 999999999

    async def test_upgrade_rod_level_10_requires_starry_ship(self, db):
        user = await db.user_get(USER_ID)
        user.rod_level = 10
        user.gold = 999999999
        ok, msg = await upgrade_rod(USER_ID)
        assert ok is False
        assert "星空艇" in msg
        user_after = await db.user_get(USER_ID)
        assert user_after.rod_level == 10

    async def test_upgrade_rod_level_10_with_starry_ship(self, db):
        user = await db.user_get(USER_ID)
        user.rod_level = 10
        user.gold = 999999999
        await db.items_add(USER_ID, STARRY_SHIP_ITEM_ID, STARRY_SHIP_ITEM_TYPE, 1)
        ok, msg = await upgrade_rod(USER_ID)
        assert ok is True
        user_after = await db.user_get(USER_ID)
        assert user_after.rod_level == 11

    async def test_upgrade_rod_bonus_cannot_bypass_ship_gate(self, db):
        """雕像把总等级顶到 11 后，基础仍 10，未建艇不能继续商店升竿。"""
        user = await db.user_get(USER_ID)
        user.rod_level = 11
        user.bonus_rod_level = 1
        user.gold = 999999999
        ok, msg = await upgrade_rod(USER_ID)
        assert ok is False
        assert "星空艇" in msg
        user_after = await db.user_get(USER_ID)
        assert user_after.rod_level == 11
        assert user_after.gold == 999999999

    async def test_upgrade_rod_base_over_10_without_ship_blocked(self, db):
        """已越界（基础 > 10）未建艇时，继续升级仍被拦住。"""
        user = await db.user_get(USER_ID)
        user.rod_level = 12
        user.bonus_rod_level = 1
        user.gold = 999999999
        ok, msg = await upgrade_rod(USER_ID)
        assert ok is False
        assert "星空艇" in msg
        user_after = await db.user_get(USER_ID)
        assert user_after.rod_level == 12

    async def test_upgrade_rod_price_ignores_bonus_level(self, db):
        """雕像加成不抬价：总等级 5（基础 4）按 4→5 的价格扣费，而不是 5→6。"""
        from zhenxun.plugins.zhenxun_plugin_fishing.config import ConfigManager

        user = await db.user_get(USER_ID)
        user.rod_level = 5
        user.bonus_rod_level = 1  # base = 4
        expected_price = ConfigManager.get_rod_upgrade_price(4)
        inflated_price = ConfigManager.get_rod_upgrade_price(5)
        assert expected_price > 0
        assert inflated_price != expected_price
        user.gold = expected_price + 1000
        gold_before = user.gold
        ok, msg = await upgrade_rod(USER_ID)
        assert ok is True, msg
        user_after = await db.user_get(USER_ID)
        assert user_after.rod_level == 6
        assert user_after.bonus_rod_level == 1
        assert user_after.base_rod_level == 5
        assert user_after.gold == gold_before - expected_price
        assert user_after.gold != gold_before - inflated_price

    async def test_upgrade_rod_with_bonus_and_ship_uses_base_price(self, db):
        """已建艇 + 雕像：基础 10 升到 11，扣的是 10→11 价，不是总等级 11→12 价。"""
        from zhenxun.plugins.zhenxun_plugin_fishing.config import ConfigManager

        user = await db.user_get(USER_ID)
        user.rod_level = 11
        user.bonus_rod_level = 1  # base = 10
        await db.items_add(USER_ID, STARRY_SHIP_ITEM_ID, STARRY_SHIP_ITEM_TYPE, 1)
        expected_price = ConfigManager.get_rod_upgrade_price(10)
        wrong_price = ConfigManager.get_rod_upgrade_price(11)
        user.gold = expected_price + 5000
        gold_before = user.gold
        ok, msg = await upgrade_rod(USER_ID)
        assert ok is True, msg
        user_after = await db.user_get(USER_ID)
        assert user_after.rod_level == 12
        assert user_after.base_rod_level == 11
        assert user_after.gold == gold_before - expected_price
        assert user_after.gold != gold_before - wrong_price


class TestUpgradeHook:
    async def test_upgrade_hook_success(self, db):
        user = await db.user_get(USER_ID)
        user.gold = 10000
        ok, msg = await upgrade_hook(USER_ID)
        assert ok is True
        user_after = await db.user_get(USER_ID)
        assert user_after.hook_level == 1

    async def test_upgrade_hook_no_gold(self, db):
        user = await db.user_get(USER_ID)
        user.gold = 0
        ok, msg = await upgrade_hook(USER_ID)
        assert ok is False


class TestBuyItem:
    async def test_buy_bait(self, db):
        user = await db.user_get(USER_ID)
        user.gold = 10000
        ok, msg = await buy_item(USER_ID, "1", 5)
        assert ok is True
        item = await db.items_get_item(USER_ID, "1", "bait")
        assert item is not None
        assert item["count"] == 5

    async def test_buy_bait_no_gold(self, db):
        user = await db.user_get(USER_ID)
        user.gold = 0
        ok, msg = await buy_item(USER_ID, "1")
        assert ok is False

    async def test_buy_nonexistent_item(self, db):
        user = await db.user_get(USER_ID)
        user.gold = 10000
        ok, msg = await buy_item(USER_ID, "不存在的物品")
        assert ok is False

    async def test_buy_display_slot(self, db):
        user = await db.user_get(USER_ID)
        user.display_frames = 10
        ok, msg = await upgrade_display_slots(USER_ID)
        assert ok is True
        user_after = await db.user_get(USER_ID)
        assert user_after.display_slots == 4

    async def test_buy_display_slot_max(self, db):
        user = await db.user_get(USER_ID)
        user.display_slots = 10
        ok, msg = await upgrade_display_slots(USER_ID)
        assert "最大" in msg or "✅" not in msg.split("\n")[0] if "\n" in msg else "❌" in msg

    async def test_buy_display_slot_no_frames(self, db):
        user = await db.user_get(USER_ID)
        user.display_frames = 0
        ok, msg = await upgrade_display_slots(USER_ID)
        assert "不足" in msg


class TestDoNest:
    async def test_do_nest_not_fishing(self, db):
        ok, msg = await do_nest(USER_ID)
        assert ok is False
        assert "还没有" in msg

    async def test_do_nest_success(self, db):
        user = await db.user_get(USER_ID)
        user.corn = 5
        await start_fishing(USER_ID, "1")
        ok, msg = await do_nest(USER_ID)
        assert ok is True
        assert "打窝成功" in msg

    async def test_do_nest_no_corn(self, db):
        user = await db.user_get(USER_ID)
        user.corn = 0
        user.gold = 0
        await start_fishing(USER_ID, "1")
        ok, msg = await do_nest(USER_ID)
        assert isinstance(ok, bool)

    async def test_do_nest_daily_limit(self, db):
        user = await db.user_get(USER_ID)
        user.corn = 10
        await start_fishing(USER_ID, "1")
        ok1, _ = await do_nest(USER_ID)
        assert ok1 is True
        ok2, _ = await do_nest(USER_ID)
        assert ok2 is True
        ok3, msg = await do_nest(USER_ID)
        assert ok3 is False


class TestCheckSign:
    async def test_first_sign(self, db):
        is_new, corn, days_missed = await check_sign(USER_ID)
        assert is_new is True
        assert corn >= 1
        assert days_missed == 0

    async def test_double_sign(self, db):
        await check_sign(USER_ID)
        is_new, corn, days_missed = await check_sign(USER_ID)
        assert is_new is False
        assert days_missed == 0


class TestExchangeToGold:
    async def test_exchange_success(self, db):
        user = await db.user_get(USER_ID)
        user.gold = 1000
        ok, msg, gold = await exchange_to_gold(USER_ID, 500)
        assert ok is True
        user_after = await db.user_get(USER_ID)
        assert user_after.gold == 500

    async def test_exchange_no_gold(self, db):
        user = await db.user_get(USER_ID)
        user.gold = 0
        ok, msg, gold = await exchange_to_gold(USER_ID, 100)
        assert ok is False


class TestUniversalDisplayUpgrade:
    """万能升级：木框 / 猫框 / 星空框未满 10 一并校验。"""

    async def test_upgrade_starry_frame_consumes_star_frames(self, db):
        user = await db.user_get(USER_ID)
        user.display_slots = 10
        user.display_frames = 0
        user.cat_frames = 0
        user.star_frames = 5
        user.starry_frames = 0
        user.upgraded_display_count = 10
        await db.items_add(USER_ID, STARRY_SHIP_ITEM_ID, STARRY_SHIP_ITEM_TYPE, 1)

        ok, msg = await upgrade_display_slots(USER_ID)
        assert ok is True
        assert "星空展示框" in msg
        assert "星空框" in msg
        user_after = await db.user_get(USER_ID)
        assert user_after.starry_frames == 1
        assert user_after.star_frames == 4
        assert user_after.cat_frames == 0
        assert user_after.display_slots == 10

    async def test_starry_does_not_consume_cat_frames(self, db):
        """旧 bug：星空展示框误扣猫框；现应只扣星空框。"""
        user = await db.user_get(USER_ID)
        user.display_slots = 10
        user.cat_frames = 99
        user.star_frames = 1
        user.starry_frames = 0
        user.upgraded_display_count = 10
        await db.items_add(USER_ID, STARRY_SHIP_ITEM_ID, STARRY_SHIP_ITEM_TYPE, 1)

        ok, msg = await upgrade_display_slots(USER_ID)
        assert ok is True
        user_after = await db.user_get(USER_ID)
        assert user_after.starry_frames == 1
        assert user_after.star_frames == 0
        assert user_after.cat_frames == 99

    async def test_cat_frames_alone_cannot_upgrade_starry(self, db):
        user = await db.user_get(USER_ID)
        user.display_slots = 10
        user.cat_frames = 99
        user.star_frames = 0
        user.starry_frames = 0
        user.upgraded_display_count = 10
        await db.items_add(USER_ID, STARRY_SHIP_ITEM_ID, STARRY_SHIP_ITEM_TYPE, 1)

        ok, msg = await upgrade_display_slots(USER_ID)
        assert ok is True
        assert "星空框不足" in msg
        user_after = await db.user_get(USER_ID)
        assert user_after.starry_frames == 0
        assert user_after.cat_frames == 99

    async def test_pre_ship_still_expands_slots_not_starry(self, db):
        user = await db.user_get(USER_ID)
        user.display_slots = 3
        user.display_frames = 5
        user.cat_frames = 0
        user.star_frames = 10
        user.starry_frames = 0
        ok, msg = await upgrade_display_slots(USER_ID)
        assert ok is True
        assert "增加展示框" in msg
        assert "升级星空展示框" not in msg
        user_after = await db.user_get(USER_ID)
        assert user_after.display_slots == 4
        assert user_after.starry_frames == 0
        assert user_after.star_frames == 10

    async def test_buy_item_aliases_all_route_to_upgrade(self, db):
        aliases = [
            "升级展示栏",
            "增加展示栏位",
            "增加展示框",
            "强化展示栏位",
            "猫猫展示框",
            "升级星空木框",
            "升级星空展示框",
            "星空木框",
            "星空展示框",
            "展示栏位",
            "展示框",
            "展示栏",
        ]
        for alias in aliases:
            user = await db.user_get(USER_ID)
            user.display_slots = 10
            user.cat_frames = 0
            user.star_frames = 2
            user.starry_frames = 0
            user.upgraded_display_count = 10
            await db.items_add(USER_ID, STARRY_SHIP_ITEM_ID, STARRY_SHIP_ITEM_TYPE, 1)

            ok, msg = await buy_item(USER_ID, alias)
            assert ok is True, alias
            user_after = await db.user_get(USER_ID)
            assert user_after.starry_frames == 1, alias
            assert user_after.star_frames == 1, alias
            # 重置，避免 alias 循环互相污染
            user_after.starry_frames = 0
            user_after.star_frames = 2

    async def test_upgrade_reports_all_shortages(self, db):
        user = await db.user_get(USER_ID)
        user.display_slots = 3
        user.display_frames = 0
        user.cat_frames = 0
        user.star_frames = 0
        user.starry_frames = 0
        user.upgraded_display_count = 0
        await db.items_add(USER_ID, STARRY_SHIP_ITEM_ID, STARRY_SHIP_ITEM_TYPE, 1)

        ok, msg = await upgrade_display_slots(USER_ID)
        assert ok is True
        assert "木框不足" in msg
        assert "猫框不足" in msg
        assert "星空框不足" in msg
        assert "还差" in msg
        user_after = await db.user_get(USER_ID)
        assert user_after.display_slots == 3
        assert user_after.upgraded_display_count == 0
        assert user_after.starry_frames == 0

    async def test_partial_success_hides_shortage_lines(self, db):
        """有任一成功时只回报成功项，不夹带失败不足信息。"""
        user = await db.user_get(USER_ID)
        user.display_slots = 3
        user.display_frames = 5  # 够扩栏
        user.cat_frames = 0  # 不够强化
        user.star_frames = 0  # 不够星空
        user.starry_frames = 0
        user.upgraded_display_count = 0
        await db.items_add(USER_ID, STARRY_SHIP_ITEM_ID, STARRY_SHIP_ITEM_TYPE, 1)

        ok, msg = await upgrade_display_slots(USER_ID)
        assert ok is True
        assert "✅" in msg
        assert "增加展示框" in msg
        assert "不足" not in msg
        user_after = await db.user_get(USER_ID)
        assert user_after.display_slots == 4
        assert user_after.upgraded_display_count == 0
        assert user_after.starry_frames == 0

    async def test_upgrade_all_affordable_types(self, db):
        user = await db.user_get(USER_ID)
        user.display_slots = 3
        user.display_frames = 5
        user.cat_frames = 5
        user.star_frames = 5
        user.starry_frames = 0
        user.upgraded_display_count = 0
        await db.items_add(USER_ID, STARRY_SHIP_ITEM_ID, STARRY_SHIP_ITEM_TYPE, 1)

        ok, msg = await upgrade_display_slots(USER_ID)
        assert ok is True
        assert "增加展示框" in msg
        assert "猫猫展示框" in msg
        assert "升级星空展示框" in msg
        user_after = await db.user_get(USER_ID)
        assert user_after.display_slots == 4
        assert user_after.upgraded_display_count == 1
        assert user_after.starry_frames == 1
        assert user_after.star_frames == 4
        assert user_after.cat_frames == 4  # 强化第1个耗1

    async def test_cat_upgrade_only(self, db):
        user = await db.user_get(USER_ID)
        user.display_slots = 5
        user.display_frames = 0
        user.cat_frames = 3
        user.star_frames = 0
        user.starry_frames = 0
        user.upgraded_display_count = 2  # 下一级需要 3 个猫框

        ok, msg = await upgrade_display_slots(USER_ID)
        assert ok is True
        assert "猫猫展示框" in msg
        user_after = await db.user_get(USER_ID)
        assert user_after.upgraded_display_count == 3
        assert user_after.cat_frames == 0
        assert user_after.display_slots == 5

    async def test_starry_cost_progression(self, db):
        """第 n 次升级消耗 n 个星空框。"""
        user = await db.user_get(USER_ID)
        user.display_slots = 10
        user.upgraded_display_count = 10
        user.cat_frames = 0
        user.starry_frames = 2  # 下一级=3，需 3 个
        user.star_frames = 3
        await db.items_add(USER_ID, STARRY_SHIP_ITEM_ID, STARRY_SHIP_ITEM_TYPE, 1)

        ok, msg = await upgrade_display_slots(USER_ID)
        assert ok is True
        user_after = await db.user_get(USER_ID)
        assert user_after.starry_frames == 3
        assert user_after.star_frames == 0

    async def test_starry_max_and_all_max(self, db):
        user = await db.user_get(USER_ID)
        user.display_slots = 10
        user.upgraded_display_count = 10
        user.starry_frames = 10
        user.star_frames = 99
        await db.items_add(USER_ID, STARRY_SHIP_ITEM_ID, STARRY_SHIP_ITEM_TYPE, 1)

        ok, msg = await upgrade_display_slots(USER_ID)
        assert ok is True
        assert "已达上限" in msg
        user_after = await db.user_get(USER_ID)
        assert user_after.starry_frames == 10
        assert user_after.star_frames == 99

    async def test_expand_then_can_upgrade_cat_same_command(self, db):
        """扩栏后同一指令可立刻强化新栏位。"""
        user = await db.user_get(USER_ID)
        user.display_slots = 3
        user.display_frames = 1  # 第4栏需要1个木框
        user.cat_frames = 1  # 强化第1个需要1个猫框
        user.upgraded_display_count = 0
        user.star_frames = 0

        ok, msg = await upgrade_display_slots(USER_ID)
        assert ok is True
        assert "增加展示框" in msg
        assert "猫猫展示框" in msg
        user_after = await db.user_get(USER_ID)
        assert user_after.display_slots == 4
        assert user_after.upgraded_display_count == 1


class TestRenderShopStarFrames:
    async def test_render_shop_accepts_star_frames_kwarg(self, db):
        """回归：view 传入 star_frames 时不应 TypeError。"""
        from zhenxun.plugins.zhenxun_plugin_fishing.render.shop import render_shop

        image = await render_shop(
            [],
            [],
            rod_level=5,
            rod_upgrade_price=100,
            hook_level=1,
            hook_upgrade_price=50,
            display_slots=5,
            display_frames=2,
            cat_frames=3,
            upgraded_display_count=1,
            gold=1000,
            user_id=USER_ID,
            starry_frames=0,
            has_starry_ship=True,
            star_frames=7,
        )
        assert image == b"FAKE_IMAGE_BYTES"

    async def test_frame_upgrade_rows_structure(self, db, monkeypatch):
        """单卡片 frame_upgrade 应包含木框/猫框/星空框三行。"""
        from zhenxun.plugins.zhenxun_plugin_fishing.render import shop as shop_render

        captured = {}

        def _capture_template(name, **kwargs):
            captured.update(kwargs)
            return "<html>fake</html>"

        monkeypatch.setattr(shop_render, "render_template", _capture_template)

        await shop_render.render_shop(
            [],
            [],
            rod_level=5,
            rod_upgrade_price=100,
            hook_level=1,
            hook_upgrade_price=50,
            display_slots=5,
            display_frames=2,
            cat_frames=3,
            upgraded_display_count=1,
            gold=1000,
            user_id=USER_ID,
            starry_frames=1,
            has_starry_ship=True,
            star_frames=7,
        )
        fu = captured.get("frame_upgrade")
        assert fu is not None
        assert fu["cmd"] == "升级展示栏"
        keys = [r["key"] for r in fu["rows"]]
        assert keys == ["wood", "cat", "starry"]
        assert any("木框" in r["material"] or r["is_max"] for r in fu["rows"])
        starry = next(r for r in fu["rows"] if r["key"] == "starry")
        assert "星空框" in starry["material"]
        assert starry["owned_text"] == "拥有 7"

    async def test_frame_upgrade_without_ship_hides_starry(self, db, monkeypatch):
        from zhenxun.plugins.zhenxun_plugin_fishing.render import shop as shop_render

        captured = {}

        def _capture_template(name, **kwargs):
            captured.update(kwargs)
            return "<html>fake</html>"

        monkeypatch.setattr(shop_render, "render_template", _capture_template)

        await shop_render.render_shop(
            [],
            [],
            rod_level=5,
            rod_upgrade_price=100,
            hook_level=1,
            hook_upgrade_price=50,
            display_slots=3,
            display_frames=1,
            cat_frames=0,
            upgraded_display_count=0,
            gold=100,
            user_id=USER_ID,
            starry_frames=0,
            has_starry_ship=False,
            star_frames=5,
        )
        keys = [r["key"] for r in captured["frame_upgrade"]["rows"]]
        assert keys == ["wood", "cat"]

    async def test_get_shop_image_passes_star_frames(self, db, monkeypatch):
        from zhenxun.plugins.zhenxun_plugin_fishing.shop import view as shop_view

        captured = {}

        async def _capture_render_shop(*args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return b"FAKE_IMAGE_BYTES"

        monkeypatch.setattr(shop_view, "render_shop", _capture_render_shop)

        user = await db.user_get(USER_ID)
        user.star_frames = 6
        user.starry_frames = 1
        await db.items_add(USER_ID, STARRY_SHIP_ITEM_ID, STARRY_SHIP_ITEM_TYPE, 1)

        image = await shop_view.get_shop_image(USER_ID)
        assert image == b"FAKE_IMAGE_BYTES"
        assert captured["kwargs"].get("star_frames") == 6
        assert captured["kwargs"].get("starry_frames") == 1
        assert captured["kwargs"].get("has_starry_ship") is True
        assert captured["kwargs"].get("base_rod_level") == user.base_rod_level


class TestNestBuffExtension:
    """玉米打窝满后延长已有 buff 的行为验证。"""

    async def test_nest_full_then_extend_oldest(self, db, monkeypatch):
        """已有5个buff、请求10个玉米：立刻用5个填满，再延长最旧的5个。"""
        user = await db.user_get(USER_ID)
        user.corn = 20
        await start_fishing(USER_ID, "1")

        # 预先创建 5 个 nest buff（end_time 递增，模拟不同时间打的窝）
        now = datetime.now()
        for i in range(5):
            await db.buff_add_location_buff(
                location_id="1",
                buff_type=BuffEffect.BUFF_TYPE_NEST,
                duration_hours=8,
                value=5,
                description=f"打窝效果",
                source_user_id=USER_ID,
            )

        # 记录最旧 5 个 buff 的原始 end_time
        old_buffs = sorted(
            [b for b in db._buffs if b.buff_type == BuffEffect.BUFF_TYPE_NEST],
            key=lambda b: b.end_time,
        )
        original_end_times = [b.end_time for b in old_buffs[:5]]

        # 用真正的 filter mock 替换默认的空返回 mock
        monkeypatch.setattr(
            FishingBuff, "filter", db.make_buff_filter_mock()
        )

        ok, msg = await do_nest(USER_ID, corn_count=10, is_private=True)
        assert ok is True
        assert "延长" in msg

        # 验证：总消耗 10 个玉米
        user_after = await db.user_get(USER_ID)
        assert user_after.corn == 10

        # 验证：新增 5 个 buff（总 10 个），最旧 5 个的 end_time 被延长
        nest_buffs = [
            b for b in db._buffs if b.buff_type == BuffEffect.BUFF_TYPE_NEST
        ]
        assert len(nest_buffs) == 10

        # 最旧 5 个 buff 的 end_time 应该各延长了 8 小时
        for i, buff in enumerate(old_buffs[:5]):
            expected = original_end_times[i] + timedelta(hours=8)
            # 允许微小时间差（mock 的 save 是 no-op，end_time 直接在对象上修改）
            assert abs((buff.end_time - expected).total_seconds()) < 1

    async def test_nest_already_full_extend_only(self, db, monkeypatch):
        """已有10个buff（已满）、请求5个玉米：不新增，仅延长最旧5个。"""
        user = await db.user_get(USER_ID)
        user.corn = 10
        await start_fishing(USER_ID, "1")

        for i in range(10):
            await db.buff_add_location_buff(
                location_id="1",
                buff_type=BuffEffect.BUFF_TYPE_NEST,
                duration_hours=8,
                value=5,
                description="打窝效果",
                source_user_id=USER_ID,
            )

        old_buffs = sorted(
            [b for b in db._buffs if b.buff_type == BuffEffect.BUFF_TYPE_NEST],
            key=lambda b: b.end_time,
        )
        original_end_times = [b.end_time for b in old_buffs]

        monkeypatch.setattr(FishingBuff, "filter", db.make_buff_filter_mock())

        ok, msg = await do_nest(USER_ID, corn_count=5, is_private=True)
        assert ok is True
        assert "延长" in msg
        assert "打窝成功" not in msg

        # 消耗 5 个玉米
        user_after = await db.user_get(USER_ID)
        assert user_after.corn == 5

        # buff 总数不变（仍为 10）
        nest_buffs = [
            b for b in db._buffs if b.buff_type == BuffEffect.BUFF_TYPE_NEST
        ]
        assert len(nest_buffs) == 10

        # 最旧 5 个被延长 8h，最新 5 个不变
        for i in range(5):
            expected = original_end_times[i] + timedelta(hours=8)
            assert abs((old_buffs[i].end_time - expected).total_seconds()) < 1
        for i in range(5, 10):
            assert old_buffs[i].end_time == original_end_times[i]

    async def test_nest_more_corn_than_extendable(self, db, monkeypatch):
        """已有10个buff、请求15个玉米：cap到10个，10个buff各延长1次。"""
        user = await db.user_get(USER_ID)
        user.corn = 20
        await start_fishing(USER_ID, "1")

        for i in range(10):
            await db.buff_add_location_buff(
                location_id="1",
                buff_type=BuffEffect.BUFF_TYPE_NEST,
                duration_hours=8,
                value=5,
                description="打窝效果",
                source_user_id=USER_ID,
            )

        old_buffs = sorted(
            [b for b in db._buffs if b.buff_type == BuffEffect.BUFF_TYPE_NEST],
            key=lambda b: b.end_time,
        )
        original_end_times = [b.end_time for b in old_buffs]

        monkeypatch.setattr(FishingBuff, "filter", db.make_buff_filter_mock())

        ok, msg = await do_nest(USER_ID, corn_count=15, is_private=True)
        assert ok is True
        assert "延长" in msg
        assert "上限" in msg  # cap 提示

        # cap 到 10：只消耗 10 个玉米
        user_after = await db.user_get(USER_ID)
        assert user_after.corn == 10  # 20 - 10 = 10

        # buff 总数不变（仍为 10）
        nest_buffs = [
            b for b in db._buffs if b.buff_type == BuffEffect.BUFF_TYPE_NEST
        ]
        assert len(nest_buffs) == 10

        # 10 个 buff 各延长 1 次（+8h）
        for i in range(10):
            expected = original_end_times[i] + timedelta(hours=8)
            assert abs((old_buffs[i].end_time - expected).total_seconds()) < 1


class TestCatFrameNestExtension:
    """猫框打窝 — 独立50%进度条，满后循环延长已有 buff。"""

    async def _setup_starry_fishing(self, db, monkeypatch):
        """在星空图(11)开始钓鱼，需要星空艇+足够竿等级。"""
        user = await db.user_get(USER_ID)
        user.rod_level = 20
        await db.items_add(USER_ID, STARRY_SHIP_ITEM_ID, STARRY_SHIP_ITEM_TYPE, 1)
        await start_fishing(USER_ID, "11")

    async def test_cat_nest_basic_success(self, db, monkeypatch):
        """猫框打窝基本成功：使用 BUFF_TYPE_CAT_NEST，不与玉米共用。"""
        await self._setup_starry_fishing(db, monkeypatch)
        user = await db.user_get(USER_ID)
        user.cat_frames = 5

        monkeypatch.setattr(FishingBuff, "filter", db.make_buff_filter_mock())

        ok, msg = await do_cat_frame_nest(USER_ID, frame_count=3, is_private=True)
        assert ok is True
        assert "猫框" in msg

        # 验证创建的是 cat_nest 类型 buff，不是 nest 类型
        cat_nest_buffs = [
            b for b in db._buffs if b.buff_type == BuffEffect.BUFF_TYPE_CAT_NEST
        ]
        assert len(cat_nest_buffs) == 3
        # 验证是全局 buff，不是地点级
        assert all(b.target_type == "global" for b in cat_nest_buffs)

        nest_buffs = [
            b for b in db._buffs if b.buff_type == BuffEffect.BUFF_TYPE_NEST
        ]
        assert len(nest_buffs) == 0

        user_after = await db.user_get(USER_ID)
        assert user_after.cat_frames == 2  # 5 - 3 = 2

    async def test_cat_nest_full_then_extend_oldest(self, db, monkeypatch):
        """已有5个cat_nest buff、请求10个猫框：5个填满，5个延长最旧。"""
        await self._setup_starry_fishing(db, monkeypatch)
        user = await db.user_get(USER_ID)
        user.cat_frames = 20

        for i in range(5):
            await db.buff_add_global_buff(
                buff_type=BuffEffect.BUFF_TYPE_CAT_NEST,
                start_time=datetime.now(),
                end_time=datetime.now() + timedelta(hours=8),
                value=5,
                description="猫框打窝效果",
            )

        old_buffs = sorted(
            [b for b in db._buffs if b.buff_type == BuffEffect.BUFF_TYPE_CAT_NEST],
            key=lambda b: b.end_time,
        )
        original_end_times = [b.end_time for b in old_buffs[:5]]

        monkeypatch.setattr(FishingBuff, "filter", db.make_buff_filter_mock())

        ok, msg = await do_cat_frame_nest(USER_ID, frame_count=10, is_private=True)
        assert ok is True
        assert "延长" in msg

        user_after = await db.user_get(USER_ID)
        assert user_after.cat_frames == 10  # 20 - 10 = 10

        cat_nest_buffs = [
            b for b in db._buffs if b.buff_type == BuffEffect.BUFF_TYPE_CAT_NEST
        ]
        assert len(cat_nest_buffs) == 10

        # 最旧 5 个被延长 8h
        for i, buff in enumerate(old_buffs[:5]):
            expected = original_end_times[i] + timedelta(hours=8)
            assert abs((buff.end_time - expected).total_seconds()) < 1

    async def test_cat_nest_already_full_extend_only(self, db, monkeypatch):
        """已有10个cat_nest buff（已满）、请求5个猫框：仅延长，不新增。"""
        await self._setup_starry_fishing(db, monkeypatch)
        user = await db.user_get(USER_ID)
        user.cat_frames = 10

        for i in range(10):
            await db.buff_add_global_buff(
                buff_type=BuffEffect.BUFF_TYPE_CAT_NEST,
                start_time=datetime.now(),
                end_time=datetime.now() + timedelta(hours=8),
                value=5,
                description="猫框打窝效果",
            )

        old_buffs = sorted(
            [b for b in db._buffs if b.buff_type == BuffEffect.BUFF_TYPE_CAT_NEST],
            key=lambda b: b.end_time,
        )
        original_end_times = [b.end_time for b in old_buffs]

        monkeypatch.setattr(FishingBuff, "filter", db.make_buff_filter_mock())

        ok, msg = await do_cat_frame_nest(USER_ID, frame_count=5, is_private=True)
        assert ok is True
        assert "延长" in msg
        assert "打窝成功" not in msg

        user_after = await db.user_get(USER_ID)
        assert user_after.cat_frames == 5  # 10 - 5 = 5

        cat_nest_buffs = [
            b for b in db._buffs if b.buff_type == BuffEffect.BUFF_TYPE_CAT_NEST
        ]
        assert len(cat_nest_buffs) == 10  # 总数不变

        # 最旧 5 个被延长 8h，最新 5 个不变
        for i in range(5):
            expected = original_end_times[i] + timedelta(hours=8)
            assert abs((old_buffs[i].end_time - expected).total_seconds()) < 1
        for i in range(5, 10):
            assert old_buffs[i].end_time == original_end_times[i]

    async def test_cat_nest_more_than_extendable(self, db, monkeypatch):
        """已有10个cat_nest buff、请求15个猫框：cap到10个，10个buff各延长1次。"""
        await self._setup_starry_fishing(db, monkeypatch)
        user = await db.user_get(USER_ID)
        user.cat_frames = 20

        for i in range(10):
            await db.buff_add_global_buff(
                buff_type=BuffEffect.BUFF_TYPE_CAT_NEST,
                start_time=datetime.now(),
                end_time=datetime.now() + timedelta(hours=8),
                value=5,
                description="猫框打窝效果",
            )

        old_buffs = sorted(
            [b for b in db._buffs if b.buff_type == BuffEffect.BUFF_TYPE_CAT_NEST],
            key=lambda b: b.end_time,
        )
        original_end_times = [b.end_time for b in old_buffs]

        monkeypatch.setattr(FishingBuff, "filter", db.make_buff_filter_mock())

        ok, msg = await do_cat_frame_nest(USER_ID, frame_count=15, is_private=True)
        assert ok is True
        assert "延长" in msg
        assert "上限" in msg  # cap 提示

        # cap 到 10：只消耗 10 个猫框
        user_after = await db.user_get(USER_ID)
        assert user_after.cat_frames == 10  # 20 - 10 = 10

        cat_nest_buffs = [
            b for b in db._buffs if b.buff_type == BuffEffect.BUFF_TYPE_CAT_NEST
        ]
        assert len(cat_nest_buffs) == 10  # 总数不变

        # 10 个 buff 各延长 1 次（+8h）
        for i in range(10):
            expected = original_end_times[i] + timedelta(hours=8)
            assert abs((old_buffs[i].end_time - expected).total_seconds()) < 1


class TestFrameBuffExtension:
    """木框满后延长已有 buff 的行为验证。"""

    async def test_frame_full_then_extend_oldest(self, db, monkeypatch):
        """已有7个frame buff、请求8个木框：3个填满，5个延长最旧buff。"""
        user = await db.user_get(USER_ID)
        user.display_frames = 10
        await start_fishing(USER_ID, "1")

        now = datetime.now()
        for i in range(7):
            await db.buff_add_global_buff(
                buff_type=BuffEffect.BUFF_TYPE_FRAME,
                start_time=now,
                end_time=now + timedelta(hours=8),
                value=5,
                description="木框效果",
            )

        old_buffs = sorted(
            [b for b in db._buffs if b.buff_type == BuffEffect.BUFF_TYPE_FRAME],
            key=lambda b: b.end_time,
        )
        original_end_times = [b.end_time for b in old_buffs]

        monkeypatch.setattr(FishingBuff, "filter", db.make_buff_filter_mock())

        ok, msg = await use_display_frame_buff(USER_ID, count=8, is_private=True)
        assert ok is True
        assert "延长" in msg

        # 消耗 8 个木框（3新增 + 5延长）
        user_after = await db.user_get(USER_ID)
        assert user_after.display_frames == 2

        # 总 buff 数 = 7 + 3 = 10
        frame_buffs = [
            b for b in db._buffs if b.buff_type == BuffEffect.BUFF_TYPE_FRAME
        ]
        assert len(frame_buffs) == 10

        # 最旧 5 个被延长 8h
        for i in range(5):
            expected = original_end_times[i] + timedelta(hours=8)
            assert abs((old_buffs[i].end_time - expected).total_seconds()) < 1

    async def test_frame_already_full_extend_only(self, db, monkeypatch):
        """已有10个frame buff（已满）、请求5个木框：仅延长，不新增。"""
        user = await db.user_get(USER_ID)
        user.display_frames = 5
        await start_fishing(USER_ID, "1")

        now = datetime.now()
        for i in range(10):
            await db.buff_add_global_buff(
                buff_type=BuffEffect.BUFF_TYPE_FRAME,
                start_time=now,
                end_time=now + timedelta(hours=8),
                value=5,
                description="木框效果",
            )

        old_buffs = sorted(
            [b for b in db._buffs if b.buff_type == BuffEffect.BUFF_TYPE_FRAME],
            key=lambda b: b.end_time,
        )
        original_end_times = [b.end_time for b in old_buffs]

        monkeypatch.setattr(FishingBuff, "filter", db.make_buff_filter_mock())

        ok, msg = await use_display_frame_buff(USER_ID, count=5, is_private=True)
        assert ok is True
        assert "延长" in msg

        # 消耗 5 个木框
        user_after = await db.user_get(USER_ID)
        assert user_after.display_frames == 0

        # buff 总数不变
        frame_buffs = [
            b for b in db._buffs if b.buff_type == BuffEffect.BUFF_TYPE_FRAME
        ]
        assert len(frame_buffs) == 10

        # 最旧 5 个被延长，最新 5 个不变
        for i in range(5):
            expected = original_end_times[i] + timedelta(hours=8)
            assert abs((old_buffs[i].end_time - expected).total_seconds()) < 1
        for i in range(5, 10):
            assert old_buffs[i].end_time == original_end_times[i]

    async def test_frame_more_than_extendable(self, db, monkeypatch):
        """已有10个frame buff、请求15个木框：cap到10个，10个buff各延长1次。"""
        user = await db.user_get(USER_ID)
        user.display_frames = 20
        await start_fishing(USER_ID, "1")

        now = datetime.now()
        for i in range(10):
            await db.buff_add_global_buff(
                buff_type=BuffEffect.BUFF_TYPE_FRAME,
                start_time=now,
                end_time=now + timedelta(hours=8),
                value=5,
                description="木框效果",
            )

        old_buffs = sorted(
            [b for b in db._buffs if b.buff_type == BuffEffect.BUFF_TYPE_FRAME],
            key=lambda b: b.end_time,
        )
        original_end_times = [b.end_time for b in old_buffs]

        monkeypatch.setattr(FishingBuff, "filter", db.make_buff_filter_mock())

        ok, msg = await use_display_frame_buff(USER_ID, count=15, is_private=True)
        assert ok is True
        assert "延长" in msg
        assert "上限" in msg  # cap 提示

        # cap 到 10：只消耗 10 个木框
        user_after = await db.user_get(USER_ID)
        assert user_after.display_frames == 10  # 20 - 10 = 10

        # buff 总数不变（仍为 10）
        frame_buffs = [
            b for b in db._buffs if b.buff_type == BuffEffect.BUFF_TYPE_FRAME
        ]
        assert len(frame_buffs) == 10

        # 10 个 buff 各延长 1 次（+8h）
        for i in range(10):
            expected = original_end_times[i] + timedelta(hours=8)
            assert abs((old_buffs[i].end_time - expected).total_seconds()) < 1

