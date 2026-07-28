from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
import time

from PIL import Image

from .base import (
    PLAYER_IMAGES_PATH,
    SCENES_IMAGES_PATH,
    gradient_bg,
    render_html,
    render_template,
    save_debug_output,
)

# 天气类型 → 天气叠加图片文件名映射
_WEATHER_OVERLAY_MAP = {
    "rain": "小雨",
    "storm": "暴雨",
}
from .fishing_status import _build_buff_timeline

# Scene special render marker S@effect and optional foreground *-fg.png
_SCENE_FG_SUFFIXES = ("-fg", "_fg")
# 长钓线：自下而上扫描“稳定细线带”——单行非透明像素数 1~9（宽度 < 10），
# 且连续 5 行宽度完全相同；取最靠近底部的 5 行作为拉伸采样带。找不到则不拉伸。
# 结果按文件缓存。
_LONGLINE_WIDTH_LIMIT = 10  # 宽度须 < 10
_LONGLINE_BAND_ROWS = 5
_LONGLINE_BAND_CACHE: dict[tuple[str, int, int], tuple[float, float] | None] = {}


def _find_weather_overlay(weather_type: str) -> str:
    """根据天气类型查找对应的天气叠加图片，返回 file:// URI 或空字符串"""
    overlay_name = _WEATHER_OVERLAY_MAP.get(weather_type)
    if not overlay_name:
        return ""
    for f in SCENES_IMAGES_PATH.iterdir():
        if f.suffix == ".png" and f.stem == overlay_name:
            return f.as_uri()
    return ""


def _is_foreground_scene_file(path: Path) -> bool:
    """Foreground layer files: {id}-{name}-fg.png (not used as background)."""
    stem = path.stem
    return any(stem.endswith(suf) for suf in _SCENE_FG_SUFFIXES)


def _parse_special_and_layout(suffix: str) -> tuple[list[str], str]:
    """Parse optional special-render marker S@effects from layout suffix.

    Examples:
      S@longline_50 -> (["longline"], "50")
      S@longline_50_60 -> (["longline"], "50_60")
      S@longline+T@1,2_3,4 -> (["longline"], "T@1,2_3,4")
      S@longline,foo+T@... -> (["longline", "foo"], "T@...")
      50 / T@... -> ([], original suffix)
    """
    if not suffix.startswith("S@"):
        return [], suffix
    body = suffix[2:]
    plus_t = body.find("+T")
    if plus_t >= 0:
        eff_part = body[:plus_t]
        layout_part = body[plus_t + 1 :]
        effects = [e.strip() for e in eff_part.split(",") if e.strip()]
        return effects, layout_part
    matched = re.match(r"^([A-Za-z][A-Za-z0-9,]*)_(\d[\d_]*)$", body)
    if matched:
        effects = [e.strip() for e in matched.group(1).split(",") if e.strip()]
        return effects, matched.group(2)
    effects = [e.strip() for e in body.split(",") if e.strip()]
    return effects, "50"


def _parse_scene_heights(stem: str) -> list[int]:
    """旧格式：最后一段为单高度或下划线分隔的多高度控制点。"""
    parts = stem.split("-")
    if not parts:
        return [50]
    height_parts = parts[-1].split("_")
    heights = []
    for part in height_parts:
        try:
            heights.append(int(part))
        except ValueError:
            return [50]
    return heights or [50]


def _interpolate_scene_height(heights: list[int], x: float, width: int) -> float:
    if not heights:
        return 50
    if len(heights) == 1 or width <= 0:
        return heights[0]
    ratio = min(max(x / width, 0), 1)
    pos = ratio * (len(heights) - 1)
    idx = int(pos)
    if idx >= len(heights) - 1:
        return heights[-1]
    frac = pos - idx
    return heights[idx] + (heights[idx + 1] - heights[idx]) * frac


def _parse_track_points(points_raw: str) -> list[tuple[float, float]]:
    """解析轨道控制点：x,y_x,y_...（百分比 0~100）。"""
    points: list[tuple[float, float]] = []
    for token in points_raw.split("_"):
        if not token or "," not in token:
            return []
        xs, ys = token.split(",", 1)
        try:
            x = float(xs)
            y = float(ys)
        except ValueError:
            return []
        points.append((min(max(x, 0), 100), min(max(y, 0), 100)))
    return points


