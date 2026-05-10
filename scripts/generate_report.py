#!/usr/bin/env python3
"""
results/summary.json + summary_classified_llm.json から最終HTMLレポートを生成。

このレポート自体もHTML出力 — 検証テーマと整合させる。
"""

import csv
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
SUMMARY_JSON = RESULTS / "summary.json"
CLASSIFIED_JSON = RESULTS / "summary_classified_llm.json"
SUMMARY_CSV = RESULTS / "summary.csv"
OUT = RESULTS / "report.html"

CSS = """
:root {
  --c-text: #1a1a1a;
  --c-muted: #5a5a5a;
  --c-bg: #f7f8fa;
  --c-surface: #ffffff;
  --c-border: #e1e4e8;
  --c-accent: #0366d6;
  --c-md: #2563eb;
  --c-html: #dc2626;
  --c-warn: #d97706;
  --c-success: #1a7f37;
}
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans", "Yu Gothic", sans-serif;
  color: var(--c-text);
  background: var(--c-bg);
  margin: 0;
  padding: 0;
  line-height: 1.7;
}
main { max-width: 980px; margin: 0 auto; padding: 2rem 1.5rem 4rem; }
header.hero {
  background: linear-gradient(135deg, #0366d6 0%, #6f42c1 100%);
  color: #fff;
  padding: 3rem 1.5rem 2rem;
  text-align: center;
}
header.hero h1 { font-size: 2rem; margin: 0 0 0.5rem; }
header.hero p { margin: 0; opacity: 0.9; }

h1, h2, h3 { color: var(--c-text); margin-top: 2rem; }
h2 { border-bottom: 2px solid var(--c-border); padding-bottom: 0.3rem; }

table { width: 100%; border-collapse: collapse; margin: 1rem 0; background: var(--c-surface); }
th, td { border: 1px solid var(--c-border); padding: 0.5rem 0.7rem; text-align: left; vertical-align: top; }
th { background: #f0f3f6; font-weight: 600; }
tr:nth-child(even) td { background: #fafbfc; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }

.badge { display: inline-block; padding: 0.1em 0.6em; border-radius: 999px; font-size: 0.78em; font-weight: 600; }
.badge-md   { background: #dbeafe; color: var(--c-md); border: 1px solid var(--c-md); }
.badge-html { background: #fee2e2; color: var(--c-html); border: 1px solid var(--c-html); }

.kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; margin: 1rem 0 2rem; }
.kpi { background: var(--c-surface); border: 1px solid var(--c-border); border-radius: 8px; padding: 1rem; }
.kpi h4 { margin: 0 0 0.4rem; font-size: 0.85rem; color: var(--c-muted); text-transform: uppercase; letter-spacing: 0.05em; }
.kpi .value { font-size: 1.6rem; font-weight: 700; }
.kpi .delta { font-size: 0.85rem; color: var(--c-muted); margin-top: 0.2rem; }

.chart {
  background: var(--c-surface); border: 1px solid var(--c-border); border-radius: 8px;
  padding: 1rem; margin: 1.5rem 0;
}
.chart svg { width: 100%; height: auto; display: block; }
.legend { display: flex; gap: 1.5rem; margin: 0.5rem 0 0; font-size: 0.9rem; flex-wrap: wrap; }
.legend-item { display: flex; align-items: center; gap: 0.4rem; }
.legend-swatch { width: 14px; height: 14px; border-radius: 3px; }

aside.callout {
  border-left: 4px solid var(--c-accent);
  background: var(--c-surface);
  padding: 0.8rem 1rem; margin: 1rem 0; border-radius: 0 6px 6px 0;
}
aside.callout.win { border-color: var(--c-success); }
aside.callout.warn { border-color: var(--c-warn); }
aside.callout.danger { border-color: var(--c-html); }

details { background: var(--c-surface); border: 1px solid var(--c-border); border-radius: 6px; padding: 0.6em 1em; margin: 0.6em 0; }
summary { cursor: pointer; font-weight: 600; }

code { background: var(--c-surface); border: 1px solid var(--c-border); border-radius: 3px; padding: 0.05em 0.3em; font-family: "SF Mono", monospace; font-size: 0.9em; }

ul.examples li { margin: 0.4em 0; }
"""


def fmt_pct(x, digits=1, signed=False):
    if x is None:
        return "—"
    sign = "+" if signed and x >= 0 else ""
    return f"{sign}{x*100:.{digits}f}%"


