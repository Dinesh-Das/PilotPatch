"""Observe public chat controls; never inspect credentials, cookies or hidden auth state."""

import re
from urllib.parse import urlparse

from pilotpatch.config import Selectors

COPILOT_HOSTS = {"copilot.microsoft.com", "copilot.com", "copilot.ai"}


def copilot_origin(page) -> bool:
    url = urlparse(page.url)
    return url.scheme == "https" and url.hostname in COPILOT_HOSTS


async def visible(page, selector: str):
    matches = page.locator(selector)
    return [
        matches.nth(index)
        for index in range(await matches.count())
        if await matches.nth(index).is_visible()
    ]


async def service_error_visible(page, selectors: Selectors) -> bool:
    if await visible(page, selectors.errors):
        return True
    # This banner was visible in the user's Copilot screenshot. Its text is evidence
    # of an error, never an instruction to refresh or resubmit a request automatically.
    banner = page.get_by_text(
        "Your request couldn't be completed. Refresh to try again.", exact=True
    )
    return any([await banner.nth(index).is_visible() for index in range(await banner.count())])


async def observe(page, selectors: Selectors) -> dict:
    result = dict(
        authenticated=False,
        chat_ready=False,
        connection_verified=False,
        account="unavailable",
        composer_count=0,
        account_control_count=0,
    )
    if page is None or page.is_closed():
        return dict(result, state="browser_closed")
    if not copilot_origin(page):
        return dict(result, state="manual_authentication_required")
    result["environment"] = urlparse(page.url).hostname
    profiles = await visible(page, selectors.signed_in)
    composers = await visible(page, selectors.composer)
    sign_out_controls = []
    for role in ("menuitem", "button", "link"):
        sign_out = page.get_by_role(role, name=re.compile(r"^sign\s*out$", re.I))
        sign_out_controls.extend(
            [
                sign_out.nth(index)
                for index in range(await sign_out.count())
                if await sign_out.nth(index).is_visible()
            ]
        )
    sign_in_controls = await visible(page, selectors.sign_in)
    # Labels can differ in capitalization or include an account suffix. A visible
    # sign-in button wins over a generic avatar, so guest chat never proves login.
    if not sign_in_controls:
        sign_in = page.get_by_role("button", name=re.compile(r"^sign\s*in\b", re.I))
        sign_in_controls = [
            sign_in.nth(index)
            for index in range(await sign_in.count())
            if await sign_in.nth(index).is_visible()
        ]
    result.update(
        composer_count=len(composers), account_control_count=len(profiles) + len(sign_out_controls)
    )
    result["authenticated"] = bool(profiles or sign_out_controls) and not sign_in_controls
    if await service_error_visible(page, selectors):
        return dict(result, state="service_error")
    if sign_in_controls:
        return dict(result, state="sign_in_required")
    if not profiles and not sign_out_controls:
        return dict(
            result,
            state="account_control_not_recognized" if composers else "waiting_for_copilot_chat",
        )
    result["authenticated"] = True
    result["account"] = "signed-in account control detected; inspect Edge for account identity"
    if len(profiles) == 1:
        label = await profiles[0].get_attribute("aria-label")
        if label:
            result["account"] = label[:160]
    if len(composers) != 1:
        return dict(
            result, state="chat_input_not_recognized" if not composers else "multiple_chat_inputs"
        )
    return dict(result, state="authenticated_ui", chat_ready=True)
