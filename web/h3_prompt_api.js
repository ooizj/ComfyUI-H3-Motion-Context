import { app } from "../../scripts/app.js";
import { localizer, t } from "./h3_i18n.js";

const style = document.createElement("style");
style.textContent = `
.h3-api-key{box-sizing:border-box;display:flex;align-items:center;gap:8px;width:calc(100% - 20px);height:28px;margin:0 10px;padding:0 8px;border:1px solid var(--border-color,#555);border-radius:7px;background:var(--comfy-input-bg,#222);color:var(--input-text,#ddd);font:12px sans-serif}
.h3-api-key input{flex:1;min-width:0;width:0;border:0;outline:none;background:transparent;color:inherit;font:inherit}
.h3-api-key:focus-within{border-color:#75cabc}.h3-api-key button{display:flex;align-items:center;padding:2px;border:0;background:transparent;color:inherit;cursor:pointer}.h3-api-key button:focus-visible{outline:1px solid #75cabc}.h3-api-key svg{width:17px;height:17px}
`;
document.head.append(style);

function install(node) {
  if (node.h3ApiKey) return;
  const index = node.widgets.findIndex(widget => widget.name === "api_key");
  const original = node.widgets[index];
  const row = document.createElement("div");
  row.className = "h3-api-key";
  const label = document.createElement("span");
  label.textContent = "api_key";
  const input = document.createElement("input");
  input.type = "password";
  input.value = original.value ?? "";
  input.setAttribute("aria-label", "H3 API Key");
  input.autocomplete = "off";
  input.spellcheck = false;
  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/><path class="slash" d="m3 3 18 18"/></svg>';
  const setVisible = visible => {
    input.type = visible ? "text" : "password";
    toggle.title = visible ? t("隐藏 API Key", "Hide API key") : t("显示 API Key", "Show API key");
    toggle.setAttribute("aria-label", toggle.title);
    toggle.setAttribute("aria-pressed", String(visible));
    toggle.querySelector(".slash").style.display = visible ? "" : "none";
  };
  toggle.onclick = () => setVisible(input.type === "password");
  const i18n = localizer(() => setVisible(input.type === "text"));
  i18n.set(input, "未设置", "Not set", "placeholder");
  const oldRemoved = node.onRemoved;
  node.onRemoved = function (...args) { i18n.dispose(); oldRemoved?.apply(this, args); };
  row.append(label, input, toggle);
  for (const event of ["pointerdown", "pointermove", "pointerup", "mousedown", "dblclick"]) {
    row.addEventListener(event, e => e.stopPropagation());
  }
  input.addEventListener("keydown", e => {
    if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== "s") e.stopPropagation();
  });
  const widget = node.addDOMWidget("api_key", "custom", row, {
    ...original.options,
    getValue: () => input.value,
    setValue: value => { input.value = value ?? ""; },
    getMinHeight: () => 28,
    getMaxHeight: () => 28,
    margin: 0,
    hideOnZoom: false,
    onDraw: widget => { widget.width = node.size[0]; },
  });
  // Replace in place so saved workflows keep the same widget-value ordering.
  node.widgets.splice(node.widgets.indexOf(widget), 1);
  node.widgets[index] = widget;
  original.onRemove?.();
  widget.callback = original.callback;
  input.addEventListener("input", () => {
    widget.callback?.(widget.value);
    node.graph?.change();
    node.setDirtyCanvas(true);
  });
  node.h3ApiKey = { hide: () => setVisible(false) };
  setVisible(false);
}

app.registerExtension({
  name: "H3MotionContext.PromptAPI",
  nodeCreated(node) { if (node.comfyClass === "MiniMaxH3PromptAPI") install(node); },
  loadedGraphNode(node) {
    if (node.comfyClass === "MiniMaxH3PromptAPI") { install(node); node.h3ApiKey.hide(); }
  },
});
