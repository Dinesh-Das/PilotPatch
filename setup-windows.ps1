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
From a source checkout, a missing VSIX is built alongside the wheel, source archive
and Edge ZIP in artifacts\. The office bundle supplies the VSIX and installs offline.
VERSION comes from pyproject.toml.

Setup prepares %LOCALAPPDATA%\PilotPatch\edge-extension\manifest.json and the other
Edge extension files. In Edge's Load unpacked dialog, select the edge-extension folder
printed by setup. When the PilotPatch popup asks for a pairing file, use the private
edge-pairing.json printed by setup.

.PARAMETER Python
Full path to an approved x64 CPython 3.11, 3.12 or 3.13 executable.

.PARAMETER Dev
Installs development tools into the same .venv\ from a source checkout.

.PARAMETER InstallEditor
Installs the PilotPatch VSIX using the local VS Code command-line tool.

.PARAMETER OpenEdgeSetup
Opens the Edge extensions page and copies the unpacked extension folder path.

.EXAMPLE
.\setup-windows.ps1

.EXAMPLE
.\setup-windows.ps1 -InstallEditor -OpenEdgeSetup
#>
[CmdletBinding()]
param(
    [string]$Python,
    [switch]$Dev,
    [switch]$InstallEditor,
    [switch]$OpenEdgeSetup
)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$venvRoot = Join-Path $projectRoot '.venv'
$venvPython = Join-Path $venvRoot 'Scripts\python.exe'
# Single-quoted Python literals survive legacy PowerShell 5.1 native argument passing.
$pythonCheck = "import sys,sysconfig; assert (3,11) <= sys.version_info < (3,14) and sysconfig.get_platform() == 'win-amd64' and sys.implementation.name == 'cpython', 'Windows x64 CPython 3.11-3.13 required'"

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Setup step failed ($LASTEXITCODE). See the error immediately above." }
}

function Find-VSCodeCli {
    $command = Get-Command code.cmd -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($command) { return $command.Source }
    $installations = @()
    if ($env:LOCALAPPDATA) { $installations += Join-Path $env:LOCALAPPDATA 'Programs' }
    $installations += $env:ProgramW6432, $env:ProgramFiles, ${env:ProgramFiles(x86)}
    foreach ($installation in $installations) {
        if (-not $installation) { continue }
        $candidate = Join-Path $installation 'Microsoft VS Code\bin\code.cmd'
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
}

if (Test-Path -LiteralPath $venvPython) {
    try {
        Invoke-Checked $venvPython @('-I', '-c', $pythonCheck)
    } catch {
        throw "Existing .venv cannot run Windows x64 Python 3.11-3.13. Virtual environments are not portable: recreate .venv on this laptop with an approved Python installation, then rerun setup. No packages were installed."
    }
    if (-not $Python) { $Python = $venvPython }
}
if (-not $Python) {
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        foreach ($version in @('-3.13', '-3.12', '-3.11')) {
            try {
                $candidate = & $launcher.Source $version -I -c "$pythonCheck; print(sys.executable)" 2>$null
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
    throw 'Install approved Windows x64 Python 3.11-3.13, then rerun; or use -Python C:\Path\python.exe.'
}
Invoke-Checked $Python @('-I', '-c', $pythonCheck)
$projectFile = Join-Path $projectRoot 'pyproject.toml'
$readVersion = "import sys,tomllib; print(tomllib.load(open(sys.argv[1], 'rb'))['project']['version'])"
$version = Invoke-Checked $Python @('-I', '-c', $readVersion, $projectFile)
$wheelhouse = Join-Path $projectRoot 'wheelhouse'
$wheel = Join-Path $projectRoot "dist\pilotpatch-$version-py3-none-any.whl"
$vsix = Join-Path $projectRoot "artifacts\pilotpatch-$version.vsix"
$requirements = Join-Path $projectRoot 'requirements.txt'
$officeBundle = (Test-Path -LiteralPath (Join-Path $projectRoot 'OFFICE-BUNDLE')) -or
    ((-not (Test-Path -LiteralPath (Join-Path $projectRoot '.git'))) -and
        ((Test-Path -LiteralPath $wheelhouse) -or (Test-Path -LiteralPath $wheel)))
$index = @()
if ($officeBundle) {
    if ($Dev) { throw 'Development setup requires a source checkout. Run office bundle setup without -Dev.' }
    $repair = 'Extract the complete office ZIP into a new folder, then rerun setup. No packages were installed.'
    if (-not (Test-Path -LiteralPath $wheelhouse -PathType Container) -or
        -not (Get-ChildItem -LiteralPath $wheelhouse -Filter '*.whl' -File | Select-Object -First 1)) {
        throw "Office bundle is missing the wheelhouse with Windows dependency wheels. $repair"
    }
    if (-not (Test-Path -LiteralPath $wheel -PathType Leaf)) {
        throw "Office bundle is missing the backend wheel at $wheel. $repair"
    }
    if ($InstallEditor -and -not (Test-Path -LiteralPath $vsix -PathType Leaf)) {
        throw "Office bundle is missing the VS Code installer at $vsix. $repair"
    }
    if (-not (Test-Path -LiteralPath $requirements -PathType Leaf)) {
        throw "Office bundle is missing the requirements.txt file. $repair"
    }
    Write-Host 'Installing from the included Windows wheel bundle.'
    $index = @('--no-index', '--find-links', $wheelhouse)
}
if (-not (Test-Path -LiteralPath $venvPython)) {
    Invoke-Checked $Python @('-I', '-m', 'venv', $venvRoot)
}
Invoke-Checked $venvPython (@('-I', '-m', 'pip', 'install') + $index + @('--only-binary=:all:', '-r', $requirements))
if ($index.Count) {
    Invoke-Checked $venvPython (@('-I', '-m', 'pip', 'install') + $index + @('--no-deps', $wheel))
} elseif ($Dev) {
    Invoke-Checked $venvPython @('-I', '-m', 'pip', 'install', '-e', "$projectRoot[dev]")
} else {
    Invoke-Checked $venvPython @('-I', '-m', 'pip', 'install', '--no-deps', '-e', $projectRoot)
}
Invoke-Checked $venvPython @('-I', '-m', 'pip', 'check')
$connectArgs = @('-I', '-m', 'pilotpatch', '--project', $projectRoot, 'connect')
if ($OpenEdgeSetup) { $connectArgs += '--open-edge' }
Invoke-Checked $venvPython $connectArgs
Invoke-Checked $venvPython @('-I', '-m', 'pilotpatch', '--project', $projectRoot, 'register-editor')
if ($InstallEditor) {
    try {
        if (-not (Test-Path -LiteralPath $vsix -PathType Leaf)) {
            Invoke-Checked $venvPython @('-I', (Join-Path $projectRoot 'scripts\build.py'), '--no-office')
        }
        $editor = Find-VSCodeCli
        if (-not $editor) { throw 'The VS Code command-line tool was not found.' }
        Invoke-Checked $editor @('--install-extension', $vsix)
        Write-Host "Installed the VS Code extension from $vsix"
    } catch {
        throw "Backend and Edge setup are ready. $($_.Exception.Message) In approved VS Code, use Extensions > Install from VSIX and select $vsix"
    }
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
if ($InstallEditor) {
    Write-Host 'After selecting the tab in Edge, open your project in VS Code and click PilotPatch, then Test connection.'
} else {
    Write-Host 'For VS Code, rerun setup with -InstallEditor.'
    Write-Host "After selecting the tab in Edge, run & '$projectRoot\copilot.cmd' probe"
}
