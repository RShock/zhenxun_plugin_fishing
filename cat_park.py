"""猫猫乐园活动逻辑。"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from PIL import Image

from zhenxun.services.log import logger

from .config import ConfigManager, FishData, LocationData, calculate_fish_price
from .models import FishingUser
from .render.base import FONT_FAMILY_DEFAULT, gradient_bg, render_html

CAT_PARK_LOCATION_ID = "S1"
CAT_PARK_STATE_ITEM_ID = "cat_park_state"
CAT_PARK_STATE_ITEM_TYPE = "event_state"
CAT_PARK_MATERIAL_TYPE = "cat_park_material"
CAT_PARK_DIFFICULTY = 6
CAT_PARK_FISH_PRICE_RATE = 1.0  # 猫猫乐园鱼价系数（原0.99为平衡方程求解值，改为1.0以对玩家友好，建筑加成增幅不再被隐藏折扣稀释）
CAT_PARK_MATERIAL_RATE = 0.30  # 基础材料率（猫爬架广场 Lv0）；Lv1~Lv3 随建筑等级递增
CAT_PARK_MATERIAL_PRICE = 80
CAT_PARK_GRAY_TEST_USER_IDS = {"418648118", "470103427"}

# 建筑等级字符串的输出顺序，必须与建设列表编号/用户可见建筑顺序保持一致。
# status_api 返回的 cat_park 字段按此顺序编码 9 个建筑等级（'0'-'3'）。
CAT_PARK_IMAGE_BUILDING_ORDER = [
    "猫猫小木屋",
    "喵喵鱼塘",
    "猫爬架广场",
    "喵咖咖啡馆",
    "猫猫过山车",
    "旋转逗猫棒",
    "水晶猫城堡",
    "猫咪摩天轮",
    "传奇猫雕像",
]

CAT_PARK_FISH = [
    "橘座鲫鱼",
    "暹罗鳊鱼",
    "布偶白条",
    "奶牛麦穗",
    "三花泥鳅",
    "金渐层锦鲤",
    "英短青鱼",
    "无毛鲶鱼",
    "折耳翘嘴",
    "卷耳黄颡",
]

CAT_PARK_MATERIAL_WEIGHTS = {
    "毛线团": 1,
    "特级小鱼干": 1,
    "彩虹逗猫棒": 1,
}

CAT_PARK_BUILDING_EFFECTS = {
    "猫猫小木屋": ["鱼饵节省 3%", "鱼饵节省 6%", "鱼饵节省 10%"],
    "喵喵鱼塘": ["钓鱼速度 +3%", "钓鱼速度 +6%", "钓鱼速度 +10%"],
    "猫爬架广场": ["材料率 35%", "材料率 40%", "材料率 45%"],
    "喵咖咖啡馆": ["鱼价 +3%", "鱼价 +6%", "鱼价 +10%"],
    "旋转逗猫棒": ["双倍鱼获 3%", "双倍鱼获 6%", "双倍鱼获 10%"],
    "猫咪摩天轮": ["每日签到 1抽", "每日签到 2抽", "每日签到 3抽"],
    "猫猫过山车": ["天气增幅 3%", "天气增幅 6%", "天气增幅 10%"],
    "水晶猫城堡": ["钓鱼等级+1概率 5%", "钓鱼等级+1概率 15%", "钓鱼等级+1概率 30%"],
    "传奇猫雕像": ["解锁 Lv2", "解锁 Lv3", "鱼竿等级 +1"],
}

CAT_PARK_BUILD_COSTS = {
    # 单材料（a/b/c 各 1）：毛线团 / 特级小鱼干 / 彩虹逗猫棒
    # Lv1 降 25%, Lv2 降 15%, Lv3 不变 → 平滑前期过渡
    "猫猫小木屋": {
        1: {"毛线团": 15},
        2: {"毛线团": 30},
        3: {"毛线团": 55},
    },
    "喵喵鱼塘": {
        1: {"特级小鱼干": 18},
        2: {"特级小鱼干": 34},
        3: {"特级小鱼干": 60},
    },
    "猫爬架广场": {
        1: {"彩虹逗猫棒": 15},
        2: {"彩虹逗猫棒": 30},
        3: {"彩虹逗猫棒": 55},
    },
    # ab（毛线团 + 特级小鱼干）各 2
    "喵咖咖啡馆": {
        1: {"毛线团": 9, "特级小鱼干": 9},
        2: {"毛线团": 17, "特级小鱼干": 17},
        3: {"毛线团": 30, "特级小鱼干": 30},
    },
    "猫猫过山车": {
        1: {"毛线团": 9, "特级小鱼干": 9},
        2: {"毛线团": 17, "特级小鱼干": 17},
        3: {"毛线团": 30, "特级小鱼干": 30},
    },
    # bc（特级小鱼干 + 彩虹逗猫棒）各 2
    "旋转逗猫棒": {
        1: {"特级小鱼干": 9, "彩虹逗猫棒": 9},
        2: {"特级小鱼干": 17, "彩虹逗猫棒": 17},
        3: {"特级小鱼干": 30, "彩虹逗猫棒": 30},
    },
    "水晶猫城堡": {
        1: {"特级小鱼干": 9, "彩虹逗猫棒": 9},
        2: {"特级小鱼干": 17, "彩虹逗猫棒": 17},
        3: {"特级小鱼干": 30, "彩虹逗猫棒": 30},
    },
    # ac（毛线团 + 彩虹逗猫棒）各 2，含雕像
    "猫咪摩天轮": {
        1: {"毛线团": 9, "彩虹逗猫棒": 9},
        2: {"毛线团": 17, "彩虹逗猫棒": 17},
        3: {"毛线团": 30, "彩虹逗猫棒": 30},
    },
    "传奇猫雕像": {
        1: {"毛线团": 12, "彩虹逗猫棒": 12},
        2: {"毛线团": 24, "彩虹逗猫棒": 24},
        3: {"毛线团": 42, "彩虹逗猫棒": 42},
    },
}

_EVENT_IMAGE_DIR = Path(__file__).parent / "resources" / "images" / "event1"
_CAT_PARK_BUILD_BACKGROUND = _EVENT_IMAGE_DIR / "大地图.png"
_SCENE_IMAGE = (
    Path(__file__).parent / "resources" / "images" / "scenes" / "s1-猫猫乐园-72.png"
)
_MAP_JSON = _EVENT_IMAGE_DIR / "cat_park_map.json"


def is_cat_park_location(location_id: str | None) -> bool:
    return bool(location_id) and location_id.upper() == CAT_PARK_LOCATION_ID


def get_cat_park_location() -> LocationData:
    """从 ConfigManager 获取 S1 位置数据（统一配置源，避免硬编码漂移）。"""
    from .config import ConfigManager

    loc = ConfigManager.get_location(CAT_PARK_LOCATION_ID)
    if loc is None:
        raise RuntimeError("S1 猫猫乐园未在 locations.json 中配置")
    return loc


def get_cat_park_total_cost() -> int:
    return sum(
        sum(cost.values())
        for levels in CAT_PARK_BUILD_COSTS.values()
        for cost in levels.values()
    )


def _default_state() -> dict[str, Any]:
    return {
        "buildings": dict.fromkeys(CAT_PARK_BUILD_COSTS, 0),
        "rod_reward_claimed": False,
    }


async def get_cat_park_state(user_id: str) -> dict[str, Any]:
    item = await FishingUser.get_item(
        user_id, CAT_PARK_STATE_ITEM_ID, CAT_PARK_STATE_ITEM_TYPE
    )
    if not item:
        return _default_state()
    raw = item.get("data") or item.get("extra")
    if not raw:
        user = await FishingUser.get_user(user_id)
        entry = (
            user.items.get(f"{CAT_PARK_STATE_ITEM_ID}|{CAT_PARK_STATE_ITEM_TYPE}", {})
            if user.items
            else {}
        )
        raw = entry.get("data")
    if isinstance(raw, str):
        try:
            state = json.loads(raw)
        except json.JSONDecodeError:
            return _default_state()
    elif isinstance(raw, dict):
        state = raw
    else:
        return _default_state()
    default = _default_state()
    buildings = state.get("buildings", {})
    default["buildings"].update(
        {k: int(v) for k, v in buildings.items() if k in default["buildings"]}
    )
    default["rod_reward_claimed"] = bool(state.get("rod_reward_claimed", False))
    return default


async def save_cat_park_state(user_id: str, state: dict[str, Any]) -> None:
    user = await FishingUser.get_user(user_id)
    user.items = user.items if isinstance(user.items, dict) else {}
    key = f"{CAT_PARK_STATE_ITEM_ID}|{CAT_PARK_STATE_ITEM_TYPE}"
    user.items[key] = {
        "item_type": CAT_PARK_STATE_ITEM_TYPE,
        "count": 1,
        "data": json.dumps(state, ensure_ascii=False),
    }
    user.items = dict(user.items)
    await user.save(update_fields=["items"])


def is_cat_park_gray_test_user(user_id: str) -> bool:
    return str(user_id).strip() in CAT_PARK_GRAY_TEST_USER_IDS


async def has_two_normal_utr_collections(user_id: str) -> bool:
    collected = await FishingUser.get_user_collected(user_id)
    completed_count = 0
    for loc in ConfigManager.get_locations():
        if loc.id == CAT_PARK_LOCATION_ID:
            continue
        if all((fish_name, "UTR") in collected for fish_name in loc.fish_pool):
            completed_count += 1
            if completed_count >= 2:
                return True
    return False


async def has_cat_park_ticket(user_id: str) -> bool:
    return is_cat_park_gray_test_user(user_id) or await has_two_normal_utr_collections(
        user_id
    )


async def get_cat_park_materials(user_id: str) -> dict[str, int]:
    result = dict.fromkeys(CAT_PARK_MATERIAL_WEIGHTS, 0)
    items = await FishingUser.get_user_items(user_id)
    for item in items:
        if item["item_type"] == CAT_PARK_MATERIAL_TYPE and item["item_id"] in result:
            result[item["item_id"]] = item["count"]
    return result


async def add_cat_park_material(
    user_id: str, material_name: str, count: int = 1
) -> None:
    await FishingUser.add_item(user_id, material_name, CAT_PARK_MATERIAL_TYPE, count)


def roll_cat_park_material() -> str:
    names = list(CAT_PARK_MATERIAL_WEIGHTS)
    weights = list(CAT_PARK_MATERIAL_WEIGHTS.values())
    return random.choices(names, weights=weights, k=1)[0]


def cat_park_building_level(state: dict[str, Any], building: str) -> int:
    return int(state.get("buildings", {}).get(building, 0))


def can_upgrade_cat_park_building(
    state: dict[str, Any], building: str
) -> tuple[bool, str]:
    buildings = state["buildings"]
    current = int(buildings.get(building, 0))
    if current >= 3:
        return False, "已满级"
    next_level = current + 1
    statue_level = int(buildings.get("传奇猫雕像", 0))
    if building == "传奇猫雕像":
        others = [lv for name, lv in buildings.items() if name != "传奇猫雕像"]
        if not all(lv >= next_level for lv in others):
            return False, f"需要其他8栋建筑全部达到 Lv{next_level}"
        return True, ""
    if next_level == 2 and statue_level < 1:
        return False, "需要先建成传奇猫雕像 Lv1"
    if next_level == 3 and statue_level < 2:
        return False, "需要先建成传奇猫雕像 Lv2"
    return True, ""


def _cost_text(cost: dict[str, int]) -> str:
    return "、".join(f"{name}{count}" for name, count in cost.items())


def _material_lacks(cost: dict[str, int], materials: dict[str, int]) -> list[str]:
    return [
        f"{name}{need - materials.get(name, 0)}"
        for name, need in cost.items()
        if materials.get(name, 0) < need
    ]


async def upgrade_cat_park_building(
    user_id: str, index_or_name: str
) -> tuple[bool, str]:
    state = await get_cat_park_state(user_id)
    building_names = list(CAT_PARK_BUILD_COSTS)
    target = index_or_name.strip()
    if target.isdigit():
        idx = int(target)
        if not 1 <= idx <= len(building_names):
            return False, "建筑编号不存在。"
        building = building_names[idx - 1]
    else:
        matches = [name for name in building_names if target in name]
        if not matches:
            return False, "建筑名称不存在。"
        building = matches[0]

    ok, reason = can_upgrade_cat_park_building(state, building)
    if not ok:
        return False, reason

    next_level = state["buildings"][building] + 1
    cost = CAT_PARK_BUILD_COSTS[building][next_level]
    materials = await get_cat_park_materials(user_id)
    lacks = _material_lacks(cost, materials)
    if lacks:
        return False, "材料不足：" + "、".join(lacks)

    for name, count in cost.items():
        await FishingUser.remove_item(user_id, name, CAT_PARK_MATERIAL_TYPE, count)
    state["buildings"][building] = next_level

    reward_msg = ""
    if (
        building == "传奇猫雕像"
        and next_level == 3
        and not state.get("rod_reward_claimed")
    ):
        user = await FishingUser.get_user(user_id)
        user.rod_level += 1
        user.bonus_rod_level += 1
        await user.save(update_fields=["rod_level", "bonus_rod_level"])
        state["rod_reward_claimed"] = True
        reward_msg = "\n最终奖励已发放：鱼竿等级 +1（额外加成，不影响商店升级价格）。"

    await save_cat_park_state(user_id, state)
    effect = CAT_PARK_BUILDING_EFFECTS[building][next_level - 1]
    completed_msg = ""
    if building == "传奇猫雕像" and next_level == 3:
        messages: list[str] = []
        await sell_completed_cat_park_materials(user_id, messages)
        if messages:
            completed_msg = "\n" + "\n".join(messages)
    return True, f"{building} 已升级到 Lv{next_level}，效果：{effect}。{reward_msg}{completed_msg}"


def _load_map_config() -> dict[str, Any]:
    if not _MAP_JSON.exists():
        return {"facilities": []}
    with open(_MAP_JSON, encoding="utf-8") as f:
        return json.load(f)


def _image_size(path: Path, default: tuple[int, int]) -> tuple[int, int]:
    if not path.exists():
        return default
    try:
        with Image.open(path) as img:
            return img.size
    except Exception:
        return default


def _map_background_size(
    cfg: dict[str, Any], actual_size: tuple[int, int]
) -> tuple[int, int]:
    size = cfg.get("backgroundSize") or {}
    width = int(size.get("width") or actual_size[0])
    height = int(size.get("height") or actual_size[1])
    return width, height


def _facility_image_src(facility: dict[str, Any], level: int) -> str:
    images = facility.get("images", {})
    image_names = facility.get("imageNames", {})
    value = images.get(str(level)) or image_names.get(str(level))
    if not value:
        return ""
    if isinstance(value, str) and value.startswith("data:image"):
        return value
    name = image_names.get(str(level)) or Path(str(value)).name
    path = _EVENT_IMAGE_DIR / name
    return path.as_uri() if path.exists() else ""


def _facility_image_size(facility: dict[str, Any], level: int) -> tuple[int, int]:
    size = (facility.get("imageSizes") or {}).get(str(level)) or {}
    width = int(size.get("w") or 0)
    height = int(size.get("h") or 0)
    if width > 0 and height > 0:
        return width, height
    image_names = facility.get("imageNames", {})
    name = image_names.get(str(level))
    if name:
        return _image_size(_EVENT_IMAGE_DIR / name, (64, 64))
    return 64, 64


async def render_cat_park_image(user_id: str, message: str = "") -> bytes:
    state = await get_cat_park_state(user_id)
    materials = await get_cat_park_materials(user_id)
    cfg = _load_map_config()
    actual_size = _image_size(_CAT_PARK_BUILD_BACKGROUND, (1376, 768))
    map_width, map_height = _map_background_size(cfg, actual_size)
    scene_scale = min(688 / actual_size[0], 384 / actual_size[1], 1)
    scene_width = round(actual_size[0] * scene_scale)
    scene_height = round(actual_size[1] * scene_scale)
    scale_x = actual_size[0] / map_width * scene_scale
    scale_y = actual_size[1] / map_height * scene_scale
    scene_src = (
        _CAT_PARK_BUILD_BACKGROUND.as_uri()
        if _CAT_PARK_BUILD_BACKGROUND.exists()
        else ""
    )

    facility_tags = []
    facilities = sorted(cfg.get("facilities", []), key=lambda f: int(f.get("y", 0)))
    for facility in facilities:
        name = facility.get("name", "")
        level = cat_park_building_level(state, name)
        if level <= 0:
            continue
        src = _facility_image_src(facility, level)
        if not src:
            continue
        img_w, img_h = _facility_image_size(facility, level)
        width = max(1, round(img_w * scale_x))
        height = max(1, round(img_h * scale_y))
        x = round(int(facility.get("x", 0)) * scale_x)
        y = round(int(facility.get("y", 0)) * scale_y)
        facility_tags.append(
            f"<img class='facility' src='{src}' style='left:{x}px; top:{y}px; width:{width}px; height:{height}px;' />"
        )
    facilities_html = "".join(facility_tags)

    rows = []
    for idx, name in enumerate(CAT_PARK_BUILD_COSTS, 1):
        level = cat_park_building_level(state, name)
        if level >= 3:
            next_text = "已满级"
            effect = CAT_PARK_BUILDING_EFFECTS[name][-1]
            can_upgrade = False
        else:
            next_level = level + 1
            cost = CAT_PARK_BUILD_COSTS[name][next_level]
            effect = CAT_PARK_BUILDING_EFFECTS[name][next_level - 1]
            condition_ok, reason = can_upgrade_cat_park_building(state, name)
            lacks = _material_lacks(cost, materials)
            can_upgrade = condition_ok and not lacks
            next_text = f"Lv{next_level}：{_cost_text(cost)}"
            if not condition_ok:
                next_text += f"（{reason}）"
            elif lacks:
                next_text += f"（材料不足：{'、'.join(lacks)}）"
        rows.append(
            {
                "idx": idx,
                "name": name,
                "level": level,
                "next": next_text,
                "effect": effect,
                "can": can_upgrade,
                "status_cls": "can-build" if can_upgrade else "normal",
            }
        )

    material_cards = []
    material_image_names = {
        "毛线团": "毛线团.png",
        "特级小鱼干": "小鱼干.png",
        "彩虹逗猫棒": "逗猫棒.png",
    }
    for name, count in materials.items():
        path = _EVENT_IMAGE_DIR / material_image_names.get(name, f"{name}.png")
        src = path.as_uri() if path.exists() else ""
        material_cards.append({"name": name, "count": count, "src": src})
    material_html = "".join(
        "<div class='material'>"
        + (f"<img src='{card['src']}' />" if card["src"] else "")
        + f"<div><div class='mn'>{card['name']}</div><div class='mc'>×{card['count']}</div></div></div>"
        for card in material_cards
    )
    html = f"""
