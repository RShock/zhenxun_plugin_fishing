"""
收杆事务内的内存结算编排。

所有变更作用于同一 FishingUser 实例 + dirty 集合，
调用方在事务末尾执行一次 save_dirty。
"""

from __future__ import annotations

from datetime import datetime, timedelta

from zhenxun.services.log import logger

from ..config import (
    DISPLAY_SLOT_COSTS,
    ConfigManager,
    FishData,
    LocationData,
    calculate_fish_price,
    generate_fish_numeric_id,
)
from ..models import FishingBuffCalculator
from ..models import user_mutations as mut
from .cat_gift import extract_fish_gifts
from .context import merge_fish


def apply_daily_rewards_on_user(
    user,
    is_new_sign: bool,
    display_income: int,
    days_missed: int,
    dirty: set[str],
) -> None:
    if not is_new_sign:
        return
    is_new, _corn, _missed = mut.apply_check_and_sign(user, dirty)
    if not is_new:
        return
    if display_income > 0:
        mut.apply_add_gold(user, display_income * (days_missed + 1), dirty)


def apply_distribute_cat_gifts_on_user(
    user,
    location_id: str,
    fish_pool: list,
    cat_gifts: dict | None,
    dirty: set[str],
) -> list[str]:
    if not cat_gifts:
        return []

    messages: list[str] = []
    if cat_gifts.get("gold", 0) > 0:
        mut.apply_add_gold(user, cat_gifts["gold"], dirty)
        messages.append(f"🐱 猫送了{cat_gifts['gold']}金币")
    if cat_gifts.get("cat_frames", 0) > 0:
        mut.apply_add_cat_frames(user, cat_gifts["cat_frames"], dirty)
        messages.append(f"🐱 猫送了{cat_gifts['cat_frames']}个猫框")
    if cat_gifts.get("corn", 0) > 0:
        mut.apply_add_corn(user, cat_gifts["corn"], dirty)
        messages.append(f"🐱 猫送了{cat_gifts['corn']}个玉米")
    if cat_gifts.get("bait_count", 0) > 0 and cat_gifts.get("bait_id", ""):
        mut.apply_add_item(
            user, cat_gifts["bait_id"], "bait", cat_gifts["bait_count"], dirty
        )
        messages.append(f"🐱 猫送了{cat_gifts['bait_count']}个鱼饵")

    for gift in extract_fish_gifts(cat_gifts):
        gift_fish_name = gift.get("fish_name", "")
        gift_fish_rarity = gift.get("fish_rarity", "")
        if not gift_fish_name or not gift_fish_rarity:
            continue
        gift_fish = ConfigManager.get_fish(gift_fish_name)
        if not gift_fish:
            continue
        fish_index = 0
        if gift_fish.id in fish_pool:
            fish_index = fish_pool.index(gift_fish.id)
            if location_id.upper() != "S1":
                fish_index += 1
        numeric_id = generate_fish_numeric_id(
            location_id, fish_index, gift_fish_rarity
        )
        cat_result = apply_add_fish_entries_on_user(
            user,
            [(gift_fish.id, gift_fish_rarity, numeric_id, 1)],
            dirty,
            check_achievements=False,
            auto_display=False,
            effective_difficulty=0,
        )
        messages.extend(cat_result["messages"])
    return messages


def _calc_entry_price(
    user,
    fish_data: FishData,
    rarity: str,
    effective_difficulty: int,
) -> int:
    from ..cat_park import CAT_PARK_FISH, cat_park_fish_price, get_cat_park_effect_values

    if fish_data.id in CAT_PARK_FISH:
        # 从 user.items 读猫乐园状态，避免再查库
        from ..cat_park import (
            CAT_PARK_STATE_ITEM_ID,
            CAT_PARK_STATE_ITEM_TYPE,
            _default_state,
        )
        import json

        item = mut.get_item_on_user(user, CAT_PARK_STATE_ITEM_ID, CAT_PARK_STATE_ITEM_TYPE)
        state = _default_state()
        if item:
            # get_item_on_user 只返回 count；状态在 items 的 data 字段
            items = user.items or {}
            entry = items.get(f"{CAT_PARK_STATE_ITEM_ID}|{CAT_PARK_STATE_ITEM_TYPE}", {})
            raw = entry.get("data") if isinstance(entry, dict) else None
            if isinstance(raw, str):
                try:
                    state = json.loads(raw)
                except json.JSONDecodeError:
                    pass
            elif isinstance(raw, dict):
                state = raw
        effects = get_cat_park_effect_values(state)
        return cat_park_fish_price(fish_data, rarity, effects.get("price_bonus", 0))
    return calculate_fish_price(fish_data, rarity, effective_difficulty)


