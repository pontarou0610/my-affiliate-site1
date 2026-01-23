# PowerShell: deploy.ps1
# Hugo プロジェクトのルートで実行してください

# 記事タイトル／スラッグの重複チェック
python .\scripts\check_unique_posts.py
if ($LASTEXITCODE -ne 0) {
    Write-Error "重複が解消されるまでデプロイを中断します。"
    exit $LASTEXITCODE
}

# Hugo で生成（古い出力の残存を防ぐ）
hugo --minify --cleanDestinationDir

# public フォルダへ移動
Set-Location -Path ".\public"

# Git 操作（コミット＆プッシュ）
git add .
$datetime = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
git commit -m "Auto deploy at $datetime"
git push origin main

# 元のディレクトリに戻る
Set-Location -Path ".."
