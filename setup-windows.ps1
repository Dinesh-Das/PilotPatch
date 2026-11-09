[CmdletBinding()]
param(
    [string]$Python,
    [switch]$Dev
)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$venvRoot = Join-Path $projectRoot '.venv'
$venvPython = Join-Path $venvRoot 'Scripts\python.exe'
# Single-quoted Python literals survive legacy PowerShell 5.1 native argument passing.
$pythonCheck = "import sys; assert (3,11) <= sys.version_info < (3,14) and sys.maxsize > 2**32 and sys.implementation.name == 'cpython', '64-bit CPython 3.11-3.13 required'"

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed with exit code $LASTEXITCODE" }
}

if (Test-Path -LiteralPath $venvPython) {
    try {
        Invoke-Checked $venvPython @('-I', '-c', $pythonCheck)
    } catch {
        throw "Existing .venv cannot run 64-bit Python 3.11-3.13. Virtual environments are not portable: recreate .venv on this laptop with an approved Python installation, then rerun setup. No packages were installed."
    }
    if (-not $Python) { $Python = $venvPython }
}
if (-not $Python) {
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        foreach ($version in @('-3.13', '-3.12', '-3.11')) {
            try {
                $candidate = & $launcher.Source $version -c 'import sys; print(sys.executable)' 2>$null
                if ($LASTEXITCODE -eq 0) { $Python = $candidate; break }
            } catch {
                # PowerShell 5.1 can turn even redirected native stderr into an error.
                continue
            }
        }
    }
    if (-not $Python) {
        $candidate = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($candidate) { $Python = $candidate.Source }
    }
}
if (-not $Python) {
    throw 'Install approved 64-bit Python 3.11-3.13, then rerun; or use -Python C:\Path\python.exe.'
}
Invoke-Checked $Python @('-I', '-c', $pythonCheck)
if (-not (Test-Path -LiteralPath $venvPython)) {
    Invoke-Checked $Python @('-I', '-m', 'venv', $venvRoot)
}
Invoke-Checked $venvPython @('-I', '-m', 'pip', 'install', '--only-binary=:all:', '-r', (Join-Path $projectRoot 'requirements.txt'))
if ($Dev) {
    Invoke-Checked $venvPython @('-I', '-m', 'pip', 'install', '-e', "$projectRoot[dev]")
} else {
    Invoke-Checked $venvPython @('-I', '-m', 'pip', 'install', '--no-deps', '-e', $projectRoot)
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
Write-Host "Run: & '$projectRoot\copilot.cmd' connect"
Write-Host "Pair the extension with your current Edge profile, then run login."
Write-Host "Then: & '$projectRoot\copilot.cmd' probe"
Write-Host "To use copilot-agent anywhere in this PowerShell session:"
Write-Host ('$env:Path = "' + $venvRoot + '\Scripts;' + '$env:Path"')
