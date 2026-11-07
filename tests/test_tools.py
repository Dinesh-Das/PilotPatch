import hashlib
import subprocess

import pytest

from pilotpatch.config import Config
from pilotpatch.security.permissions import Permissions
from pilotpatch.tools.filesystem import FileTools
from pilotpatch.tools.repository import Repository


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def tools(tmp_path, mode="auto-edit", dry_run=False, confirm=lambda _: True):
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    return FileTools(
        Repository(repo, Config()), tmp_path / "state", Permissions(mode, confirm), dry_run=dry_run
    )


def test_explore_search_ignore_and_redaction(tmp_path):
    fs = tools(tmp_path)
    root = fs.repo.root
    (root / "a.py").write_text('answer = 42\npassword = "secret-value"\n')
    (root / ".env").write_text("sensitive")
    (root / ".gitignore").write_text("ignored/\n")
    (root / "ignored").mkdir()
    (root / "ignored/x.py").write_text("answer = 0")
    assert fs.repo.files("*.py") == ["a.py"]
    assert fs.repo.search("answer")["matches"][0]["line"] == 1
    assert "secret-value" not in fs.repo.read("a.py")["content"]


def test_replace_requires_exact_unique_content_and_backup(tmp_path):
    fs = tools(tmp_path)
    file = fs.repo.root / "a.py"
    file.write_text("old\n")
    result = fs.replace("a.py", "old", "new")
    assert file.read_text() == "new\n"
    assert result["applied"] is True
    assert "-old" in result["diff"]
    assert list((tmp_path / "state/backups").rglob("*.bak"))[0].read_text() == "old\n"
    with pytest.raises(ValueError):
        fs.replace("a.py", "old", "again")


def test_write_hash_prevents_lost_edits(tmp_path):
    fs = tools(tmp_path)
    (fs.repo.root / "a").write_text("user edit")
    with pytest.raises(ValueError):
        fs.write("a", "overwrite", digest("stale"))
    with pytest.raises(ValueError):
        fs.write("a", "overwrite", None)
    assert (fs.repo.root / "a").read_text() == "user edit"


def test_no_overwrite_if_user_edits_during_approval(tmp_path):
    fs = tools(tmp_path, mode="approve")
    target = fs.repo.root / "a"
    target.write_text("old")

    def edit_during_approval(_):
        target.write_text("user changed")
        return True

    fs.permissions.confirm = edit_during_approval
    with pytest.raises(ValueError):
        fs.write("a", "new", digest("old"))
    assert target.read_text() == "user changed"


@pytest.mark.parametrize("mode,dry_run", [("auto-edit", True), ("read-only", False)])
def test_no_writes_in_dry_run_or_readonly(tmp_path, mode, dry_run):
    fs = tools(tmp_path, mode, dry_run)
    if mode == "read-only":
        with pytest.raises(PermissionError):
            fs.write("new.py", "pass", None)
    else:
        assert fs.write("new.py", "pass", None)["applied"] is False
    assert not (fs.repo.root / "new.py").exists()


def test_delete_and_rename_always_require_approval(tmp_path):
    fs = tools(tmp_path, confirm=lambda _: False)
    (fs.repo.root / "a").write_text("old")
    with pytest.raises(PermissionError):
        fs.delete("a", digest("old"))
    with pytest.raises(PermissionError):
        fs.rename("a", "b", digest("old"))
    assert (fs.repo.root / "a").exists()


def test_unified_patch_context_and_no_newline(tmp_path):
    fs = tools(tmp_path)
    (fs.repo.root / "a.py").write_text("one\ntwo\n")
    patch = "--- a/a.py\n+++ b/a.py\n@@ -1,2 +1,2 @@\n one\n-two\n+three\n"
    fs.patch(patch)
    assert (fs.repo.root / "a.py").read_text() == "one\nthree\n"
    with pytest.raises(ValueError):
        fs.patch(patch)


def test_git_status_diff_exclude_sensitive_content(tmp_path):
    fs = tools(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=fs.repo.root, check=True)
    (fs.repo.root / "a.py").write_text("one\n")
    assert "a.py" in fs.repo.git_status()["output"]
