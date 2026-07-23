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
        layout = fs._parse_scene_layout("15-云鲸庭-S@longline_50")
        assert layout["mode"] == "heights"
        assert layout["heights"] == [50]
        assert layout["effects"] == ["longline"]

    def test_tracks_with_longline(self):
        layout = fs._parse_scene_layout("15-云鲸庭-S@longline+T@10,80_40,85")
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
        assert fs._is_foreground_scene_file(tmp_path / "15-云鲸庭-fg.png")
        assert fs._is_foreground_scene_file(tmp_path / "15-云鲸庭_fg.png")
        assert not fs._is_foreground_scene_file(tmp_path / "15-云鲸庭-S@longline+T@23.7,70.8_43.3,80.7_62,79.4_83,68.7+T@11.8,67.8_19.3,72.6+T@87.7,63.1_98.7,58.4.png")

    def test_find_scene_skips_foreground(self, monkeypatch, tmp_path: Path):
        bg = tmp_path / "15-云鲸庭-S@longline+T@23.7,70.8_43.3,80.7_62,79.4_83,68.7+T@11.8,67.8_19.3,72.6+T@87.7,63.1_98.7,58.4.png"
        fg = tmp_path / "15-云鲸庭-fg.png"
        bg.write_bytes(b"bg")
        fg.write_bytes(b"fg")
        monkeypatch.setattr(fs, "SCENES_IMAGES_PATH", tmp_path)
        loc = SimpleNamespace(id="15", name="云鲸庭")
        found, layout = fs._find_scene_file(loc)
        assert found == bg
        assert layout["effects"] == ["longline"]

    def test_find_foreground_file(self, monkeypatch, tmp_path: Path):
        bg = tmp_path / "15-云鲸庭-S@longline+T@23.7,70.8_43.3,80.7_62,79.4_83,68.7+T@11.8,67.8_19.3,72.6+T@87.7,63.1_98.7,58.4.png"
        fg = tmp_path / "15-云鲸庭-fg.png"
        bg.write_bytes(b"bg")
        fg.write_bytes(b"fg")
        monkeypatch.setattr(fs, "SCENES_IMAGES_PATH", tmp_path)
        loc = SimpleNamespace(id="15", name="云鲸庭")
        assert fs._find_foreground_file(loc) == fg


class TestLonglineActorView:
    def test_longline_preserves_top_and_sets_fields(self, tmp_path: Path):
        img = tmp_path / "skin.png"
        img.write_bytes(b"x")
        skin_h = 100.0
        y_offset = -10
        view = fs._actor_view(
            img,
            "Tester",
            (40.0, skin_h),
            (100.0, 70.0),
            y_offset,
            True,
            effects=["longline"],
        )
        assert view["special"] == "longline"
        body_h = skin_h * 0.60
        assert view["body_h"] == pytest.approx(body_h)
        # normal top = y_offset + skin_h; longline top = line_base + body_h
        assert view["line_base"] + view["body_h"] == pytest.approx(y_offset + skin_h)
        assert view["line_img_height_pct"] == pytest.approx(1000.0)
        assert view["line_img_top_pct"] == pytest.approx(-600.0)

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

        bg = tmp_path / "15-云鲸庭-S@longline+T@23.7,70.8_43.3,80.7_62,79.4_83,68.7+T@11.8,67.8_19.3,72.6+T@87.7,63.1_98.7,58.4.png"
        fg = tmp_path / "15-云鲸庭-fg.png"
        bg.write_bytes(b"bg")
        fg.write_bytes(b"fg")
        monkeypatch.setattr(render_base, "SCENES_IMAGES_PATH", tmp_path)
        found = render_base._find_location_image_path("云鲸庭")
        assert found == bg
