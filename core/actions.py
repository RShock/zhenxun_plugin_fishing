"""钓鱼用例编排与结算边界。

调用链固定为 Handler → 本模块 → 纯计算引擎/服务 → Model；Handler 不应直接编写
业务状态。结算遵循「先在内存模拟、成功后单事务落库」：状态、鱼获、鱼饵与统计必须
原子提交，失败时整体回滚；自动选出的临时鱼饵只属于本轮结果，不覆盖玩家持久化偏好。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from zhenxun.services.log import logger

from ..config import ConfigManager, LocationData
from ..models import (
    BuffEffect,
    FishingBuff,
    FishingBuffCalculator,
    FishingUser,
    _make_naive,
)
from ..render import render_fishing_status
from ..scene_instance import (
    SHADOW_SCENE_INPUT,
    SHADOW_SCENE_LOCATION_ID,
    SHADOW_SCENE_USER_ID,
    get_scene_instance_id,
)
from ..services import build_buff_messages, calculate_display_income, get_or_create_user
from ..weather_service import ensure_weather_generated, get_location_weather
from .bait import consume_bait_incremental, select_bait_with_preference
from .cat_gift import default_cat_gifts, merge_cat_gifts
from .context import FishingContext, StepResult, deserialize_fish_caught, merge_fish
from .engine import simulate_fishing_loop
from .hints import build_pity_hints
from .probability import calculate_display_probabilities
from .scene import render_scene
from .settlement_status import build_settlement_status
from .speed import build_speed_bonus_detail, calculate_effective_fishing_interval

# ═══════════════════════════════════════════════════════════════════════════════
# 内部辅助
# ═══════════════════════════════════════════════════════════════════════════════


class StopFishingAborted(Exception):
    """收杆中止（例如并发下状态已被清空），不视为系统错误。"""


@asynccontextmanager
async def _stop_db_transaction():
    """收杆写库事务。

    - 正常环境：所有写操作进入同一事务，异常则整单回滚。
    - 测试/未初始化 ORM：退化为空上下文（MockDB 本身无真实提交语义）。
    """
    use_tx = False
    in_transaction = None
    try:
        from tortoise import Tortoise
        from tortoise.transactions import in_transaction as _in_tx

        use_tx = bool(getattr(Tortoise, "_inited", False))
        in_transaction = _in_tx
    except Exception:
        use_tx = False

    if not use_tx or in_transaction is None:
        yield None
        return

    async with in_transaction() as connection:
        yield connection


async def _lock_fishing_user(user_id: str):
    """事务内锁定用户行，防止并发收杆互相覆盖。"""
    try:
        user = await FishingUser.filter(user_id=user_id).select_for_update().first()
    except Exception:
        # Mock / 不支持行锁时回退
        return await FishingUser.get_user(user_id)
    if user is None:
        return await FishingUser.get_user(user_id)
    return user


async def _process_daily_rewards(user_id: str) -> tuple[bool, int, int, int]:
    """处理每日签到和展示收益。"""
    is_new_sign, corn_count, days_missed = await FishingUser.check_and_sign(user_id)
    display_income = 0
    multiplier = days_missed + 1
    if is_new_sign:
        display_income = await calculate_display_income(user_id)
        if display_income > 0:
            total_income = display_income * multiplier
            await FishingUser.add_gold(user_id, total_income)
    return is_new_sign, corn_count, display_income, days_missed


async def _prepare_fishing_context(
    user_id: str,
    status_dict: dict,
    gm_mode: bool = False,
) -> FishingContext | None:
    """从状态字典构建钓鱼上下文。"""
    location = ConfigManager.get_location(status_dict["location_id"])
    if not location:
        return None

    user = await get_or_create_user(user_id)

    # 直接使用用户当前鱼饵设置，不重新选择
    # 开始钓鱼时已通过 select_bait_with_preference 设定 bait_id
    # 钓鱼期间玩家通过"设定鱼饵"修改的是 preferred_bait_id，不影响正在使用的 bait_id
    # 鱼饵用完时由循环内部自动切换
    bait = ConfigManager.get_bait(user.bait_id)
    bait_speed_bonus = bait.speed_bonus if bait else 0

    bait_remaining = 0
    if bait and str(bait.id) != "0":
        bait_item = await FishingUser.get_item(user_id, str(bait.id), "bait")
        bait_remaining = bait_item["count"] if bait_item else 0

    now = datetime.now()
    settle_start = _make_naive(
        datetime.fromisoformat(
            status_dict.get("last_settle_time", status_dict["start_time"])
        )
    )

    if gm_mode:
        start_time = _make_naive(datetime.fromisoformat(status_dict["start_time"]))
        now = start_time + timedelta(hours=10)
        settle_start = start_time

    buffs = await FishingBuff.get_active_buffs_for_fishing(
        user_id,
        location.id,
        settle_start,
        now,
        location_buff_target_id=get_scene_instance_id(status_dict, location.id),
    )

    # 星空图的乱纪元只是一层显示名称：完成该图收集后，结算效果等同迷途风；
    # 未完成时不附加任何天气增益，等同晴天。
    from ..starry import is_starry_location
    from ..weather_service import get_chaotic_era_windows

    if is_starry_location(location.id) and await FishingUser.has_unlocked_lost_wind(
        user_id, location.id
    ):
        for window_start, window_end in await get_chaotic_era_windows(
            location.id, settle_start, now
        ):
            buffs.append(
                FishingBuff(
                    buff_type=BuffEffect.BUFF_TYPE_WEATHER_LOST_WIND,
                    start_time=window_start,
                    end_time=window_end,
                    value=1,
                    description="乱纪元：迷途风效果已觉醒",
                    target_type=BuffEffect.TARGET_TYPE_USER,
                    target_id=user_id,
                )
            )

    buff_messages = build_buff_messages(buffs, settle_start, now)

    return FishingContext(
        user=user,
        user_id=user_id,
        location=location,
        buffs=buffs,
        bait=bait,
        bait_speed_bonus=bait_speed_bonus,
        bait_remaining=bait_remaining,
        settle_start=settle_start,
        now=now,
        buff_messages=buff_messages,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 公开 API
# ═══════════════════════════════════════════════════════════════════════════════


async def start_fishing(
    user_id: str, location_id: str, nickname: str = "", group_id: str | None = None
) -> tuple[bytes, bool, str]:
    """开始钓鱼。"""
    user = await get_or_create_user(user_id, nickname)
    await ensure_weather_generated()

    if await FishingUser.is_fishing(user_id):
        status = await FishingUser.get_status(user_id)
        if status:
            loc = ConfigManager.get_location(status["location_id"])
            if loc:
                image = await render_scene(user_id, loc, group_id=group_id)
                return image, False, "你已经在钓鱼了，输入【收杆】结束钓鱼！"

    shadow_scene = location_id == SHADOW_SCENE_INPUT
    if shadow_scene and str(user_id) != SHADOW_SCENE_USER_ID:
        locations = ConfigManager.get_locations()
        from ..render import render_location_select

        image = await render_location_select(user_id, locations, user.rod_level)
        return image, False, "该隐藏测试地图仅对指定测试账号开放。"

    effective_location_id = SHADOW_SCENE_LOCATION_ID if shadow_scene else location_id
    location = ConfigManager.get_location(effective_location_id)
    from ..cat_park import has_cat_park_ticket, is_cat_park_location
    from ..starry import has_starry_ship, is_starry_location

    if not location or (
        not shadow_scene
        and (
            (
                is_cat_park_location(location_id)
                and not await has_cat_park_ticket(user_id)
            )
            or (is_starry_location(location_id) and not await has_starry_ship(user_id))
            or (
                not is_cat_park_location(location_id)
                and user.rod_level < location.difficulty
            )
        )
    ):
        locations = ConfigManager.get_locations()
        from ..render import render_location_select

        image = await render_location_select(user_id, locations, user.rod_level)
        return image, False, ""

    best_bait_id, best_bait_count = await select_bait_with_preference(user_id)
    user.bait_id = str(best_bait_id)
    await user.save(update_fields=["bait_id"])

    status = await FishingUser.start_fishing(user_id, location.id)
    if shadow_scene:
        # ?????? 11 ????????????? -11 ???????
        status["shadow_scene"] = True
        status["scene_instance_id"] = SHADOW_SCENE_INPUT
        await FishingUser.update_fishing_status(user_id, status)
    image = await render_scene(user_id, location, group_id=group_id)
    logger.info(f"用户 {user_id} 在 {location.name} 开始钓鱼")
    return image, True, ""


async def _compute_settle_step(
    user_id: str, gm_mode: bool = False
) -> tuple[StepResult, dict, FishingContext] | None:
    """仅计算本段钓鱼结算结果，不写数据库。

    返回 (step, updated_status, ctx)。收杆原子提交与状态查询共用此纯计算路径。
    """
    status_dict = await FishingUser.get_status(user_id)
    if not status_dict:
        return None

    ctx = await _prepare_fishing_context(user_id, status_dict, gm_mode)
    if not ctx:
        return None

    existing_fish = deserialize_fish_caught(status_dict.get("fish_caught", []))
    existing_bait_consumed = status_dict.get("bait_consumed", 0)
    frame_pity = status_dict.get("frame_pity", ctx.user.frame_pity_counter)
    cat_frame_pity = status_dict.get("cat_frame_pity", ctx.user.cat_frame_pity_counter)
    utr_pity = status_dict.get("utr_pity", ctx.user.utr_pity_counter)

    simulation = await simulate_fishing_loop(
        ctx, frame_pity, cat_frame_pity, initial_utr_pity=utr_pity
    )

    if "cat_frame_pity" in simulation.cat_gifts:
        cat_frame_pity = simulation.cat_gifts["cat_frame_pity"]

    new_bait_consumed = sum(simulation.bait_usage.values())
    total_fish = merge_fish(existing_fish, simulation.fish_caught)
    total_bait_consumed = existing_bait_consumed + new_bait_consumed

    existing_cat_eaten = deserialize_fish_caught(status_dict.get("cat_eaten_fish", []))
    total_cat_eaten = existing_cat_eaten + simulation.cat_eaten_fish

    existing_cat_gifts = status_dict.get("cat_gifts", default_cat_gifts())
    merged_cat_gifts = merge_cat_gifts(
        existing_cat_gifts, simulation.cat_gifts, cat_frame_pity
    )

    updated_status = build_settlement_status(
        status_dict=status_dict,
        last_settle_time=ctx.now,
        fish_caught=total_fish,
        bait_consumed=total_bait_consumed,
        frame_pity=simulation.frame_pity,
        cat_frame_pity=cat_frame_pity,
        utr_pity=simulation.utr_pity,
        cat_eaten_fish=total_cat_eaten,
        cat_gifts=merged_cat_gifts,
        meteor_fish_numbers=simulation.meteor_fish_numbers,
    )

    step = StepResult(
        new_fish=simulation.fish_caught,
        new_bait_consumed=new_bait_consumed,
        frame_pity=simulation.frame_pity,
        cat_frame_pity=cat_frame_pity,
        utr_pity=simulation.utr_pity,
        bait=simulation.bait,
        bait_remaining=simulation.bait_remaining,
        bait_usage=simulation.bait_usage,
        buff_messages=ctx.buff_messages,
        cat_eaten_fish=simulation.cat_eaten_fish,
        cat_gifts=simulation.cat_gifts,
    )
    return step, updated_status, ctx


async def settle_fishing_step(user_id: str, gm_mode: bool = False) -> StepResult | None:
    """结算一次钓鱼步进（状态查询路径：立即落库）。"""
    computed = await _compute_settle_step(user_id, gm_mode)
    if not computed:
        return None

    step, updated_status, ctx = computed

    # 模拟阶段只计算自动换饵结果，不持久化 user.bait_id；状态与鱼饵扣除
    # 必须在同一事务中提交，避免状态已推进但鱼饵未扣除。
    async with _stop_db_transaction():
        await FishingUser.update_fishing_status(user_id, updated_status)
        if step.bait_usage:
            await consume_bait_incremental(
                user_id, ctx.user, step.bait_usage, step.buff_messages
            )

    return step


async def check_fishing_status(
    user_id: str,
    location: LocationData | None = None,
    group_id: str | None = None,
) -> tuple[bytes | None, StepResult | None]:
    """查看当前钓鱼状态（含步进结算）。"""
    step = await settle_fishing_step(user_id)
    if not step:
        return None, None

    status_dict = await FishingUser.get_status(user_id)
    if not status_dict:
        return None, None

    if not location:
        location = ConfigManager.get_location(status_dict["location_id"])
    if not location:
        return None, None

    user = await FishingUser.get_user(user_id)

    total_fish = deserialize_fish_caught(status_dict.get("fish_caught", []))
    total_bait_consumed = status_dict.get("bait_consumed", 0)
    cat_eaten_fish = deserialize_fish_caught(status_dict.get("cat_eaten_fish", []))
    cat_gifts = status_dict.get("cat_gifts", default_cat_gifts())

    start_time = _make_naive(datetime.fromisoformat(status_dict["start_time"]))
    total_duration = datetime.now() - start_time
    total_duration_min = total_duration.total_seconds() / 60

    # S1 材料率（随猫爬架广场等级动态变化）+ 喵喵鱼塘速度乘区
    material_rate = 0.0
    cat_park_speed_multiplier = 1.0
    cat_park_weather_bonus = 0.0
    from ..cat_park import is_cat_park_location

    if is_cat_park_location(location.id):
        from ..cat_park import get_cat_park_effect_values, get_cat_park_state

        state = await get_cat_park_state(user_id)
        cp_effects = get_cat_park_effect_values(state)
        material_rate = cp_effects.get("material_rate", 0.0)
        cat_park_speed_multiplier = cp_effects.get("cat_park_speed_multiplier", 1.0)
        cat_park_weather_bonus = cp_effects.get("weather_bonus", 0.0)

    probability_max_rarity = location.max_rarity
    from ..starry import is_starry_location

    if is_starry_location(location.id) and f"collect_scene_{location.id}" not in (
        user.achievements or []
    ):
        probability_max_rarity = "UR"

    probabilities = calculate_display_probabilities(
        user.rod_level,
        location.difficulty,
        probability_max_rarity,
        0,
        material_rate=material_rate,
        starry_utr_unlocked=(
            is_starry_location(location.id) and probability_max_rarity == "UTR"
        ),
    )
    bait = ConfigManager.get_bait(user.bait_id)

    active_buffs = await FishingBuff.get_active_buffs_for_fishing(
        user_id,
        location.id,
        start_time,
        datetime.now(),
        location_buff_target_id=get_scene_instance_id(status_dict, location.id),
    )
    effects = None
    if active_buffs:
        effects = FishingBuffCalculator.get_effects_at_time(
            active_buffs,
            datetime.now(),
            user.rod_level,
            bait.speed_bonus if bait else 0,
            location.difficulty,
        )
        if cat_park_weather_bonus > 0:
            from .engine import _apply_cat_park_weather_bonus

            _apply_cat_park_weather_bonus(effects, cat_park_weather_bonus)
        probabilities = calculate_display_probabilities(
            effects["rod_level"],
            location.difficulty,
            probability_max_rarity,
            duoduo_count=effects.get("duoduo_count", 0),
            weather_luck_boost=effects.get("weather_luck_boost", 0),
            weather_lost_wind=effects.get("weather_lost_wind", False),
            material_rate=material_rate,
            starry_utr_unlocked=(
                is_starry_location(location.id) and probability_max_rarity == "UTR"
            ),
            weather_lost_wind_multiplier=effects.get(
                "weather_lost_wind_multiplier", 1.0
            ),
        )

    bait_speed_bonus = (
        effects["speed_bonus"] if effects else (bait.speed_bonus if bait else 0)
    )
    extra_speed_multiplier = (
        effects.get("extra_speed_multiplier", 1.0) if effects else 1.0
    )
    weather_speed_multiplier = (
        effects.get("weather_speed_multiplier", 1.0) if effects else 1.0
    )
    # 提取星空艇加成值，用于速度明细中单独显示
    starry_bonus_value = 0
    if active_buffs:
        for b in active_buffs:
            if b.buff_type == BuffEffect.BUFF_TYPE_STARRY_BONUS:
                starry_bonus_value = max(starry_bonus_value, b.value)
    fishing_interval = calculate_effective_fishing_interval(
        user.hook_level,
        bait_speed_bonus,
        extra_speed_multiplier,
        weather_speed_multiplier,
        cat_park_speed_multiplier,
    )
    speed_bonus_detail = build_speed_bonus_detail(
        user.hook_level,
        bait.speed_bonus if bait else 0,
        bait_speed_bonus,
        extra_speed_multiplier,
        weather_speed_multiplier,
        cat_park_speed_multiplier,
        starry_bonus=starry_bonus_value,
    )

    now = datetime.now()
    weather_info = await get_location_weather(location.id, user_id)

    image = await render_fishing_status(
        user_id=user_id,
        location=location,
        total_duration_min=total_duration_min,
        total_fish=total_fish,
        new_fish=step.new_fish,
        total_bait_consumed=total_bait_consumed,
        new_bait_consumed=step.new_bait_consumed,
        probabilities=probabilities,
        bait=step.bait,
        bait_remaining=step.bait_remaining,
        buff_messages=step.buff_messages,
        fishing_power=user.rod_level - location.difficulty,
        rod_level=user.rod_level,
        buffs=active_buffs,
        fishing_start_time=start_time,
        now_time=now,
        fishing_interval=fishing_interval,
        speed_bonus_detail=speed_bonus_detail,
        weather_info=weather_info,
        cat_eaten_fish=cat_eaten_fish if cat_eaten_fish else None,
        cat_gifts=cat_gifts,
        material_rate=material_rate,
        frame_pity=status_dict.get("frame_pity", user.frame_pity_counter),
        utr_pity=status_dict.get("utr_pity", user.utr_pity_counter),
        cat_frame_pity=status_dict.get("cat_frame_pity", user.cat_frame_pity_counter),
        meteor_fish_numbers=status_dict.get("meteor_fish_numbers") or None,
    )

    return image, step


async def _preview_daily_rewards(user_id: str) -> tuple[bool, int, int, int]:
    """预览签到结果（只读，不写库）。"""
    from datetime import date

    user = await FishingUser.get_user(user_id)
    today = date.today()
    if user.last_sign_date == today:
        return False, 0, 0, 0

    days_missed = 0
    if user.last_sign_date is not None:
        delta = (today - user.last_sign_date).days
        days_missed = max(0, delta - 1)

    display_income = await calculate_display_income(user_id)
    # corn 预览：签到后会 +1
    corn_after = int(user.corn or 0) + 1
    return True, corn_after, display_income, days_missed


@dataclass
class _StopSettlementPlan:
    """收杆各领域阶段共享的受控内存计划。"""

    user_id: str
    user: Any
    gm_mode: bool
    is_private: bool
    step: StepResult
    updated_status: dict
    is_new_sign: bool
    display_income: int
    days_missed: int
    corn_count: int
    dirty: set[str] = field(default_factory=set)
    location: Any = None
    total_fish: list = field(default_factory=list)
    total_bait_consumed: int = 0
    frame_pity: int = 0
    cat_frame_pity: int = 0
    utr_pity: int = 0
    cat_eaten_fish: list = field(default_factory=list)
    cat_gifts: dict = field(default_factory=dict)
    meteor_fish_numbers: list[int] = field(default_factory=list)
    bait_speed_bonus: float = 0
    start_time: datetime | None = None
    now: datetime | None = None
    buffs: list = field(default_factory=list)
    starry_score_info: dict | None = None
    miracle_info: dict | None = None
    starry_rewards: list[dict] = field(default_factory=list)

    @property
    def messages(self) -> list[str]:
        return self.step.buff_messages


async def _apply_session_reward_stage(plan: _StopSettlementPlan) -> None:
    """应用签到、会话快照、扣饵和停止状态，并准备结算上下文。"""
    from ..models import user_mutations as mut
    from . import stop_mutations as sm

    sm.apply_daily_rewards_on_user(
        plan.user,
        plan.is_new_sign,
        plan.display_income,
        plan.days_missed,
        plan.dirty,
    )
    status = dict(plan.updated_status)
    if plan.step.new_bait_consumed > 0:
        mut.apply_consume_bait_incremental(
            plan.user, plan.step.bait_usage, plan.messages, plan.dirty
        )

    plan.total_fish = deserialize_fish_caught(status.get("fish_caught", []))
    plan.total_bait_consumed = status.get("bait_consumed", 0)
    plan.frame_pity = status.get("frame_pity", plan.user.frame_pity_counter)
    plan.cat_frame_pity = status.get("cat_frame_pity", plan.user.cat_frame_pity_counter)
    plan.utr_pity = status.get("utr_pity", plan.user.utr_pity_counter)
    plan.cat_eaten_fish = deserialize_fish_caught(status.get("cat_eaten_fish", []))
    plan.cat_gifts = status.get("cat_gifts", default_cat_gifts())
    plan.meteor_fish_numbers = status.get("meteor_fish_numbers", [])
    plan.location = ConfigManager.get_location(status["location_id"])
    if not plan.location:
        raise RuntimeError(f"收杆地点无效: {status.get('location_id')}")

    mut.apply_stop_fishing(plan.user, plan.dirty)
    plan.bait_speed_bonus = plan.step.bait.speed_bonus if plan.step.bait else 0
    plan.start_time = _make_naive(datetime.fromisoformat(status["start_time"]))
    plan.now = datetime.now()
    if plan.gm_mode:
        plan.now = plan.start_time + timedelta(hours=10)
    plan.buffs = await FishingBuff.get_active_buffs_for_fishing(
        plan.user_id,
        plan.location.id,
        plan.start_time,
        plan.now,
        location_buff_target_id=get_scene_instance_id(status, plan.location.id),
    )


async def _apply_stop_settlement_plan(
    user_id: str,
    user,
    *,
    gm_mode: bool,
    is_private: bool,
    step: StepResult,
    updated_status: dict,
    is_new_sign: bool,
    display_income: int,
    days_missed: int,
    corn_count: int,
) -> tuple[dict, list[str], bool, set[str]]:
    """按固定领域顺序在已锁定用户上应用结算计划，不执行数据库写入。"""
    plan = _StopSettlementPlan(
        user_id=user_id,
        user=user,
        gm_mode=gm_mode,
        is_private=is_private,
        step=step,
        updated_status=updated_status,
        is_new_sign=is_new_sign,
        display_income=display_income,
        days_missed=days_missed,
        corn_count=corn_count,
    )
    await _apply_session_reward_stage(plan)
    _apply_pity_cat_gift_stage(plan)
    render_data, is_last_stop = _apply_catch_achievement_display_stage(plan)
    return render_data, plan.messages, is_last_stop, plan.dirty


def _apply_pity_cat_gift_stage(plan: _StopSettlementPlan) -> None:
    """按原顺序派发猫礼物并回写三类保底。"""
    from ..models import user_mutations as mut
    from . import stop_mutations as sm

    plan.messages.extend(
        sm.apply_distribute_cat_gifts_on_user(
            plan.user,
            plan.location.id,
            list(plan.location.fish_pool),
            plan.cat_gifts,
            plan.dirty,
        )
    )
    mut.apply_writeback_pity(
        plan.user,
        plan.frame_pity,
        plan.cat_frame_pity,
        plan.utr_pity,
        plan.dirty,
    )


def _apply_starry_rewards(plan: _StopSettlementPlan) -> tuple[float, int]:
    """处理流星鱼入库和奖池，返回本次积分与有效流星鱼数。"""
    from ..models import user_mutations as mut
    from . import stop_mutations as sm
    from .starry_system import score_starry_fish

    score = 0.0
    count = 0
    for num in plan.meteor_fish_numbers:
        if int(num) > 999_999:
            mut.apply_add_item(plan.user, str(num), "meteor_fish", 1, plan.dirty)
            continue
        scored = score_starry_fish(num)
        score += scored.raw_score
        count += 1
        mut.apply_add_starry_fish(plan.user, num, plan.location.id, plan.dirty)
        if not scored.reward_pool or scored.reward_pool == "none":
            continue
        granted = sm.apply_grant_rewards_for_starry_fish_on_user(
            plan.user, num, plan.dirty
        )
        for reward in granted:
            reward.setdefault("fish_id", scored.id_text)
            reward.setdefault("display_score", scored.display_score)
            reward.setdefault(
                "pool_name", reward.get("pool_name") or scored.reward_pool
            )
            reward.setdefault("granted", True)
            if reward.get("granted"):
                score += float(reward.get("score_bonus") or 0)
        plan.starry_rewards.extend(granted)
    return score, count


def _apply_miracle_claims(plan: _StopSettlementPlan) -> None:
    """尝试连续领取奇迹并构造展示信息。"""
    from ..models import user_mutations as mut

    claims = mut.apply_try_claim_miracles(plan.user, dirty=plan.dirty)
    if not claims:
        return
    last = claims[-1]
    claim_count = len(claims)
    consumed = sum(int(claim.get("subset_count") or 0) for claim in claims)
    if claim_count == 1:
        subtitle = f"消耗 {consumed} 条流星鱼达成奇迹"
    else:
        subtitle = f"连续达成 {claim_count} 次奇迹，共消耗 {consumed} 条流星鱼"
    subtitle += "；星辰木框可用于升级星空木框"
    plan.miracle_info = {
        "claim_count": claim_count,
        "frames_gained": claim_count,
        "subset_count": consumed,
        "star_frames": int(last.get("star_frames") or 0),
        "can_upgrade_starry_frame": True,
        "hint": subtitle,
        "subtitle": subtitle,
    }


def _set_starry_score_info(plan: _StopSettlementPlan, score: float, count: int) -> None:
    from .starry_system import S2_TICKET_SCORE_THRESHOLD

    if count <= 0:
        return
    accumulated = float(plan.user.starry_score_accumulated or 0)
    target = float(S2_TICKET_SCORE_THRESHOLD)
    if accumulated >= target and not bool(
        getattr(plan.user, "s2_ticket_claimed", False)
    ):
        plan.user.s2_ticket_claimed = True
        plan.dirty.add("s2_ticket_claimed")
        plan.messages.append("🎫 星空努力值达标，已获得 S2 入场券")
    target_display = int(target) if target.is_integer() else target
    progress_pct = min(100.0, accumulated / target * 100) if target else 0.0
    plan.starry_score_info = {
        "session_score": round(score, 3),
        "accumulated": round(accumulated, 3),
        "target": target_display,
        "remaining": round(max(0.0, target - accumulated), 3),
        "progress_pct": round(progress_pct, 1),
        "reached": accumulated >= target,
        "claimed": bool(getattr(plan.user, "s2_ticket_claimed", False)),
    }


def _build_bait_log_info(plan: _StopSettlementPlan) -> str:
    if plan.total_bait_consumed <= 0 or not plan.step.bait_usage:
        return ""
    parts = []
    for bait_id, count in plan.step.bait_usage.items():
        bait = ConfigManager.get_bait(bait_id)
        if bait:
            parts.append(f"{count}个{bait.name}")
    return f"，消耗{'、'.join(parts)}" if parts else ""


def _apply_stop_limit(plan: _StopSettlementPlan) -> bool:
    from ..models import user_mutations as mut

    if plan.gm_mode or plan.is_private:
        return False
    from ..services.limit_service import is_group_action_limit_enabled

    if not is_group_action_limit_enabled():
        return False
    stop_count, is_last_stop = mut.apply_increment_stop_count(plan.user, plan.dirty)
    logger.info(f"用户 {plan.user_id} 今日第 {stop_count} 次收杆")
    return is_last_stop


def _apply_catch_achievement_display_stage(
    plan: _StopSettlementPlan,
) -> tuple[dict, bool]:
    """处理流星、签到附加奖励、鱼获成就、提示与最终展示。"""
    from . import stop_mutations as sm

    starry_score, starry_count = _apply_starry_rewards(plan)
    _apply_miracle_claims(plan)
    _set_starry_score_info(plan, starry_score, starry_count)
    if plan.is_new_sign:
        plan.messages.extend(
            sm.apply_ferris_wheel_rewards_on_user(
                plan.user, plan.days_missed, plan.dirty
            )
        )
    fish_coins, achievements, merged_fish, materials = (
        sm.apply_process_fish_results_on_user(
            plan.user,
            plan.location,
            plan.total_fish,
            plan.buffs,
            plan.bait_speed_bonus,
            plan.now,
            plan.frame_pity,
            plan.utr_pity,
            plan.messages,
            plan.dirty,
        )
    )
    _append_pity_hints(plan)
    _log_stop_result(plan, fish_coins)
    render_data = _build_stop_render_data(
        plan, fish_coins, achievements, merged_fish, materials
    )
    return render_data, _apply_stop_limit(plan)


def _append_pity_hints(plan: _StopSettlementPlan) -> None:
    from ..starry import is_starry_location

    effects = None
    if plan.buffs:
        effects = FishingBuffCalculator.get_effects_at_time(
            plan.buffs,
            plan.now,
            plan.user.rod_level,
            plan.bait_speed_bonus,
            plan.location.difficulty,
        )
    starry = is_starry_location(plan.location.id)
    plan.messages.extend(
        build_pity_hints(
            total_fish=plan.total_fish,
            frame_pity=plan.frame_pity,
            cat_frame_pity=plan.cat_frame_pity,
            utr_pity=plan.utr_pity,
            display_slots=plan.user.display_slots,
            upgraded_display_count=plan.user.upgraded_display_count,
            cat_frames=plan.user.cat_frames,
            effects_now=effects,
            skip_frame_pity=starry,
            is_starry=starry,
        )
    )


def _log_stop_result(plan: _StopSettlementPlan, fish_coins: int) -> None:
    fish_count = sum(count for _, _, count in plan.total_fish)
    bait_info = _build_bait_log_info(plan)
    logger.info(
        f"用户 {plan.user_id} 收杆，钓到 {fish_count} 条鱼，"
        f"价值 {fish_coins} 钓鱼币{bait_info}"
    )


def _build_stop_render_data(
    plan: _StopSettlementPlan,
    fish_coins: int,
    achievements: list[str],
    merged_fish: list,
    materials: dict,
) -> dict:
    sign_info = None
    if plan.is_new_sign:
        sign_info = {
            "corn_count": plan.corn_count,
            "display_income": plan.display_income,
            "days_missed": plan.days_missed,
        }
    return {
        "user_id": plan.user_id,
        "location": plan.location,
        "duration_minutes": (plan.now - plan.start_time).total_seconds() / 60,
        "merged_fish": merged_fish,
        "fish_coins": fish_coins,
        "achievement_messages": achievements,
        "sign_info": sign_info,
        "cat_eaten_fish": plan.cat_eaten_fish,
        "cat_gifts": plan.cat_gifts,
        "buffs": plan.buffs,
        "fishing_start_time": plan.start_time,
        "now_time": plan.now,
        "meteor_fish_numbers": plan.meteor_fish_numbers,
        "cat_park_materials": materials,
        "starry_score": plan.starry_score_info,
        "miracle": plan.miracle_info,
        "starry_rewards": plan.starry_rewards,
        "bait": plan.step.bait,
        "bait_remaining": plan.step.bait_remaining,
    }


async def _apply_stop_settlement_writes(
    user_id: str,
    *,
    gm_mode: bool,
    is_private: bool,
    step: StepResult,
    updated_status: dict,
    is_new_sign: bool,
    display_income: int,
    days_missed: int,
    corn_count: int,
) -> tuple[dict, list[str], bool]:
    """收杆事务内：锁行、应用结算计划，并在末尾唯一一次写库。"""
    from ..models import user_mutations as mut

    user = await _lock_fishing_user(user_id)
    if not user.fishing_status:
        raise StopFishingAborted("not_fishing")

    render_data, messages, is_last_stop, dirty = await _apply_stop_settlement_plan(
        user_id,
        user,
        gm_mode=gm_mode,
        is_private=is_private,
        step=step,
        updated_status=updated_status,
        is_new_sign=is_new_sign,
        display_income=display_income,
        days_missed=days_missed,
        corn_count=corn_count,
    )
    await mut.save_dirty(user, dirty)
    return render_data, messages, is_last_stop


async def stop_fishing(
    user_id: str, gm_mode: bool = False, is_private: bool = False
) -> tuple[dict | None, list[str], bool]:
    """收杆：结算所有鱼获，输出结果。

    原子性保证：
    - 事务外：只读预览签到、模拟本段鱼获（不写库）
    - 事务内：签到/扣饵/清会话/入包/流星/成就/计数 等全部写库
    - 任一步失败：事务回滚，数据库保持收杆前状态
    """
    await ensure_weather_generated()

    # ── 事务外：纯计算，失败不会改库 ──
    is_new_sign, corn_count, display_income, days_missed = await _preview_daily_rewards(
        user_id
    )
    computed = await _compute_settle_step(user_id, gm_mode)
    if not computed:
        return None, [], False
    step, updated_status, _ctx = computed

    # ── 事务内：一次性提交全部写库 ──
    try:
        async with _stop_db_transaction():
            return await _apply_stop_settlement_writes(
                user_id,
                gm_mode=gm_mode,
                is_private=is_private,
                step=step,
                updated_status=updated_status,
                is_new_sign=is_new_sign,
                display_income=display_income,
                days_missed=days_missed,
                corn_count=corn_count,
            )
    except StopFishingAborted as exc:
        logger.warning(f"用户 {user_id} 收杆中止: {exc}")
        return None, [], False
    except Exception:
        logger.exception(f"用户 {user_id} 收杆事务失败，已回滚全部数据库修改")
        raise


async def run_post_settlement(
    user_id: str, is_private: bool, messages: list[str]
) -> list[str]:
    """收杆/时光药水共用的后半段结算逻辑。

    按顺序执行：
    1. 自动锁鱼（优先级高于自动卖鱼，在卖鱼前执行）
    2. 自动卖鱼（按用户设定的稀有度阈值出售背包中的鱼）
    3. 自动卖猫乐园材料（猫雕像全部升到3级后自动出售多余材料）

    所有提示消息追加到 messages 列表并返回。
    """
    # 1. 自动锁鱼
    auto_lock_enabled = await FishingUser.get_auto_lock(user_id)
    if auto_lock_enabled:
        from ..backpack import auto_lock_fish

        auto_lock_pattern = await FishingUser.get_auto_lock_pattern(user_id)
        if auto_lock_pattern:
            locked_count = await auto_lock_fish(user_id, auto_lock_pattern)
            if locked_count > 0:
                messages.append(f"🔒 自动锁鱼：已锁定 {locked_count} 种")

    # 2. 自动卖鱼
    auto_sell_enabled = await FishingUser.get_auto_sell(user_id)
    if auto_sell_enabled:
        from ..backpack import sell_fish

        auto_sell_rarity = await FishingUser.get_auto_sell_rarity(user_id)
        success, sell_msg = await sell_fish(
            user_id, auto_sell_rarity, is_private=is_private
        )
        if success:
            user = await FishingUser.get_user(user_id)
            messages.append(f"🔄 自动卖鱼：{sell_msg}")
            messages.append(f"💰 当前金币：{user.gold}")

    # 3. 自动卖猫乐园材料（猫雕像全部升到3级后）
    from ..cat_park import sell_completed_cat_park_materials

    await sell_completed_cat_park_materials(user_id, messages)

    return messages
