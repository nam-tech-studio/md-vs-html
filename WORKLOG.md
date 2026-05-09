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

