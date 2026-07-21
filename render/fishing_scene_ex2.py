"""钓鱼场景 EX2：WebGL2 高级局部变形与黑洞效果测试。"""

import asyncio
import base64
from pathlib import Path

from nonebot.log import logger
from nonebot_plugin_htmlrender import html_to_pic

from .base import SCENES_IMAGES_PATH, TEMPLATES_PATH, render_template

_EX2_CASES = (
    ("3", "强局部上下差异扭曲", "warp", "非线性波束 · 上压下拉"),
    ("8", "漩涡吸入", "vortex", "旋转逆映射 · 向心吸入"),
    ("13", "黑洞引力透镜", "blackhole", "事件视界 · 引力环 · RGB 色散"),
)
_TEMPLATES_FILE_URL = f"file:///{TEMPLATES_PATH.as_posix()}"


def _find_scene_by_id(scene_id: str) -> Path | None:
    """按场景 ID 查找正式场景图。"""
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


def _build_scene_ex2_cases() -> list[dict[str, str]]:
    cases = []
    for index, (scene_id, title, effect, detail) in enumerate(_EX2_CASES, start=1):
        scene_file = _find_scene_by_id(scene_id)
        if scene_file is None:
            raise FileNotFoundError(f"缺少 EX2 测试场景图：{scene_id}")
        cases.append(
            {
                "index": str(index),
                "title": title,
                "effect": effect,
                "detail": detail,
                "scene_uri": (
                    "data:image/png;base64,"
                    + base64.b64encode(scene_file.read_bytes()).decode("ascii")
                ),
            }
        )
    return cases


async def _render_ex2_html(html: str, width: int) -> bytes:
    """等待页面完成 shader/降级绘制后截图，并保留 htmlrender 降级链。"""
    try:
        from zhenxun.services.renderer import engine_manager

        engine = await engine_manager.get_engine()
        return await engine.render(
            html,
            TEMPLATES_PATH,
            viewport={"width": width, "height": 10},
            wait=350,
        )
    except Exception as exc:
        logger.warning(f"EX2 PlaywrightEngine 渲染失败，回退到 html_to_pic: {exc}")
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                return await html_to_pic(
                    html,
                    wait=1400,
                    template_path=_TEMPLATES_FILE_URL,
                    viewport={"width": width, "height": 10},
                )
            except Exception as fallback_exc:
                last_error = fallback_exc
                logger.warning(
                    f"EX2 降级截图失败 (尝试 {attempt + 1}/3): {fallback_exc}"
                )
                if attempt < 2:
                    await asyncio.sleep(1 + attempt)
        assert last_error is not None
        raise last_error


async def render_fishing_scene_ex2_test() -> bytes:
    """单张截图展示局部扭曲、漩涡吸入和黑洞透镜/视界/色散。"""
    width = 420
    html = render_template(
        "fishing_scene_ex2.html",
        body_bg="#03050d",
        width=width,
        cases=_build_scene_ex2_cases(),
    )
    return await _render_ex2_html(html, width)
