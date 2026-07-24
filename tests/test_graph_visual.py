"""在 pytest 环境中生成白商列表 HTML，验证视觉效果。"""
import json
from pathlib import Path

from zhenxun.plugins.zhenxun_plugin_fishing.constants import RARITY_COLORS
from zhenxun.plugins.zhenxun_plugin_fishing.render.base import (
    gradient_bg,
    render_template,
)

OUT_DIR = Path(r"c:\Users\Administrator\.trae-cn\work\6a62baabd6700100ef34b48a")


class TestListRender:
    """生成白商列表 HTML 用于视觉验证。"""

    def test_generate_list_html(self):
        now_items = [
            {
                "pay_fish": [
                    {"name": "鲤鱼", "rarity": "N", "location_name": "浅水区"},
                    {"name": "鲶鱼", "rarity": "N", "location_name": "浅水区"},
                ],
                "get_groups": [
                    {"rarity": "UR", "location_name": "浅水区", "names": ["小鲫鱼"]},
                ],
            },
            {
                "pay_fish": [
                    {"name": "金鱼", "rarity": "SSR", "location_name": "深水区"},
                ],
                "get_groups": [
                    {"rarity": "UR", "location_name": "深水区", "names": ["黑鱼"]},
                    {"rarity": "UR", "location_name": "急流区", "names": ["刀鱼"]},
                ],
            },
        ]
        possible_items = [
            {
                "pay_label": "深海区 UTR",
                "pay_rarity": "UTR",
                "get_groups": [
                    {"rarity": "UTR", "location_name": "深海区", "names": ["鲨鱼", "旗鱼"]},
                ],
            },
        ]
        html = render_template(
            "white_market_list.html",
            body_bg=gradient_bg("blue"),
            width=700,
            has_data=True,
            now_items_json=json.dumps(now_items, ensure_ascii=False),
            possible_items_json=json.dumps(possible_items, ensure_ascii=False),
            rarity_colors_json=json.dumps(RARITY_COLORS, ensure_ascii=False),
        )
        html_path = OUT_DIR / "white_market_list_test.html"
        html_path.write_text(html, encoding="utf-8")
        print(f"\nHTML saved to: {html_path}")
        assert "wm-title" in html
        assert "nodes_json" not in html

    def test_generate_list_empty(self):
        html = render_template(
            "white_market_list.html",
            body_bg=gradient_bg("blue"),
            width=700,
            has_data=False,
            now_items_json="[]",
            possible_items_json="[]",
            rarity_colors_json=json.dumps(RARITY_COLORS, ensure_ascii=False),
        )
        assert "wm-empty" in html
        assert "暂无交换记录" in html
