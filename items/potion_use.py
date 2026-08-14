"""
道具使用系统 — 时光药水、回档药水、幸运药水、闪光药水、木框加速、UTR自选券。

这些道具不在鱼店出售，因此从 shop/ 拆出至 items/。
药水时长等配置见 config/items.json，效果描述需与 web/static/help.html 保持同步。
"""

from datetime import datetime, timedelta

from zhenxun.services.log import logger

from ..config import MAX_FRAME_BUFF_LAYERS, ConfigManager
from ..core.cat_gift import default_cat_gifts
from ..core.context import (
    deserialize_fish_caught,
    deserialize_meteor_fish_records,
    normalize_time_potions,
    serialize_fish_caught,
    serialize_meteor_fish_records,
)
from ..models import BuffEffect, FishingBuff, FishingUser, _make_naive
from ..scene_instance import get_scene_instance_id
from ..services import get_or_create_user, ledger_service
from ..shop.view import get_status_image
from ..starry import is_starry_location

_MUTEX_POTION_BUFFS = (
    (BuffEffect.BUFF_TYPE_DUODUO, "真多多药水"),
    (BuffEffect.BUFF_TYPE_LUCKY_BOOST, "幸运药水"),
    (BuffEffect.BUFF_TYPE_GAMMA_RAY_BURST, "闪光药水"),
)


async def _resolve_mutex_potion_timing(
    user_id: str, buff_type: str
) -> tuple[str, "FishingBuff | None", datetime | None, str | None]:
    """确定新药水的生效时机。

    三种核心药水（多多/幸运/闪光）之间不重叠生效。当已有其他药水覆盖时，
    新药水的 start_time 延后到所有互斥 buff 中最晚的 end_time 之后，
    确保新药水拥有完整的 8 小时可用区间。

    返回 (mode, extend_buff, delayed_start, active_potion_name):
    - ("extend", buff, None, None): 同类型 buff 已存在（含未来排期），延长 end_time
    - ("delay", None, start_time, potion_name): 有其他互斥药水生效中/已排期，
      新 buff 的 start_time 应设为所有互斥 buff 中最晚的 end_time
    - ("immediate", None, None, None): 无任何互斥 buff，立即生效
    """
    now = datetime.now()
    all_mutex_types = [bt for bt, _ in _MUTEX_POTION_BUFFS]
    # 查询所有未过期的互斥药水 buff（含当前生效和未来排期）
    all_buffs = await FishingBuff.filter(
        target_type=BuffEffect.TARGET_TYPE_USER,
        target_id=user_id,
        buff_type__in=all_mutex_types,
        end_time__gt=now,
    ).order_by("-end_time").all()

    if not all_buffs:
        return "immediate", None, None, None

    # 同类型：延长最晚结束的那个
    same_type = [b for b in all_buffs if b.buff_type == buff_type]
    if same_type:
        latest_same = max(same_type, key=lambda b: b.end_time)
        # 检查是否有异类型 buff 排期更晚（start_time 在同类型 end_time 之后）
        # 如果有，延长同类型会导致跨类型时间重叠，应改为延后模式
        other_type = [b for b in all_buffs if b.buff_type != buff_type]
        if other_type:
            latest_other = max(other_type, key=lambda b: b.end_time)
            if latest_other.end_time > latest_same.end_time:
                latest_end = _make_naive(latest_other.end_time)
                active_name = next(
                    (name for bt, name in _MUTEX_POTION_BUFFS if bt == latest_other.buff_type),
                    "其他药水",
                )
                return "delay", None, latest_end, active_name
        return "extend", latest_same, None, None

    # 异类型：取所有互斥 buff 中最晚的 end_time 作为新 buff 的起点
    latest = max(all_buffs, key=lambda b: b.end_time)
    latest_end = _make_naive(latest.end_time)
    active_name = next(
        (name for bt, name in _MUTEX_POTION_BUFFS if bt == latest.buff_type),
        "其他药水",
    )
    return "delay", None, latest_end, active_name


