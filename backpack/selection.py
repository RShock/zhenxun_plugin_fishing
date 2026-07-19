"""
鱼获选择解析器 — FishSelection 数据类、parse_fish_selection 解析函数。
"""

import re
from dataclasses import dataclass, field

from ..config import INDEX_RARITY, RARITY_INDEX


_RARITY_MAP_LOWER = {k.lower(): k for k in RARITY_INDEX}

_ALL_KEYWORDS = {"全部", "all", "所有"}

_BATCH_SEP_RE = re.compile(r"[,;，；\s]+")

_CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")


@dataclass
class FishSelection:
    rarity_letters: list[str] = field(default_factory=list)
    rarity_precise: list[str] = field(default_factory=list)
    numeric_ids: list[str] = field(default_factory=list)
    location_prefixes: list[str] = field(default_factory=list)
    select_all: bool = False

    def is_empty(self) -> bool:
        return (
            not self.rarity_letters
            and not self.rarity_precise
            and not self.numeric_ids
            and not self.location_prefixes
            and not self.select_all
        )

    def all_rarities(self) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for r in self.rarity_letters + self.rarity_precise:
            if r not in seen:
                seen.add(r)
                result.append(r)
        return result


def parse_fish_selection(fish_input: str) -> FishSelection:
    input_stripped = fish_input.strip()
    input_lower = input_stripped.lower()

    if input_lower in _ALL_KEYWORDS:
        return FishSelection(select_all=True)

    parts = _BATCH_SEP_RE.split(input_stripped)
    parts = [p for p in parts if p]

    if not parts:
        return FishSelection()

    if len(parts) == 1 and parts[0].lower() in _ALL_KEYWORDS:
        return FishSelection(select_all=True)

    result = FishSelection()
    for part in parts:
        if part.lower() in _ALL_KEYWORDS:
            return FishSelection(select_all=True)

        if part.startswith("**"):
            index_str = part[2:]
            if index_str.isdigit():
                index = int(index_str)
                if index in INDEX_RARITY:
                    result.rarity_precise.append(INDEX_RARITY[index])
            continue

        # 位置通配符：如 S1** / 1** 匹配鱼ID以该前缀开头的所有鱼
        if part.endswith("**") and len(part) > 2:
            prefix = part[:-2]
            if prefix[:2].upper() == "S1":
                result.location_prefixes.append("s1")
            else:
                result.location_prefixes.append(prefix.lower())
            continue

        if part.lower() in _RARITY_MAP_LOWER:
            result.rarity_letters.append(_RARITY_MAP_LOWER[part.lower()])
            continue

        result.numeric_ids.append(part)

    return result


def is_likely_misfire(fish_input: str) -> bool:
    """
    判断输入是否可能是误触（如「解锁道具组合是这个游戏充值服务爽点」）。

    判定条件：输入含汉字，且不含任何有效选择器
    （rarity 字母 / **N / 全部|all|所有 / 纯数字 ID）。
    用于锁鱼/解锁 handler 静默忽略明显不是指令的误触文本。
    """
    stripped = fish_input.strip()
    if not stripped:
        return False
    if not _CHINESE_RE.search(stripped):
        return False
    for part in _BATCH_SEP_RE.split(stripped):
        if not part:
            continue
        if part.lower() in _ALL_KEYWORDS:
            return False
        if part.startswith("**"):
            if part[2:].isdigit() and int(part[2:]) in INDEX_RARITY:
                return False
            continue
        if part.endswith("**") and len(part) > 2:
            return False
        if part.lower() in _RARITY_MAP_LOWER:
            return False
        if part.isdigit():
            return False
    return True