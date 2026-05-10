#!/usr/bin/env python3
"""
判定結果のhallucinations を「構造メタ情報の言及」と「真のビジネス幻覚」に分類する。

HTML を読んだ被験者は、ビジネス内容に加えて HTML 構造 (lang, viewport, data-属性,
SVG色・ストローク・aria属性・キャプション等) も「説明」に含めることがある。
これは原文MDに記述がないため判定者にhallucination扱いされるが、形式のノイズに過ぎず、
ビジネス要件の幻覚 (新機能・新数値の捏造) ではない。

本スクリプトは extras 判定結果に対してパターンマッチで分類し、
results/summary_classified.json に再集計を出力する。
"""

import json
import re
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXT_DIR = ROOT / "results" / "judgments" / "extras"
OUT = ROOT / "results" / "summary_classified.json"

# 構造メタ情報を示す単語パターン (HTML特有のフォーマット観察)
STRUCTURE_PATTERNS = [
    # HTMLタグ
    r"<\w+", r"</\w+",
    # head 系メタデータ
    r"\blang\s*=", r"\blang属性", r"\bxml:lang",
    r"charset", r"UTF-?8",
    r"viewport", r"initial-scale", r"width=device-width",
    r"<link\b", r"<meta\b",
    r"styles?\.css", r"スタイルシート", r"インラインCSS", r"インラインスタイル",
    r"DOCTYPE", r"!doctype",
    # 属性系
    r"\bdata-[a-z-]+", r"data属性", r"data-category", r"data-section",
    r"\baria-", r"aria属性", r"aria-label", r"aria-labelledby", r"role=",
    r"\bclass\s*=", r"クラス属性", r"クラス名",
    r"\bid\s*=", r"\bhref\s*=",
    # SVG / 図
    r"<svg", r"\bSVG", r"\bsvg\b",
    r"stroke", r"fill[=:]", r"stroke-dasharray", r"破線", r"viewBox", r"<marker",
    r"\b図(?:が|は|の|に|を|: ?)", r"^図\s*[:.]", r"\b図\s*\d", r"ダイアグラム",
    r"の?図(?:が|は|の|として|タイトル|ラベル|キャプション)",
    r"アイコン", r"ボックス", r"矢印", r"\b線\b", r"破線", r"実線",
    r"配色", r"色 ?(?:#|コード)", r"#[0-9a-fA-F]{3,6}",
    r"緑系|黄系|灰系|青系|赤系", r"カラー", r"カラーリング", r"背景色", r"文字色",
    r"フォント", r"font",
    r"キャプション", r"figcaption",
    r"figure",
    # セマンティック構造観察
    r"テーブル形式", r"表形式", r"<table>", r"<thead>", r"<tbody>", r"<tr>", r"<td>", r"<th>",
    r"\b<dl>", r"\bdl\b.*形式", r"定義リスト",
    r"<title>", r"<head>", r"<body>", r"<header>", r"<main>", r"<section>",
    r"<details>", r"<summary>", r"<aside>", r"<nav>",
    r"<figure>", r"<figcaption>",
    r"<ul>", r"<ol>", r"<li>", r"<p>", r"<h[1-6]>", r"<caption>",
    r"<strong>", r"<em>", r"<code>",
    r"見出しレベル", r"h1.*h2", r"見出しタグ",
    r"番号付きリスト", r"箇条書き", r"bullet",
    r"バッジ", r"badge",
    r"マーカー(?:に|を|が)", r"<marker",
    # 階層/順序の観察
    r"セクション番号", r"出現順", r"並び順", r"順序が", r"順序で並",
    r"カテゴリ分類", r"階層図", r"階層として",
    r"番号は\d+(?:-|〜)\d+", r"非連続な順序",
    # ファイル/フォーマット観察
    r"ファイル名は", r"ファイル名が", r"\.html\b", r"requirements\.html",
    r"HTML(?:5)?(?:文書|形式|フォーマット|ファイル)",
    r"添付されている.*図", r"ハイパーリンク",
    r"レイアウト",
    r"タイトル(?:は|が).*requirements",
    # 「タイトル/ラベル/キャプション/テキストは『〜』である」型 (図関連)
    r"(?:タイトル|ラベル|キャプション|テキスト)(?:は|が)「.*」(?:である|です)",
    r"の?(?:タイトル|ラベル|キャプション)テキスト",
    # SVG 状態遷移図
    r"状態遷移図", r"プレゼンス.*遷移図", r"ワークフロー(?:構造)?図",
    r"トリガー.*ステップ.*アクション(?!の)",
    r"3つの.*ノード",
    # 「~として表現/記述/分類されている」型
    r"として(?:表現|記述|分類|可視化|図示)され",
    r"線が引かれ", r"線が結ば", r"接続(?:され|して)",
    r"要素として(?:「|『|\[)",
    r"figcap", r"figcaption",
    # 分類タグ・data-属性の値列挙
    r"分類タグ", r"カテゴリ(?:分類|タグ)?の?値",
    r"\b(?:user|workspace|presence|channel|message|notification|nfr|tech|security|warning|overview|account|extension|support|admin)\b\s*(?:として|タグ|属性|を付与|が付与|が指定)",
    # 表構造
    r"表「[^」]*」", r"テーブル「[^」]*」",
    r"表として(?:記述|表現|まとめられ)",
    # ARIA/role 観察
    r"\barole=", r"\barrole=", r"\borarole=",
    # 色カテゴリ表現
    r"\b(?:緑|黄|灰|青|赤|オレンジ)系", r"\b(?:緑|黄|灰|青|赤|オレンジ)色",
    # その他
    r"見出しと(?:紐|結)付け", r"aria-labelledby",
    r"スクロール挙動", r"レスポンシブ",
    # h1/h2/h3 階層観察
    r"h[1-3](?:から|→|〜|まで)",
    r"\bvalues?\s*=",
]

