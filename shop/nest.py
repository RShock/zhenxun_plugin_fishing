"""
打窝系统 — 玉米打窝、猫猫框打窝。
"""

from datetime import datetime

from zhenxun.services.log import logger

from ..config import DAILY_NEST_LIMIT, MAX_NEST_LAYERS, ConfigManager
from ..models import BuffEffect, FishingBuff, FishingUser
from ..services import get_or_create_user


async def do_nest(
    user_id: str, corn_count: int = 1, is_private: bool = False, **kwargs
) -> tuple[bool, str]:
    status = await FishingUser.get_status(user_id)
    if not status:
        return False, "你还没有在钓鱼，无法打窝！请先【钓鱼 地点编号】开始钓鱼"

    location_id = status["location_id"]
    location = ConfigManager.get_location(location_id)
    if not location:
        return False, "当前钓鱼地点无效"

    if not is_private:
        nest_count = await FishingUser.get_nest_count(user_id)
        if nest_count >= DAILY_NEST_LIMIT:
            return False, "今天已经不能再打窝了"

    user = await get_or_create_user(user_id)
    if user.corn <= 0:
        return False, "香甜玉米不足，当前没有玉米，无法打窝"
    # 宽容机制：请求数量超出库存时，使用全部剩余玉米
    original_request = corn_count
    corn_adjusted = False
    if user.corn < corn_count:
        corn_count = user.corn
        corn_adjusted = True

    # 星空艇加成（1-10 图 + S1 生效）与玉米打窝共享 50% 上限
    from ..starry import STARRY_BONUS_VALUE, get_starry_bonus_count, is_starry_location

    starry_bonus_layers = 0
    if not is_starry_location(location_id):
        starry_bonus_layers = await get_starry_bonus_count()
    available_layers = max(0, MAX_NEST_LAYERS - starry_bonus_layers)

    current_nest_buffs = await FishingBuff.filter(
        target_type=BuffEffect.TARGET_TYPE_LOCATION,
        target_id=location_id,
        buff_type=BuffEffect.BUFF_TYPE_NEST,
        end_time__gt=datetime.now(),
    ).all()
    total_layers = len(current_nest_buffs)
    if total_layers >= available_layers:
        starry_pct = starry_bonus_layers * STARRY_BONUS_VALUE
        if starry_bonus_layers > 0:
            return (
                False,
                f"当前地点速度加成已满{MAX_NEST_LAYERS * 5}%"
                f"（星空艇加速 +{starry_pct}%，玉米打窝 +{total_layers * 5}%），无法继续打窝",
            )
        return False, f"当前地点打窝效果已满{MAX_NEST_LAYERS * 5}%，无法继续打窝"

    layers_to_add = min(corn_count, available_layers - total_layers)
    actual_corn = layers_to_add

    await FishingUser.reduce_corn(user_id, actual_corn)

    duration_hours = ConfigManager.get_nest_duration_hours()
    for _ in range(layers_to_add):
        await FishingBuff.add_location_buff(
            location_id=location_id,
            buff_type=BuffEffect.BUFF_TYPE_NEST,
            duration_hours=duration_hours,
            value=5,
            description=f"打窝效果，{location.name}钓鱼速度+5%",
            source_user_id=user_id,
        )

    new_total = total_layers + layers_to_add
    if not is_private:
        nest_day_count, is_last = await FishingUser.increment_nest_count(user_id)
    else:
        is_last = False

    added_pct = layers_to_add * 5
    total_pct = new_total * 5
    starry_pct = starry_bonus_layers * STARRY_BONUS_VALUE
    msg = f"在【{location.name}】打窝成功，速度+{added_pct}%，持续{duration_hours}小时"
    if new_total > layers_to_add:
        if starry_bonus_layers > 0:
            msg += f"（玉米累计 +{total_pct}%，星空艇加速 +{starry_pct}%，合计 +{total_pct + starry_pct}%）"
        else:
            msg += f"（该地点累计+{total_pct}%）"
    if actual_corn < corn_count:
        msg += f"\n已达到{MAX_NEST_LAYERS * 5}%上限（与星空艇加速共享），仅消耗{actual_corn}个玉米，{corn_count - actual_corn}个玉米未消耗"
    if corn_adjusted:
        msg += f"\n玉米不足请求的{original_request}个，已使用全部剩余{corn_count}个玉米打窝"
    if not is_private and is_last:
        msg += "\n今天已经不能再打窝"

    logger.info(
        f"用户 {user_id} 在{location.name}打窝{layers_to_add}层，当前玉米{new_total}层，星空艇{starry_bonus_layers}层"
    )
    return True, msg


