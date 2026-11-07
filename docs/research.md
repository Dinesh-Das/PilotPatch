# Integration research — 8 November 2026

## Reference repository

Inspected [miuuyy/codex-chatgpt-web](https://github.com/miuuyy/codex-chatgpt-web),
commit `860fa576eb47d9e20d7d8289235bfea94392d2fd`, including `docs/architecture.md`,
`docs/security-model.md`, `src/chatgpt-ui/composer.ts` and `src/chatgpt-ui/turns.ts`.
Its architecture includes a local Responses bridge, persistent Electron browser
partition, browser-only/full modes, and a capability broker/tunnel for native tools.
It binds turns to logical DOM identities and waits for response-owned completion evidence.
It separates login from task conversations and fails on markup/model drift.

PilotPatch adopts the architectural lessons of isolated login state, explicit turn
ownership, deterministic tool dispatch, and uncertain-outcome handling. No source code
was copied. The ChatGPT selectors, model adapters, Responses passthrough, OpenAI tunnel,
Electron launcher and native Codex integration are not reusable for the requested
Microsoft-only Python CLI. A direct tool loop is smaller and has no second reasoning engine.

## Browser automation

[Playwright's browser documentation](https://playwright.dev/python/docs/browsers#google-chrome--microsoft-edge)
supports the installed `msedge` channel and warns that enterprise browser policy can
affect automation. [Persistent contexts](https://playwright.dev/python/docs/api/class-browsertype#browser-type-launch-persistent-context)
store browser state in a dedicated user-data directory; default everyday browser
profiles must not be reused. PilotPatch does not install or replace Edge, alter its
security policy, spoof fingerprints, intercept internal service APIs, or extract cookies.

Microsoft's [personal Copilot terms](https://www.microsoft.com/en-us/microsoft-copilot/for-individuals/termsofuse)
(effective 18 August 2026) prohibit automated access by bots/scrapers. They expressly
exclude work, school and organization/Entra accounts. This exclusion does not itself
authorize enterprise UI automation: applicable Microsoft agreements and organization
policy still govern use. The browser adapter is unofficial software, not evidence
of a supported or permitted integration. Verify authorization for the account/environment.

Without a signed-in authorized account, current Copilot turn selectors cannot be
validated against authenticated production markup. Defaults are candidate selectors,
not a claim of current live DOM compatibility. Local HTML fixture tests validate the
algorithm only; `login`, `status`, and `probe` must pass in the actual environment.

## Official enterprise alternative

The [Microsoft 365 Chat API overview](https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/api/ai-services/chat/overview)
describes multi-turn work/web-grounded conversations, an additional Microsoft 365 Copilot
license and preview terms. The documented
[create-conversation endpoint](https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/api/ai-services/chat/copilotroot-post-conversations)
is `POST https://graph.microsoft.com/beta/copilot/conversations` with an empty JSON body.
The documentation lists all these delegated work/school permissions as required:
`Sites.Read.All`, `Mail.Read`, `People.Read.All`, `OnlineMeetingTranscript.Read.All`,
`Chat.Read`, `ChannelMessage.Read.All`, and `ExternalItem.Read.All`.
Personal Microsoft accounts and application-only permissions are unsupported.
Beta APIs are subject to change and are not supported for production use.

No tenant license, Entra app registration, delegated user consent or admin approval
was available for validation. Consequently no API connector is shipped or advertised
as usable. The provider protocol permits a future explicitly selected Microsoft
connector without changing tool permissions; it must never become an automatic fallback.
