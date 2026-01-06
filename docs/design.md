# Hugo記事要約のX自動投稿：設計

## 全体像（構成図）

```
GitHub Actions (schedule / workflow_dispatch)
  ├─ checkout (+ submodules)
  ├─ install hugo / python deps
  ├─ tools/autopost.py
  │    ├─ select_article.py        (対象選定)
  │    ├─ extract_summary.py       (抽出要約)
  │    ├─ build_site.py            (hugo build -> public/)
  │    ├─ get_canonical_url.py     (public/*.html から canonical 抽出)
  │    ├─ compose_tweet.py         (280文字調整)
  │    └─ post_to_x.py             (X API v2 POST /2/tweets)
  └─ (投稿成功時のみ) state.json を commit & push
```

## データフロー
1) `content/posts/**/*.md` から候補記事を収集  
2) `draft: true` を除外し、`date`（優先）/mtime（代替）で最新未投稿を1件選定  
3) Front matter を除去し、Markdown をプレーンテキスト化して最初の自然文段落を抽出  
4) `hugo --minify` を実行し `public/` を生成  
5) 対象記事に対応する生成HTMLを推定し、`<link rel=canonical ...>` を抽出  
6) `{summary}\n{url}\n{hashtags}` 形式で投稿文を組み立て（280文字に収まるよう要約を優先短縮）  
7) `DRY_RUN=1` なら投稿せずログ出力して終了  
8) 本番なら X API v2 に投稿し、成功時のみ `state.json` を更新

## 記事選定
- 対象：デフォルトは `content/posts/**/*.md`（設定で変更可能）
- 除外：`draft: true`
- “最新”判定：
  - `front matter` の `date` があればそれを使用（ISO 8601/日付形式を許容）
  - なければファイル更新日時（mtime）

## 要約（ルールベース抽出）
- Front matter を除去する。
- 以下を可能な範囲で除外/整形して、本文のプレーンテキストを生成する：
  - コードブロック、引用、箇条書き、URL羅列、見出し
  - Markdownリンク/画像記法（テキスト側を優先）
- 本文の最初の自然文段落を抽出し、概ね 120〜160 文字に整形する。
  - `。！？` 等で2文程度に収める。

## URL生成（確実性優先）
- Actions 内で `hugo --minify` を実行して `public/` を生成する。
- 原則：生成HTMLから canonical URL を抽出して採用する。
- 生成HTML推定：
  - `url` / `slug` / `date` / `permalinks` 設定を元に、出力先HTML候補を作る。
  - 見つからない場合は `public/` を探索して canonical を拾う。
- canonical取得不能時：
  - `baseURL + 推定パス` でフォールバックする。

## 冪等性（重複投稿防止）
- `.autopost/state.json` に投稿済み識別子（filepath hash）、投稿日時、投稿ID を保存する。
- 投稿成功時のみ state を更新する（失敗時は更新しない）。
- GitHub Actions では state 更新が発生した場合のみ commit & push する。

## 失敗時挙動
- 対象記事がない（全て投稿済み/候補なし）：正常終了（no-op）。
- 本番モードで Secrets 不足：
  - `FORCE_POST=1` ならエラー終了（誤設定検知）。
  - それ以外は安全のため投稿せず、ログ出力して正常終了する。
- X API エラー（401/403/429/5xx 等）：投稿せずエラー終了、state は更新しない。
- Hugo build / canonical 抽出失敗：フォールバックURLで継続（可能な範囲）。

## モードと設定
- 既定：workflow 側の `DRY_RUN=1` で安全に導入できるようにする。
- 切替：workflow の `DRY_RUN` を外し、Secrets を登録して本番運用する。
- ハッシュタグ：`tools/config.py` で管理（デフォルト空）。

