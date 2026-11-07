[CmdletBinding()]
param(
    [string]$Python,
    [switch]$Dev
)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed with exit code $LASTEXITCODE" }
}

if (-not $Python) {
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        $Python = & $launcher.Source -3 -c 'import sys; print(sys.executable)'
        if ($LASTEXITCODE -ne 0) { $Python = $null }
    }
    if (-not $Python) {
        $candidate = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($candidate) { $Python = $candidate.Source }
    }
}
if (-not $Python) {
    throw 'Install Python 3.11+ from python.org, then rerun; or use -Python C:\Path\python.exe.'
}
Invoke-Checked $Python @('-c', 'import sys; assert sys.version_info >= (3,11), "Python 3.11+ required"')
$venvRoot = Join-Path $projectRoot '.venv'
$venvPython = Join-Path $venvRoot 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    Invoke-Checked $Python @('-m', 'venv', $venvRoot)
}
Invoke-Checked $venvPython @('-m', 'pip', 'install', '-r', (Join-Path $projectRoot 'requirements.txt'))
if ($Dev) {
    Invoke-Checked $venvPython @('-m', 'pip', 'install', '-e', "$projectRoot[dev]")
} else {
    Invoke-Checked $venvPython @('-m', 'pip', 'install', '--no-deps', '-e', $projectRoot)
}
$edgeCandidates = @(
    (Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe'),
    (Join-Path $env:ProgramFiles 'Microsoft\Edge\Application\msedge.exe'),
    (Join-Path $env:LOCALAPPDATA 'Microsoft\Edge\Application\msedge.exe')
)
if (-not ($edgeCandidates | Where-Object { Test-Path -LiteralPath $_ })) {
    Write-Warning 'Microsoft Edge was not found. Install it through your approved software channel.'
}
Write-Host "PilotPatch installed. No browsers or system settings were changed."
Write-Host "Run: & '$projectRoot\copilot.cmd' login"
Write-Host "Then: & '$projectRoot\copilot.cmd' probe"
Write-Host "To use copilot-agent anywhere in this PowerShell session:"
Write-Host ('$env:Path = "' + $venvRoot + '\Scripts;' + '$env:Path"')