async def use_time_potion(
    user_id: str, count: int = 1, **kwargs
) -> tuple[bool, bytes | str]:
    if count < 1:
        return False, "数量必须大于0"

    status = await FishingUser.get_status(user_id)
    if not status:
        return False, "你还没有在钓鱼，无法使用时光药水！请先【钓鱼 地点编号】开始钓鱼"

    user = await get_or_create_user(user_id)
    potion_item = await FishingUser.get_item(user_id, "time_potion", "potion")
    potion_count = potion_item["count"] if potion_item else 0
    if potion_count <= 0:
        return False, "时光药水不足，当前没有时光药水"
    # 宽容机制：请求数量超出库存时，使用全部剩余药水
    if potion_count < count:
        count = potion_count

    bait = ConfigManager.get_bait(user.bait_id)
    if not bait or user.bait_id == "0":
        return False, "当前没有使用鱼饵，无法使用时光药水"

    bait_item = await FishingUser.get_item(user_id, str(bait.id), "bait")
    bait_remaining = bait_item["count"] if bait_item else 0
    if bait_remaining < 30:
        return (
            False,
            f"当前鱼饵{bait.name}不足30个（当前{bait_remaining}个），无法使用时光药水",
        )

    await FishingUser.remove_item(user_id, "time_potion", "potion", count)

    from ..core.potion import use_time_potion_settle

    hours = 8 * count
    success, result = await use_time_potion_settle(user_id, hours, potion_count=count)
    return success, result


_ROLLBACK_WINDOW_HOURS = 24


