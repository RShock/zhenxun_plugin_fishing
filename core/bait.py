"""
鱼饵管理 — 最佳鱼饵选择、渐增消耗、鱼饵信息获取、优先鱼饵设定。
"""

from ..config import ConfigManager, FishData
from ..models import FishingUser


async def select_best_bait(user_id: str) -> tuple[int, int]:
    """从用户背包中选择价格最高的鱼饵。"""
    items = await FishingUser.get_user_items(user_id)
    bait_items = [i for i in items if i["item_type"] == "bait" and i["count"] > 0]
    if not bait_items:
        return 0, 0

    best_bait = None
    best_price = -1
    for bi in bait_items:
        bait_data = ConfigManager.get_bait(bi["item_id"])
        if bait_data and bait_data.price > best_price:
            best_price = bait_data.price
            best_bait = bait_data

    if best_bait:
        bait_item = await FishingUser.get_item(user_id, str(best_bait.id), "bait")
        return best_bait.id, bait_item["count"] if bait_item else 0
    return 0, 0


async def select_bait_with_preference(user_id: str) -> tuple[int, int]:
    """根据用户优先设定选择鱼饵，无设定或设定鱼饵不足时回退到最佳鱼饵。"""
    user = await FishingUser.get_user(user_id)
    preferred_id = user.preferred_bait_id

    if preferred_id and preferred_id != "0":
        preferred_item = await FishingUser.get_item(user_id, preferred_id, "bait")
        if preferred_item and preferred_item["count"] > 0:
            return int(preferred_id), preferred_item["count"]

    return await select_best_bait(user_id)


async def set_preferred_bait(user_id: str, bait_input: str) -> tuple[bool, str]:
    """设定优先使用的鱼饵。bait_input 为数字ID或名称，'0'或'取消'清除设定。"""
    if bait_input in ("0", "取消", "自动", "清除"):
        user = await FishingUser.get_user(user_id)
        user.preferred_bait_id = "0"
        await user.save(update_fields=["preferred_bait_id"])
        return True, "已清除优先鱼饵设定，将自动选择最佳鱼饵"

    bait = ConfigManager.get_bait(bait_input)
    if not bait:
        return False, f"未找到鱼饵：{bait_input}"

    user = await FishingUser.get_user(user_id)
    user.preferred_bait_id = str(bait.id)
    user.bait_id = str(bait.id)
    await user.save(update_fields=["preferred_bait_id", "bait_id"])

    bait_item = await FishingUser.get_item(user_id, str(bait.id), "bait")
    count = bait_item["count"] if bait_item else 0
    hint = f"（当前拥有{count}个）" if count > 0 else "（⚠️ 当前未持有该鱼饵）"
    return True, f"已设定优先鱼饵为【{bait.name}】{hint}"


async def consume_bait_incremental(
    user_id: str,
    user,
    bait_usage: dict[str, int],
    buff_messages: list[str],
) -> None:
    """渐增消耗鱼饵并更新消息。"""
    for bait_id_str, consumed in bait_usage.items():
        if consumed <= 0:
            continue
        await FishingUser.remove_item(user_id, bait_id_str, "bait", consumed)
        bait_data = ConfigManager.get_bait(bait_id_str)
        if bait_data:
            remaining_item = await FishingUser.get_item(user_id, bait_id_str, "bait")
            remaining = remaining_item["count"] if remaining_item else 0
            buff_messages.append(
                f"🪱 使用了{consumed}个{bait_data.name}（剩余{remaining}个）"
            )

    best_bait_id, _ = await select_best_bait(user_id)
    user.bait_id = str(best_bait_id)
    await user.save(update_fields=["bait_id"])


async def get_bait_info(user_id: str, user) -> tuple[str, int, int]:
    """获取当前鱼饵的名称、数量和速度加成。"""
    bait = ConfigManager.get_bait(user.bait_id)
    bait_name = ""
    bait_count = 0
    if bait and user.bait_id != "0":
        bait_name = bait.name
        bait_item = await FishingUser.get_item(user_id, str(bait.id), "bait")
        bait_count = bait_item["count"] if bait_item else 0
    return bait_name, bait_count, bait.speed_bonus if bait else 0