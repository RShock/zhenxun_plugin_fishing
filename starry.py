"""星空钓鱼解锁与判定。"""

import asyncio
from datetime import datetime

from .models import BuffEffect, FishingBuff, FishingUser
from .services import get_or_create_user

STARRY_LOCATION_IDS = {str(i) for i in range(11, 21)}
STARRY_SHIP_ITEM_ID = "starship"
STARRY_SHIP_ITEM_TYPE = "starry_unlock"
STARRY_SHIP_COST = 600000
STARRY_BONUS_VALUE = 5  # 每位玩家解锁为全服 1-10 图提供 +5% 速度加成
STARRY_MAX_LAYERS = 10  # 星空艇加成最多 10 层（即 50%）
STARRY_BONUS_END_YEAR = 2099  # 永久 buff 的远期 end_time 年份（避开 Windows 时间戳上限 ~3001）


def is_starry_location(location_id: str) -> bool:
    return str(location_id) in STARRY_LOCATION_IDS


async def has_starry_ship(user_id: str) -> bool:
    return await FishingUser.has_item(
        user_id, STARRY_SHIP_ITEM_ID, STARRY_SHIP_ITEM_TYPE
    )


async def get_starry_bonus_count() -> int:
    """当前生效的星空艇加成层数（最多 10 层）。"""
    now = datetime.now()
    buff = await FishingBuff.filter(
        target_type=BuffEffect.TARGET_TYPE_GLOBAL,
        buff_type=BuffEffect.BUFF_TYPE_STARRY_BONUS,
        start_time__lte=now,
        end_time__gt=now,
    ).first()
    if buff is None:
        return 0
    return min(buff.value // STARRY_BONUS_VALUE, STARRY_MAX_LAYERS)


async def update_starry_bonus_buff() -> tuple[int, bool]:
    """每次新玩家建设星空艇时叠加 1 层全局 buff（最多 10 层）。

    Returns:
        (当前层数, 本次是否实际叠层)。已达上限时不再叠层，第二项为 False。

    采用单条记录更新机制：首个玩家创建记录，后续玩家累加 value 并刷新描述，
    不再为每个玩家创建独立记录，避免 start_time 被重置导致历史时段失效。
    """
    now = datetime.now()
    far_future = datetime(STARRY_BONUS_END_YEAR, 12, 31, 23, 59, 59)
    buff = await FishingBuff.filter(
        target_type=BuffEffect.TARGET_TYPE_GLOBAL,
        buff_type=BuffEffect.BUFF_TYPE_STARRY_BONUS,
        end_time__gt=now,
    ).first()
    if buff is None:
        await FishingBuff.add_global_buff(
            buff_type=BuffEffect.BUFF_TYPE_STARRY_BONUS,
            start_time=now,
            end_time=far_future,
            value=STARRY_BONUS_VALUE,
            description=f"星空艇加成：全服1-10图+S1钓鱼速度+{STARRY_BONUS_VALUE}%",
        )
        return 1, True
    current_layers = min(buff.value // STARRY_BONUS_VALUE, STARRY_MAX_LAYERS)
    if current_layers >= STARRY_MAX_LAYERS:
        # 已满：不改 buff，也不应再触发全服公告
        return STARRY_MAX_LAYERS, False
    new_layers = current_layers + 1
    buff.value = new_layers * STARRY_BONUS_VALUE
    buff.description = (
        f"星空艇加成：全服1-10图+S1钓鱼速度+{new_layers * STARRY_BONUS_VALUE}%"
    )
    await buff.save(update_fields=["value", "description"])
    return new_layers, True


async def build_starry_ship(
    user_id: str, nickname: str = ""
) -> tuple[bool, str]:
    user = await get_or_create_user(user_id)
    if user.rod_level < 10:
        return False, "钓竿达到 Lv.10 后才能建设星空艇。"

    if await FishingUser.has_item(user_id, STARRY_SHIP_ITEM_ID, STARRY_SHIP_ITEM_TYPE):
        return True, "你已经拥有星空艇，可以输入【钓鱼11】前往牛奶河。"

    if user.gold < STARRY_SHIP_COST:
        return (
            False,
            f"建设星空艇需要 {STARRY_SHIP_COST} 钓鱼币，还差 {STARRY_SHIP_COST - user.gold} 钓鱼币。",
        )

    user.gold -= STARRY_SHIP_COST
    await user.save(update_fields=["gold"])
    await FishingUser.add_item(user_id, STARRY_SHIP_ITEM_ID, STARRY_SHIP_ITEM_TYPE, 1)

    # 更新全局 buff：每位新玩家建设叠加 1 层，最多 10 层（即 +50%）
    bonus_count, layer_increased = await update_starry_bonus_buff()
    bonus_pct = bonus_count * STARRY_BONUS_VALUE

    # 触发自动公告：仅在实际叠层时公告；第10次播达上限+迷途风，第11次起不再公告
    # 后台发送，避免群发 sleep 阻塞玩家本人的建设回包
    from .services import announce_starry_ship_build
    from nonebot import logger

    if layer_increased:
        display_name = nickname or user.nickname or user_id

        async def _announce_in_background() -> None:
            try:
                await announce_starry_ship_build(
                    user_id,
                    display_name,
                    bonus_count,
                    layer_increased=True,
                )
            except Exception as e:
                logger.warning(f"[星空艇] 自动公告发送失败: {e}")

        asyncio.create_task(_announce_in_background())

    if layer_increased:
        capped_note = ""
        if bonus_count >= STARRY_MAX_LAYERS:
            capped_note = "（已达 10 层上限，后续建设将无法继续叠加）"
        return (
            True,
            "星空艇建设完成！第二部分【星空钓鱼】已解锁，输入【钓鱼11】前往牛奶河。\n"
            f"✨ 你为全服一阶段地图（1-10 + S1）带来了 +{STARRY_BONUS_VALUE}% 永久速度加成"
            f"（当前累计 {bonus_count} 层，+{bonus_pct}%{capped_note}）。",
        )

    return (
        True,
        "星空艇建设完成！第二部分【星空钓鱼】已解锁，输入【钓鱼11】前往牛奶河。\n"
        f"当前全服星空艇加成已达上限（{STARRY_MAX_LAYERS} 层，+{bonus_pct}%），"
        "本次建设不再叠加速度加成。",
    )