def fmt_num(x, digits=2, signed=False):
    if x is None:
        return "—"
    sign = "+" if signed and x >= 0 else ""
    return f"{sign}{x:.{digits}f}"


def render_bar_chart(summary, metric_path, title, format_value, max_value=None, key_format=("md", "html")):
    lengths = sorted({s["length"] for s in summary})
    formats = list(key_format)
    colors = {"md": "#2563eb", "html": "#dc2626"}

    by_key = {(s["length"], s["format"]): s for s in summary}

    if max_value is None:
        vals = []
        for l in lengths:
            for f in formats:
                s = by_key.get((l, f))
                if s:
                    v = s
                    for k in metric_path:
                        v = v.get(k)
                        if v is None:
                            break
                    if v is not None:
                        vals.append(v)
        max_value = max(vals) * 1.15 if vals else 1.0

    if max_value == 0:
        max_value = 1.0

    width = 720
    height = 320
    pad_left = 60
    pad_right = 20
    pad_top = 30
    pad_bottom = 50
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom

    group_w = plot_w / len(lengths)
    bar_w = (group_w - 16) / 2

    svg = [
        f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{title}">',
        f'<text x="{width/2}" y="20" text-anchor="middle" font-size="14" font-weight="600">{title}</text>',
    ]

    for i in range(6):
        y = pad_top + plot_h - (plot_h * i / 5)
        v = max_value * i / 5
        svg.append(f'<line x1="{pad_left}" y1="{y}" x2="{width-pad_right}" y2="{y}" stroke="#e1e4e8" stroke-width="1"/>')
        svg.append(f'<text x="{pad_left-6}" y="{y+4}" text-anchor="end" font-size="11" fill="#5a5a5a">{format_value(v)}</text>')

    for li, length in enumerate(lengths):
        gx = pad_left + group_w * li
        for fi, fmt in enumerate(formats):
            s = by_key.get((length, fmt))
            if not s:
                continue
            v = s
            for k in metric_path:
                v = v.get(k)
                if v is None:
                    break
            if v is None:
                continue
            bar_h = plot_h * (v / max_value) if max_value else 0
            x = gx + 8 + bar_w * fi
            y = pad_top + plot_h - bar_h
            svg.append(
                f'<rect x="{x}" y="{y}" width="{bar_w}" height="{bar_h}" fill="{colors[fmt]}" rx="2" />'
            )
            svg.append(
                f'<text x="{x+bar_w/2}" y="{y-3}" text-anchor="middle" font-size="11" fill="#1a1a1a">{format_value(v)}</text>'
            )
        svg.append(
            f'<text x="{gx + group_w/2}" y="{height-pad_bottom+18}" text-anchor="middle" font-size="12" fill="#1a1a1a">{length}行</text>'
        )

    svg.append("</svg>")

    legend = (
        '<div class="legend">'
        f'<div class="legend-item"><div class="legend-swatch" style="background:{colors["md"]}"></div>Markdown</div>'
        f'<div class="legend-item"><div class="legend-swatch" style="background:{colors["html"]}"></div>HTML</div>'
        '</div>'
    )

    return f'<div class="chart">{"".join(svg)}{legend}</div>'


def render_summary_table(summary):
    rows = []
    for s in sorted(summary, key=lambda x: (x["length"], x["format"])):
        cov = s["coverage_rate"]
        hallu = s["hallucination_rate"]
        faith = s["faithful_extras"]
        sig = s["total_signal"]
        fmt_cls = "badge-md" if s["format"] == "md" else "badge-html"
        rows.append(
            f'<tr>'
            f'<td>{s["length"]}行</td>'
            f'<td><span class="badge {fmt_cls}">{s["format"].upper()}</span></td>'
            f'<td class="num">{s["trials"]}</td>'
            f'<td class="num">{fmt_pct(cov["mean"])} ± {fmt_pct(cov["sd"])}</td>'
            f'<td class="num">{fmt_pct(hallu["mean"]) if hallu["mean"] is not None else "—"}</td>'
            f'<td class="num">{fmt_num(faith["mean"], 1) if faith["mean"] is not None else "—"}</td>'
            f'<td class="num">{fmt_num(sig["mean"], 1) if sig["mean"] is not None else "—"}</td>'
            f'</tr>'
        )
    return (
        '<table><thead><tr>'
        '<th>長さ</th><th>形式</th><th>試行数</th>'
        '<th>Coverage rate (mean±SD)</th>'
        '<th>Hallucination rate (raw)</th>'
        '<th>Faithful Extras (mean)</th>'
        '<th>Total Signal (mean)</th>'
        '</tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table>"
    )


