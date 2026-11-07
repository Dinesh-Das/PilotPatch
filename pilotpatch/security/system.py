import os
from pathlib import Path


def windows_binary(name: str) -> str:
    """Pin OS utilities so an untrusted project cannot shadow them in the CWD."""
    return str(Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32" / name)
