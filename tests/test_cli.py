import os
import subprocess
import sys

import pytest

from pilotpatch.cli import parser


@pytest.mark.parametrize(
    "argv,task",
    [
        (["--project", "C:/Work space/repo", "Fix the bug"], "Fix the bug"),
        (["run", "Fix the bug", "--dry-run"], "run"),
        (["--share-code", "run", "Fix the bug"], "run"),
    ],
)
def test_cli_argument_forms(argv, task):
    assert parser().parse_intermixed_args(argv).command_or_task == task


def test_help_version_and_history_without_browser(tmp_path):
    environment = dict(os.environ, PYTHONIOENCODING="utf-8")
    for args in [["--help"], ["--version"], ["--home", str(tmp_path), "history"]]:
        result = subprocess.run(
            [sys.executable, "-m", "pilotpatch", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
            timeout=15,
        )
        assert result.returncode == 0, result.stderr + result.stdout
