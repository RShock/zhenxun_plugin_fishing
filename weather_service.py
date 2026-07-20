import asyncio
import random
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .config import ConfigManager
from .models import BuffEffect, FishingBuff, FishingUser, FishingWeather, _make_naive
from .starry import is_starry_location

WEATHER_NORMAL_TYPES = ["rain", "meteor", "storm", "cat"]
WEATHER_NORMAL_CHANCE = 0.5
WEATHER_LOST_WIND_COUNT = 3
WEATHER_MIN_HOURS = 6
WEATHER_MAX_HOURS = 18

_TZ = ZoneInfo("Asia/Shanghai")
_weather_lock = asyncio.Lock()


async def _is_starry_bonus_maxed() -> bool:
    """检查星空艇加成是否已达10层上限（迷途风替换晴天条件）。"""
    from .starry import get_starry_bonus_count, STARRY_MAX_LAYERS

    return await get_starry_bonus_count() >= STARRY_MAX_LAYERS


def _format_hour(dt, is_end: bool = False) -> str:
    h = dt.hour
    if is_end and h == 0:
        return "24"
    return str(h)


def _now_local() -> datetime:
    return datetime.now(_TZ).replace(tzinfo=None)


def _today_local() -> date:
    return datetime.now(_TZ).date()


def _weather_date_at(at_time: datetime) -> date:
    """返回指定时刻所属天气日的数据库日期。"""
    local_time = at_time.astimezone(_TZ).replace(tzinfo=None) if at_time.tzinfo else at_time
    if local_time.hour >= 23:
        return local_time.date()
    return local_time.date() - timedelta(days=1)


def _weather_date() -> date:
    """返回当前天气日对应的数据库日期。"""
    return _weather_date_at(datetime.now(_TZ))


async def ensure_weather_generated() -> bool:
    """确保当前天气日的天气已生成（加锁防并发）。"""
    async with _weather_lock:
        if await FishingWeather.is_generated_today():
            return False
        result = await generate_daily_weather()
        await generate_s1_weather()
        await generate_starry_weather()
        return result


async def generate_s1_weather() -> bool:
    """S1 猫猫乐园独立天气生成：50% 迷途风 / 40% 其他天气（各10%）/ 10% 晴天。

    S1 不参与全局天气分配，每天独立 roll。
    """
    from .cat_park import CAT_PARK_LOCATION_ID

    today = _weather_date()
    today_23pm = datetime.combine(today, time(23, 0))
    tomorrow_23pm = today_23pm + timedelta(days=1)

    # 检查 S1 今日是否已生成（用 date 字段，避免 sunny 的 start_time=None 被遗漏）
    existing = await FishingWeather.filter(
        location_id=CAT_PARK_LOCATION_ID,
        date=today,
    ).first()
    if existing:
        return False

    roll = random.random()
    # 星空艇满层时，晴天替换为迷途风
    starry_maxed = await _is_starry_bonus_maxed()
    if starry_maxed and roll < 0.10:
        # 原10%晴天变为迷途风
        weather_type = "lost_wind"
        start_time = today_23pm
        end_time = tomorrow_23pm
    elif roll < 0.10:
        # 10% 晴天
        weather_type = "sunny"
        start_time = None
        end_time = None
    elif roll < 0.50:
        # 40% 其他天气（rain/meteor/storm/cat 各 10%）
        weather_type = random.choice(WEATHER_NORMAL_TYPES)
        duration_hours = random.randint(WEATHER_MIN_HOURS, WEATHER_MAX_HOURS)
        latest_start_hour = 24 - duration_hours
        start_hour = random.randint(0, latest_start_hour)
        start_time = today_23pm + timedelta(hours=start_hour)
        end_time = start_time + timedelta(hours=duration_hours)
    else:
        # 50% 迷途风（全天）
        weather_type = "lost_wind"
        start_time = today_23pm
        end_time = tomorrow_23pm

    await FishingWeather.get_or_create(
        location_id=CAT_PARK_LOCATION_ID,
        date=today,
        defaults={
            "weather_type": weather_type,
            "start_time": start_time,
            "end_time": end_time,
        },
    )

    if weather_type != "sunny" and start_time and end_time:
        buff_type_map = {
            "rain": BuffEffect.BUFF_TYPE_WEATHER_RAIN,
            "meteor": BuffEffect.BUFF_TYPE_WEATHER_METEOR,
            "storm": BuffEffect.BUFF_TYPE_WEATHER_STORM,
            "lost_wind": BuffEffect.BUFF_TYPE_WEATHER_LOST_WIND,
            "cat": BuffEffect.BUFF_TYPE_WEATHER_CAT,
        }
        desc_map = {
            "rain": "雨天：上鱼速度+10%",
            "meteor": "流星：最高稀有度基础值+2%",
            "storm": "暴雨：鱼饵消耗减半",
            "lost_wind": "迷途风：传说鱼出没",
            "cat": "猫！：会吃鱼！",
        }
        value_map = {
            "rain": 10,
            "meteor": 2,
            "storm": 1,
            "lost_wind": 1,
            "cat": 1,
        }
        await FishingBuff.add_buff(
            buff_type=buff_type_map[weather_type],
            start_time=start_time,
            end_time=end_time,
            value=value_map[weather_type],
            description=desc_map[weather_type],
            target_type=BuffEffect.TARGET_TYPE_LOCATION,
            target_id=CAT_PARK_LOCATION_ID,
        )

    return True


