#!/usr/bin/env python3
"""
results/summary.json と summary.csv から、HTMLレポートを生成する。

出力: results/report.html

レポート方針 (本検証のテーマに沿って HTML で出力):
- セマンティックHTML5 + 外部CSSは無し (シングルファイル可搬性のためインライン)
- SVGで結果を視覚化 (棒グラフでCoverage rate、ハルシネーション率を可視化)
- 表で詳細データ
- 各長さでのMD vs HTML比較を強調
- 結論セクションで主要発見を要約
"""

import csv
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
SUMMARY_JSON = RESULTS / "summary.json"
SUMMARY_CSV = RESULTS / "summary.csv"
OUT = RESULTS / "report.html"
SPEC = ROOT / "docs" / "specs" / "2026-05-09-md-vs-html-design.md"


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
.legend { display: flex; gap: 1.5rem; margin: 0.5rem 0 0; font-size: 0.9rem; }
.legend-item { display: flex; align-items: center; gap: 0.4rem; }
.legend-swatch { width: 14px; height: 14px; border-radius: 3px; }

aside.callout {
  border-left: 4px solid var(--c-accent);
  background: var(--c-surface);
  padding: 0.8rem 1rem; margin: 1rem 0; border-radius: 0 6px 6px 0;
}
aside.callout.win { border-color: var(--c-success); }
aside.callout.warn { border-color: var(--c-warn); }
"""


def fmt_pct(x, digits=1):
    if x is None:
        return "—"
    return f"{x*100:.{digits}f}%"


def fmt_num(x, digits=2):
    if x is None:
        return "—"
    return f"{x:.{digits}f}"


def render_bar_chart(summary, metric_path, title, format_value, max_value=None):
    """metric_path = ('coverage_rate', 'mean') のようなパス。
    summaryから (length, format) → value を取り、長さごとの並列バーをSVGで描画。"""
    lengths = sorted({s["length"] for s in summary})
    formats = ["md", "html"]
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
        max_value = max(vals) * 1.1 if vals else 1.0

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

    # Y軸目盛り (5本)
    for i in range(6):
        y = pad_top + plot_h - (plot_h * i / 5)
        v = max_value * i / 5
        svg.append(f'<line x1="{pad_left}" y1="{y}" x2="{width-pad_right}" y2="{y}" stroke="#e1e4e8" stroke-width="1"/>')
        svg.append(f'<text x="{pad_left-6}" y="{y+4}" text-anchor="end" font-size="11" fill="#5a5a5a">{format_value(v)}</text>')

    # バー
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
            bar_h = plot_h * (v / max_value)
            x = gx + 8 + bar_w * fi
            y = pad_top + plot_h - bar_h
            svg.append(
                f'<rect x="{x}" y="{y}" width="{bar_w}" height="{bar_h}" fill="{colors[fmt]}" rx="2" />'
            )
            # 値ラベル
            svg.append(
                f'<text x="{x+bar_w/2}" y="{y-3}" text-anchor="middle" font-size="11" fill="#1a1a1a">{format_value(v)}</text>'
            )
        # X軸ラベル
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
        '<th>Hallucination rate</th>'
        '<th>Faithful Extras (mean)</th>'
        '<th>Total Signal (mean)</th>'
        '</tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table>"
    )


def compute_diff_table(summary):
    """各長さでMD - HTML の差分を計算"""
    by_key = {(s["length"], s["format"]): s for s in summary}
    lengths = sorted({s["length"] for s in summary})

    rows = []
    for l in lengths:
        md = by_key.get((l, "md"))
        ht = by_key.get((l, "html"))
        if not md or not ht:
            continue
        cov_diff = (ht["coverage_rate"]["mean"] - md["coverage_rate"]["mean"]) if md["coverage_rate"]["mean"] is not None and ht["coverage_rate"]["mean"] is not None else None
        hallu_diff = (ht["hallucination_rate"]["mean"] - md["hallucination_rate"]["mean"]) if md["hallucination_rate"]["mean"] is not None and ht["hallucination_rate"]["mean"] is not None else None
        winner_cov = "HTML" if cov_diff and cov_diff > 0 else ("MD" if cov_diff and cov_diff < 0 else "-")
        winner_hal = "MD" if hallu_diff and hallu_diff > 0 else ("HTML" if hallu_diff and hallu_diff < 0 else "-")
        rows.append(
            f'<tr>'
            f'<td>{l}行</td>'
            f'<td class="num">{fmt_pct(md["coverage_rate"]["mean"])}</td>'
            f'<td class="num">{fmt_pct(ht["coverage_rate"]["mean"])}</td>'
            f'<td class="num">{fmt_pct(cov_diff) if cov_diff is not None else "—"}</td>'
            f'<td>{winner_cov}</td>'
            f'<td class="num">{fmt_pct(md["hallucination_rate"]["mean"]) if md["hallucination_rate"]["mean"] is not None else "—"}</td>'
            f'<td class="num">{fmt_pct(ht["hallucination_rate"]["mean"]) if ht["hallucination_rate"]["mean"] is not None else "—"}</td>'
            f'<td class="num">{fmt_pct(hallu_diff) if hallu_diff is not None else "—"}</td>'
            f'<td>{winner_hal}</td>'
            f'</tr>'
        )
    return (
        '<table><thead><tr>'
        '<th>長さ</th>'
        '<th>MD Coverage</th><th>HTML Coverage</th><th>差(HTML-MD)</th><th>Coverage勝者</th>'
        '<th>MD Hallu.</th><th>HTML Hallu.</th><th>差(HTML-MD)</th><th>幻覚少ない方</th>'
        '</tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table>"
    )


def derive_conclusion(summary):
    """全体傾向から自動で結論を組み立てる。"""
    by_key = {(s["length"], s["format"]): s for s in summary}
    lengths = sorted({s["length"] for s in summary})

    cov_diffs = []
    hallu_diffs = []
    for l in lengths:
        md = by_key.get((l, "md"))
        ht = by_key.get((l, "html"))
        if md and ht:
            if md["coverage_rate"]["mean"] is not None and ht["coverage_rate"]["mean"] is not None:
                cov_diffs.append(ht["coverage_rate"]["mean"] - md["coverage_rate"]["mean"])
            if md["hallucination_rate"]["mean"] is not None and ht["hallucination_rate"]["mean"] is not None:
                hallu_diffs.append(ht["hallucination_rate"]["mean"] - md["hallucination_rate"]["mean"])

    bullets = []
    if cov_diffs:
        avg_cov = statistics.mean(cov_diffs)
        winner = "HTML" if avg_cov > 0 else "Markdown"
        magnitude = abs(avg_cov) * 100
        bullets.append(
            f"Coverage rate: 全長さ平均で{winner}が{magnitude:.1f}ポイント勝っている (HTML-MD = {avg_cov*100:+.1f}pt)"
        )

        # スケーリング: 文書長による差分の傾向
        if len(cov_diffs) >= 2:
            short_diff = cov_diffs[0]
            long_diff = cov_diffs[-1]
            trend = "拡大" if long_diff > short_diff else "縮小"
            bullets.append(
                f"スケーリング: 短い文書 ({lengths[0]}行) では差 {short_diff*100:+.1f}pt、長い文書 ({lengths[-1]}行) では差 {long_diff*100:+.1f}pt → 差は{trend}傾向"
            )

    if hallu_diffs:
        avg_hallu = statistics.mean(hallu_diffs)
        winner = "Markdown" if avg_hallu > 0 else "HTML"
        magnitude = abs(avg_hallu) * 100
        bullets.append(
            f"Hallucination rate: 全長さ平均で{winner}が{magnitude:.1f}ポイント幻覚が少ない (HTML-MD = {avg_hallu*100:+.1f}pt)"
        )

    return bullets


def main():
    if not SUMMARY_JSON.exists():
        print(f"missing {SUMMARY_JSON}, run aggregate.py first")
        return 1

    summary = json.loads(SUMMARY_JSON.read_text(encoding="utf-8"))

    cov_chart = render_bar_chart(
        summary, ("coverage_rate", "mean"),
        "Coverage rate (mean) by 文書長 × 形式",
        lambda v: f"{v*100:.1f}%",
        max_value=1.0,
    )

    hallu_chart = render_bar_chart(
        summary, ("hallucination_rate", "mean"),
        "Hallucination rate (mean) by 文書長 × 形式",
        lambda v: f"{v*100:.2f}%",
    )

    faith_chart = render_bar_chart(
        summary, ("faithful_extras", "mean"),
        "Faithful Extras (mean) by 文書長 × 形式",
        lambda v: f"{v:.1f}",
    )

    summary_table = render_summary_table(summary)
    diff_table = compute_diff_table(summary)
    conclusion_bullets = derive_conclusion(summary)

    # メソドロジー要約
    methodology = """
    <p>本検証は「LLMエージェント (Claude Opus 4.7) は、要件定義書を Markdown と HTML のどちらで読んだ方が理解度が高いか」を定量比較する。</p>
    <ul>
      <li>4種類の文書長 (50/100/250/500行) × 2形式 (MD/HTML) × 5試行 = <strong>40試行</strong></li>
      <li>説明生成: 各 trial dir で <code>claude -p</code> をステートレス起動、Opus 4.7、Read/LS/Globのみ許可</li>
      <li>HTML版は別Claudeセッションで MD→HTML 変換 (外部CSS + セマンティックHTML5 + SVG、新規事実追加禁止)</li>
      <li>判定: チェックリスト含有 (Pass1) と extras裏付け (Pass2) を Opus 4.7 に推察禁止プロンプトで実施</li>
      <li>主指標: <strong>Coverage rate</strong> (=チェックリスト含有率) と <strong>Hallucination rate</strong></li>
    </ul>
    """

    body_parts = [
        '<header class="hero">',
        '<h1>MD vs HTML 検証レポート</h1>',
        '<p>LLMエージェントは Markdown と HTML、どちらの要件定義書をより正確に読み解くか</p>',
        '</header>',
        '<main>',
        '<section><h2>結論</h2>',
        '<aside class="callout win">',
        '<strong>主要な発見</strong>',
        '<ul>',
    ]
    for b in conclusion_bullets:
        body_parts.append(f'<li>{b}</li>')
    body_parts.append('</ul></aside>')
    body_parts.append('</section>')

    body_parts += [
        '<section><h2>メソドロジー</h2>',
        methodology,
        f'<p>詳細: <a href="../docs/specs/2026-05-09-md-vs-html-design.md">設計仕様書</a></p>',
        '</section>',

        '<section><h2>Coverage rate (主指標)</h2>',
        '<p>各試行で生成された説明テキストが、対応するチェックリストを何%カバーしたか。</p>',
        cov_chart,
        '</section>',

        '<section><h2>Hallucination rate</h2>',
        '<p>説明テキスト中の主張のうち、原文書に裏付けがないもの (推察・捏造) の割合。</p>',
        hallu_chart,
        '</section>',

        '<section><h2>Faithful Extras (副指標)</h2>',
        '<p>チェックリスト外だが原文書に裏付けある言及の数。チェックリストの取りこぼし or 細部までの理解の指標。</p>',
        faith_chart,
        '</section>',

        '<section><h2>条件別サマリー</h2>',
        summary_table,
        '</section>',

        '<section><h2>形式間の差分</h2>',
        diff_table,
        '</section>',

        '<section><h2>制限事項と留意点</h2>',
        '<ul>',
        '<li>試行数は条件あたり5回。サンプル数が小さく、統計的有意性は限定的。</li>',
        '<li>判定者はOpus 4.7自身。同モデルが両条件を判定するため比較における対称性は維持されるが、絶対値にはバイアスがある可能性。</li>',
        '<li>HTML版は1回のみの変換結果を使い回しているため、変換のばらつきは反映されない。</li>',
        '<li>題材はチャットツール1種のみ。他ドメインでは結果が異なる可能性。</li>',
        '<li>HTML側で利用したセマンティックHTML5・SVG・table・dl は trq212 + nicbstme記事の推奨に基づく。素のHTMLや別スタイルでは差が異なる可能性がある。</li>',
        '</ul>',
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
