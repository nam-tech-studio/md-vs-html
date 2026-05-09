# MD vs HTML: エージェント理解度比較検証 設計

## 背景と目的

要件定義書を **Markdown** で書くべきか **HTML** で書くべきか、SNS上で議論がある。
本検証はLLMエージェント (Claude Opus 4.7) が同一内容の要件定義書を両形式で読んだとき、
どちらが理解度・網羅性が高いかを定量比較する。

## 仮説

- H1: HTMLのセマンティックタグ・階層構造のおかげで、文書が長くなるほどHTMLの方がCoverage rateが高くなる
- H2: 形式によってHallucination(幻覚)率に差が出る
- 帰無: 形式間で有意差はない

## 実験条件

| 因子 | 水準 |
|---|---|
| 文書長 | 50行 / 100行 / 250行 / 500行 (MD原本基準) |
| 形式 | Markdown / HTML |
| 試行数 | 各条件 5回 |
| 被験者モデル | Claude Opus 4.7 (`claude-opus-4-7`) |
| 判定者モデル | Claude Opus 4.7 (推察禁止プロンプト) |

合計 4 × 2 × 5 = **40試行**

## 公平性の担保

1. **HTML版は別Claudeセッションで MD→HTML 変換** して作成
   - 同一プロンプトで4本変換、変換ログも保存
   - 変換時はセマンティックタグ・data属性・階層構造を活かすよう指示
2. **被験者セッションは試行ごとに完全分離**
   - 各試行ディレクトリ (`trials/<length>_<format>/`) には `requirements.{md,html}` の1ファイルのみ
   - `claude -p` をsubprocessで起動、ステートレス実行
3. **説明生成プロンプトは両形式で完全同一**
4. **判定者は同モデル (Opus 4.7)**
   - 同モデルバイアスは両条件で対称に効くため、比較において相殺される
   - 「推察・補完禁止、明示的言及のみYES」と強く制約

## ディレクトリ構成

```
md-vs-html/
  docs/specs/
    2026-05-09-md-vs-html-design.md
  source/                          # MD原本(被験者からは隔離)
    50.md / 100.md / 250.md / 500.md
    convert_log/                   # MD→HTML変換セッションのログ
  trials/                          # 被験者が見るディレクトリ群
    50_md/requirements.md
    50_html/requirements.html
    100_md/requirements.md
    100_html/requirements.html
    250_md/requirements.md
    250_html/requirements.html
    500_md/requirements.md
    500_html/requirements.html
  checklists/
    50.json / 100.json / 250.json / 500.json
  prompts/
    explain.txt                    # 説明生成プロンプト
    judge_coverage.txt             # Pass1: チェックリスト含有判定
    judge_extras_extract.txt       # Pass2a: claim抽出
    judge_extras_classify.txt      # Pass2b: claim分類
    convert.txt                    # MD→HTML変換プロンプト
  scripts/
    convert.sh                     # MD→HTML変換実行
    run_explain.sh                 # 説明生成 (claude CLI × 40)
    run_judge.py                   # 判定 (Opus API × 2パス)
    aggregate.py                   # 集計
    generate_report.py             # HTMLレポート生成
  results/
    explanations/<length>_<format>_<trial>.md
    judgments/
      coverage/<length>_<format>_<trial>.json
      extras/<length>_<format>_<trial>.json
    summary.csv
    report.html                    # 最終レポート(HTML)
```

## チェックリスト形式

```json
[
  {"id": 1, "text": "ユーザーは2段階認証を有効化できる"},
  {"id": 2, "text": "セッションタイムアウトは15分"},
  ...
]
```

## 説明生成プロンプト (両形式で完全同一)

```
このディレクトリにある要件定義書を読み、内容を一つも漏らさず徹底的に説明してください。
すべての要件、制約、決定事項、機能、非機能、用語、ビジネスルール、エッジケースを列挙してください。
```

## 実行コマンド (1試行)

```bash
cd trials/50_md
claude -p "$(cat ../../prompts/explain.txt)" \
  --model claude-opus-4-7 \
  --allowedTools "Read,LS,Glob" \
  --permission-mode acceptEdits \
  > ../../results/explanations/50_md_trial1.md
```

## 判定パイプライン

### Pass 1 — Coverage判定

各 (説明テキスト, チェックリスト項目) ペアについて:

```
あなたは厳密な事実判定者です。推察・補完・行間読みは禁止。
以下の説明テキストに、この要件項目が「明示的に言及されている」場合のみYES。
言い換え(同義語・パラフレーズ)は許容するが、新規追加・推測されたものはNO。

[説明テキスト]
...

[要件項目]
...

出力: {"covered": true|false, "evidence": "<該当箇所の引用 or null>"}
```

### Pass 2 — Extra抽出 & 裏付け判定

**2a. claim抽出**: 説明テキストから個別主張を列挙

```
出力: [{"id": 1, "claim": "..."}, ...]
```

**2b. 各claimの分類**:

```
出力: {
  "matches_checklist_id": int|null,
  "supported_by_source": bool,
  "evidence_in_source": "<原文書の引用 or null>"
}
```

## 集計指標 (各 length × format 条件で40試行平均±SD)

| 指標 | 定義 | 解釈 |
|---|---|---|
| Coverage rate | A / |checklist| | 期待要件の網羅度 (主指標) |
| Faithful extras | B (件数) | チェックリスト外で原文書に裏付けあり |
| Hallucination rate | C / (A+B+C) | 幻覚・捏造率 |
| Total signal | A+B | 理解できた事実の総量 |

A=Covered, B=Faithful Extra, C=Hallucination

## 結果レポートが答える問い

1. MD vs HTML で **Coverage rate** に差はあるか？(主目的)
2. MD vs HTML で **Hallucination率** に差はあるか？(副次)
3. 文書長(50→500行)が増えるとき、形式間の差は拡大するか縮小するか？(スケーリング)
4. 結論: どちらの形式を要件定義書に推奨するか

## 進め方 (実装順)

1. 要件定義書 (MD) とチェックリストをユーザーと協働で4長さ分作成
2. MD→HTML変換 (別Claudeセッション×4)
3. スクリプト実装 (`run_explain.sh`, `run_judge.py`, `aggregate.py`, `generate_report.py`)
4. 40試行 + 判定実行
5. 集計 → HTMLレポート生成

## コスト見積もり (概算)

- 説明生成: 40試行 × Opus (入力5K + 出力3K) ≈ $12
- 判定: 40 × (チェック項目数 + claim数) × Opus ≈ $10-30
- 合計 **$25-50** 規模
