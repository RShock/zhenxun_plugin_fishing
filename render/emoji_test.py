import base64

from .base import (
    FISH_IMAGES_PATH,
    ITEMS_IMAGES_PATH,
    gradient_bg,
    render_html,
    render_template,
)


def _image_to_base64(path) -> str:
    try:
        data = path.read_bytes()
        return f"data:image/png;base64,{base64.b64encode(data).decode('ascii')}"
    except Exception:
        return ""


def _get_utr_test_data() -> dict:
    starry_path = ITEMS_IMAGES_PATH / "utr背景.png"
    fish_path = None
    try:
        for p in FISH_IMAGES_PATH.iterdir():
            if p.suffix == ".png" and "鲤鱼" in p.stem:
                fish_path = p
                break
        if fish_path is None:
            for p in FISH_IMAGES_PATH.iterdir():
                if p.suffix == ".png":
                    fish_path = p
                    break
    except Exception:
        pass

    starry_uri = starry_path.as_uri() if starry_path.exists() else ""
    fish_uri = fish_path.as_uri() if fish_path else ""
    starry_b64 = _image_to_base64(starry_path) if starry_path.exists() else ""
    fish_b64 = _image_to_base64(fish_path) if fish_path else ""
    fish_name = fish_path.stem if fish_path else "(无测试鱼图)"

    return {
        "starry_uri": starry_uri,
        "fish_uri": fish_uri,
        "starry_b64": starry_b64,
        "fish_b64": fish_b64,
        "fish_name": fish_name,
    }


