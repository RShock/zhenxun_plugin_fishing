"""账本系统与统一道具管理测试。

测试范围：
1. 金币服务 (spend_gold/earn_gold/adjust_gold/set_gold) — 验证金币变动与账本记录
2. GoldDelta — 事务内金币跟踪器
3. 金币对账 — 基准条目、正常对账、异常检测
4. 道具使用记录 — log_item_use + 延迟写入
5. 钓鱼会话记录 — log_fishing_session
6. 统一道具注册表 — 标量/JSON 道具的增删查
"""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# In-memory ledger mock
# ═══════════════════════════════════════════════════════════════════════════════


class _LedgerEntry:
    """Mock FishingLedger row."""

    def __init__(self, id, **kwargs):
        self.id = id
        for k, v in kwargs.items():
            setattr(self, k, v)


class InMemoryLedger:
    """模拟 FishingLedger 的内存存储，支持 create + 对账查询。"""

    def __init__(self):
        self.entries: list[_LedgerEntry] = []
        self._next_id = 1

    def reset(self):
        self.entries.clear()
        self._next_id = 1

    async def create(self, **kwargs):
        entry = _LedgerEntry(self._next_id, **kwargs)
        self.entries.append(entry)
        self._next_id += 1
        return entry

    async def has_gold_entries(self, user_id):
        return any(
            e.user_id == user_id and e.entry_type == "gold" for e in self.entries
        )

    async def get_last_gold_entry(self, user_id):
        gold_entries = [
            e for e in self.entries
            if e.user_id == user_id and e.entry_type == "gold"
        ]
        if not gold_entries:
            return None
        return gold_entries[-1]

    def gold_entries(self, user_id):
        return [
            e for e in self.entries
            if e.user_id == user_id and e.entry_type == "gold"
        ]

    def item_use_entries(self, user_id):
        return [
            e for e in self.entries
            if e.user_id == user_id and e.entry_type == "item_use"
        ]

    def fishing_entries(self, user_id):
        return [
            e for e in self.entries
            if e.user_id == user_id and e.entry_type == "fishing"
        ]


@pytest.fixture
def ledger(db, monkeypatch):
    """设置内存账本 mock，替换 FishingLedger 的 create/has_gold_entries/get_last_gold_entry。"""
    from zhenxun.plugins.zhenxun_plugin_fishing.models import FishingLedger
    from zhenxun.plugins.zhenxun_plugin_fishing.services import ledger_service

    mem = InMemoryLedger()
    ledger_service._pending_entries.clear()

    monkeypatch.setattr(FishingLedger, "create", mem.create)
    monkeypatch.setattr(FishingLedger, "has_gold_entries", mem.has_gold_entries)
    monkeypatch.setattr(FishingLedger, "get_last_gold_entry", mem.get_last_gold_entry)

    yield mem

    ledger_service._pending_entries.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# 1. 金币服务测试
# ═══════════════════════════════════════════════════════════════════════════════


async def test_gold_transaction_reuses_same_task_scope(monkeypatch):
    from tortoise import Tortoise, transactions

    from zhenxun.plugins.zhenxun_plugin_fishing.services.gold_service import (
        _gold_transaction,
    )

    connection = object()
    enter_count = 0

    @asynccontextmanager
    async def fake_in_transaction():
        nonlocal enter_count
        enter_count += 1
        yield connection

    monkeypatch.setattr(Tortoise, "_inited", True)
    monkeypatch.setattr(transactions, "in_transaction", fake_in_transaction)

    async with _gold_transaction() as outer:
        async with _gold_transaction() as inner:
            assert outer is connection
            assert inner is outer

    assert enter_count == 1


async def test_gold_transaction_does_not_reuse_scope_in_child_task(monkeypatch):
    from tortoise import Tortoise, transactions

    from zhenxun.plugins.zhenxun_plugin_fishing.services.gold_service import (
        _gold_transaction,
    )

    enter_count = 0

    @asynccontextmanager
    async def fake_in_transaction():
        nonlocal enter_count
        enter_count += 1
        yield object()

    monkeypatch.setattr(Tortoise, "_inited", True)
    monkeypatch.setattr(transactions, "in_transaction", fake_in_transaction)

    async def child_transaction():
        async with _gold_transaction():
            pass

    async with _gold_transaction():
        await asyncio.create_task(child_transaction())

    assert enter_count == 2


