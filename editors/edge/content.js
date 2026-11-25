/* Public visible DOM only. No cookies, auth storage, internal endpoints or page messages. */
(() => {
  "use strict";
  const driverVersion = 4;
  if (globalThis.__pilotpatchDriver === driverVersion) return;
  globalThis.__pilotpatchDriver = driverVersion;
  const hosts = ["copilot.com", "copilot.microsoft.com", "copilot.ai"];
  const seen = new Map();
  const failures = new Set(["turn_lost", "wrong_origin", "invalid_command", "duplicate_command",
    "invalid_selectors", "invalid_nonce", "unsupported_action", "not_ready", "invalid_prompt",
    "composer_has_draft", "send_control_not_unique", "unsupported_composer", "send_disabled",
    "unsent_draft_cleared"]);
  let activeNonce = null;
  let prepared = null;
  const visible = element => !!element.getClientRects().length
    && getComputedStyle(element).visibility !== "hidden";
  const find = selector => [...document.querySelectorAll(selector)].filter(visible);
  const named = expression => [...document.querySelectorAll("button, a, [role=button], [role=menuitem]")]
    .filter(e => visible(e) && expression.test(e.getAttribute("aria-label") || e.innerText.trim()));
  function composerText(field) {
    const text = field.value ?? field.innerText;
    // Copilot's current rich composer appends this zero-width caret placeholder.
    return field.id === "m365-chat-editor-target-element" && field.isContentEditable
      ? text.replace(/\u200b\u200c$/, "") : text;
  }
  function writeComposer(field, text) {
    if (field instanceof HTMLTextAreaElement || field instanceof HTMLInputElement) {
      const proto = field instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, "value").set.call(field, text);
    } else if (field.isContentEditable) field.textContent = text;
    else throw new Error("unsupported_composer");
    field.dispatchEvent(new InputEvent("input", {bubbles: true,
      inputType: text ? "insertText" : "deleteContent", data: text || null}));
  }
  function consumePreparation() {
    const pending = prepared;
    prepared = null;
    pending?.field.removeEventListener("input", pending.onInput);
    return pending;
  }
  function serviceError(s) {
    return find(s.errors).length > 0 || [...document.querySelectorAll("p, div, span")].some(e =>
      visible(e) && e.children.length === 0
      && e.textContent.trim() === "Your request couldn't be completed. Refresh to try again.");
  }
  function status(s) {
    const profiles = find(s.signed_in), composers = find(s.composer);
    const signedOut = find(s.sign_in).length || named(/^sign\s*in\b/i).length;
    const accounts = profiles.length + named(/^sign\s*out$/i).length;
    const authenticated = !!accounts && !signedOut;
    let state = "authenticated_ui";
    if (serviceError(s)) state = "service_error";
    else if (signedOut) state = "sign_in_required";
    else if (!accounts) state = composers.length ? "account_control_not_recognized" : "waiting_for_copilot_chat";
    else if (composers.length !== 1) state = composers.length ? "multiple_chat_inputs" : "chat_input_not_recognized";
    return {authenticated, chat_ready: state === "authenticated_ui", state,
      composer_count: composers.length, account_control_count: accounts,
      account: authenticated ? "signed-in account control detected; inspect Edge for identity" : "unavailable"};
  }
  function response(s, nonce, max) {
    if (nonce !== activeNonce) throw new Error("turn_lost");
    if (serviceError(s)) return {error: true};
    const users = find(s.user).filter(e => e.innerText.includes(nonce));
    if (users.length !== 1) return {bound: false, ambiguous: users.length > 1};
    if (find(s.user).some(e => e !== users[0]
        && (users[0].compareDocumentPosition(e) & Node.DOCUMENT_POSITION_FOLLOWING))) {
      return {ambiguous: true};
    }
    const answers = find(s.assistant).filter(e =>
      users[0].compareDocumentPosition(e) & Node.DOCUMENT_POSITION_FOLLOWING);
    if (answers.length !== 1) return {bound: false, ambiguous: answers.length > 1};
    const answer = answers[0];
    const turn = users[0].closest('[data-testid="m365-chat-llm-web-ui-chat-message"]');
    if (turn && !turn.contains(answer)) return {ambiguous: true};
    const bodies = s.assistant_body ? [...answer.querySelectorAll(s.assistant_body)].filter(visible) : [];
    if (bodies.length > 1) return {ambiguous: true};
    if (!bodies.length && answer.matches('[role="article"][aria-labelledby^="copilot-message-"]')) {
      return {bound: false};
    }
    const copy = (bodies[0] || answer).cloneNode(true);
    copy.querySelectorAll('button, svg, script, style, [aria-hidden="true"]').forEach(e => e.remove());
    const blocks = copy.querySelectorAll("pre");
    let text = copy.textContent || "";
    if (blocks.length === 1) {
      const outside = copy.cloneNode(true);
      outside.querySelector('pre').remove();
      // Only an empty wrapper or a JSON language label is UI chrome. Keep warnings
      // and prose so strict protocol parsing cannot turn an example into an action.
      if (/^(?:json)?$/i.test(outside.textContent.trim())) text = blocks[0].textContent;
    }
    if (text.length > max) return {oversize: true};
    const completed = [...answer.querySelectorAll(s.completion)].some(e =>
      visible(e) && !e.closest('pre, code')
      && !/^copy(?:\s+code.*)?$/i.test((e.getAttribute('aria-label') || '').trim()));
    return {bound: true, text, completed,
      busy: answer.getAttribute("aria-busy") === "true" || !!answer.querySelector('[aria-busy="true"]'),
      generating: find(s.stop).length > 0};
  }
  async function operate(command, phase) {
    const url = new URL(location.href);
    if (url.protocol !== "https:" || url.port || !hosts.includes(url.hostname)) throw new Error("wrong_origin");
    if (!command || !/^[a-f0-9]{32}$/.test(command.id)) throw new Error("invalid_command");
    if (command.action === "submit" && phase === "commit") {
      const pending = consumePreparation(); // Commit is never replayable.
      if (!pending || pending.id !== command.id || pending.url !== location.href) {
        throw new Error("turn_lost");
      }
      const {field, text, selectors: s} = pending;
      const composers = find(s.composer);
      const ownsDraft = field.isConnected && !pending.edited &&
        composers.length === 1 && composers[0] === field && composerText(field) === text;
      const buttons = find(s.send);
      if (!ownsDraft || buttons.length !== 1 || buttons[0].disabled
          || buttons[0].getAttribute("aria-disabled") === "true"
          || !status(s).chat_ready || find(s.stop).length) {
        // Only the exact draft in our original editor can be cleared, before any Send click.
        if (ownsDraft) {
          writeComposer(field, "");
          if (!composerText(field).trim()) throw new Error("unsent_draft_cleared");
        }
        throw new Error("send_disabled");
      }
      activeNonce = pending.nonce;
      const mode = currentCopilotMode();
      buttons[0].click();
      return {submitted: true, reasoning_mode: mode};
    }
    if (seen.has(command.id)) throw new Error("duplicate_command");
    if (phase !== "mode") {
      seen.set(command.id, true);
      if (seen.size > 128) seen.delete(seen.keys().next().value);
    }
    const p = command.payload, s = p?.selectors;
    if (!s || Object.values(s).some(value => typeof value !== "string" || value.length > 4096)) throw new Error("invalid_selectors");
    if (command.action === "status") return status(s);
    if (!/^[a-f0-9]{24}$/.test(p.nonce)) throw new Error("invalid_nonce");
    if (command.action === "response") return response(s, p.nonce, p.max);
    if (command.action !== "submit") throw new Error("unsupported_action");
    const current = status(s), composer = find(s.composer);
    if (!current.authenticated || !current.chat_ready || find(s.stop).length) throw new Error("not_ready");
    // Preserve unsent user work in the selected everyday tab.
    const field = composer[0];
    if (composerText(field).trim()) throw new Error("composer_has_draft");
    if (phase === "mode") return {mode: await selectCopilotMode()};
    if (phase !== "prepare") throw new Error("unsupported_action");
    if (typeof p.text !== "string" || p.text.length > 501000) throw new Error("invalid_prompt");
    const sends = find(s.send);
    if (sends.length > 1) throw new Error("send_control_not_unique");
    consumePreparation();
    field.focus();
    writeComposer(field, p.text);
    const pending = {id: command.id, field, text: p.text, selectors: s, url: location.href,
      nonce: p.nonce, edited: false};
    pending.onInput = event => { if (event.isTrusted) pending.edited = true; };
    field.addEventListener("input", pending.onInput);
    prepared = pending;
    return {prepared: true};
  }
  chrome.runtime.onMessage.addListener((message, sender, reply) => {
    if (sender.id !== chrome.runtime.id || message?.type !== `pilotpatch-command-v${driverVersion}`) return false;
    Promise.resolve().then(() => operate(message.command, message.phase)).then(reply,
      error => reply({failure: failures.has(error.message) ? error.message : "page_controls_changed"}));
    return true;
  });
})();
