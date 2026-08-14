from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from zhenxun.plugins.zhenxun_plugin_fishing.models import FishingUser

from zhenxun.plugins.zhenxun_plugin_fishing.fishing import (
    SimulationResult,
    check_fishing_status,
    settle_fishing_step,
    simulate_fishing_loop,
    start_fishing,
    stop_fishing,
    use_time_potion_settle,
)

USER_ID = "test_user_001"
LOCATION_1 = "1"


class TestLocationReplyNormalization:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("1", "1"),
            (" 12 ", "12"),
            ("s1", "S1"),
            ("S1", "S1"),
            ("-11", "-11"),
            ("我要是输入1，会怎样？", None),
            ("地图1", None),
            ("? 1", None),
            ("", None),
        ],
    )
    def test_only_complete_location_ids_are_accepted(self, raw, expected):
        from zhenxun.plugins.zhenxun_plugin_fishing.handlers.fishing import (
            normalize_location_reply,
        )

        assert normalize_location_reply(raw) == expected


class TestBlackMarketHint:
    @pytest.mark.parametrize(
        ("black_market_count", "available_date", "expected"),
        [
            (0, date(2026, 8, 1), False),
            (1, date(2026, 7, 30), True),
            (1, None, True),
            (1, date(2026, 8, 1), False),
        ],
    )
    def test_show_when_either_market_is_available(
        self, black_market_count, available_date, expected
    ):
        from zhenxun.plugins.zhenxun_plugin_fishing.handlers.fishing import (
            should_show_black_market_hint,
        )

        assert (
            should_show_black_market_hint(
                black_market_count,
                available_date,
                today=date(2026, 7, 30),
            )
            is expected
        )


class TestStopFishingHandlerBoundary:
    async def test_active_group_failure_does_not_block_settlement(self, monkeypatch):
        from zhenxun.plugins.zhenxun_plugin_fishing.handlers import fishing as handler
        from zhenxun.plugins.zhenxun_plugin_fishing.models import FishingActiveGroup

        call_order = []

        async def fake_stop_fishing(*args, **kwargs):
            call_order.append("settlement")
            return {"user_id": USER_ID}, [], False

        async def broken_active_group_record(*args, **kwargs):
            call_order.append("active_group")
            raise RuntimeError("malformed nickname")

        monkeypatch.setattr(
            handler, "_ensure_user", AsyncMock(return_value=(USER_ID, "TestUser"))
        )
        monkeypatch.setattr(handler, "_is_private_chat", Mock(return_value=False))
        monkeypatch.setattr(
            handler, "is_group_action_limit_enabled", AsyncMock(return_value=False)
        )
        monkeypatch.setattr(FishingUser, "get_stop_count", AsyncMock(return_value=0))
        monkeypatch.setattr(FishingUser, "get_status_count", AsyncMock(return_value=0))
        monkeypatch.setattr(FishingUser, "is_fishing", AsyncMock(return_value=True))
        monkeypatch.setattr(
            FishingUser,
            "get_user",
            AsyncMock(
                return_value=type(
                    "User", (), {"smart_black_market_available_date": date.max}
                )()
            ),
        )
        monkeypatch.setattr(
            FishingUser, "get_black_market_count", AsyncMock(return_value=1)
        )
        monkeypatch.setattr(handler, "stop_fishing", fake_stop_fishing)
        monkeypatch.setattr(
            FishingActiveGroup, "record_fishing", broken_active_group_record
        )
        monkeypatch.setattr(
            handler,
            "run_post_settlement",
            AsyncMock(side_effect=lambda user_id, is_private, messages: messages),
        )

        event = type("GroupEvent", (), {"group_id": 161355983})()
        result = await handler._settle_stop_fishing.__wrapped__(event, Mock())

        assert result == ({"user_id": USER_ID}, [], False, USER_ID)
        assert call_order == ["settlement", "active_group"]


