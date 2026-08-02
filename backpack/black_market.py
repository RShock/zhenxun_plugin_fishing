"""
黑商/白商交换 — 用更高级的鱼交换同级或更低级目标鱼，并支持历史逆交换。
"""

import json
import random
import re
from dataclasses import dataclass
from datetime import date, timedelta

from ..config import (
    RARITY_COLORS,
    RARITY_INDEX,
    ConfigManager,
    generate_fish_numeric_id,
    normalize_fish_numeric_id,
)
from ..core.result import add_fish_to_user
from ..models import FishingExchangeRecord, FishingUser

DAILY_BLACK_MARKET_LIMIT = 1
_SAME_RARITY_RANDOM_RATE = 0.7
_BLACK_MARKET_PITY_THRESHOLD = 4
BLACK_MARKET_USAGE = (
    "黑商用法：黑商 鱼名字稀有度 鱼名字稀有度 / 黑商 鱼ID 鱼ID\n"
    "也可以使用：黑商交换 鱼名字稀有度 鱼名字稀有度\n"
    "例如：黑商 鲤鱼UR 草鱼SSR / 黑商交换 123 456 / 黑商交换 s101 s105\n"
    "鱼ID：1-9图为3位数字、10-15图为4位数字、猫猫乐园为 s1 开头（如 s101）\n"
    "来源鱼的场景等级和稀有度必须都不低于目标鱼；若稀有度相同，有 70% 概率改为获得目标鱼所在场景中相同稀有度的其他鱼。"
)
SMART_BLACK_MARKET_USAGE = (
    "智能黑商用法：智能黑商 来源鱼 目标鱼 / 智能黑商交换 来源鱼 目标鱼\n"
    "一次指令会把随机产物继续作为来源鱼交换，直到获得目标鱼，或产物因解锁图鉴/自动展示离开背包。"
)

_RARITY_RE = "UTR|SSR|UR|SR|R|N"
_EXCHANGE_RE = re.compile(
    rf"^\s*(?P<src_name>.+?)\s*(?P<src_rarity>{_RARITY_RE})"
    rf"(?P<dst_name>.+?)\s*(?P<dst_rarity>{_RARITY_RE})\s*$",
    re.IGNORECASE,
)
_NAME_EXCHANGE_TRIGGER_RE = re.compile(
    rf".+?(?:{_RARITY_RE}).+?(?:{_RARITY_RE})", re.IGNORECASE
)
# 鱼数字编号 token：
# - 猫猫乐园(S1): s1 + 1位索引 + 1位稀有度，如 s101
# - 1-9图: 3位数字，如 111
# - 10-15图: 4位数字，如 1011
_FISH_ID = r"(?:[sS]1\d{2}(?!\d)|(?<!\d)\d{3,4}(?!\d))"
# 分隔符用 \W+（非字母数字）而非原来的 \D+（非数字），
# 否则 s1XX 的 s 会被 \D 吞掉，导致猫猫乐园鱼被误识别为1图鱼。
_ID_EXCHANGE_TRIGGER_RE = re.compile(rf"{_FISH_ID}\W+{_FISH_ID}")
_ID_EXCHANGE_RE = re.compile(
    rf"^\W*(?P<src_id>{_FISH_ID})\W+(?P<dst_id>{_FISH_ID})\W*$"
)
_MARKET_PREFIX_RE = re.compile(
    r"^\s*(?:黑商|黑市|白商|白市)(?:交换)?\s*", re.IGNORECASE
)


@dataclass(frozen=True)
class ExchangeParseResult:
    should_reply: bool
    parsed: tuple[str, str, str, str] | None = None
    reason: str = ""


@dataclass(frozen=True)
class FishTarget:
    name: str
    rarity: str
    location_id: str
    location_name: str
    scene_level: int
    fish_index: int
    numeric_id: str


def _normalize_rarity(rarity: str) -> str:
    upper = rarity.upper()
    return upper if upper in RARITY_INDEX else ""


def _parse_name_exchange(text: str) -> tuple[str, str, str, str] | None:
    matched = _EXCHANGE_RE.match(text or "")
    if not matched:
        return None
    src_rarity = _normalize_rarity(matched.group("src_rarity"))
    dst_rarity = _normalize_rarity(matched.group("dst_rarity"))
    src_name = matched.group("src_name").strip(" \t\r\n,，;；:/：、")
    dst_name = matched.group("dst_name").strip(" \t\r\n,，;；:/：、")
    if not src_name or not dst_name or not src_rarity or not dst_rarity:
        return None
    return (
        src_name,
        src_rarity,
        dst_name,
        dst_rarity,
    )