async def use_rollback_potion(user_id: str) -> tuple[bool, bytes | str]:
    """使用回档药水：回溯最近 _ROLLBACK_WINDOW_HOURS 小时的钓鱼结果。

    削弱后只回溯最近 24 小时：
    - start_time 早于 24 小时前的鱼获（catch_time 为 None 或早于截止点）保留
    - 24 小时窗口内的鱼获被移除并重新结算
    - 鱼饵按鱼获比例退还（无法精确追踪每条鱼消耗的饵，用鱼数比例估算）
    - 本次钓鱼期间使用过时光药水时不允许回档（避免时光药水模拟的鱼获与真实钓鱼混淆）
    """
    status_dict = await FishingUser.get_status(user_id)
    if not status_dict:
        return False, "你还没有在钓鱼，无法使用回档药水！请先【钓鱼 地点编号】开始钓鱼"

    user = await FishingUser.get_user(user_id)
    if not user:
        return False, "玩家数据不存在，无法使用回档药水"
    rollback_item = await FishingUser.get_item(user_id, "回档药水", "potion")
    potion_count = rollback_item["count"] if rollback_item else 0
    if potion_count < 1:
        return False, "回档药水不足，需要1瓶（当前0瓶）"

    if not is_starry_location(status_dict.get("location_id", "")):
        return False, "回档药水仅可在星空地图（11-20）使用，普通地图和猫猫乐园无法使用"

    # 使用过时光药水的钓鱼会话不允许回档
    time_potions_raw = normalize_time_potions(
        status_dict.get("time_potions_used", [])
    )
    if time_potions_raw:
        return False, "本次钓鱼期间使用过时光药水，无法使用回档药水"

    await FishingUser.remove_item(user_id, "回档药水", "potion", 1)

    now = datetime.now()
    cutoff = now - timedelta(hours=_ROLLBACK_WINDOW_HOURS)
    original_start_time = _make_naive(
        datetime.fromisoformat(status_dict["start_time"])
    )
    # 回溯截止点不会早于开钓时间（会话不足 24h 时退化为全量回档）
    rollback_cutoff = max(original_start_time, cutoff)
    is_full_rollback = rollback_cutoff == original_start_time

    # ── 按时间戳拆分已有鱼获 ──
    existing_fish = deserialize_fish_caught(status_dict.get("fish_caught", []))
    existing_cat_eaten = deserialize_fish_caught(
        status_dict.get("cat_eaten_fish", [])
    )
    existing_meteor = deserialize_meteor_fish_records(status_dict)

    keep_fish: list = []
    remove_fish: list = []
    for fish, rarity, count, ct in existing_fish:
        # catch_time 为 None（旧数据）：
        #   - 会话不足 24h（全量回档）→ 视为窗口内，移除
        #   - 会话超过 24h → 视为窗口外，保留
        if not is_full_rollback and (ct is None or ct < rollback_cutoff):
            keep_fish.append((fish, rarity, count, ct))
        else:
            remove_fish.append((fish, rarity, count, ct))

    keep_cat_eaten: list = []
    remove_cat_eaten: list = []
    for fish, rarity, count, ct in existing_cat_eaten:
        if not is_full_rollback and (ct is None or ct < rollback_cutoff):
            keep_cat_eaten.append((fish, rarity, count, ct))
        else:
            remove_cat_eaten.append((fish, rarity, count, ct))

    keep_meteor: list[tuple[int, datetime | None]] = []
    remove_meteor: list[tuple[int, datetime | None]] = []
    for number, ct in existing_meteor:
        if not is_full_rollback and (ct is None or ct < rollback_cutoff):
            keep_meteor.append((number, ct))
        else:
            remove_meteor.append((number, ct))

    # ── 估算鱼饵退还量 ──
    # bait_usage_log 只记录总消耗，无时间戳。用「被移除鱼数 / 总鱼数」
    # 比例估算 24h 窗口内消耗的鱼饵。全量回档时比例为 1.0。
    total_fish_count = sum(
        c for _, _, c, _ in existing_fish + existing_cat_eaten
    )
    removed_fish_count = sum(
        c for _, _, c, _ in remove_fish + remove_cat_eaten
    )
    if total_fish_count > 0:
        refund_ratio = removed_fish_count / total_fish_count
    else:
        refund_ratio = 1.0 if is_full_rollback else 0.0

    bait_usage_log = status_dict.get("bait_usage_log", {})
    total_bait_consumed = status_dict.get("bait_consumed", 0)
    refunded_bait = 0
    new_bait_usage_log: dict[str, int] = {}
    for bait_id, count in bait_usage_log.items():
        count = int(count)
        if count > 0:
            refund_count = round(count * refund_ratio)
            keep_count = count - refund_count
            if refund_count > 0:
                await FishingUser.add_item(user_id, str(bait_id), "bait", refund_count)
                refunded_bait += refund_count
            if keep_count > 0:
                new_bait_usage_log[bait_id] = keep_count

    new_bait_consumed = total_bait_consumed - round(
        total_bait_consumed * refund_ratio
    )

    # ── 构建回溯后的状态 ──
    # time_potions_used 已在入口处检查为空，回档后保持空列表
    reset_status = {
        "location_id": status_dict["location_id"],
        "start_time": status_dict["start_time"],
        # last_settle_time 推进到截止点，check_fishing_status 会从这里重新结算到 now
        "last_settle_time": rollback_cutoff.isoformat(),
        "fish_caught": serialize_fish_caught(keep_fish),
        "bait_consumed": new_bait_consumed,
        # 保底计数器沿用玩家当前值（与原回档一致：保留当前保底进度）
        "frame_pity": user.frame_pity_counter,
        "cat_frame_pity": user.cat_frame_pity_counter,
        "utr_pity": user.utr_pity_counter,
        "cat_eaten_fish": serialize_fish_caught(keep_cat_eaten),
        # 猫礼物无法按时间拆分，重置为默认值
        "cat_gifts": default_cat_gifts() | {"cat_frame_pity": 0},
        "meteor_fish_numbers": [number for number, _ in keep_meteor],
        "meteor_fish_records": serialize_meteor_fish_records(keep_meteor),
        "time_potions_used": [],
        "bait_usage_log": new_bait_usage_log,
    }
    if status_dict.get("shadow_scene"):
        reset_status["shadow_scene"] = True
        reset_status["scene_instance_id"] = get_scene_instance_id(status_dict)
    await FishingUser.update_fishing_status(user_id, reset_status)

    # 构建回档提示消息，通过结算页面显示给玩家
    window_desc = (
        "全部钓鱼进度"
        if is_full_rollback
        else f"最近{_ROLLBACK_WINDOW_HOURS}小时"
    )
    rollback_messages = [f"⏪ 回档药水生效，回溯{window_desc}"]
    if refunded_bait > 0:
        rollback_messages.append(f"🎁 退还鱼饵 {refunded_bait} 个")

    from ..core.actions import check_fishing_status

    image, step = await check_fishing_status(
        user_id, extra_messages=rollback_messages
    )
    if image is None:
        image = await get_status_image(user_id)

    logger.info(
        f"用户 {user_id} 使用回档药水，回溯{window_desc}，"
        f"保留{len(keep_fish)}条鱼获，移除{len(remove_fish)}条，"
        f"保留{len(keep_meteor)}条流星鱼，移除{len(remove_meteor)}条，"
        f"退还鱼饵 {refunded_bait} 个"
    )
    await ledger_service.log_item_use(
        user_id,
        item_id="回档药水",
        item_type="potion",
        item_name="回档药水",
        count=1,
        context="use_rollback_potion",
    )
    return True, image


