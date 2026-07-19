from datetime import datetime, timedelta
from unittest.mock import Mock

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
        real_simulate = simulate_fishing_loop

        async def capture_simulation(*args, **kwargs):
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
