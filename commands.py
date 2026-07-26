"""钓鱼插件公开指令的单一注册源。

每条公开指令在这里同时声明正则、Matcher 属性名、Web 可用性和插件元数据别名。
QQ 端的 ``matchers.py`` 与 Web 端的 ``command_router.py`` 都只能按名称读取本表，
禁止另建平行命令表；GM / 调试命令因权限模型不同，仍留在 ``matchers.py``。

不要给指令增加 category：帮助页由人工维护，运行时注册不承担展示分组职责。
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class CommandDef:
    pattern: str
    name: str
    matcher: str
    aliases: tuple[str, ...]
    web: bool = True


COMMAND_DEFS: tuple[CommandDef, ...] = (
    CommandDef(r"(?:钓鱼|抛竿|抛杆)(?:\s*((?:-?\d+(?:\.\d+)?)|[sS]1)(?=\s|$))?", "钓鱼", "fishing_matcher", ("钓鱼", "抛竿")),
    CommandDef(r"(?:收杆|收钩|收线|收竿)", "收杆", "stop_fishing_matcher", ("收杆",)),
    CommandDef(r"背包", "背包", "backpack_matcher", ("背包",)),
    # “卖鱼饵”是独立公开指令；负向前瞻避免先被更短的“卖鱼”吞掉。
    CommandDef(r"卖鱼(?!饵)(?:\s*(.+))?", "卖鱼", "sell_fish_matcher", ("卖鱼",)),
    CommandDef(r"(?:鱼店|鱼币商店|钓鱼商店)", "鱼店", "shop_matcher", ("鱼店", "鱼币商店", "钓鱼商店")),
    CommandDef(r"升级(?:鱼竿|钓杆|鱼杆|钓竿)", "升级钓竿", "upgrade_rod_matcher", ("升级钓竿", "升级鱼竿")),
    CommandDef(r"升级(?:鱼钩|钓钩|吊钩|渔钩)", "升级鱼钩", "upgrade_hook_matcher", ("升级鱼钩",)),
    # “买鱼饵”是“鱼店购买”的前缀别名（与“卖出鱼饵 鱼饵名”对称）：买鱼饵 鱼饵名 [数量]
    CommandDef(r"(?:鱼店购买|买鱼饵)\s*(\S+)(?:\s+(\d+))?", "购买", "buy_matcher", ("鱼店购买", "买鱼饵")),
    # 展示框万能升级：升级展示栏/升级展示框/升级木框/升级星空展示框 均为同一指令的别名
    CommandDef(r"(?:升级展示栏|升级展示框|升级展示位|升级木框|升级星空展示框|升级星空木框|增加展示栏位|扩展展示栏|扩充展示栏|强化展示栏位|星空木框|展示框|猫猫展示框|星空展示框)", "升级展示栏", "display_slot_matcher", ("升级展示栏", "升级展示框", "升级木框", "升级星空展示框", "增加展示栏位", "强化展示栏位")),
    CommandDef(r"(?:钓鱼状态|状态)", "钓鱼状态", "status_matcher", ("钓鱼状态",)),
    CommandDef(r"(?:钓鱼打窝|打窝)(?:\s+(\d+))?", "打窝", "nest_matcher", ("打窝",)),
    CommandDef(r"(?:钓鱼图鉴|图鉴|查看图鉴)([12]?)", "图鉴", "collection_matcher", ("钓鱼图鉴", "图鉴", "查看图鉴")),
    CommandDef(r"(?:流星鱼展馆|星空祈愿展馆|星空起源展馆|星空鱼展馆|星空展馆|星鱼展馆)", "星空鱼展馆", "starry_exhibition_matcher", ("流星鱼展馆",)),
    CommandDef(r"(?:星空排行|星空排名|星空排行榜)", "星空排行", "starry_ranking_matcher", ("星空排行",)),
    CommandDef(r"钓鱼币兑换(?:\s*(\d+))?", "兑换", "exchange_matcher", ("钓鱼币兑换",)),
    CommandDef(r"(?:黑商|黑市)撤回(?:\s*(\d+))?", "黑商撤回", "black_market_revoke_matcher", ("黑商撤回",)),
    CommandDef(r"(?:黑商|黑市)(?:交换)?(?:\s*(.*))?", "黑商交换", "black_market_matcher", ("黑商交换",)),
    CommandDef(r"(?:白商|白市)", "白商", "white_market_matcher", ("白商",)),
    CommandDef(r"(?:白商|白市)(?:交换)?\s*(.+)", "白商交换", "white_market_exchange_matcher", ("白商交换",)),
    CommandDef(r"锁鱼(?:\s*(.+))?", "锁鱼", "lock_fish_matcher", ("锁鱼",)),
    CommandDef(r"解锁(?:\s*(.+))?", "解锁", "unlock_fish_matcher", ("解锁",)),
    CommandDef(r"(?:赠送|送鱼)(?:\s*((?:[sS]1\d{2})|-?\d+))?", "赠送", "gift_fish_matcher", ("赠送", "送鱼")),
    CommandDef(r"自动卖鱼(?:\s*(开启|关闭|N|R|SR|SSR|UR|UTR))?", "自动卖鱼", "auto_sell_matcher", ("自动卖鱼",)),
    CommandDef(r"自动锁鱼(?:\s*(.*))?", "自动锁鱼", "auto_lock_matcher", ("自动锁鱼",)),
    CommandDef(r"钓鱼改名(?:\s*(.+))?", "改名", "rename_matcher", ("钓鱼改名",)),
    CommandDef(r"更换皮肤(?:\s*(\S+))?", "更换皮肤", "skin_matcher", ("更换皮肤",)),
    CommandDef(r"钓鱼使用\s*(\S+)(?:\s+(.+))?", "使用物品", "use_item_matcher", ("钓鱼使用",)),
    CommandDef(r"(?:天气预报|钓鱼天气|天气|天气状态)(?:\s*([12]))?", "天气", "weather_forecast_matcher", ("天气预报", "钓鱼天气", "天气", "天气状态")),
    CommandDef(r"建设猫猫乐园(?:\s*(.+))?", "建设猫猫乐园", "cat_park_build_matcher", ("建设猫猫乐园",)),
    CommandDef(r"建设星空艇", "建设星空艇", "build_starry_ship_matcher", ("建设星空艇",)),
    CommandDef(r"(?:设定鱼饵|设置鱼饵|选择鱼饵)\s*(.*)", "设定鱼饵", "set_bait_matcher", ("设定鱼饵",)),
    CommandDef(r"(?:卖出鱼饵|卖鱼饵)\s+(.+)", "卖出鱼饵", "sell_bait_matcher", ("卖出鱼饵",)),
    CommandDef(r"(?:钓鱼公告|钓鱼广播)\s+(.+)", "钓鱼公告", "fishing_announcement_matcher", ("钓鱼公告",), web=False),
)

COMMAND_MAP: dict[str, CommandDef] = {command.name: command for command in COMMAND_DEFS}


def get_command_pattern(name: str) -> str:
    """按稳定名称获取正则，避免调用方依赖声明顺序。"""
    try:
        return COMMAND_MAP[name].pattern
    except KeyError as exc:
        raise KeyError(f"未知钓鱼命令定义: {name}") from exc


def iter_web_commands() -> Iterator[CommandDef]:
    """返回 Web 端可执行的公开指令。"""
    return (command for command in COMMAND_DEFS if command.web)


def iter_command_aliases() -> Iterator[str]:
    """返回插件元数据使用的去重指令别名，顺序与声明一致。"""
    seen: set[str] = set()
    for command in COMMAND_DEFS:
        for alias in command.aliases:
            if alias not in seen:
                seen.add(alias)
                yield alias


def find_command_pattern(command_text: str, names: Iterable[str] | None = None) -> str | None:
    """返回完整匹配 ``command_text`` 的命令名。"""
    allowed = set(names) if names is not None else None
    for command in COMMAND_DEFS:
        if allowed is not None and command.name not in allowed:
            continue
        if re.fullmatch(command.pattern, command_text):
            return command.name
    return None