def parse_black_market_exchange(text: str) -> tuple[str, str, str, str] | None:
    return _parse_name_exchange(text)


def extract_market_exchange_input(text: str) -> str:
    return _MARKET_PREFIX_RE.sub("", text or "", count=1).strip()


def should_parse_market_exchange(text: str) -> bool:
    text = text or ""
    return bool(
        _NAME_EXCHANGE_TRIGGER_RE.search(text) or _ID_EXCHANGE_TRIGGER_RE.search(text)
    )


def parse_market_exchange(text: str) -> ExchangeParseResult:
    text = (text or "").strip()
    if not should_parse_market_exchange(text):
        return ExchangeParseResult(False, reason="not_exchange_like")

    parsed = _parse_name_exchange(text)
    if parsed:
        return ExchangeParseResult(True, parsed=parsed)

    matched = _ID_EXCHANGE_RE.match(text)
    if matched:
        source = find_fish_target_by_numeric_id(matched.group("src_id"))
        target = find_fish_target_by_numeric_id(matched.group("dst_id"))
        if source and target:
            return ExchangeParseResult(
                True,
                parsed=(source.name, source.rarity, target.name, target.rarity),
            )

    return ExchangeParseResult(True, reason="parse_failed")


def _adjusted_fish_index(location_id: str, pool_index: int) -> int:
    """将 fish_pool 的 0-based 索引转为 numeric_id 生成用的索引。

    与 save_fish_to_backpack 保持一致：非 S1 钓场 +1。
    """
    return pool_index if location_id.upper() == "S1" else pool_index + 1


def find_fish_target(fish_name: str, rarity: str) -> FishTarget | None:
    for loc in ConfigManager.get_locations():
        for idx, name in enumerate(loc.fish_pool):
            if name != fish_name:
                continue
            fish_index = _adjusted_fish_index(loc.id, idx)
            numeric_id = generate_fish_numeric_id(loc.id, fish_index, rarity)
            return FishTarget(
                name=fish_name,
                rarity=rarity,
                location_id=loc.id,
                location_name=loc.name,
                scene_level=loc.difficulty + 1,
                fish_index=fish_index,
                numeric_id=numeric_id,
            )
    return None


def find_fish_target_by_numeric_id(numeric_id: str) -> FishTarget | None:
    normalized_id = normalize_fish_numeric_id(numeric_id)
    for loc in ConfigManager.get_locations():
        for idx, name in enumerate(loc.fish_pool):
            fish_index = _adjusted_fish_index(loc.id, idx)
            for rarity in RARITY_INDEX:
                if (
                    generate_fish_numeric_id(loc.id, fish_index, rarity)
                    == normalized_id
                ):
                    return FishTarget(
                        name=name,
                        rarity=rarity,
                        location_id=loc.id,
                        location_name=loc.name,
                        scene_level=loc.difficulty + 1,
                        fish_index=fish_index,
                        numeric_id=normalized_id,
                    )
    return None


def _find_fish_target_by_location(
    location_id: str, pool_index: int, rarity: str
) -> FishTarget | None:
    loc = ConfigManager.get_location(location_id)
    if not loc or not (0 <= pool_index < len(loc.fish_pool)):
        return None
    fish_name = loc.fish_pool[pool_index]
    fish_index = _adjusted_fish_index(loc.id, pool_index)
    return FishTarget(
        name=fish_name,
        rarity=rarity,
        location_id=loc.id,
        location_name=loc.name,
        scene_level=loc.difficulty + 1,
        fish_index=fish_index,
        numeric_id=generate_fish_numeric_id(loc.id, fish_index, rarity),
    )


def can_exchange(source: FishTarget, target: FishTarget) -> bool:
    source_rarity = RARITY_INDEX.get(source.rarity, 0)
    target_rarity = RARITY_INDEX.get(target.rarity, 0)
    return source.scene_level >= target.scene_level and source_rarity >= target_rarity


def _maybe_randomize_same_rarity_target(
    source: FishTarget, target: FishTarget
) -> tuple[FishTarget, bool]:
    if source.rarity != target.rarity or random.random() >= _SAME_RARITY_RANDOM_RATE:
        return target, False

    loc = ConfigManager.get_location(target.location_id)
    if not loc:
        return target, False
    excluded_ids = {source.numeric_id, target.numeric_id}
    candidates = []
    for idx, _fish_name in enumerate(loc.fish_pool):
        candidate = _find_fish_target_by_location(
            target.location_id, idx, target.rarity
        )
        if candidate and candidate.numeric_id not in excluded_ids:
            candidates.append(idx)
    if not candidates:
        return target, False
    randomized = _find_fish_target_by_location(
        target.location_id, random.choice(candidates), target.rarity
    )
    return (randomized, True) if randomized else (target, False)


