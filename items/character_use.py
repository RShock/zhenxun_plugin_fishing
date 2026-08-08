"""角色道具的使用逻辑。"""

from ..models import FishingUser
from ..models import user_mutations as mut
from ..services.achievement_service import BIG_FISH_ITEM_ID, BIG_FISH_ITEM_TYPE


async def use_big_fish(user_id: str, count: int = 1, **kwargs) -> tuple[bool, str]:
    """将一个大肥鱼道具放入角色队伍。"""
    user = await FishingUser.get_user(user_id)
    item = mut.get_item_on_user(user, BIG_FISH_ITEM_ID, BIG_FISH_ITEM_TYPE)
    if not item or item.get("count", 0) < 1:
        return False, "你没有可使用的大肥鱼！"

    slots = mut.get_character_slots_on_user(user)
    raw_position = str(kwargs.get("arg") or "").strip()
    if raw_position and raw_position not in {"1", "2", "3"}:
        return False, "角色位置只能是1、2或3！"

    if raw_position:
        position = int(raw_position)
    else:
        try:
            position = slots.index(None) + 1
        except ValueError:
            return (
                False,
                "队伍已满，需要输入“钓鱼使用 大肥鱼 1/2/3”" "来指定他的位置！",
            )

    dirty: set[str] = set()
    if not mut.apply_remove_item(user, BIG_FISH_ITEM_ID, BIG_FISH_ITEM_TYPE, 1, dirty):
        return False, "大肥鱼数量不足，使用失败！"
    # 指定已占用位置时覆盖原角色，但不额外返还被替换角色。
    mut.apply_set_character_slot(user, position, BIG_FISH_ITEM_ID, dirty)
    await mut.save_dirty(user, dirty)
    return True, f"大肥鱼被放在了队伍第{position}位！"
