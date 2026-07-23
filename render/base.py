import asyncio
import hashlib
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from nonebot.log import logger
from nonebot_plugin_htmlrender import html_to_pic

from ..config import RARITY_COLORS, RARITY_NAMES, ConfigManager

DEBUG_TEMP_DIR = Path(__file__).parent.parent / "temp"

DEBUG_MODE = False

_fish_image_cache: dict[str, str] = {}

TEMPLATES_PATH = Path(__file__).parent.parent / "templates"
FISH_IMAGES_PATH = Path(__file__).parent.parent / "resources" / "images" / "fish"
SCENES_IMAGES_PATH = Path(__file__).parent.parent / "resources" / "images" / "scenes"
PLAYER_IMAGES_PATH = Path(__file__).parent.parent / "resources" / "images" / "player"
ITEMS_IMAGES_PATH = Path(__file__).parent.parent / "resources" / "images" / "items"
FONTS_PATH = Path(__file__).parent.parent / "resources" / "fonts"

_UTR_STARRY_SRC: str | None = None


def _get_utr_starry_src() -> str:
    global _UTR_STARRY_SRC
    if _UTR_STARRY_SRC is None:
        path = ITEMS_IMAGES_PATH / "utr背景.png"
        _UTR_STARRY_SRC = path.as_uri() if path.exists() else ""
    return _UTR_STARRY_SRC


_jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_PATH)),
    autoescape=True,
    trim_blocks=True,
    lstrip_blocks=True,
)

_HYPIXEL_FONT_PATH = FONTS_PATH / "HYPixel11pxU-2.ttf"

HYPIXEL_FONT_URI = _HYPIXEL_FONT_PATH.as_uri() if _HYPIXEL_FONT_PATH.exists() else ""

FONT_FAMILY = "'HYPixel','Microsoft YaHei','Segoe UI Emoji',sans-serif"
FONT_FAMILY_DEFAULT = "'Microsoft YaHei','Segoe UI Emoji',sans-serif"


def _build_font_face_css() -> str:
    css = ""
    if HYPIXEL_FONT_URI:
        css += f"""
@font-face {{
    font-family: "HYPixel";
    src: url("{HYPIXEL_FONT_URI}") format("truetype");
    font-weight: normal;
    font-style: normal;
    font-display: swap;
}}
"""
    return css


FONT_FACE_CSS = _build_font_face_css()

GRADIENTS = {
    "blue": "linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)",
    "purple": "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
    "green": "linear-gradient(135deg, #11998e 0%, #38ef7d 100%)",
    "orange": "linear-gradient(135deg, #f5af19 0%, #f12711 100%)",
    "pink": "linear-gradient(135deg, #a8edea 0%, #fed6e3 100%)",
    "peach": "linear-gradient(135deg, #ffecd2 0%, #fcb69f 100%)",
}


def gradient_bg(gradient_name: str) -> str:
    return GRADIENTS.get(gradient_name, GRADIENTS["blue"])


_TEMPLATES_FILE_URL = f"file:///{TEMPLATES_PATH.as_posix()}"

_rendered_html_map: dict[str, str] = {}
_MAX_HTML_CACHE = 128


async def render_html(html: str, width: int = 300) -> bytes:
    try:
        from zhenxun.services.renderer import engine_manager

        engine = await engine_manager.get_engine()
        result = await engine.render(
            html,
            TEMPLATES_PATH,
            viewport={"width": width, "height": 10},
        )
    except Exception as e:
        logger.warning(f"PlaywrightEngine 渲染失败，回退到 html_to_pic: {e}")
        last_error = None
        for attempt in range(3):
            try:
                result = await html_to_pic(
                    html,
                    wait=500,
                    template_path=_TEMPLATES_FILE_URL,
                    viewport={"width": width, "height": 10},
                )
                break
            except Exception as e2:
                last_error = e2
                logger.warning(f"渲染截图失败 (尝试 {attempt + 1}/3): {e2}")
                if attempt < 2:
                    await asyncio.sleep(1 + attempt)
        else:
            raise last_error

    h = hashlib.md5(result, usedforsecurity=False).hexdigest()
    if len(_rendered_html_map) >= _MAX_HTML_CACHE:
        _rendered_html_map.clear()
    _rendered_html_map[h] = html
    return result


