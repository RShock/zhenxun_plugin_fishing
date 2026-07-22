"""钓鱼引擎 — 纯模拟循环、鱼种捕获、稀有度抽选。

技术约束：引擎只计算 ``SimulationResult``，不得写数据库或发送消息；持久化由
``core.actions`` 统一完成。模拟时的 ``catch_time`` 是 naive datetime，数据库读取的
Buff 时间可能带时区，比较前必须经 ``models.user._make_naive`` 归一化。布尔 Buff
必须按每次捕获时间判断有效区间，数值 Buff 则通过 ``get_effects_at_time`` 叠加。
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
import random
from typing import Any

from zhenxun.services.log import logger

from ..config import ConfigManager, FishData, LocationData
from ..constants import (
    CAT_EAT_CHANCE,
    FRAME_PITY_THRESHOLD,
    UTR_PITY_THRESHOLD,
    apply_meteor_effect,
    get_lost_wind_utr_probability,
    get_rarity_probabilities_full,
)
from ..models import BuffEffect, FishingBuffCalculator, FishingUser, _make_naive
from .cat import process_cat_gift
from .context import FishingContext, SimulationResult, deserialize_fish_caught
from .starry_system import expand_starry_fish_with_duoduo, roll_starry_fish

# ── 调试：幸运选择日志过滤 ──
# 设为 None 则输出所有人的日志
_DEBUG_LUCKY_USER_ID = None
# 运行时由 simulate_fishing_loop 设置当前 user_id
_debug_current_user_id: str | None = None

# ═══════════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════════


def _apply_duoduo(rarity_index: int, duoduo_count: int) -> tuple[int, int]:
    """多多 buff 效果：降稀有度翻倍数量。"""
    actual_downgrade = min(duoduo_count, rarity_index)
    new_index = rarity_index - actual_downgrade
    quantity = 1 << actual_downgrade
    return new_index, quantity


def _compute_duoduo_quantity(duoduo_count: int, cat_park_double_rate: float) -> int:
    """计算多多药水 + 猫乐园旋转逗猫棒合并后的数量倍率。

    多多药水提供整数翻倍（1 << duoduo_count），猫乐园旋转逗猫棒提供小数概率翻倍。
    两者在结算层面合并为一个浮点倍率，小数部分用概率计算：
    - 整数部分为保底数量
    - 小数部分为额外 +1 的概率

    例：duoduo_count=0, double_rate=0.10 → 1.10 → 1条(90%) / 2条(10%)
        duoduo_count=1, double_rate=0.06 → 2.06 → 2条(94%) / 3条(6%)
    """
    base_mult = 1 << duoduo_count
    total_mult = base_mult + cat_park_double_rate
    floor_mult = int(total_mult)
    frac = total_mult - floor_mult
    if frac > 0 and random.random() < frac:
        return floor_mult + 1
    return floor_mult


# ═══════════════════════════════════════════════════════════════════════════════
# 稀有度抽选
# ═══════════════════════════════════════════════════════════════════════════════


def _merge_probabilities_at_max_rarity(
    probabilities: list[float], max_rarity: str
) -> list[float]:
    """将超过场景稀有度上限的概率质量归并到上限槽。"""
    max_idx = (
        _RARITY_ORDER.index(max_rarity)
        if max_rarity in _RARITY_ORDER
        else len(_RARITY_ORDER) - 1
    )
    merged = list(probabilities)
    if len(merged) <= max_idx:
        merged.extend([0.0] * (max_idx + 1 - len(merged)))
        return merged

    merged[max_idx] += sum(merged[max_idx + 1 :])
    merged[max_idx + 1 :] = [0.0] * (len(merged) - max_idx - 1)
    return merged


def _select_rarity(fish: FishData, probabilities: list[float]) -> tuple[FishData, int]:
    """按概率抽选稀有度索引。"""
    total = sum(probabilities)
    if total <= 0:
        return fish, 0

    rand = random.random() * total
    cumulative = 0
    for i, prob in enumerate(probabilities):
        cumulative += prob
        if rand <= cumulative:
            return fish, i

    return fish, 0


def _cap_rarity(rarity_index: int, max_rarity: str) -> str:
    """按最大稀有度封顶。"""
    order = ["N", "R", "SR", "SSR", "UR", "UTR"]
    max_idx = order.index(max_rarity) if max_rarity in order else len(order) - 1
    if rarity_index > max_idx:
        return order[max_idx]
    if rarity_index < len(order):
        return order[rarity_index]
    return order[-1]


def _cap_rarity_str(rarity: str, max_rarity: str) -> str:
    """按最大稀有度封顶（接收字符串稀有度名称）。"""
    order = ["N", "R", "SR", "SSR", "UR", "UTR"]
    max_idx = order.index(max_rarity) if max_rarity in order else len(order) - 1
    r_idx = order.index(rarity) if rarity in order else 0
    if r_idx > max_idx:
        return order[max_idx]
    return rarity


def _find_uncollected_fish(
    fish_pool: list[str], collected_fish_names: set[str]
) -> list[FishData]:
    """从不完整收集的鱼种中找出未收集的。"""
    uncollected: list[FishData] = []
    for fid in fish_pool:
        f = ConfigManager.get_fish(fid)
        if f and f.id not in collected_fish_names:
            uncollected.append(f)
    return uncollected


# ═══════════════════════════════════════════════════════════════════════════════
# 捕获 + 追加
# ═══════════════════════════════════════════════════════════════════════════════

_RARITY_ORDER = ["N", "R", "SR", "SSR", "UR", "UTR"]


# ──────────────────────────────────────────────────────────────────────────────
# 模块 1：单次随机结算
# ──────────────────────────────────────────────────────────────────────────────


def _single_random_roll(
    fish_pool: list[str],
    rod_level: int,
    difficulty: int,
    weather_luck_boost: float,
    weather_lost_wind: bool,
    weather_lost_wind_multiplier: float,
    location: LocationData | None,
    is_starry: bool,
    max_rarity: str,
    material_rate: float = 0.0,
    is_cat_park: bool = False,
    utr_special_active: bool = False,
) -> tuple[FishData | None, str | None, bool, bool, bool]:
    """一次独立的随机结算。

    返回 (fish, rarity, is_frame_hit, is_lost_wind_utr_hit, is_material)。
    不涉及保底判定和保底计数器更新——纯随机结算。

    能生成的掉落类型：
    - 展示木框（is_frame_hit=True）
    - 迷途风UTR鱼（is_lost_wind_utr_hit=True）
    - 猫猫乐园材料（is_material=True）
    - 普通鱼
    - 未钓到（fish=None）
    """
    # 猫猫乐园材料掉落（在木框/UTR之前判定，与原逻辑一致）
    if is_cat_park and material_rate > 0 and random.random() < material_rate:
        from ..cat_park import CAT_PARK_MATERIAL_TYPE, roll_cat_park_material

        material = FishData(
            id=f"{CAT_PARK_MATERIAL_TYPE}:{roll_cat_park_material()}",
            base_price=0,
        )
        return material, "N", False, False, True

    # 木框随机概率拦截（0.7%，非星空图）
    if not is_starry and random.random() < 0.007:
        return (
            FishData(id="展示木框", base_price=0),
            "UTR",
            True,
            False,
            False,
        )

    # UTR 递进概率拦截：由真实迷途风或已觉醒的乱纪元效果标签启用。
    if location and utr_special_active:
        utr_probability = get_lost_wind_utr_probability(rod_level, difficulty)
        utr_probability *= weather_lost_wind_multiplier
        if random.random() < utr_probability:
            fish_id = random.choice(location.fish_pool)
            fish = ConfigManager.get_fish(fish_id)
            if fish:
                return fish, "UTR", False, True, False

    # 稀有度表抽选
    fish_id = random.choice(fish_pool)
    fish = ConfigManager.get_fish(fish_id)
    if not fish:
        return None, None, False, False, False

    probabilities = get_rarity_probabilities_full(rod_level, difficulty)

    # 星空图的概率表最高只到 UR；UTR 仍仅来自递进概率与 150 次保底。
    # 其他场景则严格按自身 max_rarity 封顶。扩展槽位保留在原始概率表中，
    # 但抽样前必须把所有超限概率质量归并到上限槽，绝不能落入 N。
    table_max_rarity = "UR" if is_starry else max_rarity
    probabilities = _merge_probabilities_at_max_rarity(
        probabilities, table_max_rarity
    )

    if weather_luck_boost > 0:
        probabilities = apply_meteor_effect(probabilities, weather_luck_boost)

    fish_caught, rarity_index = _select_rarity(fish, probabilities)
    rarity_name = _cap_rarity(rarity_index, table_max_rarity)
    return fish_caught, rarity_name, False, False, False


# ──────────────────────────────────────────────────────────────────────────────
# 模块 2：幸运选择 —— 两次结算取最优
# ──────────────────────────────────────────────────────────────────────────────


def _roll_priority(
    is_fr: bool, is_lw: bool, r: str | None
) -> tuple[int, int]:
    """计算单次结算结果的优先级（越大越好）。

    木框 > 迷途风UTR > 普通鱼（按稀有度高低）
    """
    if is_fr:
        return (3, 999)
    if is_lw:
        return (2, 999)
    r_idx = _RARITY_ORDER.index(r) if r in _RARITY_ORDER else 0
    return (1, r_idx)


def _lucky_select(
    roll1: tuple[FishData | None, str | None, bool, bool, bool],
    roll2: tuple[FishData | None, str | None, bool, bool, bool],
    collected_set: set[tuple[str, str]] | None = None,
    max_rarity: str = "SSR",
    cat_park_prefer_material: bool = False,
) -> tuple[FishData | None, str | None, bool, bool, bool]:
    """幸运选择函数：从两次独立结算中选取最优结果。

    参数：
        roll1, roll2: 两次 _single_random_roll 的结果（5元组）
        collected_set: 已收集鱼种集合（用于优先未收集的鱼）
        max_rarity: 稀有度封顶
        cat_park_prefer_material: 猫猫乐园偏好——True 时优先选取材料而非鱼
            （猫雕像未全部建到3级时，材料优先；全部建完后，鱼优先）

    返回 (fish, rarity, is_frame_hit, is_lost_wind_utr_hit, is_material)。
    """
    fish1, rarity1, is_frame1, is_lw1, is_mat1 = roll1
    fish2, rarity2, is_frame2, is_lw2, is_mat2 = roll2

    p1 = _roll_priority(is_frame1, is_lw1, rarity1)
    p2 = _roll_priority(is_frame2, is_lw2, rarity2)

    # # ── 调试日志（已注释）──
    # _uid = _debug_current_user_id
    # _log_enabled = _DEBUG_LUCKY_USER_ID is None or _uid == _DEBUG_LUCKY_USER_ID
    # if _log_enabled:
    #     logger.info(
    #         f"[幸运选择] user={_uid} prefer_material={cat_park_prefer_material} | "
    #         f"roll1: fish={fish1.id if fish1 else None}, rarity={rarity1}, "
    #         f"frame={is_frame1}, lw={is_lw1}, mat={is_mat1}, priority={p1} | "
    #         f"roll2: fish={fish2.id if fish2 else None}, rarity={rarity2}, "
    #         f"frame={is_frame2}, lw={is_lw2}, mat={is_mat2}, priority={p2}"
    #     )

    # 猫猫乐园偏好定制：材料优先 vs 鱼优先
    if cat_park_prefer_material:
        # 猫雕像未全部建到3级：优先选材料
        if is_mat1 and not is_mat2:
            # if _log_enabled:
            #     logger.info(f"[幸运选择] user={_uid} 结果=roll1（材料优先）")
            return roll1
        if is_mat2 and not is_mat1:
            # if _log_enabled:
            #     logger.info(f"[幸运选择] user={_uid} 结果=roll2（材料优先）")
            return roll2
    else:
        # 猫雕像全部建到3级：优先选非材料（真正的鱼）
        if not is_mat1 and is_mat2:
            # if _log_enabled:
            #     logger.info(f"[幸运选择] user={_uid} 结果=roll1（鱼优先）")
            return roll1
        if not is_mat2 and is_mat1:
            # if _log_enabled:
            #     logger.info(f"[幸运选择] user={_uid} 结果=roll2（鱼优先）")
            return roll2

    # 标准优先级比较：木框 > 迷途风UTR > 普通鱼
    if p2 > p1:
        # if _log_enabled:
        #     logger.info(
        #         f"[幸运选择] user={_uid} 结果=roll2（优先级更高 p2={p2} > p1={p1}）"
        #     )
        return roll2
    elif p1[0] == 1 and p2[0] == 1 and collected_set is not None:
        # 同为普通鱼且稀有度相同，优先未收集的
        r1_capped = _cap_rarity_str(rarity1, max_rarity) if rarity1 else None
        r2_capped = _cap_rarity_str(rarity2, max_rarity) if rarity2 else None
        if r1_capped and r2_capped and r1_capped == r2_capped:
            f1_collected = (
                (fish1.id, r1_capped) in collected_set if fish1 else True
            )
            f2_collected = (
                (fish2.id, r2_capped) in collected_set if fish2 else True
            )
            if f1_collected and not f2_collected:
                # if _log_enabled:
                #     logger.info(f"[幸运选择] user={_uid} 结果=roll2（未收集优先）")
                return roll2

    # if _log_enabled:
    #     logger.info(f"[幸运选择] user={_uid} 结果=roll1（默认）")
    return roll1


# ──────────────────────────────────────────────────────────────────────────────
# 模块 3：单次钓鱼捕获判定（三段式：保底检查 → 随机结算 → 计数更新）
# ──────────────────────────────────────────────────────────────────────────────


def _catch_fish_with_buffs(
    fish_pool: list[str],
    rod_level: int,
    difficulty: int,
    collected_fish_names: set[str] | None = None,
    wish_active: bool = False,
    drop_bonus: int = 0,
    max_rarity: str = "SSR",
    frame_pity: int = 0,
    duoduo_count: int = 0,
    weather_luck_boost: float = 0,
    weather_lost_wind: bool = False,
    weather_lost_wind_multiplier: float = 1.0,
    location: LocationData | None = None,
    weather_cat_eat: bool = False,
    lucky_double_active: bool = False,
    utr_pity: int = 0,
    collected_set: set[tuple[str, str]] | None = None,
    cat_park_prefer_material: bool = False,
    material_rate: float = 0.0,
    is_cat_park: bool = False,
    cat_park_double_rate: float = 0.0,
) -> tuple[FishData | None, str | None, int, int, int]:
    """单次钓鱼捕获判定（三段式：保底检查 → 随机结算 → 计数更新）。

    返回: (fish, rarity, duoduo_mult, new_frame_pity, new_utr_pity)

    Part 1: 保底阈值检查 —— 满了直接给保底奖励并清零
    Part 2: 随机结算 —— 调用 _single_random_roll 1~2次，再调用 _lucky_select 取最优
    Part 3: 保底计数更新 —— 根据最终结果更新计数器

    参数 cat_park_prefer_material: 猫猫乐园幸运偏好
        True = 猫雕像未全部3级，幸运药水优先选材料
        False = 猫雕像全部3级或非猫猫乐园，幸运药水优先选鱼
    参数 cat_park_double_rate: 猫乐园旋转逗猫棒双倍概率（0~0.10），
        与多多药水在结算层面合并为浮点倍率，小数部分用概率计算
    """
    duoduo_mult = _compute_duoduo_quantity(duoduo_count, cat_park_double_rate)

    from ..starry import is_starry_location

    is_starry = bool(location and is_starry_location(location.id))
    # UTR 递进概率和 150 次保底统一由迷途风效果标签启用：
    # 普通图来自真实迷途风；星空图来自已觉醒的乱纪元。
    utr_special_active = weather_lost_wind

    def _next_frame_pity(*, delta: int = 0, reset: bool = False) -> int:
        """11-20 星空图不掉展示木框，保底计数完全冻结。"""
        if is_starry:
            return frame_pity
        if reset:
            return 0
        return frame_pity + delta

    # ──────────────────────────────────────────────────────────────
    # Part 1: 保底阈值检查
    # ──────────────────────────────────────────────────────────────
    # 展示木框保底（非星空图）
    if not is_starry and (frame_pity + 1) >= FRAME_PITY_THRESHOLD:
        frame_fish = FishData(id="展示木框", base_price=0)
        new_frame_pity = _next_frame_pity(reset=True)
        new_utr_pity = utr_pity + 1 if utr_special_active else utr_pity
        # 展示木框是非鱼类道具，不受多多药水/猫乐园双倍影响
        return frame_fish, "UTR", 1, new_frame_pity, new_utr_pity

    # UTR 保底（真实迷途风或已觉醒的乱纪元）
    if utr_special_active and location and (utr_pity + 1) >= UTR_PITY_THRESHOLD:
        fish_id = random.choice(location.fish_pool)
        fish = ConfigManager.get_fish(fish_id)
        if fish:
            new_utr_pity = 0
            # UTR鱼受多多药水翻倍，保底次数也翻倍
            new_frame_pity = _next_frame_pity(delta=duoduo_mult)
            return fish, "UTR", duoduo_mult, new_frame_pity, new_utr_pity

    # ──────────────────────────────────────────────────────────────
    # Part 2: 随机结算 —— 调用 _single_random_roll 1~2次 + _lucky_select
    # ──────────────────────────────────────────────────────────────
    roll1 = _single_random_roll(
        fish_pool,
        rod_level,
        difficulty,
        weather_luck_boost,
        weather_lost_wind,
        weather_lost_wind_multiplier,
        location,
        is_starry,
        max_rarity,
        material_rate=material_rate,
        is_cat_park=is_cat_park,
        utr_special_active=utr_special_active,
    )

    if lucky_double_active:
        roll2 = _single_random_roll(
            fish_pool,
            rod_level,
            difficulty,
            weather_luck_boost,
            weather_lost_wind,
            weather_lost_wind_multiplier,
            location,
            is_starry,
            max_rarity,
            material_rate=material_rate,
            is_cat_park=is_cat_park,
            utr_special_active=utr_special_active,
        )
        fish, rarity, is_frame, is_lost_wind_utr, is_material = _lucky_select(
            roll1,
            roll2,
            collected_set=collected_set,
            max_rarity=max_rarity,
            cat_park_prefer_material=cat_park_prefer_material,
        )
    else:
        fish, rarity, is_frame, is_lost_wind_utr, is_material = roll1

    # 封顶（用 is not None 避免 0/"N" 的 falsy 问题）
    if rarity is not None and not is_frame and not is_lost_wind_utr and not is_material:
        rarity = _cap_rarity_str(rarity, max_rarity)

    # 许愿：50% 替换为未收集鱼种（仅对普通鱼生效，不对材料/木框/UTR生效）
    if (
        wish_active
        and not is_frame
        and not is_lost_wind_utr
        and not is_material
        and collected_fish_names is not None
        and random.random() < 0.5
    ):
        uncollected = _find_uncollected_fish(fish_pool, collected_fish_names)
        if uncollected:
            fish = random.choice(uncollected)

    # ──────────────────────────────────────────────────────────────
    # Part 3: 保底计数更新
    # ──────────────────────────────────────────────────────────────
    if is_material:
        # 材料：frame_pity +1, utr_pity +1（迷途风时），不受多多药水影响
        new_frame_pity = _next_frame_pity(delta=1)
        new_utr_pity = utr_pity + 1 if utr_special_active else utr_pity
        # 材料是非鱼类，不受多多药水数量翻倍影响
        return fish, rarity, 1, new_frame_pity, new_utr_pity
    if is_frame:
        # 展示木框：frame_pity 清零，若迷途风天气则 utr_pity +1
        new_frame_pity = _next_frame_pity(reset=True)
        new_utr_pity = utr_pity + 1 if utr_special_active else utr_pity
        # 展示木框是非鱼类道具，不受多多药水数量翻倍影响
        return fish, rarity, 1, new_frame_pity, new_utr_pity
    elif is_lost_wind_utr:
        # 迷途风UTR：utr_pity 清零，frame_pity +duoduo_mult（翻倍鱼提供翻倍保底）
        new_utr_pity = 0
        new_frame_pity = _next_frame_pity(delta=duoduo_mult)
        # UTR鱼是真正的鱼，受多多药水数量翻倍影响
        return fish, rarity, duoduo_mult, new_frame_pity, new_utr_pity
    else:
        # 普通鱼或未钓到：保底计数器 +duoduo_mult（多多药水翻倍鱼提供翻倍保底次数）
        new_frame_pity = _next_frame_pity(delta=duoduo_mult)
        new_utr_pity = (
            utr_pity + duoduo_mult if utr_special_active else utr_pity
        )

    return fish, rarity, duoduo_mult, new_frame_pity, new_utr_pity


def _try_catch_one(
    fish_pool: list[str],
    effects: dict,
    collected_fish_names: set[str],
    location: LocationData,
    frame_pity: int,
    utr_pity: int = 0,
    collected_set: set[tuple[str, str]] | None = None,
) -> tuple[FishData | None, str | None, int, int, int]:
    """包装 _catch_fish_with_buffs 为一次判定。

    返回: (fish, rarity, new_frame_pity, quantity, new_utr_pity)
    """
    rod_level = effects["rod_level"]
    castle_rate = effects.get("cat_park_castle_rod_rate", 0)
    if castle_rate > 0 and random.random() < castle_rate:
        rod_level += 1

    fish, rarity, quantity, new_frame_pity, new_utr_pity = _catch_fish_with_buffs(
        fish_pool,
        rod_level,
        effects["difficulty"],
        collected_fish_names,
        effects.get("wish_active", False),
        effects.get("drop_bonus", 0),
        effects.get("max_rarity", location.max_rarity),
        frame_pity,
        effects.get("duoduo_count", 0),
        effects.get("weather_luck_boost", 0),
        effects.get("weather_lost_wind", False),
        effects.get("weather_lost_wind_multiplier", 1.0),
        location,
        weather_cat_eat=effects.get("weather_cat_eat", False),
        lucky_double_active=effects.get("lucky_double_active", False),
        utr_pity=utr_pity,
        collected_set=collected_set,
        cat_park_prefer_material=effects.get("cat_park_prefer_material", False),
        material_rate=effects.get("material_rate", 0.0),
        is_cat_park=effects.get("is_cat_park", False),
        cat_park_double_rate=effects.get("cat_park_double_rate", 0.0),
    )
    if fish is not None and rarity is not None:
        return fish, rarity, new_frame_pity, quantity, new_utr_pity
    return None, None, new_frame_pity, 0, new_utr_pity


def _try_append_starry_meteor_fish(
    location: LocationData,
    fish: FishData | None,
    rarity: str | None,
    meteor_fish_numbers: list[int] | None,
    effects: dict | None = None,
) -> None:
    """星空地图额外掉落 6 位编号流星鱼（星空祈愿）。

    现阶段仍复用历史字段名 meteor_fish_numbers 贯穿结算链路，
    真正的流星鱼规则由 core.starry_system 统一计算。
    """
    if not fish or not rarity or meteor_fish_numbers is None:
        return

    from ..starry import is_starry_location

    if not is_starry_location(location.id):
        return

    active_buffs = effects.get("_active_buffs", []) if effects else []
    has_solar_wind = any(
        buff.buff_type == BuffEffect.BUFF_TYPE_WEATHER_SOLAR_WIND
        for buff in active_buffs
    )
    has_meteor_shower = any(
        buff.buff_type == BuffEffect.BUFF_TYPE_WEATHER_METEOR_SHOWER
        for buff in active_buffs
    )
    has_hengjiyuan = any(
        buff.buff_type == BuffEffect.BUFF_TYPE_WEATHER_HENGJIYUAN
        for buff in active_buffs
    )
    has_gamma_burst = any(
        buff.buff_type == BuffEffect.BUFF_TYPE_GAMMA_RAY_BURST for buff in active_buffs
    )

    if has_gamma_burst:
        has_solar_wind = True
        has_meteor_shower = True
        has_hengjiyuan = True

    starry_fish = roll_starry_fish(
        rod_level=int((effects or {}).get("rod_level", 0) or 0),
        solar_wind=has_solar_wind,
        meteor_shower=has_meteor_shower,
        hengjiyuan=has_hengjiyuan,
        lucky_double=bool(effects and effects.get("lucky_double_active", False)),
    )
    if starry_fish is not None:
        # 真多多后置：先得到最终编号产物，再检查多多并复制为两条同号
        duoduo_active = bool(effects and int(effects.get("duoduo_count", 0) or 0) > 0)
        meteor_fish_numbers.extend(
            expand_starry_fish_with_duoduo(
                starry_fish.fish_id,
                duoduo_active=duoduo_active,
            )
        )


def _append_fish(
    fish: FishData | None,
    rarity: str | None,
    frame_pity: int,
    fish_caught: list[tuple[FishData, str, int]],
    collected_fish_names: set[str],
    quantity: int = 1,
    cat_eaten_fish: list[tuple[FishData, str, int]] | None = None,
    effects: dict | None = None,
    location: LocationData | None = None,
    collected_set: set[tuple[str, str]] | None = None,
    cat_gifts: dict | None = None,
    bait_id: str = "",
) -> int:
    """将捕获的鱼追加到结果列表中，处理猫吃鱼逻辑。"""
    lucky_double = bool(effects and effects.get("lucky_double_active", False))
    if fish and rarity:
        if quantity == 0:
            if cat_eaten_fish is not None:
                cat_eaten_fish.append((fish, rarity, 1))
            if cat_gifts is not None:
                process_cat_gift(
                    fish, rarity, cat_gifts, location, collected_set, bait_id,
                    lucky_double=lucky_double,
                )
        elif (
            effects
            and effects.get("weather_cat_eat", False)
            and fish.id != "展示木框"
            and not fish.id.startswith("cat_park_material:")
        ):
            eaten_count = 0
            for _ in range(quantity):
                cat_eat_chance = CAT_EAT_CHANCE * effects.get(
                    "weather_cat_eat_multiplier", 1.0
                )
                if random.random() < cat_eat_chance:
                    eaten_count += 1
                    if cat_eaten_fish is not None:
                        cat_eaten_fish.append((fish, rarity, 1))
                    if cat_gifts is not None:
                        process_cat_gift(
                            fish, rarity, cat_gifts, location, collected_set, bait_id,
                            lucky_double=lucky_double,
                        )
            kept = quantity - eaten_count
            if kept > 0:
                fish_caught.append((fish, rarity, kept))
                collected_fish_names.add(fish.id)
        else:
            fish_caught.append((fish, rarity, quantity))
            collected_fish_names.add(fish.id)
    return frame_pity


def _catch_fish_at_interval(
    effects: dict,
    location: LocationData,
    collected_fish_names: set[str],
    frame_pity: int,
    fish_caught: list[tuple[FishData, str, int]],
    utr_pity: int = 0,
    cat_eaten_fish: list[tuple[FishData, str, int]] | None = None,
    collected_set: set[tuple[str, str]] | None = None,
    cat_gifts: dict | None = None,
    bait_id: str = "",
    dragon_boat_buffs: list | None = None,
    meteor_fish_numbers: list[int] | None = None,
    catch_time: datetime | None = None,
) -> tuple[int, int]:
    """在一次钓鱼间隔执行捕获（含双倍捕获和额外掉落）。

    猫乐园旋转逗猫棒的双倍概率已合并到 _catch_fish_with_buffs 的 duoduo_mult 中，
    不再通过额外捕获次数实现。
    """

    base_catch_count = 2 if effects["double_catch"] else 1
    for _ in range(base_catch_count):
        fish, rarity, frame_pity, quantity, utr_pity = _try_catch_one(
            location.fish_pool,
            effects,
            collected_fish_names,
            location,
            frame_pity,
            utr_pity,
            collected_set=collected_set,
        )
        _append_fish(
            fish,
            rarity,
            frame_pity,
            fish_caught,
            collected_fish_names,
            quantity,
            cat_eaten_fish=cat_eaten_fish,
            effects=effects,
            location=location,
            collected_set=collected_set,
            cat_gifts=cat_gifts,
            bait_id=bait_id,
        )
        _try_append_starry_meteor_fish(
            location, fish, rarity, meteor_fish_numbers, effects=effects
        )
        # 掉到材料时结束本次间隔（与原逻辑一致：材料不触发双倍捕获）
        if fish is not None and fish.id.startswith("cat_park_material:"):
            logger.debug(
                f"[材料调试] user={_debug_current_user_id} 掉到材料 {fish.id}，"
                f"fish_caught长度: {len(fish_caught)}，结束本次间隔"
            )
            break
        # 端午活动：2%概率额外获得流星鱼（仅在buff时间区间内）
        if (
            dragon_boat_buffs
            and meteor_fish_numbers is not None
            and fish
            and rarity
            and catch_time
            and any(
                _make_naive(b.start_time) <= catch_time <= _make_naive(b.end_time)
                for b in dragon_boat_buffs
            )
        ):
            if random.random() < 0.02:
                meteor_fish_numbers.append(random.randint(10000000, 99999999))

    drop_bonus = effects.get("drop_bonus", 0)
    if drop_bonus > 0 and random.random() < drop_bonus * 0.05:
        fish, rarity, frame_pity, quantity, utr_pity = _try_catch_one(
            location.fish_pool,
            effects,
            collected_fish_names,
            location,
            frame_pity,
            utr_pity,
        )
        _append_fish(
            fish,
            rarity,
            frame_pity,
            fish_caught,
            collected_fish_names,
            quantity,
            cat_eaten_fish=cat_eaten_fish,
            effects=effects,
            location=location,
            collected_set=collected_set,
            cat_gifts=cat_gifts,
            bait_id=bait_id,
        )

    return frame_pity, utr_pity


def _consume_one_bait(
    bait_remaining: int,
    no_bait_mode: bool,
    effects: dict,
) -> tuple[int, bool, bool]:
    """消耗一个鱼饵，返回 (consumed_count, new_bait_remaining, new_no_bait_mode)。

    顺序：先确认有鱼饵 → 再按概率消耗。
    - 鱼饵用尽时切换到无饵模式
    - 暴风天气有额外节省概率
    - 猫猫乐园有鱼饵节省概率
    """
    if no_bait_mode or bait_remaining <= 0:
        return 0, bait_remaining, True

    # 暴风天气：额外节省概率
    if effects.get("weather_half_bait", False):
        storm_save = min(1.0, 0.5 * effects.get("weather_storm_multiplier", 1.0))
        if random.random() < storm_save:
            return 0, bait_remaining, False

    # 猫猫乐园鱼饵节省
    if random.random() < effects.get("cat_park_bait_save", 0):
        return 0, bait_remaining, False

    # 正常消耗
    return 1, bait_remaining - 1, False


def _try_catch_in_remaining_time(
    remaining_minutes: float,
    fishing_interval: float,
    effects: dict,
    location: LocationData,
    collected_fish_names: set[str],
    frame_pity: int,
    fish_caught: list[tuple[FishData, str, int]],
    no_bait_mode: bool,
    bait_remaining: int,
    utr_pity: int = 0,
    cat_eaten_fish: list[tuple[FishData, str, int]] | None = None,
    collected_set: set[tuple[str, str]] | None = None,
    cat_gifts: dict | None = None,
    bait_id: str = "",
    dragon_boat_buffs: list | None = None,
    meteor_fish_numbers: list[int] | None = None,
    catch_time: datetime | None = None,
) -> tuple[int, int, bool, int, int]:
    """在剩余时间内按概率尝试一次捕获。

    鱼饵消耗由主循环统一后置处理：本函数只负责钓鱼，不扣鱼饵。
    返回 caught=1 表示钓到了鱼（主循环据此扣鱼饵），caught=0 表示未钓到。
    """
    # 按剩余时间比例判定是否钓到鱼
    if random.random() >= (remaining_minutes / fishing_interval):
        return 0, bait_remaining, no_bait_mode, frame_pity, utr_pity

    # 钓到了鱼，执行和完整间隔一样的捕获逻辑
    frame_pity, utr_pity = _catch_fish_at_interval(
        effects,
        location,
        collected_fish_names,
        frame_pity,
        fish_caught,
        utr_pity,
        cat_eaten_fish=cat_eaten_fish,
        collected_set=collected_set,
        cat_gifts=cat_gifts,
        bait_id=bait_id,
        dragon_boat_buffs=dragon_boat_buffs,
        meteor_fish_numbers=meteor_fish_numbers,
        catch_time=catch_time,
    )
    return 1, bait_remaining, no_bait_mode, frame_pity, utr_pity


# ═══════════════════════════════════════════════════════════════════════════════
# 主模拟循环
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class _SimulationState:
    """模拟循环的可变状态；字段顺序与最终结果一一对应。"""

    current_time: datetime
    frame_pity: int
    utr_pity: int
    bait: FishData | None
    bait_speed_bonus: int
    bait_remaining: int
    fish_caught: list[tuple[FishData, str, int]] = field(default_factory=list)
    cat_eaten_fish: list[tuple[FishData, str, int]] = field(default_factory=list)
    meteor_fish_numbers: list[int] = field(default_factory=list)
    bait_usage: dict[str, int] = field(default_factory=dict)
    available_baits: dict[str, dict] = field(default_factory=dict)
    collected_fish_names: set[str] = field(default_factory=set)
    collected_set: set[tuple[str, str]] = field(default_factory=set)
    dragon_boat_buffs: list = field(default_factory=list)
    cat_gifts: dict = field(default_factory=dict)
    no_bait_mode: bool = False


class _WindowAction(Enum):
    FULL_INTERVAL = auto()
    TRY_REMAINDER = auto()
    STOP = auto()


async def _initialize_simulation_state(
    ctx: FishingContext,
    initial_frame_pity: int | None,
    initial_cat_frame_pity: int | None,
    initial_utr_pity: int | None,
) -> _SimulationState:
    """按原调用顺序读取用户状态并建立循环状态。"""
    frame_pity = (
        initial_frame_pity
        if initial_frame_pity is not None
        else ctx.user.frame_pity_counter
    )
    cat_frame_pity = (
        initial_cat_frame_pity
        if initial_cat_frame_pity is not None
        else ctx.user.cat_frame_pity_counter
    )
    user_fish = await FishingUser.get_user_fish(ctx.user_id)
    collected_fish_names = {f["fish_name"] for f in user_fish}
    collected_set = await FishingUser.get_user_collected(ctx.user_id)
    status_dict = await FishingUser.get_status(ctx.user_id)
    if status_dict:
        existing_fish = deserialize_fish_caught(status_dict.get("fish_caught", []))
        for fish, _rarity, _count in existing_fish:
            collected_fish_names.add(fish.id)

    if initial_utr_pity is not None:
        utr_pity = initial_utr_pity
    elif status_dict:
        utr_pity = status_dict.get("utr_pity", ctx.user.utr_pity_counter)
    else:
        utr_pity = ctx.user.utr_pity_counter

    available_baits: dict[str, dict] = {}
    items = await FishingUser.get_user_items(ctx.user_id)
    for item in items:
        if item["item_type"] == "bait" and item["count"] > 0:
            bait_data = ConfigManager.get_bait(item["item_id"])
            if bait_data:
                available_baits[str(bait_data.id)] = {
                    "data": bait_data,
                    "remaining": item["count"],
                }

    return _SimulationState(
        current_time=ctx.settle_start,
        frame_pity=frame_pity,
        utr_pity=utr_pity,
        bait=ctx.bait,
        bait_speed_bonus=ctx.bait_speed_bonus,
        bait_remaining=ctx.bait_remaining,
        available_baits=available_baits,
        collected_fish_names=collected_fish_names,
        collected_set=collected_set,
        dragon_boat_buffs=[
            b for b in ctx.buffs if b.buff_type == BuffEffect.BUFF_TYPE_DRAGON_BOAT
        ],
        cat_gifts={
            "gold": 0,
            "corn": 0,
            "bait_id": "",
            "bait_count": 0,
            "cat_frames": 0,
            "fish_gifts": [],
            "cat_frame_pity": cat_frame_pity,
        },
    )


async def _switch_depleted_bait(ctx: FishingContext, state: _SimulationState) -> None:
    """鱼饵耗尽时沿用原规则切换到价格最高的库存鱼饵。"""
    if state.no_bait_mode or state.bait_remaining > 0:
        return
    best_id = None
    best_price = -1
    for bait_id, info in state.available_baits.items():
        if info["remaining"] > 0 and info["data"].price > best_price:
            best_price = info["data"].price
            best_id = bait_id
    if best_id:
        new_bait = state.available_baits[best_id]["data"]
        new_count = state.available_baits[best_id]["remaining"]
        if state.bait and state.bait.id != new_bait.id:
            switch_message = (
                f"🎣 {state.bait.name}已用完，"
                f"切换为{new_bait.name}（剩余{new_count}个）"
            )
            ctx.buff_messages.append(switch_message)
        state.bait = new_bait
        state.bait_speed_bonus = new_bait.speed_bonus
        state.bait_remaining = new_count
        return
    if state.bait:
        ctx.buff_messages.append(f"🎣 {state.bait.name}已用完，没有其他鱼饵了")
    state.no_bait_mode = True
    state.bait = None


async def _calculate_loop_effects(
    ctx: FishingContext,
    state: _SimulationState,
    freeze_buff_time: datetime | None,
) -> dict:
    """计算当前时刻的 buff、场景和天气效果。"""
    buff_time = freeze_buff_time if freeze_buff_time is not None else state.current_time
    current_bait_speed = 0 if state.no_bait_mode else state.bait_speed_bonus
    effects = FishingBuffCalculator.get_effects_at_time(
        ctx.buffs,
        buff_time,
        ctx.user.rod_level,
        current_bait_speed,
        ctx.location.difficulty,
    )
    effects["_active_buffs"] = [
        buff
        for buff in ctx.buffs
        if _make_naive(buff.start_time) <= buff_time < _make_naive(buff.end_time)
    ]
    from ..cat_park import (
        CAT_PARK_MATERIAL_RATE,
        get_cat_park_state,
        get_user_cat_park_effect_values,
        is_cat_park_location,
    )
    from ..starry import is_starry_location

    if is_starry_location(
        ctx.location.id
    ) and f"collect_scene_{ctx.location.id}" not in (ctx.user.achievements or []):
        effects["max_rarity"] = "UR"
    if not is_cat_park_location(ctx.location.id):
        return effects

    cat_park_effects = await get_user_cat_park_effect_values(ctx.user_id)
    effects["is_cat_park"] = True
    effects["cat_park_speed_multiplier"] = cat_park_effects.get(
        "cat_park_speed_multiplier", 1.0
    )
    effects["cat_park_double_rate"] = cat_park_effects.get("double_rate", 0)
    effects["cat_park_castle_rod_rate"] = cat_park_effects.get("castle_rod_rate", 0)
    effects["cat_park_bait_save"] = cat_park_effects.get("bait_save", 0)
    effects["material_rate"] = cat_park_effects.get(
        "material_rate", CAT_PARK_MATERIAL_RATE
    )
    _apply_cat_park_weather_bonus(effects, cat_park_effects.get("weather_bonus", 0))
    cat_park_state = await get_cat_park_state(ctx.user_id)
    all_built = all(
        level >= 3 for level in cat_park_state.get("buildings", {}).values()
    )
    effects["cat_park_prefer_material"] = not all_built
    return effects


def _apply_cat_park_weather_bonus(effects: dict, weather_bonus: float) -> None:
    if weather_bonus <= 0:
        return
    if effects.get("weather_speed_multiplier", 1.0) > 1:
        speed_extra = effects["weather_speed_multiplier"] - 1
        effects["weather_speed_multiplier"] = 1 + speed_extra * (1 + weather_bonus)
    if effects.get("weather_luck_boost", 0) > 0:
        effects["weather_luck_boost"] *= 1 + weather_bonus
    if effects.get("weather_half_bait", False):
        effects["weather_storm_multiplier"] = 1 + weather_bonus
    if effects.get("weather_lost_wind", False):
        effects["weather_lost_wind_multiplier"] = 1 + weather_bonus
    if effects.get("weather_cat_eat", False):
        effects["weather_cat_eat_multiplier"] = 1 + weather_bonus


def _calculate_fishing_interval(ctx: FishingContext, effects: dict) -> float:
    interval = ConfigManager.calculate_fishing_interval(
        ctx.user.hook_level, effects["speed_bonus"], False
    )
    interval /= effects.get("extra_speed_multiplier", 1.0)
    interval /= effects.get("weather_speed_multiplier", 1.0)
    interval /= effects.get("cat_park_speed_multiplier", 1.0)
    return interval


def _select_window_action(
    ctx: FishingContext,
    state: _SimulationState,
    fishing_interval: float,
    time_credit_minutes: float | None,
) -> tuple[_WindowAction, float | datetime | None]:
    """只计算时间窗口，不触发随机调用。"""
    if time_credit_minutes is not None:
        if time_credit_minutes < fishing_interval:
            return _WindowAction.STOP, None
        return _WindowAction.FULL_INTERVAL, time_credit_minutes - fishing_interval
    next_fish_time = state.current_time + timedelta(minutes=fishing_interval)
    if next_fish_time > ctx.now:
        remaining = (ctx.now - state.current_time).total_seconds() / 60
        return _WindowAction.TRY_REMAINDER, remaining
    return _WindowAction.FULL_INTERVAL, next_fish_time


def _record_bait_consumption(
    state: _SimulationState, effects: dict, fish_count_before: int
) -> None:
    if len(state.fish_caught) <= fish_count_before:
        return
    consumed, state.bait_remaining, state.no_bait_mode = _consume_one_bait(
        state.bait_remaining, state.no_bait_mode, effects
    )
    logger.debug(
        f"[材料调试] user={_debug_current_user_id} "
        f"fish_caught: {fish_count_before}→{len(state.fish_caught)}, "
        f"consumed={consumed}, bait_remaining={state.bait_remaining}"
    )
    if consumed > 0 and state.bait:
        bait_id = str(state.bait.id)
        state.bait_usage[bait_id] = state.bait_usage.get(bait_id, 0) + consumed
        if bait_id in state.available_baits:
            state.available_baits[bait_id]["remaining"] -= consumed


async def simulate_fishing_loop(
    ctx: FishingContext,
    initial_frame_pity: int | None = None,
    initial_cat_frame_pity: int | None = None,
    initial_utr_pity: int | None = None,
    freeze_buff_time: datetime | None = None,
    time_credit_minutes: float | None = None,
    initial_available_baits: dict[str, dict[str, Any]] | None = None,
    initial_no_bait_mode: bool | None = None,
) -> SimulationResult:
    """主钓鱼模拟循环：按时序推进，处理鱼饵消耗、鱼获、猫系统。

    两种模式：
    - 正常模式：current_time 从 settle_start 推进到 ctx.now，
      每条鱼消耗 fishing_interval 分钟的实际时间。
    - 时光药水模式：current_time 不推进，每条鱼从时间余额中扣除
      fishing_interval 分钟。余额不足时丢弃剩余时间并结束。
      此模式下 freeze_buff_time 应设为使用时刻，确保 buff 在整个模拟期间冻结。
    """
    global _debug_current_user_id
    _debug_current_user_id = ctx.user_id
    state = await _initialize_simulation_state(
        ctx, initial_frame_pity, initial_cat_frame_pity, initial_utr_pity
    )
    if initial_available_baits is not None:
        state.available_baits = {
            bait_id: dict(info) for bait_id, info in initial_available_baits.items()
        }
    if initial_no_bait_mode is not None:
        state.no_bait_mode = initial_no_bait_mode

    while True:
        await _switch_depleted_bait(ctx, state)
        effects = await _calculate_loop_effects(ctx, state, freeze_buff_time)
        fishing_interval = _calculate_fishing_interval(ctx, effects)

        action, window_value = _select_window_action(
            ctx, state, fishing_interval, time_credit_minutes
        )
        if action is _WindowAction.STOP:
            break
        if time_credit_minutes is not None:
            time_credit_minutes = float(window_value)
        elif action is _WindowAction.TRY_REMAINDER:
            remaining_time = float(window_value)
            if remaining_time > 0:
                fish_count_before = len(state.fish_caught)
                remainder_result = _try_catch_in_remaining_time(
                    remaining_time,
                    fishing_interval,
                    effects,
                    ctx.location,
                    state.collected_fish_names,
                    state.frame_pity,
                    state.fish_caught,
                    state.no_bait_mode,
                    state.bait_remaining,
                    state.utr_pity,
                    cat_eaten_fish=state.cat_eaten_fish,
                    collected_set=state.collected_set,
                    cat_gifts=state.cat_gifts,
                    bait_id=str(state.bait.id) if state.bait else "",
                    dragon_boat_buffs=state.dragon_boat_buffs,
                    meteor_fish_numbers=state.meteor_fish_numbers,
                    catch_time=state.current_time,
                )
                (
                    caught,
                    state.bait_remaining,
                    state.no_bait_mode,
                    state.frame_pity,
                    state.utr_pity,
                ) = remainder_result
                if caught > 0:
                    _record_bait_consumption(state, effects, fish_count_before)
            break

        # 1-10/S1 看迷途风；11-20 看 collect_scene 解锁后 max_rarity=UTR
        from ..starry import is_starry_location as _is_starry_loc
        _starry = _is_starry_loc(ctx.location.id)
        _utr_active = (
            (not _starry and effects.get("weather_lost_wind", False))
            or (_starry and effects.get("max_rarity", ctx.location.max_rarity) == "UTR")
        )
        utr_was_guaranteed = (
            state.utr_pity + 1 >= UTR_PITY_THRESHOLD and _utr_active
        )
        from ..starry import is_starry_location as _is_starry

        frame_was_guaranteed = (
            state.frame_pity >= FRAME_PITY_THRESHOLD
            and not _is_starry(ctx.location.id)
        )
        fish_count_before = len(state.fish_caught)
        state.frame_pity, state.utr_pity = _catch_fish_at_interval(
            effects,
            ctx.location,
            state.collected_fish_names,
            state.frame_pity,
            state.fish_caught,
            state.utr_pity,
            cat_eaten_fish=state.cat_eaten_fish,
            collected_set=state.collected_set,
            cat_gifts=state.cat_gifts,
            bait_id=str(state.bait.id) if state.bait else "",
            dragon_boat_buffs=state.dragon_boat_buffs,
            meteor_fish_numbers=state.meteor_fish_numbers,
            catch_time=state.current_time,
        )
        _record_bait_consumption(state, effects, fish_count_before)

        if utr_was_guaranteed and state.utr_pity == 0:
            msg = (
                "✨ UTR保底触发！必出UTR鱼！"
                if _starry
                else "🌀 迷途风保底触发！必出UTR鱼！"
            )
            ctx.buff_messages.append(msg)
        if frame_was_guaranteed and state.frame_pity == 0:
            ctx.buff_messages.append("🖼️ 展示木框保底触发！必出展示木框！")
        if time_credit_minutes is None:
            state.current_time = window_value

    return SimulationResult(
        fish_caught=state.fish_caught,
        bait_usage=state.bait_usage,
        frame_pity=state.frame_pity,
        bait=state.bait,
        bait_remaining=state.bait_remaining,
        cat_eaten_fish=state.cat_eaten_fish,
        cat_gifts=state.cat_gifts,
        utr_pity=state.utr_pity,
        meteor_fish_numbers=state.meteor_fish_numbers,
        available_baits=state.available_baits,
        no_bait_mode=state.no_bait_mode,
    )
