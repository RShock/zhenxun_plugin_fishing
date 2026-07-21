from pathlib import Path

import pytest

from zhenxun.plugins.zhenxun_plugin_fishing.render import fishing_scene_ex


def test_build_scene_ex_cases_uses_four_distinct_scenes(monkeypatch, tmp_path: Path):
    for scene_id in range(1, 5):
        (tmp_path / f"{scene_id}-测试场景-{scene_id}.png").touch()
    monkeypatch.setattr(fishing_scene_ex, "SCENES_IMAGES_PATH", tmp_path)

    cases = fishing_scene_ex._build_scene_ex_cases()

    assert [case["effect"] for case in cases] == [
        "skew",
        "perspective",
        "mesh",
        "displacement",
    ]
    assert len({case["scene_uri"] for case in cases}) == 4


@pytest.mark.asyncio
async def test_render_fishing_scene_ex_test_builds_single_long_screenshot(monkeypatch):
    captured = {}
    cases = [
        {"index": str(i), "title": f"测试{i}", "effect": effect, "scene_uri": f"file:///{i}.png"}
        for i, effect in enumerate(("skew", "perspective", "mesh", "displacement"), 1)
    ]

    monkeypatch.setattr(fishing_scene_ex, "_build_scene_ex_cases", lambda: cases)
    monkeypatch.setattr(
        fishing_scene_ex,
        "render_template",
        lambda template, **kwargs: captured.update(template=template, **kwargs) or "<html></html>",
    )

    async def fake_render_html(html, width):
        captured["html"] = html
        captured["render_width"] = width
        return b"png"

    monkeypatch.setattr(fishing_scene_ex, "render_html", fake_render_html)

    assert await fishing_scene_ex.render_fishing_scene_ex_test() == b"png"
    assert captured["template"] == "fishing_scene_ex.html"
    assert captured["cases"] == cases
    assert captured["width"] == captured["render_width"] == 360
