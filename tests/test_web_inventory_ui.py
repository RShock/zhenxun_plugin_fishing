from pathlib import Path
from types import SimpleNamespace

from zhenxun.plugins.zhenxun_plugin_fishing.web.api import (
    _build_display_slots,
    _fish_web_meta,
    _starry_web_records,
)


PLUGIN_DIR = Path(__file__).resolve().parents[1]
INDEX_HTML = PLUGIN_DIR / "web" / "static" / "index.html"


def test_display_slots_are_always_complete_ten_slots():
    slots = _build_display_slots(
        [{"slot": 2, "fish_name": "鲤鱼"}, {"slot": 10, "fish_name": "草鱼"}]
    )

    assert [slot["slot"] for slot in slots] == list(range(1, 11))
    assert slots[0]["empty"] is True
    assert slots[1]["fish_name"] == "鲤鱼"
    assert slots[9]["fish_name"] == "草鱼"


def test_fish_web_meta_uses_player_facing_minimum_level():
    first_scene = _fish_web_meta("小鲫鱼")
    second_scene = _fish_web_meta("草鱼")

    assert first_scene["difficulty"] == 0
    assert first_scene["minimum_level"] == 1
    assert second_scene["difficulty"] == 1
    assert second_scene["minimum_level"] == 2


def test_starry_web_records_include_image_number_score_and_legacy_items():
    user = SimpleNamespace(
        starry_fish=[{"id": "123456", "location_id": "11"}],
        starry_exhibition=[{"id": "654321", "location_id": "12"}],
    )
    items = [{"item_id": "36786820", "item_type": "meteor_fish", "count": 2}]

    backpack, exhibition = _starry_web_records(user, items)

    assert len(backpack) == 3
    assert len(exhibition) == 1
    assert sum(record.get("legacy", False) for record in backpack) == 2
    legacy_records = [record for record in backpack if record.get("legacy")]
    assert all(record["numeric_id"] == "786820" for record in legacy_records)
    assert all(isinstance(record["display_score"], int) for record in legacy_records)
    assert all(isinstance(record["score"], float) for record in legacy_records)
    for record in backpack + exhibition:
        assert record["image_url"].endswith("%E6%B5%81%E6%98%9F%E9%B1%BC.png")
        assert len(record["numeric_id"]) == 6
        assert isinstance(record["display_score"], int)
        assert isinstance(record["score"], float)


def test_web_ui_uses_element_plus_and_responsive_scroll_contract():
    html = INDEX_HTML.read_text(encoding="utf-8")
    element_plus_js = (
        PLUGIN_DIR
        / "web"
        / "static"
        / "vendor"
        / "element-plus"
        / "index.full.min.js"
    ).read_text(encoding="utf-8")

    assert "https://unpkg.com" not in html
    assert "sourceMappingURL" not in element_plus_js
    assert 'src="/vendor/vue/vue.global.prod.js"' in html
    assert 'href="/vendor/element-plus/index.css"' in html
    assert 'src="/vendor/element-plus/index.full.min.js"' in html
    assert (PLUGIN_DIR / "web" / "static" / "vendor" / "vue" / "vue.global.prod.js").is_file()
    assert (PLUGIN_DIR / "web" / "static" / "vendor" / "element-plus" / "index.css").is_file()
    assert (PLUGIN_DIR / "web" / "static" / "vendor" / "element-plus" / "index.full.min.js").is_file()
    assert ").use(ElementPlus).mount('#app')" in html
    assert "<el-dialog v-model=\"fishModal\"" in html
    assert "<el-card v-for=\"f in visibleFishCards\"" in html
    assert "<el-select v-model=\"market.targetLocation\"" in html
    assert "<el-select v-model=\"market.targetRarity\"" in html
    assert "<el-checkbox v-model=\"market.smart\">智能黑商</el-checkbox>" in html
    assert "@click=\"submitMarket\">确认交换" in html
    assert 'v-model="whiteMarketModal"' in html
    assert "@click=\"openWhiteMarket\">白商" in html
    assert "`白商交换 ${whiteMarketPayment.value.numeric_id} ${whiteMarketTargetId.value}`" in html
    assert "今日白商次数已用完" in html
    assert "fish-exchange-mark" in html
    assert "<small>ID</small>" in html
    assert "<small>价格</small>" in html
    assert "地图 / 对应最低等级" in html
    assert "来源鱼（当前鱼）" in html
    assert "完整 10 槽" in html
    assert "药水与道具" in html
    assert "width: 100%; min-width: 0; max-width: 100%" in html
    assert "overflow-x:auto; flex-wrap:nowrap" in html
    assert "overflow-x: hidden; overflow-y: auto" in html
