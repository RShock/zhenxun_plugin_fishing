import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOTAL = 1_000_000
DIGITS = 6
TOP_N = 100

FAMILIES = [
    "same_run",
    "step_high",
    "slide",
    "pure_snake",
    "snake",
    "palindrome",
    "range",
    "rhythm",
    "star_airplane",
    "pairs",
    "full_house",
]

CN_FAMILY = {
    "same_run": "同号连段",
    "step_high": "纯正滑梯/步高",
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

NOTE = {
    "same_run": "不同具体数字不分开：000、666、999 都属于同一个长度番。",
    "step_high": "相邻差恒为 +1 或 -1，例如 1234 / 9876；作为纯正滑梯替代普通滑梯计分。",
    "slide": "单调，允许相等，每步只能 0 或 1，例如 998877。",
    "pure_snake": "每步必须相差 1，且方向至少转折一次。",
    "snake": "每步最多相差 1，允许相等，且方向至少转折一次。",
    "palindrome": "回文不含全同号，全同号已被同号连段吸收。",
    "range": "全小/全大只在完整 6 位成立时计分。",
    "rhythm": "周期结构独立计分，保留 ABAB、ABCABC。",
    "star_airplane": "6 位版星空飞机：第 2-5 位每一位都处于至少 2 连块中。",
    "pairs": "对子统计恰好长度为 2 的同号连段；3 位及以上同号连段不计对。同家族最大匹配：三对吸收两对。",
    "full_house": "葫芦：任意 5 位窗口为 AAABB 或 AABBB（恰好两段同号，长度 3+2 或 2+3）；存在即计一次。",
}


def make_features():
    features = []
    for fam in ["same_run", "step_high", "slide", "pure_snake", "snake", "palindrome"]:
        for length in range(3, DIGITS + 1):
            features.append({"family": fam, "length": length, "label": f"{length}_{fam}"})
    features.append({"family": "range", "length": DIGITS, "label": "6_all_small_0_4"})
    features.append({"family": "range", "length": DIGITS, "label": "6_all_big_5_9"})
    features.append({"family": "rhythm", "length": 4, "label": "ABAB"})
    features.append({"family": "rhythm", "length": 6, "label": "ABCABC"})
    features.append({"family": "star_airplane", "length": DIGITS, "label": "star_airplane"})
    features.append({"family": "pairs", "length": 2, "label": "two_pair"})
    features.append({"family": "pairs", "length": 3, "label": "three_pair"})
    features.append({"family": "full_house", "length": 5, "label": "full_house"})
    return features

FEATURES = make_features()
FEATURE_BY_LABEL = {f["label"]: i for i, f in enumerate(FEATURES)}


def fid(family, length):
    return FEATURE_BY_LABEL[f"{length}_{family}"]


def digits_of(n):
    return [int(c) for c in f"{n:06d}"]


def digits_from_text(text):
    if not text.isdigit() or len(text) > DIGITS:
        raise ValueError("ID must be 0..999999")
    return [int(c) for c in text.zfill(DIGITS)]


def sign(x):
    return (x > 0) - (x < 0)


def window_same(d, s, length):
    return all(d[s + i] == d[s] for i in range(length))


def window_step(d, s, length):
    diff = d[s + 1] - d[s]
    return diff in (1, -1) and all(d[s + i] - d[s + i - 1] == diff for i in range(2, length))


def window_slide(d, s, length):
    diffs = [d[s + i] - d[s + i - 1] for i in range(1, length)]
    return any(x != 0 for x in diffs) and (all(x in (0, 1) for x in diffs) or all(x in (0, -1) for x in diffs))


def window_snake(d, s, length, pure):
    prev = 0
    moved = False
    turned = False
    for i in range(1, length):
        diff = d[s + i] - d[s + i - 1]
        if pure:
            if diff not in (1, -1):
                return False
        elif diff < -1 or diff > 1:
            return False
        sg = sign(diff)
        if sg:
            moved = True
            if prev and sg != prev:
                turned = True
            prev = sg
    return moved and turned


def window_pal(d, s, length):
    if window_same(d, s, length):
        return False
    return all(d[s + i] == d[s + length - 1 - i] for i in range(length // 2))


def all_small(d):
    return all(0 <= x <= 4 for x in d)


def all_big(d):
    return all(5 <= x <= 9 for x in d)


def motif_abab(d, s):
    return d[s] == d[s + 2] and d[s + 1] == d[s + 3] and d[s] != d[s + 1]


def motif_abcabc(d):
    a, b, c = d[0], d[1], d[2]
    return a == d[3] and b == d[4] and c == d[5] and len({a, b, c}) == 3


def star_airplane(d):
    return all(d[i] == d[i - 1] or d[i] == d[i + 1] for i in range(1, DIGITS - 1))


def exact_pair_runs(d):
    """Return (start, end) spans of length-exactly-2 same-digit runs."""
    runs = []
    i = 0
    n = len(d)
    while i < n:
        j = i + 1
        while j < n and d[j] == d[i]:
            j += 1
        if j - i == 2:
            runs.append((i, j))
        i = j
    return runs


def window_full_house(d, s):
    """5-digit window is AAABB or AABBB."""
    w = d[s : s + 5]
    if len(w) < 5:
        return False
    lengths = []
    i = 0
    while i < 5:
        j = i + 1
        while j < 5 and w[j] == w[i]:
            j += 1
        lengths.append(j - i)
        i = j
    return lengths == [3, 2] or lengths == [2, 3]


def full_house_spans(d):
    return [(s, s + 5) for s in range(DIGITS - 5 + 1) if window_full_house(d, s)]


def contained_in_larger(ok, s, length):
    for bigger in range(length + 1, DIGITS + 1):
        for bs in range(0, DIGITS - bigger + 1):
            if bs <= s and s + length <= bs + bigger and ok.get((bs, bigger), False):
                return True
    return False


def build_ok(d):
    return {
        "same_run": {(s, l): window_same(d, s, l) for l in range(3, DIGITS + 1) for s in range(DIGITS - l + 1)},
        "step_high": {(s, l): window_step(d, s, l) for l in range(3, DIGITS + 1) for s in range(DIGITS - l + 1)},
        "slide": {(s, l): window_slide(d, s, l) for l in range(3, DIGITS + 1) for s in range(DIGITS - l + 1)},
        "pure_snake": {(s, l): window_snake(d, s, l, True) for l in range(3, DIGITS + 1) for s in range(DIGITS - l + 1)},
        "snake": {(s, l): window_snake(d, s, l, False) for l in range(3, DIGITS + 1) for s in range(DIGITS - l + 1)},
        "palindrome": {(s, l): window_pal(d, s, l) for l in range(3, DIGITS + 1) for s in range(DIGITS - l + 1)},
    }


def raw_and_max_features(d):
    ok = build_ok(d)
    present = set()
    raw = defaultdict(int)
    maximal = defaultdict(int)

    for family in ["same_run", "step_high", "slide", "pure_snake", "snake", "palindrome"]:
        for length in range(3, DIGITS + 1):
            feature_id = fid(family, length)
            for s in range(DIGITS - length + 1):
                if ok[family][(s, length)]:
                    present.add(feature_id)
                    raw[feature_id] += 1
                    if not contained_in_larger(ok[family], s, length):
                        maximal[feature_id] += 1

    if all_small(d):
        i = FEATURE_BY_LABEL["6_all_small_0_4"]
        present.add(i); raw[i] += 1; maximal[i] += 1
    if all_big(d):
        i = FEATURE_BY_LABEL["6_all_big_5_9"]
        present.add(i); raw[i] += 1; maximal[i] += 1
    for s in range(DIGITS - 4 + 1):
        if motif_abab(d, s):
            i = FEATURE_BY_LABEL["ABAB"]
            present.add(i); raw[i] += 1; maximal[i] += 1
    if motif_abcabc(d):
        i = FEATURE_BY_LABEL["ABCABC"]
        present.add(i); raw[i] += 1; maximal[i] += 1
    if star_airplane(d):
        i = FEATURE_BY_LABEL["star_airplane"]
        present.add(i); raw[i] += 1; maximal[i] += 1

    pair_runs = exact_pair_runs(d)
    pair_count = len(pair_runs)
    if pair_count >= 3:
        i = FEATURE_BY_LABEL["three_pair"]
        present.add(i); raw[i] += 1; maximal[i] += 1
    elif pair_count == 2:
        i = FEATURE_BY_LABEL["two_pair"]
        present.add(i); raw[i] += 1; maximal[i] += 1

    fh_spans = full_house_spans(d)
    if fh_spans:
        i = FEATURE_BY_LABEL["full_house"]
        present.add(i)
        raw[i] += len(fh_spans)
        maximal[i] += 1

    return present, raw, maximal, ok


def score_digits(d, weights, explain=False):
    _, _, _, ok = raw_and_max_features(d)
    items = []

    def add(label, family, span, note=""):
        score = weights[FEATURE_BY_LABEL[label]]
        items.append({"label": label, "family": family, "span": span, "score": score, "note": note})

    if all_small(d):
        add("6_all_small_0_4", "range", "1-6")
    if all_big(d):
        add("6_all_big_5_9", "range", "1-6")
    if star_airplane(d):
        add("star_airplane", "star_airplane", "1-6", "第2-5位均属于至少2连块")

    for length in range(3, DIGITS + 1):
        for s in range(DIGITS - length + 1):
            span = f"{s + 1}-{s + length}"
            if ok["same_run"][(s, length)] and not contained_in_larger(ok["same_run"], s, length):
                add(f"{length}_same_run", "same_run", span)
            if ok["slide"][(s, length)] and not contained_in_larger(ok["slide"], s, length):
                if ok["step_high"][(s, length)]:
                    add(f"{length}_step_high", "step_high", span, "纯正替代普通滑梯计分")
                else:
                    add(f"{length}_slide", "slide", span)
            if ok["snake"][(s, length)] and not contained_in_larger(ok["snake"], s, length):
                if ok["pure_snake"][(s, length)]:
                    add(f"{length}_pure_snake", "pure_snake", span, "纯正替代普通贪吃蛇计分")
                else:
                    add(f"{length}_snake", "snake", span)
            if ok["palindrome"][(s, length)] and not contained_in_larger(ok["palindrome"], s, length):
                add(f"{length}_palindrome", "palindrome", span, "同号回文已被同号吸收")

    for s in range(DIGITS - 4 + 1):
        if motif_abab(d, s):
            add("ABAB", "rhythm", f"{s + 1}-{s + 4}")
    if motif_abcabc(d):
        add("ABCABC", "rhythm", "1-6")

    pair_runs = exact_pair_runs(d)
    pair_count = len(pair_runs)
    if pair_count >= 2:
        pair_span = f"{pair_runs[0][0] + 1}-{pair_runs[-1][1]}"
        if pair_count >= 3:
            add("three_pair", "pairs", pair_span, "三段恰好长度为2的同号连段")
        else:
            add("two_pair", "pairs", pair_span, "两段恰好长度为2的同号连段")

    fh_spans = full_house_spans(d)
    if fh_spans:
        span = f"{fh_spans[0][0] + 1}-{fh_spans[-1][1]}"
        add("full_house", "full_house", span, "5位窗口为AAABB或AABBB")

    total = sum(x["score"] for x in items)
    if explain:
        return total, sorted(items, key=lambda x: (-x["score"], x["span"], x["label"]))
    return total


def label_cn(label):
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
    length, rest = label.split("_", 1)
    suffix = {
        "same_run": "同号连段",
        "step_high": "纯正滑梯/步高",
        "slide": "滑梯",
        "pure_snake": "纯正贪吃蛇",
        "snake": "贪吃蛇",
        "palindrome": "回文",
    }[rest]
    return f"{length}位{suffix}"


def band(score):
    if score == 0:
        return "普通"
    if score <= 2:
        return "小吉"
    if score <= 4:
        return "良品"
    if score <= 6:
        return "稀有"
    if score <= 8:
        return "珍品"
    if score <= 10:
        return "极品"
    if score <= 12:
        return "传说"
    return "神话"


def run_full():
    presence = [0] * len(FEATURES)
    raw_counts = [0] * len(FEATURES)
    max_counts = [0] * len(FEATURES)

    for n in range(TOTAL):
        d = digits_of(n)
        present, raw, maximal, _ = raw_and_max_features(d)
        for i in present:
            presence[i] += 1
        for i, c in raw.items():
            raw_counts[i] += c
        for i, c in maximal.items():
            max_counts[i] += c

    weights = []
    with (ROOT / "six_fan_stats.tsv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["id", "family", "length", "label", "presence_count", "raw_occurrence_count", "maximal_occurrence_count", "probability", "rarity_points"])
        for i, feat in enumerate(FEATURES):
            p = presence[i] / TOTAL
            points = -math.log10(p) if p else 0.0
            weights.append(points)
            writer.writerow([i, feat["family"], feat["length"], feat["label"], presence[i], raw_counts[i], max_counts[i], f"{p:.12f}", f"{points:.6f}"])

    rounded_hist = defaultdict(int)
    tenth_hist = defaultdict(int)
    top = []
    score_sum = 0.0
    score_sq_sum = 0.0
    max_score = 0.0

    for n in range(TOTAL):
        d = digits_of(n)
        score = score_digits(d, weights)
        score_sum += score
        score_sq_sum += score * score
        max_score = max(max_score, score)
        rounded_hist[int(math.floor(score + 0.5))] += 1
        tenth_hist[int(math.floor(score * 10 + 1e-9))] += 1
        top.append((score, n))

    top.sort(key=lambda x: (-x[0], x[1]))
    top = top[:TOP_N]

    with (ROOT / "six_rounded_score_distribution.tsv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["rounded_score", "count", "probability"])
        for score in sorted(rounded_hist):
            count = rounded_hist[score]
            writer.writerow([score, count, f"{count / TOTAL:.12f}"])

    with (ROOT / "six_score_distribution.tsv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["score_floor", "score_ceiling", "count", "probability"])
        for bin_id in sorted(tenth_hist):
            count = tenth_hist[bin_id]
            writer.writerow([f"{bin_id / 10:.1f}", f"{(bin_id + 1) / 10:.1f}", count, f"{count / TOTAL:.12f}"])

    with (ROOT / "six_top_scores.tsv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["rank", "id", "score", "rounded_score"])
        for rank, (score, n) in enumerate(top, 1):
            writer.writerow([rank, f"{n:06d}", f"{score:.6f}", int(math.floor(score + 0.5))])

    mean = score_sum / TOTAL
    var = score_sq_sum / TOTAL - mean * mean
    with (ROOT / "six_score_summary.txt").open("w", encoding="utf-8") as f:
        f.write(f"total={TOTAL}\n")
        f.write(f"mean_score={mean:.9f}\n")
        f.write(f"stddev_score={math.sqrt(max(var, 0.0)):.9f}\n")
        f.write(f"max_score={max_score:.9f}\n")
        f.write(f"top_id={top[0][1]:06d}\n")

    write_report()


def load_fans():
    with (ROOT / "six_fan_stats.tsv").open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def load_rounded():
    with (ROOT / "six_rounded_score_distribution.tsv").open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def write_report():
    fans = load_fans()
    rounded = load_rounded()
    with (ROOT / "six_top_scores.tsv").open("r", encoding="utf-8", newline="") as f:
        top = list(csv.DictReader(f, delimiter="\t"))[:30]
    summary = {}
    for line in (ROOT / "six_score_summary.txt").read_text(encoding="utf-8").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            summary[k] = v

    total = sum(int(r["count"]) for r in rounded)
    cumulative = 0
    lines = []
    lines.append("# 6位幸运 ID 概率、番种与整数分分布")
    lines.append("")
    lines.append("本版将号码空间改为 `000000` 到 `999999`，共 10^6 个 ID。规则沿用 9 位 v2 的最大番种设计，但全小/全大和星空飞机改为 6 位语境。")
    lines.append("")
    lines.append("## 设计口径")
    lines.append("")
    lines.append("1. 番种分值为 `-log10(番种出现概率)`。")
    lines.append("2. 同家族取最大匹配，小番被大番包含时不重复计主分。")
    lines.append("3. 同号吸收同号回文。")
    lines.append("4. 全小/全大只在完整 6 位成立：全小为 0-4，全大为 5-9。")
    lines.append("5. 6 位星空飞机：第 2 到第 5 位每一位都必须和左邻或右邻相同。")
    lines.append("6. 对子：统计恰好长度为 2 的同号连段；两对 / 三对同家族，三对吸收两对。")
    lines.append("7. 葫芦：任意 5 位窗口为 AAABB 或 AABBB；存在即计一次，不因双窗口叠分。")
    lines.append("8. 游戏展示分为原始总分四舍五入后的整数分。")
    lines.append("")
    lines.append("## 全量摘要")
    lines.append("")
    lines.append(f"- 总号码数：{int(summary['total']):,}")
    lines.append(f"- 原始分平均值：{float(summary['mean_score']):.6f}")
    lines.append(f"- 原始分标准差：{float(summary['stddev_score']):.6f}")
    lines.append(f"- 原始最高分：{float(summary['max_score']):.6f}")
    lines.append(f"- 最高分代表 ID：`{summary['top_id']}`")
    lines.append("")
    lines.append("## 整数分精确分布")
    lines.append("")
    lines.append("| 展示分 | 建议段位 | 数量 | 概率 | 至少该分数量 | 至少该分概率 |")
    lines.append("|---:|---|---:|---:|---:|---:|")
    for r in rounded:
        score = int(r["rounded_score"])
        count = int(r["count"])
        cumulative += count
        ge_count = total - cumulative + count
        lines.append(f"| {score} | {band(score)} | {count:,} | {count / total:.12f} | {ge_count:,} | {ge_count / total:.12f} |")
    lines.append("")
    lines.append("## 番种分值与出现概率")
    lines.append("")
    lines.append("| 番种 | 家族 | 长度 | 命中号码数 | 出现概率 | 番种分值 |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for r in sorted(fans, key=lambda x: float(x["rarity_points"]), reverse=True):
        lines.append(f"| {label_cn(r['label'])} | {CN_FAMILY[r['family']]} | {r['length']} | {int(r['presence_count']):,} | {float(r['probability']):.12f} | {float(r['rarity_points']):.6f} |")
    lines.append("")
    lines.append("## 按家族拆分")
    for family in FAMILIES:
        rows = [r for r in fans if r["family"] == family]
        if not rows:
            continue
        lines.append("")
        lines.append(f"### {CN_FAMILY[family]}")
        lines.append("")
        lines.append(NOTE[family])
        lines.append("")
        lines.append("| 番种 | 概率 | 分值 |")
        lines.append("|---|---:|---:|")
        for r in sorted(rows, key=lambda x: (int(x["length"]), x["label"])):
            lines.append(f"| {label_cn(r['label'])} | {float(r['probability']):.12f} | {float(r['rarity_points']):.6f} |")
    lines.append("")
    lines.append("## Top 30")
    lines.append("")
    lines.append("| 排名 | ID | 原始分 | 展示分 |")
    lines.append("|---:|---|---:|---:|")
    for r in top:
        lines.append(f"| {r['rank']} | `{r['id']}` | {float(r['score']):.6f} | {r['rounded_score']} |")
    (ROOT / "six_digit_game_design_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def explain_id(text):
    fan_rows = load_fans()
    weights = [0.0] * len(FEATURES)
    for r in fan_rows:
        weights[int(r["id"])] = float(r["rarity_points"])
    d = digits_from_text(text)
    total, items = score_digits(d, weights, explain=True)
    print(f"ID\t{''.join(map(str, d))}")
    print(f"TOTAL\t{total:.6f}\tROUNDED\t{int(math.floor(total + 0.5))}")
    print("family\tpattern\tspan\tscore\tnote")
    if not items:
        print("-\t无显著最大番种\t-\t0.000000\t")
    for item in items:
        print(f"{CN_FAMILY[item['family']]}\t{label_cn(item['label'])}\t{item['span']}\t{item['score']:.6f}\t{item['note']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="run full 6-digit enumeration")
    parser.add_argument("--report", action="store_true", help="regenerate report from existing TSV files")
    parser.add_argument("--id", help="explain a single 6-digit id")
    args = parser.parse_args()
    if args.full:
        run_full()
    elif args.report:
        write_report()
    elif args.id:
        explain_id(args.id)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
