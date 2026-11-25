import hashlib
import subprocess

import pytest

from pilotpatch.config import Config
from pilotpatch.security.permissions import Permissions
from pilotpatch.tools.filesystem import FileTools
from pilotpatch.tools.repository import Repository
from pilotpatch.tools.review import ReviewRepository


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


def test_inventory_honors_nested_negation_and_loads_each_ignore_file_once(tmp_path, monkeypatch):
    from pathspec import GitIgnoreSpec

    fs = tools(tmp_path)
    root = fs.repo.root
    (root / "nested").mkdir()
    (root / "extra").mkdir()
    (root / ".gitignore").write_text("*.dart\n")
    (root / "nested/.gitignore").write_text("!keep.dart\n")
    (root / "nested/keep.dart").write_text("keep")
    (root / "nested/drop.dart").write_text("drop")
    parsed = []
    original = GitIgnoreSpec.from_lines

    def read_rules(lines):
        parsed.append(lines)
        return original(lines)

    monkeypatch.setattr(GitIgnoreSpec, "from_lines", read_rules)
    assert fs.repo.files("*.dart") == ["nested/keep.dart"]
    assert len(parsed) == 2


def test_line_ranges_preserve_private_key_redaction_and_byte_limit(tmp_path):
    fs = tools(tmp_path)
    target = fs.repo.root / "fixture.py"
    target.write_bytes(
        b"before = 1\n-----BEGIN PRIVATE KEY-----\n"
        b"example-private-key-body\n-----END PRIVATE KEY-----\nafter = 2\n"
    )
    assert "example-private-key-body" not in fs.repo.read_range("fixture.py", 3, 3)["content"]
    assert "after = 2" in fs.repo.read_range("fixture.py", 3, 5)["content"]
    fs.repo = Repository(fs.repo.root, Config(max_file_bytes=1024))
    target.write_text(("é" * 280 + "\n") * 2, encoding="utf-8")
    with pytest.raises(ValueError, match="Range too large"):
        fs.repo.read_range("fixture.py", 1, 2)


def test_repository_diff_fetches_only_changed_blobs(tmp_path, monkeypatch):
    fs = tools(tmp_path)
    root = fs.repo.root
    for index in range(5):
        (root / f"file {index}.py").write_bytes(b"value = 1\n")
    key_text = (
        b"-----BEGIN PRIVATE KEY-----\n"
        + b"other-fixture-line\n" * 6
        + b"original-fixture-body\n"
        + b"other-fixture-line\n" * 6
        + b"-----END PRIVATE KEY-----\n"
    )
    (root / "fixture.txt").write_bytes(key_text)
    for args in (
        ["init", "-q"],
        ["config", "core.autocrlf", "false"],
        ["add", "."],
        [
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "fixture",
        ],
    ):
        subprocess.run(["git", *args], cwd=root, check=True)
    (root / "file 4.py").write_bytes(b"value = 2\n")
    invoked = []
    real_run = subprocess.run

    def run(command, **kwargs):
        invoked.append(command)
        return real_run(command, **kwargs)

    monkeypatch.setattr(subprocess, "run", run)
    report = fs.repo.git_diff()
    assert "+value = 2" in report["output"]
    assert not report["truncated"]
    assert len(invoked) == 2
    (root / "fixture.txt").write_bytes(
        key_text.replace(b"original-fixture-body", b"new-fixture-body")
    )
    assert fs.repo.git_diff("fixture.txt")["output"] == ""


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


def test_staged_rename_links_only_the_visible_final_paths(tmp_path):
    fs = tools(tmp_path)
    (fs.repo.root / "original.py").write_text("value = 1", encoding="utf-8")
    draft = ReviewRepository(fs.repo)
    fs.repo = draft
    fs.rename("original.py", "temporary.py", digest("value = 1"))
    fs.rename("temporary.py", "final.py", digest("value = 1"))
    fs.write("unrelated.py", "pass", None)
    changes = sorted(draft.changes.values(), key=lambda item: item.name)
    assert [item.name for item in changes] == ["final.py", "original.py", "unrelated.py"]
    assert draft.review_groups(changes) == {0: 0, 1: 0}
    assert changes[0].review_entry(0, 12000, 0)["added"] == 1
    assert changes[1].review_entry(1, 12000, 0)["removed"] == 1


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


def test_readonly_git_cannot_execute_project_shadow_binary(tmp_path, monkeypatch):
    fs = tools(tmp_path)
    fake = fs.repo.root / "git.exe"
    fake.write_bytes(b"untrusted executable")
    monkeypatch.setattr("pilotpatch.tools.repository.shutil.which", lambda _: str(fake))
    with pytest.raises(ValueError, match="outside"):
        fs.repo.git_status()
