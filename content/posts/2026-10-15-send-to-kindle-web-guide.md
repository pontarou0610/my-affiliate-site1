---
title: "Send to Kindle Web活用ガイド｜ブラウザから200MBまでのEPUB・PDFを転送する手順とエラー対処法"
date: 2026-10-15
lastmod: 2026-10-15
draft: false
tags: ['電子書籍', 'Kindle', 'EPUB', 'PDF', 'Send to Kindle']
categories: ["電子書籍"]
description: "ブラウザから直接電子書籍や資料を送れる「Send to Kindle Web」の使い方を解説。最大200MB対応のメリット、メール送信との違い、転送エラー時の対処法を公式仕様に基づいて整理します。"
slug: "send-to-kindle-web-guide"
hasRelatedProducts: false
showRakutenWidget: false
showProductRecommendations: false
robotsNoIndex: true
---

## まず結論：200MB以下のファイルをブラウザから送りたい人向け

Kindle端末やKindleアプリで手持ちのEPUBやPDFを読みたい場合、**Send to Kindle Web**（ブラウザ版）は送信方法の候補です。Amazon公式ヘルプでは、Webから1ファイル200MB以下の文書をアップロードできると案内しています（[Web版の仕様](https://digprjsurvey.amazon.co.uk/csad/help/node/G5WYD9SAF7PGXRNA)）。

メール送信は添付合計50MB以下が公式の条件です（[メール送信の仕様](https://digprjsurvey.amazon.co.uk/csad/help/node/G7NECT4B4ZWHQ8WV)）。メールの上限を超えるEPUBやPDFではWeb版を検討できます。ただし、容量内でも暗号化や文書構造によって送信・変換に失敗する場合があります。自分で作成した資料や、利用権限のあるDRMフリーのファイルを使いましょう。

この記事では、送信前の準備、ライブラリへの追加、エラーの切り分けを整理します。仕様は2026年10月15日に本文を確認できたAmazon英国公式ヘルプに基づきます。日本向け送信画面の表示や提供状況は、利用時に確認してください。

---

## Send to Kindle Webの基本仕様と対応ファイル形式

Amazon公式ヘルプで確認できる範囲を整理します。

### 基本スペック
- **アクセス先**: `https://www.amazon.co.jp/sendtokindle`（Amazonアカウントでログイン）
- **1ファイルあたりの最大容量**: **200MB**
- **利用料金**: サービスの追加料金なし。インターネット接続は別途必要です。
- **ライブラリ保存**: 「ライブラリに追加」（Add to your library）を有効にすると、同じアカウントの対応端末へダウンロードできます。

容量・料金・保存の根拠は[Amazon公式ヘルプ](https://digprjsurvey.amazon.co.uk/csad/help/node/G5WYD9SAF7PGXRNA)です。全端末での読書位置・ハイライトの同期を保証するものではありません。また、送信用のWebページと、ブラウザで本を読む「Kindle for Web」は別です。後者はパーソナル・ドキュメント非対応と案内されています（[公式対応表](https://digprjsurvey.amazon.co.uk/csad/help/node/TNtSm13k3txFI4EvDV)）。

### 対応ファイル形式一覧
以下は[公式の対応形式一覧](https://digprjsurvey.amazon.co.uk/csad/help/node/G5WYD9SAF7PGXRNA)と[公式の文書・端末別対応表](https://digprjsurvey.amazon.co.uk/csad/help/node/TNtSm13k3txFI4EvDV)に掲載されている形式です。表示や機能はファイルの内容によって異なります。

| 形式 | 拡張子 | 特徴・主な用途 |
| --- | --- | --- |
| EPUB | `.epub` | 電子書籍。変換後の文字・目次・図版を確認 |
| PDF | `.pdf` | 図表・スライド・論文など。読む端末でレイアウトを確認 |
| Microsoft Word | `.docx`, `.doc` | 文書。複雑な表などは変換後の表示を確認 |
| リッチテキスト / テキスト | `.rtf`, `.txt` | プレーンなテキスト文書、メモ |
| Webページ | `.htm`, `.html` | HTMLドキュメント |
| 画像形式 | `.png`, `.gif`, `.jpg`, `.jpeg`, `.bmp` | 画像ファイル |

古い形式の送信可否を推測せず、手元のファイルが現在の対応一覧にあるかを確認してください。拡張子だけを変更してもファイル形式の変換にはなりません。

---

## Send to Kindle Webの送信手順（3ステップ）

以下は公式ヘルプに基づく基本的な流れです。画面上の項目名や追加の案内は利用環境で確認し、送信後は読む端末で本文まで開いてください。

### ステップ1：公式サイトへアクセスしてログイン
ブラウザで[日本向けのSend to Kindleページ](https://www.amazon.co.jp/sendtokindle)を開き、利用するKindle端末・アプリと同じAmazonアカウントでサインインします。

### ステップ2：送信するファイルを追加する

ページのファイル追加操作から、200MB以下の対応ファイルを選びます。最初は1ファイルだけで試し、タイトルや内容を取り違えていないか確認しましょう。

### ステップ3：送信設定を確認して「送信」
- **ライブラリへの保存**: 後から対応端末へダウンロードしたい場合は「ライブラリに追加」（Add to your library）を有効にします（[公式案内](https://digprjsurvey.amazon.co.uk/csad/help/node/G5WYD9SAF7PGXRNA)）。
- 画面の案内に沿って送信を実行し、結果やエラー表示を確認します。エラーがある場合は、同じファイルを繰り返し送る前に原因を確認してください。

端末側をインターネットに接続し、ライブラリで文書を確認してダウンロードします。アップロード操作の完了だけで、変換や端末への配信まで完了したとは判断しないでください。所要時間は一律に保証できません。

---

## 送信ルート別の比較（Web版・メール・アプリ）

Send to Kindleには複数の送信手段が存在します。用途や利用環境に合わせて使い分けるのが合理的です。

| 項目 | Send to Kindle Web（ブラウザ版） | Send to Kindle Eメール | デスクトップアプリ（Win/Mac） |
| --- | --- | --- | --- |
| **容量条件** | 1ファイル**200MB以下** | 添付合計50MB以下、1通25ファイルまで | 利用するアプリの公式案内で要確認 |
| **準備** | ブラウザで利用、アカウントでサインイン | 送信先の確認と送信元アドレスの承認 | 対応アプリが必要 |
| **送信方法** | Webページからファイルを追加 | ファイルを添付してメール送信 | Mac / Windows用アプリから送信 |
| **検討する場面** | メールの添付上限を超える文書 | 普段のメール環境から送りたい場合 | すでに対応アプリを使っている場合 |

比較の根拠は[Web・アプリ送信の公式概要](https://digprjsurvey.amazon.co.uk/csad/help/node/G5WYD9SAF7PGXRNA)と[メール条件](https://digprjsurvey.amazon.co.uk/csad/help/node/G7NECT4B4ZWHQ8WV)です。メールサービス側の容量上限も確認しましょう。デスクトップ版の上限をWeb版と同じとは扱わず、使う環境の案内を確認してください。

---

## 転送が失敗する・端末に届かないときの確認ポイント

送信ボタンを押したにもかかわらずエラーになる場合や、端末側で一向に受信できない場合は、以下の順序で原因を切り分けます。

### 1. ファイル容量と拡張子を確認する
- ファイルサイズが200MBを超えていないか確認します。
- 拡張子が対応形式（`.epub`, `.pdf`等）になっているか確認します。
- パスワード保護・暗号化されたファイルには対応していません。DRM保護のある他社ストアの本も送信用ファイルとして扱わず、購入元が案内する閲覧方法を確認してください。

対応形式や暗号化のエラーは、[公式エラー一覧のE001・E004](https://digprjsurvey.amazon.co.uk/csad/help/node/T48rsVm3gY7KeGkKUk)を参照してください。

### 2. 表示されたエラーコードを確認する

[Amazon公式のエラー別手順](https://digprjsurvey.amazon.co.uk/csad/help/node/T48rsVm3gY7KeGkKUk)に照らして確認します。

- **E005**: PDFの破損・暗号化を確認し、元のファイルがPCのPDF閲覧アプリで開けるか試します。
- **E013 / E016**: 複雑な表や数式など、変換に適さない要素がないか確認します。元のレイアウトで届いても、文字サイズを調整できない場合があります。
- **E999 / メンテナンス表示**: 時間を置いてから再試行します。

元文書を直す場合は、編集する権限のあるファイルのコピーで作業してください。ファイル名だけを原因と決めつけないようにしましょう。

### 3. 端末の同期とWi-Fi接続状態を確認する
- 端末がインターネットに接続できているか確認します。メール送信でも、公式ヘルプは受信端末の接続を求めています（[メール送信ヘルプ](https://digprjsurvey.amazon.co.uk/csad/help/node/G7NECT4B4ZWHQ8WV)）。
- Web版で「ライブラリに追加」を有効にしたか、同じAmazonアカウントを利用しているか確認します。
- 文書がライブラリに表示されても、読む端末へのダウンロードと本文の表示まで確認します。オフラインで読む予定なら、通信を切って開けるかも事前に試しましょう。

---

## 関連記事

- **通勤時間での読書設定**:
  Send to Kindleで送ったEPUBを移動中に快適に読むための設定やデバイス選びは、[通勤向けEPUB実践チェックリスト](/posts/2026/02/kindleteepubwokuai-shi-nidu-mutamenochietsukurisuto-tong-qin/)で詳しく解説しています。
- **マンガの余白・向きなどの調整**:
  ファイルが届いても表示が崩れる場合は、[Send to Kindleでマンガが崩れるときの対処法](/posts/2026/03/send-to-kindletemankawosong-rutobeng-rerushi-nodui-chu-fa-yu/)へ進んでください。本記事はWebから送る準備とエラー確認に絞っています。
- **端末選び**:
  読む端末から検討する場合は、[KindleとKoboの比較](/posts/kindle-vs-kobo/)を参考にしてください。送信するためだけに専用端末を購入する前に、手持ちの対応アプリで文書を確認する方法もあります。

---

## 出典・一次資料

以下のAmazon英国公式ヘルプ本文を2026年10月15日に確認しました。日本向けのログイン後画面や、実ファイルの送信結果を検証した体験記事ではありません。

- [Send to Kindleの概要・Web容量・対応形式](https://digprjsurvey.amazon.co.uk/csad/help/node/G5WYD9SAF7PGXRNA)
- [メール送信の条件](https://digprjsurvey.amazon.co.uk/csad/help/node/G7NECT4B4ZWHQ8WV)
- [送信エラーと対処手順](https://digprjsurvey.amazon.co.uk/csad/help/node/T48rsVm3gY7KeGkKUk)
- [文書・端末別のメモ対応](https://digprjsurvey.amazon.co.uk/csad/help/node/TNtSm13k3txFI4EvDV)
