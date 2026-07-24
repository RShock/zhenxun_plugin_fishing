"""
药水系统 — 时光药水、回档药水、幸运药水、闪光药水、木框加速、UTR自选券。
"""

from datetime import datetime, timedelta

from zhenxun.services.log import logger

from ..core.cat_gift import default_cat_gifts
from ..config import MAX_FRAME_BUFF_LAYERS, ConfigManager
from ..models import BuffEffect, FishingBuff, FishingUser, _make_naive
from ..scene_instance import get_scene_instance_id
from ..services import get_or_create_user

from .view import get_status_image


_MUTEX_POTION_BUFFS = (
    (BuffEffect.BUFF_TYPE_DUODUO, "真多多药水"),
    (BuffEffect.BUFF_TYPE_LUCKY_BOOST, "幸运药水"),
    (BuffEffect.BUFF_TYPE_GAMMA_RAY_BURST, "闪光药水"),
)


async def _get_active_mutex_potion_name(
    user_id: str, current_buff_type: str
) -> str | None:
    """同类药水允许续时，但三种核心药水之间不能同时生效。"""
    for buff_type, potion_name in _MUTEX_POTION_BUFFS:
        if buff_type == current_buff_type:
            continue
        if await FishingBuff.get_active_user_buff(user_id, buff_type):
            return potion_name
    return None


async def use_time_potion(
    user_id: str, count: int = 1, **kwargs
) -> tuple[bool, bytes | str]:
    if count < 1:
        return False, "数量必须大于0"

    status = await FishingUser.get_status(user_id)
    if not status:
        return False, "你还没有在钓鱼，无法使用时光药水！请先【钓鱼 地点编号】开始钓鱼"

    user = await get_or_create_user(user_id)
    potion_item = await FishingUser.get_item(user_id, "time_potion", "potion")
    potion_count = potion_item["count"] if potion_item else 0
    if potion_count <= 0:
        return False, "时光药水不足，当前没有时光药水"
    # 宽容机制：请求数量超出库存时，使用全部剩余药水
    if potion_count < count:
        count = potion_count

    bait = ConfigManager.get_bait(user.bait_id)
    if not bait or user.bait_id == "0":
        return False, "当前没有使用鱼饵，无法使用时光药水"

    bait_item = await FishingUser.get_item(user_id, str(bait.id), "bait")
    bait_remaining = bait_item["count"] if bait_item else 0
    if bait_remaining < 30:
        return (
            False,
            f"当前鱼饵{bait.name}不足30个（当前{bait_remaining}个），无法使用时光药水",
        )

    await FishingUser.remove_item(user_id, "time_potion", "potion", count)

    from ..core.potion import use_time_potion_settle

    hours = 8 * count
    success, result = await use_time_potion_settle(user_id, hours, potion_count=count)
    return success, result


