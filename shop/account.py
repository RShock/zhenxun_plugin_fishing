"""
商店杂项 — 兑换金币、签到、改名、皮肤管理。
"""

from zhenxun.services.log import logger

from ..config import ConfigManager
from ..models import FishingUser
from ..services import get_or_create_user


async def exchange_to_gold(user_id: str, amount: int) -> tuple[bool, str, int]:
    user = await get_or_create_user(user_id)
    if user.gold < amount:
        return False, f"钓鱼币不足，当前只有 {user.gold} 钓鱼币", 0

    exchange_rate = ConfigManager.get_exchange_rate()
    gold_received = amount * exchange_rate

    user.gold -= amount
    await user.save(update_fields=["gold"])

    from zhenxun.models.user_console import UserConsole

    await UserConsole.add_gold(user_id, gold_received, "fishing_exchange")

    logger.info(f"用户 {user_id} 兑换 {amount} 钓鱼币为 {gold_received} 金币")
    return True, f"成功兑换 {gold_received} 金币！", gold_received


async def check_sign(user_id: str) -> tuple[bool, int, int]:
    return await FishingUser.check_and_sign(user_id)


async def rename_fishing_user(user_id: str, new_name: str) -> tuple[bool, str]:
    if not new_name or len(new_name) > 20:
        return False, "名字长度需要在1-20个字符之间"
    user = await get_or_create_user(user_id)
    user.nickname = new_name
    await user.save(update_fields=["nickname"])
    logger.info(f"用户 {user_id} 改名为 {new_name}")
    return True, f"改名成功！你的新名字是：{new_name}"


async def change_skin(user_id: str, skin_id: str) -> tuple[bool, str]:
    from ..render import _find_skin_file

    skin_file, _ = _find_skin_file(skin_id)
    if not skin_file or not skin_file.exists():
        return False, f"皮肤 {skin_id} 不存在"

    success, message = await FishingUser.change_skin(user_id, skin_id)
    if success:
        logger.info(f"用户 {user_id} 更换皮肤为 {skin_id}")
    return success, message