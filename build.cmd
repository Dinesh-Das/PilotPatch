@echo off
setlocal
rem Run .\build.cmd in PowerShell from the PilotPatch folder.
rem The builder uses the folder containing this script, regardless of where you run it.
rem It reads VERSION from pyproject.toml and prints the full path of each artifact.
rem Files created in artifacts\ beside this script:
rem   pilotpatch-VERSION-py3-none-any.whl   Python install package
rem   pilotpatch-VERSION.tar.gz            Python source distribution
rem   pilotpatch-VERSION.vsix              VS Code extension installer
rem   PilotPatch-Edge-VERSION.zip          Edge extension files
rem   PilotPatch-Office-VERSION.zip        Offline Windows bundle with the wheel,
rem                                         VSIX, source files and Windows dependency wheels
rem   PilotPatch-Office-VERSION.zip.sha256 Checksum for the office bundle
rem Pass --no-office to skip the office ZIP and its checksum.
rem Pass --wheelhouse PATH to use a local folder of approved wheels.
rem For Edge's Load unpacked picker, run .\setup-windows.ps1 and use the
rem edge-extension folder it prints. That folder contains manifest.json.

if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" -I -c "import sys; assert (3, 11) <= sys.version_info < (3, 14)" >nul 2>&1
  if not errorlevel 1 goto venv
)
for %%V in (3.13 3.12 3.11) do (
  py.exe -%%V -I -c "import sys" >nul 2>&1
  if not errorlevel 1 (
    py.exe -%%V -I "%~dp0scripts\build.py" %*
    exit /b
  )
)
python.exe -I -c "import sys; assert (3, 11) <= sys.version_info < (3, 14)" >nul 2>&1
if errorlevel 1 (
  echo Install approved 64-bit CPython 3.11, 3.12, or 3.13, then run build.cmd again. 1>&2
  exit /b 1
)
python.exe -I "%~dp0scripts\build.py" %*
exit /b %errorlevel%

:venv
"%~dp0.venv\Scripts\python.exe" -I "%~dp0scripts\build.py" %*
exit /b %errorlevel%