class TestStartFishing:
    async def test_start_fishing_creates_user(self, db):
        image, ok, hint = await start_fishing(USER_ID, LOCATION_1, "TestUser")
        assert ok is True
        user = await db.user_get(USER_ID)
        assert user is not None
        assert user.user_id == USER_ID

    async def test_start_fishing_sets_status(self, db):
        await start_fishing(USER_ID, LOCATION_1, "TestUser")
        assert await db.status_is_fishing(USER_ID) is True
        status = await db.status_get(USER_ID)
        assert status is not None
        assert status["location_id"] == LOCATION_1

    async def test_start_fishing_records_group_context(self, db):
        await start_fishing(USER_ID, LOCATION_1, "TestUser", group_id="1054188847")
        status = await db.status_get(USER_ID)
        assert status is not None
        assert status["group_id"] == "1054188847"

    async def test_start_fishing_returns_image(self, db):
        image, ok, hint = await start_fishing(USER_ID, LOCATION_1)
        assert image is not None
        assert isinstance(image, bytes)
        assert ok is True

    async def test_start_fishing_already_fishing(self, db):
        await start_fishing(USER_ID, LOCATION_1)
        image, ok, hint = await start_fishing(USER_ID, LOCATION_1)
        assert ok is False
        assert image is not None

    async def test_start_fishing_invalid_location(self, db):
        user = await db.user_get(USER_ID)
        user.rod_level = 1
        image, ok, hint = await start_fishing(USER_ID, "999")
        assert ok is False
        assert "地图不存在" in hint

    async def test_start_fishing_rod_level_too_low_hint(self, db):
        """鱼竿等级不够时应给出明确提示。"""
        user = await db.user_get(USER_ID)
        user.rod_level = 6  # 10图 difficulty=9，6级不够
        image, ok, hint = await start_fishing(USER_ID, "10")
        assert ok is False
        assert "鱼竿等级不够" in hint
        assert "9" in hint

    async def test_start_fishing_starry_without_ship_hint(self, db, monkeypatch):
        """未建设星空艇时进入星空图应给出明确提示。"""
        from zhenxun.plugins.zhenxun_plugin_fishing import starry

        monkeypatch.setattr(starry, "has_starry_ship", AsyncMock(return_value=False))
        user = await db.user_get(USER_ID)
        user.rod_level = 10
        image, ok, hint = await start_fishing(USER_ID, "11")
        assert ok is False
        assert "尚未建设星空艇" in hint

    async def test_start_fishing_cat_park_without_ticket_hint(self, db, monkeypatch):
        """未获得猫猫乐园门票时应给出明确提示。"""
        from zhenxun.plugins.zhenxun_plugin_fishing import cat_park

        monkeypatch.setattr(
            cat_park, "has_cat_park_ticket", AsyncMock(return_value=False)
        )
        user = await db.user_get(USER_ID)
        user.rod_level = 10
        image, ok, hint = await start_fishing(USER_ID, "S1")
        assert ok is False
        assert "猫猫乐园门票" in hint

    async def test_shadow_scene_is_hidden_and_restricted(self, db, monkeypatch):
        from zhenxun.plugins.zhenxun_plugin_fishing import render as render_module
        from zhenxun.plugins.zhenxun_plugin_fishing.core import actions

        scene_mock = AsyncMock(return_value=b"SHADOW_SCENE")
        select_mock = AsyncMock(return_value=b"LOCATION_LIST")
        monkeypatch.setattr(actions, "render_scene", scene_mock)
        monkeypatch.setattr(render_module, "render_location_select", select_mock)

        denied_image, denied_ok, denied_hint = await start_fishing(
            "418648119", "-11", "Denied"
        )
        assert denied_image == b"LOCATION_LIST"
        assert denied_ok is False
        assert "指定测试账号" in denied_hint
        assert await FishingUser.get_status("418648119") is None

        image, ok, hint = await start_fishing("418648118", "-11", "ShadowTester")
        assert image == b"SHADOW_SCENE"
        assert ok is True
        assert hint == ""
        status = await FishingUser.get_status("418648118")
        assert status is not None
        assert status["location_id"] == "11"
        assert status["scene_instance_id"] == "-11"
        assert status["shadow_scene"] is True
        assert status["time_potions_used"] == []
        rendered_location = scene_mock.await_args.args[1]
        assert rendered_location.id == "11"

    async def test_shadow_scene_players_are_isolated_from_map_11(self, db):
        shadow_id = "418648118"
        normal_id = "shadow-isolation-normal"
        await FishingUser.start_fishing(shadow_id, "11")
        shadow_status = await FishingUser.get_status(shadow_id)
        shadow_status["scene_instance_id"] = "-11"
        shadow_status["shadow_scene"] = True
        await FishingUser.update_fishing_status(shadow_id, shadow_status)
        await FishingUser.start_fishing(normal_id, "11")

        assert await FishingUser.get_location_fishers("-11") == [shadow_id]
        assert await FishingUser.get_location_fishers("11") == [normal_id]

    async def test_start_fishing_sign_in_on_first_fish(self, db):
        await start_fishing(USER_ID, LOCATION_1, "TestUser")
        await stop_fishing(USER_ID, gm_mode=True)
        user = await db.user_get(USER_ID)
        assert user.corn >= 1


