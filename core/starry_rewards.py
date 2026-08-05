"""Starry fish reward grant: draw, inventory write, fragment auto-upgrade.

Pure rules live in starry_system.draw_starry_reward; this module persists rewards.
Each settled starry fish immediately draws once from its score pool.
"""

from __future__ import annotations

from zhenxun.services.log import logger

from ..models import FishingUser
from .starry_system import (
    REWARD_POOL_NAMES,
    draw_starry_reward,
    get_reward_pool,
    limit_ultimate_reward_pool,
    score_starry_fish,
)

# 碎片凑满 5 个 → 立即抽高一级奖池；可在同一次收杆内连锁结算
_FRAGMENT_SPECS = {
    "lottery_fragment_low": {
        "item_id": "lottery_fragment_low",
        "item_type": "fragment",
        "upgrade_need": 5,
        "upgrade_pool": "middle",
        "name": "中级抽奖碎片",
    },
    "lottery_fragment_mid": {
        "item_id": "lottery_fragment_mid",
        "item_type": "fragment",
        "upgrade_need": 5,
        "upgrade_pool": "high",
        "name": "高级抽奖碎片",
    },
    "lottery_fragment_high": {
        "item_id": "lottery_fragment_high",
        "item_type": "fragment",
        "upgrade_need": 5,
        "upgrade_pool": "ultimate",
        "name": "究极抽奖碎片",
    },
}

_REWARD_HANDLERS = {
    "corn": ("corn", None, None),
    "black_market_extra_ticket": ("item", "black_market_extra_ticket", "ticket"),
    "lottery_fragment_low": ("item", "lottery_fragment_low", "fragment"),
    "wish_score": ("wish_score", None, None),
    "duoduo_potion": ("item", "真多多药水", "potion"),
    "lucky_potion": ("item", "幸运药水", "potion"),
    "reset_potion": ("item", "回档药水", "potion"),
    "cat_frame": ("cat_frame", None, None),
    "lottery_fragment_mid": ("item", "lottery_fragment_mid", "fragment"),
    "lottery_fragment_high": ("item", "lottery_fragment_high", "fragment"),
    "flash_potion": ("item", "闪光药水", "potion"),
    "time_potion": ("item", "time_potion", "potion"),
    "utr_select_ticket": ("item", "utr_select_ticket", "ticket"),
}


async def _apply_single_reward(
    user_id: str,
    reward: dict,
    *,
    source: str,
) -> dict:
    """Grant one reward entry and return a display dict."""
    key = str(reward.get("key", ""))
    name = str(reward.get("name", key))
    count = int(reward.get("count", 1) or 1)
    pool = str(reward.get("pool", ""))
    handler = _REWARD_HANDLERS.get(key)
    if not handler:
        logger.warning(f"unknown starry reward key={key} user={user_id}")
        return {
            "key": key,
            "name": name,
            "count": count,
            "pool": pool,
            "pool_name": REWARD_POOL_NAMES.get(pool, pool),
            "source": source,
            "granted": False,
        }

    kind, item_id, item_type = handler
    score_bonus = 0.0
    if kind == "corn":
        await FishingUser.add_corn(user_id, count)
    elif kind == "cat_frame":
        await FishingUser.add_cat_frames(user_id, count)
    elif kind == "wish_score":
        score_bonus = float(reward.get("score_bonus", 0.5) or 0.5) * count
        user = await FishingUser.get_user(user_id)
        user.starry_score_accumulated = (
            float(user.starry_score_accumulated or 0) + score_bonus
        )
        await user.save(update_fields=["starry_score_accumulated"])
    elif kind == "item":
        await FishingUser.add_item(user_id, str(item_id), str(item_type), count)
    else:
        logger.warning(f"unimplemented reward kind={kind} key={key}")

    result = {
        "key": key,
        "name": name,
        "count": count,
        "pool": pool,
        "pool_name": reward.get("pool_name") or REWARD_POOL_NAMES.get(pool, pool),
        "source": source,
        "granted": True,
        "fish_id": reward.get("fish_id"),
        "display_score": reward.get("display_score"),
        "upgrade_from": reward.get("upgrade_from"),
    }
    if score_bonus:
        result["score_bonus"] = score_bonus
    return result


async def _resolve_fragment_upgrades(
    user_id: str,
    *,
    fish_id: str | int | None = None,
    display_score: int | None = None,
) -> list[dict]:
    """凑满碎片立刻抽奖：5中级→中级池、5高级→高级池、5究极→究极池。

    同一次收杆内可连锁（例如中级碎片合成出高级碎片后继续合成）。
    """
    granted: list[dict] = []
    for _ in range(40):
        upgraded = False
        for frag_key, spec in _FRAGMENT_SPECS.items():
            item = await FishingUser.get_item(
                user_id, spec["item_id"], spec["item_type"]
            )
            count = int(item["count"]) if item else 0
            need = int(spec["upgrade_need"])
            if count < need:
                continue
            times = count // need
            for _i in range(times):
                ok = await FishingUser.remove_item(
                    user_id, spec["item_id"], spec["item_type"], need
                )
                if not ok:
                    break
                # 碎片合成获得的奖池不受究极展品3次限制，直接使用目标池
                upgrade_pool = spec["upgrade_pool"]
                drawn = draw_starry_reward(upgrade_pool)
                if not drawn:
                    break
                drawn["upgrade_from"] = spec["name"]
                if fish_id is not None:
                    fid = str(fish_id)
                    drawn["fish_id"] = fid.zfill(6) if fid.isdigit() else fid
                if display_score is not None:
                    drawn["display_score"] = int(display_score)
                entry = await _apply_single_reward(
                    user_id,
                    drawn,
                    source=f"fragment_upgrade:{frag_key}",
                )
                granted.append(entry)
                upgraded = True
        if not upgraded:
            break
    return granted


async def grant_starry_pool_reward(
    user_id: str,
    pool: str,
    *,
    fish_id: str | int | None = None,
    display_score: int | None = None,
    limit_current_ultimate_fish: bool = False,
) -> list[dict]:
    """Draw and grant from pool immediately; resolve fragment upgrades."""
    if not pool or pool == "none":
        return []
    reward_pool = pool
    if pool == "ultimate":
        exhibition = await FishingUser.get_user_starry_exhibition(user_id)
        reward_pool = limit_ultimate_reward_pool(
            pool,
            exhibition,
            current_fish_id=fish_id if limit_current_ultimate_fish else None,
            current_display_score=display_score,
        )
    drawn = draw_starry_reward(reward_pool)
    if not drawn:
        return []
    if reward_pool != pool:
        drawn["downgraded_from"] = pool
    if fish_id is not None:
        fid = str(fish_id)
        drawn["fish_id"] = fid.zfill(6) if fid.isdigit() else fid
    if display_score is not None:
        drawn["display_score"] = int(display_score)

    results = [await _apply_single_reward(user_id, drawn, source="catch")]
    results.extend(await _resolve_fragment_upgrades(user_id))
    return results


async def grant_rewards_for_starry_fish(
    user_id: str,
    fish_id: int | str,
) -> list[dict]:
    """Score one starry fish and immediately draw its reward pool."""
    scored = score_starry_fish(fish_id)
    pool = scored.reward_pool or get_reward_pool(scored.display_score)
    return await grant_starry_pool_reward(
        user_id,
        pool,
        fish_id=scored.id_text,
        display_score=scored.display_score,
        limit_current_ultimate_fish=True,
    )
