from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.syntax import Syntax

console = Console(highlight=False)


def confirm(message: str) -> bool:
    if not console.is_terminal:
        return False
    return Confirm.ask(message, default=False)


def preview(diff: str):
    console.print(Syntax(diff, "diff", word_wrap=True))


def banner(project):
    console.print(
        Panel(
            f"Project: {project}\nProvider: Microsoft Copilot Web\n"
            "Destination: https://copilot.microsoft.com/",
            title="PilotPatch",
            border_style="cyan",
        )
    )


def report(result: dict):
    console.print(Panel(result["copilot"]["summary"], title="Copilot summary", markup=False))
    console.print(f"Applied file changes: {len(result['files_changed'])}", markup=False)
    for path in result["files_changed"]:
        console.print(f"  {path}", markup=False)
    if result["dry_run"]:
        console.print(
            "Dry run: edits and commands were simulated locally; no project changes applied."
        )
    if not result["checks"]:
        console.print("Verification: no commands were executed.")
    for check in result["checks"]:
        status = "TIMEOUT" if check["timed_out"] else f"exit {check['exit_code']}"
        console.print(f"Verification ({status}): {check['argv']}", markup=False)
    for issue in result["copilot"]["remaining_issues"]:
        console.print(f"Remaining: {issue}", markup=False)


def event(message: str):
    console.print(message, markup=False)
