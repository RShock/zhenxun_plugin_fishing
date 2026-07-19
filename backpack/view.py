"""
背包视图渲染 — get_backpack_image, get_collection_image。
"""

from ..config import ConfigManager, calculate_fish_price, generate_fish_numeric_id
from ..models import FishingUser
from ..render import render_backpack, render_collection, render_starry_exhibition
from ..services import get_or_create_user


def build_potion_inventory(items_list: list[dict]) -> list[dict]:
    """Build backpack potion rows from stored item entries, including legacy keys."""
    potion_list = []
    for item in items_list:
        if item.get("item_type") != "potion" or item.get("count", 0) <= 0:
            continue
        item_id = str(item.get("item_id", ""))
        if item_id == "time_potion":
            potion_list.append(
                {
                    "item_id": item_id,
                    "name": "时光药水",
                    "count": item["count"],
                    "sort_key": 0,
                }
            )
            continue
        potion = ConfigManager.get_potion(item_id)
        potion_list.append(
            {
                "item_id": item_id,
                "name": potion.name if potion else item_id,
                "count": item["count"],
                "sort_key": potion.id if potion else 999,
            }
        )
    potion_list.sort(key=lambda p: (p["sort_key"], p["name"]))
    for potion in potion_list:
        potion.pop("sort_key", None)
    return potion_list



_MISC_ITEM_NAMES = {
    "black_market_extra_ticket": "黑商额外兑换券",
    "lottery_fragment_low": "中级抽奖碎片",
    "lottery_fragment_mid": "高级抽奖碎片",
    "lottery_fragment_high": "究极抽奖碎片",
    "utr_select_ticket": "UTR自选券",
}


def build_misc_inventory(items_list: list[dict]) -> list[dict]:
    """Tickets/fragments from starry lottery for backpack props section."""
    result = []
    for item in items_list:
        item_type = item.get("item_type")
        count = int(item.get("count", 0) or 0)
        if count <= 0:
            continue
        item_id = str(item.get("item_id", ""))
        if item_type in ("ticket", "fragment") or item_id in _MISC_ITEM_NAMES:
            name = _MISC_ITEM_NAMES.get(item_id, item_id)
            result.append({"item_id": item_id, "name": name, "count": count})
    result.sort(key=lambda x: x["name"])
    return result

def _coerce_starry_records(raw) -> list[dict]:
    """Normalize starry_fish / starry_exhibition payloads from DB or memory."""
    if not raw:
        return []
    if isinstance(raw, str):
        import json

        try:
            raw = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    if not isinstance(raw, list):
        return []
    result: list[dict] = []
    for record in raw:
        if not isinstance(record, dict):
            continue
        fish_id = record.get("id", record.get("fish_id", ""))
        if fish_id in (None, ""):
            continue
        try:
            numeric = int(fish_id)
            number = f"{numeric:06d}" if 0 <= numeric <= 999_999 else str(fish_id)
        except (TypeError, ValueError):
            number = str(fish_id).zfill(6)
        display_score = record.get("display_score")
        if display_score is None:
            display_score = record.get("score", 0)
        try:
            display_score = int(float(display_score))
        except (TypeError, ValueError):
            display_score = 0
        result.append(
            {
                "number": number,
                "count": 1,
                "display_score": display_score,
                "source": "starry",
            }
        )
    return result


