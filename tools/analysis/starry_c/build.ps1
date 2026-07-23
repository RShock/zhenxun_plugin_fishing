param(
  [string]$OutName = "scan_starry_max_score.exe"
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Src = Join-Path $Root "scan_starry_max_score.c"
$Out = Join-Path $Root $OutName

function Find-Gcc {
  $cmd = Get-Command gcc -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  return $null
}
function Find-Tcc {
  $cmd = Get-Command tcc -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  $portable = Join-Path $env:TEMP "tcc-0.9.27-win64\tcc\tcc.exe"
  if (Test-Path $portable) { return $portable }
  return $null
}
function Ensure-Tcc {
  $existing = Find-Tcc
  if ($existing) { return $existing }
  $zip = Join-Path $env:TEMP "tcc-0.9.27-win64-bin.zip"
  $dest = Join-Path $env:TEMP "tcc-0.9.27-win64"
  $url = "https://download.savannah.gnu.org/releases/tinycc/tcc-0.9.27-win64-bin.zip"
  Write-Host "Downloading TinyCC from $url"
  python -c "import urllib.request; from pathlib import Path; urllib.request.urlretrieve(r'$url', r'$zip'); print('downloaded', Path(r'$zip').stat().st_size)"
  Expand-Archive -Path $zip -DestinationPath $dest -Force
  $portable = Join-Path $dest "tcc\tcc.exe"
  if (-not (Test-Path $portable)) { throw "tcc extract failed" }
  return $portable
}

$gcc = Find-Gcc
if ($gcc) {
  Write-Host "Using GCC: $gcc"
  & $gcc -O3 -march=native -o $Out $Src
} else {
  $tcc = Ensure-Tcc
  Write-Host "Using TinyCC: $tcc"
  & $tcc -O2 -lkernel32 -o $Out $Src
}
if ($LASTEXITCODE -ne 0) { throw "build failed" }
Write-Host "Built $Out"
& $Out --selftest
