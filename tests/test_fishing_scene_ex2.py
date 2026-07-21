from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

from zhenxun.plugins.zhenxun_plugin_fishing.render import fishing_scene_ex2


def test_build_scene_ex2_cases_uses_distinct_scenes(monkeypatch, tmp_path: Path):
    for scene_id in (3, 8, 13):
        (tmp_path / f"{scene_id}-测试场景.png").write_bytes(bytes([scene_id]))
    monkeypatch.setattr(fishing_scene_ex2, "SCENES_IMAGES_PATH", tmp_path)

    cases = fishing_scene_ex2._build_scene_ex2_cases()

    assert [case["effect"] for case in cases] == ["warp", "vortex", "blackhole"]
    assert len({case["scene_uri"] for case in cases}) == 3
    assert all(case["scene_uri"].startswith("data:image/png;base64,") for case in cases)


def test_ex2_template_contains_shader_sync_and_fallback():
    template = (
        Path(fishing_scene_ex2.__file__).parent.parent
        / "templates"
        / "fishing_scene_ex2.html"
    ).read_text(encoding="utf-8")

    for marker in (
        "#version 300 es",
        "fragmentSource",
        "safeSample",
        "u_mode",
        "WebGL2 shader",
        "Canvas2D 降级",
        "gl.finish()",
        "__FISHING_EX2_READY__",
        "requestAnimationFrame",
    ):
        assert marker in template
    assert "safeSample(base+dir*chroma).r" in template
    assert "safeSample(base-dir*chroma).b" in template
    assert "smoothstep(horizon-.018,horizon+.018,r)" in template


@pytest.mark.asyncio
async def test_render_fishing_scene_ex2_builds_single_screenshot(monkeypatch):
    captured = {}
    cases = [
        {
            "index": str(i),
            "title": effect,
            "effect": effect,
            "detail": "detail",
            "scene_uri": f"file:///{i}.png",
        }
        for i, effect in enumerate(("warp", "vortex", "blackhole"), 1)
    ]
    monkeypatch.setattr(fishing_scene_ex2, "_build_scene_ex2_cases", lambda: cases)
    monkeypatch.setattr(
        fishing_scene_ex2,
        "render_template",
        lambda template, **kwargs: captured.update(template=template, **kwargs)
        or "<html></html>",
    )

    async def fake_render(html, width):
        captured.update(html=html, render_width=width)
        return b"png"

    monkeypatch.setattr(fishing_scene_ex2, "_render_ex2_html", fake_render)

    assert await fishing_scene_ex2.render_fishing_scene_ex2_test() == b"png"
    assert captured["template"] == "fishing_scene_ex2.html"
    assert captured["cases"] == cases
    assert captured["width"] == captured["render_width"] == 420


@pytest.mark.asyncio
async def test_ex2_renderer_passes_wait_to_playwright(monkeypatch):
    captured = {}

    class Engine:
        async def render(self, html, base_path, **options):
            captured.update(html=html, base_path=base_path, **options)
            return b"png"

    async def get_engine():
        return Engine()

    renderer_module = ModuleType("zhenxun.services.renderer")
    renderer_module.engine_manager = SimpleNamespace(get_engine=get_engine)
    monkeypatch.setitem(sys.modules, "zhenxun.services.renderer", renderer_module)

    assert await fishing_scene_ex2._render_ex2_html("<html/>", 420) == b"png"
    assert captured["wait"] >= 350
    assert captured["viewport"] == {"width": 420, "height": 10}
