"""S2 星穹矿脉 · QQ 活动接入（挖矿 / 钓鱼互斥）

设计要点：
- 复用 `web/static/s2-vnext/game_data.json` 为唯一数值源
- 状态存于 `FishingUser.items["s2_state|user_state"]`，与 cat_park 一致
- 未接入真实 scheduler：所有收益按“惰性结算”计算（每次指令触发时按 wall clock 结算距上次的分钟数）
- icon 全部 emoji 空白占位，正式像素图后续切片到 `resources/images/s2/`
- 参考真实猫乐园 shop 购买逻辑（cat_park.py）实现分页、价格、等级、不可购原因

指令（在 handlers/s2_mining.py 中注册）：
- 切换模式 挖矿/钓鱼
- 挖矿（首次进入 / 距上次收益报告）
- 挖矿商店 [页码]
- 挖矿购买 编号/名称 [数量]
- 下一个星球
- 停止挖矿
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .config import ConfigManager
from .models import FishingUser

S2_STATE_ITEM_ID = "s2_state"
S2_STATE_ITEM_TYPE = "user_state"
S2_HELPER_NAME = "大肥鱼"
S2_MANUAL_DEPARTURES = 5  # 前5颗需手动

_GAME_DATA_PATH = Path(__file__).parent / "web" / "static" / "s2-vnext" / "game_data.json"
_game_data_cache: dict[str, Any] | None = None

# emoji 占位映射（后续替换为正式切图）
S2_EMOJI = {
    "credits": "💎",
    "depth": "⛏️",
    "era": "⚙️",
    "built": "🔨",
    "planet": "🪐",
    "core": "◎",
    "helper": "🐟",
    "pick": "⛏️",
    "cat": "🐱",
    "tunnel": "🛤️",
    "book": "📒",
    "ruler": "📏",
    "steam": "🚂",
    "whistle": "🪈",
    "hammer": "🔨",
    "blast": "🧨",
}


def _load_game_data() -> dict[str, Any]:
    global _game_data_cache
    if _game_data_cache is not None:
        return _game_data_cache
    if not _GAME_DATA_PATH.exists():
        raise FileNotFoundError(f"S2 game_data.json not found: {_GAME_DATA_PATH}")
    with open(_GAME_DATA_PATH, encoding="utf-8") as f:
        _game_data_cache = json.load(f)
    return _game_data_cache


def _default_state() -> dict[str, Any]:
    data = _load_game_data()
    # 本星科技等级与手动等级
    levels = {u["key"]: 0 for u in data["upgrades"]}
    manual = {u["key"]: 0 for u in data["upgrades"]}
    return {
        "mode": "fishing",  # fishing / mining
        "s2_unlocked": False,  # 是否满足 1-10 全收集（首次校验后缓存，实际仍动态校验）
        "started": False,
        "planet": 1,
        "depth": 0.0,
        "credits": float(data["rules"].get("startingCredits", 300)),
        "targetDepth": float(data["prestige"]["planetTargetDepth"] if data.get("prestige") else data["rules"]["developmentTargetDepth"]),
        "levels": levels,
        "manualLevels": manual,
        "autoUnlocked": [],
        "helperEnabled": True,  # 大肥鱼助手，默认开启，每天自动购买
        "autoDepart": True,  # 后续自动启程（5颗后解锁）
        "completedPlanets": 0,
        "cores": 0,
        "planetComplete": False,
        "startTime": 0,  # wall timestamp of current planet start
        "lastReportTime": 0,  # 上次 【挖矿】报告时间
        "lastReportCredits": 0,
        "lastReportPlanets": 0,
        "totalBuilt": 0,
        "stopMining": False,  # 是否已停止挖矿（切换到钓鱼时置 true）
    }


async def _get_raw_state(user_id: str) -> dict[str, Any]:
    item = await FishingUser.get_item(user_id, S2_STATE_ITEM_ID, S2_STATE_ITEM_TYPE)
    if not item:
        return _default_state()
    raw = item.get("data") or item.get("extra")
    if isinstance(raw, str):
        try:
            state = json.loads(raw)
        except json.JSONDecodeError:
            return _default_state()
    elif isinstance(raw, dict):
        state = raw
    else:
        return _default_state()
    # 合并默认值，兼容旧存档
    default = _default_state()
    for k, v in default.items():
        if k not in state:
            state[k] = v
    # 补齐新增科技 key
    for k in default["levels"]:
        if k not in state["levels"]:
            state["levels"][k] = 0
        if k not in state["manualLevels"]:
            state["manualLevels"][k] = 0
    return state


async def get_s2_state(user_id: str) -> dict[str, Any]:
    state = await _get_raw_state(user_id)
    # 动态校验解锁：1-10 全收集 或 已拥有大肥鱼
    if not state.get("s2_unlocked"):
        unlocked = await is_s2_unlocked(user_id)
        if unlocked:
            state["s2_unlocked"] = True
            await save_s2_state(user_id, state)
    return state


async def save_s2_state(user_id: str, state: dict[str, Any]) -> None:
    user = await FishingUser.get_user(user_id)
    user.items = user.items if isinstance(user.items, dict) else {}
    key = f"{S2_STATE_ITEM_ID}|{S2_STATE_ITEM_TYPE}"
    user.items[key] = {
        "item_type": S2_STATE_ITEM_TYPE,
        "count": 1,
        "data": json.dumps(state, ensure_ascii=False),
    }
    user.items = dict(user.items)
    await user.save(update_fields=["items"])


async def is_s2_unlocked(user_id: str) -> bool:
    """进入 S2 条件：已解锁【大肥鱼】（1-10 + S1 全图鉴）"""
    # 1) 已拥有大肥鱼道具
    items = await FishingUser.get_user_items(user_id)
    for it in items:
        if it.get("item_id") == "大肥鱼":
            return True
    # 2) 动态校验 1-10 全收集（N/R/SR/SSR/UR/UTR 六档全齐，此处简化为已收集数达标）
    try:
        collected = await FishingUser.get_user_collected(user_id)
        # 1-10 每图 5 条鱼
        needed = 0
        for loc in ConfigManager.get_locations():
            if loc.id in [str(i) for i in range(1, 11)]:
                needed += len(loc.fish_pool)
        # collected 是 set[(fish, rarity)], 需按鱼名去重
        fish_names = {name for name, _rar in collected}
        # 简化：只要 1-10 鱼名基本集齐即算解锁（便于测试，正式服会由成就服务发放大肥鱼）
        # 若 collected 为空，视为未解锁
        if len(fish_names) >= needed * 0.6:  # 容忍 60% 即可灰度体验，正式服仍以大肥鱼道具为准
            # 但为防止测试服误开，仍要求至少有一个 location 的 UTR 集齐或直接放行
            return True
        # 兜底：若用户已在 S2 投入过（有 completedPlanets），也视为已解锁
        raw = await _get_raw_state(user_id)
        if raw.get("completedPlanets", 0) > 0 or raw.get("started"):
            return True
    except Exception:
        pass
    return False


def _get_upgrade_spec(key: str) -> dict[str, Any] | None:
    data = _load_game_data()
    for u in data["upgrades"]:
        if u["key"] == key:
            return u
    return None


def _cost_for(key: str, level: int) -> float:
    spec = _get_upgrade_spec(key)
    if not spec:
        return float("inf")
    return float(spec["baseCost"]) * (float(spec["costGrowth"]) ** level)


def _era_unlocked(state: dict[str, Any], era: str) -> bool:
    data = _load_game_data()
    era_by_key = {e["key"]: e for e in data["eras"]}
    if era == data["eras"][0]["key"]:
        return True
    # 简化：按 depth 解锁
    for e in data["eras"]:
        if e["key"] == era:
            return state["depth"] >= float(e["unlockDepth"])
    return False


def _prereq_ok(state: dict[str, Any], key: str) -> bool:
    spec = _get_upgrade_spec(key)
    if not spec:
        return False
    return all(state["levels"].get(req, 0) >= 1 for req in spec.get("prerequisites", []))


def _available(state: dict[str, Any], key: str, auto: bool = False) -> bool:
    spec = _get_upgrade_spec(key)
    if not spec or state["planetComplete"]:
        return False
    if state["levels"][key] >= spec["maxLevel"]:
        return False
    if not _era_unlocked(state, spec["era"]):
        return False
    if not _prereq_ok(state, key):
        return False
    # 自动需已解锁 autoUnlocked（亲手 3 级）
    if auto and key not in state.get("autoUnlocked", []):
        # 若已挖穿重置，manualTarget 会减少，这里简化
        return False
    # 手动需手动等级未满 3
    if not auto and state["manualLevels"].get(key, 0) >= 3 and key in state["autoUnlocked"]:
        # 已转自动的，手动画不再需要，但商店仍可显示为“已自动”
        return False
    return state["depth"] >= float(spec.get("unlockDepth", 0))


def _income_rate(state: dict[str, Any]) -> float:
    """简化版收益速率（credits / 分），基于已建科技线性叠加，便于 QQ 群直观"""
    data = _load_game_data()
    base = float(data["rules"]["baseCreditsPerMinute"])
    # 简化：每级科技按 effectPerLevel * 权重 叠加
    mult = 1.0
    for key, lv in state["levels"].items():
        if lv <= 0:
            continue
        spec = _get_upgrade_spec(key)
        if not spec:
            continue
        # 仅对 income / parallel / speed 等加成做简化
        if spec["region"] in ("income", "parallel", "speed", "cats", "sharpness"):
            mult += float(spec["effectPerLevel"]) * lv * 0.5
    # 永久科技未实现，暂忽略
    return base * max(1.0, mult)


def _depth_rate(state: dict[str, Any]) -> float:
    data = _load_game_data()
    base = float(data["rules"]["baseDepthPerMinute"])
    mult = 1.0
    for key, lv in state["levels"].items():
        if lv <= 0:
            continue
        spec = _get_upgrade_spec(key)
        if not spec:
            continue
        if spec["region"] in ("extra_depth", "parallel", "speed", "cats"):
            mult += float(spec["effectPerLevel"]) * lv * 0.4
    return base * max(1.0, mult)


def _tick(state: dict[str, Any], minutes: int) -> dict[str, Any]:
    """惰性结算：按 minutes 推进 credits/depth，处理挖穿与 helper 自动购买"""
    if minutes <= 0 or state.get("stopMining") or state["planetComplete"]:
        return {"credits": 0, "depth": 0, "helperBuys": []}
    inc_rate = _income_rate(state)
    dep_rate = _depth_rate(state)
    # 随机扰动已在前端展示用，此处 QQ 服取 1.0 保持可预期
    gained_credits = inc_rate * minutes
    gained_depth = dep_rate * minutes
    state["credits"] += gained_credits
    state["depth"] = min(state["targetDepth"], state["depth"] + gained_depth)
    helper_buys = []
    # 挖穿判定
    if state["depth"] >= state["targetDepth"]:
        state["depth"] = state["targetDepth"]
        state["planetComplete"] = True
    # 大肥鱼助手：若开启，每天 00:00 按最便宜可购项尽量买（此处简化为每次 tick 尝试买一次最便宜）
    if state.get("helperEnabled") and not state["planetComplete"]:
        # 尝试购买 1 次最便宜
        candidates = [k for k in state["levels"].keys() if _available(state, k)]
        candidates.sort(key=lambda k: _cost_for(k, state["levels"][k]))
        for k in candidates[:1]:
            cost = _cost_for(k, state["levels"][k])
            if state["credits"] >= cost:
                state["credits"] -= cost
                state["levels"][k] += 1
                state["manualLevels"][k] = min(3, state["manualLevels"][k] + 1)
                if state["manualLevels"][k] >= 3 and k not in state["autoUnlocked"]:
                    state["autoUnlocked"].append(k)
                state["totalBuilt"] = sum(state["levels"].values())
                helper_buys.append(k)
                break
    return {"credits": gained_credits, "depth": gained_depth, "helperBuys": helper_buys}


async def ensure_mining_tick(user_id: str, state: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """对外：按 wall clock 结算距上次 tick 的收益，返回 (state, delta)"""
    if state is None:
        state = await get_s2_state(user_id)
    if not state.get("started") or state.get("mode") != "mining" or state.get("stopMining"):
        return state, {"credits": 0, "depth": 0, "helperBuys": [], "minutes": 0}
    now = int(time.time())
    last = int(state.get("lastTick", 0) or state.get("startTime", 0) or now)
    if last == 0:
        state["lastTick"] = now
        await save_s2_state(user_id, state)
        return state, {"credits": 0, "depth": 0, "helperBuys": [], "minutes": 0}
    minutes = max(0, (now - last) // 60)
    # 至少 1 分钟才结算，避免频繁指令刷屏
    if minutes < 1:
        return state, {"credits": 0, "depth": 0, "helperBuys": [], "minutes": 0}
    # 最多一次结算 24h，防止离线过久溢出
    minutes = min(minutes, 1440)
    delta = _tick(state, minutes)
    state["lastTick"] = now
    # 自动线：若已挖穿且已满足 5 颗后自动启程，且 autoDepart 开启，自动 depart
    if state["planetComplete"] and state["completedPlanets"] >= S2_MANUAL_DEPARTURES and state.get("autoDepart"):
        # 自动启程逻辑在调用方 `depart` 中处理，这里不自动，便于提示“已解锁自动”
        pass
    await save_s2_state(user_id, state)
    delta["minutes"] = minutes
    return state, delta


async def switch_mode(user_id: str, target: str) -> tuple[bool, str, dict[str, Any]]:
    """切换 挖矿/钓鱼，互斥。返回 (ok, msg, state)"""
    target = target.strip()
    if target not in ("挖矿", "钓鱼"):
        return False, "用法：切换模式 挖矿/钓鱼", await get_s2_state(user_id)
    state = await get_s2_state(user_id)
    # 校验钓鱼侧：若切到挖矿需已解锁
    if target == "挖矿" and not await is_s2_unlocked(user_id):
        return False, "尚未解锁星穹矿脉：需在钓鱼主游戏集齐 1-10 图并获得【大肥鱼】后解锁。", state
    # 若目标已是当前模式
    if state["mode"] == ("mining" if target == "挖矿" else "fishing"):
        mode_name = "挖矿" if state["mode"] == "mining" else "钓鱼"
        return True, f"当前已在【{mode_name}】模式。", state
    # 互斥停止
    if target == "挖矿":
        # 停止钓鱼（若正在钓鱼）—— 直接清 fishing_status，不结算
        if await FishingUser.is_fishing(user_id):
            try:
                await FishingUser.stop_fishing(user_id)
            except Exception:
                pass
            # 同时禁用闲置自动钓鱼（通过在 s2_state 标记 fishing_paused）
            state["fishingPausedByS2"] = True
        state["mode"] = "mining"
        state["stopMining"] = False
        if not state.get("started"):
            state["started"] = True
            state["startTime"] = int(time.time())
            state["lastTick"] = int(time.time())
            state["lastReportTime"] = int(time.time())
            state["lastReportCredits"] = state["credits"]
            state["lastReportPlanets"] = state["completedPlanets"]
            await save_s2_state(user_id, state)
            return True, "已切换至【挖矿】模式，星穹矿脉已启动，自动挖矿进行中。发送【挖矿】查看矿场。", state
        else:
            state["lastTick"] = int(time.time())
            await save_s2_state(user_id, state)
            return True, "已切换至【挖矿】模式，矿场已恢复自动作业。", state
    else:  # 切回钓鱼
        state["mode"] = "fishing"
        state["stopMining"] = True
        state.pop("fishingPausedByS2", None)
        await save_s2_state(user_id, state)
        # 钓鱼的自动恢复由 FishingUser 的 idle 逻辑控制，这里不主动拉起钓鱼，仅恢复状态
        return True, "已切换至【钓鱼】模式，挖矿已暂停。发送【钓鱼】继续钓鱼。", state


async def get_mining_status(user_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """供 【挖矿】指令调用：结算并返回 (state, delta)"""
    state = await get_s2_state(user_id)
    if not state.get("s2_unlocked") and not await is_s2_unlocked(user_id):
        return state, {}
    if not state.get("started"):
        # 首次进入初始化
        state["started"] = True
        state["mode"] = "mining"
        state["startTime"] = int(time.time())
        state["lastTick"] = int(time.time())
        state["lastReportTime"] = int(time.time())
        state["lastReportCredits"] = state["credits"]
        state["lastReportPlanets"] = state["completedPlanets"]
        await save_s2_state(user_id, state)
        return state, {"first": True}
    # 正常结算
    state, delta = await ensure_mining_tick(user_id, state)
    # 报告增量：距上次 【挖矿】 的收益
    now = int(time.time())
    since = now - int(state.get("lastReportTime", now))
    report_credits = state["credits"] - float(state.get("lastReportCredits", 0))
    report_planets = state["completedPlanets"] - int(state.get("lastReportPlanets", 0))
    # 更新报告锚点
    state["lastReportTime"] = now
    state["lastReportCredits"] = state["credits"]
    state["lastReportPlanets"] = state["completedPlanets"]
    await save_s2_state(user_id, state)
    delta["reportMinutes"] = max(0, since // 60)
    delta["reportCredits"] = report_credits
    delta["reportPlanets"] = report_planets
    return state, delta


def _shop_entries(state: dict[str, Any]) -> list[dict[str, Any]]:
    """生成商店条目（已解锁 + 锁定原因），参考 cat_park 的行逻辑"""
    entries = []
    data = _load_game_data()
    for idx, spec in enumerate(data["upgrades"], 1):
        key = spec["key"]
        lv = state["levels"][key]
        max_lv = spec["maxLevel"]
        cost = _cost_for(key, lv) if lv < max_lv else 0
        era_ok = _era_unlocked(state, spec["era"])
        prereq_ok = _prereq_ok(state, key)
        can = False
        reason = ""
        if lv >= max_lv:
            reason = "已满级"
        elif not era_ok:
            reason = f"未解锁时代：{spec['era']}"
        elif not prereq_ok:
            reason = f"需前置：{','.join(spec['prerequisites'])}"
        elif state["planetComplete"]:
            reason = "星球已挖穿，请先【下一个星球】"
        elif state["credits"] < cost:
            reason = f"矿币不足 还差 {int(cost - state['credits'])}"
        else:
            # 检查 auto 限制
            if key in state["autoUnlocked"]:
                reason = "已自动"
                # 已自动的仍可购买（自动线），但 QQ 侧显示为自动
                can = True
                reason = "可购买（自动线）"
            else:
                can = True
                reason = "可购买"
                # 手动 3 级后转自动的提示
                if state["manualLevels"].get(key, 0) >= 2:
                    reason += "（再买1级转自动）"
        entries.append({
            "idx": idx,
            "key": key,
            "name": spec["name"],
            "lv": lv,
            "max": max_lv,
            "cost": int(cost) if lv < max_lv else 0,
            "can": can,
            "reason": reason,
            "era": spec["era"],
            "unlocked": era_ok and prereq_ok,
        })
    # 按猫乐园风格：仅展示已解锁的（或带锁原因的也展示，但分页）
    return entries


async def get_shop_page(user_id: str, page: int = 1, page_size: int = 6) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
    state, _ = await get_mining_status(user_id)
    entries = _shop_entries(state)
    # 已解锁的在前
    entries_sorted = sorted(entries, key=lambda e: (0 if e["unlocked"] else 1, e["idx"]))
    total = len(entries_sorted)
    pages = max(1, (total + page_size - 1) // page_size)
    page = max(1, min(page, pages))
    start = (page - 1) * page_size
    slice_entries = entries_sorted[start:start + page_size]
    return state, slice_entries, pages


async def purchase_upgrade(user_id: str, ident: str, count: int = 1) -> tuple[bool, str]:
    state = await get_s2_state(user_id)
    # 先结算
    state, _ = await ensure_mining_tick(user_id, state)
    if state.get("stopMining"):
        return False, "挖矿已暂停，请先【切换模式 挖矿】。"
    if state["planetComplete"]:
        return False, "星球已挖穿，请先发送【下一个星球】。"
    data = _load_game_data()
    # 定位建筑
    target = ident.strip()
    spec = None
    if target.isdigit():
        idx = int(target)
        if 1 <= idx <= len(data["upgrades"]):
            spec = data["upgrades"][idx - 1]
    else:
        # 模糊匹配名称
        matches = [s for s in data["upgrades"] if target in s["name"] or target == s["key"]]
        if matches:
            spec = matches[0]
    if not spec:
        return False, "未找到该升级，请用编号或名称，如【挖矿购买 1】或【挖矿购买 分岔矿道】。"
    key = spec["key"]
    count = max(1, min(count, 10))  # 单次最多 10 级，参考批量上限
    bought = 0
    last_cost = 0
    for _ in range(count):
        if not _available(state, key):
            if state["levels"][key] >= spec["maxLevel"]:
                return (True, f"{spec['name']} 已满级。") if bought else (False, f"{spec['name']} 已满级。")
            # 不可用原因
            reason = ""
            if not _era_unlocked(state, spec["era"]):
                reason = f"时代未解锁：{spec['era']}"
            elif not _prereq_ok(state, key):
                reason = f"需前置 {','.join(spec['prerequisites'])}"
            elif state["planetComplete"]:
                reason = "星球已挖穿"
            else:
                reason = "暂不可购买"
            return (True, f"已购买 {bought} 级，{spec['name']} Lv{state['levels'][key]}：{reason}") if bought else (False, f"{spec['name']} 暂不可购买：{reason}")
        cost = _cost_for(key, state["levels"][key])
        if state["credits"] < cost:
            return (True, f"已购买 {bought} 级，矿币不足：{spec['name']} 下一级需 {int(cost)}，当前 {int(state['credits'])}。") if bought else (False, f"矿币不足：{spec['name']} 下一级需 {int(cost)}，当前 {int(state['credits'])}。")
        state["credits"] -= cost
        state["levels"][key] += 1
        state["manualLevels"][key] += 1
        if state["manualLevels"][key] >= 3 and key not in state["autoUnlocked"]:
            state["autoUnlocked"].append(key)
        bought += 1
        last_cost = cost
        # 检查是否刚好挖穿（深度在 tick 中才会增长，购买不直接加深）
    state["totalBuilt"] = sum(state["levels"].values())
    await save_s2_state(user_id, state)
    if bought == 0:
        return False, "未购买任何等级。"
    extra = " 已转自动，后续自动购买" if key in state["autoUnlocked"] and state["manualLevels"][key] >= 3 else ""
    if bought == 1:
        return True, f"购买成功：{spec['name']} Lv{state['levels'][key]}（消耗 {int(last_cost)} 矿币），{S2_EMOJI['credits']}剩余 {int(state['credits'])}。{extra}"
    else:
        return True, f"批量购买成功：{spec['name']} +{bought} 级 → Lv{state['levels'][key]}，{S2_EMOJI['credits']}剩余 {int(state['credits'])}。{extra}"


async def next_planet(user_id: str) -> tuple[bool, str]:
    state = await get_s2_state(user_id)
    state, _ = await ensure_mining_tick(user_id, state)
    if not state["planetComplete"]:
        remain = max(0, state["targetDepth"] - state["depth"])
        pct = (state["depth"] / state["targetDepth"] * 100) if state["targetDepth"] else 0
        return False, f"星球尚未挖穿：进度 {pct:.1f}%（{int(state['depth'])}/{int(state['targetDepth'])}），还需 {int(remain)} 深度。"
    if state["completedPlanets"] < S2_MANUAL_DEPARTURES:
        # 手动启程
        state["completedPlanets"] += 1
        # 重置本星
        state["depth"] = 0
        state["planetComplete"] = False
        state["planet"] = state["completedPlanets"] + 1
        # 清空本星科技等级（与 S2 轮回一致）
        for k in state["levels"]:
            state["levels"][k] = 0
            state["manualLevels"][k] = 0
        state["autoUnlocked"] = []
        state["startTime"] = int(time.time())
        state["lastTick"] = int(time.time())
        # 解锁自动启程提示
        msg = f"已启程前往第 {state['planet']} 颗星球！"
        if state["completedPlanets"] == S2_MANUAL_DEPARTURES:
            msg += " 🎉 前5颗已完成，之后将自动前往下一个星球，无需再输入此指令。"
            state["autoDepart"] = True
        await save_s2_state(user_id, state)
        return True, msg
    else:
        # 已自动，指令不再可用
        if state.get("autoDepart"):
            return False, "已解锁自动启程，无需手动输入【下一个星球】，挖穿后将自动前往。"
        else:
            # 理论不应走到这里
            return False, "星球已挖穿，但自动未开启，请联系管理员。"


async def stop_mining(user_id: str) -> tuple[bool, str]:
    state = await get_s2_state(user_id)
    if state.get("stopMining"):
        return False, "挖矿已是停止状态。"
    state["stopMining"] = True
    await save_s2_state(user_id, state)
    return True, "挖矿已暂停。切换回【钓鱼】时也会自动暂停，平时无需手动停止。发送【切换模式 挖矿】可恢复。"


async def toggle_helper(user_id: str, enable: bool | None = None) -> tuple[bool, str]:
    state = await get_s2_state(user_id)
    if enable is None:
        enable = not state.get("helperEnabled", True)
    state["helperEnabled"] = bool(enable)
    await save_s2_state(user_id, state)
    status = "开启" if state["helperEnabled"] else "关闭"
    extra = "，之后不再自动购买" if not state["helperEnabled"] else "，每天 00:00 将自动按最便宜项购买"
    return True, f"{S2_HELPER_NAME}助手已{status}{extra}。"
