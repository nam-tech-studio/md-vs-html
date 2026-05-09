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

PARALLEL=6 で 40試行を並列実行中。1試行のテストで33秒だったので、6並列なら 40/6 ≈ 7バッチ × 30-60s = 4-7分の見積もり。

