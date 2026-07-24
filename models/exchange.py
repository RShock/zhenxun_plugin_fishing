"""
交换记录模型 — 黑商/白商交换历史。
"""

from __future__ import annotations

from datetime import datetime

from tortoise import fields
from tortoise.expressions import F

from zhenxun.services.db_context import Model


class FishingExchangeRecord(Model):
    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    user_id = fields.CharField(255, description="黑商交换达成者", index=True)
    source_name = fields.CharField(255, description="黑商消耗鱼名")
    source_rarity = fields.CharField(10, description="黑商消耗鱼稀有度")
    source_numeric_id = fields.CharField(50, description="黑商消耗鱼编号")
    source_location_id = fields.CharField(20, description="黑商消耗鱼场景ID")
    source_location_name = fields.CharField(255, description="黑商消耗鱼场景名")
    source_scene_level = fields.IntField(description="黑商消耗鱼场景等级")
    target_name = fields.CharField(255, description="黑商获得鱼名")
    target_rarity = fields.CharField(10, description="黑商获得鱼稀有度")
    target_numeric_id = fields.CharField(50, description="黑商获得鱼编号")
    target_location_id = fields.CharField(20, description="黑商获得鱼场景ID")
    target_location_name = fields.CharField(255, description="黑商获得鱼场景名")
    target_scene_level = fields.IntField(description="黑商获得鱼场景等级")
    is_active = fields.BooleanField(default=True, description="是否仍可白商逆交换", index=True)
    reversed_by_user_id = fields.CharField(255, null=True, description="白商逆交换/黑商撤回操作者")
    # is_randomized: 该次黑商交换是否被同稀有度随机替换了目标鱼。
    # 撤回时据此回退保底计数器（失败 +1 的逆操作）。
    is_randomized = fields.BooleanField(default=False, description="黑商交换是否被随机替换目标")
    # used_extra_ticket: 该次交换是否消耗了黑商额外券，撤回时需返还。
    used_extra_ticket = fields.BooleanField(default=False, description="是否消耗了黑商额外券")
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")

    class Meta:
        table = "fishing_exchange_record"
        table_description = "钓鱼黑商交换记录表"

    @classmethod
    def _run_script(cls):
        return [
            "CREATE TABLE IF NOT EXISTS fishing_exchange_record ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "user_id VARCHAR(255) NOT NULL, "
            "source_name VARCHAR(255) NOT NULL, "
            "source_rarity VARCHAR(10) NOT NULL, "
            "source_numeric_id VARCHAR(50) NOT NULL, "
            "source_location_id VARCHAR(20) NOT NULL, "
            "source_location_name VARCHAR(255) NOT NULL, "
            "source_scene_level INTEGER NOT NULL, "
            "target_name VARCHAR(255) NOT NULL, "
            "target_rarity VARCHAR(10) NOT NULL, "
            "target_numeric_id VARCHAR(50) NOT NULL, "
            "target_location_id VARCHAR(20) NOT NULL, "
            "target_location_name VARCHAR(255) NOT NULL, "
            "target_scene_level INTEGER NOT NULL, "
            "is_active BOOLEAN NOT NULL DEFAULT 1, "
            "reversed_by_user_id VARCHAR(255), "
            "create_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "update_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"
            ");",
            # 增量字段：老库补列，新库已含则 SQLite 忽略报错
            "ALTER TABLE fishing_exchange_record ADD COLUMN is_randomized BOOLEAN NOT NULL DEFAULT 0;",
            "ALTER TABLE fishing_exchange_record ADD COLUMN used_extra_ticket BOOLEAN NOT NULL DEFAULT 0;",
        ]

    @classmethod
    async def create_black_record(
        cls,
        user_id: str,
        source,
        target,
        is_randomized: bool = False,
        used_extra_ticket: bool = False,
    ) -> "FishingExchangeRecord":
        return await cls.create(
            user_id=user_id,
            source_name=source.name,
            source_rarity=source.rarity,
            source_numeric_id=source.numeric_id,
            source_location_id=source.location_id,
            source_location_name=source.location_name,
            source_scene_level=source.scene_level,
            target_name=target.name,
            target_rarity=target.rarity,
            target_numeric_id=target.numeric_id,
            target_location_id=target.location_id,
            target_location_name=target.location_name,
            target_scene_level=target.scene_level,
            is_randomized=is_randomized,
            used_extra_ticket=used_extra_ticket,
        )

    @classmethod
    async def list_active_records(cls) -> list["FishingExchangeRecord"]:
        return await cls.filter(is_active=True).exclude(
            source_numeric_id=F("target_numeric_id")
        ).order_by(
            "target_scene_level",
            "target_location_id",
            "target_name",
            "target_rarity",
            "id",
        )

    @classmethod
    async def find_active_reverse(cls, source, target) -> "FishingExchangeRecord" | None:
        if source.numeric_id == target.numeric_id:
            return None
        return await cls.filter(
            is_active=True,
            source_numeric_id=target.numeric_id,
            target_numeric_id=source.numeric_id,
        ).order_by("id").first()

    @classmethod
    async def find_active_by_source_numeric_id(
        cls, source_numeric_id: str
    ) -> list["FishingExchangeRecord"]:
        """查找黑商source是指定鱼的所有有效记录。

        白商新逻辑：玩家获得鱼=黑商source（指定鱼），
        支付鱼只需与黑商target同地图同稀有度即可，不再要求精确逆映射。
        返回所有匹配记录，由调用方进一步筛选target的location+rarity。
        """
        return await cls.filter(
            is_active=True,
            source_numeric_id=str(source_numeric_id),
        ).exclude(source_numeric_id=F("target_numeric_id")).order_by("id")

    @classmethod
    async def invalidate_record(cls, record_id: int, reversed_by_user_id: str) -> None:
        record = await cls.get(id=record_id)
        record.is_active = False
        record.reversed_by_user_id = reversed_by_user_id
        record.update_time = datetime.now()
        await record.save(update_fields=["is_active", "reversed_by_user_id", "update_time"])

    @classmethod
    async def list_today_records_by_user(
        cls, user_id: str
    ) -> list["FishingExchangeRecord"]:
        """查询某用户当天创建、仍有效的黑商记录，按 id 降序（最近在前）。

        黑商撤回仅限当天，用 create_time 过滤；排除 source==target 的无效记录。
        """
        from datetime import date

        start = datetime.combine(date.today(), datetime.min.time())
        end = datetime.combine(date.today(), datetime.max.time())
        return (
            await cls.filter(
                user_id=user_id,
                is_active=True,
                create_time__gte=start,
                create_time__lte=end,
            )
            .exclude(source_numeric_id=F("target_numeric_id"))
            .order_by("-id")
        )

    @classmethod
    async def revoke_record(cls, record_id: int, user_id: str) -> "FishingExchangeRecord | None":
        """撤回指定记录：标记失效并记录操作者，返回更新后的记录。

        仅当记录属于该用户且仍有效时才撤回；否则返回 None。
        """
        record = await cls.filter(
            id=record_id, user_id=user_id, is_active=True
        ).first()
        if not record:
            return None
        record.is_active = False
        record.reversed_by_user_id = user_id
        record.update_time = datetime.now()
        await record.save(
            update_fields=["is_active", "reversed_by_user_id", "update_time"]
        )
        return record
