"""S2 星穹矿脉 · QQ 指令处理器"""

from __future__ import annotations

import re

from nonebot.adapters import Event
from nonebot.matcher import Matcher
from nonebot.params import RegexGroup

from ..matchers import (
    s2_buy_matcher,
    s2_helper_matcher,
    s2_help_matcher,
    s2_mining_matcher,
    s2_next_matcher,
    s2_shop_matcher,
    s2_stop_matcher,
    switch_mode_matcher,
)
from ..render.s2_mining import render_mining_help, render_mining_main, render_shop_with_total
from ..s2_mining import (
    S2_HELPER_NAME,
    S2_MANUAL_DEPARTURES,
    S2_WHITELIST,
    get_mining_status,
    get_s2_state,
    get_shop_page,
    is_s2_whitelisted_event,
    next_planet,
    purchase_upgrade,
    stop_mining,
    switch_mode,
    toggle_helper,
)
from ..services.user_lock_service import with_user_lock
from ..utils import _ensure_user, _get_nickname, _send_image, _send_text


def _check_whitelist(event) -> bool:
    try:
        uid = event.get_user_id()
    except Exception:
        uid = ""
    return is_s2_whitelisted_event(event, uid)


@s2_help_matcher.handle()
@with_user_lock("S2/帮助")
async def _(event: Event, matcher: Matcher):
    if not _check_whitelist(event):
        await matcher.finish()
        return
    image = await render_mining_help()
    await _send_image(matcher, image, user_id=event.get_user_id())


@switch_mode_matcher.handle()
@with_user_lock("S2/切换模式")
async def _(event: Event, matcher: Matcher, group: tuple = RegexGroup()):
    if not _check_whitelist(event):
        # 静默忽略，非白名单不产生副作用也不发送消息
        await matcher.finish()
        return
    user_id, nickname = await _ensure_user(event)
    raw = event.get_plaintext() if hasattr(event, "get_plaintext") else ""
    # 兼容 RegexGroup 与直接解析
    target = ""
    if group and group[0]:
        target = group[0].strip()
    else:
        m = re.search(r"切换模式\s*(挖矿|钓鱼)", raw)
        if m:
            target = m.group(1)
    if not target:
        await _send_text(matcher, "用法：切换模式 挖矿/钓鱼", user_id)
        return
    ok, msg, _ = await switch_mode(user_id, target)
    await _send_text(matcher, msg, user_id)


@s2_mining_matcher.handle()
@with_user_lock("S2/挖矿")
async def _(event: Event, matcher: Matcher):
    if not _check_whitelist(event):
        await matcher.finish()
        return
    user_id, nickname = await _ensure_user(event)
    state, delta = await get_mining_status(user_id)
    if not state.get("s2_unlocked"):
        await _send_text(matcher, "🔒 尚未解锁星穹矿脉：需在钓鱼主游戏集齐 1-10 图并获得【大肥鱼】后解锁。", user_id)
        return
    # 若不在挖矿模式，提示切换
    if state.get("mode") != "mining":
        await _send_text(matcher, "当前在【钓鱼】模式，请先发送【切换模式 挖矿】。", user_id)
        return
    if state.get("stopMining"):
        await _send_text(matcher, "挖矿已暂停，发送【切换模式 挖矿】恢复。", user_id)
        return
    # 首次进入的 delta 含 first 标记，渲染会显示引导
    image = await render_mining_main(state, delta, S2_HELPER_NAME)
    # 附加文字提示（距上次收益已在图中，这里仅作额外）
    await _send_image(matcher, image, user_id=user_id)


@s2_shop_matcher.handle()
@with_user_lock("S2/商店")
async def _(event: Event, matcher: Matcher, group: tuple = RegexGroup()):
    if not _check_whitelist(event):
        await matcher.finish()
        return
    user_id, _ = await _ensure_user(event)
    state = await get_s2_state(user_id)
    if not state.get("s2_unlocked"):
        await _send_text(matcher, "🔒 尚未解锁星穹矿脉。", user_id)
        return
    if state.get("mode") != "mining":
        await _send_text(matcher, "请先【切换模式 挖矿】后再查看商店。", user_id)
        return
    page = 1
    if group and group[0] and str(group[0]).strip().isdigit():
        page = int(str(group[0]).strip())
    # 同步结算一次
    from ..s2_mining import ensure_mining_tick
    state, _ = await ensure_mining_tick(user_id, state)
    # 获取分页
    _, rows, pages = await get_shop_page(user_id, page, page_size=6)
    # 为 total 提供正确值
    from ..s2_mining import _shop_entries
    total = len(_shop_entries(state))
    image = await render_shop_with_total(state, rows, page, pages, total)
    await _send_image(matcher, image, user_id=user_id)