def _parse_scene_tracks(stem: str) -> list[dict] | None:
    """多轨道格式：T@{x},{y}_{x},{y}+T@...

    - 轨道之间用 ``+`` 分隔
    - ``T@`` 后为轨迹控制点（x,y 百分比）；兼容历史 ``T{容量}@``，容量会被忽略
    - 人数不设上限，由系统按各轨长度做密度均衡分配
    - 解析失败返回 None，回退旧高度格式
    """
    parts = stem.split("-")
    if not parts:
        return None
    suffix = parts[-1]
    if "@" not in suffix or "T" not in suffix:
        return None
    tracks: list[dict] = []
    for segment in suffix.split("+"):
        segment = segment.strip()
        if not segment.startswith("T") or "@" not in segment:
            return None
        head, points_raw = segment.split("@", 1)
        # 允许 T@ 或历史 T4@（容量忽略）
        if head != "T":
            if len(head) < 2 or head[0] != "T":
                return None
            try:
                int(head[1:])
            except ValueError:
                return None
        points = _parse_track_points(points_raw)
        if len(points) < 1:
            return None
        tracks.append({"points": points})
    return tracks or None


def _polyline_length(points: list[tuple[float, float]]) -> float:
    total = 0.0
    for i in range(1, len(points)):
        x0, y0 = points[i - 1]
        x1, y1 = points[i]
        total += ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
    return total


def _point_on_polyline(
    points: list[tuple[float, float]], t: float
) -> tuple[float, float]:
    """在折线上按弧长比例 t∈[0,1] 线性插值。"""
    if not points:
        return 50.0, 50.0
    if len(points) == 1:
        return points[0]
    t = min(max(t, 0.0), 1.0)
    total = _polyline_length(points)
    if total <= 1e-9:
        return points[0]
    target = t * total
    walked = 0.0
    for i in range(1, len(points)):
        x0, y0 = points[i - 1]
        x1, y1 = points[i]
        seg = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        if walked + seg >= target or i == len(points) - 1:
            if seg <= 1e-9:
                return x0, y0
            frac = (target - walked) / seg
            frac = min(max(frac, 0.0), 1.0)
            return x0 + (x1 - x0) * frac, y0 + (y1 - y0) * frac
        walked += seg
    return points[-1]


def _parse_scene_layout(stem: str) -> dict:
    """解析场景文件名后缀，兼容旧高度、多轨道与特殊渲染标记。

    返回::
        {"mode": "heights", "heights": [int, ...], "effects": [str, ...]}
        或
        {"mode": "tracks", "tracks": [{"points": [(x,y), ...]}, ...], "effects": [...]}
    """
    parts = stem.split("-")
    suffix = parts[-1] if parts else ""
    effects, layout_suffix = _parse_special_and_layout(suffix)
    layout_stem = f"_layout-_-{layout_suffix}"
    tracks = _parse_scene_tracks(layout_stem)
    if tracks:
        return {"mode": "tracks", "tracks": tracks, "effects": effects}
    return {
        "mode": "heights",
        "heights": _parse_scene_heights(layout_stem),
        "effects": effects,
    }


def _track_length(track: dict) -> float:
    """轨道有效长度；单点轨给极小正长，避免除零且仍可被分配。"""
    points = track.get("points") or []
    length = _polyline_length(points)
    if length > 1e-9:
        return length
    # 单点/零长：视为极短轨，仍可参与分配但不抢长轨
    return 1e-3


def _allocate_track_slots(tracks: list[dict], count: int) -> list[int]:
    """按「人数/长度」密度智能分配：每次把下一个人放到密度最低的轨道。

    平局时优先排在前面的轨道。支持 1~无限人，无容量上限。
    """
    n = len(tracks)
    if n == 0 or count <= 0:
        return [0] * n
    slots = [0] * n
    lengths = [_track_length(t) for t in tracks]
    for _ in range(count):
        best = 0
        best_density = slots[0] / lengths[0]
        for i in range(1, n):
            density = slots[i] / lengths[i]
            if density < best_density - 1e-12:
                best = i
                best_density = density
            # 密度相同则保持更靠前的轨道（best 更小）
        slots[best] += 1
    return slots