async def _get_nickname(user_id: str) -> str:
    """通过 user_id 获取用户昵称，没有昵称则返回 user_id 前 6 位。"""
    user = await FishingUser.get_user(user_id)
    if user and user.nickname:
        return user.nickname[:6]
    return str(user_id)[:6]


async def _is_location_unlocked(user, location_id: str, rarity: str) -> bool:
    """检查用户是否已解锁指定地图且鱼竿等级足够钓到该稀有度。

    UTR 鱼还需场景全收集成就（collect_scene_{id}）。
    非 UTR 鱼额外检查：当前鱼竿等级在该场景封顶后的最终概率中该稀有度须 > 0，
    避免用未封顶原始概率错误展示不可获得的稀有度。
    """
    location = ConfigManager.get_location(location_id)
    if not location:
        return False

    user_id = user.user_id

    # 按地图类型分别检查解锁条件
    if location_id == "S1":
        from ..cat_park import has_cat_park_ticket

        if not await has_cat_park_ticket(user_id):
            return False
    elif location_id.isdigit() and int(location_id) >= 11:
        from ..starry import has_starry_ship

        if not await has_starry_ship(user_id):
            return False
        if user.rod_level < location.difficulty:
            return False
    else:
        if user.rod_level < location.difficulty:
            return False

    # 非 UTR：按场景封顶后的最终分布判断，不能用未封顶原始概率误判。
    if rarity != "UTR":
        from ..core.probability import calculate_display_probabilities

        probs = calculate_display_probabilities(
            user.rod_level, location.difficulty, location.max_rarity
        )
        if probs.get(rarity, 0) <= 0:
            return False

    # UTR 鱼需要场景全收集成就（解锁迷途风/UTR）
    # collect_scene_{id} 要求该图所有鱼 × {N,R,SR,SSR,UR} 全收集，
    # 因此隐含"已收集到该图所有 UR"，未集齐则 UTR 不展示
    if rarity == "UTR":
        if not await FishingUser.is_achievement_completed(
            user_id, f"collect_scene_{location_id}"
        ):
            return False

    return True


