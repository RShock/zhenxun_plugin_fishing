"""S2 挖矿渲染：共享像素素材与动态游戏数据。"""

from __future__ import annotations

from .base import gradient_bg, render_html, render_template
from .s2_assets import get_fatfish_image_src, get_s2_icon_src, get_s2_image_src

_PIXEL_DIGITS = {
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"),
    "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"),
    "7": ("111", "001", "001", "001", "001"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "111"),
}


def pixel_level_src(level: int) -> str:
    """生成每个数字 3x5 像素的等级徽标。"""
    import base64

    digits = str(max(0, int(level)))
    width = len(digits) * 4 - 1
    rects = []
    for offset, digit in enumerate(digits):
        for y, row in enumerate(_PIXEL_DIGITS.get(digit, _PIXEL_DIGITS["0"])):
            for x, bit in enumerate(row):
                if bit == "1":
                    rects.append(f"<rect x='{offset * 4 + x}' y='{y}' width='1' height='1'/>")
    svg = (
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='5' "
        f"viewBox='0 0 {width} 5'><g fill='%23fff8d6'>{''.join(rects)}</g></svg>"
    )
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


async def render_mining_help() -> bytes:
    html = render_template(
        "s2_mining_help.html",
        body_bg=gradient_bg("peach"),
        width=720,
        s2_image=get_s2_image_src,
        fatfish_image=get_fatfish_image_src,
    )
    return await render_html(html, 720)


async def render_mining_main(state: dict, delta: dict, helper_name: str = "大肥鱼") -> bytes:
    # 计算显示用字段
    data = state  # 简化：直接传 state，前端取 depth/targetDepth 等
    # 时代名
    try:
        from ..s2_mining import _load_game_data
        gd = _load_game_data()
        # 简化：按 depth 找当前 era
        era_name = gd["eras"][0]["name"]
        done = 0
        for era in gd["eras"]:
            if state["depth"] >= float(era["unlockDepth"]):
                era_name = era["name"]
                done += 1
            else:
                break
        completed_eras = done
    except Exception:
        era_name = "原始时代"
        completed_eras = 0
    # 下一项可购
    try:
        from ..s2_mining import _shop_entries, _cost_for, _available
        entries = _shop_entries(state)
        # 找最便宜可购
        affordable = [e for e in entries if e["can"]]
        if affordable:
            affordable.sort(key=lambda e: e["cost"])
            nxt = affordable[0]
            next_name = nxt["name"]
            next_lv = nxt["lv"] + 1
            next_cost = nxt["cost"]
            next_key = nxt["key"]
        else:
            # 找下一个待解锁（时代/前置）
            nxt = next((e for e in entries if not e["unlocked"]), None)
            if nxt:
                next_name = nxt["name"]
                next_lv = nxt["lv"] + 1
                next_cost = nxt["cost"]
                next_key = nxt["key"]
            else:
                next_name = "暂无可建"
                next_lv = 0
                next_cost = 0
                next_key = None
    except Exception:
        next_name = "分岔矿道"
        next_lv = 3
        next_cost = 760
        next_key = "split_tunnel"

    # 速率
    try:
        from ..s2_mining import _income_rate, _depth_rate
        income_rate = _income_rate(state)
        depth_rate = _depth_rate(state)
    except Exception:
        income_rate = 8
        depth_rate = 25
    planet_minutes = round((state.get("real_last_tick", 0) - state.get("startTime", 0)) / 60, 1) if state.get("startTime") else 0
    html = render_template(
        "s2_mining_main.html",
        body_bg=gradient_bg("peach"),
        width=720,
        state=state,
        delta=delta,
        helper_name=helper_name,
        era_name=era_name,
        completed_eras=completed_eras,
        next_name=next_name,
        next_lv=next_lv,
        next_cost=next_cost,
        next_icon=get_s2_icon_src(next_key) if next_key else get_s2_image_src("icon_empty"),
        s2_image=get_s2_image_src,
        fatfish_image=get_fatfish_image_src,
        income_rate=income_rate,
        depth_rate=depth_rate,
        planet_minutes=planet_minutes,
    )
    return await render_html(html, 720)


async def render_mining_status(state: dict, delta: dict) -> bytes:
    from ..s2_mining import _load_game_data

    levels = state.get("levels", {})
    rows = []
    for spec in _load_game_data().get("upgrades", []):
        level = int(levels.get(spec["key"], 0))
        if level <= 0:
            continue
        rows.append({
            "name": spec.get("name", spec["key"]),
            "level": level,
            "max": int(spec.get("maxLevel", level)),
            "icon": get_s2_icon_src(spec["key"]),
            "pixel_level": pixel_level_src(level),
        })
    html = render_template(
        "s2_mining_status.html",
        body_bg=gradient_bg("peach"),
        width=720,
        state=state,
        delta=delta,
        rows=rows,
        s2_image=get_s2_image_src,
        fatfish_image=get_fatfish_image_src,
    )
    return await render_html(html, 720)


async def render_mining_shop(state: dict, rows: list[dict], page: int, pages: int) -> bytes:
    html = render_template(
        "s2_mining_shop.html",
        body_bg=gradient_bg("peach"),
        width=720,
        state=state,
        rows=rows,
        page=page,
        pages=pages,
        total=len(rows) + (pages - 1) * 6,  # 近似总数，前端仅展示
        s2_tech=get_s2_icon_src,
        s2_image=get_s2_image_src,
    )
    # 修正 total 为真实总数，需传入
    # 重新渲染一次带正确的 total（上面 len(rows) 不准）
    # 为简化，直接在外层计算 total 并替换
    return await render_html(html, 720)


async def render_shop_with_total(state: dict, rows: list[dict], page: int, pages: int, total: int) -> bytes:
    html = render_template(
        "s2_mining_shop.html",
        body_bg=gradient_bg("peach"),
        width=720,
        state=state,
        rows=rows,
        page=page,
        pages=pages,
        total=total,
        s2_tech=get_s2_icon_src,
        s2_image=get_s2_image_src,
    )
    return await render_html(html, 720)
