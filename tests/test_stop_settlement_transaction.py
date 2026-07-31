from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import date
from unittest.mock import AsyncMock

import pytest

from zhenxun.plugins.zhenxun_plugin_fishing.core import actions, stop_mutations
from zhenxun.plugins.zhenxun_plugin_fishing.core.context import StepResult
from zhenxun.plugins.zhenxun_plugin_fishing.core.result import add_fish_to_user
from zhenxun.plugins.zhenxun_plugin_fishing.fishing import start_fishing, stop_fishing
from zhenxun.plugins.zhenxun_plugin_fishing.models import user_mutations

USER_ID = "stop_settlement_user"
LOCATION_ID = "1"


def _step(messages=None):
    return StepResult(
        new_fish=[],
        new_bait_consumed=0,
        frame_pity=2,
        cat_frame_pity=3,
        bait=None,
        bait_remaining=0,
        utr_pity=4,
        buff_messages=list(messages or ["步进消息"]),
    )


async def _arrange_settlement(db, monkeypatch):
    user = await db.user_get(USER_ID)
    user.rod_level = 5
    await start_fishing(USER_ID, LOCATION_ID, "SettlementUser")
    status = deepcopy(await db.status_get(USER_ID))
    status.update(
        {
            "frame_pity": 2,
            "cat_frame_pity": 3,
            "utr_pity": 4,
            "cat_gifts": {
                "gold": 7,
                "cat_frames": 2,
                "corn": 3,
                "bait_id": "",
                "bait_count": 0,
            },
            "cat_eaten_fish": [],
            "meteor_fish_numbers": [],
        }
    )
    monkeypatch.setattr(
        actions,
        "_preview_daily_rewards",
        AsyncMock(return_value=(True, 1, 11, 0)),
    )
    monkeypatch.setattr(
        actions,
        "_compute_settle_step",
        AsyncMock(return_value=(_step(), status, None)),
    )
    return user


def _transaction_with_memory_rollback(user, events):
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
        else:
            events.append("transaction.commit")

    return transaction


