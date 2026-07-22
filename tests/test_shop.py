import pytest
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
    do_nest,
    check_sign,
    exchange_to_gold,
)
from zhenxun.plugins.zhenxun_plugin_fishing.fishing import start_fishing, stop_fishing
from zhenxun.plugins.zhenxun_plugin_fishing.models import BuffEffect
from zhenxun.plugins.zhenxun_plugin_fishing.render.shop import render_shop


USER_ID = "test_user_001"


class TestShopRenderStarryFrame:
    """鱼店渲染：星空木框升级仅在已建星空艇后展示。"""

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
        # 低竿等级同样不应展示星空木框
        rows = await self._capture_frame_rows(has_starry_ship=False, rod_level=5)
        assert not any(r.get("key") == "starry" for r in rows)


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
        assert "星空木框" in msg
        assert "星辰木框" in msg
        user_after = await db.user_get(USER_ID)
        assert user_after.starry_frames == 1
        assert user_after.star_frames == 4
        assert user_after.cat_frames == 0
        assert user_after.display_slots == 10

    async def test_starry_does_not_consume_cat_frames(self, db):
        """旧 bug：星空木框误扣猫猫框；现应只扣星辰木框。"""
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
        assert "星辰木框不足" in msg
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
        assert "增加展示栏位" in msg
        assert "升级星空木框" not in msg
        user_after = await db.user_get(USER_ID)
        assert user_after.display_slots == 4
        assert user_after.starry_frames == 0
        assert user_after.star_frames == 10

    async def test_buy_item_aliases_all_route_to_upgrade(self, db):
        aliases = [
            "升级展示栏",
            "增加展示栏位",
            "强化展示栏位",
            "升级星空木框",
            "星空木框",
            "展示栏位",
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
        assert "展示木框不足" in msg
        assert "猫猫框不足" in msg
        assert "星辰木框不足" in msg
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
        assert "增加展示栏位" in msg
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
        assert "增加展示栏位" in msg
        assert "强化展示栏位" in msg
        assert "升级星空木框" in msg
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
        assert "强化展示栏位" in msg
        user_after = await db.user_get(USER_ID)
        assert user_after.upgraded_display_count == 3
        assert user_after.cat_frames == 0
        assert user_after.display_slots == 5

    async def test_starry_cost_progression(self, db):
        """第 n 次升级消耗 n 个星辰木框。"""
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
        user.display_frames = 1  # 第4栏需要1个展示木框
        user.cat_frames = 1  # 强化第1个需要1个猫框
        user.upgraded_display_count = 0
        user.star_frames = 0

        ok, msg = await upgrade_display_slots(USER_ID)
        assert ok is True
        assert "增加展示栏位" in msg
        assert "强化展示栏位" in msg
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
        assert any("展示木框" in r["material"] or r["is_max"] for r in fu["rows"])
        starry = next(r for r in fu["rows"] if r["key"] == "starry")
        assert "星辰木框" in starry["material"]
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

