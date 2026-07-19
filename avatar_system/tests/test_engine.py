"""
头像生成引擎测试
"""

import colorsys
import sys
from pathlib import Path

import pytest
from PIL import Image

# 确保 avatar_system 包可被导入
_BASE = Path(__file__).resolve().parent.parent.parent  # fishing 目录
if str(_BASE) not in sys.path:
    sys.path.insert(0, str(_BASE))

from avatar_system.engine import (
    apply_color,
    composite_layers,
    generate_avatar,
    generate_from_config,
    hex_to_hsv,
)


def _resources_dir() -> Path:
    return Path(__file__).parent.parent / "resources"


def test_hex_to_hsv_red():
    """测试红色转 HSV。"""
    h, s, v = hex_to_hsv("#FF0000")
    assert abs(h - 0.0) < 0.01
    assert abs(s - 1.0) < 0.01
    assert abs(v - 1.0) < 0.01


def test_hex_to_hsv_white():
    """测试白色转 HSV。"""
    h, s, v = hex_to_hsv("#FFFFFF")
    assert abs(v - 1.0) < 0.01
    assert abs(s - 0.0) < 0.01


def test_apply_color_preserves_value():
    """
    测试 HSV 明度保留着色：着色后像素明度(V)应保持不变。
    """
    # 创建灰度渐变测试图：从黑到白
    img = Image.new("RGBA", (10, 1))
    pixels = []
    for i in range(10):
        gray = int(i / 9 * 255)
        pixels.append((gray, gray, gray, 255))
    img.putdata(pixels)

    # 着红色
    result = apply_color(img, "#FF0000")

    # 检查着色前后明度(V)一致
    orig_data = img.getdata()
    res_data = result.getdata()
    for orig, res in zip(orig_data, res_data):
        orig_h, orig_s, orig_v = colorsys.rgb_to_hsv(
            orig[0] / 255.0, orig[1] / 255.0, orig[2] / 255.0
        )
        res_h, res_s, res_v = colorsys.rgb_to_hsv(
            res[0] / 255.0, res[1] / 255.0, res[2] / 255.0
        )
        assert abs(orig_v - res_v) < 0.02, (
            f"明度应保持不变: 原始V={orig_v:.4f}, 着色后V={res_v:.4f}"
        )
        # 非黑色像素的饱和度应为目标色饱和度
        if orig_v > 0.01:
            assert abs(res_s - 1.0) < 0.02, (
                f"饱和度应为1.0: 实际={res_s:.4f}"
            )


def test_apply_color_preserves_alpha():
    """测试透明像素不被修改。"""
    img = Image.new("RGBA", (4, 1))
    img.putdata([
        (255, 255, 255, 0),    # 透明
        (255, 255, 255, 128),  # 半透明
        (128, 128, 128, 255),  # 灰色不透明
        (0, 0, 0, 255),        # 黑色不透明
    ])

    result = apply_color(img, "#0000FF")

    res_data = list(result.getdata())
    # 透明像素不变
    assert res_data[0] == (255, 255, 255, 0)
    # 半透明像素 alpha 不变
    assert res_data[1][3] == 128
    assert res_data[2][3] == 255
    assert res_data[3][3] == 255


def test_apply_color_target_color():
    """测试着色结果的颜色与目标色一致（对于白色像素应完全变为目标色）。"""
    # 纯白色图片
    img = Image.new("RGBA", (3, 3), (255, 255, 255, 255))
    result = apply_color(img, "#00FF00")

    # 所有像素应该都是绿色
    for px in result.getdata():
        assert px[0] == 0
        assert px[1] == 255
        assert px[2] == 0
        assert px[3] == 255


def test_composite_layers():
    """测试图层叠加：上层应覆盖下层。"""
    # 底图：全红
    bottom = Image.new("RGBA", (4, 4), (255, 0, 0, 255))
    # 顶图：右上角 2x2 蓝色
    top = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    for y in range(2):
        for x in range(2, 4):
            top.putpixel((x, y), (0, 0, 255, 255))

    result = composite_layers([bottom, top], canvas_size=(4, 4))
    # 左上角 (0,0) 应为红色
    assert result.getpixel((0, 0)) == (255, 0, 0, 255)
    # 右上角 (3,1) 应为蓝色
    assert result.getpixel((3, 1)) == (0, 0, 255, 255)
    # 左下角 (0,3) 应为红色
    assert result.getpixel((0, 3)) == (255, 0, 0, 255)


def test_generate_and_save():
    """
    端到端测试：使用1.png作为通用素材，着色后合成并保存。
    由于所有素材还未绘制，这里用1.png分别作为 hair/clothes/rod 来验证流程。
    """
    from avatar_system.engine import save_avatar

    # 复制1.png到素材目录用于测试
    player_png = (
        Path(__file__).parent.parent.parent
        / "resources" / "images" / "player" / "1.png"
    )
    if not player_png.exists():
        pytest.skip("1.png 不存在，跳过集成测试")

    target_img = _resources_dir() / "hair" / "hair_default.png"
    target_img2 = _resources_dir() / "clothes" / "clothes_default.png"
    target_img3 = _resources_dir() / "rod" / "rod_default.png"

    # 如果尚未复制素材，使用1.png做测试
    import shutil

    if not target_img.exists():
        shutil.copy(str(player_png), str(target_img))
    if not target_img2.exists():
        shutil.copy(str(player_png), str(target_img2))
    if not target_img3.exists():
        shutil.copy(str(player_png), str(target_img3))

    avatar = generate_avatar(
        resources_dir=_resources_dir(),
        hair="hair_default",
        hair_color="#FFD700",  # 金色
        clothes="clothes_default",
        clothes_color="#FF4444",  # 红色
        rod="rod_default",
        rod_color="#8B4513",  # 棕色
    )

    assert avatar.size == (22, 61)
    assert avatar.mode == "RGBA"

    # 保存到 output
    output_path = Path(__file__).parent.parent / "output" / "test_gold_red.png"
    save_avatar(avatar, output_path)
    assert output_path.exists()
    print(f"测试图片已保存到: {output_path}")


def test_generate_from_config():
    """测试从 JSON 配置批量生成。"""
    config_path = Path(__file__).parent.parent / "configs" / "default.json"
    output_dir = Path(__file__).parent.parent / "output"

    # 确保测试素材存在
    player_png = (
        Path(__file__).parent.parent.parent
        / "resources" / "images" / "player" / "1.png"
    )
    if not player_png.exists():
        pytest.skip("1.png 不存在，跳过集成测试")

    import shutil

    for subdir, name in [("hair", "hair_default"), ("clothes", "clothes_default"), ("rod", "rod_default")]:
        target = _resources_dir() / subdir / f"{name}.png"
        if not target.exists():
            shutil.copy(str(player_png), str(target))

    results = generate_from_config(
        config_path=config_path,
        resources_dir=_resources_dir(),
        output_dir=output_dir,
    )

    assert len(results) == 2  # default 和 blue_look
    assert all(p.exists() for p in results.values())
    print(f"配置生成完成: {results}")