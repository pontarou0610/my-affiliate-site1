---
title: "Send to Kindleで縦書きEPUBの余白が崩れる原因と対策｜Calibreでの確認・修正手順"
date: 2026-11-27T12:00:00+09:00
lastmod: 2026-11-27T12:00:00+09:00
draft: false
tags: ["Kindle", "Send to Kindle", "EPUB", "Calibre", "電子書籍"]
categories: ["電子書籍"]
keywords: ["Send to Kindle 余白 おかしい", "Send to Kindle 縦書き 崩れる", "Calibre EPUB 縦書き Kindle", "Kindle EPUB 余白 対策"]
description: "Send to Kindleで自作やDRMフリーの縦書きEPUBを送った際に、上下左右の余白が不自然に広がる・レイアウトが崩れる原因と、Calibreを使った修正手順を解説します。"
slug: "send-to-kindle-vertical-epub-margin-calibre"
hasRelatedProducts: false
showRakutenWidget: false
showProductRecommendations: false
---
自分で作成した原稿や、利用権限のあるDRMフリーの日本語縦書きEPUBを「Send to Kindle」で送信した際、**「上下に不自然な大きい余白ができる」「左右のマージンが極端に詰まる」「行間や段落の空き方が意図と違う」**といった表示崩れに悩むケースがX（旧Twitter）や技術ブログでたびたび話題になります。

Send to Kindleの基本的な送信手順や容量上限（Web版は200MBまで）については[Send to Kindle Web活用ガイド](/posts/2026/10/send-to-kindle-web-guide/)で整理していますが、この記事では一歩踏み込んで、**縦書きEPUBの余白・レイアウトが崩れる原因と、電子書籍管理ソフト「Calibre（カリバー）」を使った具体的な対策手順**を解説します。

※本記事の手順は、ご自身で執筆・作成したファイルや、規約上加工・個人利用が認められているDRMフリーのEPUBファイルを対象としています。なお、Send to Kindleの変換仕様やCalibreのメニュー表記、各端末のファームウェア挙動はアップデートにより変更される場合があるため、最新の公式ヘルプもあわせてご確認ください。

## なぜSend to Kindleで縦書きEPUBの余白が崩れるのか？

Send to Kindleは、アップロードされたEPUBファイルをそのまま端末へ置くのではなく、**Amazonのサーバー側でKindle向けの内部フォーマットへ変換してから各端末へ配信する仕組み**をとっています。この変換時やKindle端末側のファームウェア更新によって、次のような現象が起こりやすくなります。

1. **縦書き宣言（`primary-writing-mode`）の認識ズレ**  
   本文のCSSにだけ `writing-mode: vertical-rl;` が書かれていて、EPUB全体の設計図にあたるOPFファイルに縦書き指定がない場合、変換器が「横書きベースの本」と誤認して余白計算をおかしくすることがあります。
2. **固定マージンや行間（`line-height`）の強制リセット**  
   EPUB内のCSSで極端に狭い行間や固定ピクセルの余白（`margin` / `padding`）が指定されていると、Kindle側のレンダリング仕様と衝突し、逆に大きな余白（いわゆるデスマージン）が入る原因になります。
3. **段落間の空行・マージン重複**  
   変換ツールの初期設定によって `<p>` タグごとに上下マージンが自動挿入され、日本語の縦書き小説では1行おきに隙間が空いたような見た目になることがあります。

## 対策1：Calibreの「本を編集」でOPFの縦書きメタデータを確認する

まず最初に確認したいのが、EPUB内部の `content.opf`（または `metadata.opf`）にある記述方向（Writing Mode）の宣言です。

※変換・編集前には必ず原本EPUBをバックアップし、送信後に実機・アプリで表示を確認してください。

### 確認・修正の手順

1. PC版の **Calibre** を起動し、対象のEPUBを選択して右クリック ＞ **「本を編集（Edit book）」** を開きます。
2. 左側のファイル一覧から **`content.opf`**（または `.opf` ファイル）をダブルクリックして開きます。
3. `<metadata>` 〜 `</metadata>` タグの中に、以下の1行が含まれているか確認します。

```xml
<meta name="primary-writing-mode" content="vertical-rl"/>
```

4. もしこの記述がない場合は `<metadata>` 内に追記し、`horizontal-lr` などになっている場合は `vertical-rl` に書き換えて保存します。
5. 保存したEPUBを改めて[Send to Kindle Web](/posts/2026/10/send-to-kindle-web-guide/)から送信し、端末やKindleアプリでの表示を確認します。

## 対策2：Calibreの「本を変換（EPUB→EPUB）」でCSSと余白を整理する

OPFの指定だけでは余白や段落の空きが直らない場合、Calibreの変換機能を使って余分なマージン指定をリセットする方法が有効です。

