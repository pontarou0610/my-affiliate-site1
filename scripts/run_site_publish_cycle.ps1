param(
  [int]$Cycles = 1,
  [int]$Count = 1,
  [int]$Updates = 1,
  [switch]$ExternalSupplyCheck,
  [switch]$SkipGenerate,
  [switch]$Pull,
  [switch]$Publish,
  [switch]$Push,
  [switch]$AllowDirty,
  [int]$WaitDeploySeconds = 0
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $RepoRoot

$ArgsList = @(
  "scripts/site_publish_cycle.py",
  "--cycles", $Cycles,
  "--count", $Count,
  "--updates", $Updates
)

if ($ExternalSupplyCheck) {
  $ArgsList += @("--external-supply-check")
}
if ($SkipGenerate) {
  $ArgsList += @("--skip-generate")
}
if ($Pull) {
  $ArgsList += @("--pull")
}
if ($Publish) {
  $ArgsList += @("--publish")
}
if ($Push) {
  $ArgsList += @("--push")
}
if ($AllowDirty) {
  $ArgsList += @("--allow-dirty")
}
if ($WaitDeploySeconds -gt 0) {
  $ArgsList += @("--wait-deploy-seconds", $WaitDeploySeconds)
}

python @ArgsList
