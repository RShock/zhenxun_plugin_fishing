"""
core/ — 钓鱼核心逻辑包。

避免在此处实现业务逻辑；各模块只负责单一关注点：
  context   — 数据结构（FishingContext, StepResult）
  engine    — 钓鱼模拟循环 + 捕获判定
  probability — 概率分布计算
  cat       — 猫天气系统
  bait      — 鱼饵管理
  scene     — 场景渲染数据组装
  actions   — 外部命令入口（start, stop, check, settle）
  result    — 鱼获处理（保存、成就、展示）
  potion    — 时光药水结算
"""

from ..services import auto_display_fish
from .actions import (
    check_fishing_status,
    settle_fishing_step,
    start_fishing,
    stop_fishing,
)
from .context import (
    FishingContext,
    SimulationResult,
    StepResult,
    deserialize_fish_caught,
    merge_fish,
    serialize_fish_caught,
)
from .engine import simulate_fishing_loop
from .potion import use_time_potion_settle
from .probability import calculate_display_probabilities
from .result import (
    add_fish_to_user,
    check_and_apply_achievements,
    process_fish_results,
    save_fish_to_backpack,
)
from .scene import render_scene

__all__ = [
    "FishingContext",
    "SimulationResult",
    "StepResult",
    "add_fish_to_user",
    "auto_display_fish",
    "calculate_display_probabilities",
    "check_and_apply_achievements",
    "check_fishing_status",
    "deserialize_fish_caught",
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