async def test_gold_transaction_propagates_business_exception(monkeypatch):
    from tortoise import Tortoise, transactions

    from zhenxun.plugins.zhenxun_plugin_fishing.services.gold_service import (
        _gold_transaction,
    )

    @asynccontextmanager
    async def fake_in_transaction():
        yield object()

    monkeypatch.setattr(Tortoise, "_inited", True)
    monkeypatch.setattr(transactions, "in_transaction", fake_in_transaction)

    with pytest.raises(ValueError, match="rollback me"):
        async with _gold_transaction():
            raise ValueError("rollback me")


class TestGoldService:
    """测试 spend_gold / earn_gold / adjust_gold / set_gold。"""

    async def test_spend_gold_success(self, db, ledger):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import spend_gold

        user_id = "test_spend"
        await db.user_get_or_create(user_id)
        db._users[user_id].gold = 1000

        ok = await spend_gold(user_id, 300, "buy_bait", "购买鱼饵")
        assert ok is True
        assert db._users[user_id].gold == 700

        gold_entries = ledger.gold_entries(user_id)
        assert len(gold_entries) == 1
        entry = gold_entries[0]
        assert entry.gold_before == 1000
        assert entry.gold_after == 700
        assert entry.is_baseline is True
        assert entry.gold_anomaly is False
        assert entry.data["operation"] == "buy_bait"
        assert entry.data["amount"] == -300
        assert entry.data["direction"] == "expense"
        assert entry.data["category"] == "supplies"
        assert entry.data["category_label"] == "购买消耗品"

    async def test_spend_gold_insufficient(self, db, ledger):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import spend_gold

        user_id = "test_spend_fail"
        await db.user_get_or_create(user_id)
        db._users[user_id].gold = 50

        ok = await spend_gold(user_id, 300, "buy_bait")
        assert ok is False
        assert db._users[user_id].gold == 50
        assert len(ledger.gold_entries(user_id)) == 0

    async def test_spend_gold_zero_amount(self, db, ledger):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import spend_gold

        user_id = "test_spend_zero"
        await db.user_get_or_create(user_id)
        db._users[user_id].gold = 100

        ok = await spend_gold(user_id, 0, "free")
        assert ok is True
        assert db._users[user_id].gold == 100
        assert len(ledger.gold_entries(user_id)) == 0

    async def test_earn_gold_success(self, db, ledger):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import earn_gold

        user_id = "test_earn"
        await db.user_get_or_create(user_id)
        db._users[user_id].gold = 500

        await earn_gold(user_id, 200, "sell_fish", "卖鱼收入")
        assert db._users[user_id].gold == 700

        entries = ledger.gold_entries(user_id)
        assert len(entries) == 1
        assert entries[0].gold_before == 500
        assert entries[0].gold_after == 700
        assert entries[0].data["amount"] == 200
        assert entries[0].data["operation"] == "sell_fish"
        assert entries[0].data["direction"] == "income"
        assert entries[0].data["category"] == "sale"
        assert entries[0].data["category_label"] == "出售物品"

    async def test_unknown_operation_uses_direction_fallback(self, db, ledger):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import earn_gold

        user_id = "test_unknown_category"
        await db.user_get_or_create(user_id)
        await earn_gold(user_id, 50, "future_income")

        entry = ledger.gold_entries(user_id)[0]
        assert entry.data["direction"] == "income"
        assert entry.data["category"] == "other_income"
        assert entry.data["category_label"] == "其他收入"

    async def test_adjust_gold_positive(self, db, ledger):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import adjust_gold

        user_id = "test_adjust_pos"
        await db.user_get_or_create(user_id)
        db._users[user_id].gold = 100

        await adjust_gold(user_id, 50, "gm_add", "GM充值")
        assert db._users[user_id].gold == 150

        entries = ledger.gold_entries(user_id)
        assert len(entries) == 1
        assert entries[0].data["amount"] == 50

    async def test_adjust_gold_negative(self, db, ledger):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import adjust_gold

        user_id = "test_adjust_neg"
        await db.user_get_or_create(user_id)
        db._users[user_id].gold = 100

        await adjust_gold(user_id, -30, "gm_deduct", "GM扣除")
        assert db._users[user_id].gold == 70

        entries = ledger.gold_entries(user_id)
        assert len(entries) == 1
        assert entries[0].data["amount"] == -30

    async def test_adjust_gold_zero_skipped(self, db, ledger):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import adjust_gold

        user_id = "test_adjust_zero"
        await db.user_get_or_create(user_id)
        db._users[user_id].gold = 100

        await adjust_gold(user_id, 0, "noop")
        assert db._users[user_id].gold == 100
        assert len(ledger.gold_entries(user_id)) == 0

    async def test_set_gold(self, db, ledger):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import set_gold

        user_id = "test_set"
        await db.user_get_or_create(user_id)
        db._users[user_id].gold = 500

        await set_gold(user_id, 1000, "gm_set", "GM设置金币")
        assert db._users[user_id].gold == 1000

        entries = ledger.gold_entries(user_id)
        assert len(entries) == 1
        assert entries[0].gold_before == 500
        assert entries[0].gold_after == 1000
        assert entries[0].data["amount"] == 500


