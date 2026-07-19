"""
avatar_system - 像素角色换装系统

通过 HSV 明度保留法对白色素材进行着色，再按图层叠加合成最终头像。

用法示例:

    from pathlib import Path
    from avatar_system import generate_avatar, save_avatar

    base = Path(__file__).parent  # avatar_system 目录

    # 方式1: 直接调用生成
    avatar = generate_avatar(
        resources_dir=base / "resources",
        hair="hair_long",
        hair_color="#FFD700",
        clothes="shirt_01",
        clothes_color="#FF4444",
        rod="rod_default",
    )
    save_avatar(avatar, base / "output" / "player_gold_red.png")

    # 方式2: 从 JSON 配置批量生成
    from avatar_system import generate_from_config
    results = generate_from_config(
        config_path=base / "configs" / "default.json",
        resources_dir=base / "resources",
        output_dir=base / "output",
    )
"""

from .engine import (
    apply_color,
    composite_layers,
    generate_avatar,
    generate_from_config,
    load_combo_config,
    save_avatar,
)

__all__ = [
    "apply_color",
    "composite_layers",
    "generate_avatar",
    "generate_from_config",
    "load_combo_config",
    "save_avatar",
]