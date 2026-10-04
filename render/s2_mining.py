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

_ERA_HUES = {
    "foundation": 0,
    "industrial": 60,
    "electrical": 120,
    "modern": 180,
    "future": 240,
    "planetary": 300,
}


def pixel_level_src(level: int, complete: bool = False) -> str:
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
    color = "#58a85c" if complete else "#1c1c1c"
    svg = (
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='5' "
        f"viewBox='0 0 {width} 5'><g fill='{color}'>{''.join(rects)}</g></svg>"
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
        from ..s2_mining import _income_rate, _depth_rate, s2_format_depth, s2_format_number, s2_progress_percent
        income_rate = _income_rate(state)
        depth_rate = _depth_rate(state)
        progress_pct = s2_progress_percent(state)
    except Exception:
        income_rate = 8
        depth_rate = 25
        progress_pct = 0
        s2_format_number = lambda value: str(value)
        s2_format_depth = s2_format_number
    upgrade_rows = _main_upgrade_rows(state, entries if "entries" in locals() else [], income_rate, depth_rate, s2_format_number)
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
        progress_pct=progress_pct,
        s2_num=s2_format_number,
        s2_depth=s2_format_depth,
        upgrade_rows=upgrade_rows,
    )
    return await render_html(html, 720)


def _eta_text(minutes: float) -> str:
    if minutes <= 0:
        return "可用"
    if minutes < 1:
        return "约1分钟"
    if minutes < 60:
        return f"约{max(1, round(minutes))}分钟"
    hours = minutes / 60
    if hours < 24:
        return f"约{max(1, round(hours, 1))}小时"
    return f"约{max(1, round(hours / 24, 1))}天"


def _main_upgrade_rows(state: dict, entries: list[dict], income_rate: float, depth_rate: float, s2_num) -> list[dict]:
    """把商店压缩成主图内的双列清单，给出可购买或预计等待时间。"""
    from ..s2_mining import _load_game_data

    specs = {spec["key"]: spec for spec in _load_game_data().get("upgrades", [])}
    depth = float(state.get("depth", 0))
    credits = float(state.get("credits", 0))
    auto_keys = set(state.get("autoUnlocked", []))
    candidates = [entry for entry in entries if entry["key"] not in auto_keys and int(entry.get("lv", 0)) < int(entry.get("max", 0))]
    candidates.sort(key=lambda entry: (float(entry.get("cost", 0)), int(entry.get("idx", 0))))
    rows = []
    for entry in candidates[:3]:
        spec = specs.get(entry["key"], {})
        level = int(entry.get("lv", 0))
        maximum = int(entry.get("max", level))
        status = "已满级"
        status_class = "done"
        if level < maximum:
            if entry.get("can"):
                status = "可用"
                status_class = "ready"
            else:
                unlock_depth = float(spec.get("unlockDepth", 0))
                if depth < unlock_depth and depth_rate > 0:
                    status = _eta_text((unlock_depth - depth) / depth_rate)
                elif entry.get("reason", "").startswith("需前置"):
                    status = "需前置"
                elif credits < float(entry.get("cost", 0)) and income_rate > 0:
                    status = _eta_text((float(entry["cost"]) - credits) / income_rate)
                else:
                    status = "暂不可用"
                status_class = "wait"
        rows.append({
            "idx": entry.get("idx", 0),
            "name": entry.get("name", entry["key"]),
            "level": level,
            "max": maximum,
            "status": status,
            "status_class": status_class,
            "icon": get_s2_icon_src(entry["key"]),
            "hue": _ERA_HUES.get(str(spec.get("era", "foundation")), 0),
        })
    return rows


async def render_mining_status(state: dict, delta: dict) -> bytes:
    from ..s2_mining import _call_bridge, _load_game_data, s2_format_number, s2_progress_percent

    game_data = _load_game_data()
    try:
        status_result = await _call_bridge("status", {"snapshot": state["engine_snapshot"]})
    except Exception:
        status_result = {}
    rules = game_data.get("rules", {})
    income_mul = float(status_result.get("incomeMul", 1) or 1)
    depth_mul = float(status_result.get("depthMul", 1) or 1)
    income_rate = float(rules.get("baseCreditsPerMinute", 0)) * income_mul
    depth_rate = float(rules.get("baseDepthPerMinute", 0)) * depth_mul
    def _multiplier_text(value: float) -> str:
        text = f"{value:.2f}".rstrip("0").rstrip(".")
        return f"×{text}"
    labels = {item["key"]: item.get("name", item["key"]) for item in game_data.get("multiplierRegions", [])}
    labels.update({
        "critical": "暴击期望",
        "prestige": "永久科技倍率",
        "stellar_relay": "联合勘探",
        "opening_burst": "新星首秒大爆发",
        "completion_depth": "全科技满级深度",
    })
    bonuses = []
    for key, raw_value in (status_result.get("breakdown") or {}).items():
        value = float(raw_value)
        if value > 1.000001:
            bonuses.append({"label": labels.get(key, key), "value": _multiplier_text(value)})
    local_discount = float(status_result.get("localDiscount", 0) or 0)
    if local_discount > 0.000001:
        bonuses.append({"label": "本地设备成本", "value": f"{_multiplier_text(1 / (1 + local_discount))} 原价"})

    levels = state.get("levels", {})
    rows = []
    for spec in _load_game_data().get("upgrades", []):
        level = int(levels.get(spec["key"], 0))
        if level <= 0:
            continue
        era = str(spec.get("era", "foundation"))
        rows.append({
            "level": level,
            "max": int(spec.get("maxLevel", level)),
            "icon": get_s2_icon_src(spec["key"]),
            "pixel_level": pixel_level_src(level, level >= int(spec.get("maxLevel", level))),
            "hue": _ERA_HUES.get(era, 0),
        })
    html = render_template(
        "s2_mining_status.html",
        body_bg=gradient_bg("peach"),
        width=720,
        state=state,
        delta=delta,
        rows=rows,
        income_rate=income_rate,
        depth_rate=depth_rate,
        income_multiplier=_multiplier_text(income_mul),
        depth_multiplier=_multiplier_text(depth_mul),
        bonuses=bonuses,
        s2_image=get_s2_image_src,
        fatfish_image=get_fatfish_image_src,
        progress_pct=s2_progress_percent(state),
        s2_num=s2_format_number,
    )
    return await render_html(html, 720)


async def render_mining_shop(state: dict, rows: list[dict], page: int, pages: int) -> bytes:
    from ..s2_mining import s2_format_number, s2_progress_percent
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
        progress_pct=s2_progress_percent(state),
        s2_num=s2_format_number,
    )
    # 修正 total 为真实总数，需传入
    # 重新渲染一次带正确的 total（上面 len(rows) 不准）
    # 为简化，直接在外层计算 total 并替换
    return await render_html(html, 720)


async def render_shop_with_total(state: dict, rows: list[dict], page: int, pages: int, total: int) -> bytes:
    from ..s2_mining import s2_format_number, s2_progress_percent
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
        progress_pct=s2_progress_percent(state),
        s2_num=s2_format_number,
    )
    return await render_html(html, 720)