### 設定のポイント

1. Calibreで対象の本を選び、**「本を変換」** をクリックします。
2. 画面右上の「出力フォーマット」を **`EPUB`** に設定します（EPUBからEPUBへ再構築します）。
3. 左メニューの **「外観（Look & feel）」** を開き、以下を確認します。
   - **「レイアウト」タブ**: 「段落間のスペースを削除」にチェックを入れる（段落ごとの不自然な隙間をなくし、字下げに統一できます）。
   - **「スタイル」タブ（追加CSS）**: 本文の縦書きとマージンをシンプルに保つため、必要に応じて以下のような最小限のCSSを指定します。

```css
html, body {
  writing-mode: vertical-rl;
  -webkit-writing-mode: vertical-rl;
}
p {
  margin: 0;
  text-indent: 1em;
}
```

※行間（`line-height`）を1.1emのように極端に小さく指定すると、Kindle側の仕様で無効化・崩れの原因になりやすいため、まずは指定しないか `1.4`〜`1.6` 程度の標準的な値で試すのが安全です。

4. 左メニューの **「EPUB出力」** を開き、EPUBバージョン（EPUB 2 または EPUB 3）が元のファイル構造に合っているか確認して「OK」で変換します。

## 対策3：USB経由での転送や、EPUB直入れ対応端末との使い分け

Send to Kindle（クラウド変換）を通すとどうしても組版が変わってしまう特殊なレイアウトのEPUBや、画像中心のファイル（固定レイアウト）には、次の代替策もあります。

- **漫画・画像中心のEPUBの場合**: ページ順序や見開きが崩れるときのチェックポイントは[Calibreでマンガを整える手順](/posts/2026/03/calibretemankawozheng-eru-kindle-kobotedu-meruxing-nisuruzui/)および[Send to Kindleでマンガを送ると崩れる時の対処法](/posts/2026/03/send-to-kindletemankawosong-rutobeng-rerushi-nodui-chu-fa-yu/)にまとめています。
- **変換を通さずEPUBのまま読みたい場合**: 楽天Kobo端末（Kobo Clara BW / Clara Colour / Libra Colourなど）は、PCからUSB経由でDRMなしEPUBをそのまま入れて開くことができます。手元のEPUB資産を無変換で読む頻度が高い人は、[楽天Kobo端末・ストア活用ガイド](/lp/kobo/)や[KindleとKoboの比較記事](/posts/kindle-vs-kobo/)も参考にしてみてください。

### 対応端末の最新モデル・仕様を確認する

**PR／広告**: 以下のボタンには広告・アフィリエイトリンクが含まれます。端末の対応形式、最新仕様、価格、在庫状況は購入前に必ず各公式ストアでご確認ください。

{{< affbtn store="amazon" slot="vertical-epub-paperwhite" url="https://amzn.to/48wNGzs" text="AmazonでKindle Paperwhiteの最新モデルを見る" >}}

{{< affbtn store="rakuten" slot="vertical-epub-kobo" url="https://books.rakuten.co.jp/event/e-book/ereaders/" text="楽天Koboの電子書籍リーダー一覧を見る" >}}

## まとめ：送信前の3ステップ点検

1. 作業前に原本EPUBをバックアップし、`content.opf` に `primary-writing-mode="vertical-rl"` があるか確認する
2. 過剰な余白・極端な行間CSSを外し、段落間スペース設定を整える
3. Web版（[Send to Kindle Web](/posts/2026/10/send-to-kindle-web-guide/)）から送信し、Kindle端末側の「Aa（フォント・レイアウト設定）」で余白と文字サイズを微調整する

これからKindle端末を新しく選ぶ方や買い替えを検討している方は、[Kindle全機種の選び方ガイド](/lp/kindle/)もあわせてご覧ください。

## 関連記事

- [Send to Kindle Web活用ガイド｜ブラウザから200MBまでのEPUB・PDFを転送する手順](/posts/2026/10/send-to-kindle-web-guide/)
- [Calibreでマンガを整える｜Kindle・Koboで読める形にする最小手順](/posts/2026/03/calibretemankawozheng-eru-kindle-kobotedu-meruxing-nisuruzui/)
- [Send to Kindleでマンガを送ると崩れる時の対処法](/posts/2026/03/send-to-kindletemankawosong-rutobeng-rerushi-nodui-chu-fa-yu/)
- [Kindle全機種の選び方・読み放題ガイド](/lp/kindle/)
- [楽天Kobo端末・ストア活用ガイド](/lp/kobo/)
- [KindleとKoboはどっちがいい？PaperwhiteとClara BWを比較【2026年】](/posts/kindle-vs-kobo/)
