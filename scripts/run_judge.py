#!/usr/bin/env python3
"""
40試行の説明テキストに対して2パスの判定を実行する。

Pass 1: Coverage判定 (チェックリスト各項目について covered か否か)
Pass 2: Extras抽出&裏付け判定 (チェックリスト外の主張が原文書に裏付けられるか)

Usage:
  python3 scripts/run_judge.py [--length 50,100,250,500] [--format md,html] [--trial 1,2,3,4,5] [--pass 1,2] [--parallel 4]

各 (length, format, trial) ペアについて、coverage と extras を別々に実行。
出力は results/judgments/coverage/ と results/judgments/extras/ に保存。
"""

import argparse
import concurrent.futures
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = ROOT / "prompts"
RESULTS = ROOT / "results"
TRIALS = ROOT / "trials"
SOURCE = ROOT / "source"
CHECKLISTS = ROOT / "checklists"
LOG = RESULTS / "run_judge.log"

DEFAULT_LENGTHS = [50, 100, 250, 500]
DEFAULT_FORMATS = ["md", "html"]
DEFAULT_PASSES = [1, 2]


def log(msg: str):
    timestamp = time.strftime("%H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def write_json(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def run_claude(prompt: str, timeout: int = 600, retries: int = 3) -> str:
    """claude -p でプロンプトを実行し、stdoutを返す。並列実行時の間欠的失敗に備えて数回リトライ。"""
    last_err = None
    for attempt in range(retries):
        try:
            proc = subprocess.run(
                [
                    "claude",
                    "-p",
                    prompt,
                    "--model",
                    "claude-opus-4-7",
                    "--no-session-persistence",
                    "--allowedTools",
                    "",  # ツール禁止 (純粋なテキスト判定のみ)
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return proc.stdout
            last_err = (
                f"exited {proc.returncode}, "
                f"stderr={proc.stderr[:300]!r}, stdout_len={len(proc.stdout)}"
            )
        except subprocess.TimeoutExpired as e:
            last_err = f"timeout after {timeout}s"
        # 失敗時はバックオフ後リトライ
        time.sleep(2 ** attempt + 2)  # 3s, 4s, 6s
    raise RuntimeError(f"claude failed after {retries} retries: {last_err}")


def extract_json(text: str) -> dict:
    """
    LLMの応答からJSON部分を抽出してパース。
    ```json ... ``` ブロック、または最初の {...} ブロックを探す。
    """
    # コードブロック内のJSONを試す
    m = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if m:
        candidate = m.group(1).strip()
    else:
        # 最初の { から最後の } まで
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("no JSON found in response")
        candidate = text[start : end + 1]

    return json.loads(candidate)


def judge_coverage(length: int, fmt: str, trial: int) -> dict:
    explanation = read(RESULTS / "explanations" / f"{length}_{fmt}_trial{trial}.md")
    checklist = json.loads(read(CHECKLISTS / f"{length}.json"))
    rules = read(PROMPTS / "judge_coverage.txt")

    prompt = (
        rules
        + "\n\n[説明テキスト]\n"
        + explanation
        + "\n\n[チェックリスト]\n"
        + json.dumps(checklist, ensure_ascii=False, indent=2)
    )

    raw = run_claude(prompt)
    result = extract_json(raw)
    # 結果に metadata を付与
    result["_meta"] = {
        "length": length,
        "format": fmt,
        "trial": trial,
        "checklist_total": len(checklist["items"]),
        "covered_count": len(result.get("covered_ids", [])),
    }
    return result


def judge_extras(length: int, fmt: str, trial: int) -> dict:
    explanation = read(RESULTS / "explanations" / f"{length}_{fmt}_trial{trial}.md")
    checklist = json.loads(read(CHECKLISTS / f"{length}.json"))
    source = read(SOURCE / f"{length}.md")
    rules = read(PROMPTS / "judge_extras.txt")

    prompt = (
        rules
        + "\n\n[説明テキスト]\n"
        + explanation
        + "\n\n[チェックリスト]\n"
        + json.dumps(checklist, ensure_ascii=False, indent=2)
        + "\n\n[原文書]\n"
        + source
    )

    raw = run_claude(prompt)
    result = extract_json(raw)
    result["_meta"] = {
        "length": length,
        "format": fmt,
        "trial": trial,
        "faithful_count": len(result.get("faithful_extras", [])),
        "hallucination_count": len(result.get("hallucinations", [])),
    }
    return result


def run_one_pass(pass_num: int, length: int, fmt: str, trial: int) -> str:
    """1つの試行に対して指定パスを実行。既存ファイルがあればスキップ。"""
    if pass_num == 1:
        out = RESULTS / "judgments" / "coverage" / f"{length}_{fmt}_trial{trial}.json"
        runner = judge_coverage
        label = "cov"
    elif pass_num == 2:
        out = RESULTS / "judgments" / "extras" / f"{length}_{fmt}_trial{trial}.json"
        runner = judge_extras
        label = "ext"
    else:
        return f"unknown pass {pass_num}"

    if out.exists() and out.stat().st_size > 50:
        return f"[skip {label}] {length}_{fmt}_trial{trial}"

    start = time.time()
    try:
        result = runner(length, fmt, trial)
        write_json(out, result)
        secs = int(time.time() - start)
        meta = result.get("_meta", {})
        if pass_num == 1:
            return (
                f"[done {label}] {length}_{fmt}_trial{trial} "
                f"{secs}s covered={meta.get('covered_count')}/{meta.get('checklist_total')}"
            )
        else:
            return (
                f"[done {label}] {length}_{fmt}_trial{trial} "
                f"{secs}s faithful={meta.get('faithful_count')} "
                f"hallu={meta.get('hallucination_count')}"
            )
    except Exception as e:
        secs = int(time.time() - start)
        # エラー詳細をエラーファイルに残す
        errfile = out.with_suffix(".err")
        errfile.parent.mkdir(parents=True, exist_ok=True)
        errfile.write_text(f"{type(e).__name__}: {e}\n", encoding="utf-8")
        return f"[FAIL {label}] {length}_{fmt}_trial{trial} {secs}s {type(e).__name__}: {str(e)[:200]}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--length", default=",".join(map(str, DEFAULT_LENGTHS)))
    parser.add_argument("--format", default=",".join(DEFAULT_FORMATS))
    parser.add_argument("--trial", default="1,2,3,4,5")
    parser.add_argument("--pass", dest="pass_", default=",".join(map(str, DEFAULT_PASSES)))
    parser.add_argument("--parallel", type=int, default=4)
    args = parser.parse_args()

    lengths = [int(x) for x in args.length.split(",")]
    formats = args.format.split(",")
    trials = [int(x) for x in args.trial.split(",")]
    passes = [int(x) for x in args.pass_.split(",")]

    jobs = []
    for p in passes:
        for length in lengths:
            for fmt in formats:
                for trial in trials:
                    jobs.append((p, length, fmt, trial))

    log(f"Total judge jobs: {len(jobs)} | parallel={args.parallel}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.parallel) as ex:
        futures = [ex.submit(run_one_pass, *job) for job in jobs]
        for future in concurrent.futures.as_completed(futures):
            log(future.result())

    log("All judge jobs done.")


if __name__ == "__main__":
    main()
