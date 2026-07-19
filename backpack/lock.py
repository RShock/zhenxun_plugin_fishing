"""
锁定/解锁系统 — lock_fish, unlock_fish, 批量锁定/解锁辅助。
"""

from ..models import FishingUser

from .selection import FishSelection, parse_fish_selection


async def lock_fish(user_id: str, fish_input: str) -> tuple[bool, str]:
    return await _toggle_fish_lock(user_id, fish_input, lock=True)


async def unlock_fish(user_id: str, fish_input: str) -> tuple[bool, str]:
    return await _toggle_fish_lock(user_id, fish_input, lock=False)


async def auto_lock_fish(user_id: str, fish_input: str) -> int:
    """自动锁鱼：按选择器锁定鱼，只返回锁定的鱼种数（不返回详细信息）。

    供收杆/时光药水结算流程调用，优先级高于自动卖鱼。
    """
    selection = parse_fish_selection(fish_input)
    if selection.is_empty():
        return 0

    total_count = 0
    if selection.select_all:
        total_count = await FishingUser.lock_all(user_id)
        return total_count

    for rarity in selection.all_rarities():
        total_count += await FishingUser.lock_by_rarity(user_id, rarity)

    for prefix in selection.location_prefixes:
        total_count += await FishingUser.lock_by_location_prefix(user_id, prefix)

    for nid in selection.numeric_ids:
        # 先检查鱼是否存在且当前未锁定，避免重复计数
        fish = await FishingUser.get_fish_by_numeric_id(user_id, nid)
        if fish and not fish.get("locked"):
            await FishingUser.toggle_lock_by_numeric_id(user_id, nid, lock=True)
            total_count += 1

    return total_count


async def _toggle_fish_lock(
    user_id: str, fish_input: str, lock: bool
) -> tuple[bool, str]:
    action = "锁定" if lock else "解锁"
    command = "锁鱼" if lock else "解锁"
    selection = parse_fish_selection(fish_input)

    if selection.is_empty():
        return (
            False,
            f"格式：{command} 鱼ID / {command} SR / {command} **3 / {command} 全部",
        )

    if selection.select_all:
        count = await (
            FishingUser.lock_all(user_id) if lock else FishingUser.unlock_all(user_id)
        )
        if count == 0:
            return False, f"没有可{action}的鱼"
        return True, f"已{action}全部鱼，共 {count} 种"

    total_count = 0
    for rarity in selection.all_rarities():
        count = await (
            FishingUser.lock_by_rarity(user_id, rarity)
            if lock
            else FishingUser.unlock_by_rarity(user_id, rarity)
        )
        total_count += count

    # 按位置前缀批量锁定（如 S1** 匹配猫猫乐园全部鱼）
    prefix_count = 0
    for prefix in selection.location_prefixes:
        count = await (
            FishingUser.lock_by_location_prefix(user_id, prefix)
            if lock
            else FishingUser.unlock_by_location_prefix(user_id, prefix)
        )
        prefix_count += count

    done_names, failed_ids = await _lock_unlock_by_ids(
        user_id, selection.numeric_ids, lock=lock
    )

    # 构建成功描述段
    success_segments: list[str] = []
    if total_count > 0:
        rarity_str = ", ".join(selection.all_rarities())
        success_segments.append(f"稀有度 {rarity_str} 共 {total_count} 种")
    if prefix_count > 0:
        prefix_str = ", ".join(selection.location_prefixes)
        success_segments.append(f"位置 {prefix_str} 共 {prefix_count} 种")
    if done_names:
        success_segments.append(f"ID: {', '.join(done_names)}")

    if success_segments:
        msg = f"已{action} {'; '.join(success_segments)}"
        if failed_ids:
            msg += f"\n未找到编号：{', '.join(failed_ids)}"
        return True, msg

    # 没有任何成功匹配
    if failed_ids:
        return False, f"未找到编号为 {', '.join(failed_ids)} 的鱼"

    descriptors: list[str] = []
    if selection.all_rarities():
        descriptors.append(", ".join(selection.all_rarities()))
    if selection.location_prefixes:
        descriptors.append(", ".join(selection.location_prefixes))
    if descriptors:
        return False, f"没有可{action}的 {'/'.join(descriptors)} 鱼"
    return False, f"没有可{action}的鱼"


async def _lock_unlock_by_ids(
    user_id: str, ids: list[str], lock: bool
) -> tuple[list[str], list[str]]:
    done_names: list[str] = []
    failed_ids: list[str] = []
    for nid in ids:
        success = await FishingUser.toggle_lock_by_numeric_id(user_id, nid, lock=lock)
        if success:
            fish = await FishingUser.get_fish_by_numeric_id(user_id, nid)
            if fish:
                done_names.append(f"{fish['fish_name']}({fish['rarity']})")
        else:
            failed_ids.append(nid)
    return done_names, failed_ids


def _build_batch_msg(
    action: str, done_names: list[str], failed_ids: list[str]
) -> tuple[bool, str]:
    if not done_names:
        return False, f"未找到编号为 {', '.join(failed_ids)} 的鱼"
    msg = f"已{action} {len(done_names)} 种：{', '.join(done_names)}"
    if failed_ids:
        msg += f"\n未找到编号：{', '.join(failed_ids)}"
    return True, msg