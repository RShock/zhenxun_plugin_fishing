"""
钓鱼场景渲染准备 — 收集同场景玩家、组装场景数据、渲染钓鱼场景。
"""

from datetime import datetime

from zhenxun.services.log import logger

from ..cat_park import is_cat_park_location
from ..config import LocationData
from ..models import BuffEffect, FishingBuff, FishingUser, FishingWeather, _make_naive
from ..render import render_fishing_scene
from ..scene_instance import get_scene_instance_id
from ..weather_service import get_location_weather
from .bait import get_bait_info
from .probability import calculate_display_probabilities


async def collect_scene_players(
    scene_instance_id: str, group_id: str | None
) -> list[dict]:
    """收集同一钓场的在线玩家列表。"""
    fisher_ids = await FishingUser.get_location_fishers(scene_instance_id)

    if group_id:
        try:
            from nonebot import get_bot

            bot = get_bot()
            members = await bot.call_api(
                "get_group_member_list", group_id=int(group_id)
            )
            group_member_ids = {str(m["user_id"]) for m in members}
            fisher_ids = [fid for fid in fisher_ids if fid in group_member_ids]
        except Exception as e:
            logger.warning(f"获取群成员列表失败，显示所有同地图玩家: {e}")

    players = []
    now = datetime.now()
    for fid in fisher_ids:
        fuser = await FishingUser.get_user(fid)
        if len(fisher_ids) > 8:
            status = await FishingUser.get_status(fid)
            if status:
                start = _make_naive(datetime.fromisoformat(status["start_time"]))
                if (now - start).total_seconds() > 3 * 86400:
                    continue
        players.append(
            {
                "user_id": fid,
                "nickname": fuser.nickname or fid,
                "skin_id": str(fuser.skin_id) if fuser.skin_id else "1",
            }
        )
    return players


async def render_scene(
    user_id: str,
    location: LocationData,
    hints: list[str] | None = None,
    group_id: str | None = None,
) -> bytes:
    """渲染钓鱼主场景图片。"""
    import time as _time

    t0 = _time.perf_counter()

    status_dict = await FishingUser.get_status(user_id)
    scene_instance_id = get_scene_instance_id(status_dict, location.id)
    players = await collect_scene_players(scene_instance_id, group_id)
    weather_info = await get_location_weather(location.id, user_id)

    # 迷途风互斥可见性
    raw_weather = await FishingWeather.get_today_weather(location.id)
    if raw_weather and raw_weather.weather_type == "lost_wind":
        is_lost_wind_active = (
            raw_weather.start_time is not None
            and raw_weather.end_time is not None
            and _make_naive(raw_weather.start_time)
            <= datetime.now()
            < _make_naive(raw_weather.end_time)
        )
        if is_lost_wind_active:
            current_user_unlocked = await FishingUser.has_unlocked_lost_wind(
                user_id, location.id
            )
            filtered = []
            for p in players:
                p_unlocked = await FishingUser.has_unlocked_lost_wind(
                    p["user_id"], location.id
                )
                if p_unlocked == current_user_unlocked:
                    filtered.append(p)
            players = filtered

    nest_speed_bonus = await FishingBuff.get_location_buff_count(scene_instance_id)
    nest_speed_bonus = nest_speed_bonus * 5

    frame_speed_bonus = await FishingBuff.get_frame_buff_count_for_location(location.id)
    frame_speed_bonus = frame_speed_bonus * 5

    total_speed_bonus = nest_speed_bonus + frame_speed_bonus

    now = datetime.now()
    weekend_buff = await FishingBuff.filter(
        target_type=BuffEffect.TARGET_TYPE_GLOBAL,
        buff_type=BuffEffect.BUFF_TYPE_WEEKEND_BONUS,
        start_time__lte=now,
        end_time__gte=now,
    ).first()
    weekend_bonus = weekend_buff.value if weekend_buff else 0

    user = await FishingUser.get_user(user_id)
    bait_name, bait_count, bait_speed_bonus = await get_bait_info(user_id, user)
    fishing_power = user.rod_level - location.difficulty
    probability_max_rarity = location.max_rarity
    from ..starry import is_starry_location

    if is_starry_location(location.id) and f"collect_scene_{location.id}" not in (
        user.achievements or []
    ):
        probability_max_rarity = "UR"

    # S1 材料率（随猫爬架广场等级动态变化）
    material_rate = 0.0
    if is_cat_park_location(location.id):
        from ..cat_park import get_cat_park_effect_values, get_cat_park_state

        state = await get_cat_park_state(user_id)
        material_rate = get_cat_park_effect_values(state).get("material_rate", 0.0)

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

    buffs = []
    fishing_start_time = None
    if status_dict:
        start_time = _make_naive(datetime.fromisoformat(status_dict["start_time"]))
        fishing_start_time = start_time
        buffs = await FishingBuff.get_active_buffs_for_fishing(
            user_id,
            location.id,
            start_time,
            now,
            location_buff_target_id=scene_instance_id,
        )
        if buffs:
            from ..models import FishingBuffCalculator

            effects = FishingBuffCalculator.get_effects_at_time(
                buffs, now, user.rod_level, bait_speed_bonus, location.difficulty
            )
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
            )

    t1 = _time.perf_counter()

    image = await render_fishing_scene(
        location,
        players,
        user_id,
        hints=hints,
        nest_speed_bonus=total_speed_bonus,
        bait_name=bait_name,
        bait_count=bait_count,
        fishing_power=fishing_power,
        weekend_bonus=weekend_bonus,
        probabilities=probabilities,
        buffs=buffs,
        fishing_start_time=fishing_start_time,
        now_time=now,
        hook_level=user.hook_level,
        weather_info=weather_info,
        material_rate=material_rate,
        scene_inverted=bool(status_dict and status_dict.get("shadow_scene")),
    )

    t2 = _time.perf_counter()
    logger.info(
        f"[fishing_scene] user={user_id} db={t1 - t0:.3f}s render={t2 - t1:.3f}s total={t2 - t0:.3f}s"
    )

    return image
