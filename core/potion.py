"""时光药水结算 —— 两阶段结算：先处理历史待处理时间，再处理药水时间。

设计原则：
- 阶段一（正常模式）：如果 last_settle_time < now，以正常模式结算这段时间的鱼获。
  使用历史时刻的 buff（不冻结），剩余时间按概率出鱼（小数不丢弃）。
- 阶段二（时间吸收模式）：结算 time_credit_minutes = hours*60 分钟。
  使用当前时刻的 buff（freeze_buff_time=now），不足一条鱼的时间丢弃。

两个阶段的结果合并到 status_dict，用户收杆时由 end_fishing 统一结算。
"""

from datetime import datetime

from zhenxun.services.log import logger

from ..config import ConfigManager
from ..models import BuffEffect, FishingBuffCalculator, FishingUser
from ..render import render_fishing_status
from ..weather_service import get_location_weather
from .bait import consume_bait_incremental
from .cat_gift import default_cat_gifts, merge_cat_gifts
from .context import deserialize_fish_caught
from .engine import simulate_fishing_loop
from .probability import calculate_display_probabilities
from .settlement_status import build_settlement_status
from .speed import build_speed_bonus_detail, calculate_effective_fishing_interval

# 时光药水结算时应忽略的药水 buff 类型（仅阶段二过滤）
# 闪光药水（伽马射线暴）同样不与时光联动；三种药水在普通钓鱼中互斥
_TIME_POTION_IGNORED_BUFF_TYPES = frozenset(
    {
        BuffEffect.BUFF_TYPE_DUODUO,
        BuffEffect.BUFF_TYPE_LUCKY_BOOST,
        BuffEffect.BUFF_TYPE_GAMMA_RAY_BURST,
    }
)


