import pytest

from pilotpatch.tools.patch import apply_unified


def test_lf_patch_preserves_crlf_file():
    patch = "--- a/a\n+++ b/a\n@@ -1,2 +1,2 @@\n one\n-two\n+three\n"
    assert apply_unified(patch, "one\r\ntwo\r\n") == ("a", "one\r\nthree\r\n")


def test_no_final_newline():
    patch = (
        "--- a/a\n+++ b/a\n@@ -1 +1 @@\n-old\n"
        "\\ No newline at end of file\n+new\n\\ No newline at end of file\n"
    )
    assert apply_unified(patch, "old")[1] == "new"


def test_create_empty_base_and_separate_hunks():
    creation = "--- a/a\n+++ b/a\n@@ -0,0 +1,1 @@\n+new\n"
    assert apply_unified(creation, "")[1] == "new\n"
    patch = "--- a/a\n+++ b/a\n@@ -1 +1 @@\n-one\n+1\n@@ -3 +3 @@\n-three\n+3\n"
    assert apply_unified(patch, "one\ntwo\nthree\n")[1] == "1\ntwo\n3\n"


@pytest.mark.parametrize(
    "patch",
    [
        "--- a/a\n+++ b/b\n@@ -1 +1 @@\n-old\n+new\n",
        "--- a/a\n+++ b/a\n@@ -1,4 +1,1 @@\n-old\n+new\n",
        "--- a/a\n+++ b/a\n@@ -1 +8 @@\n-old\n+new\n",
        "--- a/a\n+++ b/a\n@@ -1 +1 @@\n-old\n+new\n--- a/b\n+++ b/b\n",
    ],
)
def test_reject_inconsistent_or_multifile_patch(patch):
    with pytest.raises(ValueError):
        apply_unified(patch, "old\n")
