from datetime import datetime

from ..models import BuffEffect, FishingBuff, _make_naive


def build_buff_messages(buffs: list, start_time: datetime, now: datetime) -> list[str]:
    return []


def generate_buff_message(
    buff: FishingBuff, now: datetime, is_expired: bool = False
) -> str:
    buff_end = _make_naive(buff.end_time)

    if is_expired:
        expired_hours = (now - buff_end).total_seconds() / 3600
        time_info = f"(已过时{expired_hours:.1f}小时)"
    else:
        remaining = (buff_end - now).total_seconds()
        if buff.buff_type == BuffEffect.BUFF_TYPE_NEST:
            time_info = f"(剩余{remaining / 3600:.1f}小时)"
        else:
            time_info = f"(剩余{remaining / 60:.0f}分钟)"

    # 自定义格式（有特殊数值展示的 buff）
    custom = {
        BuffEffect.BUFF_TYPE_NEST: f"速度+{buff.value}%",
        BuffEffect.BUFF_TYPE_SPEED_BOOST: f"速度+{buff.value}%",
        BuffEffect.BUFF_TYPE_DOUBLE_CATCH: "每次钓2条",
        BuffEffect.BUFF_TYPE_WEEKEND_BONUS: f"额外速度×{1 + buff.value / 100:.1f}",
        BuffEffect.BUFF_TYPE_ROD_BONUS: f"+{buff.value}",
        BuffEffect.BUFF_TYPE_FRAME: f"1-10图与S1速度+{buff.value}%",
        BuffEffect.BUFF_TYPE_STARRY_BONUS: f"1-10图与S1速度+{buff.value}% (永久)",
    }

    meta = BuffEffect.get_meta(buff.buff_type)
    if meta is None:
        # 未注册的 buff_type，回退到英文 key
        return f"{buff.buff_type} {time_info}"

    detail = custom.get(buff.buff_type)
    if buff.buff_type == BuffEffect.BUFF_TYPE_STARRY_BONUS:
        # 星空艇是永久 buff，不显示剩余时间
        suffix = f" {detail}" if detail else ""
    elif buff.buff_type == BuffEffect.BUFF_TYPE_WEEKEND_BONUS and is_expired:
        suffix = f" {detail} (已过时)" if detail else " (已过时)"
    elif detail:
        suffix = f" {detail} {time_info}"
    else:
        suffix = f" {time_info}"

    return f"{meta.emoji} {meta.display_name}:{suffix}"