def _place_on_tracks(
    tracks: list[dict], count: int, container_width: float
) -> list[tuple[float, float]]:
    """将 count 个角色放到多条轨道上，返回 (left_pos_px, scene_y_percent)。

    轨道内等距：1 人居中；多人沿弧长从起点到终点等间距（含端点）。
    """
    if count <= 0:
        return []
    slots = _allocate_track_slots(tracks, count)
    placements: list[tuple[float, float]] = []
    for track, n in zip(tracks, slots):
        if n <= 0:
            continue
        points = track["points"]
        for i in range(n):
            if len(points) <= 1:
                t = 0.0
            elif n == 1:
                t = 0.5
            else:
                # 端点 inclusive，间距相等
                t = i / (n - 1)
            x_pct, y_pct = _point_on_polyline(points, t)
            left_pos = round(x_pct / 100.0 * container_width, 1)
            placements.append((left_pos, y_pct))
    return placements


def _place_on_heights(
    heights: list[int], count: int, container_width: float, sprite_w: float
) -> list[tuple[float, float]]:
    """旧格式：横向均分 + 高度插值。"""
    if count <= 0:
        return []
    if count == 1:
        positions = [container_width / 2]
    else:
        ideal_spacing = 20
        total_with_ideal = count * sprite_w + (count - 1) * ideal_spacing
        if total_with_ideal <= container_width:
            spacing = ideal_spacing
        else:
            spacing = (container_width - count * sprite_w) / (count - 1)
        total_width = count * sprite_w + (count - 1) * spacing
        start_x = (container_width - total_width) / 2 + sprite_w / 2
        positions = [start_x + i * (sprite_w + spacing) for i in range(count)]
    return [
        (round(x, 1), _interpolate_scene_height(heights, x, container_width))
        for x in positions
    ]


def _find_scene_file(location) -> tuple[Path | None, dict]:
    default_layout = {"mode": "heights", "heights": [50], "effects": []}
    if not SCENES_IMAGES_PATH.exists():
        return None, default_layout
    for f in SCENES_IMAGES_PATH.iterdir():
        if f.suffix != ".png" or _is_foreground_scene_file(f):
            continue
        parts = f.stem.split("-")
        if len(parts) >= 3 and (
            parts[1] == location.name
            or parts[0].lower() == str(location.id).lower()
        ):
            return f, _parse_scene_layout(f.stem)
    return None, default_layout


def _find_foreground_file(location) -> Path | None:
    """Find optional foreground layer: {id}-*-fg.png."""
    if not SCENES_IMAGES_PATH.exists():
        return None
    loc_id = str(location.id).lower()
    for f in sorted(SCENES_IMAGES_PATH.iterdir(), key=lambda p: p.name.lower()):
        if f.suffix != ".png" or not _is_foreground_scene_file(f):
            continue
        parts = f.stem.split("-")
        if parts and parts[0].lower() == loc_id:
            return f
        if getattr(location, "name", None) and location.name in f.stem:
            return f
    return None


def _parse_skin_stem(stem: str) -> tuple[str, int]:
    """从皮肤文件名解析 (skin_id, y_offset)。

    约定：`{id}_{offset}.png`，offset 为整数（可负）。
    必须从**末尾**拆分，否则 `star_man_-21` 会被误拆成 `star` / `man_-21`。
    """
    if "_" not in stem:
        return stem, 0
    base, off_s = stem.rsplit("_", 1)
    try:
        return base, int(off_s)
    except ValueError:
        # 非数字后缀（如历史命名）整段当 id
        return stem, 0


def _find_skin_file(skin_id: str) -> tuple[Path | None, int]:
    if not PLAYER_IMAGES_PATH.exists():
        return None, 0
    for f in PLAYER_IMAGES_PATH.iterdir():
        if f.suffix.lower() not in (".png", ".jpg"):
            continue
        if f.stem.startswith("frame_"):
            continue
        base_id, offset = _parse_skin_stem(f.stem)
        if base_id == skin_id:
            return f, offset
    return None, 0


def _get_all_skin_files() -> list[str]:
    skin_ids = []
    if not PLAYER_IMAGES_PATH.exists():
        return skin_ids
    seen = set()
    for f in sorted(PLAYER_IMAGES_PATH.iterdir()):
        if f.suffix.lower() not in (".png", ".jpg"):
            continue
        if f.stem.startswith("frame_"):
            continue
        base_id, _ = _parse_skin_stem(f.stem)
        if base_id not in seen:
            seen.add(base_id)
            skin_ids.append(base_id)
    return skin_ids


