"""三种核心药水（多多/幸运/闪光）的延后生效行为测试。

旧逻辑：互斥药水生效中时直接拒绝使用（不消耗道具）。
新逻辑：不拒绝，而是将新药水的 start_time 延后到所有互斥 buff 结束之后，
确保新药水拥有完整的 8 小时可用区间。道具照常消耗。
"""

from datetime import datetime, timedelta

from zhenxun.plugins.zhenxun_plugin_fishing.models import (
    BuffEffect,
    FishingBuff,
)
from zhenxun.plugins.zhenxun_plugin_fishing.items.potion_use import (
    use_duoduo_potion,
    use_flash_potion,
    use_lucky_potion,
)

USER_ID = "test_mutex_001"


class TestMutexBehavior:
    async def test_lucky_delayed_when_duoduo_active(self, db):
        """多多生效中喝幸运 → 幸运被消耗，buff 延后到多多结束后生效。"""
        await db.user_get_or_create(USER_ID)
        await db.items_add(USER_ID, "幸运药水", "potion", 5)
        await db.buff_add_user_buff(
            USER_ID, BuffEffect.BUFF_TYPE_DUODUO, 480, 1, "真多多药水"
        )
        ok, msg = await use_lucky_potion(USER_ID)
        assert ok is True
        assert "真多多药水结束后生效" in msg
        item = await db.items_get_item(USER_ID, "幸运药水", "potion")
        assert item["count"] == 4  # 已消耗1瓶

        # 幸运 buff 的 start_time 应在多多 buff 的 end_time 之后
        lucky_buff = await FishingBuff.filter(
            target_id=USER_ID,
            buff_type=BuffEffect.BUFF_TYPE_LUCKY_BOOST,
        ).first()
        assert lucky_buff is not None
        duoduo_buff = await FishingBuff.filter(
            target_id=USER_ID,
            buff_type=BuffEffect.BUFF_TYPE_DUODUO,
        ).first()
        assert lucky_buff.start_time >= duoduo_buff.end_time

    async def test_duoduo_delayed_when_lucky_active(self, db):
        """幸运生效中喝多多 → 多多被消耗，buff 延后到幸运结束后生效。"""
        await db.user_get_or_create(USER_ID)
        await db.items_add(USER_ID, "真多多药水", "potion", 3)
        await db.buff_add_user_buff(
            USER_ID, BuffEffect.BUFF_TYPE_LUCKY_BOOST, 480, 1, "幸运药水"
        )
        ok, msg = await use_duoduo_potion(USER_ID)
        assert ok is True
        assert "幸运药水结束后生效" in msg
        item = await db.items_get_item(USER_ID, "真多多药水", "potion")
        assert item["count"] == 2  # 已消耗1瓶

        duoduo_buff = await FishingBuff.filter(
            target_id=USER_ID,
            buff_type=BuffEffect.BUFF_TYPE_DUODUO,
        ).first()
        assert duoduo_buff is not None
        lucky_buff = await FishingBuff.filter(
            target_id=USER_ID,
            buff_type=BuffEffect.BUFF_TYPE_LUCKY_BOOST,
        ).first()
        assert duoduo_buff.start_time >= lucky_buff.end_time

    async def test_lucky_usable_without_duoduo(self, db):
        await db.user_get_or_create(USER_ID)
        await db.items_add(USER_ID, "幸运药水", "potion", 1)
        ok, msg = await use_lucky_potion(USER_ID)
        assert ok is True
        item = await db.items_get_item(USER_ID, "幸运药水", "potion")
        assert item is None  # 消耗完

    async def test_duoduo_usable_without_lucky(self, db):
        await db.user_get_or_create(USER_ID)
        await db.items_add(USER_ID, "真多多药水", "potion", 1)
        ok, msg = await use_duoduo_potion(USER_ID)
        assert ok is True
        item = await db.items_get_item(USER_ID, "真多多药水", "potion")
        assert item is None  # 消耗完

    async def test_use_lucky_then_duoduo_delayed(self, db):
        """先喝幸运再喝多多 → 多多延后生效，道具照常消耗。"""
        await db.user_get_or_create(USER_ID)
        await db.items_add(USER_ID, "幸运药水", "potion", 1)
        await db.items_add(USER_ID, "真多多药水", "potion", 1)
        ok1, _ = await use_lucky_potion(USER_ID)
        assert ok1 is True
        # 幸运生效中，多多应延后而非拒绝
        ok2, msg2 = await use_duoduo_potion(USER_ID)
        assert ok2 is True
        assert "幸运药水结束后生效" in msg2
        item = await db.items_get_item(USER_ID, "真多多药水", "potion")
        assert item is None  # 已消耗

    async def test_use_duoduo_then_lucky_delayed(self, db):
        """先喝多多再喝幸运 → 幸运延后生效，道具照常消耗。"""
        await db.user_get_or_create(USER_ID)
        await db.items_add(USER_ID, "幸运药水", "potion", 1)
        await db.items_add(USER_ID, "真多多药水", "potion", 1)
        ok1, _ = await use_duoduo_potion(USER_ID)
        assert ok1 is True
        # 多多生效中，幸运应延后而非拒绝
        ok2, msg2 = await use_lucky_potion(USER_ID)
        assert ok2 is True
        assert "真多多药水结束后生效" in msg2
        item = await db.items_get_item(USER_ID, "幸运药水", "potion")
        assert item is None  # 已消耗

    async def test_lucky_delayed_when_flash_active(self, db):
        """闪光生效中喝幸运 → 幸运延后生效。"""
        await db.user_get_or_create(USER_ID)
        await db.items_add(USER_ID, "幸运药水", "potion", 2)
        await db.buff_add_user_buff(
            USER_ID, BuffEffect.BUFF_TYPE_GAMMA_RAY_BURST, 480, 1, "闪光药水"
        )

        ok, msg = await use_lucky_potion(USER_ID)

        assert ok is True
        assert "闪光药水结束后生效" in msg
        item = await db.items_get_item(USER_ID, "幸运药水", "potion")
        assert item["count"] == 1

    async def test_duoduo_delayed_when_flash_active(self, db):
        """闪光生效中喝多多 → 多多延后生效。"""
        await db.user_get_or_create(USER_ID)
        await db.items_add(USER_ID, "真多多药水", "potion", 2)
        await db.buff_add_user_buff(
            USER_ID, BuffEffect.BUFF_TYPE_GAMMA_RAY_BURST, 480, 1, "闪光药水"
        )

        ok, msg = await use_duoduo_potion(USER_ID)

        assert ok is True
        assert "闪光药水结束后生效" in msg
        item = await db.items_get_item(USER_ID, "真多多药水", "potion")
        assert item["count"] == 1

    async def test_flash_delayed_when_lucky_active(self, db):
        """幸运生效中喝闪光 → 闪光延后生效。"""
        await db.user_get_or_create(USER_ID)
        await db.items_add(USER_ID, "闪光药水", "potion", 2)
        await db.buff_add_user_buff(
            USER_ID, BuffEffect.BUFF_TYPE_LUCKY_BOOST, 480, 1, "幸运药水"
        )

        ok, msg = await use_flash_potion(USER_ID)

        assert ok is True
        assert "幸运药水结束后生效" in msg
        item = await db.items_get_item(USER_ID, "闪光药水", "potion")
        assert item["count"] == 1

    async def test_flash_delayed_when_duoduo_active(self, db):
        """多多生效中喝闪光 → 闪光延后生效。"""
        await db.user_get_or_create(USER_ID)
        await db.items_add(USER_ID, "闪光药水", "potion", 2)
        await db.buff_add_user_buff(
            USER_ID, BuffEffect.BUFF_TYPE_DUODUO, 480, 1, "真多多药水"
        )

        ok, msg = await use_flash_potion(USER_ID)

        assert ok is True
        assert "真多多药水结束后生效" in msg
        item = await db.items_get_item(USER_ID, "闪光药水", "potion")
        assert item["count"] == 1

    async def test_flash_usable_without_other_mutex_potion(self, db):
        await db.user_get_or_create(USER_ID)
        await db.items_add(USER_ID, "闪光药水", "potion", 1)

        ok, msg = await use_flash_potion(USER_ID)

        assert ok is True
        assert "流星鱼掉率翻倍" in msg
        assert await db.items_get_item(USER_ID, "闪光药水", "potion") is None

    async def test_same_type_extends_not_delays(self, db):
        """同类型药水重复使用应延长已有 buff 的 end_time，而非创建新 buff。"""
        await db.user_get_or_create(USER_ID)
        await db.items_add(USER_ID, "幸运药水", "potion", 2)
        ok1, _ = await use_lucky_potion(USER_ID)
        assert ok1 is True

        lucky_buffs = await FishingBuff.filter(
            target_id=USER_ID,
            buff_type=BuffEffect.BUFF_TYPE_LUCKY_BOOST,
        ).all()
        assert len(lucky_buffs) == 1
        first_end = lucky_buffs[0].end_time

        ok2, msg2 = await use_lucky_potion(USER_ID)
        assert ok2 is True
        assert "剩余时间+" in msg2

        lucky_buffs_after = await FishingBuff.filter(
            target_id=USER_ID,
            buff_type=BuffEffect.BUFF_TYPE_LUCKY_BOOST,
        ).all()
        assert len(lucky_buffs_after) == 1  # 仍然只有1条记录
        assert lucky_buffs_after[0].end_time > first_end  # end_time 被延长

    async def test_chain_delay_uses_latest_end_time(self, db):
        """A 生效中喝 B（延后），再喝 C → C 的 start_time 应为 B 的 end_time。"""
        await db.user_get_or_create(USER_ID)
        await db.items_add(USER_ID, "幸运药水", "potion", 1)
        await db.items_add(USER_ID, "真多多药水", "potion", 1)
        await db.items_add(USER_ID, "闪光药水", "potion", 1)

        # 幸运立即生效
        ok1, _ = await use_lucky_potion(USER_ID)
        assert ok1 is True

        # 多多延后到幸运结束后
        ok2, _ = await use_duoduo_potion(USER_ID)
        assert ok2 is True

        # 闪光应延后到多多结束后（不是幸运结束后）
        ok3, msg3 = await use_flash_potion(USER_ID)
        assert ok3 is True
        assert "真多多药水结束后生效" in msg3

        duoduo_buff = await FishingBuff.filter(
            target_id=USER_ID,
            buff_type=BuffEffect.BUFF_TYPE_DUODUO,
        ).first()
        flash_buff = await FishingBuff.filter(
            target_id=USER_ID,
            buff_type=BuffEffect.BUFF_TYPE_GAMMA_RAY_BURST,
        ).first()
        assert flash_buff.start_time >= duoduo_buff.end_time
