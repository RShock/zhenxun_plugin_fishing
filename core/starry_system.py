"""Pure rules for the S2 starry fish system.

This module intentionally has no database dependency. Settlement, rewards and UI can
reuse these helpers without duplicating the six-digit scoring rules.
"""

from __future__ import annotations

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
        {"key": "cat_frame", "name": "猫猫框", "count": 1},
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
STAR_FRAMES_MAX = 10
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
    "rhythm": "周期节奏",
    "star_airplane": "星空飞机",
    "pairs": "对子",
    "full_house": "葫芦",
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
    ("rhythm", 4, "ABAB", 1.598599),
    ("rhythm", 6, "ABCABC", 3.142668),
    ("star_airplane", 6, "star_airplane", 1.899285),
    ("pairs", 2, "two_pair", 1.359121),
    ("pairs", 3, "three_pair", 3.091515),
    # 葫芦：任意 5 位窗口为 AAABB 或 AABBB；存在即计一次
    # 分值 = -log10(出现概率)，全量 3510/1e6 → 2.454693
    ("full_house", 5, "full_house", 2.454693),
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
        digits[start + i] - digits[start + i - 1] == diff
        for i in range(2, length)
    )


def _window_slide(digits: Sequence[int], start: int, length: int) -> bool:
    diffs = [digits[start + i] - digits[start + i - 1] for i in range(1, length)]
    return any(diff != 0 for diff in diffs) and (
        all(diff in (0, 1) for diff in diffs)
        or all(diff in (0, -1) for diff in diffs)
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
    if _window_same(digits, start, length):
        return False
    return all(
        digits[start + i] == digits[start + length - 1 - i]
        for i in range(length // 2)
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


def _star_airplane(digits: Sequence[int]) -> bool:
    return all(
        digits[i] == digits[i - 1] or digits[i] == digits[i + 1]
        for i in range(1, DIGITS - 1)
    )


def _exact_pair_runs(digits: Sequence[int]) -> list[tuple[int, int]]:
    """Return (start, end) of length-exactly-2 same-digit runs.

    A pair is a contiguous same-digit segment of length 2 only. Longer same
    runs (3+) belong to same_run and do not count as pairs.
    """
    runs: list[tuple[int, int]] = []
    index = 0
    while index < len(digits):
        end = index + 1
        while end < len(digits) and digits[end] == digits[index]:
            end += 1
        if end - index == 2:
            runs.append((index, end))
        index = end
    return runs


def _window_full_house(digits: Sequence[int], start: int) -> bool:
    """5-digit window is AAABB or AABBB: exactly two same-digit runs of lengths 3+2 or 2+3."""
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
                features.append(
                    _feature(
                        f"{length}_palindrome",
                        "palindrome",
                        span,
                        "同号回文已被同号吸收",
                    )
                )

    for start in range(DIGITS - 4 + 1):
        if _motif_abab(digits, start):
            features.append(_feature("ABAB", "rhythm", f"{start + 1}-{start + 4}"))
    if _motif_abcabc(digits):
        features.append(_feature("ABCABC", "rhythm", "1-6"))

    pair_runs = _exact_pair_runs(digits)
    pair_count = len(pair_runs)
    if pair_count >= 2:
        pair_span = f"{pair_runs[0][0] + 1}-{pair_runs[-1][1]}"
        # 同家族最大匹配：三对吸收两对，不重复计分
        if pair_count >= 3:
            features.append(
                _feature(
                    "three_pair",
                    "pairs",
                    pair_span,
                    "三段恰好长度为2的同号连段",
                )
            )
        else:
            features.append(
                _feature(
                    "two_pair",
                    "pairs",
                    pair_span,
                    "两段恰好长度为2的同号连段",
                )
            )

    full_house_spans = _full_house_spans(digits)
    if full_house_spans:
        # 存在即计一次（不因两个 5 位窗口同时命中而叠分）
        span = f"{full_house_spans[0][0] + 1}-{full_house_spans[-1][1]}"
        features.append(
            _feature("full_house", "full_house", span, "5位窗口为AAABB或AABBB")
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
        "ABAB": "ABAB",
        "ABCABC": "ABCABC",
        "star_airplane": "星空飞机",
        "two_pair": "两对",
        "three_pair": "三对",
        "full_house": "葫芦",
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
) -> float:
    """计算星空鱼（流星鱼）掉落率。

    公式（绝对加值，互不乘算）：
    - 基础 5%
    - 鱼竿等级每超过 10 级 1 级：+0.5%
    - 太阳风：恒定 +2.5%
    """
    rod_bonus_levels = max(0, int(rod_level) - STARRY_FISH_ROD_BONUS_THRESHOLD)
    rod_bonus = rod_bonus_levels * STARRY_FISH_ROD_BONUS_PER_LEVEL
    solar_bonus = STARRY_FISH_SOLAR_WIND_BONUS if solar_wind else 0.0
    return min(1.0, STARRY_FISH_DROP_RATE + rod_bonus + solar_bonus)


def roll_starry_fish(
    *,
    rod_level: int = 0,
    solar_wind: bool = False,
    meteor_shower: bool = False,
    hengjiyuan: bool = False,
    lucky_double: bool = False,
) -> StarryFish | None:
    drop_rate = get_starry_fish_drop_rate(rod_level=rod_level, solar_wind=solar_wind)
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
        indices.extend(
            mid + index for index in range(nr) if right_mask & (1 << index)
        )
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

    始终用 meet-in-the-middle（二分枚举子集和）精确搜索。
    候选最多取 ``max_exact_n``（默认 26）个**编号最大**的鱼；
    超过此数量时直接丢弃较小编号，接受极低的漏匹配概率以保速度。
    Returns original indices into ``values``, or None.
    """
    del large_n_attempts, rng  # API compat only

    normalized = [int(value) % mod_base for value in values]
    n = len(normalized)
    if n == 0:
        return None

    # 只在最大的 max_exact_n 个编号上做 MITM
    if n <= max_exact_n:
        candidate_idxs = list(range(n))
    else:
        # 编号（mod 后）从大到小；同分用原下标稳定排序
        candidate_idxs = sorted(
            range(n),
            key=lambda i: (normalized[i], i),
            reverse=True,
        )[:max_exact_n]
        candidate_idxs.sort()  # MITM 内部用相对下标，再映射回原下标

    sub = [normalized[i] for i in candidate_idxs]
    local = _mitm_exact_indices(sub, target, mod_base)
    if not local:
        return None
    return sorted(candidate_idxs[i] for i in local)


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
