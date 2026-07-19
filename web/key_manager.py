from tortoise.exceptions import IntegrityError

from ..models import FishingWebKey


class KeyManager:
    """管理 Web 端密钥的注册、注销和认证。"""

    async def register(self, user_id: str, secret: str) -> bool:
        """注册密钥。若密钥已被其他用户占用则返回 False。"""
        existing = await self.get_user_id(secret)
        if existing and existing != user_id:
            return False
        if existing == user_id:
            return True
        try:
            await FishingWebKey.create(user_id=user_id, secret=secret)
        except IntegrityError:
            return False
        return True

    async def unregister(self, user_id: str) -> bool:
        """注销用户的所有密钥。"""
        deleted_count = await FishingWebKey.filter(user_id=user_id).delete()
        return deleted_count > 0

    async def get_user_id(self, secret: str) -> str | None:
        """根据密钥查询用户 ID。"""
        record = await FishingWebKey.filter(secret=secret).first()
        return record.user_id if record else None

    async def get_secrets(self, user_id: str) -> list[str]:
        """获取用户的所有密钥。"""
        records = await FishingWebKey.filter(user_id=user_id).order_by("id")
        return [record.secret for record in records]

    async def authenticate(self, secret: str) -> str | None:
        """认证密钥，返回对应的 user_id。"""
        return await self.get_user_id(secret)