def build_meteor_inventory(
    starry_fish=None,
    items_list: list[dict] | None = None,
) -> list[dict]:
    """汇总背包流星鱼列表。

    仅包含：
    1) 新版星空祈愿普通库存 `starry_fish`
    2) 旧版端午 `items.meteor_fish`

    展馆 `starry_exhibition` 不在背包显示，也不会被奇迹消耗。
    计分/努力值不消耗鱼；仅背包内鱼可参与奇迹并被消耗。
    """
    meteor_items: list[dict] = []
    for entry in _coerce_starry_records(starry_fish):
        meteor_items.append(
            {
                "number": entry["number"],
                "count": 1,
                "display_score": entry["display_score"],
                "source": "starry",
                "in_exhibition": False,
            }
        )
    for item in items_list or []:
        if item.get("item_type") != "meteor_fish" or item.get("count", 0) <= 0:
            continue
        for _ in range(int(item["count"])):
            meteor_items.append(
                {
                    "number": str(item.get("item_id", "")),
                    "count": 1,
                    "display_score": None,
                    "source": "legacy",
                    "in_exhibition": False,
                }
            )

    def _meteor_sort_key(entry: dict):
        num = str(entry.get("number", ""))
        source_rank = 0 if entry.get("source") == "starry" else 1
        try:
            numeric = int(num)
        except ValueError:
            numeric = 0
        score = entry.get("display_score")
        score_key = -(int(score) if score is not None else -1)
        # 星空祈愿：分高在前，同分编号大在前；旧版在后
        return (
            source_rank,
            score_key,
            -numeric if entry.get("source") == "starry" else numeric,
        )

    meteor_items.sort(key=_meteor_sort_key)
    return meteor_items


async def get_backpack_image(user_id: str) -> bytes:
    fish_list = await FishingUser.get_user_fish(user_id)
    user = await get_or_create_user(user_id)
    total_value = 0
    fish_with_price = []
    for fish in fish_list:
        fish_data = ConfigManager.get_fish(fish["fish_name"])
        price = calculate_fish_price(fish_data, fish["rarity"], 0) if fish_data else 0
        fish["price"] = price
        total_value += price * fish["count"]
        fish_with_price.append(fish)
    displays = await FishingUser.get_user_displays(user_id)
    upgraded_count = user.upgraded_display_count
    starry_count = int(getattr(user, "starry_frames", 0) or 0)
    for d in displays:
        fish_data = ConfigManager.get_fish_by_name(d["fish_name"])
        if fish_data:
            price = calculate_fish_price(fish_data, d["rarity"], 0)
            d["price"] = price
        else:
            d["price"] = 0
    sorted_by_price = sorted(
        range(len(displays)), key=lambda i: displays[i].get("price", 0), reverse=True
    )
    starry_indices = (
        set(sorted_by_price[:starry_count]) if starry_count > 0 else set()
    )
    upgraded_indices = (
        set(sorted_by_price[:upgraded_count]) if upgraded_count > 0 else set()
    )
    for i, d in enumerate(displays):
        if i in starry_indices:
            d["daily_income"] = d.get("price", 0) * 4
        elif i in upgraded_indices:
            d["daily_income"] = d.get("price", 0) * 3
        else:
            d["daily_income"] = d.get("price", 0) * 2

    items_list = await FishingUser.get_user_items(user_id)
    bait_items = [i for i in items_list if i["item_type"] == "bait" and i["count"] > 0]
    bait_list = []
    for item in bait_items:
        bait_data = ConfigManager.get_bait(int(item["item_id"]))
        if bait_data and item["count"] > 0:
            bait_list.append({"name": bait_data.name, "count": item["count"]})

    potion_list = build_potion_inventory(items_list)
    misc_list = build_misc_inventory(items_list)
    # show tickets/fragments alongside potions
    potion_list = potion_list + [
        {"item_id": m["item_id"], "name": m["name"], "count": m["count"]} for m in misc_list
    ]

    # 背包只显示 starry_fish + 旧版 meteor_fish；展馆鱼仅在展馆页。
    starry_fish = getattr(user, "starry_fish", None)
    if hasattr(FishingUser, "get_user_starry_fish"):
        try:
            starry_fish = await FishingUser.get_user_starry_fish(user_id)
        except Exception:
            pass

    meteor_items = build_meteor_inventory(
        starry_fish=starry_fish,
        items_list=items_list,
    )

    # 猫猫乐园建设素材（加入重要分区）
    from ..cat_park import CAT_PARK_MATERIAL_WEIGHTS, get_cat_park_materials

    cat_park_materials = await get_cat_park_materials(user_id)
    material_list = [
        {"name": name, "count": count}
        for name, count in cat_park_materials.items()
        if count > 0
    ]
    # 保持固定顺序
    material_order = list(CAT_PARK_MATERIAL_WEIGHTS)
    material_list.sort(key=lambda m: material_order.index(m["name"]) if m["name"] in material_order else 99)

    return await render_backpack(
        user_id,
        fish_with_price,
        total_value,
        displays,
        user.display_slots,
        user.gold,
        bait_list=bait_list,
        corn_count=user.corn,
        display_frames=user.display_frames,
        upgraded_display_count=user.upgraded_display_count,
        cat_frames=user.cat_frames,
        potion_list=potion_list,
        meteor_items=meteor_items,
        cat_park_materials=material_list,
        star_frames=int(getattr(user, "star_frames", 0) or 0),
        starry_frames=int(getattr(user, "starry_frames", 0) or 0),
    )


