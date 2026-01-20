param(
  [string]$OutputPath = "static/images/ogp-default.jpg",
  [string]$Title = "電子書籍・未来研究所",
  [string]$Subtitle = "Kindle / Kobo の選び方・セール情報",
  [int]$Width = 1200,
  [int]$Height = 630,
  [ValidateRange(1, 100)][int]$Quality = 90
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Drawing

function New-Font {
  param(
    [string[]]$PreferredNames,
    [float]$Size,
    [System.Drawing.FontStyle]$Style
  )

  foreach ($name in $PreferredNames) {
    try {
      return New-Object System.Drawing.Font($name, $Size, $Style, [System.Drawing.GraphicsUnit]::Pixel)
    }
    catch {
      continue
    }
  }

  return New-Object System.Drawing.Font(
    [System.Drawing.FontFamily]::GenericSansSerif,
    $Size,
    $Style,
    [System.Drawing.GraphicsUnit]::Pixel
  )
}

$outputDirectory = Split-Path -Parent $OutputPath
if ($outputDirectory -and -not (Test-Path $outputDirectory)) {
  New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
}

$bitmap = $null
$graphics = $null
$backgroundBrush = $null
$accentBrush = $null
$dotBrush = $null
$textBrush = $null
$shadowBrush = $null
$titleFont = $null
$subtitleFont = $null
$encoderParams = $null

try {
  $bitmap = New-Object System.Drawing.Bitmap $Width, $Height
  $graphics = [System.Drawing.Graphics]::FromImage($bitmap)

  $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
  $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
  $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
  $graphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit

  $canvasRect = New-Object System.Drawing.Rectangle 0, 0, $Width, $Height

  $backgroundBrush = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
    $canvasRect,
    [System.Drawing.Color]::FromArgb(255, 245, 250, 255),
    [System.Drawing.Color]::FromArgb(255, 226, 237, 255),
    90
  )
  $graphics.FillRectangle($backgroundBrush, $canvasRect)

  $accentBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(34, 0, 114, 206))
  $graphics.FillEllipse($accentBrush, -80, 60, 420, 420)
  $graphics.FillEllipse($accentBrush, 880, -140, 520, 520)
  $graphics.FillEllipse($accentBrush, 860, 360, 420, 420)

  $dotBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(28, 0, 0, 0))
  $graphics.FillEllipse($dotBrush, 70, 480, 18, 18)
  $graphics.FillEllipse($dotBrush, 110, 520, 10, 10)
  $graphics.FillEllipse($dotBrush, 1030, 540, 14, 14)

  $preferredFonts = @("Yu Gothic UI", "Meiryo UI", "Meiryo", "MS PGothic")
  $titleFont = New-Font -PreferredNames $preferredFonts -Size 68 -Style ([System.Drawing.FontStyle]::Bold)
  $subtitleFont = New-Font -PreferredNames $preferredFonts -Size 30 -Style ([System.Drawing.FontStyle]::Regular)

  $textBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 24, 39, 63))
  $shadowBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(60, 0, 0, 0))

  $titleSize = $graphics.MeasureString($Title, $titleFont)
  $titleX = [Math]::Round(($Width - $titleSize.Width) / 2)
  $titleY = [Math]::Round(($Height - $titleSize.Height) / 2 - 28)

  $graphics.DrawString($Title, $titleFont, $shadowBrush, $titleX + 2, $titleY + 2)
  $graphics.DrawString($Title, $titleFont, $textBrush, $titleX, $titleY)

  if ($Subtitle -and $Subtitle.Trim().Length -gt 0) {
    $subtitleSize = $graphics.MeasureString($Subtitle, $subtitleFont)
    $subtitleX = [Math]::Round(($Width - $subtitleSize.Width) / 2)
    $subtitleY = [Math]::Round($titleY + $titleSize.Height + 8)

    $graphics.DrawString($Subtitle, $subtitleFont, $shadowBrush, $subtitleX + 1, $subtitleY + 1)
    $graphics.DrawString($Subtitle, $subtitleFont, $textBrush, $subtitleX, $subtitleY)
  }

  $jpegEncoder = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() |
    Where-Object { $_.MimeType -eq "image/jpeg" } |
    Select-Object -First 1

  if (-not $jpegEncoder) {
    throw "JPEG encoder not found."
  }

  $encoderParams = New-Object System.Drawing.Imaging.EncoderParameters 1
  $encoderParams.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter(
    [System.Drawing.Imaging.Encoder]::Quality,
    [long]$Quality
  )

  $bitmap.Save($OutputPath, $jpegEncoder, $encoderParams)
  Write-Host "Generated: $OutputPath"
}
finally {
  if ($encoderParams) { $encoderParams.Dispose() }
  if ($titleFont) { $titleFont.Dispose() }
  if ($subtitleFont) { $subtitleFont.Dispose() }
  if ($shadowBrush) { $shadowBrush.Dispose() }
  if ($textBrush) { $textBrush.Dispose() }
  if ($dotBrush) { $dotBrush.Dispose() }
  if ($accentBrush) { $accentBrush.Dispose() }
  if ($backgroundBrush) { $backgroundBrush.Dispose() }
  if ($graphics) { $graphics.Dispose() }
  if ($bitmap) { $bitmap.Dispose() }
}
