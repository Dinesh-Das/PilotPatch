import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field

from pilotpatch.agent.protocol import StrictModel


def default_home() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local/share"))) / "PilotPatch"


class Selectors(StrictModel):
    composer: str = (
        'textarea, [contenteditable="true"][role="textbox"], '
        '[contenteditable="true"][aria-label*="message" i], '
        '[contenteditable="true"][data-testid="chat-input"]'
    )
    send: str = (
        'button[aria-label="Send message" i], button[aria-label="Submit message" i], '
        'button[aria-label="Send" i]'
    )
    assistant: str = '[data-content="ai-message"], [data-testid="assistant-message"]'
    user: str = '[data-content="user-message"], [data-testid="user-message"]'
    stop: str = 'button[aria-label="Stop generating"], button[aria-label="Stop responding"]'
    # A code-block Copy button can appear during streaming; require a message control.
    completion: str = 'button[aria-label="Copy message" i]'
    signed_in: str = (
        'button[aria-label*="account" i], button[aria-label*="profile" i], '
        'button[title*="profile" i], [data-testid="user-avatar"], '
        '[data-testid="account-menu-button"], [data-testid="user-menu-button"], '
        "#mectrl_main_trigger"
    )
    sign_in: str = (
        'a[href*="login.live.com"], button[aria-label="Sign in" i], '
        'a[aria-label="Sign in" i], [role="button"][aria-label="Sign in" i]'
    )
    errors: str = '[role="alert"]'


class Config(StrictModel):
    provider: Literal["copilot_browser"] = "copilot_browser"
    browser_connection: Literal["existing-edge", "managed-edge"] = "existing-edge"
    edge_connect_timeout: int = Field(default=45, ge=1, le=120)
    permission_mode: Literal["read-only", "approve", "auto-edit"] = "approve"
    max_steps: int = Field(default=40, ge=1, le=500)
    format_retries: int = Field(default=2, ge=0, le=5)
    max_file_bytes: int = Field(default=64000, ge=1024, le=1000000)
    max_context_bytes: int = Field(default=48000, ge=12000, le=500000)
    max_response_bytes: int = Field(default=100000, ge=1024, le=1000000)
    max_output_bytes: int = Field(default=16000, ge=1024, le=100000)
    command_timeout: int = Field(default=120, ge=1, le=3600)
    response_timeout: int = Field(default=180, ge=5, le=1800)
    stable_seconds: float = Field(default=3.0, ge=0.1, le=30)
    poll_seconds: float = Field(default=0.5, ge=0.05, le=5)
    retention_days: int = Field(default=30, ge=1, le=365)
    # Exact argument vectors, configured by the operator, never by repository files.
    allowed_commands: list[list[str]] = Field(default_factory=list, max_length=100)
    test_commands: dict[str, list[str]] = Field(default_factory=dict)
    proxy_server: str | None = None
    selectors: Selectors = Field(default_factory=Selectors)


def load_config(path: Path | None = None) -> Config:
    path = path or default_home() / "config.yaml"
    if not path.exists():
        return Config()
    if path.stat().st_size > 100000:
        raise ValueError("Configuration exceeds 100 KB")
    return Config.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
