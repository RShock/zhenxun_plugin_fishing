"""
公告服务 — 活跃群广播与自动公告。

提供手动广播指令和自动公告函数，供特殊事件（如星空艇建设）调用。
"""

from __future__ import annotations

import asyncio

from nonebot import get_bot, logger

from ..models import FishingActiveGroup

ANNOUNCEMENT_PREFIX = "🎣 钓鱼公告"


async def broadcast_to_active_groups(message: str) -> tuple[int, int]:
    """向所有活跃群广播消息。

    Returns:
        (success_count, fail_count)
    """
    group_ids = await FishingActiveGroup.get_active_group_ids()
    if not group_ids:
        logger.info("[公告] 没有活跃群，跳过广播")
        return 0, 0

    try:
        bot = get_bot()
    except Exception:
        logger.warning("[公告] 无法获取 bot 实例，跳过广播")
        return 0, len(group_ids)

    full_message = f"{ANNOUNCEMENT_PREFIX}\n{message}"
    success = 0
    fail = 0

    for idx, group_id in enumerate(group_ids):
        try:
            result = await bot.call_api(
                "send_group_msg",
                group_id=int(group_id),
                message=full_message,
            )
            # 路由层在限额/主Bot不可用等情况下会静默返回 None
            if result is None:
                logger.warning(
                    f"[公告] 群 {group_id} 发送返回 None（路由拒绝/不可用）"
                )
                fail += 1
            else:
                success += 1
        except Exception as e:
            logger.warning(f"[公告] 发送到群 {group_id} 失败: {e}")
            fail += 1

        if idx < len(group_ids) - 1:
            await asyncio.sleep(0.3)

    logger.info(f"[公告] 广播完成: 成功 {success} 个群, 失败 {fail} 个群")
    return success, fail


async def auto_announce(message: str) -> None:
    """自动公告：对活跃群进行自动广播。

    用于特殊事件触发，如星空艇建设、迷途风替换晴天等。
    """
    await broadcast_to_active_groups(message)


async def announce_starry_ship_build(
    user_id: str, nickname: str, bonus_count: int
) -> None:
    """星空艇建设自动公告。

    每次有玩家建设星空艇时触发。第10次建设时额外触发迷途风替换晴天公告。
    """
    from ..starry import STARRY_BONUS_VALUE, STARRY_MAX_LAYERS

    # 每次建设都公告
    if bonus_count < STARRY_MAX_LAYERS:
        message = (
            f"✨ 玩家「{nickname}」建设了星空艇！\n"
            f"全服1-10图+S1钓鱼速度加成提升至 +{bonus_count * STARRY_BONUS_VALUE}%"
            f"（当前 {bonus_count}/{STARRY_MAX_LAYERS} 层）"
        )
    else:
        # 第10次建设，达到上限，触发迷途风替换晴天公告
        message = (
            f"✨ 玩家「{nickname}」建设了星空艇！\n"
            f"星空艇加成已达 {STARRY_MAX_LAYERS} 层上限"
            f"（+{STARRY_MAX_LAYERS * STARRY_BONUS_VALUE}%）！\n"
            f"🌀 场1（图1-10 + 猫猫乐园）的晴天已被迷途风全部替换！\n"
            f"从明天起，每次天气生成时，图1-10将有5张随机天气、5张迷途风，"
            f"猫猫乐园的晴天也将被替换为迷途风。"
        )

    await auto_announce(message)
