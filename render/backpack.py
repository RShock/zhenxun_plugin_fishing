from pathlib import Path

from ..config import ConfigManager, calculate_fish_price
from .base import (
    RARITY_COLORS,
    RARITY_NAMES,
    _get_utr_starry_src,
    build_fish_item_data,
    build_starry_fish_cards,
    get_fish_image_src,
    gradient_bg,
    render_html,
    render_template,
)

_RESOURCES_DIR = Path(__file__).resolve().parent.parent / "resources"
_ITEMS_DIR = _RESOURCES_DIR / "images" / "items"


def _get_frame_src(tier: str) -> str:
    """tier: starry | cat | normal"""
    if tier in ("starry", "cat"):
        frame_path = _ITEMS_DIR / "猫猫框.png"
    else:
        frame_path = _ITEMS_DIR / "展示木框.png"
    if frame_path.exists():
        return str(frame_path)
    return ""


def _display_frame_tier(index: int, starry_frames: int, upgraded_display_count: int) -> str:
    if index < starry_frames:
        return "starry"
    if index < upgraded_display_count:
        return "cat"
    return "normal"


async def render_backpack(
    user_id: str,
    fish_list: list,
    total_value: int,
    displays: list = None,
    display_slots: int = 3,
    gold: int = 0,
    bait_list: list = None,
    corn_count: int = 0,
    display_frames: int = 0,
    upgraded_display_count: int = 0,
    cat_frames: int = 0,
    potion_list: list = None,
    meteor_items: list = None,
    cat_park_materials: list = None,
    star_frames: int = 0,
    starry_frames: int = 0,
) -> bytes:
    display_data = []
    if displays:
        sorted_displays = sorted(
            displays, key=lambda d: d.get("price", 0), reverse=True
        )
        for i, d in enumerate(sorted_displays):
            color = RARITY_COLORS.get(d["rarity"], "#808080")
            img_src = get_fish_image_src(d["fish_name"])
            frame_tier = _display_frame_tier(i, starry_frames, upgraded_display_count)
            is_upgraded = frame_tier in ("starry", "cat")
            frame_src = _get_frame_src(frame_tier)
            is_utr = d["rarity"] == "UTR"
            utr_starry_src = _get_utr_starry_src() if is_utr else ""
            display_data.append(
                {
                    "slot": d["slot"],
                    "color": color,
                    "img_src": img_src,
                    "fish_name": d["fish_name"],
                    "price": d.get("price", 0),
                    "daily_income": d.get("daily_income", 0),
                    "frame_src": frame_src,
                    "is_upgraded": is_upgraded,
                    "frame_tier": frame_tier,
                    "is_utr": is_utr,
                    "utr_starry_src": utr_starry_src,
                }
            )

    rarity_order = {"UTR": 0, "UR": 1, "SSR": 2, "SR": 3, "R": 4, "N": 5}
    sorted_fish = sorted(
        fish_list,
        key=lambda x: (
            rarity_order.get(x.get("rarity", "N"), 5),
            ConfigManager.get_fish_order(x.get("fish_name", "")),
        ),
    )

    fish_rows = []
    for fish in sorted_fish:
        fish_rows.append(
            build_fish_item_data(
                fish_name=fish["fish_name"],
                rarity=fish["rarity"],
                count=fish["count"],
                fish_base_price=fish.get("price", 0),
                numeric_id=fish["numeric_id"],
                locked=fish.get("locked", False),
            )
        )

    html = render_template(
        "backpack.html",
        body_bg=gradient_bg("pink"),
        width=550,
        gold=gold,
        displays=display_data,
        display_slots=display_slots,
        bait_list=bait_list or [],
        corn_count=corn_count,
        display_frames=display_frames,
        cat_frames=cat_frames,
        star_frames=star_frames,
        starry_frames=starry_frames,
        fish_rows=fish_rows,
        total_value=total_value,
        potion_list=potion_list or [],
        meteor_items=meteor_items or [],
        cat_park_materials=cat_park_materials or [],
    )
    return await render_html(html, 550)


async def render_display(
    user_id: str,
    displays,
    daily_income: int,
    upgraded_display_count: int = 0,
    starry_frames: int = 0,
) -> bytes:
    def _display_sort_key(d):
        price = d.get("price", 0)
        if not price:
            fish_data = ConfigManager.get_fish_by_name(d["fish_name"])
            if fish_data:
                price = calculate_fish_price(fish_data, d["rarity"], 0) * 2
        return price

    display_data = []
    sorted_displays = sorted(displays, key=_display_sort_key, reverse=True)
    for i, d in enumerate(sorted_displays):
        color = RARITY_COLORS.get(d["rarity"], "#808080")
        img_src = get_fish_image_src(d["fish_name"])
        frame_tier = _display_frame_tier(i, starry_frames, upgraded_display_count)
        is_upgraded = frame_tier in ("starry", "cat")
        frame_src = _get_frame_src(frame_tier)
        is_utr = d["rarity"] == "UTR"
        utr_starry_src = _get_utr_starry_src() if is_utr else ""
        display_data.append(
            {
                "slot": d["slot"],
                "color": color,
                "img_src": img_src,
                "rarity_name": RARITY_NAMES.get(d["rarity"], d["rarity"]),
                "fish_name": d["fish_name"],
                "frame_src": frame_src,
                "is_upgraded": is_upgraded,
                "frame_tier": frame_tier,
                "is_utr": is_utr,
                "utr_starry_src": utr_starry_src,
            }
        )

    html = render_template(
        "display.html",
        body_bg="linear-gradient(135deg, #a1c4fd 0%, #c2e9fb 100%)",
        width=400,
        displays=display_data,
        daily_income=daily_income,
    )
    return await render_html(html, 400)


async def render_starry_exhibition(user_id: str, user) -> bytes:
    raw_exhibition = list(user.starry_exhibition or [])
    raw_backpack = list(user.starry_fish or [])
    derived_from_backpack = False
    if not raw_exhibition:
        from ..core.starry_system import EXHIBITION_LIMIT, EXHIBITION_MIN_SCORE

        candidates = [
            item
            for item in raw_backpack
            if int(item.get("display_score", 0)) >= EXHIBITION_MIN_SCORE
        ]
        candidates.sort(
            key=lambda item: (float(item.get("score", 0)), int(item.get("id", 0))),
            reverse=True,
        )
        raw_exhibition = candidates[:EXHIBITION_LIMIT]
        derived_from_backpack = bool(raw_exhibition)
    cards = build_starry_fish_cards(raw_exhibition)
    total_count = len(raw_backpack)
    if not derived_from_backpack:
        total_count += len(raw_exhibition)
    html = render_template(
        "starry_exhibition.html",
        body_bg=(
            "linear-gradient(135deg, #172033 0%, #314f6f 55%, #7a6e96 100%)"
        ),
        width=560,
        cards=cards,
        total_score=round(float(user.starry_score_accumulated or 0), 3),
        total_count=total_count,
        exhibition_count=len(cards),
    )
    return await render_html(html, 560)
