from zhenxun.services.log import logger

from ..config import ConfigManager
from ..models import FishingUser
from .user_lock_service import user_operation_lock


async def get_or_create_user(user_id: str, nickname: str = "") -> FishingUser:
    async with user_operation_lock([user_id], "玩家初始化/修复"):
        user, created = await FishingUser.get_or_create_user(user_id, nickname)
        if created:
            gift = ConfigManager.get_initial_gift()
            user.rod_level = gift.rod_level
            user.hook_level = gift.hook_level
            user.bait_id = str(gift.bait) if gift.bait else "0"
            user.display_slots = gift.display_slots
            await user.save(
                update_fields=["rod_level", "hook_level", "bait_id", "display_slots"]
            )
            if gift.bait and gift.bait_count > 0:
                await FishingUser.add_item(
                    user_id, str(gift.bait), "bait", gift.bait_count
                )
            logger.info(
                f"用户 {user_id} 初始化，赠送{gift.rod_level}级钓竿、{gift.hook_level}级鱼钩"
            )
        return user


async def get_user(user_id: str) -> FishingUser:
    return await get_or_create_user(user_id)
