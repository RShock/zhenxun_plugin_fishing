import asyncio
from dataclasses import dataclass
from datetime import datetime
import json
import mimetypes
from pathlib import Path
import time
from zoneinfo import ZoneInfo

from .cat_park import (
    CAT_PARK_IMAGE_BUILDING_ORDER,
    CAT_PARK_STATE_ITEM_ID,
    CAT_PARK_STATE_ITEM_TYPE,
)
from .config import ConfigManager
from .constants import RARITY_MULTIPLIER
from .core.starry_system import S2_TICKET_SCORE_THRESHOLD
from .models import BuffEffect, FishingBuff, FishingUser, FishingWeather
from .starry import get_starry_bonus_count, is_starry_location

_TZ = ZoneInfo("Asia/Shanghai")

_WEATHER_BUFF_TYPES = frozenset(
    {
        BuffEffect.BUFF_TYPE_WEATHER_RAIN,
        BuffEffect.BUFF_TYPE_WEATHER_METEOR,
        BuffEffect.BUFF_TYPE_WEATHER_STORM,
        BuffEffect.BUFF_TYPE_WEATHER_LOST_WIND,
        BuffEffect.BUFF_TYPE_WEATHER_SOLAR_WIND,
        BuffEffect.BUFF_TYPE_WEATHER_METEOR_SHOWER,
        BuffEffect.BUFF_TYPE_WEATHER_HENGJIYUAN,
    }
)

_POTION_BUFF_TYPES = frozenset(
    {
        BuffEffect.BUFF_TYPE_WISH,
        BuffEffect.BUFF_TYPE_DUODUO,
        BuffEffect.BUFF_TYPE_SPEED_BOOST,
        BuffEffect.BUFF_TYPE_DOUBLE_CATCH,
        BuffEffect.BUFF_TYPE_LUCKY_BOOST,
        BuffEffect.BUFF_TYPE_GAMMA_RAY_BURST,
    }
)

_FISHING_STATUS_PORT = 4158
_server_task: asyncio.Task | None = None

_ROUTES: dict[str, object] = {}

# S2 ?????? Demo??? 4158 /s2/ ?????????
_S2_STATIC_PREFIX = "/s2"
_S2_DEMO_DIR = (
    Path(__file__).resolve().parent / "doc" / "s2??" / "????" / "demo" / "web"
)

_CORS_HEADERS = (
    "Access-Control-Allow-Origin: *\r\n"
    "Access-Control-Allow-Methods: GET, OPTIONS\r\n"
    "Access-Control-Allow-Headers: Content-Type, Authorization\r\n"
    "Access-Control-Max-Age: 86400\r\n"
)

_CACHE_TTL_SECONDS = 5
_cache_body: str | None = None
_cache_time: float = 0

_STARRY_REWARD_POOLS = {
    "none": {"score": "0", "items": []},
    "low": {
        "score": "1-2",
        "items": ["玉米", "黑商额外兑换券", "中级抽奖碎片", "0.5积分"],
    },
    "middle": {
        "score": "3-5",
        "items": ["多多药水", "幸运药水", "重置药水", "猫框", "高级抽奖碎片"],
    },
    "high": {
        "score": "6-10",
        "items": ["闪光药水", "时光药水", "UTR自选券", "究极抽奖碎片"],
    },
    "ultimate": {"score": "11+", "items": ["时光药水×10", "UTR自选券×10"]},
}

_COLLECTION_CACHE_TTL = 300  # 5 分钟
_collections_cache: dict[str, list[str]] | None = None
_collections_cache_time: float = 0

# 猫猫乐园建筑状态缓存（与 collections 同周期）
_cat_park_cache: dict[str, str] | None = None
_cat_park_cache_time: float = 0

_RARITY_ORDER = ["N", "R", "SR", "SSR", "UR", "UTR"]