async def generate_starry_weather() -> bool:
    """星空地图独立天气：5 张额外天气 + 5 张乱纪元。

    乱纪元的显示始终不变；其实际效果由玩家在该图的 UR 收集状态决定：
    未完成时按晴天处理，完成后在结算层按迷途风处理。
    """
    from .starry import STARRY_LOCATION_IDS

    today = _weather_date()
    today_23pm = datetime.combine(today, time(23, 0))
    tomorrow_23pm = today_23pm + timedelta(days=1)
    generated = False
    # 每天 5 张星空图有额外天气，另 5 张为乱纪元；不再出现迷途风
    starry_count = len(STARRY_LOCATION_IDS)
    special_count = min(5, starry_count)
    weather_types = [
        random.choice(["solar_wind", "meteor_shower", "hengjiyuan"])
        for _ in range(special_count)
    ] + ["chaotic_era"] * (starry_count - special_count)
    random.shuffle(weather_types)

    for location_id in sorted(STARRY_LOCATION_IDS, key=int):
        existing = await FishingWeather.filter(
            location_id=location_id,
            date=today,
        ).first()
        if existing:
            continue

        weather_type = weather_types.pop()
        start_time = today_23pm
        end_time = tomorrow_23pm

        await FishingWeather.get_or_create(
            location_id=location_id,
            date=today,
            defaults={
                "weather_type": weather_type,
                "start_time": start_time,
                "end_time": end_time,
            },
        )

        buff_type_map = {
            "solar_wind": BuffEffect.BUFF_TYPE_WEATHER_SOLAR_WIND,
            "meteor_shower": BuffEffect.BUFF_TYPE_WEATHER_METEOR_SHOWER,
            "hengjiyuan": BuffEffect.BUFF_TYPE_WEATHER_HENGJIYUAN,
        }
        value_map = {
            "solar_wind": 2.5,
            "meteor_shower": 1,
            "hengjiyuan": 1,
        }
        desc_map = {
            "solar_wind": "太阳风：流星鱼出现率恒定+2.5%",
            "meteor_shower": "流星雨：星空鱼变得幸运",
            "hengjiyuan": "恒纪元：流星鱼数字限定为2-8",
        }

        if weather_type in buff_type_map and start_time and end_time:
            await FishingBuff.add_buff(
                buff_type=buff_type_map[weather_type],
                start_time=start_time,
                end_time=end_time,
                value=value_map[weather_type],
                description=desc_map[weather_type],
                target_type=BuffEffect.TARGET_TYPE_LOCATION,
                target_id=location_id,
            )
        generated = True

    return generated


