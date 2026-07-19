"""
GM 指令 handler — 所有 superuser 调试命令。
"""

from datetime import datetime, timedelta

from nonebot.adapters import Event, Message
from nonebot.matcher import Matcher
from nonebot.params import CommandArg

from ..fishing import stop_fishing
from ..gm import parse_qq_id_list
from ..matchers import (
    gm_add_item_matcher,
    gm_add_skin_matcher,
    gm_check_achievements_matcher,
    gm_force_stop_matcher,
    gm_give_fish_matcher,
    gm_give_gold_matcher,
    gm_limit_off_matcher,
    gm_limit_on_matcher,
    gm_money_matcher,
    gm_reset_matcher,
    gm_rollback_hook_matcher,
    gm_rollback_rod_matcher,
    gm_set_gold_matcher,
    gm_weather_info_matcher,
    gm_weather_reset_matcher,
)
from ..models import FishingUser
from ..render import render_fishing_result
from ..utils import _get_at_list, _send_image


def _cmd_text(arg: Message | None = None) -> str:
    """取出 on_command 的参数纯文本。"""
    if arg is None:
        return ""
    return arg.extract_plain_text().strip()


def _resolve_target_ids(event: Event, residual_text: str = "") -> list[str]:
    """解析目标用户：优先 @，否则从文本 QQ 号解析（支持批量）。"""
    at_list = [str(x) for x in _get_at_list(event) if x]
    if at_list:
        # 去重保序
        seen = set()
        out = []
        for uid in at_list:
            if uid not in seen:
                seen.add(uid)
                out.append(uid)
        return out
    return parse_qq_id_list(residual_text or event.get_plaintext())


@gm_reset_matcher.handle()
async def _(event: Event, matcher: Matcher, arg: Message = CommandArg()):
    from ..gm import gm_reset_user

    residual = _cmd_text(arg)
    user_id = residual.split()[0] if residual else event.get_user_id()
    success, message = await gm_reset_user(user_id)
    await matcher.finish(message)


@gm_force_stop_matcher.handle()
async def _(event: Event, matcher: Matcher):
    user_id = event.get_user_id()
    status = await FishingUser.get_status(user_id)
    if not status:
        await matcher.finish("你还没有开始钓鱼！")

    gm_start_time = datetime.now() - timedelta(hours=10)
    gm_start_iso = gm_start_time.isoformat()
    user = await FishingUser.get_user(user_id)
    status["start_time"] = gm_start_iso
    status["last_settle_time"] = gm_start_iso
    status["fish_caught"] = []
    status["bait_consumed"] = 0
    status["frame_pity"] = user.frame_pity_counter
    status["utr_pity"] = user.utr_pity_counter
    status["cat_eaten_fish"] = []
    status["cat_gifts"] = {
        "gold": 0,
        "corn": 0,
        "bait_id": "",
        "bait_count": 0,
        "cat_frames": 0,
        "fish_name": "",
        "fish_rarity": "",
    }
    await FishingUser.update_fishing_status(user_id, status)

    render_data, buff_messages, _ = await stop_fishing(user_id, gm_mode=True)

    if render_data is None:
        await matcher.finish("你还没有开始钓鱼！")

    hints = list(buff_messages)
    hints.insert(0, "🔧 GM强制收杆（视为10小时前开始钓鱼）")

    image = await render_fishing_result(
        render_data["user_id"],
        render_data["location"],
        render_data["duration_minutes"],
        render_data["merged_fish"],
        render_data["fish_coins"],
        render_data["achievement_messages"],
        sign_info=render_data["sign_info"],
        hints=hints if hints else None,
        cat_eaten_fish=render_data.get("cat_eaten_fish"),
        cat_gifts=render_data.get("cat_gifts"),
        meteor_fish_numbers=render_data.get("meteor_fish_numbers"),
        cat_park_materials=render_data.get("cat_park_materials"),
        starry_score=render_data.get("starry_score"),
        miracle=render_data.get("miracle"),
            starry_rewards=render_data.get("starry_rewards"),
    )

    await _send_image(matcher, image)