def apply_auto_display_on_user(
    user,
    fish_name: str,
    rarity: str,
    numeric_id: str,
    dirty: set[str],
) -> str | None:
    if fish_name == "展示木框":
        return None
    fish_data = ConfigManager.get_fish_by_name(fish_name)
    if not fish_data:
        return None

    new_value = calculate_fish_price(fish_data, rarity, 0) * 2
    displays = mut.get_user_displays_on_user(user)
    displayed_keys = {(d["fish_name"], d["rarity"]) for d in displays}
    if (fish_name, rarity) in displayed_keys:
        return None

    used_slots = {d["slot"] for d in displays}
    for slot in range(1, int(user.display_slots or 0) + 1):
        if slot not in used_slots:
            if mut.apply_remove_fish_by_numeric_id(user, numeric_id, 1, dirty):
                mut.apply_set_display(user, slot, fish_name, rarity, numeric_id, dirty)
                return f"{fish_name}({rarity})被放在了栏位{slot}（每天获得展示收益）"
            return None

    min_value = float("inf")
    min_slot = None
    for d in displays:
        d_fish_data = ConfigManager.get_fish_by_name(d["fish_name"])
        d_value = (
            calculate_fish_price(d_fish_data, d["rarity"], 0) * 2 if d_fish_data else 0
        )
        if d_value < min_value:
            min_value = d_value
            min_slot = d["slot"]

    if min_slot is not None and new_value > min_value:
        if mut.apply_remove_fish_by_numeric_id(user, numeric_id, 1, dirty):
            mut.apply_set_display(user, min_slot, fish_name, rarity, numeric_id, dirty)
            return f"{fish_name}({rarity})替换了栏位{min_slot}（每天获得展示收益）"
    return None


def _check_achievement_on_user(
    user,
    achievement_key: str,
    required_pairs: list[tuple[str, str]],
    description: str,
    collected_set: set,
    difficulty: int,
    dirty: set[str],
    extra_message: str = "",
    bonus_multiplier: float = 1.0,
) -> dict:
    result = {"coins": 0, "messages": []}
    if mut.is_achievement_completed_on_user(user, achievement_key):
        return result

    total_price = 0
    for fish_id, rarity in required_pairs:
        if (fish_id, rarity) not in collected_set:
            return result
        fish = ConfigManager.get_fish(fish_id)
        if fish:
            total_price += calculate_fish_price(fish, rarity, difficulty)

    if not mut.apply_mark_achievement(user, achievement_key, dirty):
        return result
    bonus = int(total_price * bonus_multiplier)
    result["coins"] = bonus
    msg = f"完成 {description}，获得 {bonus} 钓鱼币"
    if extra_message:
        msg += f"\n{extra_message}"
    result["messages"].append(msg)
    logger.info(f"用户 {user.user_id} 完成 {description}，获得 {bonus} 钓鱼币")
    return result


def apply_check_all_achievements_on_user(user, dirty: set[str]) -> dict:
    from ..services.achievement_service import RARITIES_FULL, RARITIES_UP_TO_UR

    result = {"coins": 0, "messages": []}
    collected_set = mut.get_collected_set_on_user(user, dirty)
    all_locations = ConfigManager.get_locations()

    for location in all_locations:
        fish_pool = location.fish_pool
        all_fish_in_pool = []
        for fish_id in fish_pool:
            fish = ConfigManager.get_fish(fish_id)
            if fish:
                all_fish_in_pool.append(fish)
        if not all_fish_in_pool:
            continue

        checks: list[tuple[str, list[tuple[str, str]], str, str, float]] = []
        for rarity in RARITIES_UP_TO_UR:
            key = f"collect_rarity_{location.id}_{rarity}"
            pairs = [(fish.id, rarity) for fish in all_fish_in_pool]
            desc = f"{location.name} 收集全部{rarity}级鱼"
            checks.append((key, pairs, desc, "", 3.0))

        key = f"collect_rarity_{location.id}_UTR"
        pairs = [(fish.id, "UTR") for fish in all_fish_in_pool]
        checks.append((key, pairs, f"{location.name} 收集全部UTR级鱼", "", 3.0))

        for fish in all_fish_in_pool:
            key = f"collect_fish_{location.id}_{fish.id}"
            pairs = [(fish.id, rarity) for rarity in RARITIES_UP_TO_UR]
            checks.append((key, pairs, f"{fish.id} 全稀有度收集", "", 3.0))

        key = f"collect_scene_{location.id}"
        pairs = [
            (fish.id, rarity)
            for fish in all_fish_in_pool
            for rarity in RARITIES_UP_TO_UR
        ]
        try:
            from ..starry import is_starry_location

            is_starry = is_starry_location(location.id)
        except Exception:
            is_starry = False
        extra_msg = (
            f"✨ {location.name}的UTR稀有度已对你解锁！\n解锁后递进概率与 150 次 UTR 保底常驻生效（星空图不生成迷途风）。"
            if is_starry
            else f"🌀 {location.name}的迷途风天气已对你解锁！"
        )
        checks.append((key, pairs, f"{location.name} 场景全收集", extra_msg, 1.0))

        for fish in all_fish_in_pool:
            key = f"collect_fish_utr_{location.id}_{fish.id}"
            pairs = [(fish.id, rarity) for rarity in RARITIES_FULL]
            checks.append((key, pairs, f"{fish.id} 真全稀有度收集", "", 3.0))

        key = f"collect_scene_utr_{location.id}"
        pairs = [
            (fish.id, rarity) for fish in all_fish_in_pool for rarity in RARITIES_FULL
        ]
        checks.append((key, pairs, f"{location.name} 场景真全收集", "", 1.0))

        for achievement_key, required_pairs, description, extra_message, mult in checks:
            r = _check_achievement_on_user(
                user,
                achievement_key,
                required_pairs,
                description,
                collected_set,
                location.difficulty,
                dirty,
                extra_message=extra_message,
                bonus_multiplier=mult,
            )
            result["coins"] += r["coins"]
            result["messages"].extend(r["messages"])

    return result


