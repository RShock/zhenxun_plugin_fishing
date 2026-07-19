"""供 Web 端在插件内部执行指令时使用的模拟 Bot 和 Event 对象。"""

from typing import Any

from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot.compat import PYDANTIC_V2
from nonebot.internal.adapter import Bot as BaseBot
from nonebot.internal.adapter import Event as BaseEvent

if PYDANTIC_V2:
    from pydantic import BaseModel as _PydanticModel
else:
    from pydantic import BaseModel as _PydanticModel


class _Sender(_PydanticModel):
    nickname: str = ""


class FakeWebEvent(BaseEvent):
    """模拟的 Web 端事件，模拟一条来自 QQ 的消息。"""

    user_id: str = ""
    message_text: str = ""
    sender: _Sender = _Sender()

    def get_type(self) -> str:
        return "message"

    def get_event_name(self) -> str:
        return "message"

    def get_event_description(self) -> str:
        return self.message_text

    def get_user_id(self) -> str:
        return self.user_id

    def get_session_id(self) -> str:
        return f"web_{self.user_id}"

    def get_message(self) -> Message:
        return Message(self.message_text)

    def is_tome(self) -> bool:
        return False


class FakeWebBot(BaseBot):
    """模拟的 Bot 对象，拦截 send() 调用并收集响应消息。"""

    def __init__(self):
        super().__init__(adapter=None, self_id="web_bot")
        self._responses: list[Message] = []

    def reset(self):
        """清空已收集的响应消息。"""
        self._responses.clear()

    async def send(
        self,
        event: BaseEvent,
        message: str | Message | MessageSegment,
        **kwargs: Any,
    ) -> Any:
        if isinstance(message, str):
            msg = Message(MessageSegment.text(message))
        elif isinstance(message, MessageSegment):
            msg = Message(message)
        else:
            msg = message
        self._responses.append(msg)
        return None

    @property
    def responses(self) -> list[Message]:
        return self._responses