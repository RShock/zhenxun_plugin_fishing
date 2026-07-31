"""时光药水结算性能重构的回归与性能测试。

验证 simulate_fishing_loop 的分段缓存机制：
- 时光药水模式下效果只计算一次（buff 冻结）
- 循环内不重复查询猫乐园数据库
- 大额时间余额能快速完成（旧实现 500 瓶需 3 分钟）
- 分段按 buff 边界正确切分
"""

import time
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from zhenxun.plugins.zhenxun_plugin_fishing.config import ConfigManager
from zhenxun.plugins.zhenxun_plugin_fishing.core import engine
from zhenxun.plugins.zhenxun_plugin_fishing.core.context import FishingContext

USER_ID = "perf-test-user"
LOCATION_1 = "1"


async def _make_ctx(db, duration_minutes=0, buffs=None, bait_remaining=0):
    user = await db.user_get(USER_ID)
    user.rod_level = 5
    user.hook_level = 3
    location = ConfigManager.get_location(LOCATION_1)
    now = datetime(2026, 7, 19, 12, 0, 0)
    return FishingContext(
        user=user,
        user_id=USER_ID,
        location=location,
        buffs=buffs or [],
        bait=None,
        bait_speed_bonus=0,
        bait_remaining=bait_remaining,
        settle_start=now - timedelta(minutes=duration_minutes),
        now=now,
    )


