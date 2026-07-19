"""
网页端 HTTP API — 供前端定时轮询和按需查询角色状态/背包/场景/成就/图鉴。
"""

from datetime import datetime

from aiohttp import web

from .key_manager import KeyManager

# ── 认证 ──────────────────────────────────────────────────────────────


async def _auth(request: web.Request) -> str | None:
    secret = request.query.get("secret", "")
    if not secret:
        return None
    return await KeyManager().authenticate(secret)


async def _require_auth(request: web.Request) -> tuple[str | None, web.Response | None]:
    auth_user = await _auth(request)
    if not auth_user:
        return None, web.json_response({"error": "unauthorized"}, status=401)
    target_user = request.match_info["user_id"]
    # "_" 是前端在未知 user_id 时使用的占位符
    if target_user != "_" and auth_user != target_user:
        return None, web.json_response({"error": "unauthorized"}, status=401)
    return auth_user, None


def auth_required(handler):
    """装饰器：自动提取认证后的 user_id 注入到 handler。"""

    async def wrapper(request: web.Request) -> web.Response:
        user_id, err = await _require_auth(request)
        if err:
            return err
        return await handler(request, user_id)

    return wrapper


# ── 辅助函数 ──────────────────────────────────────────────────────────


def _build_fishing_status(status: dict) -> dict:
    """从原始钓鱼状态构建前端格式的钓鱼状态数据。"""
    from ..config import ConfigManager

    loc = ConfigManager.get_location(status.get("location_id", ""))
    st = status.get("start_time")
    if st:
        if isinstance(st, datetime):
            elapsed = (datetime.now() - st.replace(tzinfo=None)).total_seconds()
            st_str = st.isoformat()
        else:
            elapsed = 0
            st_str = str(st)
    else:
        elapsed = 0
        st_str = ""
    return {
        "is_fishing": True,
        "location_id": status.get("location_id", ""),
        "location_name": loc.name if loc else "",
        "start_time": st_str,
        "elapsed_seconds": int(elapsed),
    }


_KNOWN_ITEM_NAMES = {"time_potion": "时光药水"}


def _translate_item(item_id: str | int, item_type: str, config: "ConfigManager") -> str:
    if item_type == "bait":
        bait = config.get_bait(item_id)
        if bait:
            return bait.name
    else:
        potion = config.get_potion(item_id)
        if potion:
            return potion.name
    return _KNOWN_ITEM_NAMES.get(str(item_id), str(item_id))


# ── API 端点 ──────────────────────────────────────────────────────────


