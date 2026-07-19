"""
赠送系统 — gift_fish, 赠送成就应用。
"""

from zhenxun.services.log import logger

from ..config import DAILY_GIFT_LIMIT, ConfigManager, calculate_fish_price
from ..core.result import add_fish_to_user
from ..models import FishingUser
from ..services import get_or_create_user


async def gift_fish(user_id: str, target_id: str, numeric_id: str) -> tuple[bool, str]:
    numeric_id = numeric_id.strip()

    # 最先检查：目标是否已解锁该鱼图鉴
    # 若目标未解锁且鱼为 UTR，则为 UTR 解锁型赠送，不消耗每日次数
    # 此检查必须在每日次数检查之前，否则次数用完时无法触发 UTR 解锁
    fish = await FishingUser.get_fish_by_numeric_id(user_id, numeric_id)
    if not fish or fish["count"] < 1:
        return False, f"未找到编号为 {numeric_id} 的鱼"

    # 锁定的鱼允许赠送：锁定是发送者对自身背包的保护标记，
    # 赠送后接收者通过 add_fish_to_user 收到的鱼默认为未锁定状态。
    is_utr_unlock_gift = False
    if fish["rarity"] == "UTR":
        target_collected = await FishingUser.is_collected(
            target_id, fish["fish_name"], "UTR"
        )
        if not target_collected:
            is_utr_unlock_gift = True

    # 仅非 UTR 解锁型赠送才检查每日上限
    if not is_utr_unlock_gift:
        gift_count = await FishingUser.get_gift_count(user_id)
        if gift_count >= DAILY_GIFT_LIMIT:
            return False, "今天已经不能再赠送了"

    await FishingUser.remove_fish_by_numeric_id(user_id, fish["numeric_id"], 1)

    result = await add_fish_to_user(
        target_id,
        [(fish["fish_name"], fish["rarity"], fish["numeric_id"], 1)],
    )

    utr_consumed = bool(result["utr_consumed"])
    reward_coins = 0
    if not utr_consumed:
        await FishingUser.increment_gift_count(user_id)
    else:
        fish_data = ConfigManager.get_fish(fish["fish_name"])
        if fish_data:
            # UTR 解锁型赠送奖励：发送者获得 1 倍 UTR 基础价格金币
            reward_coins = calculate_fish_price(fish_data, "UTR", 0)
            await FishingUser.add_gold(user_id, reward_coins)
        else:
            logger.warning(
                f"赠送 UTR 鱼时未找到鱼配置: {fish['fish_name']}，"
                f"发送者 {user_id} 未获得金币奖励"
            )

    target_user = await get_or_create_user(target_id)
    target_name = target_user.nickname or target_id

    messages = []
    messages.extend(result["messages"])
    if result["achievement_messages"]:
        messages.extend([f"{target_name} {m}" for m in result["achievement_messages"]])

    logger.info(
        f"用户 {user_id} 赠送给 {target_id} 一条 {fish['fish_name']}({fish['rarity']})"
        + ("，目标首次获得UTR，已消耗解锁图鉴" if utr_consumed else "")
    )

    msg = f"已将 {fish['fish_name']}({fish['rarity']}) 赠送给 {target_name}"
    if messages:
        msg += "\n" + "\n".join(messages)
    if reward_coins:
        msg += f"\n你帮助 {target_name} 解锁了UTR图鉴，获得 {reward_coins} 金币"
    return True, msg
