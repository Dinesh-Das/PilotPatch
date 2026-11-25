/* Choose reasoning through the visible Copilot menu. No account changes or internal APIs. */
function visibleModeControl(element) {
  return element.getClientRects().length && getComputedStyle(element).visibility !== "hidden";
}

function copilotModeButton() {
  const buttons = [...document.querySelectorAll('button[aria-haspopup="menu"][aria-label$=", Model Selector" i]')]
    .filter(visibleModeControl);
  return buttons.length === 1 ? buttons[0] : undefined;
}

function currentCopilotMode() {
  const caption = copilotModeButton()?.getAttribute("aria-label").split(",")[0].trim().toLowerCase();
  if (caption === "think deeper") return "think_deeper";
  return caption === "auto" ? "auto" : "current";
}

async function selectCopilotMode() {
  const trigger = copilotModeButton();
  if (!trigger || currentCopilotMode() === "think_deeper") return currentCopilotMode();
  if (trigger.disabled || trigger.getAttribute("aria-disabled") === "true"
      || trigger.getAttribute("aria-expanded") === "true") {
    return currentCopilotMode();
  }
  const openMenus = () => [...document.querySelectorAll('[role="menu"]')].filter(visibleModeControl);
  const previous = new Set(openMenus());
  const url = location.href;
  trigger.click();
  let menu;
  for (let attempt = 0; attempt < 16; attempt++) {
    if (!trigger.isConnected || location.href !== url) return "current";
    const menus = openMenus().filter(item => !previous.has(item));
    if (menus.length > 1) break;
    if (menus.length === 1 && trigger.getAttribute("aria-expanded") === "true") {
      menu = menus[0];
      break;
    }
    await new Promise(resolve => setTimeout(resolve, 50));
  }
  const choices = menu ? [...menu.querySelectorAll('[role="menuitemradio"]')].filter(visibleModeControl) : [];
  for (const [label, selected] of [["think deeper", "think_deeper"], ["auto", "auto"]]) {
    const options = choices.filter(item => (item.innerText || "").trim().split("\n")[0].trim().toLowerCase() === label);
    if (options.length !== 1 || options[0].getAttribute("aria-disabled") === "true" || options[0].disabled) continue;
    options[0].click();
    for (let attempt = 0; attempt < 10 && currentCopilotMode() !== selected && location.href === url; attempt++) {
      await new Promise(resolve => setTimeout(resolve, 50));
    }
    if (currentCopilotMode() === selected) return selected;
    break;
  }
  if (trigger.isConnected && trigger.getAttribute("aria-expanded") === "true") trigger.click();
  return currentCopilotMode();
}