def apply_add_fish_entries_on_user(
    user,
    fish_entries: list[tuple[str, str, str, int]],
    dirty: set[str],
    *,
    effective_difficulty: int = 0,
    check_achievements: bool = True,
    auto_display: bool = True,
) -> dict:
    fish_coins = 0
    achievement_coins = 0
    messages: list[str] = []
    achievement_messages: list[str] = []
    displayable_fish: list[tuple[str, str, str]] = []
    auto_display_fish_entries: list[tuple[str, str, str]] = []
    utr_consumed: list[str] = []

    for fish_name, rarity, numeric_id, count in fish_entries:
        fish_data = ConfigManager.get_fish(fish_name)
        if not fish_data:
            continue

        if rarity == "UTR":
            utr_collected = mut.is_collected_on_user(user, fish_name, "UTR")
            if not utr_collected:
                mut.apply_mark_collected(user, fish_name, "UTR", 1, dirty)
                displayable_fish.append((fish_name, rarity, numeric_id))
                messages.append(f"🌈 {fish_name} UTR图鉴已解锁！（已自动消耗1条）")
                utr_consumed.append(fish_name)
                remaining = count - 1
                if remaining > 0:
                    mut.apply_add_fish(
                        user, fish_name, rarity, numeric_id, remaining, dirty
                    )
                    mut.apply_mark_collected(
                        user, fish_name, rarity, remaining, dirty
                    )
                    price = _calc_entry_price(
                        user, fish_data, rarity, effective_difficulty
                    )
                    fish_coins += price * remaining
                    messages.append(f"🎒 剩余{remaining}条{fish_name} UTR已放入背包")
                    auto_display_fish_entries.append((fish_name, rarity, numeric_id))
                continue
            mut.apply_add_fish(user, fish_name, rarity, numeric_id, count, dirty)
            mut.apply_mark_collected(user, fish_name, rarity, count, dirty)
            price = _calc_entry_price(user, fish_data, rarity, effective_difficulty)
            fish_coins += price * count
            displayable_fish.append((fish_name, rarity, numeric_id))
            auto_display_fish_entries.append((fish_name, rarity, numeric_id))
        else:
            mut.apply_add_fish(user, fish_name, rarity, numeric_id, count, dirty)
            mut.apply_mark_collected(user, fish_name, rarity, count, dirty)
            price = _calc_entry_price(user, fish_data, rarity, effective_difficulty)
            fish_coins += price * count
            displayable_fish.append((fish_name, rarity, numeric_id))
            auto_display_fish_entries.append((fish_name, rarity, numeric_id))

    if auto_display:
        for fish_name, rarity, numeric_id in auto_display_fish_entries:
            display_msg = apply_auto_display_on_user(
                user, fish_name, rarity, numeric_id, dirty
            )
            if display_msg:
                messages.append(f"🏆 自动展示: {display_msg}")

    if check_achievements and fish_entries:
        achievements = apply_check_all_achievements_on_user(user, dirty)
        if achievements["coins"] > 0:
            mut.apply_add_gold(user, achievements["coins"], dirty)
        achievement_coins = achievements["coins"]
        achievement_messages = achievements["messages"]

    return {
        "fish_coins": fish_coins,
        "achievement_coins": achievement_coins,
        "messages": messages,
        "achievement_messages": achievement_messages,
        "displayable_fish": displayable_fish,
        "utr_consumed": utr_consumed,
    }