def _get_emoji_data() -> dict:
    return {
        "emoji_sections": [
            {
                "title": "Unicode 6.0 (2010) — 基础emoji",
                "emojis": [
                    {"char": "😀", "name": "笑脸", "code": "U+1F600"},
                    {"char": "🐟", "name": "鱼", "code": "U+1F41F"},
                    {"char": "🎣", "name": "钓鱼", "code": "U+1F3A3"},
                    {"char": "⚓", "name": "锚", "code": "U+2693"},
                    {"char": "🔒", "name": "锁", "code": "U+1F512"},
                    {"char": "💰", "name": "钱袋", "code": "U+1F4B0"},
                ],
            },
            {
                "title": "Unicode 8.0 (2015) — 肤色修饰符",
                "emojis": [
                    {"char": "🤔", "name": "思考", "code": "U+1F914"},
                    {"char": "🤣", "name": "笑哭", "code": "U+1F923"},
                    {"char": "👋🏻", "name": "挥手浅肤", "code": "U+1F44B U+1F3FB"},
                    {"char": "👋🏽", "name": "挥手中肤", "code": "U+1F44B U+1F3FD"},
                    {"char": "👋🏿", "name": "挥手深肤", "code": "U+1F44B U+1F3FF"},
                ],
            },
            {
                "title": "Unicode 10.0 (2017)",
                "emojis": [
                    {"char": "🤩", "name": "好极了", "code": "U+1F929"},
                    {"char": "🥳", "name": "庆祝", "code": "U+1F973"},
                    {"char": "🧠", "name": "大脑", "code": "U+1F9E0"},
                ],
            },
            {
                "title": "Unicode 12.0 (2019)",
                "emojis": [
                    {"char": "🧟", "name": "僵尸", "code": "U+1F9DF"},
                    {"char": "🦩", "name": "火烈鸟", "code": "U+1F9A9"},
                    {"char": "🧑", "name": "成人", "code": "U+1F9D1"},
                ],
            },
            {
                "title": "Unicode 13.0 (2020) — 🪝所在版本",
                "emojis": [
                    {"char": "🪝", "name": "鱼钩", "code": "U+1FA9D"},
                    {"char": "🦭", "name": "海豹", "code": "U+1F9AD"},
                    {"char": "🪄", "name": "魔法棒", "code": "U+1FA84"},
                    {"char": "🪅", "name": "皮纳塔", "code": "U+1FA85"},
                    {"char": "🪆", "name": "套娃", "code": "U+1FA86"},
                    {"char": "🪡", "name": "缝纫针", "code": "U+1FAA1"},
                    {"char": "🪢", "name": "绳结", "code": "U+1FAA2"},
                ],
            },
            {
                "title": "Unicode 14.0 (2021)",
                "emojis": [
                    {"char": "🪸", "name": "珊瑚", "code": "U+1FAB8"},
                    {"char": "🫠", "name": "融化", "code": "U+1FAE0"},
                    {"char": "🫡", "name": "敬礼", "code": "U+1FAE1"},
                    {"char": "🫶", "name": "比心手", "code": "U+1FAF6"},
                ],
            },
            {
                "title": "Unicode 15.0 (2022)",
                "emojis": [
                    {"char": "🩷", "name": "粉心", "code": "U+1FA77"},
                    {"char": "🩵", "name": "浅蓝心", "code": "U+1FA75"},
                    {"char": "🪿", "name": "鹅", "code": "U+1FABF"},
                    {"char": "🫎", "name": "驼鹿", "code": "U+1FACE"},
                ],
            },
            {
                "title": "Unicode 15.1 (2023)",
                "emojis": [
                    {"char": "🫨", "name": "震动脸", "code": "U+1FAE8"},
                    {"char": "🪇", "name": "沙锤", "code": "U+1FA87"},
                    {"char": "🪈", "name": "长笛", "code": "U+1FA88"},
                ],
            },
        ],
        "color_sections": [
            {
                "title": "ZWJ序列 (零宽连字组合)",
                "emojis": [
                    {"char": "👨‍👩‍👧", "name": "家庭", "code": "U+1F468 ZWJ U+1F469 ZWJ U+1F467"},
                    {"char": "👩‍💻", "name": "女程序员", "code": "U+1F469 ZWJ U+1F4BB"},
                    {"char": "🧑‍🚀", "name": "宇航员", "code": "U+1F9D1 ZWJ U+1F680"},
                    {"char": "👨‍❤️‍👨", "name": "男情侣", "code": "U+1F468 ZWJ U+2764 ZWJ U+1F468"},
                    {"char": "👩‍👩‍👧‍👧", "name": "四口家", "code": "U+1F469 ZWJ x3 U+1F467"},
                ],
            },
            {
                "title": "Keycap序列 & 旗帜",
                "emojis": [
                    {"char": "#️⃣", "name": "井号键", "code": "U+0023 FE0F U+20E3"},
                    {"char": "*️⃣", "name": "星号键", "code": "U+002A FE0F U+20E3"},
                    {"char": "0️⃣", "name": "零键", "code": "U+0030 FE0F U+20E3"},
                    {"char": "🇨🇳", "name": "中国旗", "code": "U+1F1E8 U+1F1F3"},
                    {"char": "🇯🇵", "name": "日本旗", "code": "U+1F1EF U+1F1F5"},
                ],
            },
            {
                "title": "肤色组合emoji",
                "emojis": [
                    {"char": "👨🏻‍💻", "name": "男程序员浅肤", "code": "U+1F468 U+1F3FB ZWJ U+1F4BB"},
                    {"char": "👩🏽‍🚀", "name": "女宇航员中肤", "code": "U+1F469 U+1F3FD ZWJ U+1F680"},
                    {"char": "🧑🏿‍🔧", "name": "技工深肤", "code": "U+1F9D1 U+1F3FF ZWJ U+1F527"},
                ],
            },
        ],
        "hook_tests": [
            {"label": "NotoColorEmoji only", "font_family": "'NotoColorEmoji'"},
            {"label": "NotoColorEmoji first", "font_family": "'NotoColorEmoji', 'Segoe UI Emoji', sans-serif"},
            {"label": "Segoe UI Emoji only", "font_family": "'Segoe UI Emoji'"},
            {"label": "sans-serif default", "font_family": "sans-serif"},
            {"label": "system default (empty)", "font_family": ""},
        ],
    }


async def render_emoji_test(custom_text: str = "") -> bytes:
    data = _get_emoji_data()
    utr_data = _get_utr_test_data()

    html = render_template(
        "emoji_test.html",
        body_bg=gradient_bg("blue"),
        width=500,
        cols=6,
        custom_text=custom_text,
        hook_tests=data["hook_tests"],
        emoji_sections=data["emoji_sections"],
        color_sections=data["color_sections"],
        **utr_data,
    )
    return await render_html(html, 500)
