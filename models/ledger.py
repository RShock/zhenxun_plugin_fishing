"""
钓鱼账本模型 — 记录钓鱼会话、道具使用、金币变动、GM操作。

四种条目类型：
- fishing: 每次收杆的完整快照（地点、钓竿、鱼获、道具、金币等）
- item_use: 每次成功使用道具的记录
- gold: 每次金币变动的对账记录（含历史推导与异常标记）
- gm_op: GM道具/资源操作记录（添加/扣除道具、鱼饵、鱼等）

金币对账规则：
- 用户首条 gold 条目为基准（is_baseline=True），不校验历史
- 后续 gold 条目从前一条的 gold_after 推导 gold_expected
- gold_expected != gold_after 时标记 gold_anomaly=True
"""

from __future__ import annotations

from tortoise import fields

from zhenxun.services.db_context import Model


class FishingLedger(Model):
    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    user_id = fields.CharField(255, index=True, description="用户ID")
    entry_type = fields.CharField(
        20, description="条目类型: fishing/item_use/gold/gm_op"
    )
    # JSON 载荷：各类型的详细数据（鱼获列表、道具信息、金币操作明细等）
    data = fields.JSONField(description="类型相关的详细数据")

    # ── 金币对账字段（仅 entry_type='gold' 时使用）──
    gold_before = fields.IntField(null=True, description="操作前金币")
    gold_after = fields.IntField(null=True, description="操作后金币")
    gold_expected = fields.IntField(null=True, description="历史推导的预期金币")
    gold_anomaly = fields.BooleanField(
        default=False, description="金币对账异常(gold_expected!=gold_after)"
    )
    is_baseline = fields.BooleanField(
        default=False, description="用户首条金币记录(基准，不校验)"
    )

    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")

    class Meta:
        table = "fishing_ledger"
        table_description = "钓鱼账本记录表"
        # 常用查询：(user_id, entry_type, create_time) 组合索引
        indexes = [("user_id", "entry_type"), ("user_id", "create_time")]

    @classmethod
    def _run_script(cls):
        return [
            "CREATE TABLE IF NOT EXISTS fishing_ledger ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "user_id VARCHAR(255) NOT NULL, "
            "entry_type VARCHAR(20) NOT NULL, "
            "data TEXT NOT NULL, "
            "gold_before INTEGER, "
            "gold_after INTEGER, "
            "gold_expected INTEGER, "
            "gold_anomaly BOOLEAN NOT NULL DEFAULT 0, "
            "is_baseline BOOLEAN NOT NULL DEFAULT 0, "
            "create_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"
            ");",
            "CREATE INDEX IF NOT EXISTS idx_ledger_user_type ON fishing_ledger(user_id, entry_type);",
            "CREATE INDEX IF NOT EXISTS idx_ledger_user_time ON fishing_ledger(user_id, create_time);",
        ]

    @classmethod
    async def get_last_gold_entry(cls, user_id: str) -> "FishingLedger | None":
        """获取用户最近一条金币记录，用于推导预期金币。"""
        return (
            await cls.filter(user_id=user_id, entry_type="gold")
            .order_by("-create_time", "-id")
            .first()
        )

    @classmethod
    async def has_gold_entries(cls, user_id: str) -> bool:
        """用户是否已有金币记录（决定是否创建基准条目）。"""
        return await cls.filter(user_id=user_id, entry_type="gold").exists()

    @classmethod
    async def get_user_fishing_count(cls, user_id: str) -> int:
        """用户总收杆次数。"""
        return await cls.filter(user_id=user_id, entry_type="fishing").count()

    @classmethod
    async def get_user_anomaly_count(cls, user_id: str) -> int:
        """用户金币异常记录数。"""
        return await cls.filter(
            user_id=user_id, entry_type="gold", gold_anomaly=True
        ).count()