def apply_starry_reward_on_user(user, reward: dict, dirty: set[str], *, source: str) -> dict:
    from .starry_rewards import _REWARD_HANDLERS
    from .starry_system import REWARD_POOL_NAMES

    key = str(reward.get("key", ""))
    name = str(reward.get("name", key))
    count = int(reward.get("count", 1) or 1)
    pool = str(reward.get("pool", ""))
    handler = _REWARD_HANDLERS.get(key)
    if not handler:
        logger.warning(f"unknown starry reward key={key} user={user.user_id}")
        return {
            "key": key,
            "name": name,
            "count": count,
            "pool": pool,
            "pool_name": REWARD_POOL_NAMES.get(pool, pool),
            "source": source,
            "granted": False,
        }

    kind, item_id, item_type = handler
    score_bonus = 0.0
    if kind == "corn":
        mut.apply_add_corn(user, count, dirty)
    elif kind == "cat_frame":
        mut.apply_add_cat_frames(user, count, dirty)
    elif kind == "wish_score":
        score_bonus = float(reward.get("score_bonus", 0.5) or 0.5) * count
        user.starry_score_accumulated = (
            float(user.starry_score_accumulated or 0) + score_bonus
        )
        mut.mark_dirty(dirty, "starry_score_accumulated")
    elif kind == "item":
        mut.apply_add_item(user, str(item_id), str(item_type), count, dirty)
    else:
        logger.warning(f"unimplemented reward kind={kind} key={key}")

    result = {
        "key": key,
        "name": name,
        "count": count,
        "pool": pool,
        "pool_name": reward.get("pool_name") or REWARD_POOL_NAMES.get(pool, pool),
        "source": source,
        "granted": True,
        "fish_id": reward.get("fish_id"),
        "display_score": reward.get("display_score"),
        "upgrade_from": reward.get("upgrade_from"),
    }
    if score_bonus:
        result["score_bonus"] = score_bonus
    return result


def apply_fragment_upgrades_on_user(
    user,
    dirty: set[str],
    *,
    fish_id: str | int | None = None,
    display_score: int | float | None = None,
) -> list[dict]:
    """碎片够 5 个时在本杆立刻结算，可连锁到更高等级。"""
    from .starry_rewards import _FRAGMENT_SPECS
    from .starry_system import draw_starry_reward

    granted: list[dict] = []
    for _ in range(40):
        upgraded = False
        for frag_key, spec in _FRAGMENT_SPECS.items():
            item = mut.get_item_on_user(user, spec["item_id"], spec["item_type"])
            count = int(item["count"]) if item else 0
            need = int(spec["upgrade_need"])
            if count < need:
                continue
            times = count // need
            for _i in range(times):
                ok = mut.apply_remove_item(
                    user, spec["item_id"], spec["item_type"], need, dirty
                )
                if not ok:
                    break
                drawn = draw_starry_reward(spec["upgrade_pool"])
                if not drawn:
                    break
                drawn["upgrade_from"] = spec["name"]
                if fish_id is not None:
                    fid = str(fish_id)
                    drawn["fish_id"] = fid.zfill(6) if fid.isdigit() else fid
                if display_score is not None:
                    drawn["display_score"] = int(display_score)
                entry = apply_starry_reward_on_user(
                    user, drawn, dirty, source=f"fragment_upgrade:{frag_key}"
                )
                granted.append(entry)
                upgraded = True
        if not upgraded:
            break
    return granted


def apply_grant_rewards_for_starry_fish_on_user(
    user, fish_id: int | str, dirty: set[str]
) -> list[dict]:
    from .starry_system import draw_starry_reward, get_reward_pool, score_starry_fish

    scored = score_starry_fish(fish_id)
    pool = scored.reward_pool or get_reward_pool(scored.display_score)
    if not pool or pool == "none":
        return []
    drawn = draw_starry_reward(pool)
    if not drawn:
        return []
    drawn["fish_id"] = scored.id_text
    drawn["display_score"] = scored.display_score
    results = [apply_starry_reward_on_user(user, drawn, dirty, source="catch")]
    # 本杆立刻检查碎片合成（含刚抽到的碎片）
    results.extend(
        apply_fragment_upgrades_on_user(
            user,
            dirty,
            fish_id=scored.id_text,
            display_score=scored.display_score,
        )
    )
    return results