async def render_white_market_records(user_id: str) -> bytes:
    """渲染白商交换列表为简单箭头列表图片。

    白商新逻辑：支付鱼只需与黑商target同地图同稀有度即可，
    获得鱼是黑商source指定的鱼。不再要求精确逆映射。

    分两个区域显示：
    - 可以交换：玩家背包中有与黑商target同地图同稀有度的鱼，
      左边显示背包中具体的鱼，右边显示获得鱼
    - 有可能交换：玩家暂无合适的鱼但已解锁对应地图+稀有度，
      左边显示泛化标签（地图+稀有度），右边合并显示同target的多个获得鱼
    """
    records = await FishingExchangeRecord.list_active_records()

    from ..render.base import gradient_bg, render_html, render_template

    if not records:
        html = render_template(
            "white_market_list.html",
            body_bg=gradient_bg("blue"),
            width=700,
            has_data=False,
            now_items_json="[]",
            possible_items_json="[]",
            rarity_colors_json=json.dumps(RARITY_COLORS, ensure_ascii=False),
        )
        return await render_html(html, 700)

    collected_cache: dict[tuple[str, str], bool] = {}
    unlock_cache: dict[str, bool] = {}
    user = await FishingUser.get_user(user_id)
    user_fish = await FishingUser.get_user_fish(user_id)

    # 按(target_location_id, target_rarity)分组：同一地图同一稀有度的
    # 所有黑商记录合并为一条显示，避免同一支付鱼重复出现多行。
    # 组内收集所有 source（获得鱼），按 numeric_id 去重后再按(场景,稀有度)分组合并。
    loc_rarity_groups: dict[tuple[str, str], dict] = {}
    for record in records:
        # 图鉴过滤：已收集获得鱼（黑商source）则隐藏该记录
        key = (record.source_name, record.source_rarity)
        if key not in collected_cache:
            collected_cache[key] = await FishingUser.is_collected(
                user_id, record.source_name, record.source_rarity
            )
        if collected_cache[key]:
            continue

        gk = (record.target_location_id, record.target_rarity)
        if gk not in loc_rarity_groups:
            loc_rarity_groups[gk] = {
                "target_location_id": record.target_location_id,
                "target_rarity": record.target_rarity,
                "target_location_name": record.target_location_name,
                "sources": [],
            }
        loc_rarity_groups[gk]["sources"].append({
            "name": record.source_name,
            "rarity": record.source_rarity,
            "location_name": record.source_location_name,
            "location_id": record.source_location_id,
            "numeric_id": record.source_numeric_id,
        })

    now_items: list[dict] = []
    possible_items: list[dict] = []

    for gk, group in loc_rarity_groups.items():
        loc_id = group["target_location_id"]
        rarity = group["target_rarity"]
        loc_name = group["target_location_name"]
        # 标注"图x"：location_id 即地图编号（猫猫乐园=S1，其余为数字）
        loc_tag = f"图{loc_id}"

        # 右侧获得鱼：按 numeric_id 去重，再按(场景,稀有度)分组合并为单行
        seen_ids: set[str] = set()
        get_groups: list[dict] = []
        group_index: dict[tuple[str, str], int] = {}
        for s in group["sources"]:
            if s["numeric_id"] in seen_ids:
                continue
            seen_ids.add(s["numeric_id"])
            s_loc_tag = f"图{s['location_id']}"
            sgk = (s["location_name"], s["rarity"])
            if sgk not in group_index:
                group_index[sgk] = len(get_groups)
                get_groups.append({
                    "rarity": s["rarity"],
                    "location_name": s["location_name"],
                    "location_tag": s_loc_tag,
                    "names": [],
                })
            get_groups[group_index[sgk]]["names"].append(s["name"])

        # 查找玩家背包中与target同地图同稀有度的鱼
        backpack_fish = []
        seen_bp_names: set[str] = set()
        for f in user_fish:
            if f.get("rarity") != rarity or f.get("count", 0) < 1:
                continue
            if f["fish_name"] in seen_bp_names:
                continue
            # 通过find_fish_target获取location_id判断是否同地图
            f_target = find_fish_target(f["fish_name"], f["rarity"])
            if f_target and f_target.location_id == loc_id:
                seen_bp_names.add(f["fish_name"])
                backpack_fish.append({
                    "name": f["fish_name"],
                    "rarity": f["rarity"],
                    "location_name": loc_name,
                    "location_tag": loc_tag,
                })

        if backpack_fish:
            # 可以交换：左边显示背包中具体的鱼，右边显示获得鱼分组
            now_items.append({
                "pay_fish": backpack_fish,
                "pay_location_tag": loc_tag,
                "get_groups": get_groups,
            })
        else:
            # 有可能交换：检查是否已解锁
            unlock_key = f"{loc_id}|{rarity}"
            if unlock_key not in unlock_cache:
                unlock_cache[unlock_key] = await _is_location_unlocked(
                    user, loc_id, rarity
                )
            if not unlock_cache[unlock_key]:
                continue
            # 左边显示泛化标签
            possible_items.append({
                "pay_label": f"{loc_name} {rarity}",
                "pay_rarity": rarity,
                "pay_location_tag": loc_tag,
                "get_groups": get_groups,
            })

    html = render_template(
        "white_market_list.html",
        body_bg=gradient_bg("blue"),
        width=700,
        has_data=len(now_items) > 0 or len(possible_items) > 0,
        now_items_json=json.dumps(now_items, ensure_ascii=False),
        possible_items_json=json.dumps(possible_items, ensure_ascii=False),
        rarity_colors_json=json.dumps(RARITY_COLORS, ensure_ascii=False),
    )
    return await render_html(html, 700)


