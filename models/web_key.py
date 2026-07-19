"""
网页端密钥模型。
"""

from tortoise import fields

from zhenxun.services.db_context import Model


class FishingWebKey(Model):
    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    secret = fields.CharField(64, unique=True, description="网页端密钥")
    user_id = fields.CharField(255, description="绑定用户ID", index=True)
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")

    class Meta:
        table = "fishing_web_key"
        table_description = "钓鱼网页端密钥表"

    @classmethod
    def _run_script(cls):
        return [
            "CREATE TABLE IF NOT EXISTS fishing_web_key ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "secret VARCHAR(64) NOT NULL UNIQUE, "
            "user_id VARCHAR(255) NOT NULL, "
            "create_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "update_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"
            ");",
        ]
