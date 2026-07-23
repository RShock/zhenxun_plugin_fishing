# -*- coding: utf-8 -*-
"""Foreground discovery + S@ special render (longline) for fishing scenes."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from zhenxun.plugins.zhenxun_plugin_fishing.render import fishing_scene as fs


class TestParseSpecialAndLayout:
    def test_no_marker_passthrough(self):
        assert fs._parse_special_and_layout("50") == ([], "50")
        assert fs._parse_special_and_layout("T@1,2_3,4") == ([], "T@1,2_3,4")

    def test_longline_heights(self):
        assert fs._parse_special_and_layout("S@longline_50") == (["longline"], "50")
        assert fs._parse_special_and_layout("S@longline_50_60") == (["longline"], "50_60")

    def test_longline_tracks(self):
        assert fs._parse_special_and_layout("S@longline+T@1,2_3,4") == (
            ["longline"],
            "T@1,2_3,4",
        )

    def test_multi_effects_tracks(self):
        assert fs._parse_special_and_layout("S@longline,foo+T@10,20") == (
            ["longline", "foo"],
            "T@10,20",
        )

    def test_effects_only_defaults_height(self):
        assert fs._parse_special_and_layout("S@longline") == (["longline"], "50")


class TestParseSceneLayoutEffects:
    def test_heights_with_longline(self):
        layout = fs._parse_scene_layout("14-云鲸庭-S@longline_50")
        assert layout["mode"] == "heights"
        assert layout["heights"] == [50]
        assert layout["effects"] == ["longline"]

    def test_tracks_with_longline(self):
        layout = fs._parse_scene_layout("14-云鲸庭-S@longline+T@10,80_40,85")
        assert layout["mode"] == "tracks"
        assert layout["effects"] == ["longline"]
        assert len(layout["tracks"]) == 1
        assert layout["tracks"][0]["points"][0] == (10.0, 80.0)

    def test_plain_tracks_no_effects(self):
        layout = fs._parse_scene_layout("13-彗尾瀑-T@10,80_40,85")
        assert layout["mode"] == "tracks"
        assert layout.get("effects") == []


class TestForegroundDiscovery:
    def test_is_foreground_suffixes(self, tmp_path: Path):
        assert fs._is_foreground_scene_file(tmp_path / "14-云鲸庭-fg.png")
        assert fs._is_foreground_scene_file(tmp_path / "14-云鲸庭_fg.png")
        assert not fs._is_foreground_scene_file(tmp_path / "14-云鲸庭-S@longline+T@23.7,70.8_43.3,80.7_62,79.4_83,68.7+T@11.8,67.8_19.3,72.6+T@87.7,63.1_98.7,58.4.png")

    def test_find_scene_skips_foreground(self, monkeypatch, tmp_path: Path):
        bg = tmp_path / "14-云鲸庭-S@longline+T@23.7,70.8_43.3,80.7_62,79.4_83,68.7+T@11.8,67.8_19.3,72.6+T@87.7,63.1_98.7,58.4.png"
        fg = tmp_path / "14-云鲸庭-fg.png"
        bg.write_bytes(b"bg")
        fg.write_bytes(b"fg")
        monkeypatch.setattr(fs, "SCENES_IMAGES_PATH", tmp_path)
        loc = SimpleNamespace(id="14", name="云鲸庭")
        found, layout = fs._find_scene_file(loc)
        assert found == bg
        assert layout["effects"] == ["longline"]

    def test_find_foreground_file(self, monkeypatch, tmp_path: Path):
        bg = tmp_path / "14-云鲸庭-S@longline+T@23.7,70.8_43.3,80.7_62,79.4_83,68.7+T@11.8,67.8_19.3,72.6+T@87.7,63.1_98.7,58.4.png"
        fg = tmp_path / "14-云鲸庭-fg.png"
        bg.write_bytes(b"bg")
        fg.write_bytes(b"fg")
        monkeypatch.setattr(fs, "SCENES_IMAGES_PATH", tmp_path)
        loc = SimpleNamespace(id="14", name="云鲸庭")
        assert fs._find_foreground_file(loc) == fg


class TestLonglineAdaptiveBand:
    def _make_skin(self, tmp_path: Path, name: str, width: int, height: int, paint_rows):
        """paint_rows: dict[y] = list of x with opaque pixels."""
        from PIL import Image

        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        px = img.load()
        for y, xs in paint_rows.items():
            for x in xs:
                px[x, y] = (255, 255, 255, 255)
        path = tmp_path / name
        img.save(path)
        return path

    def test_stable_width_under_10_from_bottom(self, tmp_path: Path):
        """宽度 <10 且连续 5 行相同，自下而上取最底部 5 行。"""
        fs._LONGLINE_BAND_CACHE.clear()
        h, w = 100, 20
        paint = {y: list(range(0, 12)) for y in range(0, 50)}  # wide body
        # stable width=6 from y=60..89 (30 rows); lure wider at 90+
        for y in range(60, 90):
            paint[y] = list(range(0, 6))
        for y in range(90, 95):
            paint[y] = list(range(0, 14))
        path = self._make_skin(tmp_path, "stable6.png", w, h, paint)
        band = fs._analyze_longline_band(path)
        assert band is not None
        body_ratio, crop_ratio = band
        # bottom 5 of stable run: 85..90
        assert body_ratio == pytest.approx(0.85)
        assert crop_ratio == pytest.approx(0.90)

    def test_width_10_is_not_allowed(self, tmp_path: Path):
        """低于 10：恰好 10 像素不算。"""
        fs._LONGLINE_BAND_CACHE.clear()
        h, w = 40, 20
        paint = {y: list(range(0, 10)) for y in range(0, h)}
        path = self._make_skin(tmp_path, "ten.png", w, h, paint)
        assert fs._analyze_longline_band(path) is None

    def test_unstable_varying_width_not_matched(self, tmp_path: Path):
        """宽度虽 <10 但不稳定（每行变化）则不拉伸。"""
        fs._LONGLINE_BAND_CACHE.clear()
        h, w = 40, 20
        paint = {}
        for y in range(h):
            paint[y] = list(range(0, 1 + (y % 4)))  # 1..4 cycling
        path = self._make_skin(tmp_path, "vary.png", w, h, paint)
        assert fs._analyze_longline_band(path) is None

    def test_need_five_stable_rows(self, tmp_path: Path):
        fs._LONGLINE_BAND_CACHE.clear()
        h, w = 40, 20
        paint = {y: list(range(0, 12)) for y in range(h)}
        for y in range(30, 34):  # only 4 rows width=3
            paint[y] = [1, 2, 3]
        path = self._make_skin(tmp_path, "short.png", w, h, paint)
        assert fs._analyze_longline_band(path) is None

    def test_wide_body_like_cat_not_matched(self, tmp_path: Path):
        fs._LONGLINE_BAND_CACHE.clear()
        h, w = 20, 23
        paint = {y: list(range(0, min(w, 15))) for y in range(h)}
        path = self._make_skin(tmp_path, "catlike.png", w, h, paint)
        assert fs._analyze_longline_band(path) is None

    def test_cache_hit(self, tmp_path: Path):
        fs._LONGLINE_BAND_CACHE.clear()
        h, w = 100, 10
        paint = {y: [1] for y in range(70, 90)}
        path = self._make_skin(tmp_path, "cache.png", w, h, paint)
        a = fs._analyze_longline_band(path)
        b = fs._analyze_longline_band(path)
        assert a == b
        assert a is not None
        assert any(str(path.resolve()) in k[0] for k in fs._LONGLINE_BAND_CACHE)

    def test_actor_view_uses_adaptive_or_fallback(self, tmp_path: Path):
        fs._LONGLINE_BAND_CACHE.clear()
        h, w = 100, 20
        paint = {y: list(range(8)) for y in range(0, 60)}
        for y in range(70, 90):
            paint[y] = [5]  # stable width 1
        path = self._make_skin(tmp_path, "actor.png", w, h, paint)
        skin_h = 100.0
        y_offset = -10
        view = fs._actor_view(
            path, "T", (40.0, skin_h), (10.0, 70.0), y_offset, True, effects=["longline"]
        )
        assert view["special"] == "longline"
        assert view["line_base"] + view["body_h"] == pytest.approx(y_offset + skin_h)
        # no band -> normal
        fs._LONGLINE_BAND_CACHE.clear()
        # 宽身体且每行宽度变化，不应被识别为稳定细线
        path2 = self._make_skin(
            tmp_path,
            "noline.png",
            w,
            h,
            {y: list(range(0, 10 + (y % 3))) for y in range(h)},
        )
        view2 = fs._actor_view(
            path2, "T", (40.0, skin_h), (10.0, 70.0), y_offset, False, effects=["longline"]
        )
        assert view2["special"] == ""


class TestLonglineActorViewLegacyNames:
    def test_no_effects_normal(self, tmp_path: Path):
        img = tmp_path / "skin.png"
        img.write_bytes(b"x")
        view = fs._actor_view(
            img, "A", (22.0, 61.0), (10.0, 50.0), 0, False, effects=[]
        )
        assert view["special"] == ""
        assert "body_h" not in view


class TestLocationThumbnailSkipsForeground:
    def test_find_location_image_skips_fg(self, monkeypatch, tmp_path: Path):
        from zhenxun.plugins.zhenxun_plugin_fishing.render import base as render_base

        bg = tmp_path / "14-云鲸庭-S@longline+T@23.7,70.8_43.3,80.7_62,79.4_83,68.7+T@11.8,67.8_19.3,72.6+T@87.7,63.1_98.7,58.4.png"
        fg = tmp_path / "14-云鲸庭-fg.png"
        bg.write_bytes(b"bg")
        fg.write_bytes(b"fg")
        monkeypatch.setattr(render_base, "SCENES_IMAGES_PATH", tmp_path)
        found = render_base._find_location_image_path("云鲸庭")
        assert found == bg
