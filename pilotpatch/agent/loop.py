import asyncio
import hashlib
import json
from collections import Counter

from pilotpatch.agent.context import ContextBuilder, edit_request
from pilotpatch.agent.protocol import FinalAnswer, ProtocolError, parse_message
from pilotpatch.agent.state import SessionStore
from pilotpatch.providers.base import CopilotProvider
from pilotpatch.security.redaction import redact_value
from pilotpatch.tools.registry import MUTATIONS, ToolRegistry


class AgentStopped(RuntimeError):
    pass


def fingerprint(action) -> str:
    return hashlib.sha256(
        json.dumps(
            dict(tool=action.tool, arguments=action.arguments), sort_keys=True, ensure_ascii=False
        ).encode()
    ).hexdigest()


class AgentLoop:
    def __init__(
        self,
        provider: CopilotProvider,
        registry: ToolRegistry,
        store: SessionStore,
        state: dict,
        event=lambda _: None,
        *,
        review=None,
    ):
        self.provider, self.registry, self.store, self.state = provider, registry, store, state
        self.context = ContextBuilder(registry.files.repo, review=review is not None)
        self.config = registry.files.repo.config
        self.event = event
        self.review = review

    async def run(
        self,
        *,
        resume: bool = False,
        resolve_pending: bool = False,
        conversation: list[dict] | None = None,
    ) -> dict:
        state = self.state
        if state["status"] == "completed":
            return state["final"]
        if state["pending"]:
            if not resolve_pending:
                raise AgentStopped(
                    "Interrupted action has unknown outcome. Inspect diff/audit and use "
                    "resume --resolve-pending skip after reconciling it manually"
                )
            pending = state["pending"]
            result = dict(
                type="tool_result",
                id=pending["id"],
                tool=pending["tool"],
                success=False,
                error=dict(
                    code="UnknownOutcome",
                    message="Operator skipped interrupted action; "
                    "it may have executed. Inspect current files; do not replay commands.",
                ),
            )
            state["receipts"][pending["id"]] = dict(
                fingerprint=pending["fingerprint"], result=result
            )
            state["messages"].append(dict(role="tool", content=result))
            state["pending"] = None
            self.store.save(state)
        prompt = (
            self.context.resume(state)
            if resume
            else self.context.initial(state["task"], conversation)
        )
        counts = Counter(r["fingerprint"] for r in state["receipts"].values())
        corrections = 0
        edit_retries = 0
        editing = (
            conversation is not None
            and edit_request(state["task"])
            and (self.config.permission_mode != "read-only" or state["dry_run"])
        )
        operator_declined = False
        try:
            while state["steps"] < self.config.max_steps:
                state["steps"] += 1
                state["status"] = "awaiting_response"
                state["messages"].append(dict(role="user", content=prompt))
                self.store.save(state)
                self.event(f"[{state['steps']}] Sending context to Microsoft Copilot")
                self.store.audit(state, "prompt_attempted", step=state["steps"])
                response = await self.provider.send(prompt)
                state["conversation_url"] = getattr(self.provider, "conversation_url", None)
                try:
                    action = parse_message(response, self.config.max_response_bytes)
                except ProtocolError as exc:
                    corrections += 1
                    self.store.audit(state, "format_error", step=state["steps"])
                    if corrections > self.config.format_retries:
                        raise AgentStopped(
                            "Repeated invalid protocol from Copilot; session saved"
                        ) from exc
                    reminder = (
                        "The previous response was invalid. PilotPatch runs local tools on your "
                        "behalf. Request a tool with one tool_call JSON object, without prose."
                    )
                    if state["receipts"]:
                        recent = next(reversed(state["receipts"].values()))["result"]
                        prompt = self.context.result(recent, reminder=reminder)
                    else:
                        prompt = self.context.initial(
                            state["task"], conversation, reminder=reminder
                        )
                    self.store.save(state)
                    continue
                corrections = 0
                state["messages"].append(
                    dict(role="assistant", content=redact_value(action.model_dump()))
                )
                if isinstance(action, FinalAnswer):
                    edited = any(
                        r["result"].get("result", {}).get(flag)
                        for r in state["receipts"].values()
                        for flag in ("applied", "staged", "dry_run")
                        if r["result"]["tool"] in MUTATIONS
                    )
                    if (
                        editing
                        and not edited
                        and not operator_declined
                        and edit_retries < 2
                        and state["steps"] < self.config.max_steps
                    ):
                        edit_retries += 1
                        self.event(
                            "Continuing to inspect the project and prepare the requested edits…"
                        )
                        reminder = (
                            "PilotPatch runs repository tools for you. No requested edit has been "
                            "prepared yet. Use read_files or search_content to obtain source, then "
                            "request a concrete edit with replace_in_file, apply_patch "
                            "or write_file. "
                            "If a tool was denied, respect that decision."
                        )
                        if state["receipts"]:
                            recent = next(reversed(state["receipts"].values()))["result"]
                            prompt = self.context.result(recent, reminder=reminder)
                        else:
                            prompt = self.context.initial(
                                state["task"], conversation, reminder=reminder
                            )
                        continue
                    review = await self.review(action.summary) if self.review else {}
                    if self.review and editing and not review:
                        review["review_status"] = "no_draft"
                    report = dict(
                        copilot=redact_value(action.model_dump()),
                        files_changed=list(dict.fromkeys(state["changes"])),
                        checks=state["checks"],
                        dry_run=state["dry_run"],
                        reasoning_mode=getattr(self.provider, "reasoning_mode", None),
                        **review,
                        verification="Commands actually executed are listed under checks; "
                        "Copilot's narrative is not independent verification.",
                    )
                    state["status"], state["final"] = "completed", report
                    self.store.save(state)
                    self.store.audit(state, "completed", steps=state["steps"])
                    return report
                key = fingerprint(action)
                prior = state["receipts"].get(action.id)
                if prior:
                    if prior["fingerprint"] != key:
                        raise AgentStopped("Tool-call ID reused with different arguments")
                    counts[key] += 1
                    result = prior["result"]
                    self.event(
                        f"[{state['steps']}] Replaying receipt for {action.tool} ({action.id})"
                    )
                else:
                    counts[key] += 1
                    if counts[key] > 3:
                        raise AgentStopped("Repeated identical action detected; session saved")
                    state["pending"] = dict(id=action.id, tool=action.tool, fingerprint=key)
                    state["status"] = "awaiting_action"
                    self.store.save(state)
                    self.event(f"[{state['steps']}] Copilot requested {action.tool}")
                    self.store.audit(state, "tool_started", id=action.id, tool=action.tool)
                    result = await self.registry.execute(action)
                    if (
                        result.get("error", {}).get("message")
                        == "Operator declined the proposed operation"
                    ):
                        operator_declined = True
                    state["receipts"][action.id] = dict(
                        fingerprint=key, result=redact_value(result)
                    )
                    state["pending"] = None
                    if result["success"]:
                        actual = result["result"]
                        if action.tool in MUTATIONS and actual.get("applied"):
                            state["changes"].append(actual["path"])
                            if actual.get("destination"):
                                state["changes"].append(actual["destination"])
                        if action.tool in {"run_tests", "run_command"} and actual.get("executed"):
                            state["checks"].append(
                                {
                                    k: actual.get(k)
                                    for k in ("argv", "cwd", "exit_code", "timed_out", "truncated")
                                }
                            )
                    self.store.audit(
                        state,
                        "tool_finished",
                        id=action.id,
                        tool=action.tool,
                        success=result["success"],
                    )
                if counts[key] > 3:
                    raise AgentStopped("Repeated identical action detected; session saved")
                state["messages"].append(dict(role="tool", content=redact_value(result)))
                # Bound storage growth; receipts and changes remain separate and durable.
                if len(state["messages"]) > 30:
                    state["messages"] = state["messages"][-30:]
                self.store.save(state)
                prompt = self.context.result(result)
            raise AgentStopped("Maximum agent steps reached; increase max_steps to resume")
        except (asyncio.CancelledError, KeyboardInterrupt):
            state["status"] = "cancelled"
            self.store.save(state)
            self.store.audit(state, "cancelled", pending=state["pending"] is not None)
            raise
        except Exception:
            state["status"] = "interrupted"
            self.store.save(state)
            self.store.audit(state, "interrupted", pending=state["pending"] is not None)
            raise