def _get_skin_image_uri(skin_id: str) -> str | None:
    skin_file, _ = _find_skin_file(skin_id)
    if skin_file and skin_file.exists():
        return skin_file.as_uri()
    return None


def _get_skin_display_size(skin_id: str) -> tuple[int, int]:
    skin_file, _ = _find_skin_file(skin_id)
    if skin_file and skin_file.exists():
        try:
            img = Image.open(skin_file)
            pw, ph = img.size
            img.close()
            return pw * 0.5, ph * 0.5
        except Exception:
            pass
    return 80, 80


_RARITY_DISPLAY = [
    ("N", "#9e9e9e"),
    ("R", "#2196f3"),
    ("SR", "#9c27b0"),
    ("SSR", "#ff9800"),
    ("UR", "#f44336"),
    ("UTR", "#e91e63"),
]


@dataclass(frozen=True)
class _WeatherView:
    emoji: str
    name: str
    time: str = ""
    effect: str = ""
    active: bool = True
    overlay_uri: str = ""


def _load_skin_size(
    skin_file: Path | None, fallback: tuple[int, int]
) -> tuple[float, float]:
    if not skin_file or not skin_file.exists():
        return fallback
    try:
        with Image.open(skin_file) as img:
            width, height = img.size
        return (width * 0.5, height * 0.5) if width > 30 else (width, height)
    except Exception:
        return fallback


def _build_npc_entries(
    weather_info: dict | None, fallback: tuple[int, int]
) -> list[dict]:
    if not weather_info or not weather_info.get("is_active"):
        return []
    skin_by_weather = {"cat": "cat", "lost_wind": "star_man"}
    skin_id = skin_by_weather.get(weather_info.get("weather_type", "sunny"))
    if not skin_id:
        return []
    skin_file, y_offset = _find_skin_file(skin_id)
    if not skin_file or not skin_file.exists():
        return []
    skin_w, skin_h = _load_skin_size(skin_file, fallback)
    return [
        {
            "image_path": skin_file,
            "nickname": "",
            "y_offset": y_offset,
            "skin_w": skin_w,
            "skin_h": skin_h,
        }
    ]


def _prepare_player_skins(
    players: list[dict], fallback: tuple[int, int]
) -> tuple[dict, dict]:
    sizes: dict[str, tuple[float, float]] = {}
    offsets: dict[str, int] = {}
    for player in players:
        skin_id = player.get("skin_id", "1")
        if skin_id in sizes:
            continue
        skin_file, y_offset = _find_skin_file(skin_id)
        offsets[skin_id] = y_offset
        sizes[skin_id] = _load_skin_size(skin_file, fallback)
    return sizes, offsets


def _scene_placements(
    scene_layout: dict, count: int, sprite_w: float, width: int
) -> list[tuple[float, float]]:
    if scene_layout.get("mode") == "tracks":
        return _place_on_tracks(scene_layout["tracks"], count, width)
    return _place_on_heights(
        scene_layout.get("heights") or [50], count, width, sprite_w
    )


