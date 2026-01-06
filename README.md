# my-affiliate-site1

Hugo（PaperMod）で生成して GitHub Pages にデプロイしているサイト用リポジトリです。

## X（旧Twitter）自動投稿（記事要約）

`content/` 配下のMarkdownから「最新の未投稿記事」を1件選び、要約＋URLを X API v2（`POST /2/tweets`）で自動投稿します。  
既定は安全のため `DRY_RUN=1`（投稿せずログ出力）です。

- 実装：`tools/autopost.py`（ルールベース要約、外部LLM/有料要約APIは不使用）
- 冪等性：`.autopost/state.json` で投稿済みを管理（投稿成功時のみ更新）
- URL：Actions 内で `hugo --minify` して生成されたHTMLから canonical を抽出（不可ならフォールバック）

詳細は `docs/requirements.md` / `docs/design.md` を参照してください。

### 対象記事
- デフォルト：`content/posts/**/*.md`
- 除外：`draft: true`
- “最新”判定：`front matter` の `date`（優先）→ ファイル更新日時（代替）

対象を変更したい場合は、環境変数 `AUTOPOST_CONTENT_GLOBS`（カンマ区切り）で上書きできます。

### ハッシュタグ
デフォルトは空です。付けたい場合は `AUTOPOST_HASHTAGS`（カンマ区切り）または `tools/config.py` を編集します。

### セットアップ（GitHub Actions Secrets）
GitHub Actions Secrets に以下を登録してください。
- `X_API_KEY`
- `X_API_KEY_SECRET`
- `X_ACCESS_TOKEN`
- `X_ACCESS_TOKEN_SECRET`

X側（Developer Portal / App設定）の目安：
- 権限：Read and write
- 認証方式：OAuth 1.0a User Context（User Access Tokens）

### 実行方法（DRY_RUN → 本番）
1) `Actions` → `X Autopost` → `Run workflow` で `dry_run=1` を実行  
   - 選定記事・要約・URL・投稿本文がログに出ます（投稿はしません）
2) Secrets が揃っていることを確認
3) 本番に切替
   - 手動実行：`dry_run=0` で `Run workflow`
   - 定期実行：`.github/workflows/x-autopost.yml` の `DRY_RUN` を `0` に変更（または行を削除）

誤設定検知を強めたい場合は `force_post=1`（または `FORCE_POST=1`）にします。Secrets不足時にエラーになります。

### スケジュール（JST）
`.github/workflows/x-autopost.yml` は以下のJST時刻を想定しています（cronはUTC）。
- JST 07:00（UTC 22:00）
- JST 12:00（UTC 03:00）
- JST 19:00（UTC 10:00）

### トラブルシュート
- `401/403`：App権限（Read and write）、Access Token の発行方式（OAuth 1.0a User Context）を確認
- `429`：短時間連投や上限。時間を空けて再実行
- URL が想定と違う：`hugo.toml` の `baseURL` と `permalinks`、生成HTMLの canonical を確認
- 投稿されない：`DRY_RUN` が `1` のまま／Secrets不足（`FORCE_POST=1` で検知可能）
- `draft: true`：投稿対象から除外
- 280文字超過：要約を優先して短縮（`tools/compose_tweet.py`）
