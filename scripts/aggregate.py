#!/usr/bin/env python3
"""
判定結果 (results/judgments/coverage/*.json, extras/*.json) を集計し、
results/summary.csv と results/summary.json を出力する。
"""

import csv
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
COV_DIR = RESULTS / "judgments" / "coverage"
EXT_DIR = RESULTS / "judgments" / "extras"


def collect():
    """各 (length, format, trial) のメトリクスを集める。"""
    rows = []
    for cov_file in sorted(COV_DIR.glob("*.json")):
        # filename: 50_md_trial1.json
        stem = cov_file.stem
        parts = stem.split("_")
        if len(parts) < 3:
            continue
        length = int(parts[0])
        fmt = parts[1]
        trial = int(parts[2].replace("trial", ""))

        cov = json.loads(cov_file.read_text(encoding="utf-8"))
        meta = cov.get("_meta", {})
        covered = meta.get("covered_count", len(cov.get("covered_ids", [])))
        total = meta.get("checklist_total")

        ext_file = EXT_DIR / cov_file.name
        if ext_file.exists():
            ext = json.loads(ext_file.read_text(encoding="utf-8"))
            ext_meta = ext.get("_meta", {})
            faithful = ext_meta.get("faithful_count", len(ext.get("faithful_extras", [])))
            hallu = ext_meta.get("hallucination_count", len(ext.get("hallucinations", [])))
        else:
            faithful = None
            hallu = None

        coverage_rate = covered / total if total else None
        if hallu is not None and (covered + faithful + hallu) > 0:
            hallucination_rate = hallu / (covered + faithful + hallu)
        else:
            hallucination_rate = None

        rows.append({
            "length": length,
            "format": fmt,
            "trial": trial,
            "covered": covered,
            "checklist_total": total,
            "coverage_rate": coverage_rate,
            "faithful_extras": faithful,
            "hallucinations": hallu,
            "hallucination_rate": hallucination_rate,
            "total_signal": (covered + faithful) if faithful is not None else None,
        })
    return rows


def summarize(rows):
    """(length, format) ごとに平均・標準偏差を計算する。"""
    groups = {}
    for r in rows:
        key = (r["length"], r["format"])
        groups.setdefault(key, []).append(r)

    summary = []
    for (length, fmt), group_rows in sorted(groups.items()):
        def collect_metric(name):
            vals = [r[name] for r in group_rows if r.get(name) is not None]
            return vals

        cov_rates = collect_metric("coverage_rate")
        hallu_rates = collect_metric("hallucination_rate")
        faithfuls = collect_metric("faithful_extras")
        signals = collect_metric("total_signal")

        def stats(vals):
            if not vals:
                return {"mean": None, "sd": None, "n": 0}
            return {
                "mean": statistics.mean(vals),
                "sd": statistics.pstdev(vals) if len(vals) > 1 else 0.0,
                "n": len(vals),
            }

        summary.append({
            "length": length,
            "format": fmt,
            "trials": len(group_rows),
            "coverage_rate": stats(cov_rates),
            "hallucination_rate": stats(hallu_rates),
            "faithful_extras": stats(faithfuls),
            "total_signal": stats(signals),
        })
    return summary


def main():
    rows = collect()
    summary = summarize(rows)

    # CSV (詳細行レベル)
    csv_path = RESULTS / "summary.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "length", "format", "trial", "covered", "checklist_total",
            "coverage_rate", "faithful_extras", "hallucinations",
            "hallucination_rate", "total_signal",
        ])
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"Wrote {len(rows)} detail rows → {csv_path}")

    # JSON (集計レベル)
    json_path = RESULTS / "summary.json"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(summary)} summary rows → {json_path}")

    # 標準出力に整形表示
    print("\n=== Coverage rate (mean ± SD) ===")
    print(f"{'len':>5} {'fmt':>5} {'cov':>10} {'hallu':>10} {'faithful':>9} {'n':>3}")
    for s in summary:
        cov = s["coverage_rate"]
        hallu = s["hallucination_rate"]
        faith = s["faithful_extras"]
        cov_str = f"{cov['mean']:.3f}±{cov['sd']:.3f}" if cov["mean"] is not None else "  -    "
        hallu_str = f"{hallu['mean']:.3f}±{hallu['sd']:.3f}" if hallu["mean"] is not None else "  -    "
        faith_str = f"{faith['mean']:.1f}" if faith["mean"] is not None else "  - "
        print(f"{s['length']:>5} {s['format']:>5} {cov_str:>10} {hallu_str:>10} {faith_str:>9} {s['trials']:>3}")


if __name__ == "__main__":
    main()
