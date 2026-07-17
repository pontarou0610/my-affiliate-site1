# GitHub Pages CSS表示崩れ（2026-07-17）

## 結果

2026-07-17 09:39 JST、GitHub Actionsの `Deploy (Hugo)` を
`codex/post-generation-quality-gates` のコミット `cf09517a` から再実行し、表示を復旧した。

- デプロイ実行: `29545290721`
- 復旧後の `gh-pages`: `3ca7847970fd0c3b9f752022762b493de90caac6`
- 公開CSSの期待SRI: `sha256-4gDYeELQT430Spc8s3zfcL7hdmrZnQIwym8x/R7nV4E=`
- 公開CSSの実測SRI: `sha256-4gDYeELQT430Spc8s3zfcL7hdmrZnQIwym8x/R7nV4E=`
- 判定: 一致、復旧確認済み

## 原因

2026-07-15の `gh-pages` コミット `b21afbff` はWindows環境から作成されていた。
HugoがHTMLへ記録したCSSのSRIハッシュはCRLFの生成物を基準にしていたが、
Gitへの追加時にCSSがLFへ変換されたため、公開CSSの実体とSRIが不一致になった。
ブラウザは整合性検査に失敗したCSSを読み込まず、ページが未装飾で表示された。

## 5人専門家レビュー

1. Hugo担当: 記事・テーマの変更は不要。同一環境でHTMLとCSSを再生成するのが最小修正。
2. CI/CD担当: 公開処理はLinux上のGitHub Actionsへ一本化し、ローカル生成物を直接公開しない。
3. セキュリティ担当: SRIを削除して回避せず、公開後に期待値と実測値の一致を検証する。
4. SEO担当: URL・本文・メタ情報を変更しない再デプロイなので、検索資産への影響を最小化できる。
5. 収益導線担当: CTAやアフィリエイトリンクは変更せず、表示復旧を最優先する。

## 再発防止

`deploy.ps1` はローカルの `public` をGitへ直接追加する処理を廃止し、以下を行う。

1. 作業ツリーがクリーンで、ローカルHEADとリモートブランチが一致していることを確認する。
2. GitHub Actionsの `deploy.yml` を対象ブランチから起動する。
3. ワークフローの完了を監視する。
4. 公開HTMLに記録されたCSSのSRIと、公開CSSの実測SHA-256を照合する。

## 復旧方法

公開後の検証に失敗した場合は、公開を成功させた直前のソースコミットを指定して
`Deploy (Hugo)` を再実行する。`gh-pages` へWindows生成物を直接pushしない。
