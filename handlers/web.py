from nonebot import on_regex
from nonebot.adapters import Event
from nonebot.matcher import Matcher
from nonebot.params import RegexGroup

from ..utils import _is_private_chat, _send_text
from ..web.key_manager import KeyManager

register_key_matcher = on_regex(
    r"^注册网页端(?:\s+(\S+))?$",
    priority=5,
    block=True,
)

view_key_matcher = on_regex(
    r"^查看密钥$",
    priority=5,
    block=True,
)

delete_key_matcher = on_regex(
    r"^删除密钥$",
    priority=5,
    block=True,
)


@register_key_matcher.handle()
async def _(event: Event, matcher: Matcher, group: tuple = RegexGroup()):
    if not _is_private_chat(event):
        await matcher.finish("请在私聊中使用此功能！")

    user_id = event.get_user_id()
    secret = group[0] if group and group[0] else ""

    if secret:
        # 自定义密钥
        if not (3 <= len(secret) <= 32):
            await matcher.finish("密钥长度需在3-32个字符之间！")
        if not secret.isalnum() and not all(c.isalnum() or c in "_-." for c in secret):
            await matcher.finish("密钥只能包含字母、数字、下划线、短横线和点！")
    else:
        # 自动生成8位数字密钥
        import random

        km = KeyManager()
        for _ in range(20):
            secret = str(random.randint(10000000, 99999999))
            if await km.get_user_id(secret) is None:
                break

    success = await KeyManager().register(user_id, secret)
    if not success:
        await matcher.finish("该密钥已被其他用户使用，请重试！")

    await matcher.finish(
        f"网页端密钥已注册成功！\n"
        f"你的密钥：{secret}\n"
        f"在网页端连接时填入此密钥即可使用。\n"
        f"使用【查看密钥】可查看当前密钥，【删除密钥】可删除。"
    )


@view_key_matcher.handle()
async def _(event: Event, matcher: Matcher):
    if not _is_private_chat(event):
        await matcher.finish("请在私聊中使用此功能！")

    user_id = event.get_user_id()
    secrets = await KeyManager().get_secrets(user_id)
    if not secrets:
        await matcher.finish(
            "你还没有注册网页端密钥！\n使用【注册网页端 你的密钥】来注册。"
        )

    await matcher.finish(f"你的网页端密钥：{', '.join(secrets)}")


@delete_key_matcher.handle()
async def _(event: Event, matcher: Matcher):
    if not _is_private_chat(event):
        await matcher.finish("请在私聊中使用此功能！")

    user_id = event.get_user_id()
    success = await KeyManager().unregister(user_id)
    if not success:
        await matcher.finish("你还没有注册网页端密钥！")

    await matcher.finish("网页端密钥已删除。使用【注册网页端 你的密钥】可重新注册。")