# Fishing plugin pack script
# Exclude: TTF/OTF fonts, PYC cache, __pycache__, PSD sources, pytest cache, etc.

$ErrorActionPreference = "Stop"

$PluginDir = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$PluginName = Split-Path $PluginDir -Leaf
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$OutputDir = Join-Path $PluginDir "dist"
$ArchiveName = "${PluginName}_${Timestamp}.7z"
$ArchivePath = Join-Path $OutputDir $ArchiveName
$ListFile = Join-Path $env:TEMP "fishing_pack_list_$Timestamp.txt"

# Find 7z
$SevenZip = $null
foreach ($candidate in @(
    "7z.exe",
    "$env:ProgramFiles\7-Zip\7z.exe",
    "${env:ProgramFiles(x86)}\7-Zip\7z.exe",
    "$env:LOCALAPPDATA\Programs\7-Zip\7z.exe"
)) {
    if ($candidate -eq "7z.exe") {
        $cmd = Get-Command 7z.exe -ErrorAction SilentlyContinue
        if ($cmd) { $SevenZip = $cmd.Source; break }
    } elseif (Test-Path $candidate) {
        $SevenZip = $candidate
        break
    }
}

if (-not $SevenZip) {
    Write-Error "7z.exe not found. Please install 7-Zip or add it to PATH."
}

function Test-ShouldExclude {
    param([string]$RelativePath)

    $p = $RelativePath -replace '\\', '/'
    $name = Split-Path $RelativePath -Leaf

    if ($p -match '(^|/)__pycache__(/|$)') { return $true }
    if ($p -match '(^|/)\.pytest_cache(/|$)') { return $true }
    if ($p -match '(^|/)\.mypy_cache(/|$)') { return $true }
    if ($p -match '(^|/)\.ruff_cache(/|$)') { return $true }
    if ($p -match '(^|/)\.git(/|$)') { return $true }
    if ($p -match '(^|/)dist(/|$)') { return $true }
    if ($p -match '(^|/)\.venv(/|$)') { return $true }
    if ($p -match '(^|/)node_modules(/|$)') { return $true }

    $ext = [System.IO.Path]::GetExtension($name).ToLowerInvariant()
    $excludeExts = @(
        '.pyc', '.pyo', '.pyd',
        '.ttf', '.otf', '.woff', '.woff2',
        '.psd',
        '.7z', '.zip', '.rar', '.tar', '.gz',
        '.log', '.tmp', '.bak', '.swp'
    )
    if ($excludeExts -contains $ext) { return $true }

    if ($p -ieq 'tools/packaging/pack.ps1') { return $true }
    if ($name -like 'fishing_pack_list_*.txt') { return $true }

    return $false
}

Write-Host "Plugin dir: $PluginDir"
Write-Host "7-Zip:      $SevenZip"
Write-Host "Scanning files..."

$files = Get-ChildItem -Path $PluginDir -Recurse -File -Force
$includePaths = New-Object System.Collections.Generic.List[string]
$excludedCount = 0
$excludedByType = @{}

foreach ($f in $files) {
    $rel = $f.FullName.Substring($PluginDir.Length).TrimStart('\', '/')
    if (Test-ShouldExclude $rel) {
        $excludedCount++
        $ext = [System.IO.Path]::GetExtension($f.Name).ToLowerInvariant()
        if (-not $ext) { $ext = '(noext)' }
        if ($rel -match '__pycache__') { $ext = '__pycache__' }
        if (-not $excludedByType.ContainsKey($ext)) { $excludedByType[$ext] = 0 }
        $excludedByType[$ext]++
        continue
    }
    $includePaths.Add($rel)
}

if ($includePaths.Count -eq 0) {
    Write-Error "No files to pack."
}

$includePaths | Set-Content -Path $ListFile -Encoding UTF8

if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir | Out-Null
}

if (Test-Path $ArchivePath) {
    Remove-Item $ArchivePath -Force
}

Write-Host ("Included: {0} files" -f $includePaths.Count)
Write-Host ("Excluded: {0} files" -f $excludedCount)
if ($excludedByType.Count -gt 0) {
    Write-Host "Exclude breakdown:"
    $excludedByType.GetEnumerator() | Sort-Object Name | ForEach-Object {
        Write-Host ("  {0}: {1}" -f $_.Key, $_.Value)
    }
}

Write-Host "Compressing -> $ArchivePath"

Push-Location $PluginDir
try {
    & $SevenZip a -t7z -mx=9 -m0=lzma2 "-i@${ListFile}" $ArchivePath | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "7z failed with exit code: $LASTEXITCODE"
    }
}
finally {
    Pop-Location
    if (Test-Path $ListFile) { Remove-Item $ListFile -Force -ErrorAction SilentlyContinue }
}

$info = Get-Item $ArchivePath
$sizeBytes = $info.Length
$sizeKB = [math]::Round($sizeBytes / 1KB, 2)
$sizeMB = [math]::Round($sizeBytes / 1MB, 2)

Write-Host ""
Write-Host "========== DONE =========="
Write-Host "Output: $($info.FullName)"
Write-Host "Size:   $sizeBytes bytes ($sizeKB KB / $sizeMB MB)"
Write-Host "Files:  included=$($includePaths.Count) excluded=$excludedCount"
Write-Host "=========================="

Write-Output "ARCHIVE_PATH=$($info.FullName)"
Write-Output "ARCHIVE_SIZE_BYTES=$sizeBytes"
Write-Output "ARCHIVE_SIZE_MB=$sizeMB"
