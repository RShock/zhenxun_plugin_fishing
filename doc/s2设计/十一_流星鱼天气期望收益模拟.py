"""
十一 · 流星鱼天气期望收益模拟
================================

独立模拟 / 测试脚本（doc/s2设计/，与 S2 设计材料同目录）。

星空图（11-20）天气——仅此四种（见 weather_service.generate_starry_weather）：
  - 乱纪元 chaotic_era   ：无特殊效果，等同「无额外星空天气」（基准）
  - 太阳风 solar_wind    ：掉率 +2.5%，不改分数分布
  - 流星雨 meteor_shower ：2 候选取 raw_score 更高者
  - 恒纪元 hengjiyuan    ：ID 每位数字仅 {2,3,4,5,6,7,8}

注意：
  - 迷途风 / 迷风属于 1-10 图，星空图不生成，本脚本不包含。
  - 打分直接加载 core/starry_system.py，不另写规则。

打分（starry_system.score_starry_fish）
--------------------------------------
  扫番型累加 → raw_score（浮点）
  display_score = floor(raw + 0.5)
  奖池 get_reward_pool / 展示档 band()

本脚本默认假设「每天固定已掉落 10 条」看分数期望；
太阳风另附「含掉率」的每竿期望对照（因它只改掉率）。

运行
----
  python 十一_流星鱼天气期望收益模拟.py
  python 十一_流星鱼天气期望收益模拟.py --fast
  python 十一_流星鱼天气期望收益模拟.py --mc-only
"""

from __future__ import annotations

import importlib.util
import math
import random
import statistics
import sys
import types
from collections import Counter, namedtuple
from pathlib import Path
from typing import Iterable

# ═══════════════════════════════════════════════════════════════════════════════
# 0. 加载真实 starry_system（绕过插件 __init__ 对 nonebot 的依赖）
# ═══════════════════════════════════════════════════════════════════════════════

_PLUGIN_ROOT = Path(__file__).resolve().parents[2]  # zhenxun_plugin_fishing/
_CORE_DIR = _PLUGIN_ROOT / "core"
_STARRY_PATH = _CORE_DIR / "starry_system.py"