def _fake_buff(start, end, value=10, buff_type="unknown_type"):
    """构造轻量 buff 对象用于分段测试（buff_type 未知会被效果计算跳过）。"""
    return SimpleNamespace(
        buff_type=buff_type,
        start_time=start,
        end_time=end,
        value=value,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 分段构建正确性
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_freeze_buff_mode_builds_single_segment(db, monkeypatch):
    """时光药水模式（freeze_buff_time 固定）应只构建 1 段，效果只算 1 次。"""
    ctx = await _make_ctx(db)
    freeze = ctx.now
    call_count = 0
    real_compute = engine._compute_base_effects

    def counting_compute(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return real_compute(*args, **kwargs)

    monkeypatch.setattr(engine, "_compute_base_effects", counting_compute)
    segments = engine._build_effect_segments(ctx, freeze, None)

    assert len(segments) == 1
    assert segments[0].end is None
    assert call_count == 1


@pytest.mark.asyncio
async def test_normal_mode_splits_at_buff_boundaries(db):
    """正常模式应按 buff 的 start/end 切分效果段。"""
    now = datetime(2026, 7, 19, 12, 0, 0)
    buff = _fake_buff(
        start=now - timedelta(minutes=8),
        end=now - timedelta(minutes=3),
    )
    ctx = await _make_ctx(db, duration_minutes=10, buffs=[buff])
    segments = engine._build_effect_segments(ctx, None, None)
    # 断点：settle_start, buff.start, buff.end, now → 3 段
    assert len(segments) == 3
    assert segments[0].start < segments[0].end <= segments[1].start
    assert segments[1].end <= segments[2].start < segments[2].end


@pytest.mark.asyncio
async def test_no_pending_time_builds_placeholder_segment(db):
    """settle_start == now（无待结算时间）时应构建 1 个占位段，避免空段越界。"""
    ctx = await _make_ctx(db, duration_minutes=0)
    segments = engine._build_effect_segments(ctx, None, None)
    assert len(segments) == 1
    assert segments[0].end is None


# ═══════════════════════════════════════════════════════════════════════════════
# 循环内零 DB 查询
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cat_park_state_queried_once_not_per_step(db, monkeypatch):
    """猫乐园地点：循环内不得重复查询建筑状态，预加载只发生 1 次。

    旧实现每步调用 get_cat_park_state（2 次 DB 查询），500 瓶药水 = 数十万次
    DB 查询；新实现循环前预加载 1 次，循环内零 DB 查询。
    """
    ctx = await _make_ctx(db)
    monkeypatch.setattr(
        "zhenxun.plugins.zhenxun_plugin_fishing.cat_park.is_cat_park_location",
        lambda loc_id: True,
    )
    state_calls = 0

    async def counting_state(user_id):
        nonlocal state_calls
        state_calls += 1
        return {"buildings": {}}

    monkeypatch.setattr(
        "zhenxun.plugins.zhenxun_plugin_fishing.cat_park.get_cat_park_state",
        counting_state,
    )
    monkeypatch.setattr(
        "zhenxun.plugins.zhenxun_plugin_fishing.cat_park.get_cat_park_effect_values",
        lambda state: {"cat_park_speed_multiplier": 1.0},
    )
    monkeypatch.setattr(engine, "_calculate_fishing_interval", lambda *_: 5.0)
    # mock 捕获：不产鱼，仅推进 frame_pity/utr_pity
    monkeypatch.setattr(
        engine, "_catch_fish_at_interval", lambda *a, **k: (a[3], a[5])
    )

    # 12 分钟 / 5 分钟间隔 = 2 步 + 1 次预加载
    await engine.simulate_fishing_loop(ctx, time_credit_minutes=12)
    assert state_calls == 1, f"猫乐园状态应只查询1次，实际{state_calls}次"


# ═══════════════════════════════════════════════════════════════════════════════
# 性能：大额时间余额快速完成
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_large_time_credit_completes_fast(db, monkeypatch):
    """500 瓶药水等效时间余额（240000 分钟）应在数秒内完成。

    旧实现因每步 DB 查询需约 3 分钟；重构后循环内零 DB 查询、零 buff 重算。
    """
    ctx = await _make_ctx(db)
    monkeypatch.setattr(engine, "_calculate_fishing_interval", lambda *_: 1.0)
    monkeypatch.setattr(
        engine, "_catch_fish_at_interval", lambda *a, **k: (a[3], a[5])
    )

    start = time.monotonic()
    # 500 瓶 × 8 小时 × 60 分钟 = 240000 分钟，间隔 1 分钟 → 240000 步
    await engine.simulate_fishing_loop(ctx, time_credit_minutes=240000)
    elapsed = time.monotonic() - start

    assert elapsed < 10.0, f"240000 步耗时 {elapsed:.2f}s，应 < 10s（旧实现约 180s）"


@pytest.mark.asyncio
async def test_freeze_mode_reuses_effects_across_steps(db, monkeypatch):
    """时光药水模式下 effects 只计算 1 次，后续步骤直接复用。

    通过计数 _merge_bait_speed 调用次数验证：bait 速度不变时只算 1 次。
    """
    ctx = await _make_ctx(db)
    freeze = ctx.now
    merge_calls = 0
    real_merge = engine._merge_bait_speed

    def counting_merge(c, base, speed):
        nonlocal merge_calls
        merge_calls += 1
        return real_merge(c, base, speed)

    monkeypatch.setattr(engine, "_merge_bait_speed", counting_merge)
    monkeypatch.setattr(engine, "_calculate_fishing_interval", lambda *_: 5.0)
    monkeypatch.setattr(
        engine, "_catch_fish_at_interval", lambda *a, **k: (a[3], a[5])
    )

    # 25 分钟 / 5 分钟 = 5 步，bait 速度全程不变
    await engine.simulate_fishing_loop(
        ctx, freeze_buff_time=freeze, time_credit_minutes=25
    )
    assert merge_calls == 1, f"bait 不变时应只合并1次，实际{merge_calls}次"


# ═══════════════════════════════════════════════════════════════════════════════
# 鱼饵速度变化触发重算
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_bait_speed_change_triggers_recompute(db, monkeypatch):
    """鱼饵切换/无饵导致 bait_speed 变化时，应重算 effects 与 interval。"""
    from zhenxun.plugins.zhenxun_plugin_fishing.config import BaitData

    ctx = await _make_ctx(db, bait_remaining=1)
    ctx.bait = BaitData(
        id=1, name="测试饵", speed_bonus=20, price=1, description=""
    )
    ctx.bait_speed_bonus = 20
    # 库存无备用饵：1 个饵用完即进入无饵模式
    merge_calls = 0
    real_merge = engine._merge_bait_speed

    def counting_merge(c, base, speed):
        nonlocal merge_calls
        merge_calls += 1
        return real_merge(c, base, speed)

    monkeypatch.setattr(engine, "_merge_bait_speed", counting_merge)
    monkeypatch.setattr(engine, "_calculate_fishing_interval", lambda *_: 5.0)

    catch_calls = 0

    def catch(*args, **kwargs):
        nonlocal catch_calls
        catch_calls += 1
        # 第 1 次捕获产鱼触发饵消耗，之后无饵
        args[4].append(
            (SimpleNamespace(id="fish", base_price=1), "N", 1, None)
        )
        return args[3], args[5]

    monkeypatch.setattr(engine, "_catch_fish_at_interval", catch)

    await engine.simulate_fishing_loop(ctx, time_credit_minutes=20)
    # 至少 2 次 merge：初始(bait=20) + 无饵后(bait=0)
    assert merge_calls >= 2, f"饵切换应触发重算，实际 merge {merge_calls} 次"