@gm_money_matcher.handle()
async def _(event: Event, matcher: Matcher):
    user_id = event.get_user_id()
    from ..gm import gm_add_gold

    success, message = await gm_add_gold(user_id, 100000)
    await matcher.finish(message)


@gm_give_gold_matcher.handle()
async def _(event: Event, matcher: Matcher, arg: Message = CommandArg()):
    from ..gm import gm_add_gold, gm_add_gold_all, gm_apply_to_users

    body = _cmd_text(arg)
    if not body:
        await matcher.finish(
            "格式：gm发钱 金额 @用户 / gm发钱 金额 QQ1,QQ2 / gm发钱 金额 全服"
        )

    parts = body.split()
    amount_str = parts[0]
    try:
        amount = int(amount_str)
        if amount == 0:
            await matcher.finish("金额不能为0！")
    except ValueError:
        await matcher.finish("请输入有效的金额！")

    if "全服" in body:
        success, message = await gm_add_gold_all(amount)
        await matcher.finish(message)

    # 去掉金额后的剩余文本作为目标解析源
    residual = body[len(amount_str) :].strip() if body.startswith(amount_str) else " ".join(parts[1:])
    target_ids = _resolve_target_ids(event, residual)

    if not target_ids:
        await matcher.finish(
            "请@用户，或直接填写 QQ 号（可批量），或输入'全服'！\n"
            "格式：gm发钱 金额 @用户 | gm发钱 金额 QQ1,QQ2 | gm发钱 金额 全服"
        )

    if len(target_ids) == 1:
        success, message = await gm_add_gold(target_ids[0], amount)
        await matcher.finish(message)

    success, message = await gm_apply_to_users(
        target_ids,
        "发钱",
        lambda uid, a=amount: gm_add_gold(uid, a),
    )
    await matcher.finish(message)


@gm_add_skin_matcher.handle()
async def _(event: Event, matcher: Matcher, arg: Message = CommandArg()):
    from ..gm import gm_add_skin, gm_add_skin_all, gm_apply_to_users

    body = _cmd_text(arg)
    if not body:
        await matcher.finish("格式：gm添加皮肤 皮肤ID @用户 / QQ / 全服")

    parts = body.split()
    skin_id = parts[0]
    if not skin_id:
        await matcher.finish("格式：gm添加皮肤 皮肤ID @用户 / QQ / 全服")

    if "全服" in body:
        if skin_id == "全服":
            await matcher.finish("请指定要添加的皮肤ID！格式：gm添加皮肤 皮肤ID 全服")
        success, message = await gm_add_skin_all(skin_id)
        await matcher.finish(message)

    residual = body[len(skin_id) :].strip() if body.startswith(skin_id) else " ".join(parts[1:])
    target_ids = _resolve_target_ids(event, residual)

    if not target_ids:
        await matcher.finish(
            "请@用户，或直接填写 QQ 号（可批量），或输入'全服'！\n"
            "格式：gm添加皮肤 皮肤ID @用户 | gm添加皮肤 皮肤ID QQ1,QQ2 | gm添加皮肤 皮肤ID 全服"
        )

    if len(target_ids) == 1:
        success, message = await gm_add_skin(target_ids[0], skin_id)
        await matcher.finish(message)

    success, message = await gm_apply_to_users(
        target_ids,
        "添加皮肤",
        lambda uid, s=skin_id: gm_add_skin(uid, s),
    )
    await matcher.finish(message)


