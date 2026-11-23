"""Exercise installation under the Windows PowerShell 5.1 shipped with office PCs."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from pilotpatch.security.system import windows_binary

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows setup scripts")
ROOT = Path(__file__).resolve().parents[1]


def run_setup(script, command):
    return subprocess.run(
        [
            windows_binary("WindowsPowerShell/v1.0/powershell.exe"),
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            command,
        ],
        cwd=script.parent,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def test_setup_reaches_installer_with_supported_python_under_powershell51(tmp_path):
    script = tmp_path / "setup-windows.ps1"
    shutil.copyfile(ROOT / script.name, script)
    shutil.copyfile(ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
    # Existing interpreter deliberately has no pip: reach that stage without
    # contacting a package index or executing package installation in this test.
    import venv

    venv.EnvBuilder(with_pip=False).create(tmp_path / ".venv")
    result = run_setup(script, f"& {ps_quote(script)} -Python {ps_quote(sys.executable)}")
    assert "No module named pip" in result.stderr, result.stdout + result.stderr
    assert "Virtual environments are not portable" not in result.stderr


def test_setup_falls_back_when_newer_py_versions_write_stderr(tmp_path):
    script = tmp_path / "setup-windows.ps1"
    shutil.copyfile(ROOT / script.name, script)
    launcher = tmp_path / "launcher.cmd"
    interpreter = tmp_path / "supported.cmd"
    launcher.write_text(
        '@echo off\nif "%~1"=="-3.11" (\n'
        f"echo {interpreter}\nexit /b 0\n)\n"
        "echo requested Python is not installed 1>&2\nexit /b 103\n"
    )
    interpreter.write_text(
        '@echo off\nif "%~2"=="-c" exit /b 0\necho REACHED_SUPPORTED_PYTHON\nexit /b 17\n'
    )
    command = (
        "function Get-Command { param($Name, $ErrorAction) "
        "if ($Name -eq 'py.exe') { [pscustomobject]@{Source="
        + ps_quote(launcher)
        + "} } }; & "
        + ps_quote(script)
    )
    result = run_setup(script, command)
    assert "REACHED_SUPPORTED_PYTHON" in result.stdout, result.stdout + result.stderr


def test_setup_rejects_copied_or_broken_venv_before_installing(tmp_path):
    script = tmp_path / "setup-windows.ps1"
    shutil.copyfile(ROOT / script.name, script)
    broken = tmp_path / ".venv/Scripts/python.exe"
    broken.parent.mkdir(parents=True)
    broken.write_bytes(b"not a working Windows executable")
    result = run_setup(script, f"& {ps_quote(script)} -Python {ps_quote(sys.executable)}")
    assert result.returncode != 0
    assert "Virtual environments are not portable" in result.stderr
    assert "No packages were installed" in result.stderr