async def use_rollback_potion(user_id: str) -> tuple[bool, bytes | str]:
    status_dict = await FishingUser.get_status(user_id)
    if not status_dict:
        return False, "你还没有在钓鱼，无法使用回档药水！请先【钓鱼 地点编号】开始钓鱼"

    user = await get_or_create_user(user_id)
    rollback_item = await FishingUser.get_item(user_id, "回档药水", "potion")
    potion_count = rollback_item["count"] if rollback_item else 0
    if potion_count < 1:
        return False, "回档药水不足，需要1瓶（当前0瓶）"

    await FishingUser.remove_item(user_id, "回档药水", "potion", 1)

    # 退还本轮钓鱼已消耗的鱼饵：回档会重置 last_settle_time 并重新结算整段
    # 时间，重新结算时 consume_bait_incremental 会再次扣饵。若不先退还，
    # 鱼饵就被扣除两次（正常钓鱼扣一次 + 重新结算扣一次）。
    bait_usage_log = status_dict.get("bait_usage_log", {})
    refunded_bait = 0
    for bait_id, count in bait_usage_log.items():
        count = int(count)
        if count > 0:
            await FishingUser.add_item(user_id, str(bait_id), "bait", count)
            refunded_bait += count

    original_start_time = status_dict["start_time"]
    time_potions_used = max(0, int(status_dict.get("time_potions_used", 0)))
    reset_status = {
        "location_id": status_dict["location_id"],
        "start_time": original_start_time,
        "last_settle_time": original_start_time,
        "fish_caught": [],
        "bait_consumed": 0,
        "frame_pity": user.frame_pity_counter,
        "cat_frame_pity": user.cat_frame_pity_counter,
        "utr_pity": user.utr_pity_counter,
        "cat_eaten_fish": [],
        "cat_gifts": default_cat_gifts() | {"cat_frame_pity": 0},
        "time_potions_used": 0,
        "bait_usage_log": {},
    }
    if status_dict.get("shadow_scene"):
        reset_status["shadow_scene"] = True
        reset_status["scene_instance_id"] = get_scene_instance_id(status_dict)
    await FishingUser.update_fishing_status(user_id, reset_status)
    if time_potions_used:
        await FishingUser.add_item(user_id, "time_potion", "potion", time_potions_used)

    from ..core.actions import check_fishing_status

    image, step = await check_fishing_status(user_id)
    if image is None:
        image = await get_status_image(user_id)

    logger.info(
        f"用户 {user_id} 使用回档药水，重置钓鱼进度，"
        f"退还时光药水 {time_potions_used} 瓶，退还鱼饵 {refunded_bait} 个"
    )
    return True, image


async def use_lucky_potion(user_id: str, count: int = 1) -> tuple[bool, str]:
    """使用幸运药水，叠加 count * 8 小时的幸运 buff。"""
    if count < 1:
        return False, "数量必须大于0"

    user = await get_or_create_user(user_id)
    lucky_item = await FishingUser.get_item(user_id, "幸运药水", "potion")
    potion_count = lucky_item["count"] if lucky_item else 0

    # 宽容机制：请求数量超出库存时，使用全部剩余
    actual_count = min(count, potion_count)
    if actual_count < 1:
        return False, "幸运药水不足，需要1瓶（当前0瓶）"

    active_potion = await _get_active_mutex_potion_name(
        user_id, BuffEffect.BUFF_TYPE_LUCKY_BOOST
    )
    if active_potion:
        return False, f"同一时间只有1种药水可以生效（{active_potion}生效中）"

    await FishingUser.remove_item(user_id, "幸运药水", "potion", actual_count)

    total_hours = actual_count * 8

    # 时间堆叠：当前存在未过期的幸运buff则 end_time += total_hours，否则新建
    existing = await FishingBuff.get_active_user_buff(
        user_id, BuffEffect.BUFF_TYPE_LUCKY_BOOST
    )
    if existing:
        existing.end_time = _make_naive(existing.end_time) + timedelta(
            hours=total_hours
        )
        await existing.save(update_fields=["end_time"])
        logger.info(
            f"用户 {user_id} 使用{actual_count}瓶幸运药水，时间堆叠至 {existing.end_time}（+{total_hours}h）"
        )
        return (
            True,
            f"幸运药水生效！钓鱼变得幸运 ⭐，剩余时间+{total_hours}小时（使用{actual_count}瓶）",
        )
    else:
        await FishingBuff.add_user_buff(
            user_id=user_id,
            buff_type=BuffEffect.BUFF_TYPE_LUCKY_BOOST,
            duration_minutes=total_hours * 60,
            value=1,
            description="幸运药水：钓鱼变得幸运",
        )
        logger.info(
            f"用户 {user_id} 使用{actual_count}瓶幸运药水，获得幸运buff（{total_hours}小时）"
        )
        return (
            True,
            f"幸运药水生效！钓鱼变得幸运 ⭐，持续{total_hours}小时（使用{actual_count}瓶）",
        )


