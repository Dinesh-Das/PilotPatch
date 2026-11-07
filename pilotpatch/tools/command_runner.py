import asyncio
import os
import re
import shutil
import signal
import subprocess

from pilotpatch.security.permissions import Permissions
from pilotpatch.security.redaction import redact
from pilotpatch.security.system import windows_binary
from pilotpatch.tools.repository import Repository


class CommandRunner:
    def __init__(self, repo: Repository, permissions: Permissions, dry_run: bool = False):
        self.repo = repo
        self.permissions = permissions
        self.dry_run = dry_run

    async def _terminate(self, process):
        if os.name == "nt":
            # Kill descendants as well, including test workers. PID is a local integer.
            killer = await asyncio.create_subprocess_exec(
                windows_binary("taskkill.exe"),
                "/PID",
                str(process.pid),
                "/T",
                "/F",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await killer.wait()
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if process.returncode is None:
            process.kill()
        await process.wait()

    async def run(self, argv: list[str], cwd: str = ".", *, test_name: str | None = None) -> dict:
        if (
            not argv
            or len(argv) > 100
            or any(not isinstance(a, str) or "\x00" in a or len(a) > 10000 for a in argv)
        ):
            raise ValueError("Command must be a bounded, nonempty argv array")
        directory = self.repo.guard.resolve(cwd, directory=True)
        preapproved = argv in self.repo.config.allowed_commands
        if test_name is not None:
            preapproved = self.repo.config.test_commands.get(test_name) == argv
        if self.dry_run:
            return dict(executed=False, dry_run=True, argv=argv, exit_code=None)
        self.permissions.require(
            f"Run in {directory}: {subprocess.list2cmdline(argv)}?\n"
            "This executes local code with your user permissions.",
            command=True,
            preapproved=preapproved,
        )
        actual = list(argv)
        executable = shutil.which(argv[0])
        if os.name == "nt" and executable and executable.lower().endswith((".cmd", ".bat")):
            # cmd.exe expands these even inside quotes. Reject rather than trying
            # to invent a shell escaping scheme for model-provided arguments.
            if any(re.search(r"[&|<>^%!\r\n\"]", a) for a in argv):
                raise ValueError(
                    "Batch command contains shell metacharacters; use a direct executable"
                )
            actual = [
                windows_binary("cmd.exe"),
                "/d",
                "/s",
                "/c",
                '"' + subprocess.list2cmdline([executable, *argv[1:]]) + '"',
            ]
        options = (
            {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
            if os.name == "nt"
            else {"start_new_session": True}
        )
        process = await asyncio.create_subprocess_exec(
            *actual,
            cwd=directory,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            **options,
        )
        output = bytearray()
        total = 0

        async def drain():
            nonlocal total
            while data := await process.stdout.read(4096):
                total += len(data)
                output.extend(data[: max(0, self.repo.config.max_output_bytes - len(output))])

        draining = asyncio.create_task(drain())
        timed_out = False
        try:
            await asyncio.wait_for(
                asyncio.gather(process.wait(), asyncio.shield(draining)),
                self.repo.config.command_timeout,
            )
        except TimeoutError:
            timed_out = True
            await self._terminate(process)
        except asyncio.CancelledError:
            await self._terminate(process)
            raise
        finally:
            if not draining.done():
                draining.cancel()
            await asyncio.gather(draining, return_exceptions=True)
        return dict(
            executed=True,
            argv=argv,
            cwd=cwd,
            exit_code=process.returncode,
            output=redact(output.decode("utf-8", errors="replace")),
            timed_out=timed_out,
            truncated=total > self.repo.config.max_output_bytes,
        )