def apply_ferris_wheel_rewards_on_user(
    user, days_missed: int, dirty: set[str]
) -> list[str]:
    import json
    import random

    from ..cat_park import (
        CAT_PARK_FERRIS_WHEEL_REWARDS,
        CAT_PARK_STATE_ITEM_ID,
        CAT_PARK_STATE_ITEM_TYPE,
        _default_state,
    )

    items = user.items or {}
    entry = items.get(f"{CAT_PARK_STATE_ITEM_ID}|{CAT_PARK_STATE_ITEM_TYPE}", {})
    raw = entry.get("data") if isinstance(entry, dict) else None
    state = _default_state()
    if isinstance(raw, str):
        try:
            state = json.loads(raw)
        except json.JSONDecodeError:
            pass
    elif isinstance(raw, dict):
        state = raw

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
            mut.apply_add_item(user, reward_key, "potion", 1, dirty)
        elif reward_key == "cat_frame":
            mut.apply_add_cat_frames(user, 1, dirty)
        elif reward_key == "corn":
            mut.apply_add_corn(user, 1, dirty)
        reward_counts[display_name] = reward_counts.get(display_name, 0) + 1

    summary = "、".join(f"{name} ×{cnt}" for name, cnt in reward_counts.items())
    suffix = f"（累计{days_missed}天未收杆）" if days_missed > 0 else ""
    return [f"🎡 摩天轮签到{suffix}：获得 {summary}"]


def apply_process_fish_results_on_user(
    user,
    location: LocationData,
    fish_caught: list[tuple[FishData, str, int]],
    buffs: list,
    bait_speed_bonus: int,
    now,
    frame_pity: int,
    utr_pity: int,
    buff_messages: list[str],
    dirty: set[str],
) -> tuple[int, list[str], list[tuple[FishData, str, int]], list[tuple[str, str, int]]]:
    from ..cat_park import CAT_PARK_MATERIAL_TYPE

    merged = merge_fish(fish_caught, as_dict=True)
    final_effects = FishingBuffCalculator.get_effects_at_time(
        buffs, now, user.rod_level, bait_speed_bonus, location.difficulty
    )
    effective_difficulty = final_effects["difficulty"]

    frame_count = 0
    fish_entries: list[tuple[str, str, str, int]] = []
    cat_park_materials: dict[str, int] = {}

    for fish, rarity, count in merged.values():
        if fish.id.startswith(f"{CAT_PARK_MATERIAL_TYPE}:"):
            material_name = fish.id.split(":", 1)[1]
            cat_park_materials[material_name] = (
                cat_park_materials.get(material_name, 0) + count
            )
            continue
        if fish.id == "展示木框":
            frame_count += count
            continue
        fish_index = 0
        if fish.id in location.fish_pool:
            fish_index = location.fish_pool.index(fish.id)
            if location.id.upper() != "S1":
                fish_index += 1
        numeric_id = generate_fish_numeric_id(location.id, fish_index, rarity)
        fish_entries.append((fish.id, rarity, numeric_id, count))

    result = apply_add_fish_entries_on_user(
        user,
        fish_entries,
        dirty,
        effective_difficulty=effective_difficulty,
        check_achievements=True,
        auto_display=True,
    )

    for material_name, count in cat_park_materials.items():
        mut.apply_add_item(user, material_name, CAT_PARK_MATERIAL_TYPE, count, dirty)

    if frame_count > 0:
        mut.apply_add_display_frames(user, frame_count, dirty)
        buff_messages.append(f"🖼️ 获得{frame_count}个展示木框！")

    buff_messages.extend(result["messages"])

    # 展示栏升级提示（只读）
    if user.display_slots < 10:
        next_slot = user.display_slots + 1
        frames_needed = DISPLAY_SLOT_COSTS.get(next_slot, next_slot - 3)
        if user.display_frames >= frames_needed:
            buff_messages.append("💡 展示木框充足，输入【增加展示栏位】可升级展示数量")

    user.frame_pity_counter = frame_pity
    user.utr_pity_counter = utr_pity
    mut.mark_dirty(dirty, "frame_pity_counter", "utr_pity_counter")

    visible_fish: list[tuple[FishData, str, int]] = []
    materials: list[tuple[str, str, int]] = []
    for fish, rarity, count in merged.values():
        if fish.id.startswith(f"{CAT_PARK_MATERIAL_TYPE}:"):
            material_name = fish.id.split(":", 1)[1]
            materials.append((material_name, rarity, count))
        else:
            visible_fish.append((fish, rarity, count))
    return (
        result["fish_coins"],
        result["achievement_messages"],
        visible_fish,
        materials,
    )