class TestStopFishing:
    async def test_stop_fishing_without_start(self, db):
        render_data, buffs, ok = await stop_fishing(USER_ID)
        assert render_data is None
        assert buffs == []
        assert ok is False

    async def test_stop_fishing_after_start(self, db):
        await start_fishing(USER_ID, LOCATION_1, "TestUser")
        render_data, buffs, ok = await stop_fishing(USER_ID)
        assert render_data is not None
        assert isinstance(render_data, dict)
        assert isinstance(buffs, list)
        assert await db.status_is_fishing(USER_ID) is False

    async def test_stop_fishing_gives_fish(self, db):
        user = await db.user_get(USER_ID)
        user.rod_level = 5
        await start_fishing(USER_ID, LOCATION_1, "TestUser")
        render_data, buffs, ok = await stop_fishing(USER_ID, gm_mode=True)
        fish_list = await db.backpack_get_user_fish(USER_ID)
        assert len(fish_list) > 0

    async def test_stop_fishing_gm_mode(self, db):
        user = await db.user_get(USER_ID)
        user.rod_level = 5
        await start_fishing(USER_ID, LOCATION_1, "TestUser")
        render_data, buffs, ok = await stop_fishing(USER_ID, gm_mode=True)
        assert render_data is not None
        fish_list = await db.backpack_get_user_fish(USER_ID)
        assert len(fish_list) > 0

    async def test_stop_fishing_increments_stop_count(self, db):
        user = await db.user_get(USER_ID)
        user.rod_level = 5
        await start_fishing(USER_ID, LOCATION_1, "TestUser")
        await stop_fishing(USER_ID)
        count = await db.user_get_stop_count(USER_ID)
        assert count >= 1

    async def test_stop_fishing_frame_pity(self, db):
        user = await db.user_get(USER_ID)
        user.rod_level = 10
        user.frame_pity_counter = 119
        await start_fishing(USER_ID, LOCATION_1, "TestUser")
        await stop_fishing(USER_ID, gm_mode=True)
        fish_list = await db.backpack_get_user_fish(USER_ID)
        fish_names = [f["fish_name"] for f in fish_list]
        assert len(fish_names) > 0


class TestFishingFlow:
    async def test_full_fishing_cycle(self, db):
        image1, ok1, hint1 = await start_fishing(USER_ID, LOCATION_1, "TestUser")
        assert ok1 is True
        assert image1 is not None

        user = await db.user_get(USER_ID)
        user.rod_level = 5

        render_data, buffs, ok2 = await stop_fishing(USER_ID, gm_mode=True)
        assert render_data is not None
        assert await db.status_is_fishing(USER_ID) is False

        fish_list = await db.backpack_get_user_fish(USER_ID)
        assert len(fish_list) > 0

    async def test_fish_then_sell_cycle(self, db):
        user = await db.user_get(USER_ID)
        user.rod_level = 5
        await start_fishing(USER_ID, LOCATION_1, "TestUser")
        await stop_fishing(USER_ID, gm_mode=True)

        fish_list = await db.backpack_get_user_fish(USER_ID)
        assert len(fish_list) > 0

        from zhenxun.plugins.zhenxun_plugin_fishing.backpack import sell_fish

        ok, msg = await sell_fish(USER_ID, "N")
        assert isinstance(ok, bool)

    async def test_multiple_fishing_sessions(self, db):
        user = await db.user_get(USER_ID)
        user.rod_level = 5

        for i in range(3):
            await start_fishing(USER_ID, LOCATION_1)
            await stop_fishing(USER_ID, gm_mode=True)

        fish_list = await db.backpack_get_user_fish(USER_ID)
        assert len(fish_list) > 0