def render_classified_table(classified):
    rows = []
    for s in sorted(classified, key=lambda x: (x["length"], x["format"])):
        fmt_cls = "badge-md" if s["format"] == "md" else "badge-html"
        rate = s.get("business_hallucination_rate_mean")
        rate_sd = s.get("business_hallucination_rate_sd")
        rows.append(
            f'<tr>'
            f'<td>{s["length"]}行</td>'
            f'<td><span class="badge {fmt_cls}">{s["format"].upper()}</span></td>'
            f'<td class="num">{fmt_num(s["structural_meta_observations_mean"], 1)}</td>'
            f'<td class="num">{fmt_num(s["business_hallucinations_mean"], 1)}</td>'
            f'<td class="num">{fmt_pct(rate)} ± {fmt_pct(rate_sd)}</td>'
            f'</tr>'
        )
    return (
        '<table><thead><tr>'
        '<th>長さ</th><th>形式</th>'
        '<th>構造メタ観察数 (HTML特有のノイズ)</th>'
        '<th>業務hallucination数</th>'
        '<th>業務hallucination率 (mean±SD)</th>'
        '</tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table>"
    )


def compute_diff_table(summary):
    by_key = {(s["length"], s["format"]): s for s in summary}
    lengths = sorted({s["length"] for s in summary})

    rows = []
    for l in lengths:
        md = by_key.get((l, "md"))
        ht = by_key.get((l, "html"))
        if not md or not ht:
            continue

        def diff(metric):
            m = md[metric]["mean"] if md[metric]["mean"] is not None else None
            h = ht[metric]["mean"] if ht[metric]["mean"] is not None else None
            return (h - m) if m is not None and h is not None else None

        cov_diff = diff("coverage_rate")
        hallu_diff = diff("hallucination_rate")
        winner_cov = "HTML" if cov_diff and cov_diff > 1e-6 else ("MD" if cov_diff and cov_diff < -1e-6 else "—")
        winner_hal = "MD" if hallu_diff and hallu_diff > 1e-6 else ("HTML" if hallu_diff and hallu_diff < -1e-6 else "—")
        rows.append(
            f'<tr>'
            f'<td>{l}行</td>'
            f'<td class="num">{fmt_pct(md["coverage_rate"]["mean"])}</td>'
            f'<td class="num">{fmt_pct(ht["coverage_rate"]["mean"])}</td>'
            f'<td class="num">{fmt_pct(cov_diff, signed=True) if cov_diff is not None else "—"}</td>'
            f'<td>{winner_cov}</td>'
            f'<td class="num">{fmt_pct(md["hallucination_rate"]["mean"]) if md["hallucination_rate"]["mean"] is not None else "—"}</td>'
            f'<td class="num">{fmt_pct(ht["hallucination_rate"]["mean"]) if ht["hallucination_rate"]["mean"] is not None else "—"}</td>'
            f'<td class="num">{fmt_pct(hallu_diff, signed=True) if hallu_diff is not None else "—"}</td>'
            f'<td>{winner_hal}</td>'
            f'</tr>'
        )
    return (
        '<table><thead><tr>'
        '<th>長さ</th>'
        '<th>MD Cov.</th><th>HTML Cov.</th><th>差(HTML-MD)</th><th>勝者</th>'
        '<th>MD Hallu.</th><th>HTML Hallu.</th><th>差(HTML-MD)</th><th>幻覚少ない方</th>'
        '</tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table>"
    )


def render_examples(classified):
    """各HTML条件での業務hallucination例をdetailsで折りたたみ表示"""
    by_html = [s for s in classified if s["format"] == "html"]
    parts = []
    for s in sorted(by_html, key=lambda x: x["length"]):
        if not s.get("business_hallucination_examples"):
            continue
        examples = s["business_hallucination_examples"]
        items = "".join(f"<li><code>{e}</code></li>" for e in examples)
        parts.append(
            f'<details><summary>{s["length"]}行 HTML — '
            f'業務hallucination例 ({len(examples)}件サンプル)</summary>'
            f'<ul class="examples">{items}</ul></details>'
        )
    return "".join(parts)


