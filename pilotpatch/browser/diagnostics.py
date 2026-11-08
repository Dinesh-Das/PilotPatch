"""Small, safe startup diagnostics; never dump browser logs or authentication URLs."""

import re
from urllib.parse import urlsplit

from pilotpatch.security.redaction import redact


def startup_failure(stage: str, error: Exception, *, cleanup_failed: bool = False) -> str:
    raw = str(error)
    lines = raw.strip().splitlines()
    detail = lines[0] if lines else type(error).__name__

    def origin_only(match):
        try:
            url = urlsplit(match.group())
            return f"{url.scheme}://{url.hostname}/[details omitted]"
        except ValueError:
            return "[URL omitted]"

    detail = re.sub(r"https?://[^\s<>\"']+", origin_only, detail)
    detail = redact(detail)[:500]
    if "Executable doesn't exist" in raw or "executable doesn't exist" in raw.lower():
        hint = "Microsoft Edge was not found. Install it through your approved software channel."
    elif any(
        marker in raw for marker in ("ProcessSingleton", "user data directory is already in use")
    ):
        hint = (
            "Edge reports that the dedicated profile is already open. Keep any active sign-in "
            "task running; close its own Edge window only after that task has ended."
        )
    elif "ERR_CERT_" in raw or "ERR_SSL_" in raw:
        hint = (
            "Check the approved certificate trust and TLS inspection settings with your "
            "organization. Certificate verification has not been disabled."
        )
    elif "ERR_PROXY_" in raw or "ERR_TUNNEL_" in raw:
        hint = "Check the configured proxy and your organization's network access policy."
    elif stage == "opening the Copilot page":
        hint = "Check Copilot connectivity, proxy/TLS settings and any network error shown above."
    else:
        hint = "Check Edge installation and enterprise automation policy; run copilot-agent doctor."
    message = f"Cannot initialize Edge/Copilot while {stage}.\nReason: {detail}\n{hint}"
    if cleanup_failed:
        message += (
            "\nBrowser cleanup also reported an error. If a PilotPatch Edge window remains "
            "after its task has ended, close that window before retrying."
        )
    return message
