# MD vs HTML — LLMエージェント読解精度の検証

LLMエージェント (Claude Opus 4.7) は要件定義書を **Markdown** と **HTML** どちらで読んだ方が理解度が高いか、定量比較した実験。

## 背景

[trq212氏の記事](https://x.com/trq212/status/2052809885763747935) と [nicbstme氏の追加情報](https://x.com/nicbstme/status/2052965305148981494) で「要件定義書はMDよりHTMLで書くべき」という主張がある。本検証はその主張をエージェントの読解精度の観点から検証する。

## 結論 (要約)

| 指標 | 結果 |
|---|---|
| Coverage rate (網羅性) | MD/HTML とも 99-100%、**ほぼ拮抗** |
| 生 Hallucination rate | 50-100行HTMLで20-30%、500行で1% |
| 業務 Hallucination rate | 50行HTML 6.97% / MD 0%、500行HTML 0.33% / MD 0.07% |
| HTML側hallucinationの内訳 | 約85%は HTML/SVG/CSS の構造観察ノイズ (要件捏造ではない) |

詳細レポート: [`results/report.html`](results/report.html)

**主張への評価**: 「長文ほどHTMLが有利」は方向性として正しい。ただし「HTMLが上回る」のではなく「HTMLが追いつく」。短文ではHTMLにすると判定者が形式由来のノイズを大量検出する副作用がある。

## 実験設計

- 4種類の文書長 (50/100/250/500行) × 2形式 (MD/HTML) × 5試行 = **40試行**
- 被験者: Claude Opus 4.7
- HTML版は別Claudeセッションで MD→HTML 変換 (外部CSS + セマンティックHTML5 + SVG)
- 判定: チェックリスト含有 (Pass1) と extras裏付け (Pass2) を Opus 4.7 が判定
- 業務 vs 構造の分類: Haiku 4.5 が二分類

## ディレクトリ構成

```
docs/specs/2026-05-09-md-vs-html-design.md  # 設計仕様
source/                                      # MD原本 4本
checklists/                                  # 正解チェックリスト 4本
trials/<n>_<format>/requirements.<ext>       # 各trial dir (被験者が読む対象、隔離)
prompts/                                     # 被験者・判定者プロンプト
scripts/                                     # 実行スクリプト
results/
  explanations/                              # 40試行の説明テキスト
  judgments/coverage/                        # Pass1判定結果
  judgments/extras/                          # Pass2判定結果
  judgments/classified/                      # 業務/構造分類結果
  summary.{csv,json}                         # 集計
  summary_classified_llm.json                # 分類後集計
  report.html                                # 最終レポート
WORKLOG.md                                   # 作業ログ
```

## 再現方法

```bash
# 説明生成 (40試行、parallel=6で約7-10分)
PARALLEL=6 bash scripts/run_explain.sh 5

# 判定 (Pass1+Pass2 = 80判定、parallel=2で約30分)
python3 scripts/run_judge.py --parallel 2

# 業務hallucination分類
python3 scripts/classify_extras_llm.py

# 集計
python3 scripts/aggregate.py

# レポート生成
python3 scripts/generate_report.py
open results/report.html
```

## 制限事項

- 試行数5/条件、サンプル数小
- 判定者・分類者バイアス (Opus / Haiku)
- 題材はチャットツール1種のみ
- HTML変換は1ショット (4並列の独立Claudeセッション)
- 「読みやすさ」「共有のしやすさ」など人間側の便益はスコープ外

詳細は [`results/report.html`](results/report.html) の制限事項セクションを参照。
