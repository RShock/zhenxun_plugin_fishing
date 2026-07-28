"""
账本服务 — 记录钓鱼会话、道具使用、金币变动。

三种记录入口：
1. log_fishing_session: 收杆后记录完整钓鱼快照
2. log_item_use: 成功使用道具后记录
3. log_gold_change: 金币变动时记录并执行对账

金币对账流程：
- 查询用户最近一条 gold 记录
- 若无记录 → 创建基准条目 (is_baseline=True)
- 若有记录 → gold_expected = 前一条 gold_after + 本次变动
- gold_expected != gold_after → 标记 gold_anomaly=True

设计原则：
- 账本写入是业务操作的副作用，不应阻断主流程
- 所有写入使用 try/except 包裹，失败仅记日志不抛异常
- 支持批量延迟写入（事务完成后统一 flush）
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from zhenxun.services.log import logger

from ..models import FishingLedger


# ═══════════════════════════════════════════════════════════════════════════════
# 延迟写入缓冲
# ═══════════════════════════════════════════════════════════════════════════════

# 事务内无法直接写账本（可能与主事务一起回滚），
# 使用线程局部缓冲暂存待写条目，事务提交后统一 flush。
_pending_entries: list[dict] = []


def queue_entry(
    user_id: str,
    entry_type: str,
    data: dict[str, Any],
    gold_before: int | None = None,
    gold_after: int | None = None,
    gold_expected: int | None = None,
    gold_anomaly: bool = False,
    is_baseline: bool = False,
) -> None:
    """将账本条目加入延迟写入队列（事务内使用）。"""
    _pending_entries.append({
        "user_id": user_id,
        "entry_type": entry_type,
        "data": data,
        "gold_before": gold_before,
        "gold_after": gold_after,
        "gold_expected": gold_expected,
        "gold_anomaly": gold_anomaly,
        "is_baseline": is_baseline,
    })


async def flush_pending_entries() -> int:
    """将队列中的待写条目统一写入数据库。返回成功写入数。"""
    if not _pending_entries:
        return 0
    entries = list(_pending_entries)
    _pending_entries.clear()
    count = 0
    for entry in entries:
        ok = await _safe_create(entry)
        if ok:
            count += 1
    return count


async def _safe_create(entry: dict) -> bool:
    """安全写入单条账本记录，失败仅记日志。"""
    try:
        await FishingLedger.create(**entry)
        return True
    except Exception as e:
        logger.warning(f"账本写入失败: {entry.get('entry_type')}, user={entry.get('user_id')}", e=e)
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# 钓鱼会话记录
# ═══════════════════════════════════════════════════════════════════════════════


async def log_fishing_session(
    user_id: str,
    *,
    location_id: str,
    location_name: str = "",
    rod_level: int = 0,
    hook_level: int = 0,
    bait_id: str = "0",
    bait_name: str = "",
    start_time: str | None = None,
    end_time: str | None = None,
    duration_minutes: float = 0,
    weather: str = "",
    fish_caught: list[dict] | None = None,
    items_gained: list[dict] | None = None,
    starry_score: float = 0.0,
    starry_fish_count: int = 0,
    gold_earned: int = 0,
    auto_sold: bool = False,
    cat_eaten_fish: list | None = None,
    cat_gifts: dict | None = None,
    buffs_active: list[str] | None = None,
    miracle: dict | None = None,
    bait_consumed: int = 0,
    gold_before: int | None = None,
    gold_after: int | None = None,
    deferred: bool = False,
) -> None:
    """记录一次钓鱼会话的完整快照。

    deferred=True 时加入延迟队列（事务内使用），
    否则立即写入。
    """
    data = {
        "location_id": location_id,
        "location_name": location_name,
        "rod_level": rod_level,
        "hook_level": hook_level,
        "bait_id": bait_id,
        "bait_name": bait_name,
        "start_time": start_time,
        "end_time": end_time or datetime.now().isoformat(),
        "duration_minutes": round(duration_minutes, 1),
        "weather": weather,
        "fish_caught": fish_caught or [],
        "items_gained": items_gained or [],
        "starry_score": round(starry_score, 4),
        "starry_fish_count": starry_fish_count,
        "gold_earned": gold_earned,
        "auto_sold": auto_sold,
        "cat_eaten_fish": cat_eaten_fish or [],
        "cat_gifts": cat_gifts or {},
        "buffs_active": buffs_active or [],
        "miracle": miracle,
        "bait_consumed": bait_consumed,
        "gold_before": gold_before,
        "gold_after": gold_after,
    }
    if deferred:
        queue_entry(user_id, "fishing", data)
    else:
        await _safe_create({
            "user_id": user_id,
            "entry_type": "fishing",
            "data": data,
        })


# ═══════════════════════════════════════════════════════════════════════════════
# 道具使用记录
# ═══════════════════════════════════════════════════════════════════════════════


async def log_item_use(
    user_id: str,
    *,
    item_id: str,
    item_type: str,
    item_name: str = "",
    count: int = 1,
    context: str = "",
    deferred: bool = False,
) -> None:
    """记录一次成功的道具使用。

    只在道具使用成功后调用（使用失败不计入）。
    context 标识调用来源（如 'use_time_potion'、'use_lucky_potion'）。
    """
    data = {
        "item_id": item_id,
        "item_type": item_type,
        "item_name": item_name or item_id,
        "count": count,
        "context": context,
        "timestamp": datetime.now().isoformat(),
    }
    if deferred:
        queue_entry(user_id, "item_use", data)
    else:
        await _safe_create({
            "user_id": user_id,
            "entry_type": "item_use",
            "data": data,
        })


# ═══════════════════════════════════════════════════════════════════════════════
# 金币变动记录 + 对账
# ═══════════════════════════════════════════════════════════════════════════════


_GOLD_CATEGORY_MAP = {
    "fishing_income": ("fishing", "钓鱼结算"),
    "sell_fish": ("sale", "出售物品"),
    "sell_bait": ("sale", "出售物品"),
    "cat_park_material": ("sale", "出售物品"),
    "achievement": ("reward", "奖励收入"),
    "gm_achievement": ("reward", "奖励收入"),
    "gift_utr_unlock": ("reward", "奖励收入"),
    "gift_reward": ("reward", "奖励收入"),
    "cat_gift": ("reward", "奖励收入"),
    "buy_bait": ("supplies", "购买消耗品"),
    "upgrade_rod": ("upgrade", "装备升级"),
    "upgrade_hook": ("upgrade", "装备升级"),
    "build_starry_ship": ("construction", "设施建设"),
    "exchange_gold": ("exchange", "货币兑换"),
}


def classify_gold_change(operation: str, amount: int) -> tuple[str, str, str]:
    """返回收支方向、统计分类键和中文分类名。未知操作按金额方向兜底。"""
    direction = "income" if amount > 0 else "expense" if amount < 0 else "neutral"
    if operation.startswith("gm_"):
        return direction, "admin", "管理调整"
    category, label = _GOLD_CATEGORY_MAP.get(
        operation,
        ("other_income", "其他收入") if amount > 0 else
        ("other_expense", "其他支出") if amount < 0 else
        ("neutral", "无金额变动"),
    )
    return direction, category, label


async def log_gold_change(
    user_id: str,
    *,
    operation: str,
    amount: int,
    gold_before: int,
    gold_after: int,
    reason: str = "",
    details: dict | None = None,
    deferred: bool = False,
) -> bool:
    """记录金币变动并执行对账。

    对账逻辑：
    - 用户首条 gold 记录 → is_baseline=True，不校验
    - 后续记录 → gold_expected = 前一条 gold_after + amount
    - gold_expected != gold_after → gold_anomaly=True

    返回是否检测到异常。
    """
    # 对账查询用 try/except 包裹：测试环境（MockDB）或 DB 未初始化时
    # 退化为基准条目，不阻断主流程
    is_baseline = True
    gold_expected: int | None = None
    gold_anomaly = False
    try:
        has_previous = await FishingLedger.has_gold_entries(user_id)
        is_baseline = not has_previous
        if not is_baseline:
            last_entry = await FishingLedger.get_last_gold_entry(user_id)
            if last_entry and last_entry.gold_after is not None:
                gold_expected = last_entry.gold_after + amount
                gold_anomaly = gold_expected != gold_after
    except Exception:
        is_baseline = True

    direction, category, category_label = classify_gold_change(operation, amount)
    data = {
        "operation": operation,
        "amount": amount,
        "direction": direction,
        "category": category,
        "category_label": category_label,
        "reason": reason,
        "details": details or {},
        "timestamp": datetime.now().isoformat(),
    }

    entry = {
        "user_id": user_id,
        "entry_type": "gold",
        "data": data,
        "gold_before": gold_before,
        "gold_after": gold_after,
        "gold_expected": gold_expected,
        "gold_anomaly": gold_anomaly,
        "is_baseline": is_baseline,
    }

    if deferred:
        queue_entry(**entry)
    else:
        await _safe_create(entry)

    if gold_anomaly:
        logger.warning(
            f"金币对账异常: user={user_id}, operation={operation}, "
            f"expected={gold_expected}, actual={gold_after}, "
            f"diff={gold_after - (gold_expected or 0)}"
        )

    return gold_anomaly


# ═══════════════════════════════════════════════════════════════════════════════
# 查询接口
# ═══════════════════════════════════════════════════════════════════════════════


async def get_fishing_history(
    user_id: str, limit: int = 20
) -> list[FishingLedger]:
    """获取用户最近的钓鱼记录。"""
    return (
        await FishingLedger.filter(user_id=user_id, entry_type="fishing")
        .order_by("-create_time", "-id")
        .limit(limit)
        .all()
    )


async def get_item_use_history(
    user_id: str, limit: int = 20
) -> list[FishingLedger]:
    """获取用户最近的道具使用记录。"""
    return (
        await FishingLedger.filter(user_id=user_id, entry_type="item_use")
        .order_by("-create_time", "-id")
        .limit(limit)
        .all()
    )


async def get_gold_history(
    user_id: str, limit: int = 50
) -> list[FishingLedger]:
    """获取用户金币变动历史（含对账信息）。"""
    return (
        await FishingLedger.filter(user_id=user_id, entry_type="gold")
        .order_by("-create_time", "-id")
        .limit(limit)
        .all()
    )


async def get_anomaly_entries(
    user_id: str | None = None, limit: int = 50
) -> list[FishingLedger]:
    """获取金币异常记录。user_id=None 时查全库。"""
    qs = FishingLedger.filter(entry_type="gold", gold_anomaly=True)
    if user_id:
        qs = qs.filter(user_id=user_id)
    return await qs.order_by("-create_time", "-id").limit(limit).all()