async def do_cat_frame_nest(
    user_id: str, frame_count: int = 1, is_private: bool = False, **kwargs
) -> tuple[bool, str]:
    """猫猫框打窝 — 仅可在 11-20 星空图使用，地点级速度加成。"""
    if frame_count < 1:
        return False, "数量必须大于0"

    status = await FishingUser.get_status(user_id)
    if not status:
        return False, "你还没有在钓鱼，无法使用猫猫框打窝！请先【钓鱼 地点编号】开始钓鱼"

    location_id = status["location_id"]
    location = ConfigManager.get_location(location_id)
    if not location:
        return False, "当前钓鱼地点无效"

    from ..starry import is_starry_location

    if not is_starry_location(location_id):
        return False, "猫猫框打窝只能在 11-20 星空图使用"

    if not is_private:
        nest_count = await FishingUser.get_nest_count(user_id)
        if nest_count >= DAILY_NEST_LIMIT:
            return False, "今天已经不能再打窝了"

    user = await get_or_create_user(user_id)
    if user.cat_frames <= 0:
        return False, "猫猫框不足，当前没有猫猫框，无法打窝"

    original_request = frame_count
    frame_adjusted = False
    if user.cat_frames < frame_count:
        frame_count = user.cat_frames
        frame_adjusted = True

    current_nest_buffs = await FishingBuff.filter(
        target_type=BuffEffect.TARGET_TYPE_LOCATION,
        target_id=location_id,
        buff_type=BuffEffect.BUFF_TYPE_NEST,
        end_time__gt=datetime.now(),
    ).all()
    total_layers = len(current_nest_buffs)
    if total_layers >= MAX_NEST_LAYERS:
        return False, f"当前地点打窝效果已满{MAX_NEST_LAYERS * 5}%，无法继续打窝"

    layers_to_add = min(frame_count, MAX_NEST_LAYERS - total_layers)
    actual_frames = layers_to_add

    await FishingUser.reduce_cat_frames(user_id, actual_frames)

    duration_hours = ConfigManager.get_nest_duration_hours()
    for _ in range(layers_to_add):
        await FishingBuff.add_location_buff(
            location_id=location_id,
            buff_type=BuffEffect.BUFF_TYPE_NEST,
            duration_hours=duration_hours,
            value=5,
            description=f"猫猫框打窝效果，{location.name}钓鱼速度+5%",
            source_user_id=user_id,
        )

    new_total = total_layers + layers_to_add
    if not is_private:
        _, is_last = await FishingUser.increment_nest_count(user_id)
    else:
        is_last = False

    added_pct = layers_to_add * 5
    total_pct = new_total * 5
    msg = (
        f"在【{location.name}】使用猫猫框打窝成功，速度+{added_pct}%，"
        f"持续{duration_hours}小时"
    )
    if new_total > layers_to_add:
        msg += f"（该地点累计+{total_pct}%）"
    if actual_frames < frame_count:
        msg += (
            f"\n已达到{MAX_NEST_LAYERS * 5}%上限，仅消耗{actual_frames}个猫猫框，"
            f"{frame_count - actual_frames}个未消耗"
        )
    if frame_adjusted:
        msg += (
            f"\n猫猫框不足请求的{original_request}个，"
            f"已使用全部剩余{frame_count}个猫猫框打窝"
        )
    if not is_private and is_last:
        msg += "\n今天已经不能再打窝"

    logger.info(
        f"用户 {user_id} 在{location.name}使用猫猫框打窝{layers_to_add}层，当前{new_total}层"
    )
    return True, msg
