"""Exercise installation under the Windows PowerShell 5.1 shipped with office PCs."""

import os
import shutil
import subprocess
import sys
import tomllib
import venv
from pathlib import Path

import pytest

from pilotpatch.security.system import windows_binary

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows setup scripts")
ROOT = Path(__file__).resolve().parents[1]


def run_setup(script, command, *, env=None):
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
        env=env,
    )


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def test_setup_reaches_installer_with_supported_python_under_powershell51(tmp_path):
    script = tmp_path / "setup-windows.ps1"
    shutil.copyfile(ROOT / script.name, script)
    shutil.copyfile(ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
    # Existing interpreter deliberately has no pip: reach that stage without
    # contacting a package index or executing package installation in this test.
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


@pytest.mark.parametrize("missing", ["wheelhouse", "backend wheel", "VS Code installer"])
def test_incomplete_office_bundle_fails_before_installing(tmp_path, missing):
    script = tmp_path / "setup-windows.ps1"
    for name in (script.name, "pyproject.toml", "requirements.txt"):
        shutil.copyfile(ROOT / name, tmp_path / name)
    version = tomllib.loads((tmp_path / "pyproject.toml").read_text())["project"]["version"]
    (tmp_path / "OFFICE-BUNDLE").touch()
    files = {
        "wheelhouse": "wheelhouse/fixture.whl",
        "backend wheel": f"dist/pilotpatch-{version}-py3-none-any.whl",
        "VS Code installer": f"artifacts/pilotpatch-{version}.vsix",
    }
    for kind, name in files.items():
        if kind != missing:
            file = tmp_path / name
            file.parent.mkdir()
            file.touch()
    result = run_setup(
        script,
        f"& {ps_quote(script)} -Python {ps_quote(sys.executable)} -InstallEditor",
        env=dict(os.environ, PIP_NO_INDEX="1"),
    )
    assert result.returncode != 0
    assert f"missing the {missing}" in result.stderr, result.stdout + result.stderr
    assert not (tmp_path / ".venv").exists()


def test_setup_finds_user_vscode_without_path_and_prepares_edge_first(tmp_path, tmp_path_factory):
    profile = tmp_path_factory.mktemp("office-profile")
    script = tmp_path / "setup-windows.ps1"
    for name in (script.name, "pyproject.toml", "requirements.txt"):
        shutil.copyfile(ROOT / name, tmp_path / name)
    version = tomllib.loads((tmp_path / "pyproject.toml").read_text())["project"]["version"]
    code = profile / "Programs/Microsoft VS Code/bin/code.cmd"
    code.parent.mkdir(parents=True)
    code.write_text("@echo off\nexit /b 23\n")
    vsix = tmp_path / "artifacts" / f"pilotpatch-{version}.vsix"
    vsix.parent.mkdir()
    vsix.touch()
    python = tmp_path / ".venv/Scripts/python.exe"
    python.parent.mkdir(parents=True)
    shutil.copyfile(sys.executable, python)
    # Stub the native tool boundary and omit PATH discovery to simulate a stale shell.
    stub = """
    $PSDefaultParameterValues = @{}
    function Get-Command { param($Name, $ErrorAction, $CommandType) }
    function global:Invoke-CheckedFixture {
        param($Executable, $Arguments)
        if ($Arguments[1] -eq '-c' -and $Arguments[2].Contains('tomllib')) { return 'VERSION' }
        if ($Arguments -contains 'connect') { Write-Host 'EDGE_FILES_PREPARED' }
        if ($Arguments[0] -eq '--install-extension') {
            Write-Host "EDITOR_CLI_FOUND: $Executable"
            throw 'Fixture rejects VSIX installation'
        }
    }
    """
    stubbed = script.read_text(encoding="utf-8").replace(
        "function Invoke-Checked {", "function Original-Invoke {"
    )
    stubbed = stubbed.replace("Invoke-Checked ", "Invoke-CheckedFixture ")
    script.write_text(stubbed, encoding="utf-8")
    result = run_setup(
        script,
        stub.replace("VERSION", version) + f"& {ps_quote(script)} -InstallEditor",
        env=dict(os.environ, LOCALAPPDATA=str(profile)),
    )
    assert result.returncode != 0
    assert "Backend and Edge setup are ready" in result.stderr, result.stdout + result.stderr
    assert str(code) in result.stdout
    assert result.stdout.index("EDGE_FILES_PREPARED") < result.stdout.index("EDITOR_CLI_FOUND")