async def use_duoduo_potion(user_id: str, count: int = 1, **kwargs) -> tuple[bool, str]:
    """真多多药水：8h内鱼竿等级-1，钓到的鱼数量翻倍；重复使用延长时间。"""
    if count < 1:
        return False, "数量必须大于0"

    user = await get_or_create_user(user_id)
    potion_item = await FishingUser.get_item(user_id, "真多多药水", "potion")
    potion_count = potion_item["count"] if potion_item else 0
    if potion_count <= 0:
        return False, "真多多药水不足，当前没有真多多药水"
    # 宽容机制：请求数量超出库存时，使用全部剩余药水
    if potion_count < count:
        count = potion_count

    active_potion = await _get_active_mutex_potion_name(
        user_id, BuffEffect.BUFF_TYPE_DUODUO
    )
    if active_potion:
        return False, f"同一时间只有1种药水可以生效（{active_potion}生效中）"

    await FishingUser.remove_item(user_id, "真多多药水", "potion", count)

    duration = timedelta(hours=8 * count)
    existing = await FishingBuff.get_active_user_buff(
        user_id, BuffEffect.BUFF_TYPE_DUODUO
    )
    if existing:
        existing.end_time = _make_naive(existing.end_time) + duration
        await existing.save(update_fields=["end_time"])
        logger.info(
            f"用户 {user_id} 使用{count}瓶真多多药水，时间堆叠至 {existing.end_time}"
        )
        return (
            True,
            f"真多多药水生效！鱼竿等级-1，鱼获数量翻倍，剩余时间+{8 * count}小时",
        )

    await FishingBuff.add_user_buff(
        user_id=user_id,
        buff_type=BuffEffect.BUFF_TYPE_DUODUO,
        duration_minutes=480 * count,
        value=1,
        description="真多多药水：鱼竿等级-1，钓到的鱼数量翻倍",
    )

    logger.info(
        f"用户 {user_id} 使用{count}瓶真多多药水，获得多多buff（{8 * count}小时）"
    )
    return True, f"真多多药水生效！鱼竿等级-1，鱼获数量翻倍，持续{8 * count}小时"


async def use_display_frame_buff(
    user_id: str, count: int = 1, is_private: bool = False, **kwargs
) -> tuple[bool, str]:
    """木框 — 普通地图与 S1 速度加成。"""
    if count < 1:
        return False, "数量必须大于0"

    user = await get_or_create_user(user_id)
    if user.display_frames <= 0:
        return False, "木框不足，当前没有木框"
    # 硬上限：不管用户请求多少个，最多使用 MAX_FRAME_BUFF_LAYERS 个
    capped = False
    if count > MAX_FRAME_BUFF_LAYERS:
        capped = True
        count = MAX_FRAME_BUFF_LAYERS
    # 宽容机制：请求数量超出库存时，使用全部剩余木框
    if user.display_frames < count:
        count = user.display_frames

    now = datetime.now()
    # 查询已有 frame buff，按 end_time 升序排列（最旧的优先延长）
    current_frame_buffs = await FishingBuff.filter(
        target_type=BuffEffect.TARGET_TYPE_GLOBAL,
        buff_type=BuffEffect.BUFF_TYPE_FRAME,
        end_time__gt=now,
    ).order_by("end_time").all()
    total_layers = len(current_frame_buffs)

    duration_hours = ConfigManager.get_nest_duration_hours()

    # 第一阶段：填满到上限（新增 buff 记录）
    layers_to_add = min(count, max(0, MAX_FRAME_BUFF_LAYERS - total_layers))
    # 第二阶段：剩余木框循环延长已有 buff（同一 buff 可被多次延长）
    remaining = count - layers_to_add
    extended_count = 0
    if remaining > 0 and current_frame_buffs:
        extended_count = remaining
        extension_delta = timedelta(hours=duration_hours)
        for i in range(remaining):
            buff = current_frame_buffs[i % len(current_frame_buffs)]
            buff.end_time = _make_naive(buff.end_time) + extension_delta
            await buff.save(update_fields=["end_time"])

    actual_frames = layers_to_add + extended_count
    if actual_frames == 0:
        return False, f"全图木框效果已满{MAX_FRAME_BUFF_LAYERS * 5}%，无法继续使用"

    await FishingUser.reduce_display_frames(user_id, actual_frames)

    for _ in range(layers_to_add):
        await FishingBuff.add_global_buff(
            buff_type=BuffEffect.BUFF_TYPE_FRAME,
            start_time=datetime.now(),
            end_time=datetime.now() + timedelta(hours=duration_hours),
            value=5,
            description=f"木框效果，1-10图与S1钓鱼速度+5%",
        )

    new_total = total_layers + layers_to_add

    added_pct = layers_to_add * 5
    total_pct = new_total * 5

    if layers_to_add > 0:
        msg = f"使用木框成功，1-10图与S1速度+{added_pct}%，持续{duration_hours}小时"
        if new_total > layers_to_add:
            msg += f"（全图累计+{total_pct}%）"
    else:
        msg = f"木框效果已满，延长了{extended_count}次已有buff（每次+{duration_hours}小时）（全图累计+{total_pct}%）"

    if layers_to_add > 0 and extended_count > 0:
        msg += f"\n已满{MAX_FRAME_BUFF_LAYERS * 5}%上限，延长了{extended_count}次已有木框buff（每次+{duration_hours}小时）"
    if actual_frames < count:
        msg += f"\n无已有木框buff可延长，仅消耗{actual_frames}个木框，{count - actual_frames}个未消耗"
    if capped:
        msg += f"\n木框使用上限为{MAX_FRAME_BUFF_LAYERS}个，已自动调整使用数量"

    logger.info(f"用户 {user_id} 使用木框{layers_to_add}层，延长{extended_count}次，当前全图{new_total}层")
    return True, msg