async def black_market_exchange(
    user_id: str, exchange_input: str
) -> tuple[bool, str, bool]:
    if not (exchange_input or "").strip():
        return False, BLACK_MARKET_USAGE, True
    result = parse_market_exchange(exchange_input)
    if not result.should_reply:
        return False, "", False
    if not result.parsed:
        return (
            False,
            BLACK_MARKET_USAGE,
            True,
        )

    src_name, src_rarity, dst_name, dst_rarity = result.parsed
    source = find_fish_target(src_name, src_rarity)
    if not source:
        return False, f"未找到鱼：{src_name}({src_rarity})", True
    target = find_fish_target(dst_name, dst_rarity)
    if not target:
        return False, f"未找到鱼：{dst_name}({dst_rarity})", True

    fish = await FishingUser.get_fish_by_numeric_id(user_id, source.numeric_id)
    target_fish = await FishingUser.get_fish_by_numeric_id(user_id, target.numeric_id)
    if (
        (not fish or fish.get("count", 0) < 1)
        and target_fish
        and target_fish.get("count", 0) >= 1
    ):
        source, target = target, source
        fish = target_fish
    if not fish or fish.get("count", 0) < 1:
        return False, f"背包里没有 {source.name}({source.rarity})", True

    if not can_exchange(source, target):
        return (
            False,
            "交换失败：来源鱼的场景等级和稀有度必须都不低于目标鱼。",
            True,
        )

    used_count = await FishingUser.get_black_market_count(user_id)
    used_extra_ticket = False
    if used_count >= DAILY_BLACK_MARKET_LIMIT:
        used_extra_ticket = await FishingUser.remove_item(
            user_id, "black_market_extra_ticket", "ticket", 1
        )
        if not used_extra_ticket:
            return (
                False,
                "今天的免费黑商交换已经用完，继续交换需要 1 张黑商额外兑换券。",
                True,
            )

    # 黑商秘密保底：连续4次"失败"（被黑商随机替换目标鱼）后，下次必定获得指定目标
    user = await FishingUser.get_user(user_id)
    pity_counter = user.black_market_pity_counter if user else 0
    pity_triggered = pity_counter >= _BLACK_MARKET_PITY_THRESHOLD

    if pity_triggered:
        # 保底触发：不随机替换，直接使用玩家指定的目标
        actual_target, randomized = target, False
    else:
        actual_target, randomized = _maybe_randomize_same_rarity_target(source, target)

    # 更新保底计数器：被随机替换=失败+1，获得指定目标=成功清零
    if randomized:
        new_pity = pity_counter + 1
    else:
        new_pity = 0
    if user:
        user.black_market_pity_counter = new_pity
        await user.save(update_fields=["black_market_pity_counter"])

    inherited_lock = bool(fish.get("locked", False))
    await FishingUser.remove_fish_by_numeric_id(user_id, source.numeric_id, 1)
    await FishingUser.increment_black_market_count(user_id)
    # 黑商获得的目标鱼始终尝试自动上框；来源鱼的锁定状态仍在入包后独立继承。
    result = await add_fish_to_user(
        user_id,
        [(actual_target.name, actual_target.rarity, actual_target.numeric_id, 1)],
        auto_display=True,
    )
    # 锁定继承说明（非 bug）：
    # add_fish_to_user 对「首条 UTR」会自动消耗该鱼以解锁图鉴（见 core/result.py），
    # 此时鱼不入背包，toggle_lock_by_numeric_id 自然返回 False，lock_inherited 为 False。
    # 这是预期行为：用图鉴解锁消耗鱼是合理的，被消耗的鱼无需也无法锁定。
    # 切勿将此处的 lock_inherited=False 误判为锁定继承失败的 bug。
    lock_inherited = False
    if inherited_lock:
        lock_inherited = await FishingUser.toggle_lock_by_numeric_id(
            user_id, actual_target.numeric_id, True
        )
    await FishingExchangeRecord.create_black_record(
        user_id,
        source,
        actual_target,
        is_randomized=randomized,
        used_extra_ticket=used_extra_ticket,
    )

    messages = list(result["messages"])
    if used_extra_ticket:
        messages.append("票券：已消耗 1 张黑商额外兑换券")
    messages.extend(result["achievement_messages"])

    lock_hint = "（已自动锁定）" if lock_inherited else ""
    msg = (
        f"黑商交换成功：消耗 {source.name}({source.rarity}) "
        f"→ 获得 {actual_target.name}({actual_target.rarity}){lock_hint}"
    )
    if randomized:
        msg += f"\n黑商动了手脚，目标从 {target.name} 变成了 {actual_target.name}。"
    if messages:
        msg += "\n" + "\n".join(messages)
    return True, msg, True