def pop_cached_html(image_hash: str) -> str | None:
    return _rendered_html_map.pop(image_hash, None)


def render_template(
    template_name: str,
    body_bg: str,
    width: int = 400,
    **kwargs,
) -> str:
    template = _jinja_env.get_template(template_name)
    return template.render(
        hypixel_font_uri=HYPIXEL_FONT_URI,
        body_bg=body_bg,
        width=width,
        rarity_colors=RARITY_COLORS,
        rarity_names=RARITY_NAMES,
        **kwargs,
    )


def _find_fish_image_path(fish_name: str, location_id: str = None) -> Path | None:
    cache_key = f"fish:{fish_name}:{location_id or ''}"
    if cache_key in _fish_image_cache:
        return Path(_fish_image_cache[cache_key])

    item_names = [f"{fish_name}.png"]
    if fish_name == "特级小鱼干":
        item_names.append("小鱼干.png")
    if fish_name == "猫抓板木板":
        item_names.append("猫抓板.png")
    if fish_name == "彩虹逗猫棒":
        item_names.append("逗猫棒废案.png")
    for item_name in item_names:
        for item_dir in [
            ITEMS_IMAGES_PATH,
            Path(__file__).parent.parent / "resources" / "images" / "event1",
        ]:
            item_path = item_dir / item_name
            if item_path.exists():
                _fish_image_cache[cache_key] = str(item_path)
                return item_path

    if location_id and location_id.upper() == "S1":
        path = FISH_IMAGES_PATH / f"s1-{fish_name}.png"
        if path.exists():
            _fish_image_cache[cache_key] = str(path)
            return path

    # 直接按鱼名查找（如流星鱼.png）
    for direct_path in [
        FISH_IMAGES_PATH / f"{fish_name}.png",
    ]:
        if direct_path.exists():
            _fish_image_cache[cache_key] = str(direct_path)
            return direct_path

    locations = ConfigManager.get_locations()
    location_num = None

    if location_id:
        for i, loc in enumerate(locations, 1):
            if loc.id == location_id:
                location_num = i
                break

    if location_num:
        path = FISH_IMAGES_PATH / f"{location_num}-{fish_name}.png"
        if path.exists():
            _fish_image_cache[cache_key] = str(path)
            return path

    for i in range(1, 11):
        path = FISH_IMAGES_PATH / f"{i}-{fish_name}.png"
        if path.exists():
            _fish_image_cache[cache_key] = str(path)
            return path

    # S1 活动鱼全局兜底（背包/展示框等无 location_id 场景）
    s1_path = FISH_IMAGES_PATH / f"s1-{fish_name}.png"
    if s1_path.exists():
        _fish_image_cache[cache_key] = str(s1_path)
        return s1_path

    return None


def get_fish_image_src(fish_name: str, location_id: str = None) -> str:
    path = _find_fish_image_path(fish_name, location_id)
    if not path:
        return ""
    try:
        import base64

        data = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:image/png;base64,{data}"
    except Exception:
        return path.as_uri()


def build_fish_item_data(
    fish_name: str,
    rarity: str = None,
    count: int = None,
    location_id: str = None,
    show_count: bool = True,
    fish_base_price: int = None,
    extra_info: str = "",
    new_count: int = 0,
    numeric_id: str | int = None,
    locked: bool = False,
    is_cat_eaten: bool = False,
    show_utr_starry: bool = True,
) -> dict:
    color = RARITY_COLORS.get(rarity, "#808080") if rarity else "#808080"
    img_src = "" if is_cat_eaten else get_fish_image_src(fish_name, location_id)
    count_text = f"x{count}" if show_count and count else ""
    if new_count and new_count > 0:
        count_text = f"x{count}(+{new_count})" if count_text else f"(+{new_count})"
    is_utr = rarity == "UTR"
    utr_starry_src = ""
    if is_utr and fish_name != "展示木框" and not is_cat_eaten and show_utr_starry:
        utr_starry_src = _get_utr_starry_src()
    return {
        "name": fish_name,
        "color": color,
        "img_src": img_src,
        "count_text": count_text,
        "numeric_id": numeric_id,
        "locked": locked,
        "price": fish_base_price,
        "is_utr": is_utr,
        "utr_starry_src": utr_starry_src,
        "is_cat_eaten": is_cat_eaten,
    }