def _compute_collections(users: list, locations: list) -> dict[str, list[str]]:
    """计算所有玩家的图鉴压缩状态。

    每个玩家返回与 locations 等长的字符串列表，每个字符串对应一个场景。
    每条鱼用 1 个字符编码 6 个稀有度的收集情况：
      bit0=N, bit1=R, bit2=SR, bit3=SSR, bit4=UR, bit5=UTR
      字符 = chr(32 + bits)，bits ∈ [0, 63]
      未收集 = chr(32)（空格），全部收集 = chr(95)（'_'）
    普通场景（5 条鱼）= 5 字符；S1（10 条鱼）= 10 字符。
    采用字符串而非整数，避免 S1 的 60 位二进制超过 JS 安全整数上限。
    """
    result: dict[str, list[str]] = {}
    for user in users:
        collection = user.collection if isinstance(user.collection, dict) else {}
        # 构建 (fish_name, rarity) -> collected 的查找集合
        collected_set: set[tuple[str, str]] = set()
        for key, value in collection.items():
            if isinstance(value, dict):
                for rarity, count in value.items():
                    if count > 0:
                        collected_set.add((key, rarity))
                continue
            parts = key.split("|", 1)
            if len(parts) == 2 and value > 0:
                collected_set.add((parts[0], parts[1]))

        scene_strs: list[str] = []
        for loc in locations:
            chars: list[str] = []
            for fish_name in loc.fish_pool:
                bits = 0
                for rarity_idx, rarity in enumerate(_RARITY_ORDER):
                    if (fish_name, rarity) in collected_set:
                        bits |= 1 << rarity_idx
                chars.append(chr(32 + bits))
            scene_strs.append("".join(chars))
        result[user.user_id] = scene_strs
    return result


def _compute_cat_park_states(users: list) -> dict[str, str]:
    """计算所有玩家的猫猫乐园建筑等级字符串。

    每个玩家返回 9 字符字符串，按 CAT_PARK_IMAGE_BUILDING_ORDER 顺序
    （与建设列表编号/用户可见建筑顺序一致），每个字符为该建筑等级 '0'-'3'。
    数据从 user.items 中已加载的 cat_park_state 项读取，无需额外 DB 查询。
    """
    state_key = f"{CAT_PARK_STATE_ITEM_ID}|{CAT_PARK_STATE_ITEM_TYPE}"
    result: dict[str, str] = {}
    for user in users:
        items = user.items if isinstance(user.items, dict) else {}
        entry = items.get(state_key) or {}
        raw = entry.get("data") if isinstance(entry, dict) else None
        buildings: dict[str, int] = {}
        if isinstance(raw, str):
            try:
                state = json.loads(raw)
                if isinstance(state, dict):
                    buildings = state.get("buildings", {}) or {}
            except json.JSONDecodeError:
                pass
        elif isinstance(raw, dict):
            buildings = raw.get("buildings", {}) or {}
        chars = [
            str(int(buildings.get(name, 0))) for name in CAT_PARK_IMAGE_BUILDING_ORDER
        ]
        result[user.user_id] = "".join(chars)
    return result


def _content_type_for(file_path: Path) -> str:
    ctype, _ = mimetypes.guess_type(str(file_path))
    if not ctype:
        suffix = file_path.suffix.lower()
        if suffix == ".js":
            ctype = "application/javascript"
        elif suffix == ".css":
            ctype = "text/css"
        elif suffix in {".html", ".htm"}:
            ctype = "text/html"
        elif suffix == ".json":
            ctype = "application/json"
        elif suffix == ".svg":
            ctype = "image/svg+xml"
        else:
            ctype = "application/octet-stream"
    if ctype.startswith("text/") or ctype in {
        "application/javascript",
        "application/json",
        "image/svg+xml",
    }:
        if "charset=" not in ctype:
            ctype = f"{ctype}; charset=utf-8"
    return ctype


def _try_serve_s2_static(path: str) -> tuple[bytes, str, int] | None:
    """Serve /s2 and /s2/* from the S2 demo web folder. Returns None if not matched."""
    if path != _S2_STATIC_PREFIX and not path.startswith(_S2_STATIC_PREFIX + "/"):
        return None

    rel = path[len(_S2_STATIC_PREFIX) :].lstrip("/")
    if not rel or rel.endswith("/"):
        rel = "index.html"

    root = _S2_DEMO_DIR.resolve()
    target = (root / rel).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        body = json.dumps({"error": "forbidden"}, ensure_ascii=False).encode("utf-8")
        return body, "application/json; charset=utf-8", 403

    if not target.is_file():
        body = json.dumps(
            {"error": "not found", "path": path, "hint": "try /s2/"},
            ensure_ascii=False,
        ).encode("utf-8")
        return body, "application/json; charset=utf-8", 404

    return target.read_bytes(), _content_type_for(target), 200


def _route(path: str):
    def decorator(func):
        _ROUTES[path] = func
        return func

    return decorator