async def smart_black_market_exchange(
    user_id: str, exchange_input: str
) -> tuple[bool, str, bool]:
    """链式执行同一目标的黑商交换，并按实际尝试数设置冷却。"""
    if not (exchange_input or "").strip():
        return False, SMART_BLACK_MARKET_USAGE, True
    parsed = parse_market_exchange(exchange_input)
    if not parsed.should_reply:
        return False, "", False
    if not parsed.parsed:
        return False, SMART_BLACK_MARKET_USAGE, True

    src_name, src_rarity, dst_name, dst_rarity = parsed.parsed
    source = find_fish_target(src_name, src_rarity)
    target = find_fish_target(dst_name, dst_rarity)
    if not source:
        return False, f"未找到鱼：{src_name}({src_rarity})", True
    if not target:
        return False, f"未找到鱼：{dst_name}({dst_rarity})", True

    fish = await FishingUser.get_fish_by_numeric_id(user_id, source.numeric_id)
    target_fish = await FishingUser.get_fish_by_numeric_id(user_id, target.numeric_id)
    if (
        (not fish or fish.get("count", 0) < 1)
        and target_fish
        and target_fish.get("count", 0) >= 1
    ):
        source, target = target, source
        fish = target_fish
    if not fish or fish.get("count", 0) < 1:
        return False, f"背包里没有 {source.name}({source.rarity})", True
    if not can_exchange(source, target):
        return False, "交换失败：来源鱼的场景等级和稀有度必须都不低于目标鱼。", True

    used_count = await FishingUser.get_black_market_count(user_id)
    user = await FishingUser.get_user(user_id)
    today = date.today()
    available_date = getattr(user, "smart_black_market_available_date", None)
    # 当天已有黑商记录时，额外券可直接支付本轮智能黑商的启动费用；
    # 非当天产生的智能黑商冷却仍需正常等待，避免额外券跨日跳过既有冷却。
    if available_date and available_date > today and used_count < DAILY_BLACK_MARKET_LIMIT:
        return False, f"智能黑商将在 {available_date.isoformat()} 再来。", True

    start_ticket_used = False
    if used_count >= DAILY_BLACK_MARKET_LIMIT:
        start_ticket_used = await FishingUser.remove_item(
            user_id, "black_market_extra_ticket", "ticket", 1
        )
        if not start_ticket_used:
            return (
                False,
                "今天的免费黑商交换已经用完，启动智能黑商需要 1 张黑商额外兑换券。",
                True,
            )

    attempts = 0
    current = source
    route = [f"{source.name}({source.rarity})"]
    messages: list[str] = []
    stop_reason = ""
    while True:
        current_fish = await FishingUser.get_fish_by_numeric_id(
            user_id, current.numeric_id
        )
        if not current_fish or current_fish.get("count", 0) < 1:
            stop_reason = "产物已离开背包，链式交换停止"
            break

        pity_counter = user.black_market_pity_counter if user else 0
        if pity_counter >= _BLACK_MARKET_PITY_THRESHOLD:
            actual_target, randomized = target, False
        else:
            actual_target, randomized = _maybe_randomize_same_rarity_target(
                current, target
            )
        user.black_market_pity_counter = pity_counter + 1 if randomized else 0

        inherited_lock = bool(current_fish.get("locked", False))
        await FishingUser.remove_fish_by_numeric_id(user_id, current.numeric_id, 1)
        result = await add_fish_to_user(
            user_id,
            [(actual_target.name, actual_target.rarity, actual_target.numeric_id, 1)],
            auto_display=True,
        )
        if inherited_lock:
            await FishingUser.toggle_lock_by_numeric_id(
                user_id, actual_target.numeric_id, True
            )
        await FishingExchangeRecord.create_black_record(
            user_id,
            current,
            actual_target,
            is_randomized=randomized,
            # 启动券只归属于链式交换的首条记录，撤回该条时才能准确返还。
            used_extra_ticket=start_ticket_used and attempts == 0,
        )
        await FishingUser.increment_black_market_count(user_id)
        attempts += 1
        route.append(f"{actual_target.name}({actual_target.rarity})")
        messages.extend(result["messages"])
        messages.extend(result["achievement_messages"])

        if actual_target.numeric_id == target.numeric_id:
            stop_reason = "已获得目标鱼"
            break
        # 自动展示和首条 UTR 图鉴解锁都意味着本次随机产物没有留在背包；
        # 即使玩家原本另有同种鱼，也不能把旧库存误当作本次链式交换的产物继续消耗。
        product_left_backpack = bool(result["utr_consumed"]) or any(
            "自动展示" in message for message in result["messages"]
        )
        if product_left_backpack:
            stop_reason = "产物已因图鉴解锁或自动展示离开背包，链式交换停止"
            break
        current = actual_target

    if attempts == 0:
        if start_ticket_used:
            await FishingUser.add_item(
                user_id, "black_market_extra_ticket", "ticket", 1
            )
        return False, stop_reason or "智能黑商未能开始交换。", True

    ticket = await FishingUser.get_item(
        user_id, "black_market_extra_ticket", "ticket"
    )
    ticket_count = int(ticket.get("count", 0) or 0) if ticket else 0
    # 每张券只抵一天冷却；无论券有多少，智能黑商都至少要到次日才会再来。
    used_tickets = min(ticket_count, max(0, attempts - 1))
    if used_tickets:
        await FishingUser.remove_item(
            user_id, "black_market_extra_ticket", "ticket", used_tickets
        )
    cooldown_days = max(1, attempts - used_tickets)
    next_date = today + timedelta(days=cooldown_days)
    user.smart_black_market_available_date = next_date
    await user.save(
        update_fields=[
            "black_market_pity_counter",
            "smart_black_market_available_date",
        ]
    )

    msg = (
        f"智能黑商完成：共尝试 {attempts} 次\n"
        f"路线：{' → '.join(route)}\n"
        f"{stop_reason}\n"
        f"下次可用：{next_date.isoformat()}"
    )
    if start_ticket_used:
        msg += "（启动时已消耗 1 张黑商额外兑换券）"
    if used_tickets:
        msg += f"（已消耗 {used_tickets} 张黑商额外兑换券抵扣冷却）"
    if messages:
        msg += "\n" + "\n".join(messages)
    return True, msg, True