def _analyze_longline_band(image_path: Path) -> tuple[float, float] | None:
    """分析皮肤图中的稳定细钓线带，返回 (body_ratio, crop_ratio)；无法识别则 None。

    - 自下而上扫描整图
    - 候选行：该行非透明像素数满足 0 < count < 10
    - 稳定：连续若干行宽度完全相同
    - 取最靠近底部的、连续 >= 5 行稳定细线区间中的底部 5 行作为拉伸采样带
    - 形变后角色顶部与普通渲染一致（由调用方用 body_ratio 计算）
    - 宽行须完整计数到 >=10 才能判非候选；不可在临界宽度提前截断
    """
    try:
        resolved = image_path.resolve()
        st = resolved.stat()
        cache_key = (str(resolved), int(st.st_mtime_ns), int(st.st_size))
    except OSError:
        return None

    if cache_key in _LONGLINE_BAND_CACHE:
        return _LONGLINE_BAND_CACHE[cache_key]

    result: tuple[float, float] | None = None
    try:
        with Image.open(resolved) as im:
            rgba = im.convert("RGBA")
            width, height = rgba.size
            if width <= 0 or height < _LONGLINE_BAND_ROWS:
                result = None
            else:
                alpha = rgba.getchannel("A")
                alpha_data = list(alpha.getdata())
                row_widths: list[int] = []
                for y in range(height):
                    row_start = y * width
                    opaque = 0
                    for x in range(width):
                        if alpha_data[row_start + x] > 0:
                            opaque += 1
                            # 达到上限即可结束；opaque == limit 已不属于“低于 limit”
                            if opaque >= _LONGLINE_WIDTH_LIMIT:
                                break
                    row_widths.append(opaque)

                # 自下而上找：宽度 < 10 且连续相同宽度 >= 5 行
                y = height - 1
                chosen: tuple[int, int] | None = None
                while y >= 0:
                    w = row_widths[y]
                    if not (0 < w < _LONGLINE_WIDTH_LIMIT):
                        y -= 1
                        continue
                    y_end = y + 1  # exclusive
                    y_start = y
                    while y_start - 1 >= 0 and row_widths[y_start - 1] == w:
                        y_start -= 1
                    if y_end - y_start >= _LONGLINE_BAND_ROWS:
                        # 取该稳定段最靠下的 5 行（更接近钩坠，远离角色身体）
                        chosen = (y_end - _LONGLINE_BAND_ROWS, y_end)
                        break
                    y = y_start - 1

                if chosen is not None:
                    band_y0, band_y1 = chosen
                    body_ratio = band_y0 / height
                    crop_ratio = band_y1 / height
                    if crop_ratio > body_ratio + 1e-12:
                        result = (body_ratio, crop_ratio)
    except Exception:
        result = None

    _LONGLINE_BAND_CACHE[cache_key] = result
    return result


def _actor_view(
    image_path: Path,
    nickname: str,
    size: tuple[float, float],
    position: tuple[float, float],
    y_offset: int,
    is_current: bool,
    *,
    effects: list[str] | None = None,
) -> dict:
    left_pos, scene_y = position
    z_base = int(scene_y)
    skin_w, skin_h = size
    effects = list(effects or [])
    # 皮肤文件名中的 y_offset 用于把图片内的脚部线对齐到场景基准线。
    # 因此脚部线在图片内的显示坐标为 skin_h + y_offset；倒影只能取其上方内容。
    mirror_body_h = min(max(skin_h + y_offset, 0.0), skin_h)
    view = {
        "is_current": is_current,
        "nickname": nickname,
        "uri": image_path.as_uri(),
        "skin_w": skin_w,
        "skin_h": skin_h,
        "left_pos": left_pos,
        "z_index": (100 if is_current else 1) + z_base,
        "y_offset": y_offset,
        "scene_y": round(scene_y, 2),
        "scene_bottom": round(100 - scene_y, 2),
        "effects": effects,
        "special": "",
        # 镜面特效：以脚部线（scene_bottom% + y_offset）为镜像轴向下翻转，
        # 仅在脚部线以下绘制模糊倒影，不越过脚部线
        "mirror": "mirror" in effects,
        "mirror_body_h": round(mirror_body_h, 2),
    }
    if "longline" in effects:
        # 自适应识别细钓线带；识别失败则退回普通渲染，避免误拉脚部
        band_ratios = _analyze_longline_band(image_path)
        if band_ratios is not None:
            body_ratio, crop_ratio = band_ratios
            body_h = round(skin_h * body_ratio, 2)
            # 保持与普通渲染相同的顶部：bottom = scene_bottom% + y_offset，高 skin_h
            # body 高度 body_h 时，body 底边相对 y_offset 上移 (skin_h - body_h)
            line_base = round(y_offset + skin_h - body_h, 2)
            band = crop_ratio - body_ratio
            view.update(
                {
                    "special": "longline",
                    "body_h": body_h,
                    "line_base": line_base,
                    "line_img_height_pct": (
                        round(100.0 / band, 4) if band > 1e-9 else 1000.0
                    ),
                    "line_img_top_pct": (
                        round(-body_ratio / band * 100.0, 4) if band > 1e-9 else -600.0
                    ),
                    "line_body_ratio": round(body_ratio, 6),
                    "line_crop_ratio": round(crop_ratio, 6),
                }
            )
    return view


