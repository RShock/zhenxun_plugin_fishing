"""群聊每日动作限流（收杆 / 钓鱼状态）。

默认开启；GM 可通过 ``gm限流开启`` / ``gm限流关闭`` 全局切换。
关闭后，群聊中查看钓鱼状态与收杆不再受每日次数限制（私聊本身无限流）。
"""

from ..constants import DAILY_ACTION_LIMIT, MAX_STATUS_PER_DAY

# 全局限流开关（进程内，默认开启）。重启后恢复为开启。
_GROUP_ACTION_LIMIT_ENABLED = True


def is_group_action_limit_enabled() -> bool:
    """群聊收杆/钓鱼状态限流是否开启。"""
    return _GROUP_ACTION_LIMIT_ENABLED


def set_group_action_limit_enabled(enabled: bool) -> None:
    """设置群聊收杆/钓鱼状态限流开关。"""
    global _GROUP_ACTION_LIMIT_ENABLED
    _GROUP_ACTION_LIMIT_ENABLED = bool(enabled)


def remaining_stop_actions(stop_count: int, status_count: int) -> int:
    return DAILY_ACTION_LIMIT - status_count - stop_count


def max_status_views(stop_count: int) -> int:
    return min(MAX_STATUS_PER_DAY, DAILY_ACTION_LIMIT - stop_count)


def is_last_stop_action(stop_count: int, status_count: int) -> bool:
    return stop_count + 1 >= DAILY_ACTION_LIMIT - status_count


def is_last_status_view(status_count: int, stop_count: int) -> bool:
    return status_count + 1 >= max_status_views(stop_count)