async def use_lucky_potion(user_id: str, count: int = 1) -> tuple[bool, str]:
    """使用幸运药水，叠加 count * 8 小时的幸运 buff。

    若其他互斥药水（多多/闪光）正在生效或已排期，幸运药水的 start_time
    会延后到所有互斥 buff 结束之后，确保拥有完整的 8 小时区间。
    """
    if count < 1:
        return False, "数量必须大于0"

    user = await get_or_create_user(user_id)
    lucky_item = await FishingUser.get_item(user_id, "幸运药水", "potion")
    potion_count = lucky_item["count"] if lucky_item else 0

    # 宽容机制：请求数量超出库存时，使用全部剩余
    actual_count = min(count, potion_count)
    if actual_count < 1:
        return False, "幸运药水不足，需要1瓶（当前0瓶）"

    await FishingUser.remove_item(user_id, "幸运药水", "potion", actual_count)
    total_hours = actual_count * 8

    mode, extend_buff, delayed_start, active_name = (
        await _resolve_mutex_potion_timing(
            user_id, BuffEffect.BUFF_TYPE_LUCKY_BOOST
        )
    )

    if mode == "extend":
        extend_buff.end_time = _make_naive(extend_buff.end_time) + timedelta(
            hours=total_hours
        )
        await extend_buff.save(update_fields=["end_time"])
        logger.info(
            f"用户 {user_id} 使用{actual_count}瓶幸运药水，时间堆叠至 {extend_buff.end_time}（+{total_hours}h）"
        )
        await ledger_service.log_item_use(
            user_id, item_id="幸运药水", item_type="potion",
            item_name="幸运药水", count=actual_count, context="use_lucky_potion",
        )
        return (
            True,
            f"幸运药水生效！钓鱼变得幸运 ⭐，剩余时间+{total_hours}小时（使用{actual_count}瓶）",
        )

    if mode == "delay":
        start = delayed_start
        end = start + timedelta(hours=total_hours)
        await FishingBuff.add_buff(
            buff_type=BuffEffect.BUFF_TYPE_LUCKY_BOOST,
            start_time=start,
            end_time=end,
            value=1,
            description="幸运药水：钓鱼变得幸运",
            target_type=BuffEffect.TARGET_TYPE_USER,
            target_id=user_id,
        )
        logger.info(
            f"用户 {user_id} 使用{actual_count}瓶幸运药水，延后至 {start} 生效（{total_hours}h），"
            f"因{active_name}正在生效"
        )
        await ledger_service.log_item_use(
            user_id, item_id="幸运药水", item_type="potion",
            item_name="幸运药水", count=actual_count, context="use_lucky_potion",
        )
        return (
            True,
            f"幸运药水将在{active_name}结束后生效"
            f"（预计{start.strftime('%m-%d %H:%M')}开始，持续{total_hours}小时，使用{actual_count}瓶）",
        )

    # immediate：无互斥 buff，立即生效
    await FishingBuff.add_user_buff(
        user_id=user_id,
        buff_type=BuffEffect.BUFF_TYPE_LUCKY_BOOST,
        duration_minutes=total_hours * 60,
        value=1,
        description="幸运药水：钓鱼变得幸运",
    )
    logger.info(
        f"用户 {user_id} 使用{actual_count}瓶幸运药水，获得幸运buff（{total_hours}小时）"
    )
    await ledger_service.log_item_use(
        user_id, item_id="幸运药水", item_type="potion",
        item_name="幸运药水", count=actual_count, context="use_lucky_potion",
    )
    return (
        True,
        f"幸运药水生效！钓鱼变得幸运 ⭐，持续{total_hours}小时（使用{actual_count}瓶）",
    )


