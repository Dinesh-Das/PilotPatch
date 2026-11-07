from collections.abc import Callable


class Permissions:
    def __init__(self, mode: str, confirm: Callable[[str], bool]):
        self.mode = mode
        self.confirm = confirm

    def require(
        self,
        description: str,
        *,
        destructive: bool = False,
        command: bool = False,
        preapproved: bool = False,
    ) -> None:
        if self.mode == "read-only":
            raise PermissionError("Read-only mode denies edits and command execution")
        if not destructive and (
            (command and preapproved) or (not command and self.mode == "auto-edit")
        ):
            return
        if not self.confirm(description):
            raise PermissionError("Operator declined the proposed operation")
