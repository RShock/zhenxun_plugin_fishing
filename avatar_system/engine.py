"""
头像生成引擎 - 核心渲染模块

通过 HSV 明度保留法替换颜色 + 图层叠加合成。
素材使用白-灰-黑表现明暗，运行时保留明度(V)，仅替换色相(H)和饱和度(S)。

为什么用 HSV 而不是 HLS：
  HLS 中 L=1.0（白色）时无论 H/S 如何变化结果都是白色，无法对白色素材着色。
  HSV 中 V=1.0 配合目标 S 可以正确产生目标颜色，且 V 随素材明暗变化自然产生阴影。
"""

import colorsys
import json
from pathlib import Path
from typing import Optional

from PIL import Image


def hex_to_hsv(hex_color: str) -> tuple[float, float, float]:
    """将 #RRGGBB 颜色转为 HSV 三元组 (H, S, V)，值范围 0-1。"""
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0
    return colorsys.rgb_to_hsv(r, g, b)


def apply_color(image: Image.Image, target_hex: str) -> Image.Image:
    """
    对图片中所有非透明像素应用 HSV 明度保留着色：
    - 保留原像素的明度（V），确保阴影/高光关系不变
    - 替换为目标颜色的色相（H）和饱和度（S）

    素材使用白→灰→黑来画明暗：
      白色像素(V≈1.0) → 目标颜色最亮版本
      灰色像素(V≈0.5) → 目标颜色中等明暗
      黑色像素(V≈0.0) → 黑色（最深阴影）
    """
    if not target_hex:
        return image.copy()

    target_h, target_s, _target_v = hex_to_hsv(target_hex)
    pixels = list(image.getdata())
    new_pixels = []

    for px in pixels:
        r, g, b, a = px
        if a == 0:
            new_pixels.append(px)
            continue

        r_n, g_n, b_n = r / 255.0, g / 255.0, b / 255.0
        _h, _s, source_v = colorsys.rgb_to_hsv(r_n, g_n, b_n)
        nr, ng, nb = colorsys.hsv_to_rgb(target_h, target_s, source_v)
        new_pixels.append((
            int(nr * 255),
            int(ng * 255),
            int(nb * 255),
            a,
        ))

    result = Image.new("RGBA", image.size)
    result.putdata(new_pixels)
    return result


def composite_layers(
    layers: list[Image.Image],
    canvas_size: tuple[int, int] = (22, 61),
) -> Image.Image:
    """
    按顺序叠加图层，生成最终头像。

    Args:
        layers: 按从底到顶排列的图层列表
        canvas_size: 画布尺寸 (宽, 高)

    Returns:
        合成后的 RGBA 图片
    """
    canvas = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    for layer in layers:
        canvas.paste(layer, (0, 0), layer)
    return canvas


def generate_avatar(
    resources_dir: Path,
    hair: Optional[str] = None,
    hair_color: Optional[str] = None,
    clothes: Optional[str] = None,
    clothes_color: Optional[str] = None,
    rod: Optional[str] = None,
    rod_color: Optional[str] = None,
    canvas_size: tuple[int, int] = (22, 61),
    draw_order: Optional[list[str]] = None,
) -> Image.Image:
    """
    根据组合参数生成角色头像。

    Args:
        resources_dir: 素材根目录，下面应有 hair/ clothes/ rod/ 子目录
        hair: 头发素材文件名（不含路径，不含扩展名）
        hair_color: 头发颜色 #RRGGBB，None 表示不着色
        clothes: 衣服素材文件名
        clothes_color: 衣服颜色
        rod: 鱼竿素材文件名
        rod_color: 鱼竿颜色
        canvas_size: 画布尺寸
        draw_order: 绘制顺序，默认 ["rod", "clothes", "hair"]（从底到顶）

    Returns:
        合成后的 RGBA 头像图片
    """
    if draw_order is None:
        draw_order = ["rod", "clothes", "hair"]

    layer_config = {
        "hair": (hair, hair_color, "hair"),
        "clothes": (clothes, clothes_color, "clothes"),
        "rod": (rod, rod_color, "rod"),
    }

    layers = []
    for layer_name in draw_order:
        filename, color, subdir = layer_config[layer_name]
        if filename is None:
            continue

        filepath = resources_dir / subdir / f"{filename}.png"
        if not filepath.exists():
            raise FileNotFoundError(f"素材文件不存在: {filepath}")

        img = Image.open(filepath).convert("RGBA")
        if color:
            img = apply_color(img, color)
        layers.append(img)

    return composite_layers(layers, canvas_size)


def load_combo_config(config_path: Path) -> dict:
    """加载组合配置文件（JSON）。"""
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_avatar(image: Image.Image, output_path: Path) -> None:
    """保存头像为 PNG 文件，自动创建父目录。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, "PNG")


def generate_from_config(
    config_path: Path,
    resources_dir: Path,
    output_dir: Path,
    combo_id: Optional[str] = None,
) -> dict[str, Path]:
    """
    根据 JSON 配置文件批量生成头像。

    配置文件格式:
    {
        "canvas_size": [22, 61],
        "draw_order": ["rod", "clothes", "hair"],
        "combos": {
            "my_combo": {
                "hair": "hair_long",
                "hair_color": "#FFD700",
                "clothes": "shirt_01",
                "clothes_color": "#FF4444",
                "rod": "rod_default"
            }
        }
    }

    Args:
        config_path: JSON 配置文件路径
        resources_dir: 素材目录
        output_dir: 输出目录
        combo_id: 指定生成某个组合，None 则生成全部

    Returns:
        {combo_id: output_filepath} 映射
    """
    config = load_combo_config(config_path)
    canvas_size = tuple(config.get("canvas_size", [22, 61]))
    draw_order = config.get("draw_order", ["rod", "clothes", "hair"])
    combos = config.get("combos", {})

    if combo_id:
        if combo_id not in combos:
            raise KeyError(f"组合 '{combo_id}' 不存在于配置文件中")
        combos = {combo_id: combos[combo_id]}

    results = {}
    for cid, combo in combos.items():
        avatar = generate_avatar(
            resources_dir=resources_dir,
            hair=combo.get("hair"),
            hair_color=combo.get("hair_color"),
            clothes=combo.get("clothes"),
            clothes_color=combo.get("clothes_color"),
            rod=combo.get("rod"),
            rod_color=combo.get("rod_color"),
            canvas_size=canvas_size,
            draw_order=draw_order,
        )

        # 生成文件名: 组合描述
        parts = [cid]
        output_name = f"{cid}.png"
        output_path = output_dir / output_name
        save_avatar(avatar, output_path)
        results[cid] = output_path

    return results