async def use_duoduo_potion(user_id: str, count: int = 1, **kwargs) -> tuple[bool, str]:
    """真多多药水：8h内鱼竿等级-1，钓到的鱼数量翻倍；重复使用延长时间。

    若其他互斥药水（幸运/闪光）正在生效或已排期，多多药水的 start_time
    会延后到所有互斥 buff 结束之后，确保拥有完整的 8 小时区间。
    """
    if count < 1:
        return False, "数量必须大于0"

    user = await get_or_create_user(user_id)
    potion_item = await FishingUser.get_item(user_id, "真多多药水", "potion")
    potion_count = potion_item["count"] if potion_item else 0
    if potion_count <= 0:
        return False, "真多多药水不足，当前没有真多多药水"
    # 宽容机制：请求数量超出库存时，使用全部剩余药水
    if potion_count < count:
        count = potion_count

    await FishingUser.remove_item(user_id, "真多多药水", "potion", count)

    duration = timedelta(hours=8 * count)
    mode, extend_buff, delayed_start, active_name = (
        await _resolve_mutex_potion_timing(
            user_id, BuffEffect.BUFF_TYPE_DUODUO
        )
    )

    if mode == "extend":
        extend_buff.end_time = _make_naive(extend_buff.end_time) + duration
        await extend_buff.save(update_fields=["end_time"])
        logger.info(
            f"用户 {user_id} 使用{count}瓶真多多药水，时间堆叠至 {extend_buff.end_time}"
        )
        await ledger_service.log_item_use(
            user_id, item_id="真多多药水", item_type="potion",
            item_name="真多多药水", count=count, context="use_duoduo_potion",
        )
        return (
            True,
            f"真多多药水生效！鱼竿等级-1，鱼获数量翻倍，剩余时间+{8 * count}小时",
        )

    if mode == "delay":
        start = delayed_start
        end = start + duration
        await FishingBuff.add_buff(
            buff_type=BuffEffect.BUFF_TYPE_DUODUO,
            start_time=start,
            end_time=end,
            value=1,
            description="真多多药水：鱼竿等级-1，钓到的鱼数量翻倍",
            target_type=BuffEffect.TARGET_TYPE_USER,
            target_id=user_id,
        )
        logger.info(
            f"用户 {user_id} 使用{count}瓶真多多药水，延后至 {start} 生效（{8*count}h），"
            f"因{active_name}正在生效"
        )
        await ledger_service.log_item_use(
            user_id, item_id="真多多药水", item_type="potion",
            item_name="真多多药水", count=count, context="use_duoduo_potion",
        )
        return (
            True,
            f"真多多药水将在{active_name}结束后生效"
            f"（预计{start.strftime('%m-%d %H:%M')}开始，持续{8 * count}小时）",
        )

    # immediate：无互斥 buff，立即生效
    await FishingBuff.add_user_buff(
        user_id=user_id,
        buff_type=BuffEffect.BUFF_TYPE_DUODUO,
        duration_minutes=480 * count,
        value=1,
        description="真多多药水：鱼竿等级-1，钓到的鱼数量翻倍",
    )

    logger.info(
        f"用户 {user_id} 使用{count}瓶真多多药水，获得多多buff（{8 * count}小时）"
    )
    await ledger_service.log_item_use(
        user_id, item_id="真多多药水", item_type="potion",
        item_name="真多多药水", count=count, context="use_duoduo_potion",
    )
    return True, f"真多多药水生效！鱼竿等级-1，鱼获数量翻倍，持续{8 * count}小时"


