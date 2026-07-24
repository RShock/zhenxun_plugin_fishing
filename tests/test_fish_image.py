"""鱼图片查找逻辑测试。

重点覆盖 11 图及以后的星空钓场鱼：图片命名为 {location_id}-{鱼名}.png
（如 11-奶冠鲤.png）。早期 _find_fish_image_path 的兜底循环仅遍历 1-10，
导致这些鱼在背包/展示框（不传 location_id 的场景）中因找不到图片而退化
为 🐟 占位符。
"""
import pytest

from zhenxun.plugins.zhenxun_plugin_fishing.render import base as render_base
from zhenxun.plugins.zhenxun_plugin_fishing.render.base import (
    _find_fish_image_path,
    get_fish_image_src,
)


@pytest.fixture(autouse=True)
def _clear_image_cache():
    """每个用例前后清空图片查找缓存，避免用例间污染。"""
    render_base._fish_image_cache.clear()
    yield
    render_base._fish_image_cache.clear()


class TestFishImageLookup:
    def test_starry_fish_found_without_location_id(self):
        """11 图鱼在无 location_id 时应命中兜底循环找到图片。"""
        path = _find_fish_image_path("奶冠鲤")
        assert path is not None, "11 图鱼奶冠鲤应能找到图片"
        assert path.name == "11-奶冠鲤.png"

    def test_starry_fish_image_src_nonempty(self):
        """get_fish_image_src 对 11 图鱼应返回非空 src。"""
        src = get_fish_image_src("奶冠鲤")
        assert src, "11 图鱼奶冠鲤的图片 src 不应为空"

    def test_location_12_fish_found_without_location_id(self):
        """12 图鱼在无 location_id 时应找到图片。"""
        path = _find_fish_image_path("环月飞鱼")
        assert path is not None
        assert path.name == "12-环月飞鱼.png"

    def test_low_location_fish_still_found(self):
        """回归保护：1 图鱼无 location_id 仍能找到图片。"""
        path = _find_fish_image_path("小鲫鱼")
        assert path is not None
        assert path.name == "1-小鲫鱼.png"

    def test_starry_fish_with_explicit_location_id(self):
        """传 location_id=11 时应通过 location_num 路径找到图片。"""
        path = _find_fish_image_path("奶冠鲤", location_id="11")
        assert path is not None
        assert path.name == "11-奶冠鲤.png"

    def test_nonexistent_fish_returns_none(self):
        """不存在的鱼应返回 None。"""
        path = _find_fish_image_path("不存在的鱼12345")
        assert path is None

    def test_build_fish_item_data_starry_image(self):
        """build_fish_item_data 对 11 图鱼应填充非空 img_src（背包渲染路径）。"""
        from zhenxun.plugins.zhenxun_plugin_fishing.render.base import (
            build_fish_item_data,
        )

        data = build_fish_item_data("奶冠鲤", rarity="UTR", count=1)
        assert data["img_src"], "背包渲染时 11 图鱼 img_src 不应为空"