def derive_conclusion(summary, classified):
    by_key = {(s["length"], s["format"]): s for s in summary}
    by_class = {(s["length"], s["format"]): s for s in classified}
    lengths = sorted({s["length"] for s in summary})

    cov_diffs = []
    hallu_diffs = []
    biz_hallu_diffs = []
    for l in lengths:
        md = by_key.get((l, "md"))
        ht = by_key.get((l, "html"))
        if md and ht:
            if md["coverage_rate"]["mean"] is not None and ht["coverage_rate"]["mean"] is not None:
                cov_diffs.append((l, ht["coverage_rate"]["mean"] - md["coverage_rate"]["mean"]))
            if md["hallucination_rate"]["mean"] is not None and ht["hallucination_rate"]["mean"] is not None:
                hallu_diffs.append((l, ht["hallucination_rate"]["mean"] - md["hallucination_rate"]["mean"]))
        md_c = by_class.get((l, "md"))
        ht_c = by_class.get((l, "html"))
        if md_c and ht_c:
            biz_hallu_diffs.append((l, ht_c["business_hallucination_rate_mean"] - md_c["business_hallucination_rate_mean"]))

    bullets = []

    # Coverage
    if cov_diffs:
        avg_cov = statistics.mean(d for _, d in cov_diffs)
        bullets.append(
            f"<strong>Coverage rate はほぼ拮抗</strong>: 全長さでMD・HTMLとも100%またはそれに近い値。両形式とも要件の網羅性は十分。 "
            f"(全長さ平均差 HTML-MD = {avg_cov*100:+.2f}pt)"
        )

    # 生のHallu
    if hallu_diffs:
        avg = statistics.mean(d for _, d in hallu_diffs)
        bullets.append(
            f"<strong>生のHallucination率では HTMLが大幅に多い</strong>: 全長さ平均で <span style=\"color:var(--c-html)\">{avg*100:+.1f}pt</span> (HTML&minus;MD)。 "
            f"特に短い文書ほど顕著: 50行 = {hallu_diffs[0][1]*100:+.1f}pt、500行 = {hallu_diffs[-1][1]*100:+.1f}pt。"
        )

    # 構造メタ vs 業務
    bullets.append(
        "<strong>ただし HTML側のhallucinationの大半は「構造メタ情報の観察」</strong>。"
        " HTML文書中の <code>data-category</code> 属性、SVG図のキャプション、テーブル構造、配色などを「説明」として列挙したもの。"
        " 原文MDにこれらの記述はないため判定者は幻覚と判定するが、実際のビジネス要件 (新機能・新数値・新ロール) の捏造ではない。"
    )

    # 業務 hallucination (絶対値で表示)
    if biz_hallu_diffs:
        avg = statistics.mean(d for _, d in biz_hallu_diffs)
        # 絶対値 (各長さHTMLの実数)
        html_50 = next((c["business_hallucination_rate_mean"] for c in classified
                        if c["length"] == 50 and c["format"] == "html"), None)
        html_500 = next((c["business_hallucination_rate_mean"] for c in classified
                         if c["length"] == 500 and c["format"] == "html"), None)
        bullets.append(
            f"<strong>業務hallucination率に絞ると差は縮小</strong>: 全長さ平均差 {avg*100:+.2f}pt (HTML&minus;MD)。"
            f" 50行HTML = {html_50*100:.2f}%、500行HTML = {html_500*100:.2f}%。"
            " 文書が長くなるほど両形式の差は縮む。"
        )

    bullets.append(
        "<strong>結論</strong>: 短い要件定義書 (50-100行) ではMDの方が「読まれた事実」と「述べられた事実」が一致しやすく、確実。"
        " 長い文書 (250-500行) ではHTMLでもCoverage 100%・業務hallucination率 ≦1%を達成し、形式の差は実用上ほぼ無視できる。"
        " 元記事の主張「文書が長くなるほどHTMLの恩恵が大きい」は本実験では <strong>長文ではHTMLが追いつくが超えはしない</strong> として観察された。"
        " 一方、<strong>短文では HTMLにすると判定者が認識する形式ノイズが大量発生する</strong> という副作用も明らかになった。"
    )

    return bullets