async def use_time_potion_settle(
    user_id: str, hours: int, potion_count: int = 0
) -> tuple[bool, bytes | str]:
    """使用时光药水，先结算历史待处理时间，再结算药水时间。

    所有结果合并到钓鱼状态（status_dict），等用户收杆时统一结算。
    """
    status_dict = await FishingUser.get_status(user_id)
    if not status_dict:
        return False, "你还没有在钓鱼"

    location = ConfigManager.get_location(status_dict["location_id"])
    if not location:
        return False, "当前钓鱼地点无效"

    now = datetime.now()
    from .actions import _prepare_fishing_context

    # ── 读取当前保底计数（status_dict 优先，若无则从 user 记录读取）──
    user = await FishingUser.get_user(user_id)
    frame_pity = status_dict.get("frame_pity", user.frame_pity_counter if user else 0)
    cat_frame_pity = status_dict.get(
        "cat_frame_pity", user.cat_frame_pity_counter if user else 0
    )
    utr_pity = status_dict.get("utr_pity", user.utr_pity_counter if user else 0)

    # 累计变量
    all_fish: list = []
    all_bait_usage: dict[str, int] = {}
    all_cat_eaten: list = []
    all_meteor: list[int] = []
    all_buff_messages: list[str] = []
    current_frame_pity = frame_pity
    current_cat_frame_pity = cat_frame_pity
    current_utr_pity = utr_pity
    existing_cat_gifts = status_dict.get("cat_gifts", default_cat_gifts())
    merged_cat_gifts_result = existing_cat_gifts

    # ═══════════════════════════════════════════════════════════════════════════
    # 阶段一：结算历史待处理时间（正常模式，历史buff不冻结）
    # ═══════════════════════════════════════════════════════════════════════════
    current_last_settle = datetime.fromisoformat(status_dict["last_settle_time"])
    pending_minutes = (now - current_last_settle).total_seconds() / 60

    if pending_minutes > 0:
        logger.info(
            f"用户 {user_id} 时光药水阶段一：结算历史待处理时间 "
            f"{pending_minutes:.1f} 分钟"
        )

        ctx1 = await _prepare_fishing_context(user_id, status_dict, gm_mode=False)
        if ctx1:
            # 不调用 ctx.settle_start = now —— 让它从历史 settle_start 自然推进
            # 不冻结 buff —— 每个时间点使用当时的 buff
            simulation1 = await simulate_fishing_loop(
                ctx1,
                current_frame_pity,
                current_cat_frame_pity,
                initial_utr_pity=current_utr_pity,
                # 不传 freeze_buff_time 和 time_credit_minutes → 正常推进模式
            )

            all_fish.extend(simulation1.fish_caught)
            for k, v in simulation1.bait_usage.items():
                all_bait_usage[k] = all_bait_usage.get(k, 0) + v
            all_cat_eaten.extend(simulation1.cat_eaten_fish)
            if simulation1.meteor_fish_numbers:
                all_meteor.extend(simulation1.meteor_fish_numbers)
            all_buff_messages.extend(ctx1.buff_messages)

            current_frame_pity = simulation1.frame_pity
            current_utr_pity = simulation1.utr_pity
            cat_frame_pity_1 = simulation1.cat_gifts.get(
                "cat_frame_pity", current_cat_frame_pity
            )
            current_cat_frame_pity = cat_frame_pity_1
            merged_cat_gifts_result = merge_cat_gifts(
                existing_cat_gifts, simulation1.cat_gifts, cat_frame_pity_1
            )

            logger.info(
                f"用户 {user_id} 阶段一完成："
                f"钓到{sum(c for _, _, c in simulation1.fish_caught)}条鱼"
            )
        else:
            pending_minutes = 0  # 构建失败视为无待处理

    # ═══════════════════════════════════════════════════════════════════════════
    # 阶段二：时光药水结算（时间吸收模式，当前buff冻结）
    # ═══════════════════════════════════════════════════════════════════════════
    # 构建第二阶段上下文：last_settle_time 已推进到 now（阶段一已处理完），
    # 所以 settle_start = now，buffs 取当前活跃的
    ctx_status_potion = status_dict.copy()
    ctx_status_potion["last_settle_time"] = now.isoformat()
    # 阶段一后的保底计数写入 ctx_status，供 _prepare_fishing_context 取用。
    # 实际上它读取 FishingUser 记录，但这里仍用参数控制。

    ctx2 = await _prepare_fishing_context(user_id, ctx_status_potion, gm_mode=False)
    if not ctx2:
        return False, "准备钓鱼上下文失败"

    ctx2.settle_start = now
    # 阶段一的鱼饵状态继承到阶段二
    if pending_minutes > 0:
        ctx2.bait = simulation1.bait
        ctx2.bait_remaining = simulation1.bait_remaining

    # 过滤多多/幸运/闪光 buff（仅阶段二；普通钓鱼中三者互斥）
    ctx2.buffs = [
        b for b in ctx2.buffs if b.buff_type not in _TIME_POTION_IGNORED_BUFF_TYPES
    ]

    simulation2 = await simulate_fishing_loop(
        ctx2,
        current_frame_pity,
        current_cat_frame_pity,
        initial_utr_pity=current_utr_pity,
        freeze_buff_time=now,
        time_credit_minutes=hours * 60,
        initial_available_baits=(
            simulation1.available_baits if pending_minutes > 0 else None
        ),
        initial_no_bait_mode=(
            simulation1.no_bait_mode if pending_minutes > 0 else None
        ),
    )

    all_fish.extend(simulation2.fish_caught)
    for k, v in simulation2.bait_usage.items():
        all_bait_usage[k] = all_bait_usage.get(k, 0) + v
    all_cat_eaten.extend(simulation2.cat_eaten_fish)
    if simulation2.meteor_fish_numbers:
        all_meteor.extend(simulation2.meteor_fish_numbers)
    all_buff_messages.extend(ctx2.buff_messages)

    final_frame_pity = simulation2.frame_pity
    final_utr_pity = simulation2.utr_pity
    cat_frame_pity_2 = simulation2.cat_gifts.get(
        "cat_frame_pity", current_cat_frame_pity
    )
    merged_cat_gifts_result = merge_cat_gifts(
        merged_cat_gifts_result, simulation2.cat_gifts, cat_frame_pity_2
    )

    # ── 合并到钓鱼状态 ──
    existing_fish = deserialize_fish_caught(status_dict.get("fish_caught", []))
    total_fish = existing_fish + all_fish
    existing_bait_consumed = status_dict.get("bait_consumed", 0)
    total_bait_consumed_num = existing_bait_consumed + sum(all_bait_usage.values())

    # 累计鱼饵消耗明细（bait_id → 数量），供回档药水退还
    existing_bait_usage = status_dict.get("bait_usage", {})
    total_bait_usage = dict(existing_bait_usage)
    for k, v in all_bait_usage.items():
        total_bait_usage[k] = total_bait_usage.get(k, 0) + v

    existing_cat_eaten = deserialize_fish_caught(status_dict.get("cat_eaten_fish", []))
    total_cat_eaten = existing_cat_eaten + all_cat_eaten

    # last_settle_time 只推进到当前真实时间。
    # 时光药水的虚拟时间已经以鱼获形式写入 status_dict，不能推进真实时间锚点，
    # 否则后续正常等待会因为 last_settle_time 在未来而不再产鱼。
    total_pushed = pending_minutes + hours * 60
    new_last_settle = now

    updated_status = build_settlement_status(
        status_dict=status_dict,
        last_settle_time=new_last_settle,
        fish_caught=total_fish,
        bait_consumed=total_bait_consumed_num,
        frame_pity=final_frame_pity,
        cat_frame_pity=cat_frame_pity_2,
        utr_pity=final_utr_pity,
        cat_eaten_fish=total_cat_eaten,
        cat_gifts=merged_cat_gifts_result,
        meteor_fish_numbers=all_meteor if all_meteor else None,
        bait_usage=total_bait_usage,
    )
    if potion_count > 0:
        updated_status["time_potions_used"] = (
            int(status_dict.get("time_potions_used", 0)) + potion_count
        )
    await FishingUser.update_fishing_status(user_id, updated_status)

    # 鱼饵消耗
    new_bait_consumed = sum(all_bait_usage.values())
    if new_bait_consumed > 0:
        await consume_bait_incremental(
            user_id,
            await _get_user_for_bait(user_id),
            all_bait_usage,
            all_buff_messages,
        )

    # ── 渲染 ──
    fish_count = sum(count for _, _, count in all_fish) + len(all_meteor)
    potion_msgs = [f"⏳ 时光药水生效！模拟了{hours}小时钓鱼时间"]
    if pending_minutes > 0:
        potion_msgs.insert(
            0,
            f"📋 先结算了{pending_minutes:.1f}分钟的待处理钓鱼时间",
        )
    potion_msgs.append(f"共钓到{fish_count}条鱼，已合并到钓鱼状态中")
    if all_meteor:
        potion_msgs.append(f"🌠 其中流星鱼 {len(all_meteor)} 条（收杆时结算）")
    buff_messages = potion_msgs + all_buff_messages

    total_duration_min = total_pushed
    probabilities = calculate_display_probabilities(
        ctx2.user.rod_level, location.difficulty, location.max_rarity, 0
    )

    final_effects = FishingBuffCalculator.get_effects_at_time(
        ctx2.buffs,
        now,
        ctx2.user.rod_level,
        ctx2.bait.speed_bonus if ctx2.bait else 0,
        location.difficulty,
    )
    extra_speed_multiplier = final_effects.get("extra_speed_multiplier", 1.0)
    weather_speed_multiplier = final_effects.get("weather_speed_multiplier", 1.0)
    cat_park_speed_multiplier = 1.0
    from ..cat_park import is_cat_park_location

    if is_cat_park_location(location.id):
        from ..cat_park import get_user_cat_park_effect_values

        cp_effects = await get_user_cat_park_effect_values(user_id)
        cat_park_speed_multiplier = cp_effects.get("cat_park_speed_multiplier", 1.0)
    starry_bonus_value = 0
    for b in ctx2.buffs:
        if b.buff_type == BuffEffect.BUFF_TYPE_STARRY_BONUS:
            starry_bonus_value = max(starry_bonus_value, b.value)
    speed_bonus_detail = build_speed_bonus_detail(
        ctx2.user.hook_level,
        ctx2.bait.speed_bonus if ctx2.bait else 0,
        final_effects["speed_bonus"],
        extra_speed_multiplier,
        weather_speed_multiplier,
        cat_park_speed_multiplier,
        starry_bonus=starry_bonus_value,
    )
    fishing_interval = calculate_effective_fishing_interval(
        ctx2.user.hook_level,
        final_effects["speed_bonus"],
        extra_speed_multiplier,
        weather_speed_multiplier,
        cat_park_speed_multiplier,
    )
    weather_info = await get_location_weather(location.id, user_id)

    image = await render_fishing_status(
        user_id=user_id,
        location=location,
        total_duration_min=total_duration_min,
        total_fish=all_fish,
        new_fish=all_fish,
        new_bait_consumed=new_bait_consumed,
        total_bait_consumed=0,
        probabilities=probabilities,
        bait=ctx2.bait,
        buff_messages=buff_messages,
        fishing_power=ctx2.user.rod_level - location.difficulty,
        rod_level=ctx2.user.rod_level,
        buffs=ctx2.buffs,
        fishing_start_time=now,
        now_time=now,
        fishing_interval=fishing_interval,
        speed_bonus_detail=speed_bonus_detail,
        weather_info=weather_info,
        cat_eaten_fish=total_cat_eaten if total_cat_eaten else None,
        cat_gifts=merged_cat_gifts_result,
        frame_pity=final_frame_pity,
        utr_pity=final_utr_pity,
        cat_frame_pity=cat_frame_pity_2,
        meteor_fish_numbers=updated_status.get("meteor_fish_numbers") or None,
    )

    logger.info(
        f"用户 {user_id} 使用时光药水（两阶段），"
        f"历史{pending_minutes:.0f}分钟 + 药水{hours}小时，"
        f"共钓到{fish_count}条鱼"
    )

    return True, image


async def _get_user_for_bait(user_id: str):
    """获取 user 对象用于 consume_bait_incremental。"""
    from ..models import FishingUser as _FU

    return await _FU.get_user(user_id)