def build_meteor_fish_items(meteor_fish_numbers: list[int] | None) -> list[dict]:
    if not meteor_fish_numbers:
        return []
    from ..core.starry_system import format_starry_fish_id, score_starry_fish

    items = []
    for num in meteor_fish_numbers:
        if int(num) <= 999_999:
            scored = score_starry_fish(num)
            # Use meteor-fish texture; display name keeps the score.
            item = build_fish_item_data(
                "流星鱼",
                "UTR",
                show_count=False,
                numeric_id=format_starry_fish_id(num),
                show_utr_starry=False,
            )
            item["name"] = f"流星鱼[{scored.display_score}分]"
            items.append(item)
        else:
            items.append(
                build_fish_item_data(
                    "流星鱼",
                    "UTR",
                    show_count=False,
                    numeric_id=str(num),
                    show_utr_starry=False,
                )
            )
    return items


def _parse_feature_span_positions(span: str) -> list[int]:
    """Parse 1-based span text into 0-based indices.

    Supports continuous ranges and sparse lists: ``1-3``, ``1,2,6``, ``1-2,6``.
    """
    positions: list[int] = []
    raw = (span or "").strip()
    if not raw:
        return positions
    for part in raw.split(","):
        token = part.strip()
        if not token:
            continue
        try:
            if "-" in token:
                start_s, end_s = token.split("-", 1)
                start = int(start_s) - 1
                end = int(end_s)
                for idx in range(max(0, start), min(6, end)):
                    positions.append(idx)
            else:
                idx = int(token) - 1
                if 0 <= idx < 6:
                    positions.append(idx)
        except (TypeError, ValueError):
            continue
    return positions


# 数字标记染色按奖池分档，颜色与鱼稀有度一致：
# 无奖励→N，低级→R，中级→SR，高级→SSR，究极→UR
_REWARD_POOL_RARITY = {
    "none": "N",
    "low": "R",
    "middle": "SR",
    "high": "SSR",
    "ultimate": "UR",
}


def _pool_mark_rarity(reward_pool: str = "", display_score: int = 0) -> str:
    """Map starry reward pool / score to fish rarity color key.

    奖池：无→N、低→R、中→SR、高→SSR、究极→UR；展示分 ≥15 升为 UTR。
    """
    if int(display_score or 0) >= 15:
        return "UTR"
    key = (reward_pool or "none").strip().lower()
    return _REWARD_POOL_RARITY.get(key, "N")


def _contrast_text_color(bg_hex: str) -> str:
    """Pick light/dark text for a solid rarity background."""
    raw = (bg_hex or "").lstrip("#")
    if len(raw) != 6:
        return "#1f2937"
    try:
        red = int(raw[0:2], 16)
        green = int(raw[2:4], 16)
        blue = int(raw[4:6], 16)
    except ValueError:
        return "#1f2937"
    # 与鱼卡稀有色搭配：亮底（如 SSR 金）用深字，其余用白字
    luminance = (0.299 * red + 0.587 * green + 0.114 * blue) / 255
    return "#1f2937" if luminance > 0.62 else "#ffffff"


