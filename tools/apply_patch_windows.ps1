param(
    [Parameter(Position = 0)]
    [AllowEmptyString()]
    [string] $Patch,

    [switch] $Install
)

function Get-CodexPatchWrapper {
    $wrapper = Get-Command apply_patch.bat -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $wrapper) {
        throw "Cannot find Codex's generated apply_patch.bat on PATH."
    }
    return $wrapper.Path
}

if ($Install) {
    $wrapperPath = Get-CodexPatchWrapper
    $targetPath = Join-Path (Split-Path -Parent $wrapperPath) 'apply_patch.ps1'
    if ($PSCommandPath -ne $targetPath) {
        try {
            Copy-Item -LiteralPath $PSCommandPath -Destination $targetPath -Force -ErrorAction Stop
        } catch [System.UnauthorizedAccessException] {
            throw "Codex blocked writes outside the workspace. Approve an elevated copy to $targetPath, or invoke this repository script directly."
        }
    }
    Write-Output "Installed apply_patch shim: $targetPath"
    return
}

if ($null -eq $Patch) {
    throw 'Pass the complete patch text as the first argument, or use -Install.'
}

$batchWrapper = Get-CodexPatchWrapper
$wrapperText = [IO.File]::ReadAllText($batchWrapper, [Text.Encoding]::UTF8)
$match = [regex]::Match(
    $wrapperText,
    '(?m)^"([^"]+\\codex\.exe)"\s+--codex-run-as-apply-patch'
)
if (-not $match.Success) {
    throw "Cannot locate codex.exe in $batchWrapper"
}

# Windows PowerShell 5.1 reconstructs native command lines and damages multiline
# arguments containing quotes. Build the one patch argument using CommandLineToArgvW rules.
$argument = New-Object Text.StringBuilder
[void] $argument.Append('"')
$slashes = 0
foreach ($character in $Patch.ToCharArray()) {
    if ($character -eq '\') {
        $slashes++
    } elseif ($character -eq '"') {
        [void] $argument.Append(('\' * ($slashes * 2 + 1)))
        [void] $argument.Append('"')
        $slashes = 0
    } else {
        if ($slashes -gt 0) {
            [void] $argument.Append(('\' * $slashes))
            $slashes = 0
        }
        [void] $argument.Append($character)
    }
}
if ($slashes -gt 0) {
    [void] $argument.Append(('\' * ($slashes * 2)))
}
[void] $argument.Append('"')

$startInfo = New-Object Diagnostics.ProcessStartInfo
$startInfo.FileName = $match.Groups[1].Value
$startInfo.Arguments = '--codex-run-as-apply-patch ' + $argument.ToString()
$startInfo.UseShellExecute = $false
$process = [Diagnostics.Process]::Start($startInfo)
$process.WaitForExit()
$global:LASTEXITCODE = $process.ExitCode