def _build_scene_actors(
    players: list[dict],
    current_user_id: str,
    weather_info: dict | None,
    scene_layout: dict,
    width: int,
) -> list[dict]:
    fallback = (22, 61)
    sizes, offsets = _prepare_player_skins(players, fallback)
    npcs = _build_npc_entries(weather_info, fallback)
    widths = [size[0] for size in sizes.values()] + [npc["skin_w"] for npc in npcs]
    placements = _scene_placements(
        scene_layout, len(players) + len(npcs), max(widths, default=fallback[0]), width
    )
    effects = list(scene_layout.get("effects") or [])
    actors = []
    for index, player in enumerate(players):
        skin_id = player.get("skin_id", "1")
        skin_file, _ = _find_skin_file(skin_id)
        if not skin_file or not skin_file.exists():
            continue
        position = placements[index] if index < len(placements) else (0.0, 50.0)
        actors.append(
            _actor_view(
                skin_file,
                player.get("nickname", "???"),
                sizes.get(skin_id, fallback),
                position,
                offsets.get(skin_id, 0),
                player["user_id"] == current_user_id,
                effects=effects,
            )
        )
    for index, npc in enumerate(npcs, start=len(players)):
        position = placements[index] if index < len(placements) else (0.0, 50.0)
        actors.append(
            _actor_view(
                npc["image_path"],
                npc["nickname"],
                (npc["skin_w"], npc["skin_h"]),
                position,
                npc["y_offset"],
                False,
                effects=effects,
            )
        )
    return actors


def _scene_bottom(scene_layout: dict) -> float:
    if scene_layout.get("mode") == "tracks":
        return 100 - scene_layout["tracks"][0]["points"][0][1]
    return 100 - (scene_layout.get("heights") or [50])[0]


def _format_weather_hour(value, *, end: bool = False) -> str:
    if not hasattr(value, "hour"):
        return str(value)
    hour = value.hour
    return f"{'24' if end and hour == 0 else hour}点"


def _build_weather_view(weather_info: dict | None) -> _WeatherView:
    from ..config import WEATHER_EFFECT_DESC, WEATHER_EMOJI, WEATHER_NAME

    weather_type = (
        weather_info.get("weather_type", "sunny") if weather_info else "sunny"
    )
    active = weather_info.get("is_active", True) if weather_info else True
    effect = WEATHER_EFFECT_DESC.get(weather_type, "") if active else ""
    time_text = ""
    has_period = (
        weather_info and weather_info.get("start_time") and weather_info.get("end_time")
    )
    if weather_type not in ("sunny", "chaotic_era") and has_period:
        start_time = weather_info["start_time"]
        end_time = weather_info["end_time"]
        # 星空天气/迷途风等全天窗口（23点~次日23点）直接显示「全天」
        if (
            hasattr(start_time, "hour")
            and hasattr(end_time, "hour")
            and start_time.hour == 23
            and end_time.hour == 23
        ):
            time_text = "全天"
        else:
            start_text = _format_weather_hour(start_time)
            end_text = _format_weather_hour(end_time, end=True)
            time_text = f"{start_text}-{end_text}"
        effect = WEATHER_EFFECT_DESC.get(weather_type, "")
    overlay = _find_weather_overlay(weather_type) if active else ""
    return _WeatherView(
        emoji=WEATHER_EMOJI.get(weather_type, "☀️"),
        name=WEATHER_NAME.get(weather_type, "晴天"),
        time=time_text,
        effect=effect,
        active=active,
        overlay_uri=overlay,
    )


def _build_probability_items(probabilities: dict | None) -> list[dict]:
    if not probabilities:
        return []
    items = [
        {
            "rk": rarity,
            "color": color,
            "pct": f"{probabilities.get(rarity, 0) * 100:.1f}",
        }
        for rarity, color in _RARITY_DISPLAY
        if probabilities.get(rarity, 0) > 0
    ]
    multiplier = getattr(probabilities, "quantity_multiplier", 1)
    if multiplier > 1:
        items.append(
            {
                "rk": "数量",
                "color": "#8e44ad",
                "pct": f"×{multiplier}",
                "is_multiplier": True,
            }
        )
    return items