class TestStepSettlement:
    async def test_settle_step_returns_none_when_not_fishing(self, db):
        result = await settle_fishing_step(USER_ID)
        assert result is None

    async def test_settle_step_keeps_auto_switched_bait_ephemeral_and_writes_atomically(
        self, db, monkeypatch
    ):
        from zhenxun.plugins.zhenxun_plugin_fishing.config import BaitData
        from zhenxun.plugins.zhenxun_plugin_fishing.core import actions
        from zhenxun.plugins.zhenxun_plugin_fishing.core.context import StepResult
        from zhenxun.plugins.zhenxun_plugin_fishing.models.user import FishingUser

        user = await db.user_get(USER_ID)
        user.bait_id = "1"
        user.fishing_status = {"start_time": datetime.now().isoformat()}
        switched_bait = BaitData(
            id=2, name="自动换饵", speed_bonus=0, price=1, description="测试"
        )
        step = StepResult(
            new_fish=[],
            new_bait_consumed=1,
            frame_pity=0,
            cat_frame_pity=0,
            bait=switched_bait,
            bait_remaining=3,
            utr_pity=0,
            buff_messages=[],
            bait_usage={"2": 1},
        )
        updated_status = {"start_time": user.fishing_status["start_time"], "done": True}
        monkeypatch.setattr(
            actions,
            "_compute_settle_step",
            AsyncMock(return_value=(step, updated_status, Mock(user=user))),
        )
        events = []

        @asynccontextmanager
        async def transaction():
            snapshot = deepcopy(user.__dict__)
            events.append("transaction.enter")
            try:
                yield None
            except Exception:
                user.__dict__.clear()
                user.__dict__.update(snapshot)
                events.append("transaction.rollback")
                raise

        async def update_status(user_id, status):
            events.append("status.write")
            user.fishing_status = status

        async def fail_bait(*args):
            events.append("bait.write")
            raise RuntimeError("bait write failed")

        monkeypatch.setattr(actions, "_stop_db_transaction", transaction)
        monkeypatch.setattr(FishingUser, "update_fishing_status", update_status)
        monkeypatch.setattr(actions, "consume_bait_incremental", fail_bait)

        with pytest.raises(RuntimeError, match="bait write failed"):
            await settle_fishing_step(USER_ID)

        assert user.bait_id == "1"
        assert user.fishing_status == {"start_time": updated_status["start_time"]}
        assert events == [
            "transaction.enter",
            "status.write",
            "bait.write",
            "transaction.rollback",
        ]

    async def test_settle_step_returns_step_result(self, db):
        user = await db.user_get(USER_ID)
        user.rod_level = 5
        await start_fishing(USER_ID, LOCATION_1, "TestUser")
        result = await settle_fishing_step(USER_ID, gm_mode=True)
        assert result is not None
        assert hasattr(result, "new_fish")
        assert hasattr(result, "new_bait_consumed")
        assert hasattr(result, "frame_pity")
        assert hasattr(result, "bait")
        assert hasattr(result, "buff_messages")

    async def test_settle_step_does_not_persist_auto_switched_bait(
        self, db, monkeypatch
    ):
        """步进结算不持久化临时自动换饵，保持玩家持久化偏好；
        最终鱼饵在收杆阶段由 _apply_session_reward_stage 统一落库。"""
        from zhenxun.plugins.zhenxun_plugin_fishing.core import actions

        user = await db.user_get(USER_ID)
        user.rod_level = 5
        await start_fishing(USER_ID, LOCATION_1, "TestUser")
        bait_before = user.bait_id
        switched_bait = Mock(id=2, speed_bonus=20)
        step = actions.StepResult(
            new_fish=[],
            new_bait_consumed=0,
            frame_pity=0,
            cat_frame_pity=0,
            bait=switched_bait,
            bait_remaining=1,
        )
        status = await db.status_get(USER_ID)
        ctx = Mock(user=user)

        async def fake_compute(*args, **kwargs):
            return step, status, ctx

        monkeypatch.setattr(actions, "_compute_settle_step", fake_compute)
        await actions.settle_fishing_step(USER_ID)

        assert user.bait_id == bait_before

    async def test_settle_step_accumulates_fish(self, db):
        user = await db.user_get(USER_ID)
        user.rod_level = 5
        await start_fishing(USER_ID, LOCATION_1, "TestUser")

        step1 = await settle_fishing_step(USER_ID, gm_mode=True)
        assert step1 is not None

        status = await db.status_get(USER_ID)
        assert status is not None
        assert "fish_caught" in status
        assert "last_settle_time" in status

    async def test_settle_step_updates_last_settle_time(self, db):
        user = await db.user_get(USER_ID)
        user.rod_level = 5
        await start_fishing(USER_ID, LOCATION_1, "TestUser")

        status_before = await db.status_get(USER_ID)
        settle_time_before = status_before.get("last_settle_time")

        await settle_fishing_step(USER_ID, gm_mode=True)

        status_after = await db.status_get(USER_ID)
        assert status_after["last_settle_time"] != settle_time_before

    async def test_check_fishing_status_returns_image(self, db):
        user = await db.user_get(USER_ID)
        user.rod_level = 5
        await start_fishing(USER_ID, LOCATION_1, "TestUser")

        image, step = await check_fishing_status(USER_ID)
        assert image is not None
        assert isinstance(image, bytes)
        assert step is not None

    async def test_check_fishing_status_not_fishing(self, db):
        image, step = await check_fishing_status(USER_ID)
        assert image is None
        assert step is None

    async def test_check_fishing_status_preserves_fishing_state(self, db):
        user = await db.user_get(USER_ID)
        user.rod_level = 5
        await start_fishing(USER_ID, LOCATION_1, "TestUser")

        await check_fishing_status(USER_ID)
        assert await db.status_is_fishing(USER_ID) is True

    async def test_stop_fishing_after_check_status(self, db):
        user = await db.user_get(USER_ID)
        user.rod_level = 5
        await start_fishing(USER_ID, LOCATION_1, "TestUser")

        await check_fishing_status(USER_ID)
        render_data, buffs, ok = await stop_fishing(USER_ID, gm_mode=True)
        assert render_data is not None
        assert await db.status_is_fishing(USER_ID) is False
        fish_list = await db.backpack_get_user_fish(USER_ID)
        assert len(fish_list) > 0

    async def test_multiple_check_status_accumulates(self, db):
        user = await db.user_get(USER_ID)
        user.rod_level = 5
        await start_fishing(USER_ID, LOCATION_1, "TestUser")

        await settle_fishing_step(USER_ID, gm_mode=True)
        await settle_fishing_step(USER_ID, gm_mode=True)

        status = await db.status_get(USER_ID)
        total_fish_count = sum(
            entry.get("count", 0) for entry in status.get("fish_caught", [])
        )
        assert total_fish_count >= 0

    async def test_start_fishing_status_has_new_fields(self, db):
        await start_fishing(USER_ID, LOCATION_1, "TestUser")
        status = await db.status_get(USER_ID)
        assert "last_settle_time" in status
        assert "fish_caught" in status
        assert "bait_consumed" in status
        assert "frame_pity" in status
        assert status["fish_caught"] == []
        assert status["bait_consumed"] == 0


