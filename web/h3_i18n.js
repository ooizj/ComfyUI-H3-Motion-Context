import { app } from "../../scripts/app.js";

const LOCALE = "Comfy.Locale";
let locale = null;

// Editor text follows ComfyUI's language: Chinese for zh locales, English otherwise.
export const t = (zh, en) =>
  String(locale ?? app.extensionManager?.setting?.get(LOCALE) ?? navigator.language).toLowerCase().startsWith("zh") ? zh : en;

// Static editor text relabeled when ComfyUI's language changes; call dispose() when the node is removed.
export function localizer(onChange) {
  const texts = [];
  const update = event => {
    locale = event.detail.value;
    for (const [el, prop, zh, en] of texts) el[prop] = t(zh, en);
    onChange();
  };
  app.ui.settings.addEventListener(`${LOCALE}.change`, update);
  return {
    set(el, zh, en, prop = "textContent") { texts.push([el, prop, zh, en]); el[prop] = t(zh, en); return el; },
    dispose() { app.ui.settings.removeEventListener(`${LOCALE}.change`, update); },
  };
}
