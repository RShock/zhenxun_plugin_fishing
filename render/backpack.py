from pathlib import Path

from ..characters import normalize_characters
from ..config import ConfigManager, calculate_fish_price
from .base import (
    RARITY_COLORS,
    RARITY_NAMES,
    _get_utr_starry_src,
    _starry_feature_digit_styles,
    build_fish_item_data,
    build_starry_fish_cards,
    get_character_image_src,
    get_fish_image_src,
    gradient_bg,
    render_html,
    render_template,
)

_RESOURCES_DIR = Path(__file__).resolve().parent.parent / "resources"
_ITEMS_DIR = _RESOURCES_DIR / "images" / "items"


def _get_frame_src(tier: str) -> str:
    """tier: starry | cat | normal

    starry 框使用专属星空框素材；cat 与 normal 各自对应独立素材。
    （早期星空框缺素材时曾复用猫框.png + CSS hue-rotate 变色作为临时方案，
     现已替换为正式星空框.png。）
    """
    frame_map = {
        "starry": "星空框.png",
        "cat": "猫框.png",
        "normal": "木框.png",
    }
    frame_path = _ITEMS_DIR / frame_map.get(tier, "木框.png")
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
    character_item_list: list = None,
    characters: list[dict[str, str | int] | str] | None = None,
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
                white_market_exchangeable=fish.get("white_market_exchangeable", False),
            )
        )

    character_data = []
    for character in normalize_characters(characters or []):
        rarity = str(character.get("rarity", "N")).upper()
        character_data.append(
            {
                **character,
                "rarity": rarity,
                "color": RARITY_COLORS.get(rarity, RARITY_COLORS["N"]),
                "img_src": get_character_image_src(str(character["character_id"])),
            }
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
        character_item_list=character_item_list or [],
        characters=character_data,
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


async def render_starry_ranking(
    entries: list[tuple[str, str, list[dict]]],
    top_n: int = 20,
    *,
    scope: str = "全服",
) -> bytes:
    """渲染星空排行榜图片。

    entries: (user_id, nickname, exhibition_records) 列表，来自全表扫描或本群过滤。
    展馆记录保存的是入馆时分数快照，这里按当前规则重算以确保排行一致性。
    scope: 显示范围文案，用于榜单副标题（本群 / 全服）。
    """
    from ..core.starry_system import REWARD_POOL_NAMES, score_starry_fish

    flat: list[dict] = []
    for user_id, nickname, records in entries:
        for record in records:
            fish_id = str(record.get("id", "0")).zfill(6)
            scored = score_starry_fish(fish_id)
            digit_matched, digit_colors, digit_text_colors = (
                _starry_feature_digit_styles(
                    scored.features,
                    scored.id_text,
                    reward_pool=scored.reward_pool,
                    display_score=scored.display_score,
                )
            )
            flat.append(
                {
                    "player": nickname or user_id,
                    "id": scored.id_text,
                    "digits": list(scored.id_text),
                    "digit_colors": digit_colors,
                    "digit_text_colors": digit_text_colors,
                    "score": round(scored.raw_score, 3),
                    "display_score": scored.display_score,
                    "reward_pool": REWARD_POOL_NAMES.get(
                        scored.reward_pool, scored.reward_pool
                    ),
                    "features": [
                        f.display_name for f in scored.features
                    ],
                }
            )

    # 按分数降序、编号降序排序后取 top_n
    flat.sort(key=lambda item: (item["score"], int(item["id"])), reverse=True)
    flat = flat[:top_n]

    for index, item in enumerate(flat):
        item["rank"] = index + 1

    html = render_template(
        "starry_ranking.html",
        body_bg=(
            "linear-gradient(135deg, #172033 0%, #314f6f 55%, #7a6e96 100%)"
        ),
        width=560,
        entries=flat,
        top_n=top_n,
        scope=scope,
    )
    return await render_html(html, 560)