class TestFishingLoopIntegration:
    @staticmethod
    async def _context(db, duration_minutes=10, bait_remaining=0):
        from zhenxun.plugins.zhenxun_plugin_fishing.config import ConfigManager
        from zhenxun.plugins.zhenxun_plugin_fishing.core.context import FishingContext

        user = await db.user_get(USER_ID)
        user.rod_level = 5
        location = ConfigManager.get_location(LOCATION_1)
        now = datetime(2026, 7, 19, 12, 0, 0)
        return FishingContext(
            user=user,
            user_id=USER_ID,
            location=location,
            buffs=[],
            bait=None,
            bait_speed_bonus=0,
            bait_remaining=bait_remaining,
            settle_start=now - timedelta(minutes=duration_minutes),
            now=now,
        )

    async def test_normal_time_mode_runs_full_intervals(self, db, monkeypatch):
        from zhenxun.plugins.zhenxun_plugin_fishing.core import engine

        ctx = await self._context(db)
        monkeypatch.setattr(engine, "_calculate_fishing_interval", lambda *_: 5.0)
        catch = Mock(side_effect=[(1, 0), (2, 0)])
        monkeypatch.setattr(engine, "_catch_fish_at_interval", catch)

        result = await engine.simulate_fishing_loop(ctx)

        assert catch.call_count == 2
        assert result.frame_pity == 2

    async def test_time_credit_uses_credit_without_advancing_clock(
        self, db, monkeypatch
    ):
        from zhenxun.plugins.zhenxun_plugin_fishing.core import engine

        ctx = await self._context(db, duration_minutes=0)
        monkeypatch.setattr(engine, "_calculate_fishing_interval", lambda *_: 5.0)
        catch_times = []

        def catch(*args, **kwargs):
            catch_times.append(kwargs["catch_time"])
            return args[3] + 1, args[5]

        monkeypatch.setattr(engine, "_catch_fish_at_interval", catch)
        result = await engine.simulate_fishing_loop(ctx, time_credit_minutes=12)

        assert len(catch_times) == 2
        assert catch_times == [ctx.settle_start, ctx.settle_start]
        assert result.frame_pity == 2

    async def test_remaining_time_probability_path_consumes_bait_on_catch(
        self, db, monkeypatch
    ):
        from zhenxun.plugins.zhenxun_plugin_fishing.config import FishData
        from zhenxun.plugins.zhenxun_plugin_fishing.core import engine

        ctx = await self._context(db, duration_minutes=2, bait_remaining=1)
        bait = FishData(id="test-bait", base_price=1)
        ctx.bait = bait
        monkeypatch.setattr(engine, "_calculate_fishing_interval", lambda *_: 5.0)
        monkeypatch.setattr(engine.random, "random", lambda: 0.0)

        def catch(*args, **kwargs):
            args[4].append((FishData(id="test-fish", base_price=1), "N", 1))
            return args[3], args[5]

        monkeypatch.setattr(engine, "_catch_fish_at_interval", catch)
        result = await engine.simulate_fishing_loop(ctx)

        assert len(result.fish_caught) == 1
        assert result.bait_remaining == 0
        assert result.bait_usage == {"test-bait": 1}

    async def test_utr_pity_149_notifies_after_guaranteed_catch(self, db, monkeypatch):
        from zhenxun.plugins.zhenxun_plugin_fishing.config import FishData
        from zhenxun.plugins.zhenxun_plugin_fishing.core import engine

        ctx = await self._context(db, duration_minutes=0)

        def effects(*_args, **_kwargs):
            return {"weather_lost_wind": True}

        def catch(*args, **_kwargs):
            args[4].append((FishData(id="test-utr", base_price=1), "UTR", 1))
            return args[3], 0

        monkeypatch.setattr(engine, "_compute_base_effects", effects)
        monkeypatch.setattr(engine, "_calculate_fishing_interval", lambda *_: 5.0)
        monkeypatch.setattr(engine, "_catch_fish_at_interval", catch)

        await engine.simulate_fishing_loop(
            ctx,
            initial_utr_pity=149,
            time_credit_minutes=5,
        )

        assert any("保底触发" in message for message in ctx.buff_messages)

    async def test_frame_pity_149_notifies_after_guaranteed_catch(
        self, db, monkeypatch
    ):
        from zhenxun.plugins.zhenxun_plugin_fishing.config import FishData
        from zhenxun.plugins.zhenxun_plugin_fishing.core import engine

        ctx = await self._context(db, duration_minutes=0)

        def catch(*args, **_kwargs):
            args[4].append((FishData(id="木框", base_price=0), "UTR", 1))
            return 0, args[5]

        monkeypatch.setattr(engine, "_calculate_fishing_interval", lambda *_: 5.0)
        monkeypatch.setattr(engine, "_catch_fish_at_interval", catch)
        monkeypatch.setattr(engine, "_record_bait_consumption", lambda *_: None)

        await engine.simulate_fishing_loop(
            ctx,
            initial_frame_pity=149,
            time_credit_minutes=5,
        )

        assert any("木框保底触发" in message for message in ctx.buff_messages)

    async def test_bait_exhaustion_switches_to_no_bait_mode(self, db, monkeypatch):
        from zhenxun.plugins.zhenxun_plugin_fishing.config import BaitData
        from zhenxun.plugins.zhenxun_plugin_fishing.core import engine

        ctx = await self._context(db, duration_minutes=0, bait_remaining=0)
        ctx.bait = BaitData(
            id=999, name="空鱼饵", speed_bonus=0, price=1, description="测试"
        )
        monkeypatch.setattr(engine, "_calculate_fishing_interval", lambda *_: 5.0)

        result = await engine.simulate_fishing_loop(ctx, time_credit_minutes=0)

        assert result.bait is None
        assert result.bait_remaining == 0
        assert "没有其他鱼饵了" in ctx.buff_messages[-1]

    async def test_bait_switch_only_updates_simulation_state(self, db, monkeypatch):
        from zhenxun.plugins.zhenxun_plugin_fishing.config import BaitData
        from zhenxun.plugins.zhenxun_plugin_fishing.core import engine

        ctx = await self._context(db, duration_minutes=0, bait_remaining=0)
        ctx.user.bait_id = "1"
        ctx.bait = BaitData(
            id=1, name="耗尽鱼饵", speed_bonus=0, price=1, description="测试"
        )
        switched_bait = BaitData(
            id=2, name="备用鱼饵", speed_bonus=10, price=2, description="测试"
        )
        save = AsyncMock()
        monkeypatch.setattr(ctx.user, "save", save)

        result = await engine.simulate_fishing_loop(
            ctx,
            time_credit_minutes=0,
            initial_available_baits={
                "2": {"data": switched_bait, "remaining": 3},
            },
        )

        assert result.bait is switched_bait
        assert result.bait_remaining == 3
        assert ctx.user.bait_id == "1"
        save.assert_not_awaited()


