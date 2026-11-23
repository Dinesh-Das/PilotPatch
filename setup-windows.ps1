<#
.SYNOPSIS
Installs the PilotPatch backend and optionally the local VS Code extension.

.DESCRIPTION
Paths below are relative to this script unless they start with %LOCALAPPDATA%.
Creates or reuses .venv\ beside this script. The backend runs from
.venv\Scripts\python.exe, and its dependencies install into .venv\Lib\site-packages.
An extracted office bundle supplies the backend wheel in dist\ and dependencies in wheelhouse\.

Setup writes %LOCALAPPDATA%\PilotPatch\editor-backend.json so the VS Code extension
can find the installed Python. Its full path is printed during setup.

With -InstallEditor, setup installs artifacts\pilotpatch-VERSION.vsix into VS Code.
If the VSIX is missing, setup first builds it alongside the Python wheel, Python
source archive and Edge ZIP in artifacts\. VERSION comes from pyproject.toml.

Setup prepares %LOCALAPPDATA%\PilotPatch\edge-extension\manifest.json and the other
Edge extension files. In Edge's Load unpacked dialog, select the edge-extension folder
printed by setup. When the PilotPatch popup asks for a pairing file, use the private
edge-pairing.json printed by setup.

.PARAMETER Python
Full path to an approved 64-bit CPython 3.11, 3.12 or 3.13 executable.

.PARAMETER Dev
Installs the development tools into the same .venv\.

.PARAMETER InstallEditor
Installs the PilotPatch VSIX using the local VS Code command-line tool.

.EXAMPLE
.\setup-windows.ps1

.EXAMPLE
.\setup-windows.ps1 -InstallEditor
#>
[CmdletBinding()]
param(
    [string]$Python,
    [switch]$Dev,
    [switch]$InstallEditor
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
    if ($LASTEXITCODE -ne 0) { throw "Setup step failed ($LASTEXITCODE). See the error immediately above." }
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
$projectFile = Join-Path $projectRoot 'pyproject.toml'
$readVersion = "import sys,tomllib; print(tomllib.load(open(sys.argv[1], 'rb'))['project']['version'])"
$version = Invoke-Checked $venvPython @('-I', '-c', $readVersion, $projectFile)
$wheelhouse = Join-Path $projectRoot 'wheelhouse'
$wheel = Join-Path $projectRoot "dist\pilotpatch-$version-py3-none-any.whl"
$index = @()
if ((Test-Path -LiteralPath $wheelhouse) -and (Test-Path -LiteralPath $wheel) -and -not $Dev) {
    Write-Host 'Installing from the included Windows wheel bundle.'
    $index = @('--no-index', '--find-links', $wheelhouse)
}
Invoke-Checked $venvPython (@('-I', '-m', 'pip', 'install') + $index + @('--only-binary=:all:', '-r', (Join-Path $projectRoot 'requirements.txt')))
if ($index.Count) {
    Invoke-Checked $venvPython (@('-I', '-m', 'pip', 'install') + $index + @('--no-deps', $wheel))
} elseif ($Dev) {
    Invoke-Checked $venvPython @('-I', '-m', 'pip', 'install', '-e', "$projectRoot[dev]")
} else {
    Invoke-Checked $venvPython @('-I', '-m', 'pip', 'install', '--no-deps', '-e', $projectRoot)
}
Invoke-Checked $venvPython @('-I', '-m', 'pip', 'check')
Invoke-Checked $venvPython @('-I', '-m', 'pilotpatch', '--project', $projectRoot, 'register-editor')
Invoke-Checked $venvPython @('-I', '-m', 'pilotpatch', '--project', $projectRoot, 'connect')
if ($InstallEditor) {
    $editor = Get-Command code.cmd -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $editor) {
        throw 'VS Code CLI was not found. Install approved VS Code, reopen PowerShell, then rerun setup with -InstallEditor.'
    }
    $vsix = Join-Path $projectRoot "artifacts\pilotpatch-$version.vsix"
    if (-not (Test-Path -LiteralPath $vsix)) {
        Invoke-Checked $venvPython @('-I', (Join-Path $projectRoot 'scripts\build.py'), '--no-office')
    }
    Invoke-Checked $editor.Source @('--install-extension', $vsix)
    Write-Host "Installed the VS Code extension from $vsix"
    Write-Host 'After selecting the tab in Edge, open your project in VS Code and click PilotPatch, then Test connection.'
}
$edgeCandidates = @(
    (Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe'),
    (Join-Path $env:ProgramFiles 'Microsoft\Edge\Application\msedge.exe'),
    (Join-Path $env:LOCALAPPDATA 'Microsoft\Edge\Application\msedge.exe')
)
if (-not ($edgeCandidates | Where-Object { Test-Path -LiteralPath $_ })) {
    Write-Warning 'Microsoft Edge was not found. Install it through your approved software channel.'
}
Write-Host "PilotPatch $version installed into $venvRoot"
Write-Host "Backend Python is $venvPython"
if (-not $InstallEditor) {
    Write-Host 'For VS Code, rerun setup with -InstallEditor.'
    Write-Host "After selecting the tab in Edge, run & '$projectRoot\copilot.cmd' probe"
}
