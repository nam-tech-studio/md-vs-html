# 作業ログ

このファイルは検証実験の作業ログ。失敗・成功・判断・観察を時系列で記録する。
ユーザーが寝てる間の自走作業の透明性確保が目的。

## 2026-05-10 (前作業)

- 設計合意: docs/specs/2026-05-09-md-vs-html-design.md
- 4長さ分の要件定義書 (50/100/250/500行) と対応checklist完成 → コミット済
- HTML変換方針: trq212 + nicbstme記事に従い、外部CSS + セマンティックHTML5 + SVG許容

## 2026-05-10 自走開始

### 環境確認

- ANTHROPIC_API_KEY: 未設定
- claude CLI: 2.1.138 利用可能
- → **判定もAnthropic API直叩きから `claude -p` に変更**。被験者と判定者が同じCLI経由になるが、モデルは両方Opus 4.7なので比較設計は維持される。

### 作業計画

1. styles.css template作成 (済)
2. HTML変換プロンプト作成
3. サブエージェント4並列で MD→HTML 変換
4. 変換結果のサニティチェック
5. プロンプト群 (explain/judge_coverage/judge_extras) 作成
6. scripts (run_explain.sh / run_judge.py / aggregate.py / generate_report.py) 実装
7. 説明生成 40試行
8. Coverage判定 + Extras判定
9. 集計
10. HTMLレポート生成
11. サブエージェントにレポートをレビューさせる
12. コミット&プッシュ

### コスト見積もり改訂

`claude -p` 経由なので Opus 4.7 のCLI経由レート (Pro plan利用)。トークン課金は走らない。

### MD→HTML変換 (4並列サブエージェント)

完了 (各エージェント独立セッション)。

- 50.html : 142行  (table x2, dl x1, svg x1: ユーザー↔WS↔サブドメイン)
- 100.html: 248行  (table x6, dl x3, svg x1: プレゼンス遷移)
- 250.html: 422行  (table x4, dl x2, svg x2: プレゼンス + ロール階層)
- 500.html: 762行  (table x5, dl x9, svg x2: ロール階層 + ワークフロー)

すべて外部CSS参照、インラインstyle無し。各エージェントが「事実追加なし」を自己申告。

### スクリプト群

- prompts/explain.txt - 説明生成プロンプト (両形式同一)
- prompts/judge_coverage.txt - Pass1: チェックリスト含有判定
- prompts/judge_extras.txt - Pass2: extras抽出&裏付け
- scripts/run_explain.sh - claude CLI subprocess 並列実行 (各 trial dir で cd → claude -p)
- scripts/run_judge.py - Python orchestrator (Pass1+Pass2を ThreadPoolExecutor で並列化)
- scripts/aggregate.py - results を CSV/JSON にまとめる
- scripts/generate_report.py - HTML レポート生成 (SVG棒グラフ込み)

### Explain phase 起動

PARALLEL=6 で 40試行を並列実行。

### Explain phase 完了

**全40試行成功、失敗ゼロ**。所要時間 (各試行):

| 長さ | MD       | HTML      |
|---|---|---|
| 50  | 30s     | 38-53s    |
| 100 | 35-50s  | 50-80s    |
| 250 | 80-130s | 100-330s  |
| 500 | 207-220s | 205-637s |

500_html_trial4 の637sは外れ値 (恐らくレートリミット待ち)。出力行数も MD/HTML 両方とも400-470行台で揃う。

### Judge phase 起動

Pass1 (15s, coverage判定) と Pass2 (9s, extras判定) の単独テストで動作確認。

Pass1単独テスト結果 (50_md_trial1): covered=41/41 (完全カバー)
Pass2単独テスト結果 (50_md_trial1): faithful=3 hallu=0

40試行 × 2パス = 80判定を PARALLEL=6 で実行中。

### Judge phase 1回目: 部分的失敗

PARALLEL=6 で並列実行した結果、Opus 4.7 への並行 `claude -p` 起動が間欠的にレートリミットor競合で exit code 1。
- Coverage判定: 29/40 成功、11/40 (主に250以降) 失敗
- Extras判定: 1/40 成功、39/40 失敗

エラー出力は空 (stderr blank)、stdout空。`claude exited 1` のみ。
単独実行は問題なく成功 → 並列度の問題と判定。

### 対策 → Judge phase 2回目

`run_judge.py` に retry 機構 (3回まで、2-6秒バックオフ) を追加。
PARALLEL=2 で再実行 → **80/80 すべて成功**。

### 結果概要 (生指標)

| 長さ | Coverage MD | Coverage HTML | Hallucination MD | Hallucination HTML |
|---|---|---|---|---|
| 50  | 100.0% | 100.0% | 0.9%  | **33.5%** |
| 100 | 100.0% | 100.0% | 0.0%  | **23.7%** |
| 250 | 100.0% | 100.0% | 0.0%  | 2.4% |
| 500 |  99.9% | 100.0% | 0.1%  | 1.0% |

→ **CoverageはMD/HTMLほぼ拮抗、しかしHallucination率はHTMLが一貫して高い**。

### Hallucination内訳調査

HTML側のhallucination内容を確認すると、大半が「HTML/SVG/CSS構造の観察」:
- `<html lang="ja">`, viewport, charset, data-category 属性値の列挙
- SVG図のキャプション、配色、矢印ラベル、要素名
- 表構造、定義リスト構造
- `requirements.html` のファイル名、外部 styles.css 参照

これらは原文MDに存在しないため判定者は正しく「裏付けなし」と判定するが、
実際のビジネス要件 (新機能・新数値) を捏造したものではない。

### 業務hallucination分類 (Haiku 4.5)

scripts/classify_extras_llm.py で各 hallucination claim を structural/business に分類:

| 長さ | 形式 | 構造メタ平均 | 業務hallu平均 | 業務hallu率 |
|---|---|---|---|---|
| 50  | HTML | 18.2 | 3.4 | **6.97%** |
| 50  | MD   | 0.4  | 0.0 | 0.00% |
| 100 | HTML | 20.2 | 2.2 | 2.97% |
| 100 | MD   | 0.0  | 0.0 | 0.00% |
| 250 | HTML | 2.2  | 1.8 | 1.10% |
| 250 | MD   | 0.0  | 0.0 | 0.00% |
| 500 | HTML | 2.2  | 1.0 | 0.33% |
| 500 | MD   | 0.2  | 0.2 | 0.07% |

### レポート生成

scripts/generate_report.py で結果を統合した HTML レポート (results/report.html) を生成。
SVG棒グラフ x3、サマリー表 x2、差分表、業務hallucination例 (折りたたみ)、元記事との対照表。

