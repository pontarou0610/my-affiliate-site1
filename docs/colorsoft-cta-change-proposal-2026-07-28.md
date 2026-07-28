# Colorsoft CTA改善 承認資料 2026-07-28

## 状態

- 状態: CEO承認待ち
- 本番変更: 未実施
- 対象: `content/posts/2026-02-08-1-the-kindle-scribe-colorsoft-is-a-pricey-but-pretty-e-ink-col.md`
- 目的: 冒頭の3択を明確にし、既存CTAのクリック意図をそろえる

## 確認済みの事実

- 直近28日: 商用PV 10、アフィリエイトクリック 0
- Colorsoftと通常Scribeのリンク先は、Amazon公式発表に記載された製品URLと一致する。
- 既存CTAには `PR`、`nofollow sponsored noopener noreferrer`、固有の `affiliate_slot` がある。
- `affiliate_click` は `affiliate_slot`、`link_text`、`link_url` を送信する。

## 未確認事項

- A8の2026-06-30から2026-07-27の同一期間実績
- Paperwhite短縮URLの現在の製品表示。リダイレクト先ASINは確認済みだが、Amazonの自動取得が503となり商品画面は未確認。

## 提案する変更

リンク先、ボタン数、配置、`affiliate_slot` は変更しない。

| 項目 | 現在 | 提案 |
|---|---|---|
| 見出し | 購入前に、Colorsoft・通常Scribe・Paperwhiteを比較 | 購入前に、用途別の3択を公式ページで確認 |
| 説明 | 高価格帯の端末です。カラー手書きやPDF注釈が必要か、通常ScribeやPaperwhiteで足りるかを公式ページで確認してから選ぶと失敗しにくくなります。 | カラー手書き・PDF注釈ならColorsoft、手書き中心なら通常Scribe、読書中心ならPaperwhiteが候補です。価格や仕様は公式ページで確認して選びましょう。 |
| Colorsoftボタン | Colorsoftの価格を見る | Colorsoftの価格・在庫を確認 |
| 通常Scribeボタン | 通常Scribeと比較 | 通常Scribeの価格・スペックを見る |
| Paperwhiteボタン | Paperwhiteで足りるか見る | Paperwhiteを見る（短縮URLの表示確認後に再検討） |

## 5人レビュー

- SEO: 3択の判断基準を見出し・説明・ボタンで一致させる案に賛成。
- アフィリエイト規約: PRと属性は維持。リンク先と文言の一致を公開前に確認。
- UX: 3CTAを維持し、曖昧な「比較」「足りるか」を具体化する。
- Analytics: `affiliate_slot` は維持される。`link_text` を利用する分析がある場合は変更後の分類に注意。
- Audit: Paperwhiteリンクの実表示確認とCEO承認が終わるまで公開保留。

## 影響範囲と復旧方法

- 影響範囲: 対象記事のCTA文言のみ。アフィリエイトURL、HTML属性、レイアウト、他記事は変更しない。
- 検証: Hugoビルド、アフィリエイトHTML検査、GA4 DebugViewで3スロットの `affiliate_click` を確認する。
- 復旧: 対象コミットを `git revert` し、通常のGitHub Pagesデプロイで直前文言へ戻す。

## 公開ゲート

1. CEOがこの提案を承認する。
2. Paperwhiteリンクの表示内容を確認する。
3. 新しい実験IDを発行する。
4. ローカル検証を通し、影響範囲と復旧方法を再確認する。
5. CEOが本番反映を承認する。
