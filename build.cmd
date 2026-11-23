@echo off
setlocal
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