def main():
    if not SUMMARY_JSON.exists():
        print(f"missing {SUMMARY_JSON}, run aggregate.py first")
        return 1
    if not CLASSIFIED_JSON.exists():
        print(f"missing {CLASSIFIED_JSON}, run classify_extras_llm.py first")
        return 1

    summary = json.loads(SUMMARY_JSON.read_text(encoding="utf-8"))
    classified = json.loads(CLASSIFIED_JSON.read_text(encoding="utf-8"))

    cov_chart = render_bar_chart(
        summary, ("coverage_rate", "mean"),
        "Coverage rate (mean) - 文書長 × 形式",
        lambda v: f"{v*100:.0f}%",
        max_value=1.0,
    )

    hallu_chart = render_bar_chart(
        summary, ("hallucination_rate", "mean"),
        "Hallucination rate (raw) - 文書長 × 形式",
        lambda v: f"{v*100:.1f}%",
    )

    biz_hallu_chart = render_bar_chart(
        classified, ("business_hallucination_rate_mean",),
        "Business hallucination rate - 文書長 × 形式 (構造メタ除外)",
        lambda v: f"{v*100:.2f}%",
    )

    summary_table = render_summary_table(summary)
    classified_table = render_classified_table(classified)
    diff_table = compute_diff_table(summary)
    examples_html = render_examples(classified)
    conclusion_bullets = derive_conclusion(summary, classified)

    methodology = """
    <p>本検証は「LLMエージェント (Claude Opus 4.7) は、要件定義書を Markdown と HTML のどちらで読んだ方が理解度が高いか」を定量比較する。</p>
    <ul>
      <li>4種類の文書長 (50/100/250/500行) × 2形式 (MD/HTML) × 5試行 = <strong>40試行</strong></li>
      <li>説明生成: 各 trial dir で <code>claude -p</code> をステートレス起動、Opus 4.7、Read/LS/Globのみ許可</li>
      <li>HTML版は別Claudeセッションで MD→HTML 変換 (外部CSS + セマンティックHTML5 + SVG、新規事実追加禁止)
       <ul>
        <li>変換方針は <a href="https://x.com/trq212/status/2052809885763747935">trq212の元記事</a> +
        <a href="https://x.com/nicbstme/status/2052965305148981494">nicbstmeの追加情報</a> に従う</li>
       </ul>
      </li>
      <li>判定: チェックリスト含有 (Pass1) と extras裏付け (Pass2) を Opus 4.7 に推察禁止プロンプトで実施</li>
      <li>主指標: <strong>Coverage rate</strong> (=チェックリスト含有率) と <strong>Hallucination rate</strong></li>
      <li>追加分類: hallucinations を <em>構造メタ観察</em> (HTML/SVG/CSS/属性) と <em>業務hallucination</em> (要件捏造) に Haiku 4.5 で分類</li>
    </ul>
    """

    body_parts = [
        '<header class="hero">',
        '<h1>MD vs HTML 検証レポート</h1>',
        '<p>LLMエージェントは Markdown と HTML、どちらの要件定義書をより正確に読み解くか</p>',
        '</header>',
        '<main>',

        '<section><h2>結論</h2>',
        '<aside class="callout win"><strong>主要な発見</strong><ul>',
    ]
    for b in conclusion_bullets:
        body_parts.append(f'<li>{b}</li>')
    body_parts.append('</ul></aside></section>')

    body_parts += [
        '<section><h2>メソドロジー</h2>',
        methodology,
        '<p>詳細: <a href="../docs/specs/2026-05-09-md-vs-html-design.md">設計仕様書</a> /'
        ' <a href="../WORKLOG.md">作業ログ</a></p>',
        '</section>',

        '<section><h2>① Coverage rate (主指標)</h2>',
        '<p>各試行で生成された説明テキストが、対応するチェックリストを何%カバーしたか。'
        '両形式ともすべての長さで 99-100% に達しており、<strong>網羅性ではほぼ差がない</strong>。</p>',
        cov_chart,
        '</section>',

        '<section><h2>② Hallucination rate (raw)</h2>',
        '<p>説明テキスト中の主張のうち、原文書に裏付けがないもの (推察・捏造) の割合。'
        ' <strong>HTML側で50-100行の文書では20-30%という極めて高い値</strong>。'
        ' しかし内訳を見ると…</p>',
        hallu_chart,
        '</section>',

        '<section><h2>③ 構造メタ観察 vs 業務hallucination</h2>',
        '<p>HTML版を読んだ被験者は、原文MDに記述のないHTML構造の観察 (data-category属性、SVG図、'
        ' テーブル構造、配色、aria-label等) を「説明」に含める傾向がある。'
        ' これは判定者から幻覚扱いされるが、要件定義書の<em>中身</em>を捏造しているわけではない。</p>',
        '<p>そこで Haiku 4.5 を用いて、各 hallucination claim を以下の2カテゴリに分類した:</p>',
        '<ul>'
        '<li><strong>structural</strong>: HTML形式そのものに関する観察 (タグ、属性、SVG、配色等)</li>'
        '<li><strong>business</strong>: 原文書にない要件・機能・数値・固有名詞・ポリシーを捏造したもの</li>'
        '</ul>',
        classified_table,
        biz_hallu_chart,
        '<p>業務hallucination率に絞ると、最大でも約7% (50行HTML)。'
        ' 250行以上では1%前後、500行ではMD・HTMLとも0.1%以下に収束。</p>',
        examples_html,
        '</section>',

        '<section><h2>④ 条件別サマリー (生指標)</h2>',
        summary_table,
        '</section>',

        '<section><h2>⑤ 形式間の差分 (生指標ベース)</h2>',
        diff_table,
        '</section>',

        '<section><h2>⑥ 制限事項と留意点</h2>',
        '<ul>',
        '<li>試行数は条件あたり5回。サンプル数が小さく、統計的有意性は限定的。SDの確認は推奨される。</li>',
        '<li>判定者はOpus 4.7自身、Anthropic API直叩きではなく <code>claude -p</code> CLI 経由で実行。同モデルが両条件を判定するため比較における対称性は維持されるが、絶対値にはバイアスがある可能性。</li>',
        '<li>判定phase 1回目は parallel=6 で並列起動した結果、Opus への並行 <code>claude -p</code> 呼び出しが間欠的に exit code 1 で失敗 (Coverage 29/40, Extras 1/40)。リトライ機構を追加して parallel=2 で再実行し 80/80 成功。判定結果自体は単独実行と差異なし。</li>',
        '<li>分類者はHaiku 4.5 ( structural / business 二択分類)。境界事例として: 「ロール階層図(SVG): オーナー>管理者>メンバー」 はSVG観察だが内容のロール名はMD原文に存在するため曖昧。50行HTMLの「業務hallucination」例8件中複数は構造観察寄りに見える境界事例。Haikuが業務側へ寄せた可能性がある。</li>',
        '<li>HTML版は trq212 / nicbstme 記事の推奨に従って <strong>1ショット変換</strong> (4並列の独立Claudeセッション) で生成。変換セッション自体のばらつきは未測定。実運用に近い設定だが、変換のサンプル数1での比較。</li>',
        '<li>題材はチャットツール1種のみ。他ドメインでは結果が異なる可能性。</li>',
        '<li>HTML側で利用したセマンティックHTML5・SVG・table・dl は trq212 + nicbstme記事の推奨に基づく。素のHTMLや別スタイルでは差が異なる可能性。</li>',
        '<li>「読みやすさ」「共有のしやすさ」「2-way interactivity」などの<em>人間側</em>の便益は本検証のスコープ外。本検証はあくまで <em>LLMエージェントの読解精度</em> のみを測る。</li>',
        '</ul>',
        '</section>',

        '<section><h2>⑦ 元記事の主張との対照</h2>',
        '<table>',
        '<thead><tr><th>元記事の主張</th><th>本検証での観察</th></tr></thead>',
        '<tbody>',
        '<tr><td>HTMLはセマンティック構造で情報密度が高い</td>'
        '<td>本検証では <strong>Coverage rate に差は出なかった</strong>。両形式とも100%。情報密度の差は読解精度に直結しない。</td></tr>',
        '<tr><td>長い文書ほどHTMLの恩恵が大きい</td>'
        '<td><strong>正しい方向性</strong>。短文ではHTMLが幻覚多く、長文では差が小さい。'
        ' ただし「HTMLが上回る」のではなく「HTMLが追いつく」。</td></tr>',
        '<tr><td>外部CSS化でトークン削減</td>'
        '<td>本検証でも採用 (生成されたHTMLは外部 styles.css 参照のみ)。インラインCSS無しで安定して変換できた。</td></tr>',
        '<tr><td>SVGでリッチに表現できる</td>'
        '<td>SVG自体は機能した。<strong>ただし副作用として、SVG関連の構造観察 (図の色、ラベル、矢印等)'
        ' が大量に幻覚扱いされる</strong>という未報告の現象が観察された。</td></tr>',
        '</tbody></table>',
        '</section>',

        '</main>',
    ]

    html = (
        '<!DOCTYPE html>'
        '<html lang="ja"><head>'
        '<meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>MD vs HTML 検証レポート</title>'
        '<style>' + CSS + '</style>'
        '</head><body>'
        + "".join(body_parts) +
        '</body></html>'
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"Wrote → {OUT}")


if __name__ == "__main__":
    main()