class TestSimulationResultIntegration:
    async def test_normal_settlement_passes_named_simulation_result(
        self, db, monkeypatch
    ):
        from zhenxun.plugins.zhenxun_plugin_fishing.core import actions

        captured = []
        real_simulate = simulate_fishing_loop

        async def capture_simulation(*args, **kwargs):
            result = await real_simulate(*args, **kwargs)
            captured.append(result)
            return result

        monkeypatch.setattr(actions, "simulate_fishing_loop", capture_simulation)
        user = await db.user_get(USER_ID)
        user.rod_level = 5
        await start_fishing(USER_ID, LOCATION_1, "TestUser")
        step = await settle_fishing_step(USER_ID, gm_mode=True)

        assert len(captured) == 1
        simulation = captured[0]
        assert isinstance(simulation, SimulationResult)
        assert step is not None
        assert step.new_fish == simulation.fish_caught
        assert step.frame_pity == simulation.frame_pity
        assert step.bait_usage == simulation.bait_usage
        assert step.utr_pity == simulation.utr_pity

    async def test_time_potion_passes_named_results_through_both_phases(
        self, db, monkeypatch
    ):
        from zhenxun.plugins.zhenxun_plugin_fishing.core import potion

        captured = []
        call_kwargs = []
        real_simulate = simulate_fishing_loop

        async def capture_simulation(*args, **kwargs):
            call_kwargs.append(kwargs)
            result = await real_simulate(*args, **kwargs)
            captured.append(result)
            return result

        monkeypatch.setattr(potion, "simulate_fishing_loop", capture_simulation)
        user = await db.user_get(USER_ID)
        user.rod_level = 5
        await start_fishing(USER_ID, LOCATION_1, "TestUser")
        status = await db.status_get(USER_ID)
        previous_settle_time = status["last_settle_time"]

        ok, image = await use_time_potion_settle(USER_ID, 1)

        assert ok is True
        assert isinstance(image, bytes)
        assert len(captured) == 2
        assert all(isinstance(result, SimulationResult) for result in captured)
        updated = await db.status_get(USER_ID)
        assert updated["last_settle_time"] != previous_settle_time
        assert updated["frame_pity"] == captured[-1].frame_pity
        assert updated["utr_pity"] == captured[-1].utr_pity
        # 第二阶段必须以第一阶段的整套鱼饵状态初始化，不能重新读取未扣库存。
        assert call_kwargs[1]["initial_available_baits"] == captured[0].available_baits
        assert call_kwargs[1]["initial_no_bait_mode"] is captured[0].no_bait_mode