async def get_collection_image(user_id: str, page: int = 1) -> bytes:
    all_locations = ConfigManager.get_locations()
    collected_set = await FishingUser.get_user_collected(user_id)

    from ..starry import has_starry_ship, is_starry_location

    show_starry = page == 2
    has_ship = await has_starry_ship(user_id) if show_starry else False

    has_utr = any(rarity == "UTR" for _, rarity in collected_set)

    rarities_list = (
        ["N", "R", "SR", "SSR", "UR", "UTR"]
        if has_utr
        else ["N", "R", "SR", "SSR", "UR"]
    )
    full_rarities = ["N", "R", "SR", "SSR", "UR", "UTR"]

    collection_data = []
    for loc in all_locations:
        if show_starry:
            if not has_ship or not is_starry_location(loc.id):
                continue
        elif is_starry_location(loc.id):
            continue

        # S1 猫猫乐园：仅在用户解锁任意一条活动鱼后才显示图鉴
        if loc.id.upper() == "S1":
            s1_fish_ids = set(loc.fish_pool)
            has_any_s1_collected = any(
                (fid, rarity) in collected_set
                for fid in s1_fish_ids
                for rarity in full_rarities
            )
            if not has_any_s1_collected:
                continue

        loc_data = {
            "name": loc.name,
            "difficulty": loc.difficulty,
            "id": loc.id,
            "fish": [],
            "scene_complete": False,
        }
        all_fish_complete = True
        start_index = 0 if loc.id.upper() == "S1" else 1
        for fish_idx, fish_id in enumerate(loc.fish_pool, start_index):
            fish = ConfigManager.get_fish(fish_id)
            if fish:
                fish_data = {
                    "id": fish.id,
                    "name": fish.id,
                    "index": fish_idx,
                    "rarities": {},
                    "fish_complete": False,
                }
                all_rarities_collected = True
                for rarity in rarities_list:
                    numeric_id = generate_fish_numeric_id(loc.id, fish_idx, rarity)
                    collected = (fish.id, rarity) in collected_set
                    fish_data["rarities"][rarity] = {
                        "collected": collected,
                        "numeric_id": numeric_id,
                    }
                    if not collected:
                        all_rarities_collected = False
                for rarity in full_rarities:
                    if (fish.id, rarity) not in collected_set:
                        all_rarities_collected = False
                        break
                fish_data["fish_complete"] = all_rarities_collected
                if not all_rarities_collected:
                    all_fish_complete = False
                loc_data["fish"].append(fish_data)
        loc_data["scene_complete"] = all_fish_complete
        collection_data.append(loc_data)

    return await render_collection(collection_data, has_utr)


async def get_starry_exhibition_image(user_id: str) -> bytes:
    user = await get_or_create_user(user_id)
    return await render_starry_exhibition(user_id, user)
