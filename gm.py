"""
GM (Game Master) 调试命令模块。

提供超级用户专用的调试/管理功能，所有 GM 函数规范：
- 返回 (bool, str) 元组，分别表示操作是否成功和提示消息
- 使用 logger.info 记录操作日志
- 所有 import 使用相对导入 (.xxx)
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import re

from zhenxun.services.log import logger

from .config import (
    INDEX_RARITY,
    RARITY_MAP,
    ConfigManager,
    generate_fish_numeric_id,
    normalize_fish_numeric_id,
)
from .core.result import add_fish_to_user
from .core.starry_rewards import grant_rewards_for_starry_fish
from .models import FishingUser, FishingWeather
from .services import adjust_gold, earn_gold, set_gold


def _decode_fish_numeric_id(
    numeric_id: str,
) -> tuple[str | None, str | None, str | None, int | None]:
    if not numeric_id:
        return None, None, None, None

    numeric_id = normalize_fish_numeric_id(numeric_id)
    if numeric_id.startswith("s1") and len(numeric_id) == 4:
        loc_id = "S1"
        fish_idx_str = numeric_id[2]
        rarity_idx_str = numeric_id[3]
    elif numeric_id.isdigit():
        if len(numeric_id) >= 4 and numeric_id[:2] == "10":
            loc_id = "10"
            fish_idx_str = numeric_id[2:-1]
            rarity_idx_str = numeric_id[-1]
        elif len(numeric_id) == 3:
            loc_id = numeric_id[0]
            fish_idx_str = numeric_id[1]
            rarity_idx_str = numeric_id[2]
        else:
            return None, None, None, None
    else:
        return None, None, None, None
    try:
        fish_idx = int(fish_idx_str)
        rarity_idx = int(rarity_idx_str)
    except ValueError:
        return None, None, None, None
    rarity = INDEX_RARITY.get(rarity_idx)
    if not rarity:
        return None, None, None, None
    location = ConfigManager.get_location(loc_id)
    if not location:
        return None, None, None, None
    # S1 的 fish_idx 从 0 开始；其他地点从 1 开始
    if loc_id.upper() == "S1":
        if fish_idx < 0 or fish_idx >= len(location.fish_pool):
            return None, None, None, None
        fish_name = location.fish_pool[fish_idx]
    else:
        if fish_idx < 1 or fish_idx > len(location.fish_pool):
            return None, None, None, None
        fish_name = location.fish_pool[fish_idx - 1]
    fish_data = ConfigManager.get_fish(fish_name)
    if not fish_data:
        return None, None, None, None
    return fish_name, rarity, loc_id, fish_idx


async def _clear_user_data(user_id: str) -> None:
    await FishingUser.clear_all_user_data(user_id)


async def gm_reset_user(user_id: str) -> tuple[bool, str]:
    await _clear_user_data(user_id)
    await FishingUser.reset_user(user_id)
    logger.info(f"GM清空用户 {user_id} 所有数据")
    return True, f"已清空用户 {user_id} 的所有钓鱼数据！"


async def gm_add_gold(user_id: str, amount: int = 99999999) -> tuple[bool, str]:
    await adjust_gold(user_id, amount, "gm_add_gold", f"GM调整金币{amount:+d}")
    if amount >= 0:
        logger.info(f"GM给用户 {user_id} 添加 {amount} 钓鱼币")
        return True, f"已给用户 {user_id} 添加 {amount} 钓鱼币！"
    else:
        logger.info(f"GM移除用户 {user_id} 的 {-amount} 钓鱼币")
        return True, f"已移除用户 {user_id} 的 {-amount} 钓鱼币！"


async def gm_add_skin(user_id: str, skin_id: str) -> tuple[bool, str]:
    from .render.fishing_scene import _find_skin_file

    skin_file, _ = _find_skin_file(skin_id)
    if not skin_file or not skin_file.exists():
        return False, f"皮肤 {skin_id} 不存在，可用的皮肤ID请查看 player 文件夹"

    await FishingUser.add_skin(user_id, skin_id)
    await FishingUser.change_skin(user_id, skin_id)
    logger.info(f"GM给用户 {user_id} 添加皮肤 {skin_id}")
    return True, f"已给用户 {user_id} 添加皮肤 {skin_id} 并切换！"


# GM 特殊道具别名 → (canonical_id, kind)
# kind: cat_frame / display_frame / corn / potion / ticket / fragment
# 须覆盖：不在 shop.json 的道具、中文别名、以及会误触稀有度后缀的名字
_SPECIAL_ITEM_ALIASES: dict[str, tuple[str, str]] = {
    "猫框": ("cat_frame", "cat_frame"),
    "猫猫框": ("cat_frame", "cat_frame"),
    "木框": ("display_frame", "display_frame"),
    "展示木框": ("display_frame", "display_frame"),
    "香甜玉米": ("corn", "corn"),
    "玉米": ("corn", "corn"),
    # 药水（含 shop 外道具与别名；item_id 与使用/入库一致）
    "时光药水": ("time_potion", "potion"),
    "时间药水": ("time_potion", "potion"),
    "闪光药水": ("闪光药水", "potion"),
    "回档药水": ("回档药水", "potion"),
    "回溯药水": ("回档药水", "potion"),
    "重置药水": ("回档药水", "potion"),
    "幸运药水": ("幸运药水", "potion"),
    "真多多药水": ("真多多药水", "potion"),
    "多多药水": ("真多多药水", "potion"),
    "许愿药水": ("许愿药水", "potion"),
    # 券 / 碎片
    "UTR自选券": ("utr_select_ticket", "ticket"),
    "utr自选券": ("utr_select_ticket", "ticket"),
    "UTR券": ("utr_select_ticket", "ticket"),
    "utr券": ("utr_select_ticket", "ticket"),
    "utr_select_ticket": ("utr_select_ticket", "ticket"),
    "黑商额外兑换券": ("black_market_extra_ticket", "ticket"),
    "black_market_extra_ticket": ("black_market_extra_ticket", "ticket"),
    "抽奖碎片": ("lottery_fragment_low", "fragment"),
    "中级抽奖碎片": ("lottery_fragment_low", "fragment"),
    "lottery_fragment_low": ("lottery_fragment_low", "fragment"),
    "高级抽奖碎片": ("lottery_fragment_mid", "fragment"),
    "lottery_fragment_mid": ("lottery_fragment_mid", "fragment"),
    "究极抽奖碎片": ("lottery_fragment_high", "fragment"),
    "lottery_fragment_high": ("lottery_fragment_high", "fragment"),
}

_ITEM_DISPLAY_NAMES: dict[str, str] = {
    "cat_frame": "猫框",
    "display_frame": "木框",
    "corn": "香甜玉米",
    "time_potion": "时光药水",
    "闪光药水": "闪光药水",
    "回档药水": "回档药水",
    "幸运药水": "幸运药水",
    "真多多药水": "真多多药水",
    "许愿药水": "许愿药水",
    "utr_select_ticket": "UTR自选券",
    "black_market_extra_ticket": "黑商额外兑换券",
    "lottery_fragment_low": "中级抽奖碎片",
    "lottery_fragment_mid": "高级抽奖碎片",
    "lottery_fragment_high": "究极抽奖碎片",
}


def _item_display_name(item_id: str) -> str:
    return _ITEM_DISPLAY_NAMES.get(item_id, item_id)


def _parse_item_input(item_input: str) -> tuple[str, str | None]:
    """解析 GM 物品名。

    返回 ``(canonical_id, kind)``：
    - kind 为 ``cat_frame`` / ``display_frame`` / ``corn`` / ``potion`` /
      ``ticket`` / ``fragment`` / ``bait`` / 稀有度字符串 / ``None``
    - 鱼：``(鱼名, 稀有度)``；未识别道具：``(原文, None)``
    """
    item_input = item_input.strip()
    if not item_input:
        return "", None

    special = _SPECIAL_ITEM_ALIASES.get(item_input)
    if special:
        return special

    potion = ConfigManager.get_potion(item_input)
    if potion:
        return potion.name, "potion"
    bait = ConfigManager.get_bait(item_input)
    if bait:
        return bait.name, "bait"
    for rarity_key in ["utr", "ssr", "ur", "sr", "r", "n"]:
        if item_input.lower().endswith(rarity_key):
            fish_name = item_input[: -len(rarity_key)]
            return fish_name, RARITY_MAP[rarity_key]
    return item_input, None


def parse_gm_item_specs(
    item_blob: str, default_count: int = 1
) -> list[tuple[str, int]]:
    """解析 GM 物品列表，支持逗号/分号分隔与同名累加。

    支持写法：
    - ``真多多药水,幸运药水,时光药水,时光药水,时光药水``
    - ``时光药水x3`` / ``时光药水*3`` / ``时光药水×3``
    - 全局数量通过 ``default_count`` 乘到每一项（无单项后缀时）

    返回按首次出现顺序的 ``[(物品名, 数量), ...]``。
    """
    import re

    blob = (item_blob or "").strip()
    if not blob:
        return []

    # 含分隔符 → 多物品；否则整段当作单物品（可带 xN 后缀）
    parts = re.split(r"[,，;；]+", blob)
    merged: dict[str, int] = {}
    order: list[str] = []
    suffix_re = re.compile(
        r"^(?P<name>.+?)\s*[xX×*]\s*(?P<cnt>-?\d+)\s*$"
    )

    for raw in parts:
        part = raw.strip()
        if not part:
            continue
        m = suffix_re.match(part)
        if m:
            name = m.group("name").strip()
            cnt = int(m.group("cnt"))
        else:
            name = part
            cnt = default_count
        if not name:
            continue
        if name not in merged:
            order.append(name)
            merged[name] = 0
        merged[name] += cnt
    return [(name, merged[name]) for name in order]


def _token_is_qq_cluster(token: str) -> bool:
    """token 是否整段为 QQ 列表（可含逗号分隔）。"""
    import re

    parts = [p for p in re.split(r"[,，;；]+", token.strip()) if p]
    return bool(parts) and all(p.isdigit() and 5 <= len(p) <= 13 for p in parts)


def parse_gm_add_body(body: str) -> tuple[list[tuple[str, int]], str]:
    """从 ``gm添加`` 命令正文解析物品规格与目标残留文本。

    正文示例：
    - ``真多多药水,幸运药水,时光药水,时光药水,时光药水 1 3086773658``
    - ``时光药水 2 @用户``（@ 通常不在 plaintext，目标由 handler 另取）
    - ``小鲫鱼sr 10 全服``

    解析策略（从右往左）：
    1. 连续吃掉 QQ 簇 / 「全服」作为目标
    2. 若剩余末尾是整数，视为全局数量
    3. 左侧整段作为物品列表（支持逗号多物品）

    返回 ``(item_specs, target_text)``。
    """
    import re

    text = (body or "").strip()
    if not text:
        return [], ""

    tokens = [t for t in re.split(r"\s+", text) if t]
    has_all = False
    qq_ids: list[str] = []
    seen_qq: set[str] = set()

    # 从右往左剥离目标
    while tokens:
        last = tokens[-1]
        if last == "全服":
            has_all = True
            tokens.pop()
            continue
        if _token_is_qq_cluster(last):
            # 从右剥离：整簇插入队首，簇内保持左→右顺序
            cluster: list[str] = []
            for p in re.split(r"[,，;；]+", last):
                p = p.strip()
                if p and p not in seen_qq:
                    seen_qq.add(p)
                    cluster.append(p)
            qq_ids = cluster + qq_ids
            tokens.pop()
            continue
        break

    # 剩余末尾若为整数 → 全局数量（单独一个数字不当物品名）
    global_count = 1
    if tokens and re.fullmatch(r"-?\d+", tokens[-1]):
        if len(tokens) >= 2:
            global_count = int(tokens[-1])
            tokens = tokens[:-1]
        else:
            # 仅一个数字：无有效物品
            tokens = []

    item_blob = " ".join(tokens)
    specs = parse_gm_item_specs(item_blob, default_count=global_count)

    target_bits: list[str] = []
    if has_all:
        target_bits.append("全服")
    if qq_ids:
        target_bits.append(" ".join(qq_ids))
    target_text = " ".join(target_bits)
    return specs, target_text


async def gm_add_items(
    user_id: str, item_specs: list[tuple[str, int]]
) -> tuple[bool, str]:
    """按规格列表依次添加多种物品，汇总成功/失败。"""
    if not item_specs:
        return False, "请指定物品名称！"

    success_lines: list[str] = []
    success_details: list[str] = []
    fail_lines: list[str] = []
    for item_name, count in item_specs:
        ok, msg = await gm_add_item(user_id, item_name, count)
        if ok:
            success_lines.append(msg)
            # 部分物品（如星穹流星鱼）会在首行后返回评分/奖励详情。
            # 汇总时保留这些详情，避免只剩下紧凑摘要。
            _, separator, detail = msg.partition("\n")
            if separator and detail.strip():
                success_details.append(f"【{item_name}×{count}】\n{detail.strip()}")
        else:
            fail_lines.append(f"{item_name}×{count}：{msg}")

    if not success_lines and fail_lines:
        return False, "添加失败：\n" + "\n".join(fail_lines)

    # 成功时给出紧凑摘要，并附上有意义的物品详情。
    summary_bits: list[str] = []
    for item_name, count in item_specs:
        summary_bits.append(f"{item_name}×{count}")
    head = f"已给用户 {user_id} 添加：{'、'.join(summary_bits)}"
    if success_details:
        head += "\n" + "\n".join(success_details)
    if fail_lines:
        head += "\n部分失败：\n" + "\n".join(fail_lines)
        return True, head
    return True, head


async def gm_set_gold(user_id: str, amount: int) -> tuple[bool, str]:
    user = await FishingUser.get_user(user_id)
    old_gold = user.gold
    await set_gold(user_id, amount, "gm_set_gold", f"GM设定金币: {old_gold} -> {amount}")
    logger.info(f"GM设定用户 {user_id} 钓鱼币: {old_gold} -> {amount}")
    return True, f"已设定用户 {user_id} 的钓鱼币为 {amount}（原: {old_gold}）"


async def gm_rollback_rod(user_id: str) -> tuple[bool, str]:
    user = await FishingUser.get_user(user_id)
    if user.rod_level <= 0:
        return False, f"用户 {user_id} 鱼竿等级已为0，无法回退"

    old_level = user.rod_level
    new_level = old_level - 1
    user.rod_level = new_level

    forced_location_msg = ""
    if user.fishing_status and isinstance(user.fishing_status, dict):
        current_loc_id = user.fishing_status.get("location_id")
        if current_loc_id:
            current_loc = ConfigManager.get_location(current_loc_id)
            if current_loc and new_level < current_loc.difficulty:
                max_allowed_loc = None
                for loc in ConfigManager.get_locations():
                    if loc.difficulty <= new_level:
                        max_allowed_loc = loc
                if max_allowed_loc:
                    user.fishing_status["location_id"] = max_allowed_loc.id
                    forced_location_msg = (
                        f"\n⚠️ 当前场景{current_loc.name}需要鱼竿Lv.{current_loc.difficulty}，"
                        f"已强制回退到{max_allowed_loc.name}"
                    )
                else:
                    user.fishing_status = None
                    forced_location_msg = "\n⚠️ 没有符合当前等级的场景，已强制结束钓鱼"

    await user.save(update_fields=["rod_level", "fishing_status"])

    rod_name = ConfigManager.get_rod_name(new_level)
    logger.info(f"GM回退用户 {user_id} 鱼竿: Lv.{old_level} -> Lv.{new_level}")

    msg = (
        f"用户 {user_id} 鱼竿回退成功\n"
        f"鱼竿: Lv.{old_level} -> Lv.{new_level} ({rod_name})\n"
        f"当前钓鱼币: {user.gold}"
    )
    if forced_location_msg:
        msg += forced_location_msg
    return True, msg


async def gm_rollback_hook(user_id: str) -> tuple[bool, str]:
    user = await FishingUser.get_user(user_id)
    if user.hook_level <= 0:
        return False, f"用户 {user_id} 鱼钩等级已为0，无法回退"

    old_level = user.hook_level
    new_level = old_level - 1
    user.hook_level = new_level

    await user.save(update_fields=["hook_level"])

    logger.info(f"GM回退用户 {user_id} 鱼钩: Lv.{old_level} -> Lv.{new_level}")

    msg = (
        f"用户 {user_id} 鱼钩回退成功\n"
        f"鱼钩: Lv.{old_level} -> Lv.{new_level}\n"
        f"当前钓鱼币: {user.gold}"
    )
    return True, msg


@dataclass(frozen=True)
class _GmItemSpec:
    item_id: str
    category: str
    display: str
    rarity: str | None = None


_GmItemHandler = Callable[[str, _GmItemSpec, int], Awaitable[tuple[bool, str]]]
_UNKNOWN_ITEM_MESSAGE = (
    "未识别的物品或未指定稀有度！\n"
    "道具：时光/回档/幸运/闪光/真多多/许愿药水、UTR自选券、"
    "黑商额外兑换券、抽奖碎片、玉米、猫框、木框、鱼饵…\n"
    "鱼：物品名+稀有度（如：小鲫鱼sr）"
)


def _parse_gm_item(item_input: str) -> tuple[_GmItemSpec | None, str | None]:
    """解析并校验单个 GM 物品，处理器只接收规范化后的规格。"""
    if not item_input:
        return None, "请指定物品名称！"
    meteor_match = re.match(r"^流星鱼(\d+)$", item_input)
    if meteor_match:
        number = meteor_match.group(1)
        return _GmItemSpec(number, "meteor_fish", f"流星鱼 #{number}"), None

    item_id, kind = _parse_item_input(item_input)
    if not kind:
        return None, _UNKNOWN_ITEM_MESSAGE
    category = "fish" if kind in RARITY_MAP.values() else kind
    rarity = kind if category == "fish" else None
    return _GmItemSpec(
        item_id, category, _item_display_name(item_id), rarity=rarity
    ), None


async def _handle_counter_item(
    user_id: str,
    spec: _GmItemSpec,
    count: int,
    add: Callable[[str, int], Awaitable[None]],
    reduce: Callable[[str, int], Awaitable[bool]],
) -> tuple[bool, str]:
    if count >= 0:
        await add(user_id, count)
        logger.info(f"GM给用户 {user_id} 添加 {count} 个{spec.display}")
        return True, f"已给用户 {user_id} 添加 {count} 个{spec.display}！"
    success = await reduce(user_id, -count)
    if not success:
        return False, f"用户 {user_id} 的{spec.display}不足！"
    logger.info(f"GM减少用户 {user_id} 的 {-count} 个{spec.display}")
    return True, f"已减少用户 {user_id} 的 {-count} 个{spec.display}！"


async def _handle_cat_frame(
    user_id: str, spec: _GmItemSpec, count: int
) -> tuple[bool, str]:
    return await _handle_counter_item(
        user_id, spec, count, FishingUser.add_cat_frames, FishingUser.reduce_cat_frames
    )


async def _handle_display_frame(
    user_id: str, spec: _GmItemSpec, count: int
) -> tuple[bool, str]:
    return await _handle_counter_item(
        user_id,
        spec,
        count,
        FishingUser.add_display_frames,
        FishingUser.reduce_display_frames,
    )


async def _handle_corn(
    user_id: str, spec: _GmItemSpec, count: int
) -> tuple[bool, str]:
    return await _handle_counter_item(
        user_id, spec, count, FishingUser.add_corn, FishingUser.reduce_corn
    )


async def _handle_inventory_item(
    user_id: str, spec: _GmItemSpec, count: int
) -> tuple[bool, str]:
    unit = {"potion": "瓶", "ticket": "张", "fragment": "个"}[spec.category]
    if count >= 0:
        await FishingUser.add_item(user_id, spec.item_id, spec.category, count)
        logger.info(f"GM给用户 {user_id} 添加 {count}{unit}{spec.display}")
        return True, f"已给用户 {user_id} 添加 {count}{unit}{spec.display}！"
    success = await FishingUser.remove_item(
        user_id, spec.item_id, spec.category, -count
    )
    if not success:
        return False, f"用户 {user_id} 的{spec.display}不足！"
    logger.info(f"GM减少用户 {user_id} 的 {-count}{unit}{spec.display}")
    return True, f"已减少用户 {user_id} 的 {-count}{unit}{spec.display}！"


async def _handle_bait(
    user_id: str, spec: _GmItemSpec, count: int
) -> tuple[bool, str]:
    bait = ConfigManager.get_bait(spec.item_id)
    if not bait:
        return False, f"未找到鱼饵：{spec.item_id}"
    bait_spec = _GmItemSpec(str(bait.id), "bait", bait.name)
    if count >= 0:
        await FishingUser.add_item(user_id, bait_spec.item_id, "bait", count)
        logger.info(f"GM给用户 {user_id} 添加 {count} 个{bait.name}")
        return True, f"已给用户 {user_id} 添加 {count} 个{bait.name}！"
    success = await FishingUser.remove_item(user_id, bait_spec.item_id, "bait", -count)
    if not success:
        return False, f"用户 {user_id} 的{bait.name}不足！"
    logger.info(f"GM减少用户 {user_id} 的 {-count} 个{bait.name}")
    return True, f"已减少用户 {user_id} 的 {-count} 个{bait.name}！"


def _consume_starry_pool(
    pool: list, target: str, remaining: int
) -> tuple[list, int]:
    kept = []
    for item in pool:
        item_id = f"{int(item.get('id', 0)):06d}"
        if remaining > 0 and item_id == target:
            remaining -= 1
        else:
            kept.append(item)
    return kept, remaining


async def _remove_starry_fish(user_id: str, number: str, count: int) -> bool:
    user = await FishingUser.get_user(user_id)
    target = f"{int(number):06d}"
    backpack, remaining = _consume_starry_pool(
        list(user.starry_fish or []), target, count
    )
    exhibition, remaining = _consume_starry_pool(
        list(user.starry_exhibition or []), target, remaining
    )
    if remaining > 0:
        return False
    user.starry_fish = backpack
    user.starry_exhibition = exhibition
    await user.save(update_fields=["starry_fish", "starry_exhibition"])
    return True


def _format_starry_reward_entry(reward: dict) -> str:
    """把单条星穹奖励 dict 格式化为可读文本。"""
    name = str(reward.get("name") or reward.get("key") or "未知奖励")
    count = int(reward.get("count", 1) or 1)
    parts = [f"{name}×{count}"]
    if reward.get("score_bonus"):
        parts.append(f"努力值+{reward['score_bonus']}")
    if reward.get("upgrade_from"):
        parts.append(f"碎片合成:{reward['upgrade_from']}")
    if reward.get("granted") is False:
        parts.append("发放失败")
    return " ".join(parts)


def _format_gm_meteor_reward_feedback(
    number: str,
    per_fish_rewards: list[list[dict]],
) -> str:
    """汇总 GM 添加流星鱼时的评分/奖池/抽奖反馈。"""
    from .core.starry_system import REWARD_POOL_NAMES, score_starry_fish

    scored = score_starry_fish(number)
    pool_name = REWARD_POOL_NAMES.get(scored.reward_pool, scored.reward_pool)
    lines = [
        f"评分: {scored.display_score} | 奖池: {pool_name}",
    ]
    if scored.reward_pool == "none":
        lines.append("奖励: 无（评分为0不进奖池）")
        return "\n".join(lines)

    if len(per_fish_rewards) == 1:
        rewards = per_fish_rewards[0]
        if not rewards:
            lines.append("奖励: 本条未抽中/未发放")
        else:
            lines.append(
                "奖励: " + "；".join(_format_starry_reward_entry(r) for r in rewards)
            )
        return "\n".join(lines)

    for idx, rewards in enumerate(per_fish_rewards, 1):
        if not rewards:
            lines.append(f"#{idx}: 未抽中/未发放")
        else:
            detail = "；".join(_format_starry_reward_entry(r) for r in rewards)
            lines.append(f"#{idx}: {detail}")
    return "\n".join(lines)


async def _handle_meteor_fish(
    user_id: str, spec: _GmItemSpec, count: int
) -> tuple[bool, str]:
    number = spec.item_id
    is_starry = int(number) <= 999_999
    if count >= 0:
        per_fish_rewards: list[list[dict]] = []
        for _ in range(count):
            if is_starry:
                await FishingUser.add_starry_fish(user_id, number, "GM")
                rewards = await grant_rewards_for_starry_fish(user_id, number)
                per_fish_rewards.append(list(rewards or []))
            else:
                await FishingUser.add_item(user_id, number, "meteor_fish", 1)
        logger.info(f"GM给用户 {user_id} 添加 {count} 条流星鱼 #{number}")
        msg = f"已给用户 {user_id} 添加 {count} 条流星鱼 #{number}！"
        if is_starry:
            msg += "\n" + _format_gm_meteor_reward_feedback(number, per_fish_rewards)
        else:
            msg += "\n（旧版流星鱼道具，不走星穹奖池）"
        return True, msg

    success = (
        await _remove_starry_fish(user_id, number, -count)
        if is_starry
        else await FishingUser.remove_item(user_id, number, "meteor_fish", -count)
    )
    if not success:
        return False, f"用户 {user_id} 的流星鱼 #{number} 不足！"
    logger.info(f"GM减少用户 {user_id} 的 {-count} 条流星鱼 #{number}")
    return True, f"已减少用户 {user_id} 的 {-count} 条流星鱼 #{number}！"


def _find_fish_location(fish_name: str) -> tuple[str, int]:
    for loc in ConfigManager.get_locations():
        for idx, fish_id in enumerate(loc.fish_pool, 1):
            if fish_id == fish_name:
                fish_idx = idx - 1 if loc.id.upper() == "S1" else idx
                return loc.id, fish_idx
    return "1", 1


async def _handle_fish(
    user_id: str, spec: _GmItemSpec, count: int
) -> tuple[bool, str]:
    fish_name = spec.item_id
    rarity = spec.rarity or ""
    if not ConfigManager.get_fish(fish_name):
        return False, f"未找到鱼：{fish_name}"
    loc_id, fish_idx = _find_fish_location(fish_name)
    numeric_id = generate_fish_numeric_id(loc_id, fish_idx, rarity)
    if count < 0:
        current = await FishingUser.get_fish_by_numeric_id(user_id, numeric_id)
        if not current or current.get("count", 0) < -count:
            return False, f"用户 {user_id} 的 {fish_name}({rarity}) 数量不足！"
        await FishingUser.remove_fish_by_numeric_id(user_id, numeric_id, -count)
        logger.info(f"GM减少用户 {user_id} 的 {-count} 条 {fish_name}({rarity})")
        return True, f"已减少用户 {user_id} 的 {-count} 条 {fish_name}({rarity})！"

    result = await add_fish_to_user(
        user_id, [(fish_name, rarity, numeric_id, count)]
    )
    logger.info(f"GM给用户 {user_id} 添加 {count} 条 {fish_name}({rarity})")
    msg = f"已给用户 {user_id} 添加 {count} 条 {fish_name}({rarity})！"
    extra = [*result["messages"], *result["achievement_messages"]]
    return (True, msg + ("\n" + "\n".join(extra) if extra else ""))


_GM_ITEM_HANDLERS: dict[str, _GmItemHandler] = {
    "cat_frame": _handle_cat_frame,
    "display_frame": _handle_display_frame,
    "corn": _handle_corn,
    "potion": _handle_inventory_item,
    "ticket": _handle_inventory_item,
    "fragment": _handle_inventory_item,
    "bait": _handle_bait,
    "meteor_fish": _handle_meteor_fish,
    "fish": _handle_fish,
}


async def gm_add_item(user_id: str, item_input: str, count: int) -> tuple[bool, str]:
    """解析并校验物品后，按类别分发给显式注册的处理器。"""
    if not isinstance(count, int) or isinstance(count, bool):
        return False, "请输入有效的数量！"
    spec, error = _parse_gm_item(item_input)
    if error:
        return False, error
    handler = _GM_ITEM_HANDLERS[spec.category]
    return await handler(user_id, spec, count)


async def gm_give_fish(user_id: str, fish_ids_str: str) -> tuple[bool, str]:
    if not fish_ids_str:
        return False, "格式：gm发鱼 鱼ID1,鱼ID2,... @用户"

    import re

    id_parts = re.split(r"[,;，；]", fish_ids_str)
    id_parts = [p.strip() for p in id_parts if p.strip()]

    if not id_parts:
        return False, "请指定鱼的ID！格式：gm发鱼 111,113 @用户"

    fish_entries: list[tuple[str, str, str, int]] = []
    success_list = []
    failed_list = []
    for nid in id_parts:
        fish_name, rarity, loc_id, fish_idx = _decode_fish_numeric_id(nid)
        if not fish_name or not rarity:
            failed_list.append(f"{nid}(无效ID)")
            continue
        numeric_id = generate_fish_numeric_id(loc_id, fish_idx, rarity)
        fish_entries.append((fish_name, rarity, numeric_id, 1))
        success_list.append(f"{fish_name}({rarity})")

    result_extra = []
    if fish_entries:
        result = await add_fish_to_user(user_id, fish_entries)
        if result["messages"]:
            result_extra.extend(result["messages"])
        if result["achievement_messages"]:
            result_extra.extend(result["achievement_messages"])
        for entry in fish_entries:
            logger.info(f"GM给用户 {user_id} 发鱼 {entry[0]}({entry[1]})")

    result_parts = []
    if success_list:
        result_parts.append(f"已给用户 {user_id} 发送：{', '.join(success_list)}")
    if failed_list:
        result_parts.append(f"发送失败：{', '.join(failed_list)}")
    if result_extra:
        result_parts.extend(result_extra)

    if not success_list:
        return False, "; ".join(result_parts)
    return True, "\n".join(result_parts)


async def gm_weather_info() -> tuple[bool, str]:
    from .weather_service import _format_hour

    weathers_map = await FishingWeather.get_all_today_weathers()
    if not weathers_map:
        from .weather_service import _weather_date

        today = _weather_date()
        return True, f"今日({today})无天气记录"
    from .weather_service import _weather_date

    today = _weather_date()
    lines = [f"今日({today})天气:"]
    for w in weathers_map.values():
        st = _format_hour(w.start_time) + "点" if w.start_time else "--"
        et = _format_hour(w.end_time, is_end=True) + "点" if w.end_time else "--"
        lines.append(f"  {w.location_id}: {w.weather_type} ({st}~{et})")
    return True, "\n".join(lines)


async def gm_weather_reset() -> tuple[bool, str]:
    from datetime import datetime, time, timedelta

    from .models import FishingBuff
    from .weather_service import _format_hour, _weather_date, generate_daily_weather

    today = _weather_date()
    today_23pm = datetime.combine(today, time(23, 0))
    tomorrow_23pm = today_23pm + timedelta(days=1)

    weathers = await FishingWeather.filter(
        start_time__gte=today_23pm, start_time__lt=tomorrow_23pm
    ).all()
    for w in weathers:
        if w.weather_type != "sunny" and w.start_time and w.end_time:
            await FishingBuff.filter(
                target_type="location",
                target_id=w.location_id,
                start_time=w.start_time,
            ).delete()
    deleted = await FishingWeather.filter(
        start_time__gte=today_23pm, start_time__lt=tomorrow_23pm
    ).delete()
    await generate_daily_weather()
    new_weathers = await FishingWeather.filter(
        start_time__gte=today_23pm, start_time__lt=tomorrow_23pm
    ).all()
    lines = [f"已删除{deleted}条旧天气，重新生成:"]
    for w in new_weathers:
        st = _format_hour(w.start_time) + "点" if w.start_time else "--"
        et = _format_hour(w.end_time, is_end=True) + "点" if w.end_time else "--"
        lines.append(f"  {w.location_id}: {w.weather_type} ({st}~{et})")
    return True, "\n".join(lines)


async def gm_check_achievements(user_id: str) -> tuple[bool, str]:
    """重新检测并补发遗漏的成就奖励。

    适用于以下场景: 因 bug 导致成就未触发、直接修改数据库后成就状态不一致等。
    遍历所有场景的所有成就检查，只补发未标记为已完成的成就。
    """
    from .services import check_all_achievements

    result = await check_all_achievements(user_id)
    if result["coins"] > 0:
        await earn_gold(user_id, result["coins"], "gm_achievement", "GM补发成就奖励")
    if result["coins"] > 0 or result["messages"]:
        logger.info(
            f"GM补成就: 用户 {user_id} 收到 {result['coins']} 金币, "
            f"{len(result['messages'])} 条成就"
        )
        lines = [f"用户 {user_id} 成就补发结果:"]
        if result["messages"]:
            lines.append(f"  +{result['coins']} 金币，{len(result['messages'])} 条成就")
        else:
            lines.append(f"  +{result['coins']} 金币")
        return True, "\n".join(lines)
    return True, f"用户 {user_id} 所有成就已是最新状态，无需补发"


async def gm_add_gold_all(amount: int) -> tuple[bool, str]:
    """给全服所有用户添加/移除钓鱼币。"""
    users = await FishingUser.all()
    success_count = 0
    for user in users:
        await adjust_gold(user.user_id, amount, "gm_add_gold_all", f"GM全服调整{amount:+d}")
        success_count += 1
    logger.info(f"GM全服发钱: {success_count} 个用户, 每人 {amount}")
    if amount >= 0:
        return True, f"已给全服 {success_count} 个用户每人添加 {amount} 钓鱼币！"
    else:
        return True, f"已移除全服 {success_count} 个用户每人 {-amount} 钓鱼币！"


async def gm_add_item_all(item_input: str, count: int) -> tuple[bool, str]:
    """给全服所有用户添加物品。

    复用 gm_add_item 逐用户执行，只统计成功/失败数量，不收集成就消息。
    """
    if not item_input:
        return False, "请指定物品名称！"

    users = await FishingUser.all()
    success_count = 0
    fail_count = 0
    for user in users:
        success, _ = await gm_add_item(user.user_id, item_input, count)
        if success:
            success_count += 1
        else:
            fail_count += 1

    logger.info(
        f"GM全服添加物品 {item_input} x{count}: "
        f"成功 {success_count}, 失败 {fail_count}"
    )
    msg = f"已给全服 {success_count} 个用户添加 {item_input} x{count}！"
    if fail_count > 0:
        msg += f"\n失败：{fail_count} 个用户（物品不足或无效）"
    return True, msg


async def gm_give_fish_all(fish_ids_str: str) -> tuple[bool, str]:
    """给全服所有用户按鱼ID发鱼。

    复用 gm_give_fish 逐用户执行，只统计成功数量。
    """
    if not fish_ids_str:
        return False, "请指定鱼的ID！格式：gm发鱼 鱼ID1,鱼ID2 全服"

    users = await FishingUser.all()
    success_count = 0
    for user in users:
        success, _ = await gm_give_fish(user.user_id, fish_ids_str)
        if success:
            success_count += 1

    logger.info(
        f"GM全服发鱼 {fish_ids_str}: 成功 {success_count}/{len(users)}"
    )
    return True, f"已给全服 {success_count}/{len(users)} 个用户发送鱼 {fish_ids_str}！"


async def gm_add_skin_all(skin_id: str) -> tuple[bool, str]:
    """给全服所有用户添加并切换皮肤。"""
    from .render.fishing_scene import _find_skin_file

    skin_file, _ = _find_skin_file(skin_id)
    if not skin_file or not skin_file.exists():
        return False, f"皮肤 {skin_id} 不存在，可用的皮肤ID请查看 player 文件夹"

    users = await FishingUser.all()
    for user in users:
        await FishingUser.add_skin(user.user_id, skin_id)
        await FishingUser.change_skin(user.user_id, skin_id)

    logger.info(f"GM全服添加皮肤 {skin_id} 给 {len(users)} 个用户")
    return True, f"已给全服 {len(users)} 个用户添加皮肤 {skin_id} 并切换！"


def parse_qq_id_list(text: str) -> list[str]:
    """从文本中解析 QQ 号列表（5-13 位纯数字，支持空格/逗号/分号分隔）。"""
    import re

    ids: list[str] = []
    seen: set[str] = set()
    for token in re.split(r"[\s,，;；]+", (text or "").strip()):
        token = token.strip()
        if token.isdigit() and 5 <= len(token) <= 13 and token not in seen:
            seen.add(token)
            ids.append(token)
    return ids


def _split_leading_qq_ids(tokens: list[str]) -> tuple[list[str], list[str]]:
    """从 token 列表头部连续提取 QQ 号，返回 (qq_ids, remaining_tokens)。"""
    import re

    qq_ids: list[str] = []
    seen: set[str] = set()
    idx = 0
    while idx < len(tokens):
        token = tokens[idx].strip()
        if not token:
            idx += 1
            continue
        parts = [p for p in re.split(r"[,，;；]+", token) if p]
        if not parts or not all(p.isdigit() and 5 <= len(p) <= 13 for p in parts):
            break
        for p in parts:
            if p not in seen:
                seen.add(p)
                qq_ids.append(p)
        idx += 1
    return qq_ids, tokens[idx:]


async def gm_apply_to_users(
    user_ids: list[str],
    action_name: str,
    action,
) -> tuple[bool, str]:
    """对指定 QQ 列表批量执行已有 GM 动作，汇总成功/失败。"""
    if not user_ids:
        return False, "未指定目标 QQ"

    success_ids: list[str] = []
    fail_lines: list[str] = []
    for uid in user_ids:
        ok, msg = await action(uid)
        if ok:
            success_ids.append(uid)
        else:
            fail_lines.append(f"{uid}: {msg}")

    logger.info(
        f"GM批量{action_name}: 目标 {len(user_ids)} 人, "
        f"成功 {len(success_ids)}, 失败 {len(fail_lines)}"
    )
    lines = [f"批量{action_name}完成：成功 {len(success_ids)}/{len(user_ids)} 人"]
    if success_ids:
        preview = ", ".join(success_ids[:20])
        if len(success_ids) > 20:
            preview += f" ...(+{len(success_ids) - 20})"
        lines.append(f"成功QQ：{preview}")
    if fail_lines:
        lines.append("失败明细：")
        lines.extend(f"  {x}" for x in fail_lines[:30])
        if len(fail_lines) > 30:
            lines.append(f"  ...另有 {len(fail_lines) - 30} 条失败")
    return True, "\n".join(lines)