@auth_required
async def get_state(request: web.Request, user_id: str) -> web.Response:
    from ..config import ConfigManager, calculate_fish_price
    from ..models import FishingBuff, FishingUser
    from ..services import get_or_create_user
    from ..weather_service import get_all_location_weathers

    user = await get_or_create_user(user_id)

    player = {
        "user_id": user.user_id,
        "nickname": user.nickname,
        "gold": user.gold,
        "rod_level": user.rod_level,
        "hook_level": user.hook_level,
        "display_slots": user.display_slots,
        "display_frames": user.display_frames,
        "corn": user.corn,
        "cat_frames": user.cat_frames,
        "upgraded_display_count": user.upgraded_display_count,
        "auto_sell_enabled": user.auto_sell,
        "auto_sell_rarity": user.auto_sell_rarity,
        "auto_lock_enabled": user.auto_lock,
        "auto_lock_pattern": user.auto_lock_pattern,
        "bait_id": user.bait_id,
        "frame_pity": user.frame_pity_counter,
        "utr_pity": user.utr_pity_counter,
        "cat_frame_pity": user.cat_frame_pity_counter,
    }

    # ── 钓鱼状态 ──
    is_fishing = await FishingUser.is_fishing(user_id)
    if is_fishing:
        status = await FishingUser.get_status(user_id)
        fishing = (
            _build_fishing_status(status)
            if status and isinstance(status, dict)
            else {"is_fishing": True}
        )
    else:
        fishing = {"is_fishing": False}

    # ── 背包 ──
    fish_raw = await FishingUser.get_user_fish(user_id)
    total_value = 0
    fish_list = []
    for f in fish_raw:
        fd = ConfigManager.get_fish(f.get("fish_name", ""))
        price = calculate_fish_price(fd, f.get("rarity", "N"), 0) if fd else 0
        total_value += price * f.get("count", 0)
        fish_list.append(
            {
                "numeric_id": f.get("numeric_id", ""),
                "fish_name": f.get("fish_name", ""),
                "rarity": f.get("rarity", "N"),
                "count": f.get("count", 0),
                "locked": f.get("locked", False),
                "price": price,
            }
        )

    items_raw = await FishingUser.get_user_items(user_id)
    items = []
    baits = []
    for i in items_raw:
        entry = {
            "item_id": i["item_id"],
            "item_type": i["item_type"],
            "count": i["count"],
            "name": _translate_item(i["item_id"], i["item_type"], ConfigManager),
        }
        items.append(entry)
        if i["item_type"] == "bait":
            baits.append(entry)

    displays = await FishingUser.get_user_displays(user_id)
    backpack = {
        "fish": fish_list,
        "total_fish_count": len(fish_list),
        "items": items,
        "baits": baits,
        "displays": displays,
        "total_value": total_value,
    }

    # ── 场景 + 天气 + buff ──
    from ..cat_park import has_cat_park_ticket, is_cat_park_location
    from ..starry import has_starry_ship, is_starry_location

    locations_cfg = ConfigManager.get_locations()
    fisher_counts = await FishingUser.get_location_fisher_counts()
    frame_bonus_by_loc = {}
    for loc in locations_cfg:
        frame_count = await FishingBuff.get_frame_buff_count_for_location(loc.id)
        frame_bonus_by_loc[loc.id] = frame_count * 5
    all_weathers = await get_all_location_weathers(user_id)
    has_ticket = await has_cat_park_ticket(user_id)
    has_ship = await has_starry_ship(user_id)

    loc_data = []
    for loc in locations_cfg:
        if is_cat_park_location(loc.id):
            if not has_ticket:
                continue
            unlocked = True
        elif is_starry_location(loc.id):
            if not has_ship:
                continue
            unlocked = loc.difficulty <= user.rod_level
        else:
            unlocked = loc.difficulty <= user.rod_level

        fc = fisher_counts.get(loc.id, 0)
        nest_count = await FishingBuff.get_location_buff_count(loc.id)
        w = all_weathers.get(loc.id)
        weather = (
            {
                "type": w.get("weather_type", "sunny"),
                "is_active": w.get("is_active", False),
                "status": w.get("weather_status", "ended"),
            }
            if w
            else {
                "type": "chaotic_era" if is_starry_location(loc.id) else "sunny",
                "is_active": False,
                "status": "ended",
            }
        )
        loc_data.append(
            {
                "id": loc.id,
                "name": loc.name,
                "difficulty": loc.difficulty,
                "unlocked": unlocked,
                "fisher_count": fc,
                "nest_bonus": nest_count * 5,
                "frame_bonus": frame_bonus_by_loc.get(loc.id, 0),
                "weather": weather,
            }
        )

    return web.json_response(
        {
            "player": player,
            "fishing": fishing,
            "backpack": backpack,
            "locations": loc_data,
        }
    )


@auth_required
async def get_achievements(request: web.Request, user_id: str) -> web.Response:
    from ..config import ConfigManager
    from ..models import FishingUser
    from ..services.achievement_service import RARITIES_UP_TO_UR

    completed = await FishingUser.get_user_achievements(user_id)
    all_locations = ConfigManager.get_locations()

    achievement_list = []
    for loc in all_locations:
        all_fish_in_pool = [
            ConfigManager.get_fish(fid)
            for fid in loc.fish_pool
            if ConfigManager.get_fish(fid)
        ]

        loc_achievements = []

        def _add(key: str, name: str):
            loc_achievements.append(
                {
                    "key": key,
                    "name": name,
                    "completed": key in completed,
                }
            )

        # 稀有度收集成就
        for rarity in RARITIES_UP_TO_UR:
            _add(
                f"collect_rarity_{loc.id}_{rarity}", f"收集 {loc.name} 全部{rarity}级鱼"
            )

        # 单鱼全稀有度
        for fish in all_fish_in_pool:
            _add(f"collect_fish_{loc.id}_{fish.id}", f"{fish.id} 全稀有度收集")

        # 场景全收集
        _add(f"collect_scene_{loc.id}", f"{loc.name} 场景全收集")

        # 真全稀有度
        for fish in all_fish_in_pool:
            _add(f"collect_fish_utr_{loc.id}_{fish.id}", f"{fish.id} 真全稀有度收集")

        _add(f"collect_scene_utr_{loc.id}", f"{loc.name} 场景真全收集")

        achievement_list.append(
            {
                "location_id": loc.id,
                "location_name": loc.name,
                "achievements": loc_achievements,
            }
        )

    return web.json_response({"achievements": achievement_list})