# ═══════════════════════════════════════════════════════════════════════════════
# 2. GoldDelta 测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestGoldDelta:
    """测试 GoldDelta 事务内金币跟踪器。"""

    async def test_delta_commit_positive(self, db, ledger):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import GoldDelta

        user_id = "test_delta_pos"
        await db.user_get_or_create(user_id)
        db._users[user_id].gold = 100

        delta = GoldDelta(user_id, gold_before=100)
        delta.set_after(250)
        await delta.commit("fishing_income", "收杆收益")

        entries = ledger.gold_entries(user_id)
        assert len(entries) == 1
        assert entries[0].gold_before == 100
        assert entries[0].gold_after == 250
        assert entries[0].data["amount"] == 150

    async def test_delta_commit_negative(self, db, ledger):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import GoldDelta

        user_id = "test_delta_neg"
        await db.user_get_or_create(user_id)

        delta = GoldDelta(user_id, gold_before=500)
        delta.set_after(300)
        await delta.commit("cost", "消耗")

        entries = ledger.gold_entries(user_id)
        assert len(entries) == 1
        assert entries[0].data["amount"] == -200

    async def test_delta_commit_zero_skipped(self, db, ledger):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import GoldDelta

        user_id = "test_delta_zero"
        await db.user_get_or_create(user_id)

        delta = GoldDelta(user_id, gold_before=100)
        delta.set_after(100)
        result = await delta.commit("noop")

        assert result is False
        assert len(ledger.gold_entries(user_id)) == 0

    async def test_delta_commit_without_set_after(self, db, ledger):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import GoldDelta

        user_id = "test_delta_no_after"
        await db.user_get_or_create(user_id)

        delta = GoldDelta(user_id, gold_before=100)
        result = await delta.commit("noop")
        assert result is False

    async def test_delta_add_item_records_details(self, db, ledger):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import GoldDelta

        user_id = "test_delta_items"
        await db.user_get_or_create(user_id)

        delta = GoldDelta(user_id, gold_before=100)
        delta.add_item("display_income", 50, "展示收益")
        delta.add_item("cat_gift", 30, "猫礼物")
        delta.set_after(180)
        await delta.commit("fishing_income", "收杆汇总")

        entries = ledger.gold_entries(user_id)
        assert len(entries) == 1
        items = entries[0].data["details"]["items"]
        assert len(items) == 2
        assert items[0]["operation"] == "display_income"
        assert items[0]["amount"] == 50
        assert items[1]["operation"] == "cat_gift"

    async def test_delta_total_delta_property(self, db, ledger):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import GoldDelta

        delta = GoldDelta("x", gold_before=200)
        assert delta.total_delta == 0  # gold_after is None

        delta.set_after(350)
        assert delta.total_delta == 150

        delta.set_after(50)
        assert delta.total_delta == -150


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 金币对账测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestGoldReconciliation:
    """测试金币对账逻辑：基准条目、正常推导、异常检测。"""

    async def test_first_entry_is_baseline(self, db, ledger):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import earn_gold

        user_id = "test_baseline"
        await db.user_get_or_create(user_id)
        db._users[user_id].gold = 0

        await earn_gold(user_id, 100, "initial", "初始金币")
        entries = ledger.gold_entries(user_id)
        assert len(entries) == 1
        assert entries[0].is_baseline is True
        assert entries[0].gold_anomaly is False
        assert entries[0].gold_expected is None

    async def test_normal_reconciliation_no_anomaly(self, db, ledger):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import earn_gold, spend_gold

        user_id = "test_reconcile_normal"
        await db.user_get_or_create(user_id)
        db._users[user_id].gold = 0

        # 第一笔：基准
        await earn_gold(user_id, 500, "earn1")
        assert ledger.gold_entries(user_id)[-1].is_baseline is True

        # 第二笔：正常推导
        # expected = 500 + 100 = 600, actual = 600 → 无异常
        db._users[user_id].gold = 500  # 重置为前一条 gold_after
        await earn_gold(user_id, 100, "earn2")
        entries = ledger.gold_entries(user_id)
        assert len(entries) == 2
        assert entries[1].is_baseline is False
        assert entries[1].gold_expected == 600
        assert entries[1].gold_after == 600
        assert entries[1].gold_anomaly is False

    async def test_anomaly_detected_when_mismatch(self, db, ledger):
        """金币实际值与推导值不匹配时标记异常。"""
        from zhenxun.plugins.zhenxun_plugin_fishing.services import (
            GoldDelta,
            ledger_service,
        )

        user_id = "test_anomaly"
        await db.user_get_or_create(user_id)
        db._users[user_id].gold = 0

        # 基准条目：gold_after = 500
        await ledger_service.log_gold_change(
            user_id, operation="base", amount=500,
            gold_before=0, gold_after=500,
        )
        assert ledger.gold_entries(user_id)[-1].is_baseline is True

        # 异常条目：expected = 500 + 200 = 700, actual = 800 → 异常
        is_anomaly = await ledger_service.log_gold_change(
            user_id, operation="cheat", amount=200,
            gold_before=500, gold_after=800,
        )
        assert is_anomaly is True

        entries = ledger.gold_entries(user_id)
        assert len(entries) == 2
        assert entries[1].gold_expected == 700
        assert entries[1].gold_after == 800
        assert entries[1].gold_anomaly is True

    async def test_multiple_normal_entries_chain(self, db, ledger):
        """连续多笔正常交易，每笔从前一笔推导。"""
        from zhenxun.plugins.zhenxun_plugin_fishing.services import (
            earn_gold,
            spend_gold,
        )

        user_id = "test_chain"
        await db.user_get_or_create(user_id)
        db._users[user_id].gold = 0

        # 基准
        await earn_gold(user_id, 1000, "earn1")

        # 正常花费
        db._users[user_id].gold = 1000
        await spend_gold(user_id, 300, "spend1")

        # 正常收入
        db._users[user_id].gold = 700
        await earn_gold(user_id, 200, "earn2")

        # 正常花费
        db._users[user_id].gold = 900
        await spend_gold(user_id, 150, "spend2")

        entries = ledger.gold_entries(user_id)
        assert len(entries) == 4

        # 每笔都从前一笔推导
        assert entries[0].is_baseline is True
        for i in range(1, 4):
            assert entries[i].is_baseline is False
            expected = entries[i - 1].gold_after + entries[i].data["amount"]
            assert entries[i].gold_expected == expected
            assert entries[i].gold_anomaly is False


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 道具使用记录测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestItemUseLogging:
    """测试 log_item_use + 延迟写入。"""

    async def test_log_item_use_immediate(self, db, ledger):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import ledger_service

        user_id = "test_item_use"
        await db.user_get_or_create(user_id)

        await ledger_service.log_item_use(
            user_id,
            item_id="lucky_potion",
            item_type="potion",
            item_name="幸运药水",
            count=1,
            context="use_lucky_potion",
        )

        entries = ledger.item_use_entries(user_id)
        assert len(entries) == 1
        data = entries[0].data
        assert data["item_id"] == "lucky_potion"
        assert data["item_type"] == "potion"
        assert data["item_name"] == "幸运药水"
        assert data["count"] == 1
        assert data["context"] == "use_lucky_potion"
        assert "timestamp" in data

    async def test_log_item_use_deferred_then_flush(self, db, ledger):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import ledger_service

        user_id = "test_item_deferred"
        await db.user_get_or_create(user_id)

        # 延迟写入3条
        for i in range(3):
            await ledger_service.log_item_use(
                user_id,
                item_id=f"potion_{i}",
                item_type="potion",
                item_name=f"药水{i}",
                count=1,
                context="test",
                deferred=True,
            )

        # flush 前队列为空
        assert len(ledger.item_use_entries(user_id)) == 0

        # flush 后全部写入
        count = await ledger_service.flush_pending_entries()
        assert count == 3
        assert len(ledger.item_use_entries(user_id)) == 3

    async def test_log_item_use_multiple_counts(self, db, ledger):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import ledger_service

        user_id = "test_item_count"
        await db.user_get_or_create(user_id)

        await ledger_service.log_item_use(
            user_id,
            item_id="corn",
            item_type="corn",
            item_name="香甜玉米",
            count=5,
            context="do_nest",
        )

        entries = ledger.item_use_entries(user_id)
        assert len(entries) == 1
        assert entries[0].data["count"] == 5

    async def test_flush_empty_queue(self, db, ledger):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import ledger_service

        count = await ledger_service.flush_pending_entries()
        assert count == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 5. 钓鱼会话记录测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestFishingSessionLogging:
    """测试 log_fishing_session。"""

    async def test_log_fishing_session_basic(self, db, ledger):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import ledger_service

        user_id = "test_session"
        await db.user_get_or_create(user_id)

        fish_caught = [
            {"name": "鲫鱼", "rarity": "N", "count": 3},
            {"name": "鲤鱼", "rarity": "R", "count": 1},
        ]
        items_gained = [
            {"item_id": "corn", "item_type": "corn", "count": 1, "source": "sign_in"},
        ]

        await ledger_service.log_fishing_session(
            user_id,
            location_id="1",
            location_name="小溪",
            rod_level=5,
            hook_level=3,
            bait_id="0",
            bait_name="蚯蚓",
            start_time="2026-01-01T10:00:00",
            end_time="2026-01-01T10:30:00",
            duration_minutes=30,
            weather="晴天",
            fish_caught=fish_caught,
            items_gained=items_gained,
            starry_score=0.0,
            starry_fish_count=0,
            gold_earned=150,
            auto_sold=False,
            bait_consumed=30,
            gold_before=500,
            gold_after=650,
        )

        entries = ledger.fishing_entries(user_id)
        assert len(entries) == 1
        data = entries[0].data

        assert data["location_id"] == "1"
        assert data["location_name"] == "小溪"
        assert data["rod_level"] == 5
        assert data["hook_level"] == 3
        assert data["bait_name"] == "蚯蚓"
        assert data["duration_minutes"] == 30
        assert data["weather"] == "晴天"
        assert len(data["fish_caught"]) == 2
        assert data["fish_caught"][0]["name"] == "鲫鱼"
        assert data["fish_caught"][1]["rarity"] == "R"
        assert len(data["items_gained"]) == 1
        assert data["gold_earned"] == 150
        assert data["auto_sold"] is False
        assert data["bait_consumed"] == 30
        assert data["gold_before"] == 500
        assert data["gold_after"] == 650

    async def test_log_fishing_session_deferred(self, db, ledger):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import ledger_service

        user_id = "test_session_deferred"
        await db.user_get_or_create(user_id)

        await ledger_service.log_fishing_session(
            user_id,
            location_id="2",
            location_name="湖泊",
            rod_level=1,
            deferred=True,
        )

        assert len(ledger.fishing_entries(user_id)) == 0

        count = await ledger_service.flush_pending_entries()
        assert count == 1

        entries = ledger.fishing_entries(user_id)
        assert len(entries) == 1
        assert entries[0].data["location_name"] == "湖泊"

    async def test_log_fishing_session_with_starry_data(self, db, ledger):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import ledger_service

        user_id = "test_session_starry"
        await db.user_get_or_create(user_id)

        await ledger_service.log_fishing_session(
            user_id,
            location_id="11",
            location_name="星云",
            rod_level=15,
            starry_score=12.5,
            starry_fish_count=3,
            gold_earned=0,
            auto_sold=True,
            miracle={"triggered": True, "consumed": 9999999999},
        )

        entries = ledger.fishing_entries(user_id)
        data = entries[0].data
        assert data["starry_score"] == 12.5
        assert data["starry_fish_count"] == 3
        assert data["auto_sold"] is True
        assert data["miracle"]["triggered"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# 6. 统一道具注册表测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestItemRegistryScalar:
    """测试标量道具（玉米、木框、猫框、星空框）的统一管理。"""

    async def test_add_corn(self, db):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import add_item, ItemType

        user_id = "test_add_corn"
        await db.user_get_or_create(user_id)
        db._users[user_id].corn = 5

        await add_item(user_id, "corn", ItemType.CORN, 3)
        assert db._users[user_id].corn == 8

    async def test_remove_corn_success(self, db):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import (
            remove_item,
            ItemType,
        )

        user_id = "test_remove_corn"
        await db.user_get_or_create(user_id)
        db._users[user_id].corn = 10

        ok = await remove_item(user_id, "corn", ItemType.CORN, 4)
        assert ok is True
        assert db._users[user_id].corn == 6

    async def test_remove_corn_insufficient(self, db):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import (
            remove_item,
            ItemType,
        )

        user_id = "test_remove_corn_fail"
        await db.user_get_or_create(user_id)
        db._users[user_id].corn = 2

        ok = await remove_item(user_id, "corn", ItemType.CORN, 5)
        assert ok is False
        assert db._users[user_id].corn == 2

    async def test_add_display_frames(self, db):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import (
            add_item,
            ItemType,
        )

        user_id = "test_add_frames"
        await db.user_get_or_create(user_id)
        db._users[user_id].display_frames = 0

        await add_item(user_id, "display_frame", ItemType.DISPLAY_FRAME, 2)
        assert db._users[user_id].display_frames == 2

    async def test_add_cat_frames(self, db):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import (
            add_item,
            ItemType,
        )

        user_id = "test_add_cat"
        await db.user_get_or_create(user_id)
        db._users[user_id].cat_frames = 1

        await add_item(user_id, "cat_frame", ItemType.CAT_FRAME, 3)
        assert db._users[user_id].cat_frames == 4

    async def test_add_star_frames(self, db):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import (
            add_item,
            ItemType,
        )

        user_id = "test_add_star"
        await db.user_get_or_create(user_id)
        db._users[user_id].star_frames = 0

        await add_item(user_id, "star_frame", ItemType.STAR_FRAME, 5)
        assert db._users[user_id].star_frames == 5

    async def test_get_item_scalar(self, db):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import (
            get_item,
            ItemType,
        )

        user_id = "test_get_scalar"
        await db.user_get_or_create(user_id)
        db._users[user_id].corn = 7

        item = await get_item(user_id, "corn", ItemType.CORN)
        assert item is not None
        assert item["count"] == 7
        assert item["item_type"] == ItemType.CORN

    async def test_get_item_scalar_zero(self, db):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import (
            get_item,
            ItemType,
        )

        user_id = "test_get_scalar_zero"
        await db.user_get_or_create(user_id)
        db._users[user_id].corn = 0

        item = await get_item(user_id, "corn", ItemType.CORN)
        assert item is None

    async def test_add_zero_count_noop(self, db):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import (
            add_item,
            ItemType,
        )

        user_id = "test_add_zero"
        await db.user_get_or_create(user_id)
        db._users[user_id].corn = 5

        await add_item(user_id, "corn", ItemType.CORN, 0)
        assert db._users[user_id].corn == 5

    async def test_remove_zero_count_returns_true(self, db):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import (
            remove_item,
            ItemType,
        )

        user_id = "test_remove_zero"
        await db.user_get_or_create(user_id)
        db._users[user_id].corn = 5

        ok = await remove_item(user_id, "corn", ItemType.CORN, 0)
        assert ok is True
        assert db._users[user_id].corn == 5


class TestItemRegistryJSON:
    """测试 JSON 存储道具（药水、鱼饵）的统一管理。"""

    async def test_add_potion(self, db):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import (
            add_item,
            get_item,
            ItemType,
        )

        user_id = "test_add_potion"
        await db.user_get_or_create(user_id)

        await add_item(user_id, "lucky_potion", ItemType.POTION, 2)
        item = await get_item(user_id, "lucky_potion", ItemType.POTION)
        assert item is not None
        assert item["count"] == 2

    async def test_add_potion_accumulate(self, db):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import (
            add_item,
            get_item,
            ItemType,
        )

        user_id = "test_potion_acc"
        await db.user_get_or_create(user_id)

        await add_item(user_id, "time_potion", ItemType.POTION, 1)
        await add_item(user_id, "time_potion", ItemType.POTION, 3)
        item = await get_item(user_id, "time_potion", ItemType.POTION)
        assert item["count"] == 4

    async def test_remove_potion_success(self, db):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import (
            add_item,
            remove_item,
            get_item,
            ItemType,
        )

        user_id = "test_remove_potion"
        await db.user_get_or_create(user_id)

        await add_item(user_id, "lucky_potion", ItemType.POTION, 3)
        ok = await remove_item(user_id, "lucky_potion", ItemType.POTION, 2)
        assert ok is True

        item = await get_item(user_id, "lucky_potion", ItemType.POTION)
        assert item["count"] == 1

    async def test_remove_potion_insufficient(self, db):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import (
            add_item,
            remove_item,
            ItemType,
        )

        user_id = "test_remove_potion_fail"
        await db.user_get_or_create(user_id)

        await add_item(user_id, "lucky_potion", ItemType.POTION, 1)
        ok = await remove_item(user_id, "lucky_potion", ItemType.POTION, 5)
        assert ok is False

    async def test_add_bait(self, db):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import (
            add_item,
            get_item,
            ItemType,
        )

        user_id = "test_add_bait"
        await db.user_get_or_create(user_id)

        await add_item(user_id, "0", ItemType.BAIT, 50)
        item = await get_item(user_id, "0", ItemType.BAIT)
        assert item is not None
        assert item["count"] == 50


class TestItemRegistryDirty:
    """测试脏模式操作（内存修改，不 save）。"""

    def test_apply_add_corn_dirty(self, db):
        from zhenxun.plugins.zhenxun_plugin_fishing.services.item_registry import (
            apply_add_item,
            ItemType,
        )

        user_id = "test_dirty_corn"
        # 同步创建 user 对象用于脏模式测试
        from zhenxun.plugins.zhenxun_plugin_fishing.tests.mock_db import InMemoryUser

        user = InMemoryUser(user_id)
        user.corn = 5

        dirty: set[str] = set()
        apply_add_item(user, "corn", ItemType.CORN, 3, dirty)
        assert user.corn == 8
        assert "corn" in dirty

    def test_apply_remove_corn_dirty(self, db):
        from zhenxun.plugins.zhenxun_plugin_fishing.services.item_registry import (
            apply_remove_item,
            ItemType,
        )
        from zhenxun.plugins.zhenxun_plugin_fishing.tests.mock_db import InMemoryUser

        user = InMemoryUser("test_dirty_remove")
        user.corn = 10

        dirty: set[str] = set()
        ok = apply_remove_item(user, "corn", ItemType.CORN, 4, dirty)
        assert ok is True
        assert user.corn == 6
        assert "corn" in dirty

    def test_apply_remove_corn_insufficient(self, db):
        from zhenxun.plugins.zhenxun_plugin_fishing.services.item_registry import (
            apply_remove_item,
            ItemType,
        )
        from zhenxun.plugins.zhenxun_plugin_fishing.tests.mock_db import InMemoryUser

        user = InMemoryUser("test_dirty_remove_fail")
        user.corn = 2

        dirty: set[str] = set()
        ok = apply_remove_item(user, "corn", ItemType.CORN, 5, dirty)
        assert ok is False
        assert user.corn == 2
        assert "corn" not in dirty

    def test_apply_add_potion_dirty(self, db):
        from zhenxun.plugins.zhenxun_plugin_fishing.services.item_registry import (
            apply_add_item,
            get_item_on_user,
            ItemType,
        )
        from zhenxun.plugins.zhenxun_plugin_fishing.tests.mock_db import InMemoryUser

        user = InMemoryUser("test_dirty_potion")

        dirty: set[str] = set()
        apply_add_item(user, "lucky_potion", ItemType.POTION, 2, dirty)
        assert "items" in dirty

        item = get_item_on_user(user, "lucky_potion", ItemType.POTION)
        assert item is not None
        assert item["count"] == 2


class TestItemRegistryGetAll:
    """测试 get_all_items 统一查询。"""

    async def test_get_all_items_mixed(self, db):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import (
            add_item,
            get_all_items,
            ItemType,
        )

        user_id = "test_get_all"
        await db.user_get_or_create(user_id)
        db._users[user_id].corn = 5
        db._users[user_id].cat_frames = 2
        db._users[user_id].display_frames = 0  # 不应出现
        db._users[user_id].star_frames = 1

        await add_item(user_id, "lucky_potion", ItemType.POTION, 3)
        await add_item(user_id, "0", ItemType.BAIT, 50)

        items = await get_all_items(user_id)

        # 应包含 5 种道具：corn, cat_frame, star_frame, lucky_potion, bait
        # display_frames=0 不应出现
        types = {i["item_type"] for i in items}
        assert ItemType.CORN in types
        assert ItemType.CAT_FRAME in types
        assert ItemType.STAR_FRAME in types
        assert ItemType.POTION in types
        assert ItemType.BAIT in types
        assert ItemType.DISPLAY_FRAME not in types

        # 验证数量
        counts = {i["item_type"]: i["count"] for i in items}
        assert counts[ItemType.CORN] == 5
        assert counts[ItemType.CAT_FRAME] == 2
        assert counts[ItemType.STAR_FRAME] == 1
        assert counts[ItemType.POTION] == 3
        assert counts[ItemType.BAIT] == 50

    async def test_get_all_items_empty(self, db):
        from zhenxun.plugins.zhenxun_plugin_fishing.services import get_all_items

        user_id = "test_get_all_empty"
        await db.user_get_or_create(user_id)

        items = await get_all_items(user_id)
        assert items == []


class TestItemRegistryHelpers:
    """测试辅助函数。"""

    def test_is_scalar_item(self):
        from zhenxun.plugins.zhenxun_plugin_fishing.services.item_registry import (
            is_scalar_item,
            ItemType,
        )

        assert is_scalar_item(ItemType.CORN) is True
        assert is_scalar_item(ItemType.DISPLAY_FRAME) is True
        assert is_scalar_item(ItemType.CAT_FRAME) is True
        assert is_scalar_item(ItemType.STAR_FRAME) is True
        assert is_scalar_item(ItemType.POTION) is False
        assert is_scalar_item(ItemType.BAIT) is False

    def test_get_display_name_scalar(self):
        from zhenxun.plugins.zhenxun_plugin_fishing.services.item_registry import (
            get_display_name,
            ItemType,
        )

        assert get_display_name("corn", ItemType.CORN) == "香甜玉米"
        assert get_display_name("x", ItemType.DISPLAY_FRAME) == "木框"
        assert get_display_name("x", ItemType.CAT_FRAME) == "猫框"
        assert get_display_name("x", ItemType.STAR_FRAME) == "星空框"
