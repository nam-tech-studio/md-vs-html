#!/usr/bin/env python3
"""
extras 判定の hallucinations を LLM (Claude) に分類させる。

カテゴリ:
- structural: HTML/SVG/CSS など形式構造の観察 (要件本体ではない、形式由来のノイズ)
- business: 原文書にない要件・機能・数値・固有名詞・ロール・ポリシー等を捏造したもの

並列で claude -p に投げ、結果を summary_classified_llm.json に出力。
"""

import concurrent.futures
import json
import re
import statistics
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXT_DIR = ROOT / "results" / "judgments" / "extras"
COV_DIR = ROOT / "results" / "judgments" / "coverage"
OUT = ROOT / "results" / "summary_classified_llm.json"
DETAIL = ROOT / "results" / "judgments" / "classified"
LOG = ROOT / "results" / "classify_extras.log"

PROMPT = """あなたは厳密な分類者です。以下のhallucination claim一覧を、各々が「formatについての観察」か「ビジネス要件のhallucination」かに分類してください。

定義:
- structural: HTML/SVG/CSS/属性/タグ/見出し階層/配色/レイアウト/ファイル名/lang属性/data属性/aria属性/カテゴリ分類タグ/figureや図のキャプション・タイトル・ラベル・配色・要素・矢印など、HTMLという形式そのものに関する観察。要件定義書の中身ではなく、それを表現する見た目・構造の話。
- business: 原文の要件定義書に記述のない、実機能・数値・固有名詞・ロール・ポリシー・制限値・ビジネスルール等を捏造したもの。プロダクトとして「こんな要件があるはず」という推測。

出力フォーマット (これ以外の文字を一切出さない):
```json
{"types": ["structural", "business", "structural", ...]}
```

types配列は入力claimsの順番に厳密に対応するboolでなく、文字列 "structural" or "business" のみ。

入力:
"""