async def white_market_exchange(
    user_id: str, exchange_input: str
) -> tuple[bool, str, bool]:
    result = parse_market_exchange(exchange_input)
    if not result.should_reply:
        return False, "", False
    if not result.parsed:
        return (
            False,
            "格式：白商交换 鱼名字稀有度 鱼名字稀有度 / 白商交换 鱼ID 鱼ID\n例如：白商交换 草鱼SSR 鲤鱼UR / 白商交换 123 456",
            True,
        )

    src_name, src_rarity, dst_name, dst_rarity = result.parsed
    source = find_fish_target(src_name, src_rarity)
    if not source:
        return False, f"未找到鱼：{src_name}({src_rarity})", True
    target = find_fish_target(dst_name, dst_rarity)
    if not target:
        return False, f"未找到鱼：{dst_name}({dst_rarity})", True

    # 白商新逻辑：玩家用"支付鱼"交换"获得鱼"。
    # 获得鱼=黑商source（指定鱼），支付鱼只需与黑商target同地图同稀有度。
    # 尝试两个方向：source→target 或 target→source
    pay_fish, get_fish = source, target
    fish = await FishingUser.get_fish_by_numeric_id(user_id, pay_fish.numeric_id)
    if not fish or fish.get("count", 0) < 1:
        # 尝试反方向：source 和 target 都在背包里找一遍，但只提示第一个编号
        pay_fish, get_fish = target, source
        fish = await FishingUser.get_fish_by_numeric_id(user_id, pay_fish.numeric_id)
        if not fish or fish.get("count", 0) < 1:
            return False, f"没有在背包里找到{source.name}", True

    # 查找黑商source=获得鱼的有效记录
    records = await FishingExchangeRecord.find_active_by_source_numeric_id(
        get_fish.numeric_id
    )
    if not records:
        return False, f"没有找到能获得 {get_fish.name}({get_fish.rarity}) 的有效黑商记录。", True

    # 从记录中找一条 target 与支付鱼同地图同稀有度的
    matched_record = None
    for rec in records:
        if (
            rec.target_location_id == pay_fish.location_id
            and rec.target_rarity == pay_fish.rarity
        ):
            matched_record = rec
            break

    if not matched_record:
        return (
            False,
            f"没有找到匹配的交换记录：{pay_fish.name}({pay_fish.rarity}) "
            f"与 {get_fish.name}({get_fish.rarity}) 不在同一地图/稀有度。",
            True,
        )

    from ..services.white_market_service import (
        WHITE_MARKET_LIMIT_MESSAGE,
        get_white_market_eligibility,
    )

    eligibility = await get_white_market_eligibility(user_id)
    if eligibility.exhausted:
        return False, WHITE_MARKET_LIMIT_MESSAGE, True
    eligible_payment = next(
        (
            payment
            for payment in eligibility.payments
            if payment.numeric_id == pay_fish.numeric_id
        ),
        None,
    )
    if not eligible_payment or not any(
        target.numeric_id == get_fish.numeric_id
        for target in eligible_payment.targets
    ):
        return False, "当前白商资格已变化，请重新查看白商列表。", True

    await FishingUser.remove_fish_by_numeric_id(user_id, pay_fish.numeric_id, 1)
    await FishingUser.increment_gift_count(user_id)
    result = await add_fish_to_user(
        user_id,
        [(get_fish.name, get_fish.rarity, get_fish.numeric_id, 1)],
    )
    await FishingExchangeRecord.invalidate_record(matched_record.id, user_id)

    messages = list(result["messages"])
    messages.extend(result["achievement_messages"])
    if str(matched_record.user_id) == str(user_id):
        helper_line = "对应黑商记录已失效。"
    else:
        helper_nickname = await _get_nickname(matched_record.user_id)
        helper_line = f"{helper_nickname} 帮助了你，对应黑商记录已失效。"
    msg = (
        f"白商交换成功：消耗 {pay_fish.name}({pay_fish.rarity}) "
        f"→ 获得 {get_fish.name}({get_fish.rarity})\n"
        f"{helper_line}"
    )
    if messages:
        msg += "\n" + "\n".join(messages)
    return True, msg, True


