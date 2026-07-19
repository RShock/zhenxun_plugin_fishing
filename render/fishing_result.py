import time
from datetime import datetime

from ..config import ConfigManager
from .base import (
    build_fish_item_data,
    build_fish_list_data,
    build_meteor_fish_items,
    build_starry_fish_cards,
    gradient_bg,
    render_html,
    render_template,
    save_debug_output,
)
from .fishing_status import _build_buff_timeline


async def render_fishing_start(
    user_id: str,
    location,
    start_time: datetime,
    hints: list[str] | None = None,
) -> bytes:
    html = render_template(
        "fishing_start.html",
        body_bg=gradient_bg("purple"),
        width=400,
        location=location,
        start_time=start_time.strftime("%Y-%m-%d %H:%M:%S"),
        hints=hints or [],
    )
    return await render_html(html, 400)


def _build_cat_gifts_data(cat_gifts: dict) -> dict:
    from ..core.cat_gift import extract_fish_gifts

    result = {
        "gold": cat_gifts.get("gold", 0),
        "corn": cat_gifts.get("corn", 0),
        "bait_count": cat_gifts.get("bait_count", 0),
        "cat_frames": cat_gifts.get("cat_frames", 0),
        "fish_gifts": [],
    }
    bait_id = cat_gifts.get("bait_id", "")
    if bait_id:
        bait_data = ConfigManager.get_bait(bait_id)
        if bait_data:
            result["bait_name"] = bait_data.name
        else:
            result["bait_name"] = bait_id
    else:
        result["bait_name"] = ""

    fish_gift_list = []
    for gift in extract_fish_gifts(cat_gifts):
        fish_name = gift.get("fish_name", "")
        fish_rarity = gift.get("fish_rarity", "")
        if fish_name:
            fish_data = ConfigManager.get_fish(fish_name)
            if fish_data:
                fish_gift_list.append(
                    {"fish_name": fish_data.id, "fish_rarity": fish_rarity}
                )
    result["fish_gifts"] = fish_gift_list

    has_gifts = (
        result["gold"] > 0
        or result["corn"] > 0
        or result["bait_count"] > 0
        or result["cat_frames"] > 0
        or len(result["fish_gifts"]) > 0
    )
    result["has_gifts"] = has_gifts
    return result


def _build_cat_park_material_items(
    materials: list[tuple] | None,
) -> list[dict]:
    """构建猫猫乐园建设素材的图片卡片数据。

    materials: [(material_name, rarity, count), ...]
    """
    if not materials:
        return []
    # 固定顺序：毛线团 / 特级小鱼干 / 彩虹逗猫棒
    order = {"毛线团": 0, "特级小鱼干": 1, "彩虹逗猫棒": 2}
    sorted_mats = sorted(
        materials, key=lambda x: order.get(x[0], 99)
    )
    items = []
    for name, rarity, count in sorted_mats:
        items.append(
            build_fish_item_data(
                fish_name=name,
                rarity=rarity,
                count=count,
                show_count=True,
                fish_base_price=None,
            )
        )
    return items


async def render_fishing_result(
    user_id: str,
    location,
    duration_minutes: float,
    fish_caught: list[tuple],
    total_gold: int,
    achievement_messages: list[str] = None,
    sign_info: dict | None = None,
    hints: list[str] | None = None,
    cat_eaten_fish: list[tuple] | None = None,
    cat_gifts: dict | None = None,
    buffs: list | None = None,
    fishing_start_time: datetime | None = None,
    now_time: datetime | None = None,
    meteor_fish_numbers: list[int] | None = None,
    cat_park_materials: list[tuple] | None = None,
    starry_score: dict | None = None,
    miracle: dict | None = None,
    starry_rewards: list | None = None,
    bait=None,
    bait_remaining: int | None = None,
) -> bytes:
    t0 = time.perf_counter()
    fish_items = build_fish_list_data(
        fish_caught, location.id, cat_eaten_fish=cat_eaten_fish
    )
    duration_text = (
        f"{duration_minutes / 60:.1f}小时"
        if duration_minutes >= 60
        else f"{duration_minutes:.1f}分钟"
    )
    total_count = sum(c for _, _, c in fish_caught)
    total_count += len(meteor_fish_numbers or [])
    if cat_eaten_fish:
        total_count += sum(c for _, _, c in cat_eaten_fish)

    cat_gifts_data = None
    if cat_gifts:
        cat_gifts_data = _build_cat_gifts_data(cat_gifts)

    timeline_data = None
    if buffs and fishing_start_time:
        effective_now = now_time if now_time else datetime.now()
        # 收杆页面：显示开钓到收杆的时间区间
        timeline_data = _build_buff_timeline(
            buffs, fishing_start_time, effective_now, end_time=effective_now
        )

    fish_items.extend(build_meteor_fish_items(meteor_fish_numbers))
    starry_records = []
    legacy_meteor_numbers = []
    for num in meteor_fish_numbers or []:
        if int(num) <= 999_999:
            starry_records.append({"id": str(num).zfill(6)})
        else:
            legacy_meteor_numbers.append(num)
    starry_cards = build_starry_fish_cards(starry_records)
    # 将本杆抽奖结果挂到对应流星鱼卡片上，避免只显示奖池名
    rewards_by_fish: dict[str, list[dict]] = {}
    for reward in starry_rewards or []:
        if reward.get("granted") is False:
            continue
        fid = str(reward.get("fish_id") or "").zfill(6)
        if fid and fid != "000000":
            rewards_by_fish.setdefault(fid, []).append(reward)
    for card in starry_cards:
        matched = rewards_by_fish.get(str(card.get("id", "")).zfill(6), [])
        card["rewards"] = matched
        if matched:
            parts = []
            for r in matched:
                name = r.get("name", "?")
                if r.get("key") == "wish_score" or r.get("score_bonus"):
                    bonus = r.get("score_bonus") or 0.5
                    text = f"+{bonus:g}积分"
                else:
                    text = f"{name}×{r.get('count', 1)}"
                if r.get("upgrade_from"):
                    text += "(碎片升级)"
                parts.append(text)
            card["reward_text"] = "、".join(parts)
        else:
            card["reward_text"] = ""
    if starry_cards:
        fish_items = build_fish_list_data(
            fish_caught, location.id, cat_eaten_fish=cat_eaten_fish
        )
        fish_items.extend(build_meteor_fish_items(legacy_meteor_numbers))

    material_items = _build_cat_park_material_items(cat_park_materials)

    html = render_template(
        "fishing_result.html",
        body_bg=gradient_bg("green"),
        width=450,
        location_name=location.name,
        duration_text=duration_text,
        total_count=total_count,
        fish_items=fish_items,
        total_gold=total_gold,
        achievement_messages=achievement_messages or [],
        sign_info=sign_info,
        hints=hints or [],
        cat_gifts_data=cat_gifts_data,
        timeline_data=timeline_data,
        material_items=material_items,
        starry_cards=starry_cards,
        starry_score=starry_score,
        miracle=miracle,
        starry_rewards=starry_rewards or [],
        bait=bait,
        bait_remaining=bait_remaining,
    )
    result = await render_html(html, 450)
    t1 = time.perf_counter()
    save_debug_output(
        "fishing_result",
        user_id,
        html,
        result,
        {
            "template": t1 - t0,
            "render": t1 - t0,
        },
    )
    return result
