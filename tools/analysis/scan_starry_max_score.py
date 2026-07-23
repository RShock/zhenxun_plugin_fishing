"""Scan all 6-digit starry fish IDs and report max / top scores.

Usage (from plugin root):
  python tools/analysis/scan_starry_max_score.py
  python tools/analysis/scan_starry_max_score.py --start 0 --end 100000
  python tools/analysis/scan_starry_max_score.py --top 15 --show-features
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PLUGIN_ROOT.parents[2]
CI_RUNTIME = PLUGIN_ROOT / "ci" / "runtime"
CI_DIR = PLUGIN_ROOT / "ci"

for path in (CI_RUNTIME, CI_DIR, PLUGIN_ROOT, REPO_ROOT):
    path_s = str(path)
    if path_s not in sys.path:
        sys.path.insert(0, path_s)

try:
    from support.nonebot_stub import install_lightweight_nonebot_stubs

    install_lightweight_nonebot_stubs()
except Exception:
    # Running inside a fully initialized bot environment.
    pass

from zhenxun.plugins.zhenxun_plugin_fishing.core.starry_system import (  # noqa: E402
    label_cn,
    score_starry_fish,
)


def _scan(start: int, end: int, progress_every: int) -> dict:
    best_raw = -1.0
    best_display = -1
    best_ids: list[int] = []
    first_by_raw: dict[float, int] = {}

    for value in range(start, end):
        scored = score_starry_fish(value)
        raw = scored.raw_score
        if raw > best_raw + 1e-12:
            best_raw = raw
            best_display = scored.display_score
            best_ids = [value]
        elif abs(raw - best_raw) <= 1e-12:
            best_ids.append(value)

        key = round(raw, 8)
        if key not in first_by_raw:
            first_by_raw[key] = value

        if progress_every > 0 and value % progress_every == 0:
            print(
                f"progress {value} best_raw={best_raw:.6f} display={best_display}",
                flush=True,
            )

    return {
        "start": start,
        "end": end,
        "best_raw": best_raw,
        "best_display": best_display,
        "best_ids": best_ids,
        "first_by_raw": first_by_raw,
    }


def _print_report(result: dict, top_n: int, show_features: bool) -> None:
    best_ids = result["best_ids"]
    print("=== MAX ===")
    print(f"range: {result['start']:06d} .. {result['end'] - 1:06d}")
    print(f"max_raw: {result['best_raw']:.6f}")
    print(f"max_display: {result['best_display']}")
    print(f"count_at_max: {len(best_ids)}")
    shown = ", ".join(f"{i:06d}" for i in best_ids[:40])
    if len(best_ids) > 40:
        shown += f" ...(+{len(best_ids) - 40})"
    print("ids_at_max: " + shown)

    if best_ids:
        sample = score_starry_fish(best_ids[0])
        print(f"sample_pool: {sample.reward_pool}")
        if show_features:
            feats = ", ".join(
                f"{label_cn(f.label)}({f.span}:{f.score:.3f})" for f in sample.features
            )
            print(f"sample_features: {feats}")

    print(f"=== TOP {top_n} distinct raw ===")
    ordered = sorted(result["first_by_raw"].items(), reverse=True)[:top_n]
    for raw, value in ordered:
        scored = score_starry_fish(value)
        line = (
            f"{value:06d} raw={scored.raw_score:.6f} "
            f"display={scored.display_score} pool={scored.reward_pool}"
        )
        if show_features:
            feats = ", ".join(
                f"{label_cn(f.label)}({f.span})" for f in scored.features
            )
            line += f" | {feats}"
        print(line)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan starry fish score ceiling")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=1_000_000, help="exclusive")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--show-features", action="store_true")
    parser.add_argument("--progress-every", type=int, default=200_000)
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="optional path to write machine-readable summary",
    )
    args = parser.parse_args(argv)

    if not (0 <= args.start < args.end <= 1_000_000):
        raise SystemExit("require 0 <= start < end <= 1000000")

    result = _scan(args.start, args.end, args.progress_every)
    _print_report(result, args.top, args.show_features)

    if args.json_out is not None:
        payload = {
            "start": result["start"],
            "end": result["end"],
            "best_raw": result["best_raw"],
            "best_display": result["best_display"],
            "best_ids": [f"{i:06d}" for i in result["best_ids"]],
            "top_raw": [
                {
                    "raw": raw,
                    "id": f"{value:06d}",
                    "display": score_starry_fish(value).display_score,
                }
                for raw, value in sorted(
                    result["first_by_raw"].items(), reverse=True
                )[: args.top]
            ],
        }
        args.json_out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
