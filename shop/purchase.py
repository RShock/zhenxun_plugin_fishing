"""
商店购买与升级 — buy_item, 装备升级, 展示栏升级。
"""

from zhenxun.services.log import logger

from ..config import (
    DISPLAY_SLOT_COSTS,
    STARRY_FRAME_UPGRADE_COSTS,
    STARRY_FRAMES_MAX,
    UPGRADE_DISPLAY_COSTS,
    ConfigManager,
)
from ..models import FishingUser
from ..services import auto_fill_new_display_slot, get_or_create_user


async def _upgrade_equipment(user_id: str, equipment_type: str) -> tuple[bool, str]:
    user = await get_or_create_user(user_id)

    if equipment_type == "rod":
        current_level = user.rod_level
        # 商店定价基于基础等级（排除猫猫乐园雕像额外加成）
        pricing_level = user.base_rod_level
        name = "钓竿"
        max_level = 20
        get_price = ConfigManager.get_rod_upgrade_price
        get_name = ConfigManager.get_rod_name
        if current_level == 10:
            from ..starry import has_starry_ship

            if not await has_starry_ship(user_id):
                return False, "需要先在鱼店购买星空艇，才能继续升级 Lv.11 钓竿。"
    else:
        current_level = user.hook_level
        pricing_level = current_level
        name = "鱼钩"
        max_level = 10
        get_price = ConfigManager.get_hook_upgrade_price
        get_name = lambda _: f"{(current_level + 1) * 10}%"

    if current_level >= max_level:
        return False, f"{name}已达到最高等级！"

    price = get_price(pricing_level)
    if user.gold < price:
        return (
            False,
            f"钓鱼币不足，需要 {price} 钓鱼币，还差 {price - user.gold} 钓鱼币",
        )

    user.gold -= price
    if equipment_type == "rod":
        user.rod_level += 1
        await user.save(update_fields=["gold", "rod_level"])
        new_name = get_name(user.rod_level)
        msg = f"{name}升级成功！当前：{new_name}"
    else:
        user.hook_level += 1
        await user.save(update_fields=["gold", "hook_level"])
        msg = f"{name}升级成功！当前速度加成：{user.hook_level * 10}%"

    logger.info(f"用户 {user_id} 升级{name}到 {current_level + 1} 级")
    return True, msg


async def upgrade_rod(user_id: str) -> tuple[bool, str]:
    return await _upgrade_equipment(user_id, "rod")


async def upgrade_hook(user_id: str) -> tuple[bool, str]:
    return await _upgrade_equipment(user_id, "hook")