BLACK_MARKET_REVOKE_USAGE = (
    "黑商撤回用法：黑商撤回（查看当天可撤回记录）/ 黑商撤回 序号\n"
    "仅可撤回当天的黑商交换，撤回后退还获得的鱼并返还消耗的鱼。"
)


async def _do_revoke(user_id: str, record) -> tuple[bool, str, bool]:
    """执行单条黑商撤回：退目标鱼、返来源鱼、失效记录、回退次数/保底/券。"""
    # 撤回前提：玩家仍持有黑商当时获得的目标鱼
    target_fish = await FishingUser.get_fish_by_numeric_id(
        user_id, record.target_numeric_id
    )
    if not target_fish or target_fish.get("count", 0) < 1:
        return (
            False,
            f"背包中没有 {record.target_name}({record.target_rarity})，无法撤回。",
            True,
        )

    # 退还目标鱼（黑商获得的），返还来源鱼（黑商消耗的）
    await FishingUser.remove_fish_by_numeric_id(user_id, record.target_numeric_id, 1)
    result = await add_fish_to_user(
        user_id,
        [(record.source_name, record.source_rarity, record.source_numeric_id, 1)],
    )
    await FishingExchangeRecord.revoke_record(record.id, user_id)
    # 回退当日黑商交换计数
    await FishingUser.decrement_black_market_count(user_id)
    # 回退保底计数器：只有被随机替换的失败交换曾令保底 +1，撤回时对应 -1
    if record.is_randomized:
        user = await FishingUser.get_user(user_id)
        if user:
            user.black_market_pity_counter = max(
                0, user.black_market_pity_counter - 1
            )
            await user.save(update_fields=["black_market_pity_counter"])
    # 返还额外券
    ticket_hint = ""
    if record.used_extra_ticket:
        await FishingUser.add_item(user_id, "black_market_extra_ticket", "ticket", 1)
        ticket_hint = "，已返还 1 张黑商额外兑换券"

    messages = list(result["messages"])
    messages.extend(result["achievement_messages"])
    msg = (
        f"黑商撤回成功：退还 {record.target_name}({record.target_rarity}) "
        f"→ 取回 {record.source_name}({record.source_rarity}){ticket_hint}"
    )
    if messages:
        msg += "\n" + "\n".join(messages)
    return True, msg, True


async def black_market_revoke(
    user_id: str, selection: str
) -> tuple[bool, str, bool]:
    """撤回当天黑商交换。

    selection 为空时：仅 1 条记录直接撤回，多条则列出序号供选择。
    selection 为数字时：撤回对应序号的记录。
    """
    records = await FishingExchangeRecord.list_today_records_by_user(user_id)
    if not records:
        return False, "今天没有可撤回的黑商交换记录。", True

    sel = (selection or "").strip()
    if not sel:
        if len(records) == 1:
            return await _do_revoke(user_id, records[0])
        lines = ["今天有以下可撤回的黑商交换，回复「黑商撤回 序号」撤回："]
        for i, r in enumerate(records, 1):
            lines.append(
                f"{i}. 退还 {r.target_name}({r.target_rarity}) "
                f"→ 取回 {r.source_name}({r.source_rarity})"
            )
        return False, "\n".join(lines), True

    try:
        idx = int(sel)
    except ValueError:
        return False, "请输入正确的序号，例如：黑商撤回 1", True
    if not (1 <= idx <= len(records)):
        return False, f"序号超出范围，请输入 1~{len(records)} 之间的数字。", True
    return await _do_revoke(user_id, records[idx - 1])