async def use_display_frame_buff(
    user_id: str, count: int = 1, is_private: bool = False, **kwargs
) -> tuple[bool, str]:
    """木框 — 普通地图与 S1 速度加成。"""
    if count < 1:
        return False, "数量必须大于0"

    user = await get_or_create_user(user_id)
    if user.display_frames <= 0:
        return False, "木框不足，当前没有木框"
    # 硬上限：不管用户请求多少个，最多使用 MAX_FRAME_BUFF_LAYERS 个
    capped = False
    if count > MAX_FRAME_BUFF_LAYERS:
        capped = True
        count = MAX_FRAME_BUFF_LAYERS
    # 宽容机制：请求数量超出库存时，使用全部剩余木框
    if user.display_frames < count:
        count = user.display_frames

    now = datetime.now()
    # 查询已有 frame buff，按 end_time 升序排列（最旧的优先延长）
    current_frame_buffs = await FishingBuff.filter(
        target_type=BuffEffect.TARGET_TYPE_GLOBAL,
        buff_type=BuffEffect.BUFF_TYPE_FRAME,
        end_time__gt=now,
    ).order_by("end_time").all()
    total_layers = len(current_frame_buffs)

    duration_hours = ConfigManager.get_nest_duration_hours()

    # 第一阶段：填满到上限（新增 buff 记录）
    layers_to_add = min(count, max(0, MAX_FRAME_BUFF_LAYERS - total_layers))
    # 第二阶段：剩余木框循环延长已有 buff（同一 buff 可被多次延长）
    remaining = count - layers_to_add
    extended_count = 0
    if remaining > 0 and current_frame_buffs:
        extended_count = remaining
        extension_delta = timedelta(hours=duration_hours)
        for i in range(remaining):
            buff = current_frame_buffs[i % len(current_frame_buffs)]
            buff.end_time = _make_naive(buff.end_time) + extension_delta
            await buff.save(update_fields=["end_time"])

    actual_frames = layers_to_add + extended_count
    if actual_frames == 0:
        return False, f"全图木框效果已满{MAX_FRAME_BUFF_LAYERS * 5}%，无法继续使用"

    await FishingUser.reduce_display_frames(user_id, actual_frames)

    for _ in range(layers_to_add):
        await FishingBuff.add_global_buff(
            buff_type=BuffEffect.BUFF_TYPE_FRAME,
            start_time=datetime.now(),
            end_time=datetime.now() + timedelta(hours=duration_hours),
            value=5,
            description=f"木框效果，1-10图与S1钓鱼速度+5%",
        )

    new_total = total_layers + layers_to_add

    added_pct = layers_to_add * 5
    total_pct = new_total * 5

    if layers_to_add > 0:
        msg = f"使用木框成功，1-10图与S1速度+{added_pct}%，持续{duration_hours}小时"
        if new_total > layers_to_add:
            msg += f"（全图累计+{total_pct}%）"
    else:
        msg = f"木框效果已满，延长了{extended_count}次已有buff（每次+{duration_hours}小时）（全图累计+{total_pct}%）"

    if layers_to_add > 0 and extended_count > 0:
        msg += f"\n已满{MAX_FRAME_BUFF_LAYERS * 5}%上限，延长了{extended_count}次已有木框buff（每次+{duration_hours}小时）"
    if actual_frames < count:
        msg += f"\n无已有木框buff可延长，仅消耗{actual_frames}个木框，{count - actual_frames}个未消耗"
    if capped:
        msg += f"\n木框使用上限为{MAX_FRAME_BUFF_LAYERS}个，已自动调整使用数量"

    logger.info(f"用户 {user_id} 使用木框{layers_to_add}层，延长{extended_count}次，当前全图{new_total}层")
    await ledger_service.log_item_use(
        user_id, item_id="display_frame", item_type="display_frame",
        item_name="木框", count=actual_frames, context="use_display_frame_buff",
    )
    return True, msg