async def generate_daily_weather() -> bool:
    today = _weather_date()
    today_23pm = datetime.combine(today, time(23, 0))
    tomorrow_23pm = today_23pm + timedelta(days=1)

    existing = await FishingWeather.filter(date=today).all()
    existing_locs = {w.location_id for w in existing}

    locations = ConfigManager.get_locations()
    generated = False

    # S1 猫猫乐园和星空地图独立生成天气，跳过全局分配
    from .cat_park import is_cat_park_location
    from .starry import is_starry_location

    ungenerated = [
        loc
        for loc in locations
        if loc.id not in existing_locs
        and not is_cat_park_location(loc.id)
        and not is_starry_location(loc.id)
    ]
    if not ungenerated:
        return False

    # 全局天气只考虑非 S1、非星空地点
    normal_locations = [
        loc
        for loc in locations
        if not is_cat_park_location(loc.id) and not is_starry_location(loc.id)
    ]
    total_locs = len(normal_locations)
    normal_weather_count = total_locs // 2
    existing_normal_count = sum(
        1 for w in existing if w.weather_type in WEATHER_NORMAL_TYPES
    )
    remaining_normal = max(0, normal_weather_count - existing_normal_count)

    existing_lost_wind_locs = {
        w.location_id for w in existing if w.weather_type == "lost_wind"
    }

    normal_weather_locs = set()
    if remaining_normal > 0:
        candidates = [loc for loc in ungenerated]
        if len(candidates) <= remaining_normal:
            normal_weather_locs = {loc.id for loc in candidates}
        else:
            chosen = random.sample(candidates, remaining_normal)
            normal_weather_locs = {loc.id for loc in chosen}

    # 星空艇满层时，迷途风替换所有晴天（5张图），否则使用固定数量
    starry_maxed = await _is_starry_bonus_maxed()
    effective_lost_wind_count = (
        total_locs - normal_weather_count if starry_maxed else WEATHER_LOST_WIND_COUNT
    )

    lost_wind_locs = set()
    lost_wind_candidates = [
        loc
        for loc in ungenerated
        if loc.id not in normal_weather_locs and loc.id not in existing_lost_wind_locs
    ]
    remaining_lost_wind = max(0, effective_lost_wind_count - len(existing_lost_wind_locs))
    if remaining_lost_wind > 0 and lost_wind_candidates:
        if len(lost_wind_candidates) <= remaining_lost_wind:
            lost_wind_locs = {loc.id for loc in lost_wind_candidates}
        else:
            chosen = random.sample(lost_wind_candidates, remaining_lost_wind)
            lost_wind_locs = {loc.id for loc in chosen}

    for loc in ungenerated:
        today_23pm = datetime.combine(today, time(23, 0))
        tomorrow_23pm = today_23pm + timedelta(days=1)

        weather_type = "sunny"
        start_time = None
        end_time = None

        if loc.id in normal_weather_locs:
            weather_type = random.choice(WEATHER_NORMAL_TYPES)
            duration_hours = random.randint(WEATHER_MIN_HOURS, WEATHER_MAX_HOURS)

            latest_start_hour = 24 - duration_hours
            start_hour = random.randint(0, latest_start_hour)

            start_time = today_23pm + timedelta(hours=start_hour)
            end_time = start_time + timedelta(hours=duration_hours)
        elif loc.id in lost_wind_locs:
            weather_type = "lost_wind"
            start_time = today_23pm
            end_time = tomorrow_23pm
        elif starry_maxed:
            # 星空艇满层时，剩余晴天全部替换为迷途风
            weather_type = "lost_wind"
            start_time = today_23pm
            end_time = tomorrow_23pm

        await FishingWeather.get_or_create(
            location_id=loc.id,
            date=today,
            defaults={
                "weather_type": weather_type,
                "start_time": start_time,
                "end_time": end_time,
            },
        )

        if weather_type != "sunny" and start_time and end_time:
            buff_type_map = {
                "rain": BuffEffect.BUFF_TYPE_WEATHER_RAIN,
                "meteor": BuffEffect.BUFF_TYPE_WEATHER_METEOR,
                "storm": BuffEffect.BUFF_TYPE_WEATHER_STORM,
                "lost_wind": BuffEffect.BUFF_TYPE_WEATHER_LOST_WIND,
                "cat": BuffEffect.BUFF_TYPE_WEATHER_CAT,
            }
            desc_map = {
                "rain": "雨天：上鱼速度+10%",
                "meteor": "流星：最高稀有度基础值+2%",
                "storm": "暴雨：鱼饵消耗减半",
                "lost_wind": "迷途风：传说鱼出没",
                "cat": "猫！：会吃鱼！",
            }
            value_map = {
                "rain": 10,
                "meteor": 2,
                "storm": 1,
                "lost_wind": 1,
                "cat": 1,
            }
            await FishingBuff.add_buff(
                buff_type=buff_type_map[weather_type],
                start_time=start_time,
                end_time=end_time,
                value=value_map[weather_type],
                description=desc_map[weather_type],
                target_type=BuffEffect.TARGET_TYPE_LOCATION,
                target_id=loc.id,
            )

        generated = True

    return generated


