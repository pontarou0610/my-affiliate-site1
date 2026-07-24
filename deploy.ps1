# PowerShell: deploy.ps1
# GitHub Actions builds and deploys the site on Linux to keep fingerprinted assets byte-stable.

[CmdletBinding()]
param(
    [int]$VerificationAttempts = 12,
    [int]$VerificationIntervalSeconds = 5
)

$ErrorActionPreference = "Stop"
$repository = "pontarou0610/my-affiliate-site1"
$siteUrl = "https://pontarou0610.github.io/my-affiliate-site1/"

Set-Location -LiteralPath $PSScriptRoot

foreach ($command in @("git", "gh", "curl.exe")) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "$command is required but was not found in PATH."
    }
}

$workingTree = git status --porcelain
if ($LASTEXITCODE -ne 0) {
    throw "Failed to inspect the Git working tree."
}
if ($workingTree) {
    throw "The working tree is not clean. Commit or stash changes before deployment."
}

$branch = (git branch --show-current).Trim()
if (-not $branch) {
    throw "Deployment requires a checked-out branch."
}

git fetch origin $branch
if ($LASTEXITCODE -ne 0) {
    throw "Failed to fetch origin/$branch."
}

$localCommit = (git rev-parse HEAD).Trim()
$remoteCommit = (git rev-parse "origin/$branch").Trim()
if ($localCommit -ne $remoteCommit) {
    throw "Local HEAD and origin/$branch differ. Push the intended commit before deployment."
}

gh auth status | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "GitHub CLI authentication is required."
}

$workflowOutput = gh workflow run deploy.yml --repo $repository --ref $branch
if ($LASTEXITCODE -ne 0) {
    throw "Failed to start the Hugo deployment workflow."
}

$runUrl = ($workflowOutput | Select-Object -Last 1).Trim()
if ($runUrl -notmatch '/actions/runs/(?<runId>\d+)$') {
    throw "The deployment workflow started, but its run ID could not be determined."
}

$runId = $Matches.runId
Write-Host "Deployment workflow: $runUrl"
gh run watch $runId --repo $repository --exit-status
if ($LASTEXITCODE -ne 0) {
    throw "The Hugo deployment workflow failed."
}

for ($attempt = 1; $attempt -le $VerificationAttempts; $attempt++) {
    $cacheBuster = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    $indexPath = Join-Path ([IO.Path]::GetTempPath()) "my-affiliate-site1-live-$cacheBuster.html"
    & curl.exe -fsSL --retry 3 --connect-timeout 15 -H "Cache-Control: no-cache" `
        "$siteUrl`?verify=$cacheBuster" -o $indexPath
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to fetch the live site for deployment verification."
    }
    $indexContent = [IO.File]::ReadAllText($indexPath)
    Remove-Item -LiteralPath $indexPath -Force
    $assetMatch = [regex]::Match(
        $indexContent,
        'href=(?:"|)(?<url>https://[^ >"]+/assets/css/stylesheet\.[a-f0-9]+\.css)(?:"|)[^>]*integrity="(?<sri>sha256-[^"]+)"'
    )

    if ($assetMatch.Success) {
        $cssUrl = $assetMatch.Groups["url"].Value
        $expectedIntegrity = $assetMatch.Groups["sri"].Value
        $verificationCssPath = Join-Path ([IO.Path]::GetTempPath()) "my-affiliate-site1-live-$cacheBuster.css"
        & curl.exe -fsSL --retry 3 --connect-timeout 15 -H "Cache-Control: no-cache" `
            "$cssUrl`?verify=$cacheBuster" -o $verificationCssPath
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to fetch the live CSS for deployment verification."
        }
        $actualIntegrity = "sha256-" + [Convert]::ToBase64String(
            [Security.Cryptography.SHA256]::HashData([IO.File]::ReadAllBytes($verificationCssPath))
        )
        Remove-Item -LiteralPath $verificationCssPath -Force

        if ($actualIntegrity -eq $expectedIntegrity) {
            Write-Host "Deployment verified: the live CSS integrity hash matches."
            exit 0
        }
    }

    if ($attempt -lt $VerificationAttempts) {
        Start-Sleep -Seconds $VerificationIntervalSeconds
    }
}

throw "Deployment completed, but the live CSS integrity hash did not match before verification timed out."