class TestAntiIdleFishing:
    """防闲置功能：闲置超阈值时自动回到上次钓鱼地图开始钓鱼。"""

    async def test_idle_over_threshold_triggers_auto_fishing(self, db):
        """闲置超过阈值时，自动回到上次地图钓鱼，返回地图名称。"""
        from zhenxun.plugins.zhenxun_plugin_fishing.core import try_auto_fish_on_idle

        user = await db.user_get(USER_ID)
        user.rod_level = 5
        user.last_location_id = LOCATION_1
        user.last_active_time = datetime.now() - timedelta(minutes=20)

        result = await try_auto_fish_on_idle(USER_ID, "TestUser")

        assert result is not None
        assert result == "乡间浅溪"
        assert await db.status_is_fishing(USER_ID) is True

    async def test_auto_fish_starts_from_last_active_time(self, db):
        """防闲置自动钓鱼时，会话起始时间应回溯到上次活跃时间（收杆时刻），
        而非固定回溯15分钟——这样闲置期间无任何空档。"""
        from zhenxun.plugins.zhenxun_plugin_fishing.core import try_auto_fish_on_idle

        user = await db.user_get(USER_ID)
        user.rod_level = 5
        user.last_location_id = LOCATION_1
        idle_since = datetime.now() - timedelta(minutes=30)
        user.last_active_time = idle_since

        await try_auto_fish_on_idle(USER_ID, "TestUser")

        status = await db.status_get(USER_ID)
        start_time = datetime.fromisoformat(status["start_time"])
        # 会话起始应等于上次活跃时间，而非 now - 15分钟
        assert abs((start_time - idle_since).total_seconds()) < 5

    async def test_idle_under_threshold_no_trigger(self, db):
        """闲置未超阈值时不触发自动钓鱼。"""
        from zhenxun.plugins.zhenxun_plugin_fishing.core import try_auto_fish_on_idle

        user = await db.user_get(USER_ID)
        user.rod_level = 5
        user.last_location_id = LOCATION_1
        user.last_active_time = datetime.now() - timedelta(minutes=5)

        result = await try_auto_fish_on_idle(USER_ID, "TestUser")

        assert result is None
        assert await db.status_is_fishing(USER_ID) is False

    async def test_already_fishing_no_trigger(self, db):
        """用户正在钓鱼中时不触发防闲置。"""
        from zhenxun.plugins.zhenxun_plugin_fishing.core import try_auto_fish_on_idle

        user = await db.user_get(USER_ID)
        user.rod_level = 5
        await start_fishing(USER_ID, LOCATION_1, "TestUser")
        user.last_location_id = LOCATION_1
        user.last_active_time = datetime.now() - timedelta(minutes=20)

        result = await try_auto_fish_on_idle(USER_ID, "TestUser")

        assert result is None

    async def test_no_last_location_no_trigger(self, db):
        """无上次钓鱼地图记录时不触发。"""
        from zhenxun.plugins.zhenxun_plugin_fishing.core import try_auto_fish_on_idle

        user = await db.user_get(USER_ID)
        user.rod_level = 5
        user.last_active_time = datetime.now() - timedelta(minutes=20)

        result = await try_auto_fish_on_idle(USER_ID, "TestUser")

        assert result is None

    async def test_no_last_active_time_no_trigger(self, db):
        """无上次活跃时间记录时不触发。"""
        from zhenxun.plugins.zhenxun_plugin_fishing.core import try_auto_fish_on_idle

        user = await db.user_get(USER_ID)
        user.rod_level = 5
        user.last_location_id = LOCATION_1

        result = await try_auto_fish_on_idle(USER_ID, "TestUser")

        assert result is None

    async def test_rod_level_too_low_no_trigger(self, db):
        """鱼竿等级不足以访问上次地图时不触发。"""
        from zhenxun.plugins.zhenxun_plugin_fishing.core import try_auto_fish_on_idle

        user = await db.user_get(USER_ID)
        user.rod_level = 0
        user.last_location_id = "2"  # difficulty=1, rod_level=0 不足
        user.last_active_time = datetime.now() - timedelta(minutes=20)

        result = await try_auto_fish_on_idle(USER_ID, "TestUser")

        assert result is None
        assert await db.status_is_fishing(USER_ID) is False

    async def test_stop_fishing_records_last_location(self, db):
        """收杆后应记录上次钓鱼位置和活跃时间，供下次防闲置检测。"""
        user = await db.user_get(USER_ID)
        user.rod_level = 5
        await start_fishing(USER_ID, LOCATION_1, "TestUser")

        # start_fishing 内部已更新追踪字段
        assert user.last_location_id == LOCATION_1
        assert user.last_active_time is not None

        await stop_fishing(USER_ID, gm_mode=True)

        # 收杆后追踪字段仍保留
        assert user.last_location_id == LOCATION_1
        assert user.last_active_time is not None

    async def test_auto_fish_then_stop_settles(self, db):
        """防闲置触发自动钓鱼后，收杆能正常结算鱼获（懒计算补算）。"""
        from zhenxun.plugins.zhenxun_plugin_fishing.core import try_auto_fish_on_idle

        user = await db.user_get(USER_ID)
        user.rod_level = 5
        user.last_location_id = LOCATION_1
        user.last_active_time = datetime.now() - timedelta(minutes=20)

        # 防闲置自动开始钓鱼（回溯15分钟）
        result = await try_auto_fish_on_idle(USER_ID, "TestUser")
        assert result is not None
        assert await db.status_is_fishing(USER_ID) is True

        # 收杆应能正常结算鱼获
        render_data, buffs, ok = await stop_fishing(USER_ID, gm_mode=True)
        assert render_data is not None
        fish_list = await db.backpack_get_user_fish(USER_ID)
        assert len(fish_list) > 0
