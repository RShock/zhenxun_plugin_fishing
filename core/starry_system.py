"""Pure rules for the S2 starry fish system.

This module intentionally has no database dependency. Settlement, rewards and UI can
reuse these helpers without duplicating the six-digit scoring rules.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
import math
import random

from ..constants import (
    STARRY_FISH_DROP_RATE,
    STARRY_FISH_ROD_BONUS_PER_LEVEL,
    STARRY_FISH_ROD_BONUS_THRESHOLD,
    STARRY_FISH_SOLAR_WIND_BONUS,
)

DIGITS = 6
REWARD_POOL_NAMES = {
    "none": "无奖励",
    "low": "低级奖池",
    "middle": "中级奖池",
    "high": "高级奖池",
    "ultimate": "究极奖池",
}

# 抽奖碎片永远比「当前奖池」高一级：
# 低级池 → 中级碎片；中级池 → 高级碎片；高级池 → 究极碎片。
# 内部 item key 沿用历史 ID，避免已有库存失效。
STARRY_REWARD_POOL_ITEMS: dict[str, tuple[dict[str, object], ...]] = {
    "low": (
        {"key": "corn", "name": "玉米", "count": 1},
        {"key": "black_market_extra_ticket", "name": "黑商额外兑换券", "count": 1},
        {"key": "lottery_fragment_low", "name": "中级抽奖碎片", "count": 1},
        {"key": "wish_score", "name": "0.5积分", "count": 1, "score_bonus": 0.5},
    ),
    "middle": (
        {"key": "duoduo_potion", "name": "真多多药水", "count": 1},
        {"key": "lucky_potion", "name": "幸运药水", "count": 1},
        {"key": "reset_potion", "name": "回档药水", "count": 1},
        {"key": "cat_frame", "name": "猫框", "count": 3},
        {"key": "lottery_fragment_mid", "name": "高级抽奖碎片", "count": 1},
    ),
    "high": (
        {"key": "flash_potion", "name": "闪光药水", "count": 1},
        {"key": "time_potion", "name": "时光药水", "count": 1},
        {"key": "utr_select_ticket", "name": "UTR自选券", "count": 1},
        {"key": "lottery_fragment_high", "name": "究极抽奖碎片", "count": 1},
    ),
    "ultimate": (
        {"key": "time_potion", "name": "时光药水", "count": 10},
        {"key": "utr_select_ticket", "name": "UTR自选券", "count": 10},
    ),
}


def draw_starry_reward(
    pool: str,
    *,
    rng: random.Random | None = None,
) -> dict | None:
    """Equal-probability draw from a starry reward pool (pure, no DB)."""
    items = STARRY_REWARD_POOL_ITEMS.get(pool) or ()
    if not items:
        return None
    chooser = rng.choice if rng is not None else random.choice
    item = chooser(items)
    result: dict = {
        "key": item["key"],
        "name": item["name"],
        "count": int(item.get("count", 1) or 1),
        "pool": pool,
        "pool_name": REWARD_POOL_NAMES.get(pool, pool),
    }
    if "score_bonus" in item:
        result["score_bonus"] = item["score_bonus"]
    return result


HENGJIYUAN_DIGITS = "2345678"
MIRACLE_TARGET = 7_777_777
MIRACLE_MOD_BASE = 10_000_000
# 奇迹精确搜索最多取编号最大的 N 条做 MITM（默认 26）
MIRACLE_MAX_EXACT_N = 26
S2_TICKET_SCORE_THRESHOLD = 1200.0
# 星空框是升级星空展示框所需的库存，不设持有上限。
EXHIBITION_MIN_SCORE = 4
EXHIBITION_LIMIT = 10

CN_FAMILY = {
    "same_run": "同号连段",
    "step_high": "步步高",
    "slide": "滑梯",
    "pure_snake": "纯正贪吃蛇",
    "snake": "贪吃蛇",
    "palindrome": "镜像回文",
    "range": "区间色系",
    "parity": "奇偶色系",
    "rhythm": "周期节奏",
    "star_airplane": "星空飞机",
    "pairs": "对子",
    "full_house": "葫芦",
    "chunk_sequence": "分块连号",
    "pihu": "屁胡",
}

FEATURES = [
    ("same_run", 3, "3_same_run", 1.432856),
    ("same_run", 4, "4_same_run", 2.552842),
    ("same_run", 5, "5_same_run", 3.721246),
    ("same_run", 6, "6_same_run", 5.000000),
    ("step_high", 3, "3_step_high", 1.227224),
    ("step_high", 4, "4_step_high", 2.402305),
    ("step_high", 5, "5_step_high", 3.638272),
    ("step_high", 6, "6_step_high", 5.000000),
    ("slide", 3, "3_slide", 0.757901),
    ("slide", 4, "4_slide", 1.517984),
    ("slide", 5, "5_slide", 2.368759),
    ("slide", 6, "6_slide", 3.337242),
    ("pure_snake", 3, "3_pure_snake", 1.180417),
    ("pure_snake", 4, "4_pure_snake", 1.874649),
    ("pure_snake", 5, "5_pure_snake", 2.698536),
    ("pure_snake", 6, "6_pure_snake", 3.653647),
    ("snake", 3, "3_snake", 1.180417),
    ("snake", 4, "4_snake", 1.567993),
    ("snake", 5, "5_snake", 2.133004),
    ("snake", 6, "6_snake", 2.838033),
    ("palindrome", 3, "3_palindrome", 0.505804),
    ("palindrome", 4, "4_palindrome", 1.570086),
    ("palindrome", 5, "5_palindrome", 1.705313),
    ("palindrome", 6, "6_palindrome", 3.004365),
    ("range", 6, "6_all_small_0_4", 1.806180),
    ("range", 6, "6_all_big_5_9", 1.806180),
    # 全奇/全偶：每一位均有 5/10 的合法数字，概率=(1/2)^6=1/64
    # 分值 = -log10(1/64) = 1.806180
    ("parity", 6, "6_all_odd", 1.806180),
    ("parity", 6, "6_all_even", 1.806180),
    ("rhythm", 4, "ABAB", 1.598599),
    ("rhythm", 6, "ABCABC", 3.142668),
    ("star_airplane", 6, "star_airplane", 1.899285),
    # 两对：相邻两段长度≥2且数字不同（如 000011）；全量 25380/1e6 → 1.595508
    ("pairs", 2, "two_pair", 1.595508),
    ("pairs", 3, "three_pair", 3.091515),
    # 葫芦：任意 5 位窗口为 AAABB 或 AABBB；存在即计一次
    # 分值 = -log10(出现概率)，全量 3510/1e6 → 2.454693
    ("full_house", 5, "full_house", 2.454693),
    # 分块连号：2+2+2 或 3+3 分块后，块值严格递增/递减 1；命中计一次
    # 全量 2194/1e6 → 2.658763
    ("chunk_sequence", 6, "chunk_sequence", 2.658763),
    # 屁胡赋分采用宽松理论概率：只看是否有某数字至少出现 3 次，允许同时包含其他番型。
    # 全量 157600/1e6 → 0.802444；实际结算仍是严格兜底，不与其他番型叠加。
    ("pihu", 6, "pihu", 0.802444),
]
FEATURE_BY_LABEL = {
    label: i for i, (_family, _length, label, _score) in enumerate(FEATURES)
}
FEATURE_SCORE = {label: score for _family, _length, label, score in FEATURES}


@dataclass(frozen=True)
class StarryFeature:
    label: str
    family: str
    span: str
    score: float
    note: str = ""

    @property
    def display_name(self) -> str:
        return label_cn(self.label)


@dataclass(frozen=True)
class StarryFish:
    fish_id: int
    raw_score: float
    display_score: int
    features: tuple[StarryFeature, ...]
    reward_pool: str

    @property
    def id_text(self) -> str:
        return format_starry_fish_id(self.fish_id)

    @property
    def feature_summary(self) -> str:
        if not self.features:
            return "无显著番型"
        return " + ".join(feature.display_name for feature in self.features[:4])


def format_starry_fish_id(value: int | str) -> str:
    numeric = int(value)
    if numeric < 0 or numeric > 999_999:
        raise ValueError("starry fish id must be in 0..999999")
    return f"{numeric:06d}"


def digits_of(value: int | str) -> list[int]:
    return [int(ch) for ch in format_starry_fish_id(value)]


def _sign(value: int) -> int:
    return (value > 0) - (value < 0)


def _window_same(digits: Sequence[int], start: int, length: int) -> bool:
    return all(digits[start + i] == digits[start] for i in range(length))


def _window_step(digits: Sequence[int], start: int, length: int) -> bool:
    diff = digits[start + 1] - digits[start]
    return diff in (1, -1) and all(
        digits[start + i] - digits[start + i - 1] == diff for i in range(2, length)
    )


def _window_slide(digits: Sequence[int], start: int, length: int) -> bool:
    diffs = [digits[start + i] - digits[start + i - 1] for i in range(1, length)]
    return all(diff in (0, 1) for diff in diffs) or all(
        diff in (0, -1) for diff in diffs
    )


def _window_snake(digits: Sequence[int], start: int, length: int, pure: bool) -> bool:
    previous = 0
    moved = False
    turned = False
    for i in range(1, length):
        diff = digits[start + i] - digits[start + i - 1]
        if pure:
            if diff not in (1, -1):
                return False
        elif diff < -1 or diff > 1:
            return False
        direction = _sign(diff)
        if direction:
            moved = True
            if previous and direction != previous:
                turned = True
            previous = direction
    return moved and turned


def _window_palindrome(digits: Sequence[int], start: int, length: int) -> bool:
    return all(
        digits[start + i] == digits[start + length - 1 - i] for i in range(length // 2)
    )


def _motif_abab(digits: Sequence[int], start: int) -> bool:
    return (
        digits[start] == digits[start + 2]
        and digits[start + 1] == digits[start + 3]
        and digits[start] != digits[start + 1]
    )


def _motif_abcabc(digits: Sequence[int]) -> bool:
    a, b, c = digits[0], digits[1], digits[2]
    return a == digits[3] and b == digits[4] and c == digits[5] and len({a, b, c}) == 3


def _chunk_sequence_mode(digits: Sequence[int]) -> str | None:
    """识别六位编号按 2+2+2 或 3+3 分块后的相邻整数连号。"""
    two_digit = [digits[i] * 10 + digits[i + 1] for i in range(0, DIGITS, 2)]
    if (
        two_digit[1] - two_digit[0] == two_digit[2] - two_digit[1]
        and abs(two_digit[1] - two_digit[0]) == 1
    ):
        return "2+2+2"
    three_digit = [
        digits[0] * 100 + digits[1] * 10 + digits[2],
        digits[3] * 100 + digits[4] * 10 + digits[5],
    ]
    if abs(three_digit[1] - three_digit[0]) == 1:
        return "3+3"
    return None


def _star_airplane(digits: Sequence[int]) -> bool:
    return all(
        digits[i] == digits[i - 1] or digits[i] == digits[i + 1]
        for i in range(1, DIGITS - 1)
    )


def _detect_pairs(digits: Sequence[int]) -> tuple[int, str]:
    """Adjacency-based pair detection.

    Returns (pair_type, span) where pair_type is 0 (none), 2 (two_pair), or 3 (three_pair).

    two_pair: two consecutive runs both with length >= 2 and different digits.
      e.g. 000011 → runs [0000, 11] → consecutive, both ≥2, 0≠1 → two_pair.
    three_pair: exactly 3 runs of length 2 (covering all 6 digits),
      middle run's digit differs from both sides (sides may be same).
      e.g. 001122 → three_pair; 001100 → three_pair (sides same, middle different).
    three_pair absorbs two_pair (checked first).
    """
    run_digit: list[int] = []
    run_len: list[int] = []
    run_start: list[int] = []
    index = 0
    while index < len(digits):
        end = index + 1
        while end < len(digits) and digits[end] == digits[index]:
            end += 1
        run_digit.append(digits[index])
        run_len.append(end - index)
        run_start.append(index)
        index = end

    n = len(run_digit)

    # three_pair: exactly 3 runs, each length 2, middle differs from both sides
    if n == 3 and run_len[0] == 2 and run_len[1] == 2 and run_len[2] == 2:
        if run_digit[1] != run_digit[0] and run_digit[1] != run_digit[2]:
            span = f"{run_start[0] + 1}-{run_start[2] + run_len[2]}"
            return 3, span

    # two_pair: consecutive runs both length >= 2 and different digits
    for i in range(n - 1):
        if run_len[i] >= 2 and run_len[i + 1] >= 2 and run_digit[i] != run_digit[i + 1]:
            span = f"{run_start[i] + 1}-{run_start[i + 1] + run_len[i + 1]}"
            return 2, span

    return 0, ""


def _window_full_house(digits: Sequence[int], start: int) -> bool:
    """5-digit window is AAABB or AABBB: exactly two same-digit runs of
    lengths 3+2 or 2+3.
    """
    window = digits[start : start + 5]
    if len(window) < 5:
        return False
    run_lengths: list[int] = []
    index = 0
    while index < 5:
        end = index + 1
        while end < 5 and window[end] == window[index]:
            end += 1
        run_lengths.append(end - index)
        index = end
    return run_lengths == [3, 2] or run_lengths == [2, 3]


def _full_house_spans(digits: Sequence[int]) -> list[tuple[int, int]]:
    """Return (start, end) spans of all 5-digit full-house windows."""
    return [
        (start, start + 5)
        for start in range(DIGITS - 5 + 1)
        if _window_full_house(digits, start)
    ]


def _build_ok(digits: Sequence[int]) -> dict[str, dict[tuple[int, int], bool]]:
    return {
        "same_run": {
            (start, length): _window_same(digits, start, length)
            for length in range(3, DIGITS + 1)
            for start in range(DIGITS - length + 1)
        },
        "step_high": {
            (start, length): _window_step(digits, start, length)
            for length in range(3, DIGITS + 1)
            for start in range(DIGITS - length + 1)
        },
        "slide": {
            (start, length): _window_slide(digits, start, length)
            for length in range(3, DIGITS + 1)
            for start in range(DIGITS - length + 1)
        },
        "pure_snake": {
            (start, length): _window_snake(digits, start, length, True)
            for length in range(3, DIGITS + 1)
            for start in range(DIGITS - length + 1)
        },
        "snake": {
            (start, length): _window_snake(digits, start, length, False)
            for length in range(3, DIGITS + 1)
            for start in range(DIGITS - length + 1)
        },
        "palindrome": {
            (start, length): _window_palindrome(digits, start, length)
            for length in range(3, DIGITS + 1)
            for start in range(DIGITS - length + 1)
        },
    }


def _contained_in_larger(
    ok: dict[tuple[int, int], bool], start: int, length: int
) -> bool:
    for bigger in range(length + 1, DIGITS + 1):
        for bigger_start in range(0, DIGITS - bigger + 1):
            if (
                bigger_start <= start
                and start + length <= bigger_start + bigger
                and ok.get((bigger_start, bigger), False)
            ):
                return True
    return False



def _format_digit_span(positions: Iterable[int]) -> str:
    """Compact 0-based indices into a 1-based span string (e.g. 1-2,6)."""
    ordered = sorted({int(pos) for pos in positions if 0 <= int(pos) < DIGITS})
    if not ordered:
        return ""
    ranges: list[tuple[int, int]] = []
    start = prev = ordered[0]
    for pos in ordered[1:]:
        if pos == prev + 1:
            prev = pos
            continue
        ranges.append((start, prev))
        start = prev = pos
    ranges.append((start, prev))
    parts: list[str] = []
    for left, right in ranges:
        if left == right:
            parts.append(str(left + 1))
        else:
            parts.append(f"{left + 1}-{right + 1}")
    return ",".join(parts)


def _pihu_positions(digits: Sequence[int]) -> list[int]:
    """Positions whose digit value appears at least 3 times (屁胡同号位)."""
    counts = Counter(digits)
    hot = {digit for digit, count in counts.items() if count >= 3}
    return [index for index, digit in enumerate(digits) if digit in hot]


def _feature(label: str, family: str, span: str, note: str = "") -> StarryFeature:
    return StarryFeature(label, family, span, FEATURE_SCORE[label], note)


def score_starry_fish(value: int | str) -> StarryFish:
    digits = digits_of(value)
    ok = _build_ok(digits)
    features: list[StarryFeature] = []

    if all(0 <= digit <= 4 for digit in digits):
        features.append(_feature("6_all_small_0_4", "range", "1-6"))
    if all(5 <= digit <= 9 for digit in digits):
        features.append(_feature("6_all_big_5_9", "range", "1-6"))
    if all(digit % 2 == 1 for digit in digits):
        features.append(_feature("6_all_odd", "parity", "1-6", "六位数字全部为奇数"))
    if all(digit % 2 == 0 for digit in digits):
        features.append(_feature("6_all_even", "parity", "1-6", "六位数字全部为偶数"))
    if _star_airplane(digits):
        features.append(
            _feature("star_airplane", "star_airplane", "1-6", "第2-5位均属于至少2连块")
        )

    for length in range(3, DIGITS + 1):
        for start in range(DIGITS - length + 1):
            span = f"{start + 1}-{start + length}"
            if ok["same_run"][(start, length)] and not _contained_in_larger(
                ok["same_run"], start, length
            ):
                features.append(_feature(f"{length}_same_run", "same_run", span))
            if ok["slide"][(start, length)] and not _contained_in_larger(
                ok["slide"], start, length
            ):
                if ok["step_high"][(start, length)]:
                    features.append(
                        _feature(
                            f"{length}_step_high",
                            "step_high",
                            span,
                            "纯正替代普通滑梯计分",
                        )
                    )
                else:
                    features.append(_feature(f"{length}_slide", "slide", span))
            if ok["snake"][(start, length)] and not _contained_in_larger(
                ok["snake"], start, length
            ):
                if ok["pure_snake"][(start, length)]:
                    features.append(
                        _feature(
                            f"{length}_pure_snake",
                            "pure_snake",
                            span,
                            "纯正替代普通贪吃蛇计分",
                        )
                    )
                else:
                    features.append(_feature(f"{length}_snake", "snake", span))
            if ok["palindrome"][(start, length)] and not _contained_in_larger(
                ok["palindrome"], start, length
            ):
                features.append(_feature(f"{length}_palindrome", "palindrome", span))

    for start in range(DIGITS - 4 + 1):
        if _motif_abab(digits, start):
            features.append(_feature("ABAB", "rhythm", f"{start + 1}-{start + 4}"))
    if _motif_abcabc(digits):
        features.append(_feature("ABCABC", "rhythm", "1-6"))

    full_house_spans = _full_house_spans(digits)
    has_full_house = bool(full_house_spans)

    pair_type, pair_span = _detect_pairs(digits)
    if pair_type >= 3:
        features.append(
            _feature(
                "three_pair",
                "pairs",
                pair_span,
                "三段长度为2且中间与两侧不同",
            )
        )
    elif pair_type >= 2 and not has_full_house:
        # 两对是葫芦的子牌型：命中葫芦时不单独计分，由葫芦吸收。
        features.append(
            _feature(
                "two_pair",
                "pairs",
                pair_span,
                "相邻两段长度≥2且数字不同",
            )
        )

    if has_full_house:
        # 存在即计一次（不因两个 5 位窗口同时命中而叠分）
        span = f"{full_house_spans[0][0] + 1}-{full_house_spans[-1][1]}"
        features.append(
            _feature("full_house", "full_house", span, "5位窗口为AAABB或AABBB")
        )

    sequence_mode = _chunk_sequence_mode(digits)
    if sequence_mode:
        features.append(
            _feature(
                "chunk_sequence",
                "chunk_sequence",
                "1-6",
                f"按{sequence_mode}分块后严格递增或递减1",
            )
        )

    # 屁胡是严格兜底番型：其他任何番型均未命中时才有资格触发。
    # 标记仅覆盖出现次数≥3的同号位，避免整段 1-6 全亮。
    if not features and max(Counter(digits).values()) >= 3:
        pihu_pos = _pihu_positions(digits)
        features.append(
            _feature(
                "pihu",
                "pihu",
                _format_digit_span(pihu_pos),
                "无其他番型且某数字至少出现3次",
            )
        )

    features = sorted(features, key=lambda item: (-item.score, item.span, item.label))
    raw_score = sum(item.score for item in features)
    display_score = int(math.floor(raw_score + 0.5))
    return StarryFish(
        fish_id=int(format_starry_fish_id(value)),
        raw_score=raw_score,
        display_score=display_score,
        features=tuple(features),
        reward_pool=get_reward_pool(display_score),
    )


def label_cn(label: str) -> str:
    direct = {
        "6_all_small_0_4": "6位全小(0-4)",
        "6_all_big_5_9": "6位全大(5-9)",
        "6_all_odd": "6位全奇",
        "6_all_even": "6位全偶",
        "ABAB": "ABAB",
        "ABCABC": "ABCABC",
        "star_airplane": "星空飞机",
        "two_pair": "两对",
        "three_pair": "三对",
        "full_house": "葫芦",
        "chunk_sequence": "连号",
        "pihu": "屁胡",
    }
    if label in direct:
        return direct[label]
    length, family = label.split("_", 1)
    suffix = {
        "same_run": "同号连段",
        "step_high": "步步高",
        "slide": "滑梯",
        "pure_snake": "纯正贪吃蛇",
        "snake": "贪吃蛇",
        "palindrome": "回文",
    }[family]
    return f"{length}位{suffix}"


def get_reward_pool(display_score: int) -> str:
    if display_score <= 0:
        return "none"
    if display_score <= 2:
        return "low"
    if display_score <= 5:
        return "middle"
    if display_score <= 10:
        return "high"
    return "ultimate"


def band(display_score: int) -> str:
    if display_score == 0:
        return "普通"
    if display_score <= 2:
        return "小吉"
    if display_score <= 4:
        return "良品"
    if display_score <= 6:
        return "稀有"
    if display_score <= 8:
        return "珍品"
    if display_score <= 10:
        return "极品"
    if display_score <= 12:
        return "传说"
    return "神话"


def compare_starry_fish(left: int | str, right: int | str) -> int:
    left_scored = score_starry_fish(left)
    right_scored = score_starry_fish(right)
    if left_scored.raw_score != right_scored.raw_score:
        if left_scored.raw_score > right_scored.raw_score:
            return left_scored.fish_id
        return right_scored.fish_id
    return max(left_scored.fish_id, right_scored.fish_id)


def generate_starry_fish_id(hengjiyuan: bool = False) -> int:
    if hengjiyuan:
        return int("".join(random.choice(HENGJIYUAN_DIGITS) for _ in range(DIGITS)))
    return random.randint(0, 999_999)


def get_starry_fish_drop_rate(
    *,
    rod_level: int = 0,
    solar_wind: bool = False,
    gamma_ray_burst: bool = False,
) -> float:
    """计算星空鱼（流星鱼）掉落率。

    基础、鱼竿和太阳风先按绝对加值合计；闪光药水自带太阳风，
    并在合计后将最终掉落率翻倍，最终概率不超过 100%。
    """
    rod_bonus_levels = max(0, int(rod_level) - STARRY_FISH_ROD_BONUS_THRESHOLD)
    rod_bonus = rod_bonus_levels * STARRY_FISH_ROD_BONUS_PER_LEVEL
    has_solar_wind = solar_wind or gamma_ray_burst
    solar_bonus = STARRY_FISH_SOLAR_WIND_BONUS if has_solar_wind else 0.0
    drop_rate = STARRY_FISH_DROP_RATE + rod_bonus + solar_bonus
    if gamma_ray_burst:
        drop_rate *= 2
    return min(1.0, drop_rate)


def roll_starry_fish(
    *,
    rod_level: int = 0,
    solar_wind: bool = False,
    meteor_shower: bool = False,
    hengjiyuan: bool = False,
    lucky_double: bool = False,
    gamma_ray_burst: bool = False,
) -> StarryFish | None:
    drop_rate = get_starry_fish_drop_rate(
        rod_level=rod_level,
        solar_wind=solar_wind,
        gamma_ray_burst=gamma_ray_burst,
    )
    if random.random() >= drop_rate:
        return None

    candidates = [generate_starry_fish_id(hengjiyuan=hengjiyuan)]
    if meteor_shower:
        candidates.append(generate_starry_fish_id(hengjiyuan=hengjiyuan))
    if lucky_double:
        candidates.append(generate_starry_fish_id(hengjiyuan=hengjiyuan))

    best = candidates[0]
    for candidate in candidates[1:]:
        best = compare_starry_fish(best, candidate)
    return score_starry_fish(best)


def expand_starry_fish_with_duoduo(
    fish_id: int | str,
    *,
    duoduo_active: bool = False,
) -> list[int]:
    """真多多药水对流星鱼的后置结算。

    不参与掉落率与编号生成；在最终产物确定后，若多多生效，
    则复制为两条**相同编号**的流星鱼。
    """
    normalized = int(format_starry_fish_id(fish_id))
    if duoduo_active:
        return [normalized, normalized]
    return [normalized]


def _mitm_exact_indices(
    normalized: Sequence[int],
    target: int,
    mod_base: int,
) -> list[int] | None:
    """Exact meet-in-the-middle with SOS subset sums (n <= MIRACLE_MAX_EXACT_N)."""
    n = len(normalized)
    if n == 0:
        return None

    # Fast path: single element hits target.
    for index, value in enumerate(normalized):
        if value % mod_base == target % mod_base:
            return [index]

    mid = n // 2
    left = [int(v) % mod_base for v in normalized[:mid]]
    right = [int(v) % mod_base for v in normalized[mid:]]
    nl, nr = len(left), len(right)

    left_size = 1 << nl
    left_sum = [0] * left_size
    for i, value in enumerate(left):
        bit = 1 << i
        for mask in range(bit):
            left_sum[mask | bit] = left_sum[mask] + value

    sum_to_mask: dict[int, int] = {}
    for mask, total in enumerate(left_sum):
        sum_to_mask.setdefault(total % mod_base, mask)

    right_size = 1 << nr
    right_sum = [0] * right_size
    for i, value in enumerate(right):
        bit = 1 << i
        for mask in range(bit):
            right_sum[mask | bit] = right_sum[mask] + value

    for right_mask, total in enumerate(right_sum):
        needed = (target - (total % mod_base)) % mod_base
        left_mask = sum_to_mask.get(needed)
        if left_mask is None:
            continue
        if left_mask == 0 and right_mask == 0:
            continue
        indices = [index for index in range(nl) if left_mask & (1 << index)]
        indices.extend(mid + index for index in range(nr) if right_mask & (1 << index))
        if indices:
            return indices
    return None


def find_miracle_subset(
    values: Sequence[int | str],
    target: int = MIRACLE_TARGET,
    mod_base: int = MIRACLE_MOD_BASE,
    *,
    max_exact_n: int = MIRACLE_MAX_EXACT_N,
    large_n_attempts: int = 8,  # deprecated: ignored, kept for call-site compat
    rng: random.Random | None = None,  # deprecated: ignored
) -> list[int] | None:
    """Find a non-empty subset whose sum ≡ target (mod mod_base).

    始终用 meet-in-the-middle（二分枚举子集和）对全部背包候选精确搜索，
    不再截断到编号最大的若干条，确保已有解不会因编号排序被漏掉。
    Returns original indices into ``values``, or None.
    """
    del max_exact_n, large_n_attempts, rng  # API compat only

    normalized = [int(value) % mod_base for value in values]
    if not normalized:
        return None
    return _mitm_exact_indices(normalized, target, mod_base)


def build_exhibition_entries(entries: Iterable[dict]) -> list[dict]:
    eligible = [
        entry
        for entry in entries
        if float(entry.get("score", 0)) >= EXHIBITION_MIN_SCORE
    ]
    eligible.sort(
        key=lambda item: (-float(item.get("score", 0)), str(item.get("id", "")))
    )
    return eligible[:EXHIBITION_LIMIT]
