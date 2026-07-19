"""真多多药水与幸运药水通过公开使用入口的互斥行为测试。"""

from zhenxun.plugins.zhenxun_plugin_fishing.models import BuffEffect
from zhenxun.plugins.zhenxun_plugin_fishing.shop.potion_use import (
    use_duoduo_potion,
    use_lucky_potion,
)

USER_ID = "test_mutex_001"


class TestMutexBehavior:
    async def test_lucky_blocked_when_duoduo_active(self, db):
        await db.user_get_or_create(USER_ID)
        await db.items_add(USER_ID, "幸运药水", "potion", 5)
        await db.buff_add_user_buff(
            USER_ID, BuffEffect.BUFF_TYPE_DUODUO, 480, 1, "真多多药水"
        )
        ok, msg = await use_lucky_potion(USER_ID)
        assert ok is False
        assert "同一时间只有1种药水可以生效" in msg
        item = await db.items_get_item(USER_ID, "幸运药水", "potion")
        assert item["count"] == 5  # 未消耗

    async def test_duoduo_blocked_when_lucky_active(self, db):
        await db.user_get_or_create(USER_ID)
        await db.items_add(USER_ID, "真多多药水", "potion", 3)
        await db.buff_add_user_buff(
            USER_ID, BuffEffect.BUFF_TYPE_LUCKY_BOOST, 480, 1, "幸运药水"
        )
        ok, msg = await use_duoduo_potion(USER_ID)
        assert ok is False
        assert "同一时间只有1种药水可以生效" in msg
        item = await db.items_get_item(USER_ID, "真多多药水", "potion")
        assert item["count"] == 3  # 未消耗

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

    async def test_use_lucky_then_duoduo_blocked(self, db):
        await db.user_get_or_create(USER_ID)
        await db.items_add(USER_ID, "幸运药水", "potion", 1)
        await db.items_add(USER_ID, "真多多药水", "potion", 1)
        ok1, _ = await use_lucky_potion(USER_ID)
        assert ok1 is True
        # 幸运生效中，多多应被拒绝
        ok2, msg2 = await use_duoduo_potion(USER_ID)
        assert ok2 is False
        assert "同一时间只有1种药水可以生效" in msg2
        item = await db.items_get_item(USER_ID, "真多多药水", "potion")
        assert item["count"] == 1  # 未消耗

    async def test_use_duoduo_then_lucky_blocked(self, db):
        await db.user_get_or_create(USER_ID)
        await db.items_add(USER_ID, "幸运药水", "potion", 1)
        await db.items_add(USER_ID, "真多多药水", "potion", 1)
        ok1, _ = await use_duoduo_potion(USER_ID)
        assert ok1 is True
        # 多多生效中，幸运应被拒绝
        ok2, msg2 = await use_lucky_potion(USER_ID)
        assert ok2 is False
        assert "同一时间只有1种药水可以生效" in msg2
        item = await db.items_get_item(USER_ID, "幸运药水", "potion")
        assert item["count"] == 1  # 未消耗