def _starry_feature_digit_styles(
    features,
    id_text: str = "",
    reward_pool: str = "",
    display_score: int = 0,
) -> tuple[list[bool], list[str | None], list[str | None]]:
    """Return matched mask + pool-tier backgrounds for each digit.

    命中位由番型 span 决定（屁胡只标同号）；背景色按奖池，≥15 分用 UTR 色。
    """
    mask = [False] * 6
    for feature in features or []:
        span = getattr(feature, "span", "") or ""
        for idx in _parse_feature_span_positions(span):
            mask[idx] = True

    rarity = _pool_mark_rarity(reward_pool, display_score=display_score)
    color = RARITY_COLORS.get(rarity, RARITY_COLORS.get("N", "#808080"))
    text_color = _contrast_text_color(color)
    colors: list[str | None] = [color if hit else None for hit in mask]
    texts: list[str | None] = [text_color if hit else None for hit in mask]
    return mask, colors, texts


def _starry_feature_digit_mask(
    features,
    id_text: str = "",
    reward_pool: str = "",
    display_score: int = 0,
) -> list[bool]:
    """Mark digits covered by matched feature spans (1-based inclusive)."""
    mask, _colors, _texts = _starry_feature_digit_styles(
        features,
        id_text,
        reward_pool=reward_pool,
        display_score=display_score,
    )
    return mask


def build_starry_fish_cards(records: list[dict] | None) -> list[dict]:
    if not records:
        return []
    from ..core.starry_system import REWARD_POOL_NAMES, band, score_starry_fish

    cards = []
    for record in records:
        fish_id = str(record.get("id", "0")).zfill(6)
        scored = score_starry_fish(fish_id)
        # 展馆记录保存的是入馆时的分数快照；番型规则更新后，旧快照会过期。
        # 展示页始终按当前规则重算，避免老展品长期显示旧分数和旧番型。
        # 这里只修正展示，不追补历史奖池奖励或累计努力值。
        feature_names = [feature.display_name for feature in scored.features]
        digit_matched, digit_colors, digit_text_colors = _starry_feature_digit_styles(
            scored.features,
            scored.id_text,
            reward_pool=scored.reward_pool,
            display_score=scored.display_score,
        )
        # 卡片外壳按奖池稀有度染色（与普通鱼 fish-item 同色系）；命中位数字另有标记。
        pool_rarity = _pool_mark_rarity(
            scored.reward_pool, display_score=scored.display_score
        )
        pool_color = RARITY_COLORS.get(pool_rarity, RARITY_COLORS.get("N", "#808080"))
        cards.append(
            {
                "id": scored.id_text,
                "digits": list(scored.id_text),
                "digit_matched": digit_matched,
                "digit_colors": digit_colors,
                "digit_text_colors": digit_text_colors,
                "pool_rarity": pool_rarity,
                "pool_color": pool_color,
                "score": round(scored.raw_score, 3),
                "display_score": scored.display_score,
                "band": band(scored.display_score),
                "reward_pool": REWARD_POOL_NAMES.get(
                    scored.reward_pool,
                    scored.reward_pool,
                ),
                "features": feature_names[:6],
                "feature_summary": " / ".join(feature_names[:3])
                if feature_names
                else "无显著番型",
                "location_id": record.get("location_id", ""),
            }
        )
    cards.sort(key=lambda item: (item["score"], int(item["id"])), reverse=True)
    return cards

