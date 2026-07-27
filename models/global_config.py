"""钓鱼插件全局配置模型。"""

from tortoise import fields

from zhenxun.services.db_context import Model


class FishingGlobalConfig(Model):
    key = fields.CharField(100, pk=True, description="配置键")
    bool_value = fields.BooleanField(default=False, description="布尔配置值")
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")

    class Meta:
        table = "fishing_global_config"
        table_description = "钓鱼插件全局配置表"

    @classmethod
    async def get_bool(cls, key: str, default: bool = False) -> bool:
        config = await cls.filter(key=key).first()
        return bool(config.bool_value) if config else bool(default)

    @classmethod
    async def set_bool(cls, key: str, value: bool) -> None:
        await cls.update_or_create(
            key=key,
            defaults={"bool_value": bool(value)},
        )
