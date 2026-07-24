"""在 pytest 环境中生成白商有向图 HTML 和 PNG，验证视觉效果。"""
import json
from pathlib import Path

from zhenxun.plugins.zhenxun_plugin_fishing.constants import RARITY_COLORS
from zhenxun.plugins.zhenxun_plugin_fishing.render.base import (
    gradient_bg,
    render_html,
    render_template,
)

OUT_DIR = Path(r"c:\Users\Administrator\.trae-cn\work\6a62baabd6700100ef34b48a")

MOCK_NODES = [
    {"id": "鲤鱼_N", "name": "鲤鱼", "rarity": "N", "location_name": "浅水区", "location_id": "1"},
    {"id": "草鱼_R", "name": "草鱼", "rarity": "R", "location_name": "浅水区", "location_id": "1"},
    {"id": "鲫鱼_SR", "name": "鲫鱼", "rarity": "SR", "location_name": "浅水区", "location_id": "1"},
    {"id": "金鱼_SSR", "name": "金鱼", "rarity": "SSR", "location_name": "深水区", "location_id": "2"},
    {"id": "黑鱼_UR", "name": "黑鱼", "rarity": "UR", "location_name": "深水区", "location_id": "2"},
    {"id": "鲶鱼_N", "name": "鲶鱼", "rarity": "N", "location_name": "深水区", "location_id": "2"},
    {"id": "鳗鱼_SR", "name": "鳗鱼", "rarity": "SR", "location_name": "急流区", "location_id": "3"},
    {"id": "鲈鱼_SSR", "name": "鲈鱼", "rarity": "SSR", "location_name": "急流区", "location_id": "3"},
    {"id": "刀鱼_UR", "name": "刀鱼", "rarity": "UR", "location_name": "急流区", "location_id": "3"},
    {"id": "鲨鱼_UTR", "name": "鲨鱼", "rarity": "UTR", "location_name": "深海区", "location_id": "4"},
    {"id": "旗鱼_UR", "name": "旗鱼", "rarity": "UR", "location_name": "深海区", "location_id": "4"},
    {"id": "海龟_SSR", "name": "海龟", "rarity": "SSR", "location_name": "深海区", "location_id": "4"},
    {"id": "小鲫鱼_UR", "name": "小鲫鱼", "rarity": "UR", "location_name": "浅水区", "location_id": "1"},
    {"id": "小鲫鱼_N", "name": "小鲫鱼", "rarity": "N", "location_name": "浅水区", "location_id": "1"},
    {"id": "热带鱼_R", "name": "热带鱼", "rarity": "R", "location_name": "珊瑚区", "location_id": "5"},
    {"id": "小丑鱼_SR", "name": "小丑鱼", "rarity": "SR", "location_name": "珊瑚区", "location_id": "5"},
]

MOCK_EDGES = [
    {"source": "鲤鱼_N", "target": "草鱼_R", "category": "now"},
    {"source": "草鱼_R", "target": "鲫鱼_SR", "category": "now"},
    {"source": "鲫鱼_SR", "target": "金鱼_SSR", "category": "possible"},
    {"source": "金鱼_SSR", "target": "黑鱼_UR", "category": "now"},
    {"source": "黑鱼_UR", "target": "鲶鱼_N", "category": "possible"},
    {"source": "鳗鱼_SR", "target": "鲈鱼_SSR", "category": "now"},
    {"source": "鲈鱼_SSR", "target": "刀鱼_UR", "category": "now"},
    {"source": "刀鱼_UR", "target": "鲨鱼_UTR", "category": "possible"},
    {"source": "旗鱼_UR", "target": "海龟_SSR", "category": "now"},
    {"source": "小鲫鱼_N", "target": "小鲫鱼_UR", "category": "now"},
    {"source": "小鲫鱼_UR", "target": "小鲫鱼_N", "category": "possible"},
    {"source": "热带鱼_R", "target": "小丑鱼_SR", "category": "now"},
    {"source": "小丑鱼_SR", "target": "海龟_SSR", "category": "possible"},
]


class TestGraphRender:
    """生成有向图 HTML 和 PNG 用于视觉验证。"""

    def test_generate_graph_html(self):
        html = render_template(
            "white_market_graph.html",
            body_bg=gradient_bg("blue"),
            width=700,
            nodes_json=json.dumps(MOCK_NODES, ensure_ascii=False),
            edges_json=json.dumps(MOCK_EDGES, ensure_ascii=False),
            rarity_colors_json=json.dumps(RARITY_COLORS, ensure_ascii=False),
            has_data=True,
        )
        html_path = OUT_DIR / "white_market_graph_test.html"
        html_path.write_text(html, encoding="utf-8")
        print(f"\nHTML saved to: {html_path}")
        # SVG由JS动态生成，原始HTML中只有JS代码引用了<svg字符串
        assert "wmg-graph" in html
        assert "nodes_json" not in html  # Jinja变量应已被替换

    def test_generate_graph_empty(self):
        html = render_template(
            "white_market_graph.html",
            body_bg=gradient_bg("blue"),
            width=700,
            nodes_json="[]",
            edges_json="[]",
            rarity_colors_json=json.dumps(RARITY_COLORS, ensure_ascii=False),
            has_data=False,
        )
        assert "wmg-empty" in html
        assert "暂无交换记录" in html
