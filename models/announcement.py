"""
活跃群记录模型 — 用于钓鱼公告系统。

记录玩家在群内收杆的行为，用于判断群是否为活跃群（最近2天内有人收杆）。
"""

from __future__ import annotations

from datetime import datetime, timedelta

from tortoise import fields

from zhenxun.services.db_context import Model

ACTIVE_GROUP_DAYS = 2


class FishingActiveGroup(Model):
    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    group_id = fields.CharField(255, index=True, description="群号")
    user_id = fields.CharField(255, description="收杆玩家ID")
    nickname = fields.CharField(255, default="", description="收杆玩家昵称")
    last_fishing_time = fields.DatetimeField(
        auto_now=True, description="最近收杆时间"
    )

    class Meta:
        table = "fishing_active_group"
        table_description = "钓鱼活跃群记录表"

    @classmethod
    def _run_script(cls):
        return [
            "CREATE TABLE IF NOT EXISTS fishing_active_group ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "group_id VARCHAR(255) NOT NULL, "
            "user_id VARCHAR(255) NOT NULL, "
            "nickname VARCHAR(255) DEFAULT '', "
            "last_fishing_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"
            ");",
            "CREATE INDEX IF NOT EXISTS idx_fishing_active_group_gid "
            "ON fishing_active_group (group_id);",
        ]

    @classmethod
    async def record_fishing(
        cls, group_id: str, user_id: str, nickname: str = ""
    ) -> None:
        """记录玩家在群内收杆，更新或创建记录。"""
        existing = await cls.filter(
            group_id=group_id, user_id=user_id
        ).first()
        if existing:
            existing.nickname = nickname
            existing.last_fishing_time = datetime.now()
            await existing.save(
                update_fields=["nickname", "last_fishing_time"]
            )
        else:
            await cls.create(
                group_id=group_id,
                user_id=user_id,
                nickname=nickname,
            )

    @classmethod
    async def get_active_group_ids(cls) -> list[str]:
        """获取所有活跃群号（最近2天内有人收杆的群）。"""
        cutoff = datetime.now() - timedelta(days=ACTIVE_GROUP_DAYS)
        records = await cls.filter(
            last_fishing_time__gte=cutoff
        ).distinct().values_list("group_id", flat=True)
        return list(records)