class TestStopSettlementTransaction:
    async def test_add_fish_to_user_auto_displays_new_fish(self, db):
        user = await db.user_get(USER_ID)
        user.display_slots = 1

        result = await add_fish_to_user(
            USER_ID,
            [("小鲫鱼", "N", "111", 1)],
            check_achievements=False,
        )

        assert user.displays == {
            "1": {"fish_name": "小鲫鱼", "rarity": "N", "numeric_id": "111"}
        }
        assert any("自动展示" in message for message in result["messages"])

    async def test_add_fish_to_user_respects_auto_display_false(self, db):
        user = await db.user_get(USER_ID)
        user.display_slots = 1

        result = await add_fish_to_user(
            USER_ID,
            [("小鲫鱼", "N", "111", 1)],
            check_achievements=False,
            auto_display=False,
        )

        assert user.displays == {}
        assert user.backpack["111"]["count"] == 1
        assert not any("自动展示" in message for message in result["messages"])

    async def test_apply_add_fish_entries_respects_auto_display_false(self, db):
        user = await db.user_get(USER_ID)
        user.display_slots = 1
        dirty = set()

        result = stop_mutations.apply_add_fish_entries_on_user(
            user,
            [("小鲫鱼", "N", "111", 1)],
            dirty,
            check_achievements=False,
            auto_display=False,
        )

        assert user.displays == {}
        assert user.backpack["111"]["count"] == 1
        assert not any("自动展示" in message for message in result["messages"])

    async def test_stop_only_auto_displays_new_fish_without_scanning_history(
        self, db, monkeypatch
    ):
        user = await _arrange_settlement(db, monkeypatch)
        user.backpack = {
            "141": {"fish_name": "草鱼", "rarity": "N", "count": 1},
        }
        user.displays = {}
        user.display_slots = 1
        status = actions._compute_settle_step.return_value[1]
        status["fish_caught"] = [
            {"fish_id": "小鲫鱼", "rarity": "N", "count": 1}
        ]
        monkeypatch.setattr(
            actions,
            "_stop_db_transaction",
            _transaction_with_memory_rollback(user, []),
        )
        real_save_dirty = user_mutations.save_dirty
        save_calls = []

        async def tracked_save_dirty(saved_user, dirty):
            save_calls.append(set(dirty))
            await real_save_dirty(saved_user, dirty)

        monkeypatch.setattr(user_mutations, "save_dirty", tracked_save_dirty)

        await stop_fishing(USER_ID)

        assert user.displays == {
            "1": {"fish_name": "小鲫鱼", "rarity": "N", "numeric_id": "111"}
        }
        assert user.backpack["141"] == {
            "fish_name": "草鱼",
            "rarity": "N",
            "count": 1,
        }
        assert len(save_calls) == 1

    async def test_success_writes_full_chain_once(self, db, monkeypatch):
        user = await _arrange_settlement(db, monkeypatch)
        events = []
        monkeypatch.setattr(
            actions,
            "_stop_db_transaction",
            _transaction_with_memory_rollback(user, events),
        )
        real_save_dirty = user_mutations.save_dirty

        async def tracked_save_dirty(saved_user, dirty):
            events.append(("save", set(dirty)))
            await real_save_dirty(saved_user, dirty)

        monkeypatch.setattr(user_mutations, "save_dirty", tracked_save_dirty)

        render_data, messages, _ = await stop_fishing(USER_ID)

        assert render_data is not None
        assert user.fishing_status is None
        assert user.last_sign_date == date.today()
        assert user.gold == 18
        assert user.corn == 4
        assert user.cat_frames == 2
        assert user.frame_pity_counter == 2
        assert user.cat_frame_pity_counter == 3
        assert user.utr_pity_counter == 4
        assert user.daily_counters["stop"]["count"] == 1
        saves = [event for event in events if isinstance(event, tuple)]
        assert len(saves) == 1
        assert "fishing_status" in saves[0][1]
        assert events[-1] == "transaction.commit"
        assert messages.index("步进消息") < messages.index("🐱 猫送了7金币")
        assert messages.index("🐱 猫送了7金币") < messages.index("🐱 猫送了2个猫框")
        assert messages.index("🐱 猫送了2个猫框") < messages.index("🐱 猫送了3个玉米")

    async def test_disabled_limit_does_not_increment_stop_count(self, db, monkeypatch):
        user = await _arrange_settlement(db, monkeypatch)
        monkeypatch.setattr(
            actions,
            "_stop_db_transaction",
            _transaction_with_memory_rollback(user, []),
        )

        _, _, is_last_stop = await stop_fishing(
            USER_ID,
            is_private=False,
            limit_enabled=False,
        )

        assert user.daily_counters["stop"]["count"] == 0
        assert is_last_stop is False

    async def test_starry_score_threshold_grants_s2_ticket_once(self, db, monkeypatch):
        user = await _arrange_settlement(db, monkeypatch)
        user.starry_score_accumulated = 1200.0
        plan = actions._StopSettlementPlan(
            user_id=USER_ID,
            user=user,
            gm_mode=False,
            is_private=True,
            limit_enabled=True,
            step=_step(),
            updated_status={},
            is_new_sign=False,
            display_income=0,
            days_missed=0,
            corn_count=0,
        )

        actions._set_starry_score_info(plan, score=1.0, count=1)
        actions._set_starry_score_info(plan, score=1.0, count=1)

        assert user.s2_ticket_claimed is True
        assert "s2_ticket_claimed" in plan.dirty
        assert plan.starry_score_info["claimed"] is True
        assert plan.messages.count("🎫 星空努力值达标，已获得 S2 入场券") == 1

    async def test_mid_write_error_rolls_back_and_preserves_status(
        self, db, monkeypatch
    ):
        user = await _arrange_settlement(db, monkeypatch)
        before = deepcopy(user.__dict__)
        events = []
        monkeypatch.setattr(
            actions,
            "_stop_db_transaction",
            _transaction_with_memory_rollback(user, events),
        )

        async def failing_save_dirty(saved_user, dirty):
            events.append("save.failed")
            raise RuntimeError("injected write failure")

        monkeypatch.setattr(user_mutations, "save_dirty", failing_save_dirty)

        with pytest.raises(RuntimeError, match="injected write failure"):
            await stop_fishing(USER_ID)

        assert user.__dict__ == before
        assert user.fishing_status is not None
        assert events == ["transaction.enter", "save.failed", "transaction.rollback"]

    async def test_transaction_error_logs_original_exception_without_masking_it(
        self, db, monkeypatch
    ):
        user = await _arrange_settlement(db, monkeypatch)
        monkeypatch.setattr(
            actions,
            "_stop_db_transaction",
            _transaction_with_memory_rollback(user, []),
        )
        original = RuntimeError("original settlement failure")
        monkeypatch.setattr(
            actions,
            "_apply_stop_settlement_writes",
            AsyncMock(side_effect=original),
        )
        logged = []
        monkeypatch.setattr(
            actions.logger,
            "error",
            lambda info, **kwargs: logged.append((info, kwargs.get("e"))),
        )

        with pytest.raises(RuntimeError, match="original settlement failure"):
            await stop_fishing(USER_ID)

        assert logged == [
            (f"用户 {USER_ID} 收杆事务失败，已回滚全部数据库修改", original)
        ]

    async def test_messages_keep_domain_order_when_commit_succeeds(
        self, db, monkeypatch
    ):
        user = await _arrange_settlement(db, monkeypatch)
        monkeypatch.setattr(
            actions, "_stop_db_transaction", _transaction_with_memory_rollback(user, [])
        )

        _, messages, _ = await stop_fishing(USER_ID)

        expected = [
            "步进消息",
            "🐱 猫送了7金币",
            "🐱 猫送了2个猫框",
            "🐱 猫送了3个玉米",
        ]
        positions = [messages.index(message) for message in expected]
        assert positions == sorted(positions)

    async def test_domain_stages_share_plan_and_keep_execution_order(
        self, db, monkeypatch
    ):
        user = await _arrange_settlement(db, monkeypatch)
        events = []
        monkeypatch.setattr(
            actions,
            "_stop_db_transaction",
            _transaction_with_memory_rollback(user, events),
        )
        real_session = actions._apply_session_reward_stage
        real_pity_cat = actions._apply_pity_cat_gift_stage
        real_catch = actions._apply_catch_achievement_display_stage
        plans = []

        async def tracked_session(plan):
            plans.append(plan)
            events.append("stage.session")
            await real_session(plan)

        def tracked_pity_cat(plan):
            assert plan is plans[0]
            assert "fishing_status" in plan.dirty
            events.append("stage.pity_cat")
            real_pity_cat(plan)

        def tracked_catch(plan):
            assert plan is plans[0]
            assert plan.messages[:2] == ["步进消息", "🐱 猫送了7金币"]
            events.append("stage.catch")
            return real_catch(plan)

        monkeypatch.setattr(actions, "_apply_session_reward_stage", tracked_session)
        monkeypatch.setattr(actions, "_apply_pity_cat_gift_stage", tracked_pity_cat)
        monkeypatch.setattr(
            actions, "_apply_catch_achievement_display_stage", tracked_catch
        )

        render_data, messages, _ = await stop_fishing(USER_ID)

        assert render_data["sign_info"]["display_income"] == 11
        assert messages[:4] == [
            "步进消息",
            "🐱 猫送了7金币",
            "🐱 猫送了2个猫框",
            "🐱 猫送了3个玉米",
        ]
        assert events[:4] == [
            "transaction.enter",
            "stage.session",
            "stage.pity_cat",
            "stage.catch",
        ]
        assert events[-1] == "transaction.commit"

    async def test_stage_exception_propagates_and_rolls_back_without_save(
        self, db, monkeypatch
    ):
        user = await _arrange_settlement(db, monkeypatch)
        before = deepcopy(user.__dict__)
        events = []
        monkeypatch.setattr(
            actions,
            "_stop_db_transaction",
            _transaction_with_memory_rollback(user, events),
        )

        def failing_pity_cat(plan):
            events.append("stage.pity_cat.failed")
            raise ValueError("injected stage failure")

        monkeypatch.setattr(actions, "_apply_pity_cat_gift_stage", failing_pity_cat)
        save = AsyncMock()
        monkeypatch.setattr(user_mutations, "save_dirty", save)

        with pytest.raises(ValueError, match="injected stage failure"):
            await stop_fishing(USER_ID)

        assert user.__dict__ == before
        assert events == [
            "transaction.enter",
            "stage.pity_cat.failed",
            "transaction.rollback",
        ]
        save.assert_not_awaited()
