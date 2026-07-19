"""
钓鱼主模块（向后兼容门面）。

所有核心逻辑已迁移到 core/ 子包，本模块仅做重新导出以保持现有导入路径有效。
新增代码应直接从 core/ 导入。
"""

from .core import (
    FishingContext,
    SimulationResult,
    StepResult,
    calculate_display_probabilities,
    check_fishing_status,
    deserialize_fish_caught,
    merge_fish,
    process_fish_results,
    render_scene,
    save_fish_to_backpack,
    serialize_fish_caught,
    settle_fishing_step,
    simulate_fishing_loop,
    start_fishing,
    stop_fishing,
    use_time_potion_settle,
)
from .core.engine import (
    _apply_duoduo,
    _cap_rarity,
    _catch_fish_with_buffs,
    _compute_duoduo_quantity,
)

# ── 渲染包装函数（在此定义以避免循环导入） ──────────────────────────────────


async def handle_fishing_result(
    user_id: str,
    render_data: dict,
    buff_messages: list[str] | None = None,
    is_last_stop: bool = False,
) -> bytes:
    """渲染收杆结果图片（包装器，保持旧 API）。"""
    from .render import render_fishing_result

    if buff_messages is None:
        buff_messages = []
    return await render_fishing_result(
        user_id=user_id,
        location=render_data["location"],
        duration_minutes=render_data["duration_minutes"],
        merged_fish=render_data["merged_fish"],
        fish_coins=render_data["fish_coins"],
        achievement_messages=render_data.get("achievement_messages", []),
        sign_info=render_data.get("sign_info"),
        cat_eaten_fish=render_data.get("cat_eaten_fish"),
        cat_gifts=render_data.get("cat_gifts"),
        buffs=render_data.get("buffs", []),
        fishing_start_time=render_data.get("fishing_start_time"),
        now_time=render_data.get("now_time"),
        buff_messages=buff_messages,
        is_last_stop=is_last_stop,
        meteor_fish_numbers=render_data.get("meteor_fish_numbers"),
        cat_park_materials=render_data.get("cat_park_materials"),
        starry_score=render_data.get("starry_score"),
        miracle=render_data.get("miracle"),
    )


# ── 重新导出（仅公开 API） ───────────────────────────────────────────────────

__all__ = [
    "FishingContext",
    "SimulationResult",
    "StepResult",
    "_apply_duoduo",
    "_cap_rarity",
    "_catch_fish_with_buffs",
    "_compute_duoduo_quantity",
    "calculate_display_probabilities",
    "check_fishing_status",
    "deserialize_fish_caught",
    "handle_fishing_result",
    "merge_fish",
    "process_fish_results",
    "render_scene",
    "save_fish_to_backpack",
    "serialize_fish_caught",
    "settle_fishing_step",
    "simulate_fishing_loop",
    "start_fishing",
    "stop_fishing",
    "use_time_potion_settle",
]
