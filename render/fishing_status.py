from dataclasses import dataclass
from datetime import datetime, timedelta
import time

from ..config import calculate_fish_price
from ..models import BuffEffect
from .base import (
    build_fish_list_data,
    build_meteor_fish_items,
    gradient_bg,
    render_html,
    render_template,
    save_debug_output,
)

RARITY_DISPLAY = [
    ("N", "普通", "#9e9e9e"),
    ("R", "稀有", "#2196f3"),
    ("SR", "超稀有", "#9c27b0"),
    ("SSR", "超超稀有", "#ff9800"),
    ("UR", "极度稀有", "#f44336"),
    ("UTR", "传说", "#e91e63"),
]

# buff 时间轴颜色和标签从 BuffEffect.BUFF_REGISTRY 派生（单一数据源），
# 新建 buff 时只需在 BUFF_REGISTRY 注册，此处自动同步，无需手动维护。
BUFF_TIMELINE_COLORS = {
    meta.key: (meta.color, meta.display_name)
    for meta in BuffEffect.BUFF_REGISTRY.values()
}


def _to_local_naive(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        try:
            return dt.astimezone().replace(tzinfo=None)
        except (OSError, OverflowError, ValueError):
            # 远期日期（如永久 buff 的 9999/2099 年）在 Windows 上无法转为
            # Unix 时间戳，astimezone() 会抛 OSError。此时时区偏移对渲染无
            # 意义（该值会被 min(buff_end, local_end) 截断），直接剥离
            # tzinfo 即可，与 _make_naive() 行为一致。
            return dt.replace(tzinfo=None)
    return dt


def _calculate_time_markers(local_start: datetime, local_end: datetime) -> list[dict]:
    total_seconds = (local_end - local_start).total_seconds()
    if total_seconds <= 0:
        return [{"position_pct": 0, "label": f"{local_start.hour}时"}]

    start_hour = local_start.hour
    end_hour = local_end.hour
    start_day = local_start.date()
    end_day = local_end.date()

    start_hours_total = start_hour
    if end_day > start_day:
        delta_days = (end_day - start_day).days
        end_hours_total = delta_days * 24 + end_hour
    else:
        end_hours_total = end_hour
        if end_hour < start_hour:
            end_hours_total += 24

    total_hours = total_seconds / 3600

    nice_intervals = [1, 2, 3, 4, 6, 8, 12, 24]
    target_count = 5
    raw_interval = total_hours / target_count
    interval = min(nice_intervals, key=lambda x: abs(x - raw_interval))
    if interval < 1:
        interval = 1

    markers = []
    current = start_hours_total
    while current <= end_hours_total:
        markers.append(current)
        current += interval
    if markers[-1] != end_hours_total:
        markers.append(end_hours_total)
    markers = sorted(set(markers))

    result = []
    for h in markers:
        pct = (h - start_hours_total) / total_hours * 100
        if pct < -0.5 or pct > 100.5:
            continue
        pct = max(0, min(100, pct))
        display_h = h % 24
        result.append({"position_pct": round(pct, 2), "label": f"{display_h:02d}点"})

    return result


@dataclass(frozen=True)
class _TimelineWindow:
    start: datetime
    end: datetime
    fishing_start_pct: float | None
    current_time_pct: float | None


def _position_pct(moment: datetime, start: datetime, end: datetime) -> float | None:
    if not start <= moment <= end:
        return None
    total = (end - start).total_seconds()
    if total <= 0:
        return None
    offset = (moment - start).total_seconds()
    return round(max(0, min(100, offset / total * 100)), 2)


def _timeline_window(
    fishing_start: datetime, now: datetime, end_time: datetime | None
) -> _TimelineWindow:
    if end_time is not None:
        return _TimelineWindow(fishing_start, _to_local_naive(end_time), 0.0, None)
    start = fishing_start - timedelta(hours=1)
    end = now + timedelta(hours=8)
    return _TimelineWindow(
        start,
        end,
        _position_pct(fishing_start, start, end),
        _position_pct(now, start, end),
    )


def _group_buffs(buffs: list) -> tuple[list[str], dict[str, list]]:
    order: list[str] = []
    grouped: dict[str, list] = {}
    for buff in buffs:
        if buff.buff_type not in grouped:
            order.append(buff.buff_type)
            grouped[buff.buff_type] = []
        grouped[buff.buff_type].append(buff)
    return order, grouped


def _buff_segments(buffs: list, start: datetime, end: datetime) -> list[dict]:
    total_seconds = (end - start).total_seconds()
    segments = []
    for buff in buffs:
        segment_start = max(_to_local_naive(buff.start_time), start)
        segment_end = min(_to_local_naive(buff.end_time), end)
        if segment_start >= segment_end:
            continue
        left = (segment_start - start).total_seconds() / total_seconds * 100
        width = (segment_end - segment_start).total_seconds() / total_seconds * 100
        segments.append({"left_pct": round(left, 2), "width_pct": round(width, 2)})
    return sorted(segments, key=lambda segment: segment["left_pct"])


def _split_segment_lanes(segments: list[dict]) -> list[list[dict]]:
    lanes: list[list[dict]] = []
    lane_ends: list[float] = []
    for segment in segments:
        lane = next(
            (i for i, end in enumerate(lane_ends) if segment["left_pct"] >= end), None
        )
        if lane is None:
            lane = len(lanes)
            lanes.append([])
            lane_ends.append(0)
        lanes[lane].append(segment)
        lane_ends[lane] = segment["left_pct"] + segment["width_pct"]
    return lanes


def _buff_label(buff_type: str, buffs: list) -> tuple[str, str]:
    meta = BuffEffect.get_meta(buff_type)
    color = meta.color if meta else "#999999"
    label = meta.display_name if meta else buff_type
    if buff_type == BuffEffect.BUFF_TYPE_STARRY_BONUS:
        value = max((buff.value for buff in buffs), default=0)
        if value > 0:
            label = f"{label} +{value}%"
    return color, label


def _build_buff_timeline(
    buffs: list,
    fishing_start_time: datetime,
    now_time: datetime,
    end_time: datetime | None = None,
) -> dict | None:
    """构建 buff 时间轴数据。

    模式由 end_time 参数决定：
    - end_time=None（钓鱼状态/钓鱼页面模式）：显示当前时间1小时前到8小时后，标记开钓时间
    - end_time=收杆时间（收杆页面模式）：显示开钓到收杆的时间区间
    """
    if not buffs:
        return None

    fishing_start = _to_local_naive(fishing_start_time)
    window = _timeline_window(fishing_start, _to_local_naive(now_time), end_time)
    if window.end <= window.start:
        return None

    type_order, type_buffs = _group_buffs(buffs)
    rows = []
    legend = []
    for buff_type in type_order:
        color, label = _buff_label(buff_type, type_buffs[buff_type])
        legend.append({"color": color, "label": label})
        segments = _buff_segments(type_buffs[buff_type], window.start, window.end)
        rows.extend(
            {"color": color, "segments": lane}
            for lane in _split_segment_lanes(segments)
        )

    if not rows:
        return None

    return {
        "rows": rows,
        "time_markers": _calculate_time_markers(window.start, window.end),
        "legend": legend,
        "fishing_start_pct": window.fishing_start_pct,
        "current_time_pct": window.current_time_pct,
    }


@dataclass(frozen=True)
class _StatusWeather:
    emoji: str
    name: str
    description: str = ""
    active: bool = True


def _format_weather_hour(value, *, end: bool = False) -> str:
    if not hasattr(value, "hour"):
        return str(value)
    hour = value.hour
    return f"{'24' if end and hour == 0 else hour}点"


def _status_weather(weather_info: dict | None) -> _StatusWeather:
    from ..config import WEATHER_EFFECT_DESC, WEATHER_EMOJI, WEATHER_NAME

    weather_type = (
        weather_info.get("weather_type", "sunny") if weather_info else "sunny"
    )
    active = weather_info.get("is_active", True) if weather_info else True
    description = WEATHER_EFFECT_DESC.get(weather_type, "") if active else ""
    has_period = (
        weather_info and weather_info.get("start_time") and weather_info.get("end_time")
    )
    if weather_type not in ("sunny", "chaotic_era") and has_period:
        description = (
            f"{_format_weather_hour(weather_info['start_time'])}-"
            f"{_format_weather_hour(weather_info['end_time'], end=True)}"
        )
        effect = WEATHER_EFFECT_DESC.get(weather_type, "")
        if effect:
            description += f" {effect}"
    return _StatusWeather(
        WEATHER_EMOJI.get(weather_type, "☀️"),
        WEATHER_NAME.get(weather_type, "晴天"),
        description,
        active,
    )


def _probability_rows(probabilities: dict[str, float]) -> list[dict]:
    rows = [
        {
            "rarity_key": key,
            "rarity_name": name,
            "color": color,
            "pct": f"{probabilities.get(key, 0) * 100:.2f}",
        }
        for key, name, color in RARITY_DISPLAY
        if probabilities.get(key, 0) != 0
    ]
    multiplier = getattr(probabilities, "quantity_multiplier", 1)
    if multiplier > 1:
        rows.append(
            {
                "rarity_key": "数量",
                "rarity_name": "多多",
                "color": "#8e44ad",
                "pct": f"×{multiplier}",
                "is_multiplier": True,
            }
        )
    return rows


def _bait_info(bait, new_consumed: int, total_consumed: int) -> str:
    if bait:
        return f"🪱 {bait.name}：本轮消耗{new_consumed}个 / 累计消耗{total_consumed}个"
    if total_consumed > 0:
        return f"🪱 累计消耗{total_consumed}个鱼饵"
    return ""


def _is_lucky_active(buffs: list | None, now: datetime) -> bool:
    return bool(buffs) and any(
        buff.buff_type == "lucky_double" and _to_local_naive(buff.end_time) > now
        for buff in buffs
    )


async def render_fishing_status(
    user_id: str,
    location,
    total_duration_min: float,
    total_fish: list[tuple],
    new_fish: list[tuple],
    total_bait_consumed: int,
    new_bait_consumed: int,
    probabilities: dict[str, float],
    bait=None,
    buff_messages: list[str] | None = None,
    fishing_power: int = 0,
    rod_level: int = 0,
    buffs: list | None = None,
    fishing_start_time: datetime | None = None,
    now_time: datetime | None = None,
    fishing_interval: float = 0,
    speed_bonus_detail: str | None = None,
    weather_info: dict | None = None,
    cat_eaten_fish: list[tuple] | None = None,
    cat_gifts: dict | None = None,
    material_rate: float = 0.0,
    frame_pity: int = 0,
    utr_pity: int = 0,
    cat_frame_pity: int = 0,
    frame_pity_threshold: int = 150,
    utr_pity_threshold: int = 150,
    cat_frame_pity_threshold: int = 15,
    meteor_fish_numbers: list[int] | None = None,
) -> bytes:
    t0 = time.perf_counter()

    fish_items = build_fish_list_data(
        total_fish, location.id, new_fish=new_fish, cat_eaten_fish=cat_eaten_fish
    )
    meteor_items = build_meteor_fish_items(meteor_fish_numbers)
    if meteor_items:
        fish_items.extend(meteor_items)
    t1 = time.perf_counter()

    duration_text = (
        f"{total_duration_min / 60:.1f}小时"
        if total_duration_min >= 60
        else f"{total_duration_min:.1f}分钟"
    )

    total_count = sum(c for _, _, c in total_fish) + len(meteor_fish_numbers or [])
    new_count = sum(c for _, _, c in new_fish)

    total_value = sum(
        calculate_fish_price(fish, rarity, 0) * count
        for fish, rarity, count in total_fish
    )
    prob_rows = _probability_rows(probabilities)
    bait_info = _bait_info(bait, new_bait_consumed, total_bait_consumed)

    timeline_data = None
    if buffs and fishing_start_time:
        effective_now = now_time if now_time else datetime.now()
        timeline_data = _build_buff_timeline(buffs, fishing_start_time, effective_now)
    t2 = time.perf_counter()

    effective_now = now_time if now_time else datetime.now()
    lucky_active = _is_lucky_active(buffs, effective_now)
    weather = _status_weather(weather_info)
    total_cat_count = sum(c for _, _, c in cat_eaten_fish or [])

    cat_gifts_data = None
    if cat_gifts:
        from .fishing_result import _build_cat_gifts_data

        cat_gifts_data = _build_cat_gifts_data(cat_gifts)

    html = render_template(
        "fishing_status.html",
        body_bg=gradient_bg("teal"),
        width=450,
        location_name=location.name,
        location_difficulty=location.difficulty,
        duration_text=duration_text,
        total_count=total_count,
        new_count=new_count,
        total_value=total_value,
        fish_items=fish_items,
        prob_rows=prob_rows,
        bait_info=bait_info,
        fishing_power=fishing_power,
        rod_level=rod_level,
        buff_messages=buff_messages or [],
        timeline_data=timeline_data,
        fishing_interval=fishing_interval,
        speed_bonus_detail=speed_bonus_detail,
        weather_emoji=weather.emoji,
        weather_name=weather.name,
        weather_desc=weather.description,
        weather_active=weather.active,
        cat_count=total_cat_count,
        cat_gifts_data=cat_gifts_data,
        material_rate=material_rate,
        lucky_active=lucky_active,
        frame_pity=frame_pity,
        utr_pity=utr_pity,
        cat_frame_pity=cat_frame_pity,
        frame_pity_threshold=frame_pity_threshold,
        utr_pity_threshold=utr_pity_threshold,
        cat_frame_pity_threshold=cat_frame_pity_threshold,
    )
    t3 = time.perf_counter()

    result = await render_html(html, 450)
    t4 = time.perf_counter()

    save_debug_output(
        "fishing_status",
        user_id,
        html,
        result,
        {
            "fish_list": t1 - t0,
            "data_prep": t2 - t1,
            "template": t3 - t2,
            "html_to_pic": t4 - t3,
            "total": t4 - t0,
        },
    )

    return result