<!doctype html><html><head><meta charset='utf-8'>
<style>
body {{ margin:0; padding:14px; width:720px; box-sizing:border-box; font-family:{FONT_FAMILY_DEFAULT}; background:{gradient_bg("peach")}; color:#3b2f2f; }}
.title {{ text-align:center; font-size:28px; font-weight:800; margin-bottom:10px; }}
.scene {{ position:relative; border:4px solid #fff3d2; border-radius:16px; box-shadow:0 8px 20px rgba(0,0,0,.18); image-rendering:pixelated; overflow:hidden; margin:0 auto; background:#eee6cd; }}
.scene-bg {{ position:absolute; inset:0; width:100%; height:100%; image-rendering:pixelated; }}
.facility {{ position:absolute; transform:translate(-50%,-50%); image-rendering:pixelated; }}
.panel {{ margin-top:10px; background:rgba(255,255,255,.88); border-radius:14px; padding:12px; }}
.msg {{ color:#b45125; font-weight:700; margin-bottom:8px; }}
.materials {{ display:grid; grid-template-columns:repeat(3, 1fr); gap:8px; margin-bottom:10px; }}
.material {{ display:flex; align-items:center; gap:6px; background:#fff7e8; border:1px solid #ead8bd; border-radius:10px; padding:6px; }}
.material img {{ width:34px; height:34px; object-fit:contain; image-rendering:pixelated; }}
.material .mn {{ font-size:13px; font-weight:700; }}
.material .mc {{ font-size:14px; color:#d36b20; font-weight:800; }}
.row {{ display:grid; grid-template-columns:32px 120px 48px 1fr; gap:8px; align-items:start; padding:6px 0; border-top:1px solid #ead8bd; font-size:14px; }}
.row:first-child {{ border-top:0; }}
.idx {{ font-weight:800; color:#8a8a8a; }}
.name {{ font-weight:700; }}
.level {{ color:#8a8a8a; }}
.next {{ color:#8a8a8a; }}
.effect {{ color:#8a8a8a; font-size:13px; margin-top:2px; }}
.row.can-build .idx, .row.can-build .name, .row.can-build .level, .row.can-build .next, .row.can-build .effect {{ color:#2e7d32; }}
.hint {{ text-align:center; font-size:15px; margin-top:8px; font-weight:700; }}
</style></head><body>
<div class='title'>猫猫乐园建设</div>
<div class='scene' style='width:{scene_width}px; height:{scene_height}px;'>
  {f"<img class='scene-bg' src='{scene_src}' />" if scene_src else ""}
  {facilities_html}
</div>
<div class='panel'>
{f"<div class='msg'>{message}</div>" if message else ""}
<div class='materials'>{material_html}</div>
{"".join(f"<div class='row {r['status_cls']}'><div class='idx'>{r['idx']}</div><div class='name'>{r['name']}</div><div class='level'>Lv{r['level']}</div><div><div class='next'>{r['next']}</div><div class='effect'>下级效果：{r['effect']}</div></div></div>" for r in rows)}
<div class='hint'>发送「建设猫猫乐园 编号/建筑名」升级建筑<br>支持多个编号连续或空格分隔，如「建设猫猫乐园 4567」或「建设猫猫乐园 4 5 6 7」<br>建筑效果仅在猫猫乐园内有效</div>
</div></body></html>
"""
    return await render_html(html, 720)


async def sell_completed_cat_park_materials(user_id: str, messages: list[str]) -> None:
    state = await get_cat_park_state(user_id)
    if not all(level >= 3 for level in state["buildings"].values()):
        return
    materials = await get_cat_park_materials(user_id)
    total_count = sum(materials.values())
    if total_count <= 0:
        return
    for name, count in materials.items():
        if count > 0:
            await FishingUser.remove_item(user_id, name, CAT_PARK_MATERIAL_TYPE, count)
    gold = total_count * CAT_PARK_MATERIAL_PRICE
    await FishingUser.add_gold(user_id, gold)
    messages.append(
        f"猫猫乐园已竣工，多余材料自动出售：{total_count}个 × {CAT_PARK_MATERIAL_PRICE} = {gold}金币"
    )


def get_cat_park_effect_values(state: dict[str, Any]) -> dict[str, float]:
    buildings = state.get("buildings", {})
    hut = int(buildings.get("猫猫小木屋", 0))
    pond = int(buildings.get("喵喵鱼塘", 0))
    plaza = int(buildings.get("猫爬架广场", 0))
    cafe = int(buildings.get("喵咖咖啡馆", 0))
    wand = int(buildings.get("旋转逗猫棒", 0))
    coaster = int(buildings.get("猫猫过山车", 0))
    castle = int(buildings.get("水晶猫城堡", 0))
    return {
        "bait_save": [0, 0.03, 0.06, 0.10][hut],
        "cat_park_speed_multiplier": [1.0, 1.03, 1.06, 1.10][pond],
        "material_rate": [CAT_PARK_MATERIAL_RATE, 0.35, 0.40, 0.45][plaza],
        "price_bonus": [0, 0.03, 0.06, 0.10][cafe],
        "double_rate": [0, 0.03, 0.06, 0.10][wand],
        "weather_bonus": [0, 0.03, 0.06, 0.10][coaster],
        "castle_rod_rate": [0, 0.05, 0.15, 0.30][castle],
    }


async def get_user_cat_park_effect_values(user_id: str) -> dict[str, float]:
    return get_cat_park_effect_values(await get_cat_park_state(user_id))


def cat_park_fish_price(fish: FishData, rarity: str, price_bonus: float = 0) -> int:
    return int(
        calculate_fish_price(fish, rarity, CAT_PARK_DIFFICULTY)
        * CAT_PARK_FISH_PRICE_RATE
        * (1 + price_bonus)
    )


# 猫咪摩天轮每日签到奖池：(item_id, item_type, display_name, weight)
# 玉米 50%，其余 4 项各 12.5%
CAT_PARK_FERRIS_WHEEL_REWARDS = [
    ("真多多药水", "potion", "真多多药水", 12.5),
    ("time_potion", "potion", "时光药水", 12.5),
    ("幸运药水", "potion", "幸运药水", 12.5),
    ("cat_frame", None, "猫猫框", 12.5),
    ("corn", None, "玉米", 50.0),
]


async def claim_ferris_wheel_rewards(
    user_id: str, days_missed: int = 0
) -> list[str]:
    """领取猫咪摩天轮每日签到奖励。

    抽数 = 摩天轮建筑等级（0~3）× 累计天数（days_missed + 1），每日签到时调用。
    与展示收益一致，未登录的天数累计合并到下次签到一并结算。
    奖池加权随机：玉米 50% / 真多多药水 / 时光药水 / 幸运药水 / 猫猫框 各 12.5%。
    返回奖励消息列表（未建摩天轮或非新签到日返回空列表）。
    """
    state = await get_cat_park_state(user_id)
    ferris_level = int(state.get("buildings", {}).get("猫咪摩天轮", 0))
    if ferris_level <= 0:
        return []

    multiplier = days_missed + 1
    total_draws = ferris_level * multiplier
    weights = [r[3] for r in CAT_PARK_FERRIS_WHEEL_REWARDS]
    reward_counts: dict[str, int] = {}
    for _ in range(total_draws):
        reward_key, item_type, display_name, _w = random.choices(
            CAT_PARK_FERRIS_WHEEL_REWARDS, weights=weights, k=1
        )[0]
        if item_type == "potion":
            await FishingUser.add_item(user_id, reward_key, "potion", 1)
        elif reward_key == "cat_frame":
            await FishingUser.add_cat_frames(user_id, 1)
        elif reward_key == "corn":
            await FishingUser.add_corn(user_id, 1)
        reward_counts[display_name] = reward_counts.get(display_name, 0) + 1

    summary = "、".join(f"{name} ×{cnt}" for name, cnt in reward_counts.items())
    suffix = f"（累计{days_missed}天未收杆）" if days_missed > 0 else ""
    messages = [f"🎡 摩天轮签到{suffix}：获得 {summary}"]

    logger.info(
        f"用户 {user_id} 摩天轮签到 Lv{ferris_level} ×{multiplier}天，"
        f"共{total_draws}抽，获得{summary}"
    )
    return messages
