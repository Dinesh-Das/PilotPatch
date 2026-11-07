@echo off
setlocal
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo PilotPatch is not installed. Run setup-windows.ps1 first. 1>&2
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" -m pilotpatch %*
exit /b %errorlevel%
