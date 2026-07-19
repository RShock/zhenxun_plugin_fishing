"""
黑商/白商交换 — 用更高级的鱼交换同级或更低级目标鱼，并支持历史逆交换。
"""

import random
import re
from dataclasses import dataclass

from ..config import (
    DAILY_GIFT_LIMIT,
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
    "例如：黑商 鲤鱼UR 草鱼SSR / 黑商交换 123 456\n"
    "来源鱼的场景等级和稀有度必须都不低于目标鱼；若稀有度相同，有 70% 概率改为获得目标鱼所在场景中相同稀有度的其他鱼。"
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
_ID_EXCHANGE_TRIGGER_RE = re.compile(r"(?<!\d)\d{3}(?!\d)\D+(?<!\d)\d{3}(?!\d)")
_ID_EXCHANGE_RE = re.compile(
    r"^\D*(?P<src_id>(?<!\d)\d{3}(?!\d))\D+"
    r"(?P<dst_id>(?<!\d)\d{3}(?!\d))\D*$"
)
_MARKET_PREFIX_RE = re.compile(r"^\s*(?:黑商|黑市|白商|白市)(?:交换)?\s*", re.IGNORECASE)


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
    """渲染白商交换列表为图片，按可交换性分区，左侧鱼二重分组压缩显示。

    二重分组结构：
    - 第一重：左侧相同的鱼合并，只显示一次左侧鱼
    - 第二重：右侧相同场景的鱼合并，只显示一次场景名
    """
    records = await FishingExchangeRecord.list_active_records()
    if not records:
        from ..render.base import gradient_bg, render_html, render_template

        html = render_template(
            "white_market.html",
            body_bg=gradient_bg("blue"),
            width=560,
            categories=[],
        )
        return await render_html(html, 560)

    from ..render.base import get_fish_image_src

    # 批量获取图鉴状态
    collected_cache: dict[tuple[str, str], bool] = {}
    backpack_cache: dict[str, bool] = {}
    unlock_cache: dict[str, bool] = {}
    shown_reverse_keys: set[tuple[int, int]] = set()

    user = await FishingUser.get_user(user_id)

    # 临时收集每个分类下的记录条目，稍后二重分组
    cat_entries: dict[str, list[dict]] = {
        "现在可交换": [],
        "有可能做到": [],
    }

    for record in records:
        reverse_key = (record.target_numeric_id, record.source_numeric_id)
        if reverse_key in shown_reverse_keys:
            continue

        # 只显示交换来源鱼（白商可获得）未被当前用户解锁过的记录
        key = (record.source_name, record.source_rarity)
        if key not in collected_cache:
            collected_cache[key] = await FishingUser.is_collected(
                user_id, record.source_name, record.source_rarity
            )
        if collected_cache[key]:
            continue

        # 判定所属分区
        cache_key = record.source_numeric_id
        if cache_key not in backpack_cache:
            fish = await FishingUser.get_fish_by_numeric_id(
                user_id, record.source_numeric_id
            )
            backpack_cache[cache_key] = fish is not None and fish.get("count", 0) > 0

        if backpack_cache[cache_key]:
            cat = "现在可交换"
        else:
            unlock_key = f"{record.source_location_id}|{record.source_rarity}"
            if unlock_key not in unlock_cache:
                unlock_cache[unlock_key] = await _is_location_unlocked(
                    user, record.source_location_id, record.source_rarity
                )
            if not unlock_cache[unlock_key]:
                continue
            cat = "有可能做到"

        shown_reverse_keys.add(reverse_key)

        cat_entries[cat].append({
            "source_name": record.source_name,
            "source_rarity": record.source_rarity,
            "source_rarity_idx": RARITY_INDEX.get(record.source_rarity, 0),
            "source_location": record.source_location_name,
            "source_location_id": record.source_location_id,
            "source_scene_level": record.source_scene_level,
            "source_numeric_id": record.source_numeric_id,
            "source_img": get_fish_image_src(record.source_name, record.source_location_id),
            "target_name": record.target_name,
            "target_rarity": record.target_rarity,
            "target_rarity_idx": RARITY_INDEX.get(record.target_rarity, 0),
            "target_location": record.target_location_name,
            "target_location_id": record.target_location_id,
            "target_scene_level": record.target_scene_level,
            "target_img": get_fish_image_src(record.target_name, record.target_location_id),
        })

    # 对每个分类进行二重分组
    categories: dict[str, list[dict]] = {}
    for cat_name in ["现在可交换", "有可能做到"]:
        entries = cat_entries[cat_name]
        # 第一重：按左侧鱼（source_numeric_id）分组
        source_map: dict[str, dict] = {}
        for entry in entries:
            sid = entry["source_numeric_id"]
            if sid not in source_map:
                source_map[sid] = {
                    "source_name": entry["source_name"],
                    "source_rarity": entry["source_rarity"],
                    "source_location": entry["source_location"],
                    "source_img": entry["source_img"],
                    "_source_rarity_idx": entry["source_rarity_idx"],
                    "_source_scene_level": entry["source_scene_level"],
                    "_target_map": {},  # target_location_id -> group
                }
            sg = source_map[sid]
            # 第二重：按右侧场景（target_location_id）分组
            tid = entry["target_location_id"]
            if tid not in sg["_target_map"]:
                sg["_target_map"][tid] = {
                    "location": entry["target_location"],
                    "_target_scene_level": entry["target_scene_level"],
                    "targets": [],
                }
            sg["_target_map"][tid]["targets"].append({
                "name": entry["target_name"],
                "rarity": entry["target_rarity"],
                "_rarity_idx": entry["target_rarity_idx"],
                "img": entry["target_img"],
            })

        # 转为列表并排序
        source_list = list(source_map.values())
        # 左侧鱼排序：稀有度降序 → 场景等级升序 → 名称
        source_list.sort(
            key=lambda s: (-s["_source_rarity_idx"], s["_source_scene_level"], s["source_name"])
        )
        for sg in source_list:
            groups = list(sg["_target_map"].values())
            # 右侧场景排序：场景等级升序 → 场景名
            groups.sort(key=lambda g: (g["_target_scene_level"], g["location"]))
            for g in groups:
                # 右侧鱼排序：稀有度降序 → 名称
                g["targets"].sort(key=lambda t: (-t["_rarity_idx"], t["name"]))
                del g["_target_scene_level"]
            sg["target_groups"] = groups
            del sg["_target_map"]
            del sg["_source_rarity_idx"]
            del sg["_source_scene_level"]

        categories[cat_name] = source_list

    # 构建最终分区列表
    category_list: list[dict] = []
    for name in ["现在可交换", "有可能做到"]:
        groups = categories[name]
        category_list.append(
            {"name": name, "groups": groups, "empty": len(groups) == 0}
        )

    from ..render.base import gradient_bg, render_html, render_template

    html = render_template(
        "white_market.html",
        body_bg=gradient_bg("blue"),
        width=420,
        categories=category_list,
    )
    return await render_html(html, 420)


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
        ticket = await FishingUser.get_item(
            user_id, "black_market_extra_ticket", "ticket"
        )
        if ticket and int(ticket.get("count", 0) or 0) > 0:
            ok = await FishingUser.remove_item(
                user_id, "black_market_extra_ticket", "ticket", 1
            )
            if not ok:
                return False, "今天已经进行过黑商交换了", True
            used_extra_ticket = True
        else:
            return False, "今天已经进行过黑商交换了", True

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
    result = await add_fish_to_user(
        user_id,
        [(actual_target.name, actual_target.rarity, actual_target.numeric_id, 1)],
        auto_display=not inherited_lock,
    )
    if inherited_lock:
        await FishingUser.toggle_lock_by_numeric_id(
            user_id, actual_target.numeric_id, True
        )
    await FishingExchangeRecord.create_black_record(user_id, source, actual_target)

    messages = list(result["messages"])
    if used_extra_ticket:
        messages.append("票券：已消耗 1 张黑商额外兑换券")
    messages.extend(result["achievement_messages"])

    lock_hint = "（已自动锁定）" if inherited_lock else ""
    msg = (
        f"黑商交换成功：消耗 {source.name}({source.rarity}) "
        f"→ 获得 {actual_target.name}({actual_target.rarity}){lock_hint}"
    )
    if randomized:
        msg += f"\n黑商动了手脚，目标从 {target.name} 变成了 {actual_target.name}。"
    if messages:
        msg += "\n" + "\n".join(messages)
    return True, msg, True


async def white_market_exchange(user_id: str, exchange_input: str) -> tuple[bool, str, bool]:
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

    record = await FishingExchangeRecord.find_active_reverse(source, target)
    if not record:
        return False, "没有找到对应的有效黑商逆交换记录。", True

    gift_count = await FishingUser.get_gift_count(user_id)
    if gift_count >= DAILY_GIFT_LIMIT:
        return False, "今天已经不能再赠送了，无法使用白商交换。", True

    await FishingUser.remove_fish_by_numeric_id(user_id, source.numeric_id, 1)
    await FishingUser.increment_gift_count(user_id)
    result = await add_fish_to_user(
        user_id,
        [(target.name, target.rarity, target.numeric_id, 1)],
    )
    await FishingExchangeRecord.invalidate_record(record.id, user_id)

    helper_nickname = await _get_nickname(record.user_id)
    messages = list(result["messages"])
    messages.extend(result["achievement_messages"])
    msg = (
        f"白商交换成功：消耗 {source.name}({source.rarity}) "
        f"→ 获得 {target.name}({target.rarity})\n"
        f"{helper_nickname} 帮助了你，对应黑商记录已失效。"
    )
    if messages:
        msg += "\n" + "\n".join(messages)
    return True, msg, True