STRUCTURE_RE = re.compile("|".join(STRUCTURE_PATTERNS), re.IGNORECASE)


def is_structural(claim: str) -> bool:
    """主張が構造メタ情報を述べているかをパターンマッチで判定。"""
    return bool(STRUCTURE_RE.search(claim))


def classify_file(p: Path) -> dict:
    d = json.loads(p.read_text(encoding="utf-8"))
    halls = d.get("hallucinations", [])
    structural = [h for h in halls if is_structural(h["claim"])]
    business = [h for h in halls if not is_structural(h["claim"])]
    return {
        "file": p.name,
        "total_hallucinations": len(halls),
        "structural_meta": len(structural),
        "business_hallucinations": len(business),
        "business_hallucination_examples": [h["claim"] for h in business[:5]],
    }


def parse_id(name: str):
    # 50_md_trial1.json
    parts = name.replace(".json", "").split("_")
    return int(parts[0]), parts[1], int(parts[2].replace("trial", ""))


def main():
    rows = []
    for p in sorted(EXT_DIR.glob("*.json")):
        length, fmt, trial = parse_id(p.name)
        c = classify_file(p)
        c.update({"length": length, "format": fmt, "trial": trial})

        # 元データから faithful と covered を読む
        ext = json.loads(p.read_text(encoding="utf-8"))
        c["faithful_extras"] = ext.get("_meta", {}).get("faithful_count", 0)

        cov_path = ROOT / "results" / "judgments" / "coverage" / p.name
        if cov_path.exists():
            cov = json.loads(cov_path.read_text(encoding="utf-8"))
            c["covered"] = cov.get("_meta", {}).get("covered_count", 0)
            c["checklist_total"] = cov.get("_meta", {}).get("checklist_total", 0)
        rows.append(c)

    # (length, format) ごとに集計
    groups = {}
    for r in rows:
        groups.setdefault((r["length"], r["format"]), []).append(r)

    summary = []
    for (length, fmt), group_rows in sorted(groups.items()):
        total_hal = [r["total_hallucinations"] for r in group_rows]
        struct_hal = [r["structural_meta"] for r in group_rows]
        biz_hal = [r["business_hallucinations"] for r in group_rows]
        # business hallucination rate as fraction of (covered + faithful + biz_hal)
        biz_hal_rates = []
        for r in group_rows:
            denom = r.get("covered", 0) + r.get("faithful_extras", 0) + r["business_hallucinations"]
            if denom > 0:
                biz_hal_rates.append(r["business_hallucinations"] / denom)
            else:
                biz_hal_rates.append(0)

        # 例 (max 3件)
        examples = []
        for r in group_rows:
            for ex in r["business_hallucination_examples"]:
                if ex not in examples and len(examples) < 5:
                    examples.append(ex)

        summary.append({
            "length": length,
            "format": fmt,
            "trials": len(group_rows),
            "total_hallucinations_mean": statistics.mean(total_hal),
            "structural_meta_mean": statistics.mean(struct_hal),
            "business_hallucinations_mean": statistics.mean(biz_hal),
            "business_hallucination_rate_mean": statistics.mean(biz_hal_rates),
            "business_hallucination_rate_sd": statistics.pstdev(biz_hal_rates) if len(biz_hal_rates) > 1 else 0,
            "business_hallucination_examples": examples,
        })

    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote → {OUT}")
    print()
    print(f"{'len':>5} {'fmt':>5} {'total_hal':>10} {'struct':>8} {'biz':>6} {'biz_rate':>10}")
    for s in summary:
        print(
            f"{s['length']:>5} {s['format']:>5} "
            f"{s['total_hallucinations_mean']:>10.1f} "
            f"{s['structural_meta_mean']:>8.1f} "
            f"{s['business_hallucinations_mean']:>6.1f} "
            f"{s['business_hallucination_rate_mean']*100:>9.2f}%"
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