async def use_flash_potion(user_id: str, count: int = 1, **kwargs) -> tuple[bool, str]:
    """使用闪光药水，叠加 count * 8 小时的伽马射线暴 buff。

    生效期间视为同时拥有太阳风、流星雨、恒纪元，并使流星鱼掉率翻倍。
    若其他互斥药水（多多/幸运）正在生效或已排期，闪光药水的 start_time
    会延后到所有互斥 buff 结束之后，确保拥有完整的 8 小时区间。
    """
    if count < 1:
        return False, "数量必须大于0"

    await get_or_create_user(user_id)
    flash_item = await FishingUser.get_item(user_id, "闪光药水", "potion")
    potion_count = flash_item["count"] if flash_item else 0
    actual_count = min(count, potion_count)
    if actual_count < 1:
        return False, "闪光药水不足，需要1瓶（当前0瓶）"

    await FishingUser.remove_item(user_id, "闪光药水", "potion", actual_count)
    total_hours = actual_count * 8

    mode, extend_buff, delayed_start, active_name = (
        await _resolve_mutex_potion_timing(
            user_id, BuffEffect.BUFF_TYPE_GAMMA_RAY_BURST
        )
    )

    if mode == "extend":
        extend_buff.end_time = _make_naive(extend_buff.end_time) + timedelta(
            hours=total_hours
        )
        await extend_buff.save(update_fields=["end_time"])
        logger.info(
            f"用户 {user_id} 使用{actual_count}瓶闪光药水，时间堆叠至 {extend_buff.end_time}（+{total_hours}h）"
        )
        return (
            True,
            f"💥 闪光药水生效！伽马射线暴已叠加 +{total_hours}小时"
            f"（太阳风+流星雨+恒纪元，流星鱼掉率翻倍，使用{actual_count}瓶）",
        )

    if mode == "delay":
        start = delayed_start
        end = start + timedelta(hours=total_hours)
        await FishingBuff.add_buff(
            buff_type=BuffEffect.BUFF_TYPE_GAMMA_RAY_BURST,
            start_time=start,
            end_time=end,
            value=1,
            description="闪光药水：伽马射线暴（三重天气，流星鱼掉率翻倍）",
            target_type=BuffEffect.TARGET_TYPE_USER,
            target_id=user_id,
        )
        logger.info(
            f"用户 {user_id} 使用{actual_count}瓶闪光药水，延后至 {start} 生效（{total_hours}h），"
            f"因{active_name}正在生效"
        )
        await ledger_service.log_item_use(
            user_id, item_id="闪光药水", item_type="potion",
            item_name="闪光药水", count=actual_count, context="use_flash_potion",
        )
        return (
            True,
            f"💥 闪光药水将在{active_name}结束后生效"
            f"（预计{start.strftime('%m-%d %H:%M')}开始，持续{total_hours}小时，使用{actual_count}瓶）",
        )

    # immediate：无互斥 buff，立即生效
    await FishingBuff.add_user_buff(
        user_id=user_id,
        buff_type=BuffEffect.BUFF_TYPE_GAMMA_RAY_BURST,
        duration_minutes=total_hours * 60,
        value=1,
        description="闪光药水：伽马射线暴（三重天气，流星鱼掉率翻倍）",
    )
    logger.info(
        f"用户 {user_id} 使用{actual_count}瓶闪光药水，获得伽马射线暴（{total_hours}小时）"
    )
    await ledger_service.log_item_use(
        user_id, item_id="闪光药水", item_type="potion",
        item_name="闪光药水", count=actual_count, context="use_flash_potion",
    )
    return (
        True,
        f"💥 闪光药水生效！伽马射线暴持续{total_hours}小时"
        f"（太阳风+流星雨+恒纪元，流星鱼掉率翻倍，使用{actual_count}瓶）",
    )


def _normalize_utr_fish_name(raw: str) -> str:
    name = (raw or "").strip()
    if not name:
        return ""
    # 允许 "xxx UTR" / "xxx鱼UTR" 写法
    upper = name.upper()
    if upper.endswith(" UTR"):
        name = name[:-4].strip()
    elif upper.endswith("UTR") and len(name) > 3:
        name = name[:-3].strip()
    return name


async def _location_has_any_utr(user_id: str, location_id: str) -> bool:
    from ..config import ConfigManager

    loc = ConfigManager.get_location(location_id)
    if not loc:
        return False
    collected = await FishingUser.get_user_collected(user_id)
    for fish_name in loc.fish_pool:
        if (fish_name, "UTR") in collected:
            return True
    return False