@gm_add_item_matcher.handle()
async def _(event: Event, matcher: Matcher, arg: Message = CommandArg()):
    """gm添加/gm赠送：支持多物品 + QQ/@ 批量目标。

    格式：
    - gm添加 物品名 [数量] QQ1,QQ2,...
    - gm添加 物品A,物品B,物品C [数量] @用户
    - gm添加 物品A,物品Bx3 [数量] 全服
    - gm添加 时光药水x3,真多多药水 1 @用户

    多物品用逗号/分号分隔；同名自动累加（写 3 次时光药水 = ×3）。
    全局数量作用于未写 xN 后缀的每一项。
    """
    from ..gm import (
        gm_add_item_all,
        gm_add_items,
        gm_apply_to_users,
        parse_gm_add_body,
        parse_qq_id_list,
    )

    body = _cmd_text(arg)
    if not body:
        await matcher.finish(
            "格式：gm添加 物品名 [数量] QQ1,QQ2（无需@，可批量）\n"
            "多物品：gm添加 物品A,物品B,物品C [数量] @用户\n"
            "单项数量：gm添加 时光药水x3,真多多药水 1 @用户\n"
            "例如：gm添加 真多多药水,幸运药水,时光药水,时光药水,时光药水 1 @用户\n"
            "      gm添加 猫猫框 5 1922570420,3404193303\n"
            "      gm添加 小鲫鱼sr 10 全服\n"
            "物品：猫猫框、展示木框、玉米、药水(时光/回档/幸运/闪光/真多多/许愿)、"
            "UTR自选券、黑商额外兑换券、抽奖碎片、鱼饵、流星鱼、鱼名+稀有度 等"
        )

    item_specs, target_text = parse_gm_add_body(body)
    if not item_specs:
        await matcher.finish(
            "请指定要添加的物品名称！\n"
            "格式：gm添加 物品名 [数量] @用户 / QQ / 全服\n"
            "多物品：gm添加 A,B,C [数量] @用户"
        )

    if "全服" in body:
        # 全服：逐物品执行
        lines: list[str] = []
        any_ok = False
        for item_name, count in item_specs:
            ok, msg = await gm_add_item_all(item_name, count)
            any_ok = any_ok or ok
            lines.append(msg)
        await matcher.finish("\n".join(lines) if lines else "全服添加失败")

    target_ids = _resolve_target_ids(event, target_text)
    if not target_ids:
        target_ids = parse_qq_id_list(target_text)
    # 兼容：目标仅在 @ 里、plaintext 无 QQ
    if not target_ids:
        target_ids = _resolve_target_ids(event, body)

    if not target_ids:
        await matcher.finish(
            "请填写目标 QQ 号（可批量，无需@），或@用户，或输入'全服'！\n"
            "格式：gm添加 物品名 [数量] QQ1,QQ2\n"
            "      gm添加 A,B,C [数量] @用户\n"
            "      gm添加 物品名 [数量] 全服"
        )

    if len(target_ids) == 1:
        success, message = await gm_add_items(target_ids[0], item_specs)
        await matcher.finish(message)

    success, message = await gm_apply_to_users(
        target_ids,
        "添加物品",
        lambda uid, specs=item_specs: gm_add_items(uid, specs),
    )
    await matcher.finish(message)


@gm_set_gold_matcher.handle()
async def _(event: Event, matcher: Matcher, arg: Message = CommandArg()):
    from ..gm import gm_set_gold

    body = _cmd_text(arg)
    parts = body.split()
    target_id = parts[0] if parts else ""
    amount_str = parts[1] if len(parts) > 1 else ""

    if not target_id or not amount_str:
        await matcher.finish("格式：gm设定金钱 QQ号 金额")

    try:
        amount = int(amount_str)
    except ValueError:
        await matcher.finish("金额必须是整数！")

    success, message = await gm_set_gold(target_id, amount)
    await matcher.finish(message)


