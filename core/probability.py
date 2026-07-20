"""
概率计算 — 展示概率、天气调整概率。
"""

from ..constants import (
    apply_meteor_effect,
    get_display_probabilities,
    get_lost_wind_utr_probability,
)


class DisplayProbabilities(dict[str, float]):
    """兼容 dict 的展示模型。

    字典值只表示一次判定的互斥稀有度分布（总和恒为 1）；数量增益和
    木框、材料、流星鱼等独立判定通过属性单独携带，避免混入概率分布。
    """

    def __init__(
        self,
        probabilities: dict[str, float],
        *,
        quantity_multiplier: int = 1,
        independent_mechanics: dict[str, float | bool | str] | None = None,
    ) -> None:
        super().__init__(probabilities)
        self.quantity_multiplier = max(1, int(quantity_multiplier))
        self.independent_mechanics = dict(independent_mechanics or {})


def calculate_display_probabilities(
    rod_level: int,
    difficulty: int,
    max_rarity: str,
    duoduo_count: int = 0,
    weather_luck_boost: float = 0,
    weather_lost_wind: bool = False,
    material_rate: float = 0.0,
    starry_utr_unlocked: bool = False,
    weather_lost_wind_multiplier: float = 1.0,
    independent_mechanics: dict[str, float | bool | str] | None = None,
) -> dict[str, float]:
    """计算最终展示概率，综合多多、流星、迷途风、材料率效果。

    字典值始终表示一次判定的互斥鱼稀有度分布。多多的数量倍率和
    猫猫乐园材料率作为独立机制附加在返回值属性中，不会缩放该分布。

    starry_utr_unlocked：11-20 集齐全 UR 后，展示递进 UTR 概率（概率表 UTR 截断为 0）。
    """
    # 星空图解锁后仍不展示概率表 UTR，只用递进概率。
    table_max = "UR" if starry_utr_unlocked else max_rarity
    probabilities = get_display_probabilities(rod_level, difficulty, 0, table_max)

    if weather_luck_boost > 0:
        rarity_order = list(probabilities)
        adjusted = apply_meteor_effect(
            [probabilities[key] for key in rarity_order], weather_luck_boost
        )
        probabilities = dict(zip(rarity_order, adjusted, strict=True))

    independent = dict(independent_mechanics or {})
    if material_rate > 0:
        independent["material_rate"] = material_rate

    # 递进 UTR 只在迷途风效果实际生效时从普通稀有度分布中切出；
    # 星空成就仅负责解锁候选池，不能绕过乱纪元的天气门控。
    if weather_lost_wind:
        utr_probability = get_lost_wind_utr_probability(
            rod_level, difficulty
        ) * max(0.0, weather_lost_wind_multiplier)
        remaining = utr_probability
        for rarity in list(probabilities):
            if rarity == "UTR" or remaining <= 0:
                continue
            deducted = min(probabilities.get(rarity, 0.0), remaining)
            probabilities[rarity] = probabilities.get(rarity, 0.0) - deducted
            remaining -= deducted
        applied_utr_probability = utr_probability - remaining
        probabilities["UTR"] = (
            probabilities.get("UTR", 0.0) + applied_utr_probability
        )
        independent["lost_wind_utr_rate"] = applied_utr_probability

    return DisplayProbabilities(
        probabilities,
        quantity_multiplier=2**duoduo_count,
        independent_mechanics=independent,
    )