def build_fish_list_data(
    fish_caught: list[tuple],
    location_id: str = None,
    new_fish: list[tuple] | None = None,
    cat_eaten_fish: list[tuple] | None = None,
) -> list[dict]:
    from ..config import calculate_fish_price

    rarity_order = {"UTR": 0, "UR": 1, "SSR": 2, "SR": 3, "R": 4, "N": 5}

    new_fish_map: dict[tuple[str, str], int] = {}
    if new_fish:
        for fish in new_fish:
            if isinstance(fish, tuple) and len(fish) == 3:
                f, rarity, count = fish
                key = (f.id, rarity)
                new_fish_map[key] = new_fish_map.get(key, 0) + count

    merged = {}
    for fish in fish_caught:
        if isinstance(fish, tuple) and len(fish) == 3:
            f, rarity, count = fish
            key = (f.id, rarity, False)
            if key in merged:
                merged[key] = (f, rarity, merged[key][2] + count, False)
            else:
                merged[key] = (f, rarity, count, False)
        else:
            lock_icon = "🔒" if getattr(fish, "locked", False) else ""
            key = (fish.fish_name, fish.rarity, False)
            if key in merged:
                old_f, old_r, old_c, old_cat = merged[key]
                merged[key] = (old_f, old_r, old_c + fish.count, old_cat)
            else:
                merged[key] = (fish.fish_name, fish.rarity, fish.count, False)

    if cat_eaten_fish:
        for fish, rarity, count in cat_eaten_fish:
            key = (fish.id, rarity, True)
            if key in merged:
                old_f, old_r, old_c, old_cat = merged[key]
                merged[key] = (old_f, old_r, old_c + count, True)
            else:
                merged[key] = (fish, rarity, count, True)

    sorted_fish = sorted(
        merged.values(),
        key=lambda x: (
            rarity_order.get(x[1], 5),
            ConfigManager.get_fish_order(x[0].id if hasattr(x[0], "id") else x[0]),
        ),
    )

    result = []
    for entry in sorted_fish:
        f, rarity, count, is_cat_eaten = entry
        if isinstance(f, str):
            fish_name = f
            key = (fish_name, rarity)
            nc = 0 if is_cat_eaten else new_fish_map.get(key, 0)
            result.append(
                build_fish_item_data(
                    fish_name,
                    rarity,
                    count,
                    location_id,
                    new_count=nc,
                    is_cat_eaten=is_cat_eaten,
                )
            )
        else:
            key = (f.id, rarity)
            nc = 0 if is_cat_eaten else new_fish_map.get(key, 0)
            material_prefix = "cat_park_material:"
            if f.id.startswith(material_prefix):
                material_name = f.id.removeprefix(material_prefix)
                result.append(
                    build_fish_item_data(
                        material_name,
                        rarity,
                        count,
                        location_id,
                        new_count=nc,
                        fish_base_price=None,
                        is_cat_eaten=is_cat_eaten,
                    )
                )
                continue
            price = calculate_fish_price(f, rarity, 0) if not is_cat_eaten else None
            result.append(
                build_fish_item_data(
                    f.id,
                    rarity,
                    count,
                    location_id,
                    new_count=nc,
                    fish_base_price=price,
                    is_cat_eaten=is_cat_eaten,
                )
            )

    return result


def _find_location_image_path(location_name: str) -> Path | None:
    """缩略图/天气卡用场景图：只用背景，跳过 *-fg 前景层。"""
    if not SCENES_IMAGES_PATH.exists():
        return None

    for f in SCENES_IMAGES_PATH.iterdir():
        if f.suffix != ".png":
            continue
        stem = f.stem
        # 前景层仅用于完整钓鱼场景叠图，缩略图不展示
        if stem.endswith("-fg") or stem.endswith("_fg"):
            continue
        parts = stem.split("-")
        if len(parts) >= 2 and parts[1] == location_name:
            return f
    return None


def get_location_image_src(location_name: str) -> str:
    path = _find_location_image_path(location_name)
    if path:
        return path.as_uri()
    return ""


def save_debug_output(
    tag: str,
    user_id: str,
    html_content: str,
    image_data: bytes,
    timing_info: dict[str, float],
) -> None:
    global DEBUG_MODE
    if not DEBUG_MODE:
        return
    try:
        debug_dir = DEBUG_TEMP_DIR
        debug_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        base_name = f"{ts}_{tag}_{user_id}"
        html_path = debug_dir / f"{base_name}.html"
        img_path = debug_dir / f"{base_name}.png"
        txt_path = debug_dir / f"{base_name}.txt"
        html_path.write_text(html_content, encoding="utf-8")
        img_path.write_bytes(image_data)
        lines = [f"tag: {tag}", f"user_id: {user_id}", f"time: {ts}"]
        for k, v in timing_info.items():
            lines.append(f"{k}: {v:.3f}s")
        txt_path.write_text("\n".join(lines), encoding="utf-8")
    except Exception as e:
        logger.warning(f"[debug] 写入失败: {e}")