def call_claude(prompt: str, retries: int = 3, timeout: int = 300) -> str:
    last_err = None
    for attempt in range(retries):
        try:
            proc = subprocess.run(
                ["claude", "-p", prompt, "--model", "claude-haiku-4-5",
                 "--no-session-persistence", "--allowedTools", ""],
                capture_output=True, text=True, timeout=timeout,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return proc.stdout
            last_err = f"exit={proc.returncode} stderr={proc.stderr[:200]}"
        except subprocess.TimeoutExpired:
            last_err = "timeout"
        time.sleep(2 ** attempt + 1)
    raise RuntimeError(f"claude failed: {last_err}")


def extract_json(text: str) -> dict:
    m = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    candidate = m.group(1).strip() if m else text[text.find("{"): text.rfind("}") + 1]
    return json.loads(candidate)


def log(msg: str):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def parse_id(name: str):
    parts = name.replace(".json", "").split("_")
    return int(parts[0]), parts[1], int(parts[2].replace("trial", ""))


def classify_one(p: Path) -> dict:
    name = p.name
    out_path = DETAIL / name
    if out_path.exists():
        return json.loads(out_path.read_text(encoding="utf-8"))

    d = json.loads(p.read_text(encoding="utf-8"))
    halls = d.get("hallucinations", [])
    if not halls:
        result = {"file": name, "types": [], "claims": []}
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result

    claims_text = "\n".join(f"{i + 1}. {h['claim']}" for i, h in enumerate(halls))
    prompt = PROMPT + claims_text

    raw = call_claude(prompt)
    parsed = extract_json(raw)
    types = parsed.get("types", [])
    if len(types) != len(halls):
        # 失敗時はパターンマッチにフォールバック
        log(f"[warn] {name} types_len={len(types)} expected={len(halls)} → fallback all structural")
        types = ["structural"] * len(halls)

    result = {
        "file": name,
        "types": types,
        "claims": [h["claim"] for h in halls],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def aggregate(detailed_results):
    # by_id: parsed file → result
    by_meta = {}
    for d in detailed_results:
        length, fmt, trial = parse_id(d["file"])
        biz = sum(1 for t in d["types"] if t == "business")
        struct = sum(1 for t in d["types"] if t == "structural")
        biz_claims = [c for c, t in zip(d["claims"], d["types"]) if t == "business"]
        by_meta[(length, fmt, trial)] = {"biz": biz, "struct": struct, "biz_claims": biz_claims}

    # join with cov / extras meta
    rows = []
    for (length, fmt, trial), classified in by_meta.items():
        ext = json.loads((EXT_DIR / f"{length}_{fmt}_trial{trial}.json").read_text(encoding="utf-8"))
        cov = json.loads((COV_DIR / f"{length}_{fmt}_trial{trial}.json").read_text(encoding="utf-8"))
        covered = cov.get("_meta", {}).get("covered_count", 0)
        faithful = ext.get("_meta", {}).get("faithful_count", 0)
        biz = classified["biz"]
        denom = covered + faithful + biz
        rate = biz / denom if denom else 0
        rows.append({
            "length": length, "format": fmt, "trial": trial,
            "covered": covered, "faithful": faithful,
            "structural_meta_observations": classified["struct"],
            "business_hallucinations": biz,
            "business_hallucination_rate": rate,
            "biz_examples": classified["biz_claims"][:5],
        })

    # group
    groups = {}
    for r in rows:
        groups.setdefault((r["length"], r["format"]), []).append(r)

    summary = []
    for (length, fmt), grs in sorted(groups.items()):
        biz_rates = [r["business_hallucination_rate"] for r in grs]
        biz_counts = [r["business_hallucinations"] for r in grs]
        struct_counts = [r["structural_meta_observations"] for r in grs]
        examples = []
        for r in grs:
            for ex in r["biz_examples"]:
                if ex not in examples and len(examples) < 8:
                    examples.append(ex)

        summary.append({
            "length": length,
            "format": fmt,
            "trials": len(grs),
            "structural_meta_observations_mean": statistics.mean(struct_counts),
            "business_hallucinations_mean": statistics.mean(biz_counts),
            "business_hallucination_rate_mean": statistics.mean(biz_rates),
            "business_hallucination_rate_sd": statistics.pstdev(biz_rates) if len(biz_rates) > 1 else 0,
            "business_hallucination_examples": examples,
        })
    return summary, rows


def main():
    DETAIL.mkdir(parents=True, exist_ok=True)
    LOG.write_text("")  # clear

    files = sorted(EXT_DIR.glob("*.json"))
    log(f"Classifying {len(files)} hallucination files (parallel=2)")

    detailed = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        futures = {ex.submit(classify_one, p): p for p in files}
        for fut in concurrent.futures.as_completed(futures):
            p = futures[fut]
            try:
                d = fut.result()
                biz = sum(1 for t in d["types"] if t == "business")
                log(f"[done] {p.name} biz={biz}/{len(d['types'])}")
                detailed.append(d)
            except Exception as e:
                log(f"[FAIL] {p.name} {e}")

    summary, rows = aggregate(detailed)
    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    DETAIL_CSV = ROOT / "results" / "summary_classified_detail.json"
    DETAIL_CSV.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    log(f"Wrote → {OUT}")
    print()
    print(f"{'len':>5} {'fmt':>5} {'struct':>8} {'biz':>6} {'biz_rate':>10}")
    for s in summary:
        print(
            f"{s['length']:>5} {s['format']:>5} "
            f"{s['structural_meta_observations_mean']:>8.1f} "
            f"{s['business_hallucinations_mean']:>6.1f} "
            f"{s['business_hallucination_rate_mean']*100:>9.2f}% "
            f"(SD {s['business_hallucination_rate_sd']*100:.2f}pt)"
        )
    print()
    print("=== Business hallucination 例 (HTML側のみ) ===")
    for s in summary:
        if s["format"] == "html" and s["business_hallucination_examples"]:
            print(f"\n[{s['length']}_html]")
            for ex in s["business_hallucination_examples"]:
                print(f"  - {ex}")


if __name__ == "__main__":
    main()