def _load_starry_system():
    pkg_name = "zhenxun_plugin_fishing"
    if pkg_name not in sys.modules:
        pkg = types.ModuleType(pkg_name)
        pkg.__path__ = [str(_PLUGIN_ROOT)]
        sys.modules[pkg_name] = pkg

    const_name = f"{pkg_name}.constants"
    if const_name not in sys.modules:
        const = types.ModuleType(const_name)
        const.STARRY_FISH_DROP_RATE = 0.05
        const.STARRY_FISH_ROD_BONUS_PER_LEVEL = 0.005
        const.STARRY_FISH_ROD_BONUS_THRESHOLD = 10
        const.STARRY_FISH_SOLAR_WIND_BONUS = 0.025
        sys.modules[const_name] = const
    else:
        const = sys.modules[const_name]

    core_name = f"{pkg_name}.core"
    if core_name not in sys.modules:
        core = types.ModuleType(core_name)
        core.__path__ = [str(_CORE_DIR)]
        sys.modules[core_name] = core

    mod_name = f"{pkg_name}.core.starry_system"
    if mod_name in sys.modules:
        return sys.modules[mod_name]

    spec = importlib.util.spec_from_file_location(mod_name, _STARRY_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 {_STARRY_PATH}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


starry = _load_starry_system()
score_starry_fish = starry.score_starry_fish
compare_starry_fish = starry.compare_starry_fish
generate_starry_fish_id = starry.generate_starry_fish_id
band = starry.band
get_reward_pool = starry.get_reward_pool
get_starry_fish_drop_rate = starry.get_starry_fish_drop_rate
REWARD_POOL_NAMES = starry.REWARD_POOL_NAMES
HENGJIYUAN_DIGITS = starry.HENGJIYUAN_DIGITS

# 与 constants / starry_system 对齐的掉率常数（仅用于「含掉率」对照表）
BASE_DROP = 0.05
SOLAR_WIND_BONUS = 0.025

# ═══════════════════════════════════════════════════════════════════════════════
# 1. 天气定义（仅星空四种）
# ═══════════════════════════════════════════════════════════════════════════════


WeatherSpec = namedtuple(
    "WeatherSpec",
    "key name meteor_shower hengjiyuan solar_wind note affects_score",
    defaults=(False, False, False, "", True),
)

# 顺序：基准 → 只改掉率 → 改分数的两种
WEATHERS = [
    WeatherSpec(
        "chaotic_era",
        "乱纪元",
        False,
        False,
        False,
        "无特殊效果（星空默认/基准）",
        True,
    ),
    WeatherSpec(
        "solar_wind",
        "太阳风",
        False,
        False,
        True,
        "掉率 +2.5%；分数分布与乱纪元相同",
        False,
    ),
    WeatherSpec(
        "meteor_shower",
        "流星雨",
        True,
        False,
        False,
        "2 候选取优（raw_score 优先，同分取更大 ID）",
        True,
    ),
    WeatherSpec(
        "hengjiyuan",
        "恒纪元",
        False,
        True,
        False,
        "数字仅 2–8（HENGJIYUAN_DIGITS）",
        True,
    ),
]


def roll_scored_fish(
    *,
    meteor_shower: bool = False,
    hengjiyuan: bool = False,
):
    """条件于已掉落：与 roll_starry_fish 相同的生成/取优，不掷掉率。"""
    candidates = [generate_starry_fish_id(hengjiyuan=hengjiyuan)]
    if meteor_shower:
        candidates.append(generate_starry_fish_id(hengjiyuan=hengjiyuan))
    best = candidates[0]
    for c in candidates[1:]:
        best = compare_starry_fish(best, c)
    return score_starry_fish(best)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 精确枚举 / 蒙特卡洛
# ═══════════════════════════════════════════════════════════════════════════════

FISH_PER_DAY = 10
DEFAULT_SINGLE_SAMPLES = 200_000
DEFAULT_DAY_SAMPLES = 50_000
SEED = 20260719


def exact_display_score_distribution(*, hengjiyuan: bool = False) -> dict[int, int]:
    counter: Counter[int] = Counter()
    if hengjiyuan:
        from itertools import product

        for digits in product(HENGJIYUAN_DIGITS, repeat=6):
            counter[score_starry_fish(int("".join(digits))).display_score] += 1
    else:
        for i in range(1_000_000):
            counter[score_starry_fish(i).display_score] += 1
    return dict(sorted(counter.items()))


def exact_expectations(*, hengjiyuan: bool = False) -> tuple[float, float, int]:
    total_raw = 0.0
    total_disp = 0.0
    n = 0
    if hengjiyuan:
        from itertools import product

        for digits in product(HENGJIYUAN_DIGITS, repeat=6):
            fish = score_starry_fish(int("".join(digits)))
            total_raw += fish.raw_score
            total_disp += fish.display_score
            n += 1
    else:
        for i in range(1_000_000):
            fish = score_starry_fish(i)
            total_raw += fish.raw_score
            total_disp += fish.display_score
            n += 1
    return total_raw / n, total_disp / n, n


def dist_to_probs(dist: dict[int, int]) -> dict[int, float]:
    total = sum(dist.values()) or 1
    return {k: v / total for k, v in sorted(dist.items())}


def pool_breakdown(score_probs: dict[int, float]) -> dict[str, float]:
    out = {k: 0.0 for k in ("none", "low", "middle", "high", "ultimate")}
    for score, p in score_probs.items():
        out[get_reward_pool(score)] += p
    return out


def band_breakdown(score_probs: dict[int, float]) -> dict[str, float]:
    order = ["普通", "小吉", "良品", "稀有", "珍品", "极品", "传说", "神话"]
    out = {name: 0.0 for name in order}
    for score, p in score_probs.items():
        out[band(score)] += p
    return out


class _SeededRandom:
    def __init__(self, seed: int):
        self.seed = seed
        self._state = None

    def __enter__(self):
        self._state = random.getstate()
        random.seed(self.seed)
        return self

    def __exit__(self, *args):
        random.setstate(self._state)


def monte_carlo_single(weather: WeatherSpec, n: int, seed: int) -> list[dict]:
    with _SeededRandom(seed):
        out: list[dict] = []
        for _ in range(n):
            fish = roll_scored_fish(
                meteor_shower=weather.meteor_shower,
                hengjiyuan=weather.hengjiyuan,
            )
            out.append(
                {
                    "raw": fish.raw_score,
                    "display": fish.display_score,
                    "pool": fish.reward_pool,
                    "band": band(fish.display_score),
                }
            )
        return out


def monte_carlo_daily_totals(
    weather: WeatherSpec,
    n_days: int,
    fish_per_day: int,
    seed: int,
) -> list[dict]:
    with _SeededRandom(seed):
        rows: list[dict] = []
        for _ in range(n_days):
            raw_sum = 0.0
            disp_sum = 0
            for _ in range(fish_per_day):
                fish = roll_scored_fish(
                    meteor_shower=weather.meteor_shower,
                    hengjiyuan=weather.hengjiyuan,
                )
                raw_sum += fish.raw_score
                disp_sum += fish.display_score
            rows.append({"raw": raw_sum, "display": disp_sum})
        return rows


def summarize_numeric(values: Iterable[float]) -> dict:
    arr = sorted(float(v) for v in values)
    n = len(arr)

    def pct(p: float) -> float:
        if n == 0:
            return 0.0
        k = min(n - 1, max(0, int(math.ceil(p / 100.0 * n) - 1)))
        return arr[k]

    return {
        "n": n,
        "mean": statistics.fmean(arr) if arr else 0.0,
        "stdev": statistics.pstdev(arr) if n > 1 else 0.0,
        "min": arr[0] if arr else 0.0,
        "p25": pct(25),
        "p50": pct(50),
        "p75": pct(75),
        "p90": pct(90),
        "p99": pct(99),
        "max": arr[-1] if arr else 0.0,
    }


def hist_int(values: Iterable[float]) -> dict[int, int]:
    return dict(sorted(Counter(int(round(v)) for v in values).items()))


def hist_to_rows(hist: dict[int, int], max_bins: int = 40) -> list[tuple[int, float, int]]:
    total = sum(hist.values()) or 1
    items = sorted(hist.items())
    if len(items) <= max_bins:
        return [(k, v / total, v) for k, v in items]
    lo, hi = items[0][0], items[-1][0]
    width = max(1, math.ceil((hi - lo + 1) / max_bins))
    buckets: dict[int, int] = {}
    for k, v in items:
        b = lo + ((k - lo) // width) * width
        buckets[b] = buckets.get(b, 0) + v
    return [(k, v / total, v) for k, v in sorted(buckets.items())]


def bar(p: float, width: int = 40) -> str:
    n = int(round(max(0.0, min(1.0, p)) * width))
    return "#" * n + "." * (width - n)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 自检
# ═══════════════════════════════════════════════════════════════════════════════


def self_check() -> None:
    s = score_starry_fish(444444)
    labels = {f.label for f in s.features}
    assert "6_same_run" in labels, labels
    assert s.raw_score >= 5.0
    assert s.display_score == int(math.floor(s.raw_score + 0.5))
    assert s.reward_pool == get_reward_pool(s.display_score)

    assert compare_starry_fish(444444, 102938) == 444444

    for _ in range(30):
        fid = generate_starry_fish_id(hengjiyuan=True)
        assert all(ch in HENGJIYUAN_DIGITS for ch in f"{fid:06d}")

    assert get_reward_pool(0) == "none"
    assert get_reward_pool(2) == "low"
    assert get_reward_pool(5) == "middle"
    assert get_reward_pool(10) == "high"
    assert get_reward_pool(11) == "ultimate"

    # 掉率：太阳风 = 基础 + 2.5%（竿 10 级时无竿加成）
    r0 = get_starry_fish_drop_rate(rod_level=10, solar_wind=False)
    r1 = get_starry_fish_drop_rate(rod_level=10, solar_wind=True)
    assert abs(r0 - BASE_DROP) < 1e-12
    assert abs(r1 - (BASE_DROP + SOLAR_WIND_BONUS)) < 1e-12

    # 天气集合必须只有这四种
    keys = {w.key for w in WEATHERS}
    assert keys == {"chaotic_era", "solar_wind", "meteor_shower", "hengjiyuan"}
    assert "lost_wind" not in keys and "迷风" not in {w.name for w in WEATHERS}

    print("[self-check] OK — starry_system 打分 + 四种星空天气")


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 输出
# ═══════════════════════════════════════════════════════════════════════════════


def print_header(title: str) -> None:
    line = "=" * 72
    print(f"\n{line}\n{title}\n{line}")


def _print_pools_and_bands(pools: dict[str, float], bands: dict[str, float]) -> None:
    print("  奖池概率 (get_reward_pool):")
    for key in ("none", "low", "middle", "high", "ultimate"):
        name = REWARD_POOL_NAMES.get(key, key)
        print(f"    {name:8s}  {pools[key]*100:7.3f}%  {bar(pools[key])}")
    print("  展示档位 band():")
    for name, p in bands.items():
        if p <= 0:
            continue
        print(f"    {name:4s}  {p*100:7.3f}%  {bar(p)}")


def print_single_exact(weather: WeatherSpec) -> dict:
    print_header(f"[{weather.name}] 单条鱼 · 精确分布（{weather.note}）")
    e_raw, e_disp, n = exact_expectations(hengjiyuan=weather.hengjiyuan)
    dist = exact_display_score_distribution(hengjiyuan=weather.hengjiyuan)
    probs = dist_to_probs(dist)
    pools = pool_breakdown(probs)
    bands = band_breakdown(probs)

    print(f"  样本空间: {n:,}")
    print(f"  E[raw_score]     = {e_raw:.6f}")
    print(f"  E[display_score] = {e_disp:.6f}")
    print(f"  display 范围     = {min(dist)} ~ {max(dist)}")
    _print_pools_and_bands(pools, bands)
    print("  display_score 直方图:")
    for score, p, cnt in hist_to_rows(dist):
        print(f"    {score:3d}  {p*100:6.3f}%  {bar(p, 30)}  n={cnt}")

    return {
        "e_raw": e_raw,
        "e_display": e_disp,
        "dist": dist,
        "pools": pools,
        "bands": bands,
    }


def print_single_mc(weather: WeatherSpec, samples: list[dict]) -> dict:
    print_header(
        f"[{weather.name}] 单条鱼 · 蒙特卡洛（n={len(samples):,}；{weather.note}）"
    )
    raws = [s["raw"] for s in samples]
    disps = [s["display"] for s in samples]
    sr = summarize_numeric(raws)
    sd = summarize_numeric(disps)
    hist = hist_int(disps)
    probs = {k: v / len(samples) for k, v in hist.items()}
    pools = pool_breakdown(probs)
    bands = band_breakdown(probs)

    print(f"  E[raw_score]     ≈ {sr['mean']:.6f}  (σ={sr['stdev']:.4f})")
    print(f"  E[display_score] ≈ {sd['mean']:.6f}  (σ={sd['stdev']:.4f})")
    print(
        f"  display 分位: min={sd['min']:.0f} p25={sd['p25']:.0f} "
        f"p50={sd['p50']:.0f} p75={sd['p75']:.0f} "
        f"p90={sd['p90']:.0f} p99={sd['p99']:.0f} max={sd['max']:.0f}"
    )
    _print_pools_and_bands(pools, bands)
    print("  display_score 直方图:")
    for score, p, cnt in hist_to_rows(hist):
        print(f"    {score:3d}  {p*100:6.3f}%  {bar(p, 30)}  n={cnt}")

    return {
        "e_raw": sr["mean"],
        "e_display": sd["mean"],
        "pools": pools,
        "bands": bands,
        "stats_display": sd,
    }


def print_daily_mc(
    weather: WeatherSpec,
    days: list[dict],
    fish_per_day: int,
    single_e_raw: float,
    single_e_disp: float,
) -> dict:
    print_header(
        f"[{weather.name}] 每天总分 · 蒙特卡洛"
        f"（{fish_per_day} 条/天 × {len(days):,} 天；{weather.note}）"
    )
    raws = [d["raw"] for d in days]
    disps = [d["display"] for d in days]
    sr = summarize_numeric(raws)
    sd = summarize_numeric(disps)
    hist = hist_int(disps)

    print(f"  E[日 raw 总分]     ≈ {sr['mean']:.6f}  (σ={sr['stdev']:.4f})")
    print(f"  E[日 display 总分] ≈ {sd['mean']:.6f}  (σ={sd['stdev']:.4f})")
    print(
        f"  理论 10×E[单条]: raw={10 * single_e_raw:.4f}  "
        f"display={10 * single_e_disp:.4f}"
    )
    print(
        f"  display 分位: min={sd['min']:.0f} p25={sd['p25']:.0f} "
        f"p50={sd['p50']:.0f} p75={sd['p75']:.0f} "
        f"p90={sd['p90']:.0f} p99={sd['p99']:.0f} max={sd['max']:.0f}"
    )
    print("  每日 display 总分直方图（压缩桶）:")
    for score, p, cnt in hist_to_rows(hist, max_bins=30):
        print(f"    >={score:<4d}  {p*100:6.3f}%  {bar(p, 30)}  n={cnt}")

    return {"e_raw": sr["mean"], "e_display": sd["mean"], "stats_display": sd}


def print_comparison(rows: list[dict], rod_level: int = 10) -> None:
    print_header("四种星空天气期望对比（条件于已掉落 10 条/天）")
    print(
        f"{'天气':<8} {'E[raw]':>10} {'E[display]':>12} "
        f"{'日raw':>10} {'日display':>10} {'相对乱纪元':>10}"
    )
    print("-" * 72)
    base = rows[0]["single_raw"]
    for r in rows:
        rel = r["single_raw"] / base if base else 0.0
        print(
            f"{r['name']:<8} {r['single_raw']:10.4f} {r['single_disp']:12.4f} "
            f"{r['day_raw']:10.3f} {r['day_disp']:10.3f} {rel:9.3f}x"
        )

    print_header(f"含掉率的每竿期望（竿 Lv.{rod_level}，非「固定 10 条」）")
    print("  公式: E[每竿 raw] = drop_rate × E[单条 raw | 已掉落]")
    print(
        f"{'天气':<8} {'掉率':>8} {'E[单条raw]':>12} "
        f"{'E[每竿raw]':>12} {'相对乱纪元':>10}"
    )
    print("-" * 60)
    base_per_cast = None
    for r in rows:
        drop = get_starry_fish_drop_rate(
            rod_level=rod_level, solar_wind=(r["key"] == "solar_wind")
        )
        per_cast = drop * r["single_raw"]
        if base_per_cast is None:
            base_per_cast = per_cast
        rel = per_cast / base_per_cast if base_per_cast else 0.0
        print(
            f"{r['name']:<8} {drop*100:7.2f}% {r['single_raw']:12.4f} "
            f"{per_cast:12.6f} {rel:9.3f}x"
        )

    print()
    print("说明（均来自代码，非臆造）：")
    print("  - 星空天气仅 chaotic_era / solar_wind / meteor_shower / hengjiyuan")
    print("  - 乱纪元 = 无特殊效果基准（weather_service）")
    print("  - 太阳风只加掉率，条件分数分布 = 乱纪元")
    print("  - 流星雨 / 恒纪元改分数分布（starry_system.roll_starry_fish）")
    print("  - 迷途风属于 1-10 图，星空图不生成")


# ═══════════════════════════════════════════════════════════════════════════════
# 5. main
# ═══════════════════════════════════════════════════════════════════════════════


def main(
    single_samples: int = DEFAULT_SINGLE_SAMPLES,
    day_samples: int = DEFAULT_DAY_SAMPLES,
    fish_per_day: int = FISH_PER_DAY,
    seed: int = SEED,
    skip_exact: bool = False,
) -> int:
    print("十一 · 流星鱼天气期望收益模拟")
    print(f"打分源: {_STARRY_PATH}")
    print("星空天气: 乱纪元 / 太阳风 / 流星雨 / 恒纪元（无迷风）")
    print(
        f"seed={seed}  single_samples={single_samples:,}  "
        f"day_samples={day_samples:,}  fish_per_day={fish_per_day}"
    )
    self_check()

    rng = random.Random(seed)
    summary: list[dict] = []

    # 乱纪元精确分布缓存，太阳风直接复用
    chaotic_cache: dict | None = None

    for weather in WEATHERS:
        if weather.key == "solar_wind" and chaotic_cache is not None:
            print_header(
                f"[{weather.name}] 单条鱼 · 与乱纪元相同（{weather.note}）"
            )
            print(
                f"  E[raw_score]     = {chaotic_cache['e_raw']:.6f}  （复用乱纪元）"
            )
            print(
                f"  E[display_score] = {chaotic_cache['e_display']:.6f}  （复用乱纪元）"
            )
            print("  （分数直方图略，与乱纪元一致；见上方乱纪元段）")
            single_raw = chaotic_cache["e_raw"]
            single_disp = chaotic_cache["e_display"]
            # 日总分也与乱纪元同分布：复用或单独 MC 验证
            days = monte_carlo_daily_totals(
                WEATHERS[0], day_samples, fish_per_day, rng.randint(0, 2**31 - 1)
            )
            day_info = print_daily_mc(
                weather, days, fish_per_day, single_raw, single_disp
            )
        elif weather.key in ("chaotic_era", "hengjiyuan") and not skip_exact:
            single_info = print_single_exact(weather)
            single_raw = single_info["e_raw"]
            single_disp = single_info["e_display"]
            if weather.key == "chaotic_era":
                chaotic_cache = single_info
            days = monte_carlo_daily_totals(
                weather, day_samples, fish_per_day, rng.randint(0, 2**31 - 1)
            )
            day_info = print_daily_mc(
                weather, days, fish_per_day, single_raw, single_disp
            )
        else:
            samples = monte_carlo_single(
                weather, single_samples, rng.randint(0, 2**31 - 1)
            )
            single_info = print_single_mc(weather, samples)
            single_raw = single_info["e_raw"]
            single_disp = single_info["e_display"]
            if weather.key == "chaotic_era":
                chaotic_cache = {
                    "e_raw": single_raw,
                    "e_display": single_disp,
                }
            days = monte_carlo_daily_totals(
                weather, day_samples, fish_per_day, rng.randint(0, 2**31 - 1)
            )
            day_info = print_daily_mc(
                weather, days, fish_per_day, single_raw, single_disp
            )

        summary.append(
            {
                "name": weather.name,
                "key": weather.key,
                "single_raw": single_raw,
                "single_disp": single_disp,
                "day_raw": day_info["e_raw"],
                "day_disp": day_info["e_display"],
            }
        )

    print_comparison(summary)
    print("\n完成。路径: doc/s2设计/十一_流星鱼天气期望收益模拟.py")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--fast" in args:
        raise SystemExit(main(single_samples=80_000, day_samples=20_000))
    if "--mc-only" in args:
        raise SystemExit(
            main(single_samples=100_000, day_samples=30_000, skip_exact=True)
        )
    raise SystemExit(main())