async def get_chaotic_era_windows(
    location_id: str, start_time: datetime, end_time: datetime
) -> list[tuple[datetime, datetime]]:
    """返回结算区间内实际生效的乱纪元窗口。"""
    if not is_starry_location(location_id) or start_time >= end_time:
        return []

    start = _make_naive(start_time)
    end = _make_naive(end_time)
    weather_dates: list[date] = []
    cursor = _weather_date_at(start)
    last_date = _weather_date_at(end - timedelta(microseconds=1))
    while cursor <= last_date:
        weather_dates.append(cursor)
        cursor += timedelta(days=1)

    weathers = await FishingWeather.filter(
        location_id=location_id,
        date__in=weather_dates,
        weather_type="chaotic_era",
    ).all()
    windows: list[tuple[datetime, datetime]] = []
    for weather in weathers:
        weather_start = _make_naive(weather.start_time) if weather.start_time else start
        weather_end = _make_naive(weather.end_time) if weather.end_time else end
        overlap_start = max(start, weather_start)
        overlap_end = min(end, weather_end)
        if overlap_start < overlap_end:
            windows.append((overlap_start, overlap_end))
    return sorted(windows)


async def is_chaotic_era_active(
    location_id: str, at_time: datetime | None = None
) -> bool:
    """判断指定星空图当前是否处于乱纪元（仅判断显示天气，不含玩家解锁）。"""
    if not is_starry_location(location_id):
        return False
    check_time = _make_naive(at_time or _now_local())
    weather = await FishingWeather.filter(
        location_id=location_id,
        date=_weather_date_at(check_time),
        weather_type="chaotic_era",
    ).first()
    if not weather:
        return False
    start = _make_naive(weather.start_time) if weather.start_time else None
    end = _make_naive(weather.end_time) if weather.end_time else None
    return (start is None or check_time >= start) and (
        end is None or check_time < end
    )


async def get_location_weather(
    location_id: str, user_id: str | None = None
) -> dict | None:
    weather = await FishingWeather.get_today_weather(location_id)
    if not weather:
        # 星空地图无天气记录时显示「乱纪元」而非「晴天」
        default_type = "chaotic_era" if is_starry_location(location_id) else "sunny"
        return {
            "location_id": location_id,
            "weather_type": default_type,
            "is_active": False,
            "weather_status": "ended",
            "start_time": None,
            "end_time": None,
        }

    now = _now_local()
    is_active = False
    weather_status = "ended"
    if weather.weather_type != "sunny" and weather.start_time and weather.end_time:
        st = _make_naive(weather.start_time)
        et = _make_naive(weather.end_time)
        if st <= now < et:
            is_active = True
            weather_status = "active"
        elif now < st:
            weather_status = "pending"

    visible_type = weather.weather_type
    if weather.weather_type == "lost_wind":
        if user_id:
            unlocked = await FishingUser.has_unlocked_lost_wind(user_id, location_id)
            if not unlocked:
                visible_type = "sunny"
                is_active = False
        else:
            visible_type = "sunny"
            is_active = False

    # 星空地图未解锁迷途风时显示「乱纪元」而非「晴天」
    if is_starry_location(location_id) and visible_type == "sunny":
        visible_type = "chaotic_era"

    _is_inactive = visible_type in ("sunny", "chaotic_era")
    return {
        "location_id": location_id,
        "weather_type": visible_type,
        "is_active": is_active,
        "weather_status": weather_status if not _is_inactive else "ended",
        "start_time": weather.start_time if not _is_inactive else None,
        "end_time": weather.end_time if not _is_inactive else None,
    }


async def get_all_location_weathers(
    user_id: str | None = None,
) -> dict[str, dict]:
    weathers = await FishingWeather.get_all_today_weathers()
    now = _now_local()
    result = {}
    for loc_id, w in weathers.items():
        is_active = False
        weather_status = "ended"
        if w.weather_type != "sunny" and w.start_time and w.end_time:
            st = _make_naive(w.start_time)
            et = _make_naive(w.end_time)
            if st <= now < et:
                is_active = True
                weather_status = "active"
            elif now < st:
                weather_status = "pending"

        visible_type = w.weather_type
        if w.weather_type == "lost_wind":
            if user_id:
                unlocked = await FishingUser.has_unlocked_lost_wind(user_id, loc_id)
                if not unlocked:
                    visible_type = "sunny"
                    is_active = False
            else:
                visible_type = "sunny"
                is_active = False

        # 星空地图未解锁迷途风时显示「乱纪元」而非「晴天」
        if is_starry_location(loc_id) and visible_type == "sunny":
            visible_type = "chaotic_era"

        _is_inactive = visible_type in ("sunny", "chaotic_era")
        result[loc_id] = {
            "location_id": loc_id,
            "weather_type": visible_type,
            "is_active": is_active,
            "weather_status": weather_status if not _is_inactive else "ended",
            "start_time": w.start_time if not _is_inactive else None,
            "end_time": w.end_time if not _is_inactive else None,
        }
    return result