@s2_buy_matcher.handle()
@with_user_lock("S2/购买")
async def _(event: Event, matcher: Matcher, group: tuple = RegexGroup()):
    if not _check_whitelist(event):
        await matcher.finish()
        return
    user_id, _ = await _ensure_user(event)
    state = await get_s2_state(user_id)
    if not state.get("s2_unlocked"):
        await _send_text(matcher, "🔒 尚未解锁星穹矿脉。", user_id)
        return
    if state.get("mode") != "mining":
        await _send_text(matcher, "请先【切换模式 挖矿】后再购买。", user_id)
        return
    ident = ""
    count = 1
    if group:
        if len(group) >= 1 and group[0]:
            ident = str(group[0]).strip()
        if len(group) >= 2 and group[1] and str(group[1]).isdigit():
            count = int(str(group[1]))
    # 兼容 “挖矿购买 分岔矿道 2” 这种空格分隔但 ident 含空格的情况：从原文截取
    if not ident:
        raw = event.get_plaintext() if hasattr(event, "get_plaintext") else ""
        m = re.search(r"挖矿购买\s+(\S+)(?:\s+(\d+))?", raw)
        if m:
            ident = m.group(1) or ""
            if m.group(2):
                count = int(m.group(2))
    if not ident:
        await _send_text(matcher, "用法：挖矿购买 编号/名称 [数量]，例：挖矿购买 2 或 挖矿购买 分岔矿道", user_id)
        return
    ok, msg = await purchase_upgrade(user_id, ident, count)
    # 购买结果用文字 + 刷新后的主界面（便于立即看到等级变化）
    if ok:
        # 重新获取状态并结算
        new_state, _ = await get_mining_status(user_id)
        # 若当前已挖穿，购买会失败，已在上面返回，这里直接展示
        await _send_text(matcher, msg, user_id)
        # 可选：附带刷新主图（避免刷屏，暂只文字）
    else:
        await _send_text(matcher, msg, user_id)


@s2_next_matcher.handle()
@with_user_lock("S2/下一个星球")
async def _(event: Event, matcher: Matcher):
    if not _check_whitelist(event):
        await matcher.finish()
        return
    user_id, _ = await _ensure_user(event)
    state = await get_s2_state(user_id)
    if not state.get("s2_unlocked"):
        await _send_text(matcher, "🔒 尚未解锁星穹矿脉。", user_id)
        return
    if state.get("mode") != "mining":
        await _send_text(matcher, "请先【切换模式 挖矿】。", user_id)
        return
    ok, msg = await next_planet(user_id)
    await _send_text(matcher, msg, user_id)
    # 若成功启程，附带新矿场图
    if ok:
        new_state, delta = await get_mining_status(user_id)
        image = await render_mining_main(new_state, delta, S2_HELPER_NAME)
        await _send_image(matcher, image, user_id=user_id)


@s2_stop_matcher.handle()
@with_user_lock("S2/停止挖矿")
async def _(event: Event, matcher: Matcher):
    if not _check_whitelist(event):
        await matcher.finish()
        return
    user_id, _ = await _ensure_user(event)
    ok, msg = await stop_mining(user_id)
    await _send_text(matcher, msg, user_id)


@s2_helper_matcher.handle()
@with_user_lock("S2/助手")
async def _(event: Event, matcher: Matcher, group: tuple = RegexGroup()):
    if not _check_whitelist(event):
        await matcher.finish()
        return
    user_id, _ = await _ensure_user(event)
    raw = event.get_plaintext() if hasattr(event, "get_plaintext") else ""
    arg = ""
    if group and group[0]:
        arg = str(group[0]).strip()
    else:
        m = re.search(r"大肥鱼(?:助手)?(?:\s*(开启|关闭))?", raw)
        if m:
            arg = (m.group(1) or "").strip()
    enable = None
    if arg == "开启":
        enable = True
    elif arg == "关闭":
        enable = False
    ok, msg = await toggle_helper(user_id, enable)
    await _send_text(matcher, msg, user_id)