async def use_flash_potion(user_id: str, count: int = 1, **kwargs) -> tuple[bool, str]:
    """使用闪光药水，叠加 count * 8 小时的伽马射线暴 buff。

    生效期间视为同时拥有太阳风、流星雨、恒纪元，并使流星鱼掉率翻倍。
    """
    if count < 1:
        return False, "数量必须大于0"

    await get_or_create_user(user_id)
    flash_item = await FishingUser.get_item(user_id, "闪光药水", "potion")
    potion_count = flash_item["count"] if flash_item else 0
    actual_count = min(count, potion_count)
    if actual_count < 1:
        return False, "闪光药水不足，需要1瓶（当前0瓶）"

    active_potion = await _get_active_mutex_potion_name(
        user_id, BuffEffect.BUFF_TYPE_GAMMA_RAY_BURST
    )
    if active_potion:
        return False, f"同一时间只有1种药水可以生效（{active_potion}生效中）"

    await FishingUser.remove_item(user_id, "闪光药水", "potion", actual_count)
    total_hours = actual_count * 8

    existing = await FishingBuff.get_active_user_buff(
        user_id, BuffEffect.BUFF_TYPE_GAMMA_RAY_BURST
    )
    if existing:
        existing.end_time = _make_naive(existing.end_time) + timedelta(
            hours=total_hours
        )
        await existing.save(update_fields=["end_time"])
        logger.info(
            f"用户 {user_id} 使用{actual_count}瓶闪光药水，时间堆叠至 {existing.end_time}（+{total_hours}h）"
        )
        return (
            True,
            f"💥 闪光药水生效！伽马射线暴已叠加 +{total_hours}小时"
            f"（太阳风+流星雨+恒纪元，流星鱼掉率翻倍，使用{actual_count}瓶）",
        )

    await FishingBuff.add_user_buff(
        user_id=user_id,
        buff_type=BuffEffect.BUFF_TYPE_GAMMA_RAY_BURST,
        duration_minutes=total_hours * 60,
        value=1,
        description="闪光药水：伽马射线暴（三重天气，流星鱼掉率翻倍）",
    )
    logger.info(
        f"用户 {user_id} 使用{actual_count}瓶闪光药水，获得伽马射线暴（{total_hours}小时）"
    )
    return (
        True,
        f"💥 闪光药水生效！伽马射线暴持续{total_hours}小时"
        f"（太阳风+流星雨+恒纪元，流星鱼掉率翻倍，使用{actual_count}瓶）",
    )


