from ..config import ConfigManager


def build_speed_bonus_detail(
    hook_level: int,
    base_bait_speed_bonus: int,
    effective_speed_bonus: int,
    extra_speed_multiplier: float = 1.0,
    weather_speed_multiplier: float = 1.0,
    cat_park_speed_multiplier: float = 1.0,
    starry_bonus: int = 0,
) -> str | None:
    speed_bonus_parts = []
    hook_pct = hook_level * ConfigManager.get_shop().hook_speed_bonus_per_level
    if hook_pct > 0:
        speed_bonus_parts.append(f"鱼钩+{hook_pct}%")

    # 星空艇加成从总 buff 中拆出单独显示，让玩家了解星空艇贡献了多少速度
    buff_speed = effective_speed_bonus - base_bait_speed_bonus - starry_bonus
    if base_bait_speed_bonus > 0:
        speed_bonus_parts.append(f"鱼饵+{base_bait_speed_bonus}%")
    if buff_speed > 0:
        speed_bonus_parts.append(f"Buff+{buff_speed}%")
    if starry_bonus > 0:
        speed_bonus_parts.append(f"星空艇+{starry_bonus}%")
    if cat_park_speed_multiplier > 1.0:
        speed_bonus_parts.append(f"猫猫乐园×{cat_park_speed_multiplier:.2f}")
    if extra_speed_multiplier > 1.0:
        speed_bonus_parts.append(f"额外×{extra_speed_multiplier:.1f}")
    if weather_speed_multiplier > 1.0:
        speed_bonus_parts.append(f"天气×{weather_speed_multiplier:.1f}")

    return " ".join(speed_bonus_parts) if speed_bonus_parts else None


def calculate_effective_fishing_interval(
    hook_level: int,
    effective_speed_bonus: int,
    extra_speed_multiplier: float = 1.0,
    weather_speed_multiplier: float = 1.0,
    cat_park_speed_multiplier: float = 1.0,
) -> float:
    fishing_interval = ConfigManager.calculate_fishing_interval(
        hook_level, effective_speed_bonus, False
    )
    fishing_interval /= extra_speed_multiplier
    fishing_interval /= weather_speed_multiplier
    fishing_interval /= cat_park_speed_multiplier
    return max(1, fishing_interval)