@auth_required
async def get_collection(request: web.Request, user_id: str) -> web.Response:
    from ..config import ConfigManager, generate_fish_numeric_id
    from ..models import FishingUser

    all_locations = ConfigManager.get_locations()
    collected_set = await FishingUser.get_user_collected(user_id)
    has_utr = any(rarity == "UTR" for _, rarity in collected_set)
    full_rarities = ["N", "R", "SR", "SSR", "UR", "UTR"]

    rarities_list = full_rarities if has_utr else full_rarities[:-1]

    collection_data = []
    for loc in all_locations:
        loc_fish = []
        start_index = 0 if loc.id.upper() == "S1" else 1
        for fish_idx, fish_id in enumerate(loc.fish_pool, start_index):
            fish = ConfigManager.get_fish(fish_id)
            if not fish:
                continue
            rarities = {}
            all_rarities_done = True
            for rarity in rarities_list:
                numeric_id = generate_fish_numeric_id(loc.id, fish_idx, rarity)
                collected = (fish.id, rarity) in collected_set
                rarities[rarity] = {
                    "collected": collected,
                    "numeric_id": numeric_id,
                }
                if not collected:
                    all_rarities_done = False
            # 补检 full_rarities 中未在 rarities_list 的稀有度
            for rarity in full_rarities:
                if (fish.id, rarity) not in collected_set:
                    all_rarities_done = False
                    break
            loc_fish.append(
                {
                    "id": fish.id,
                    "name": fish.id,
                    "index": fish_idx,
                    "rarities": rarities,
                    "fish_complete": all_rarities_done,
                }
            )

        all_complete = all(f["fish_complete"] for f in loc_fish)
        collection_data.append(
            {
                "id": loc.id,
                "name": loc.name,
                "difficulty": loc.difficulty,
                "fish": loc_fish,
                "scene_complete": all_complete,
            }
        )

    return web.json_response(
        {
            "locations": collection_data,
            "has_utr": has_utr,
            "rarities": rarities_list,
        }
    )


def _is_scene_map_id(loc_id: str) -> bool:
    """场景图 id：数字或 s1/S1；排除「小雨/暴雨」等叠加层。"""
    if not loc_id:
        return False
    if loc_id[0].isdigit():
        return True
    return loc_id.lower().startswith("s") and len(loc_id) <= 4


async def get_scenes(request: web.Request) -> web.Response:
    """列出 scenes 目录下的场景图（轨道编辑器 / 调试用，无需鉴权）。"""
    from pathlib import Path
    from urllib.parse import quote

    scenes_dir = Path(__file__).parent.parent / "resources" / "images" / "scenes"
    items = []
    if scenes_dir.exists():
        for f in sorted(scenes_dir.glob("*.png"), key=lambda p: p.name.lower()):
            stem = f.stem
            parts = stem.split("-", 2)
            loc_id = parts[0] if parts else ""
            if not _is_scene_map_id(loc_id):
                continue
            name = parts[1] if len(parts) > 1 else stem
            layout = parts[2] if len(parts) > 2 else ""
            # 文件名含 @ + 中文等，必须 URL 编码，避免 + 被当成空格
            items.append(
                {
                    "id": loc_id,
                    "name": name,
                    "layout": layout,
                    "filename": f.name,
                    "url": f"/api/resource/images/scenes/{quote(f.name)}",
                }
            )
    return web.json_response({"scenes": items})