async def render_fishing_scene(
    location,
    players: list[dict],
    current_user_id: str,
    hints: list[str] | None = None,
    nest_speed_bonus: int = 0,
    bait_name: str = "",
    bait_count: int = 0,
    fishing_power: int = 0,
    weekend_bonus: int = 0,
    probabilities: dict | None = None,
    buffs: list | None = None,
    fishing_start_time: datetime | None = None,
    now_time: datetime | None = None,
    hook_level: int = 0,
    weather_info: dict | None = None,
    material_rate: float = 0.0,
    scene_inverted: bool = False,
) -> bytes:
    from .fishing_result import render_fishing_start

    t_start = time.perf_counter()

    scene_file, scene_layout = _find_scene_file(location)

    if not scene_file:
        return await render_fishing_start(
            current_user_id, location, datetime.now(), hints=hints
        )

    scene_uri = scene_file.as_uri()
    fg_file = _find_foreground_file(location)
    foreground_uri = fg_file.as_uri() if fg_file and fg_file.exists() else ""
    container_width = 330
    player_list = _build_scene_actors(
        players, current_user_id, weather_info, scene_layout, container_width
    )
    y_bottom = _scene_bottom(scene_layout)

    badges = []
    if nest_speed_bonus > 0:
        badges.append(f"⚡{nest_speed_bonus}%")
    if weekend_bonus > 0:
        multiplier = 1 + weekend_bonus / 100
        badges.append(f"⚡×{multiplier:.1f}")

    bait_info = f" · 🪱 {bait_name}：{bait_count}" if bait_name else ""
    power_info = f" · ⚔️ 渔力：{fishing_power}"
    from ..config import ConfigManager

    hook_pct = hook_level * ConfigManager.get_shop().hook_speed_bonus_per_level
    hook_info = f" · 🪝 鱼钩：+{hook_pct}%" if hook_level > 0 else ""
    weather = _build_weather_view(weather_info)
    prob_items = _build_probability_items(probabilities)

    timeline_data = None
    if buffs and fishing_start_time:
        effective_now = now_time if now_time else datetime.now()
        timeline_data = _build_buff_timeline(buffs, fishing_start_time, effective_now)

    t_data_prep = time.perf_counter()

    html = render_template(
        "fishing_scene.html",
        body_bg="",
        width=container_width,
        container_width=container_width,
        y_bottom=y_bottom,
        scene_uri=scene_uri,
        foreground_uri=foreground_uri,
        badges=badges,
        player_list=player_list,
        location_name=location.name,
        location_difficulty=location.difficulty,
        fish_count=len(location.fish_pool),
        bait_info=bait_info,
        power_info=power_info,
        hook_info=hook_info,
        prob_items=prob_items,
        timeline_data=timeline_data,
        hints=hints or [],
        weather_emoji=weather.emoji,
        weather_name=weather.name,
        weather_time=weather.time,
        weather_effect=weather.effect,
        weather_active=weather.active,
        weather_overlay_uri=weather.overlay_uri,
        material_rate=material_rate,
        scene_inverted=scene_inverted,
    )

    t_html = time.perf_counter()
    result = await render_html(html, container_width)
    t_end = time.perf_counter()
    save_debug_output(
        "fishing_scene",
        current_user_id,
        html,
        result,
        {
            "data_prep": t_data_prep - t_start,
            "html_build": t_html - t_data_prep,
            "html_to_pic": t_end - t_html,
            "total": t_end - t_start,
        },
    )
    return result


async def render_skin_list(owned_skins: list[str], current_skin: str) -> bytes:
    if not owned_skins:
        owned_skins = ["1"]

    skins = []
    for skin_id in owned_skins:
        is_current = skin_id == current_skin
        skin_uri = _get_skin_image_uri(skin_id)
        disp_w, disp_h = _get_skin_display_size(skin_id)

        if is_current:
            status_text = "✅ 使用中"
            status_cls = "current"
        else:
            status_text = "已拥有"
            status_cls = "owned"

        skins.append(
            {
                "id": skin_id,
                "status_cls": status_cls,
                "status_text": status_text,
                "skin_uri": skin_uri,
                "disp_w": disp_w,
                "disp_h": disp_h,
            }
        )

    html = render_template(
        "skin_list.html",
        body_bg=gradient_bg("purple"),
        width=400,
        skins=skins,
        current_skin=current_skin,
    )
    return await render_html(html, 400)