async def _handle_request(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    try:
        request_line = await asyncio.wait_for(reader.readline(), timeout=5.0)
        if not request_line:
            writer.close()
            await writer.wait_closed()
            return

        try:
            parts = request_line.decode().split(" ")
            method = parts[0]
            path = parts[1] if len(parts) > 1 else "/"
        except (IndexError, UnicodeDecodeError):
            method = "GET"
            path = "/"

        while True:
            header = await asyncio.wait_for(reader.readline(), timeout=2.0)
            if header in (b"\r\n", b"\n", b""):
                break

        if method == "OPTIONS":
            response = (
                f"HTTP/1.1 204 No Content\r\n{_CORS_HEADERS}Content-Length: 0\r\n\r\n"
            )
            writer.write(response.encode())
            await writer.drain()
            return

        static_resp = _try_serve_s2_static(path.split("?", 1)[0])
        if static_resp is not None:
            data, content_type, status = static_resp
            reason = {200: "OK", 403: "Forbidden", 404: "Not Found"}.get(status, "OK")
            response = (
                f"HTTP/1.1 {status} {reason}\r\n"
                f"Content-Type: {content_type}\r\n"
                f"Content-Length: {len(data)}\r\n"
                f"{_CORS_HEADERS}"
                "\r\n"
            ).encode() + data
            writer.write(response)
            await writer.drain()
            return

        handler = _ROUTES.get(path.split("?", 1)[0])
        if handler:
            body = await handler()
            status_line = "HTTP/1.1 200 OK"
        else:
            body = json.dumps(
                {
                    "error": "not found",
                    "available": [*list(_ROUTES.keys()), "/s2/"],
                },
                ensure_ascii=False,
            )
            status_line = "HTTP/1.1 404 Not Found"

        data = body.encode("utf-8")
        response = (
            f"{status_line}\r\n"
            "Content-Type: application/json; charset=utf-8\r\n"
            f"Content-Length: {len(data)}\r\n"
            f"{_CORS_HEADERS}"
            "\r\n"
        ).encode() + data

        writer.write(response)
        await writer.drain()
    except (asyncio.TimeoutError, ConnectionResetError, Exception):
        pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def _get_location_buffs_batch(
    location_ids: list[str],
) -> dict[str, dict[str, int]]:
    now = datetime.now()
    buffs = await FishingBuff.filter(
        target_type=BuffEffect.TARGET_TYPE_LOCATION,
        target_id__in=location_ids,
        start_time__lte=now,
        end_time__gt=now,
    ).all()
    result: dict[str, dict[str, int]] = {lid: {} for lid in location_ids}
    for buff in buffs:
        if buff.buff_type in _WEATHER_BUFF_TYPES:
            continue
        loc_counts = result.setdefault(buff.target_id, {})
        loc_counts[buff.buff_type] = loc_counts.get(buff.buff_type, 0) + 1
    return result


async def _get_raw_weathers() -> dict[str, dict]:
    weathers = await FishingWeather.get_all_today_weathers()
    now = datetime.now(_TZ).replace(tzinfo=None)
    result = {}
    for loc_id, w in weathers.items():
        is_active = False
        st = None
        et = None
        if w.weather_type != "sunny" and w.start_time and w.end_time:
            st = (
                w.start_time.replace(tzinfo=None)
                if w.start_time.tzinfo
                else w.start_time
            )
            et = w.end_time.replace(tzinfo=None) if w.end_time.tzinfo else w.end_time
            if st <= now < et:
                is_active = True
        result[loc_id] = {
            "type": w.weather_type,
            "is_active": is_active,
            "start_time": st.isoformat() if st else None,
            "end_time": et.isoformat() if et else None,
        }
    return result


@dataclass(frozen=True)
class _SceneSnapshot:
    locations: list
    users: list
    fisher_counts: dict[str, int]
    location_buffs: dict[str, dict[str, int]]
    weathers: dict[str, dict]
    global_frame_count: int
    starry_bonus_count: int


def _count_fishers(users: list) -> dict[str, int]:
    counts: dict[str, int] = {}
    for user in users:
        status = user.fishing_status
        location_id = status.get("location_id") if isinstance(status, dict) else None
        if location_id:
            counts[location_id] = counts.get(location_id, 0) + 1
    return counts


async def _load_scene_snapshot() -> _SceneSnapshot:
    locations = ConfigManager.get_locations()
    users = await FishingUser.all()
    location_ids = [location.id for location in locations]
    location_buffs, weathers, frame_count, starry_count = await asyncio.gather(
        _get_location_buffs_batch(location_ids),
        _get_raw_weathers(),
        FishingBuff.get_global_buff_count(BuffEffect.BUFF_TYPE_FRAME),
        get_starry_bonus_count(),
    )
    return _SceneSnapshot(
        locations,
        users,
        _count_fishers(users),
        location_buffs,
        weathers,
        frame_count,
        starry_count,
    )


def _location_buffs(snapshot: _SceneSnapshot, location_id: str) -> dict[str, int]:
    buffs = snapshot.location_buffs.get(location_id, {})
    if not is_starry_location(location_id) and snapshot.global_frame_count > 0:
        buffs = {**buffs, BuffEffect.BUFF_TYPE_FRAME: snapshot.global_frame_count}
    if not is_starry_location(location_id) and snapshot.starry_bonus_count > 0:
        buffs = {
            **buffs,
            BuffEffect.BUFF_TYPE_STARRY_BONUS: snapshot.starry_bonus_count,
        }
    return buffs


def _fish_catalog(location) -> tuple[list[str], list[list[int]]]:
    names = list(location.fish_pool)
    prices = []
    for fish_name in names:
        fish = ConfigManager.get_fish(fish_name)
        base_price = fish.base_price if fish else 0
        prices.append(
            [
                int(base_price * RARITY_MULTIPLIER.get(rarity, 1))
                for rarity in _RARITY_ORDER
            ]
        )
    return names, prices


def _location_payload(snapshot: _SceneSnapshot, location) -> dict:
    names, prices = _fish_catalog(location)
    return {
        "id": location.id,
        "name": location.name,
        "lv": location.difficulty,
        "fishers": snapshot.fisher_counts.get(location.id, 0),
        "buffs": _location_buffs(snapshot, location.id),
        "weather": snapshot.weathers.get(location.id, {}),
        "fish_names": names,
        "fish_prices": prices,
    }


def _cached_user_maps(
    users: list, locations: list, now_mono: float
) -> tuple[dict, dict]:
    global _collections_cache, _collections_cache_time
    global _cat_park_cache, _cat_park_cache_time

    if (
        _collections_cache is None
        or now_mono - _collections_cache_time >= _COLLECTION_CACHE_TTL
    ):
        _collections_cache = _compute_collections(users, locations)
        _collections_cache_time = time.monotonic()
    if (
        _cat_park_cache is None
        or now_mono - _cat_park_cache_time >= _COLLECTION_CACHE_TTL
    ):
        _cat_park_cache = _compute_cat_park_states(users)
        _cat_park_cache_time = time.monotonic()
    return _collections_cache, _cat_park_cache


async def _load_user_buffs(users: list, now: datetime) -> dict[str, list[dict]]:
    buffs = await FishingBuff.filter(
        target_type=BuffEffect.TARGET_TYPE_USER,
        target_id__in=[user.user_id for user in users],
        start_time__lte=now,
        end_time__gt=now,
        buff_type__in=_POTION_BUFF_TYPES,
    ).all()
    result: dict[str, list[dict]] = {}
    for buff in buffs:
        result.setdefault(buff.target_id, []).append(
            {
                "type": buff.buff_type,
                "value": buff.value,
                "start_time": buff.start_time.isoformat(),
                "end_time": buff.end_time.isoformat(),
            }
        )
    return result


def _bait_state(user) -> tuple[str, int]:
    if not user.bait_id or user.bait_id == "0":
        return "", 0
    bait = ConfigManager.get_bait(user.bait_id)
    items = user.items if isinstance(user.items, dict) else {}
    entry = items.get(f"{user.bait_id}|bait") or {}
    return bait.name if bait else "", entry.get("count", 0)


def _fishing_state(user, now: datetime) -> tuple[str, str, int]:
    status = user.fishing_status
    if not isinstance(status, dict):
        return "", "", 0
    location_id = status.get("location_id", "")
    location = ConfigManager.get_location(location_id) if location_id else None
    duration = 0
    try:
        if status.get("start_time"):
            duration = int(
                (now - datetime.fromisoformat(status["start_time"])).total_seconds()
            )
    except (ValueError, TypeError):
        pass
    return location_id, location.name if location else "", duration


def _player_payload(
    user,
    now: datetime,
    locations: list,
    collections: dict,
    cat_parks: dict,
    buffs: dict,
) -> dict:
    bait_name, bait_remaining = _bait_state(user)
    location_id, location_name, duration = _fishing_state(user, now)
    achievements = user.achievements if isinstance(user.achievements, list) else []
    return {
        "user_id": user.user_id,
        "nickname": user.nickname or "",
        "rod_level": user.rod_level,
        "hook_level": user.hook_level,
        "bait_id": user.bait_id,
        "bait_name": bait_name,
        "bait_remaining": bait_remaining,
        "location_id": location_id,
        "location_name": location_name,
        "fishing_duration_seconds": duration,
        "achievements": [
            item
            for item in achievements
            if isinstance(item, str) and item.startswith("collect_scene_")
        ],
        "buffs": buffs.get(user.user_id, []),
        "collections": collections.get(user.user_id, [""] * len(locations)),
        "cat_park": cat_parks.get(user.user_id, "000000000"),
        "starry_score_accumulated": float(user.starry_score_accumulated or 0),
        "star_frames": int(user.star_frames or 0),
        "starry_frames": int(user.starry_frames or 0),
        "s2_ticket_claimed": bool(user.s2_ticket_claimed),
        "starry_exhibition_count": len(user.starry_exhibition)
        if user.starry_exhibition
        else 0,
        "starry_fish_count": len(user.starry_fish) if user.starry_fish else 0,
    }


@_route("/")
async def _get_status_json() -> str:
    global _cache_body, _cache_time

    now_mono = time.monotonic()
    if _cache_body is not None and (now_mono - _cache_time) < _CACHE_TTL_SECONDS:
        return _cache_body

    try:
        now = datetime.now()
        snapshot = await _load_scene_snapshot()
        collections, cat_parks = _cached_user_maps(
            snapshot.users, snapshot.locations, now_mono
        )
        user_buffs = await _load_user_buffs(snapshot.users, now)
        result = {
            "updated_at": now.isoformat(),
            "locations": [
                _location_payload(snapshot, location) for location in snapshot.locations
            ],
            "players": [
                _player_payload(
                    user,
                    now,
                    snapshot.locations,
                    collections,
                    cat_parks,
                    user_buffs,
                )
                for user in snapshot.users
            ],
        }

        body = json.dumps(result, ensure_ascii=False)
        _cache_body = body
        _cache_time = time.monotonic()
        return body
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@_route("/scene")
async def _get_scene_json() -> str:
    try:
        snapshot = await _load_scene_snapshot()
        scenes = []
        for location in snapshot.locations:
            fishers = snapshot.fisher_counts.get(location.id, 0)
            buffs = _location_buffs(snapshot, location.id)
            if fishers > 0 or any(value > 0 for value in buffs.values()):
                scenes.append(
                    {
                        "id": location.id,
                        "name": location.name,
                        "difficulty": location.difficulty,
                        "fishers": fishers,
                        "buffs": buffs,
                        "weather": snapshot.weathers.get(location.id, {}),
                    }
                )

        return json.dumps(
            {"updated_at": datetime.now().isoformat(), "active_scenes": scenes},
            ensure_ascii=False,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@_route("/starry")
async def _get_starry_json() -> str:
    try:
        users = await FishingUser.all()

        starry_players = []
        for user in users:
            score = float(user.starry_score_accumulated or 0)
            if score <= 0:
                continue
            starry_players.append(
                {
                    "user_id": user.user_id,
                    "nickname": user.nickname or "",
                    "starry_score_accumulated": score,
                    "star_frames": int(user.star_frames or 0),
                    "starry_frames": int(user.starry_frames or 0),
                    "starry_exhibition_count": len(user.starry_exhibition)
                    if user.starry_exhibition
                    else 0,
                    "starry_fish_count": len(user.starry_fish)
                    if user.starry_fish
                    else 0,
                    "s2_ticket_claimed": bool(user.s2_ticket_claimed),
                }
            )

        starry_players.sort(key=lambda p: p["starry_score_accumulated"], reverse=True)

        return json.dumps(
            {
                "updated_at": datetime.now().isoformat(),
                "rules": {
                    "base_drop_rate": 0.05,
                    "id_digits": 6,
                    "s2_ticket_score_threshold": S2_TICKET_SCORE_THRESHOLD,
                    "s2_ticket_source": "score_accumulation",
                    "reward_pools": _STARRY_REWARD_POOLS,
                    "miracle_target": 7777777,
                    "miracle_mod_base": 10000000,
                    "exhibition_min_score": 4,
                    "exhibition_limit": 10,
                },
                "starry_players": starry_players,
            },
            ensure_ascii=False,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


async def _run_server():
    server = await asyncio.start_server(
        _handle_request, "0.0.0.0", _FISHING_STATUS_PORT
    )
    async with server:
        await server.serve_forever()


def start_status_server():
    global _server_task
    if _server_task is not None:
        return
    _server_task = asyncio.get_event_loop().create_task(_run_server())