async def _location_missing_ur(user_id: str, location_id: str) -> list[str]:
    """返回该地图中尚未收集 UR 的鱼名列表；全部收集齐时返回空列表。

    特性：仅凭他人赠送解锁 UTR 图鉴但不曾自行钓齐 UR 的玩家，
    无法使用自选券兑换该图 UTR——需自行收集齐该图全部 UR 后方可兑换。
    """
    from ..config import ConfigManager

    loc = ConfigManager.get_location(location_id)
    if not loc:
        return []
    collected = await FishingUser.get_user_collected(user_id)
    missing = [
        fish_name
        for fish_name in loc.fish_pool
        if (fish_name, "UR") not in collected
    ]
    return missing


async def use_utr_select_ticket(
    user_id: str, count: int = 1, **kwargs
) -> tuple[bool, str]:
    """使用 UTR 自选券兑换指定 UTR 鱼。

    用法：钓鱼使用 UTR自选券 鱼名
    条件：目标鱼所在地图已解锁至少 1 条 UTR，且该图全部 UR 已收集齐。
    """
    fish_name = _normalize_utr_fish_name(
        str(kwargs.get("arg") or kwargs.get("extra") or kwargs.get("target") or "")
    )
    if not fish_name:
        return (
            False,
            "请指定要兑换的 UTR 鱼名！\n"
            "格式：钓鱼使用 UTR自选券 鱼名\n"
            "条件：该鱼所在地图需已解锁至少 1 条 UTR",
        )

    await get_or_create_user(user_id)
    ticket = await FishingUser.get_item(user_id, "utr_select_ticket", "ticket")
    ticket_count = ticket["count"] if ticket else 0
    if ticket_count < 1:
        return False, "UTR自选券不足（当前0张）"

    from ..backpack.black_market import find_fish_target
    from ..core.result import add_fish_to_user

    target = find_fish_target(fish_name, "UTR")
    if not target:
        # 尝试模糊：去掉/补上“鱼”后缀
        alt = fish_name[:-1] if fish_name.endswith("鱼") else f"{fish_name}鱼"
        target = find_fish_target(alt, "UTR")
        if target:
            fish_name = alt
    if not target:
        return (
            False,
            f"未找到鱼种「{fish_name}」，请输入正确的鱼名（如地图中的 UTR 鱼）",
        )

    if not await _location_has_any_utr(user_id, target.location_id):
        return (
            False,
            f"无法兑换：需要先在【{target.location_name}】解锁至少 1 条 UTR 鱼后，"
            f"才能用自选券兑换该图的 UTR（目标：{target.name}）",
        )

    missing_ur = await _location_missing_ur(user_id, target.location_id)
    if missing_ur:
        return (
            False,
            f"无法兑换：需先收集齐【{target.location_name}】的全部 UR 鱼"
            f"（还差 {len(missing_ur)} 条：{'、'.join(missing_ur)}），"
            f"才能用自选券兑换该图的 UTR",
        )

    ok = await FishingUser.remove_item(user_id, "utr_select_ticket", "ticket", 1)
    if not ok:
        return False, "UTR自选券扣除失败，请重试"

    result = await add_fish_to_user(
        user_id,
        [(target.name, "UTR", target.numeric_id, 1)],
        effective_difficulty=max(0, target.scene_level - 1),
        check_achievements=True,
        auto_display=True,
    )
    msgs = list(result.get("messages") or [])
    ach = list(result.get("achievement_messages") or [])
    lines = [
        f"🎫 UTR自选券兑换成功！获得 {target.name} UTR（{target.location_name}）",
    ]
    lines.extend(msgs)
    lines.extend(ach)
    if result.get("fish_coins"):
        lines.append(f"💰 计入鱼获价值 {result['fish_coins']} 钓鱼币（未自动卖出）")
    logger.info(
        f"用户 {user_id} 使用UTR自选券兑换 {target.name} UTR @ {target.location_id}"
    )
    return True, "\n".join(lines)
