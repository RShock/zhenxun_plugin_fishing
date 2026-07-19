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
) -> dict:
    existing_meteor = status_dict.get("meteor_fish_numbers", [])
    if meteor_fish_numbers:
        existing_meteor = existing_meteor + meteor_fish_numbers
    return {
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