@gm_give_fish_matcher.handle()
async def _(event: Event, matcher: Matcher, arg: Message = CommandArg()):
    from ..gm import gm_give_fish, gm_give_fish_all, gm_apply_to_users

    body = _cmd_text(arg)
    if not body:
        await matcher.finish("格式：gm发鱼 鱼ID1,鱼ID2 @用户 / QQ / 全服")

    parts = body.split()
    fish_ids_str = parts[0]
    if not fish_ids_str:
        await matcher.finish("格式：gm发鱼 鱼ID1,鱼ID2 @用户 / QQ / 全服")

    if "全服" in body:
        if fish_ids_str == "全服":
            await matcher.finish("请指定要发送的鱼ID！格式：gm发鱼 鱼ID1,鱼ID2 全服")
        success, message = await gm_give_fish_all(fish_ids_str)
        await matcher.finish(message)

    residual = body[len(fish_ids_str) :].strip() if body.startswith(fish_ids_str) else " ".join(parts[1:])
    target_ids = _resolve_target_ids(event, residual)

    if not target_ids:
        await matcher.finish(
            "请@用户，或直接填写 QQ 号（可批量），或输入'全服'！\n"
            "格式：gm发鱼 鱼ID1,鱼ID2 @用户 | gm发鱼 鱼ID1,鱼ID2 QQ1,QQ2 | gm发鱼 鱼ID1,鱼ID2 全服"
        )

    if len(target_ids) == 1:
        success, message = await gm_give_fish(target_ids[0], fish_ids_str)
        await matcher.finish(message)

    success, message = await gm_apply_to_users(
        target_ids,
        "发鱼",
        lambda uid, f=fish_ids_str: gm_give_fish(uid, f),
    )
    await matcher.finish(message)


@gm_rollback_rod_matcher.handle()
async def _(event: Event, matcher: Matcher, arg: Message = CommandArg()):
    from ..gm import gm_rollback_rod

    residual = _cmd_text(arg)
    target_id = residual.split()[0] if residual else ""
    if not target_id:
        await matcher.finish("格式：gm回退鱼竿 QQ号")

    success, message = await gm_rollback_rod(target_id)
    await matcher.finish(message)


@gm_rollback_hook_matcher.handle()
async def _(event: Event, matcher: Matcher, arg: Message = CommandArg()):
    from ..gm import gm_rollback_hook

    residual = _cmd_text(arg)
    target_id = residual.split()[0] if residual else ""
    if not target_id:
        await matcher.finish("格式：gm回退鱼钩 QQ号")

    success, message = await gm_rollback_hook(target_id)
    await matcher.finish(message)


@gm_weather_info_matcher.handle()
async def _(event: Event, matcher: Matcher):
    from ..gm import gm_weather_info

    success, message = await gm_weather_info()
    await matcher.finish(message)


@gm_weather_reset_matcher.handle()
async def _(event: Event, matcher: Matcher):
    from ..gm import gm_weather_reset

    success, message = await gm_weather_reset()
    await matcher.finish(message)


@gm_check_achievements_matcher.handle()
async def _(event: Event, matcher: Matcher):
    from ..gm import gm_apply_to_users, gm_check_achievements

    target_ids = _resolve_target_ids(event)
    if not target_ids:
        target_ids = [event.get_user_id()]

    if len(target_ids) == 1:
        success, message = await gm_check_achievements(target_ids[0])
        await matcher.finish(message)

    success, message = await gm_apply_to_users(
        target_ids,
        "补成就",
        gm_check_achievements,
    )
    await matcher.finish(message)


@gm_limit_on_matcher.handle()
async def _(matcher: Matcher):
    from zhenxun.services.log import logger

    from ..services.limit_service import set_group_action_limit_enabled

    set_group_action_limit_enabled(True)
    logger.info("GM开启群聊钓鱼限流（收杆/钓鱼状态）")
    await matcher.finish(
        "已开启群聊钓鱼限流：群里「钓鱼状态」「收杆」恢复每日次数限制。"
    )


@gm_limit_off_matcher.handle()
async def _(matcher: Matcher):
    from zhenxun.services.log import logger

    from ..services.limit_service import set_group_action_limit_enabled

    set_group_action_limit_enabled(False)
    logger.info("GM关闭群聊钓鱼限流（收杆/钓鱼状态）")
    await matcher.finish(
        "已关闭群聊钓鱼限流：群里可无限次查看「钓鱼状态」与「收杆」（私聊本就无限流）。"
        "\n重启机器人后默认会重新开启限流。"
    )
