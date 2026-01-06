# Hugo記事要約のX自動投稿：要件定義

## 目的
- HugoのMarkdown記事から要約を生成し、X（旧Twitter）へ自動投稿する。
- GitHub Actions の `schedule`（cron）で完全自動運用できるようにする。
- 同じ記事を複数回投稿しない（冪等性）。

## 範囲
- 対象：`content/` 配下のMarkdownのうち、デフォルトは `content/posts/**/*.md`（ブログ記事）を対象とする。
  - `draft: true` は除外する。
  - “最新”判定は `front matter` の `date` を優先し、なければファイル更新日時を使用する。
- 1回の実行で最大1件だけ投稿する。
- URL は `hugo` ビルド後に `public/` に生成されたHTMLから `canonical` を抽出して取得する（取得不能時はフォールバック）。

## 制約
- 有料要約API/外部LLMは禁止。
  - 要約はローカルのルールベース抽出要約で実装する。
- 投稿API：X API v2 の `POST /2/tweets` を使用する。
- 認証：OAuth 1.0a User Context。
- 依存は最小限にし、Pythonライブラリは `requests` と `requests-oauthlib` を基本とする。

## 運用前提（GitHub Actions Secrets）
以下を GitHub Actions Secrets に登録し、実装では環境変数として受け取る。
- `X_API_KEY`
- `X_API_KEY_SECRET`
- `X_ACCESS_TOKEN`
- `X_ACCESS_TOKEN_SECRET`

## モード設計（安全優先）
- `DRY_RUN=1`：投稿せず、選定記事・要約・URL・投稿本文をログ出力して正常終了する。
- 本番（`DRY_RUN` 未指定/0）：Secrets が揃っている場合のみ投稿する。
- `FORCE_POST=1`：本番モードで Secrets が不足している場合は明示エラーにする（誤設定検知）。

## 受け入れ条件（Done）
- `workflow_dispatch` で `DRY_RUN=1` が成功し、生成内容がログに出る。
- 本番実行で投稿でき、投稿後 `state.json` が更新され、次回同じ記事は再投稿しない。
- `draft: true` の記事は除外される。
- `canonical` URL が取れる時はそれを使い、取れない時はフォールバックが機能する。

