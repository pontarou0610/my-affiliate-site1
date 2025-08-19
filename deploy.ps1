# PowerShell: deploy.ps1
# Hugoプロジェクトのルートで実行する

# ステップ1：Hugoで公開ビルド
hugo

# ステップ2：publicフォルダに移動
Set-Location -Path ".\public"

# ステップ3：Git操作（コミット＆プッシュ）
git add .
$datetime = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
git commit -m "Auto deploy at $datetime"
git push origin main

# ステップ4：元のディレクトリに戻る
Set-Location -Path ".."
