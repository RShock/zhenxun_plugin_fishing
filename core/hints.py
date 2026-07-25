"""
保底/升级提示生成 — 纯计算，无 async，方便单测。
"""

from ..constants import (
    CAT_FRAME_PITY_THRESHOLD,
    FRAME_PITY_THRESHOLD,
    UPGRADE_DISPLAY_COSTS,
    UTR_PITY_THRESHOLD,
)


def build_pity_hints(
    total_fish: list,
    frame_pity: int,
    cat_frame_pity: int,
    utr_pity: int,
    display_slots: int,
    upgraded_display_count: int,
    cat_frames: int,
    effects_now: dict | None,
    skip_frame_pity: bool = False,
    is_starry: bool = False,
) -> list[str]:
    hints: list[str] = []

    has_frame = any(fish.id in ("展示木框", "木框") for fish, _, _, *_ in total_fish)
    if not skip_frame_pity and not has_frame:
        # 当前这一杆尚未结算，提示的是“再钓多少次会触发”，需包含即将进行的一次。
        remaining = FRAME_PITY_THRESHOLD - frame_pity
        hints.append(f"🖼️ 距离下次木框保底还有{remaining}次")
    if cat_frame_pity > 0:
        cat_remaining = CAT_FRAME_PITY_THRESHOLD - cat_frame_pity
        hints.append(f"🐱 距离下次猫框保底还有{cat_remaining}次")
    if utr_pity > 0:
        # 玩家口径“X次后必出”包含触发保底的下一次。
        utr_remaining = max(0, UTR_PITY_THRESHOLD - utr_pity)
        if is_starry:
            hints.append(
                f"✨ UTR保底: {utr_pity}/{UTR_PITY_THRESHOLD}（{utr_remaining}次后必出）"
            )
        else:
            hints.append(
                f"🌀 迷途风UTR保底: {utr_pity}/{UTR_PITY_THRESHOLD}（{utr_remaining}次后必出）"
            )
    if (
        display_slots > 0
        and upgraded_display_count < display_slots
        and upgraded_display_count < 10
    ):
        next_upgrade = upgraded_display_count + 1
        frames_needed = UPGRADE_DISPLAY_COSTS.get(next_upgrade, next_upgrade)
        if cat_frames >= frames_needed:
            hints.append(
                f"🐱 猫框足够！输入【升级展示栏】可强化展示框（需要{frames_needed}个，当前{cat_frames}个）"
            )

    return hints