async def _buy_bait(user_id: str, user, item, count: int) -> tuple[bool, str]:
    actual_count = min(count, user.gold // item.price) if item.price > 0 else count
    if actual_count <= 0:
        return False, f"钓鱼币不足，无法购买 {item.name}"

    total_price = item.price * actual_count
    user.gold -= total_price
    user.bait_id = str(item.id)
    await user.save(update_fields=["gold", "bait_id"])
    await FishingUser.add_item(user_id, str(item.id), "bait", actual_count)

    logger.info(f"用户 {user_id} 购买了 {actual_count} 个 {item.name}")
    if actual_count < count:
        return (
            True,
            f"成功购买 {actual_count} 个 {item.name}！\n(因鱼币不足，原计划购买 {count} 个)",
        )
    return True, f"成功购买 {actual_count} 个 {item.name}！"


async def buy_item(user_id: str, name_or_id: str, count: int = 1) -> tuple[bool, str]:
    if name_or_id.strip() in [
        "增加展示栏位",
        "展示栏位",
        "展示栏",
        "升级展示栏",
        "强化展示栏位",
        "升级星空木框",
        "星空木框",
    ]:
        return await upgrade_display_slots(user_id)

    user = await get_or_create_user(user_id)
    item, item_type = ConfigManager.get_item_by_name_or_id(name_or_id)

    if not item:
        return False, f"未找到物品: {name_or_id}"

    if item_type == "bait":
        return await _buy_bait(user_id, user, item, count)
    elif item_type == "potion":
        return False, "药水无法在鱼店购买，请通过签到、活动或 GM 命令获取"

    return False, "未知物品类型"


async def upgrade_display_slots(user_id: str) -> tuple[bool, str]:
    """万能升级展示框：兼容增加/强化展示栏位、升级星空木框等全部指令。

    规则：
    1. 展示栏位（木框）、猫猫框强化、星空木框 未满 10 的加入校验列表
       （星空木框仅建设星空艇后参与）
    2. 校验列表中凡材料足够的全部升级并扣框
    3. 若一个都升不了，报告校验列表里各自缺多少
    4. 星空木框消耗星辰木框（star_frames）
    """
    user = await get_or_create_user(user_id)
    from ..starry import has_starry_ship

    has_ship = await has_starry_ship(user_id)
    success_messages: list[str] = []
    shortage_messages: list[str] = []
    checked_any = False
    dirty_fields: set[str] = set()

    # ── 1. 增加展示栏位（展示木框）────────────────────────────────────────
    if user.display_slots < 10:
        checked_any = True
        next_slot = user.display_slots + 1
        frames_needed = DISPLAY_SLOT_COSTS.get(next_slot, next_slot - 3)
        owned = int(user.display_frames or 0)
        if owned >= frames_needed:
            user.display_frames = owned - frames_needed
            user.display_slots = next_slot
            dirty_fields.update(["display_frames", "display_slots"])

            auto_fill_msg = ""
            filled = await auto_fill_new_display_slot(user_id, next_slot)
            if filled:
                auto_fill_msg = f"，已自动将{filled}展示到新栏位！"

            logger.info(
                f"用户 {user_id} 用{frames_needed}个展示木框购买了第 {next_slot} 个展示栏"
            )
            success_messages.append(
                f"✅ 增加展示栏位：第 {next_slot} 个，消耗{frames_needed}个展示木框"
                f"{auto_fill_msg}"
            )
        else:
            shortage_messages.append(
                f"❌ 增加展示栏位：展示木框不足，需要{frames_needed}个"
                f"（当前{owned}个），还差{frames_needed - owned}个"
            )

    # ── 2. 强化展示栏位（猫猫框）──────────────────────────────────────────
    # 栏位扩充后可能立刻可强化，因此放在展示栏升级之后再判断
    if (
        user.display_slots > 0
        and user.upgraded_display_count < user.display_slots
        and user.upgraded_display_count < 10
    ):
        checked_any = True
        next_upgrade = user.upgraded_display_count + 1
        frames_needed = UPGRADE_DISPLAY_COSTS.get(next_upgrade, next_upgrade)
        owned = int(user.cat_frames or 0)
        if owned >= frames_needed:
            user.cat_frames = owned - frames_needed
            user.upgraded_display_count = next_upgrade
            dirty_fields.update(["cat_frames", "upgraded_display_count"])

            logger.info(
                f"用户 {user_id} 用{frames_needed}个猫猫框强化了第 {next_upgrade} 个展示栏"
            )
            success_messages.append(
                f"✅ 强化展示栏位：第 {next_upgrade} 个，消耗{frames_needed}个猫猫框\n"
                f"展示收益最高的鱼将获得3倍收益！"
            )
        else:
            shortage_messages.append(
                f"❌ 强化展示栏位：猫猫框不足，需要{frames_needed}个"
                f"（当前{owned}个），还差{frames_needed - owned}个"
            )

    # ── 3. 升级星空木框（星辰木框）────────────────────────────────────────
    current_starry = int(user.starry_frames or 0)
    if has_ship and current_starry < STARRY_FRAMES_MAX:
        checked_any = True
        next_level = current_starry + 1
        frames_needed = STARRY_FRAME_UPGRADE_COSTS.get(next_level, next_level)
        owned = int(user.star_frames or 0)
        if owned >= frames_needed:
            user.star_frames = owned - frames_needed
            user.starry_frames = next_level
            dirty_fields.update(["star_frames", "starry_frames"])

            logger.info(
                f"用户 {user_id} 用{frames_needed}个星辰木框升级星空木框至 {next_level}"
            )
            success_messages.append(
                f"✅ 升级星空木框：第 {next_level} 个，消耗{frames_needed}个星辰木框\n"
                f"最贵的鱼展示收益提升至 4 倍！（{next_level}/{STARRY_FRAMES_MAX}）"
            )
        else:
            shortage_messages.append(
                f"❌ 升级星空木框：星辰木框不足，需要{frames_needed}个"
                f"（当前{owned}个），还差{frames_needed - owned}个"
            )

    if not checked_any:
        return True, "所有展示相关升级已达上限！"

    if success_messages:
        await user.save(update_fields=sorted(dirty_fields))
        return True, "\n".join(success_messages)

    return True, "\n".join(shortage_messages)
