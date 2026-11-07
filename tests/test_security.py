import pytest

from pilotpatch.security.paths import PathGuard, SafetyError
from pilotpatch.security.redaction import redact


@pytest.mark.parametrize(
    "name",
    [
        "../outside",
        "C:\\Windows\\system.ini",
        "/tmp/x",
        ".git/config",
        ".env",
        "src/.env.production",
        "id_rsa",
        "x.pem",
        "a:stream",
        "a/../b",
        "CON",
        "a./file",
        ".npmrc",
        "x\\..\\bad",
    ],
)
def test_reject_unsafe_paths(tmp_path, name):
    with pytest.raises(SafetyError):
        PathGuard(tmp_path).resolve(name)


def test_safe_nested_file(tmp_path):
    assert PathGuard(tmp_path).resolve("src/main.py") == tmp_path / "src/main.py"


def test_symlink_escape(tmp_path):
    outside = tmp_path.parent / (tmp_path.name + "-outside")
    outside.mkdir()
    try:
        (tmp_path / "link").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("OS requires symlink privilege")
    with pytest.raises(SafetyError):
        PathGuard(tmp_path).resolve("link/file")


def test_redacts_common_credentials():
    text = (
        'password="super-secret"\nAuthorization: Bearer abcdefghi\napi_key: abcdefghi\nnormal = 42'
    )
    result = redact(text)
    assert "super-secret" not in result
    assert "abcdefghi" not in result
    assert "normal = 42" in result