def _normalize_utr_fish_name(raw: str) -> str:
    name = (raw or "").strip()
    if not name:
        return ""
    # 允许 "xxx UTR" / "xxx鱼UTR" 写法
    upper = name.upper()
    if upper.endswith(" UTR"):
        name = name[:-4].strip()
    elif upper.endswith("UTR") and len(name) > 3:
        name = name[:-3].strip()
    return name


async def _location_has_any_utr(user_id: str, location_id: str) -> bool:
    from ..config import ConfigManager

    loc = ConfigManager.get_location(location_id)
    if not loc:
        return False
    collected = await FishingUser.get_user_collected(user_id)
    for fish_name in loc.fish_pool:
        if (fish_name, "UTR") in collected:
            return True
    return False


async def use_utr_select_ticket(
    user_id: str, count: int = 1, **kwargs
) -> tuple[bool, str]:
    """使用 UTR 自选券兑换指定 UTR 鱼。

    用法：钓鱼使用 UTR自选券 鱼名
    条件：目标鱼所在地图已解锁至少 1 条 UTR。
    """
    fish_name = _normalize_utr_fish_name(
        str(kwargs.get("arg") or kwargs.get("extra") or kwargs.get("target") or "")
    )
    if not fish_name:
        return (
            False,
            "请指定要兑换的 UTR 鱼名！\n"
            "格式：钓鱼使用 UTR自选券 鱼名\n"
            "条件：该鱼所在地图需已解锁至少 1 条 UTR",
        )

    await get_or_create_user(user_id)
    ticket = await FishingUser.get_item(user_id, "utr_select_ticket", "ticket")
    ticket_count = ticket["count"] if ticket else 0
    if ticket_count < 1:
        return False, "UTR自选券不足（当前0张）"

    from ..backpack.black_market import find_fish_target
    from ..core.result import add_fish_to_user

    target = find_fish_target(fish_name, "UTR")
    if not target:
        # 尝试模糊：去掉/补上“鱼”后缀
        alt = fish_name[:-1] if fish_name.endswith("鱼") else f"{fish_name}鱼"
        target = find_fish_target(alt, "UTR")
        if target:
            fish_name = alt
    if not target:
        return (
            False,
            f"未找到鱼种「{fish_name}」，请输入正确的鱼名（如地图中的 UTR 鱼）",
        )

    if not await _location_has_any_utr(user_id, target.location_id):
        return (
            False,
            f"无法兑换：需要先在【{target.location_name}】解锁至少 1 条 UTR 鱼后，"
            f"才能用自选券兑换该图的 UTR（目标：{target.name}）",
        )

    ok = await FishingUser.remove_item(user_id, "utr_select_ticket", "ticket", 1)
    if not ok:
        return False, "UTR自选券扣除失败，请重试"

    result = await add_fish_to_user(
        user_id,
        [(target.name, "UTR", target.numeric_id, 1)],
        effective_difficulty=max(0, target.scene_level - 1),
        check_achievements=True,
        auto_display=True,
    )
    msgs = list(result.get("messages") or [])
    ach = list(result.get("achievement_messages") or [])
    lines = [
        f"🎫 UTR自选券兑换成功！获得 {target.name} UTR（{target.location_name}）",
    ]
    lines.extend(msgs)
    lines.extend(ach)
    if result.get("fish_coins"):
        lines.append(f"💰 计入鱼获价值 {result['fish_coins']} 钓鱼币（未自动卖出）")
    logger.info(
        f"用户 {user_id} 使用UTR自选券兑换 {target.name} UTR @ {target.location_id}"
    )
    return True, "\n".join(lines)
