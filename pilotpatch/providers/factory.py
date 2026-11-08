from pathlib import Path

from pilotpatch.config import Config
from pilotpatch.providers.copilot_browser import CopilotBrowser
from pilotpatch.providers.existing_edge import CopilotExistingEdge


def browser_provider(home: Path, config: Config):
    if config.browser_connection == "managed-edge":
        return CopilotBrowser(home, config)
    return CopilotExistingEdge(home, config)
