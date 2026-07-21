"""钓鱼场景图片变形能力的超管测试渲染。"""

from pathlib import Path

from .base import SCENES_IMAGES_PATH, render_html, render_template

_SCENE_TESTS = (
    ("1", "CSS 斜切 / 基础变换", "skew"),
    ("2", "CSS 整体透视", "perspective"),
    ("3", "上下不同扭曲", "mesh"),
    ("4", "水波热浪位移", "displacement"),
)


def _find_scene_by_id(scene_id: str) -> Path | None:
    """按场景 ID 查找正式场景图，避免把天气叠加图加入测试。"""
    if not SCENES_IMAGES_PATH.exists():
        return None
    prefix = f"{scene_id}-"
    return next(
        (
            path
            for path in sorted(SCENES_IMAGES_PATH.iterdir())
            if path.suffix.lower() == ".png" and path.stem.startswith(prefix)
        ),
        None,
    )


def _build_scene_ex_cases() -> list[dict[str, str]]:
    """构建固定的四项测试数据，每项使用不同的正式场景图。"""
    cases = []
    for index, (scene_id, title, effect) in enumerate(_SCENE_TESTS, start=1):
        scene_file = _find_scene_by_id(scene_id)
        if scene_file is None:
            raise FileNotFoundError(f"缺少测试场景图：{scene_id}")
        cases.append(
            {
                "index": str(index),
                "title": title,
                "effect": effect,
                "scene_uri": scene_file.as_uri(),
            }
        )
    return cases


async def render_fishing_scene_ex_test() -> bytes:
    """一次截图纵向展示四张不同场景图及四种变形效果。"""
    width = 360
    html = render_template(
        "fishing_scene_ex.html",
        body_bg="#07141f",
        width=width,
        cases=_build_scene_ex_cases(),
    )
    return await render_html(html, width)
