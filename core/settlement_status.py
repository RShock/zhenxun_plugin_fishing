from datetime import datetime

from .context import serialize_fish_caught


def build_settlement_status(
    status_dict: dict,
    last_settle_time: datetime,
    fish_caught: list,
    bait_consumed: int,
    frame_pity: int,
    cat_frame_pity: int,
    utr_pity: int,
    cat_eaten_fish: list,
    cat_gifts: dict,
    meteor_fish_numbers: list[int] | None = None,
    bait_usage: dict[str, int] | None = None,
) -> dict:
    existing_meteor = status_dict.get("meteor_fish_numbers", [])
    if meteor_fish_numbers:
        existing_meteor = existing_meteor + meteor_fish_numbers
    # 保留影子场景、药水计数等会话元数据；结算只覆盖它负责推进的字段。
    updated_status = dict(status_dict)
    updated_status.update(
        {
            "location_id": status_dict["location_id"],
            "start_time": status_dict["start_time"],
            "last_settle_time": last_settle_time.isoformat(),
            "fish_caught": serialize_fish_caught(fish_caught),
            "bait_consumed": bait_consumed,
            "frame_pity": frame_pity,
            "cat_frame_pity": cat_frame_pity,
            "utr_pity": utr_pity,
            "cat_eaten_fish": serialize_fish_caught(cat_eaten_fish),
            "cat_gifts": cat_gifts,
            "meteor_fish_numbers": existing_meteor,
        }
    )
    # 按鱼饵类型累计已消耗明细，供回档药水精确退还（避免重复扣除）
    bait_usage_log = dict(status_dict.get("bait_usage_log", {}))
    if bait_usage:
        for bait_id, count in bait_usage.items():
            if count > 0:
                bait_usage_log[bait_id] = bait_usage_log.get(bait_id, 0) + count
    updated_status["bait_usage_log"] = bait_usage_log
    return updated_status
