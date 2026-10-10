import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { localizer, t } from "./h3_i18n.js";

const FIELDS = [
  ["subject_definitions", ["主体定义", "Subject definitions"],
    ["<Subject 1> 是 <Picture 1> 中穿红色外套的女孩。", "<Subject 1> is the girl in <Picture 1>, wearing a red coat."]],
  ["summary", ["内容概述", "Summary"],
    ["[reference generation] 参考 <Picture 1> 的人物，生成 <Subject 1> 在雨后街道行走的短片。",
     "[reference generation] A short video of <Subject 1> walking down a street after rain."]],
  ["retention_analysis", ["参考保留规则", "Retention analysis"],
    ["<Subject 1>（出现于 [Shot 1]、[Shot 2]）：fully_preserved - 脸部、发型和红色外套保持一致。",
     "<Subject 1> (appears in [Shot 1], [Shot 2]): fully_preserved - her face, hairstyle and red coat stay consistent."]],
  ["detailed_description", ["画面与动作时间线", "Shots and timed actions"],
    ["写实电影风格，雨后傍晚，柔和侧光。\n[Shot 1] 中景，<Subject 1> 站在街道左侧。\n0–3 秒：女孩沿街向前走，镜头缓慢跟拍。\n3–6 秒：她停下脚步，抬头看向右侧橱窗。\n[Shot 2] At 00:06.000, 镜头切到女孩面部近景。\n6–9 秒：她轻轻微笑，倒影中的灯光掠过脸颊。",
     "Realistic cinematic style, a street after rain at dusk, soft side light.\n[Shot 1] A medium shot frames <Subject 1> on the left side of the street.\nFrom 0 to 3 seconds: she walks forward along the street as the camera slowly tracks her.\nFrom 3 to 6 seconds: she stops and looks up at a shop window on the right.\n[Shot 2] At 00:06.000, the shot cuts to a close-up of her face.\nFrom 6 to 9 seconds: she smiles softly as reflected lights slide across her cheek."]],
  ["overall_soundscape", ["整体环境声", "Overall soundscape"],
    ["适用于整片的低音量环境底声；只有要求全片静音时填 N/A。局部音效、对白写入上方对应动作时间段。",
     "Low ambience shared by the whole video; write N/A only for a fully silent video. Put local sound effects and dialogue in the matching timed passage above."]],
  ["non_diegetic_music", ["背景音乐", "Background music"], ["N/A", "N/A"]],
];
const AI_LANGUAGES = ["English", "中文"];
const DELETED_PICTURE = /<Picture (?:已删除|deleted)>/;
const LANGUAGE_KEY = "H3MotionContext.PromptBuilder.ai_language";

const css = document.createElement("style");
css.textContent = `
.h3pb{box-sizing:border-box;width:100%;height:100%;overflow:auto;background:#131b23;color:#e4ebf2;border:1px solid #344352;border-radius:9px;padding:14px;font:13px/1.5 system-ui,sans-serif;cursor:default}
.h3pb *{box-sizing:border-box}.h3pb button{border:1px solid #405366;background:#223343;border-radius:5px;padding:5px 10px;color:#e4ebf2;font:inherit;cursor:pointer}.h3pb button:hover{background:#30485c}.h3pb button:disabled{opacity:.4;cursor:default}.h3pb button:focus-visible,.h3pb textarea:focus{outline:1px solid #75cabc}
.h3pb .h3pb-row{display:flex;gap:7px;align-items:center;flex-wrap:wrap}.h3pb .h3pb-title{font-size:17px;font-weight:650;margin-right:auto}.h3pb small{color:#a6b7c6;font-size:11px}.h3pb .h3pb-note{margin:6px 0 10px;color:#a6b7c6;font-size:12px}.h3pb .h3pb-primary{background:#275b53;border-color:#559486}.h3pb .h3pb-pictures{display:flex;gap:8px;width:100%;min-width:0;flex-shrink:0;overflow-x:scroll;overflow-y:hidden;padding:9px 0;min-height:110px;scrollbar-width:auto;scrollbar-color:#648f9f #0b131b}
.h3pb .h3pb-pictures::-webkit-scrollbar{height:14px}
.h3pb .h3pb-pictures::-webkit-scrollbar-track{background:#0b131b;border-radius:7px}
.h3pb .h3pb-pictures::-webkit-scrollbar-thumb{background:#648f9f;border:3px solid #0b131b;border-radius:7px}
.h3pb .h3pb-card{flex:0 0 126px;border:1px solid #344d5d;border-radius:6px;padding:5px;position:relative;background:#1b2732}.h3pb .h3pb-card img{width:114px;height:78px;object-fit:contain;background:#10161c;display:block;cursor:pointer}.h3pb .h3pb-card strong{display:block;font-size:11px;color:#8bdbcb;text-align:center}.h3pb .h3pb-card .h3pb-row{gap:3px;justify-content:center;margin-top:4px}.h3pb .h3pb-card button{font-size:11px;padding:1px 5px}.h3pb .h3pb-drop{display:grid;place-items:center;min-width:150px;border:1px dashed #648174;border-radius:6px;color:#9dbcb0;padding:10px;flex:1;font-size:12px;text-align:center}.h3pb .h3pb-field{position:relative;display:block;margin:10px 0}.h3pb .h3pb-label{display:flex;gap:8px;align-items:baseline;margin-bottom:4px;font-weight:600}.h3pb .h3pb-label code{color:#8faaba;font:11px ui-monospace,monospace;font-weight:400}.h3pb .h3pb-segment{display:inline-flex;border:1px solid #405366;border-radius:6px;overflow:hidden}.h3pb .h3pb-segment button{border:0;border-radius:0;background:#1b2732;padding:3px 14px}.h3pb .h3pb-segment button+button{border-left:1px solid #405366}.h3pb .h3pb-segment button[aria-pressed=true]{background:#275b53;color:#fff;font-weight:600}.h3pb textarea{display:block;width:100%;min-height:64px;resize:vertical;padding:9px;background:#0b131b;color:#e3edf5;border:1px solid #364958;border-radius:5px;font:12px/1.6 ui-monospace,"Microsoft YaHei",monospace;tab-size:2}.h3pb textarea::placeholder{color:#778b9a}.h3pb textarea[data-field=detailed_description]{min-height:140px}.h3pb .h3pb-complete{position:absolute;z-index:20;left:6px;right:6px;top:45px;max-height:165px;overflow:auto;background:#203342;border:1px solid #76b9ad;border-radius:5px;box-shadow:0 6px 18px #0008}.h3pb .h3pb-complete button{display:flex;align-items:center;gap:9px;width:100%;border:0;border-radius:0;text-align:left;background:transparent}.h3pb .h3pb-complete button[aria-selected=true]{background:#365c69}.h3pb .h3pb-complete img{width:32px;height:25px;object-fit:contain}.h3pb .h3pb-complete span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.h3pb .h3pb-warning{color:#edbf7e;font-size:12px;white-space:pre-wrap}.h3pb .h3pb-status{margin-top:6px;min-height:18px;font-size:12px;color:#8bdbcb;white-space:pre-wrap}.h3pb details{margin-top:8px}.h3pb summary{cursor:pointer;color:#b9d0df}.h3pb .h3pb-preview{min-height:250px;margin-top:7px}.h3pb [hidden]{display:none!important}
`;
document.head.append(css);

function element(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}

function viewUrl(path) {
  const match = path.match(/ \[(input|output|temp)\]$/);
  const name = match ? path.slice(0, match.index) : path;
  const slash = name.lastIndexOf("/");
  return api.apiURL(`/view?${new URLSearchParams({
    filename: name.slice(slash + 1), subfolder: name.slice(0, Math.max(0, slash)), type: match?.[1] || "input",
  })}`);
}

function parsePrompt(source) {
  const text = source.trim().replace(/^```[^\n]*\n([\s\S]*?)\n```$/, "$1");
  const headings = new RegExp(`^[ \\t]*(?:#{1,6}[ \\t]+)?(?:\\*\\*)?(${FIELDS.map(([name]) => name).join("|")})(?:\\*\\*)?[ \\t]*(?:[:：][ \\t]*(?:\\*\\*)?[ \\t]*|(?=\\r?$))`, "gim");
  const matches = [...text.matchAll(headings)];
  if (!matches.length) throw new Error(t("未找到六段字段标题。普通描述请点击“AI 转成六段”。", "No field headings found. Use \"AI to six fields\" for a plain description."));
  if (text.slice(0, matches[0].index).trim()) throw new Error(t("首个标题前还有文字，请移入对应段落，或使用“AI 转成六段”。", "Text before the first heading: move it into a field or use \"AI to six fields\"."));
  const values = {};
  matches.forEach((match, index) => {
    const name = match[1].toLowerCase();
    if (Object.hasOwn(values, name)) throw new Error(t(`${name} 标题重复，请合并后再拆分。`, `Duplicate ${name} heading. Merge them before splitting.`));
    values[name] = text.slice(match.index + match[0].length, matches[index + 1]?.index ?? text.length).trim();
  });
  return values;
}

function install(node) {
  if (node.h3PromptBuilder) return;
  const widgets = Object.fromEntries(node.widgets.map(w => [w.name, w]));
  for (const name of [...FIELDS.map(f => f[0]), "pictures", "ai_request", "ai_read_images", "log_prompts", "ai_language"]) {
    const widget = widgets[name];
    widget.hidden = true;
    widget.options = { ...widget.options, hidden: true };
    widget.draw = () => {};
    widget.computeSize = () => [0, -4];
    if (widget.inputEl) widget.inputEl.hidden = true;
    if (widget.element) widget.element.hidden = true;
  }
  widgets.ai_request.value = 0;
  // New nodes start with the last chosen language; saved workflows restore their own value on configure.
  try {
    const saved = localStorage.getItem(LANGUAGE_KEY);
    if (AI_LANGUAGES.includes(saved)) widgets.ai_language.value = saved;
  } catch {}
  const root = element("div", "h3pb");
  const syncWidth = () => { root.style.width = `${Math.max(1, node.size[0] - 20)}px`; };
  const oldResize = node.onResize;
  node.onResize = function (...args) {
    oldResize?.apply(this, args);
    syncWidth();
  };
  root.tabIndex = 0;
  for (const type of ["pointerdown", "pointermove", "pointerup", "mousedown", "dblclick", "keydown", "keyup", "wheel"]) {
    root.addEventListener(type, e => e.stopPropagation());
  }
  let logPath;
  const i18n = localizer(() => { renderGallery(); refresh(); showLog(); });
  const local = i18n.set;
  const header = element("div", "h3pb-row");
  header.append(local(element("div", "h3pb-title"), "H3 参考提示词", "H3 Reference Prompt"), local(element("small", ""), "Ref2VA · 手动填写无需 LLM", "Ref2VA · manual editing needs no LLM"));
  root.append(header);
  const row = element("div", "h3pb-row");
  const button = (label, handler, parent = row) => {
    const btn = element("button");
    if (Array.isArray(label)) local(btn, ...label); else btn.textContent = label;
    btn.type = "button";
    btn.onclick = handler;
    parent.append(btn);
    return btn;
  };
  const importer = element("details");
  importer.append(local(element("summary", ""), "导入整段提示词", "Import a full prompt"));
  importer.append(local(element("div", "h3pb-note"), "完整 H3 提示词可按标题拆分；普通描述可结合所选参考图，用 AI 展开成六段。填入后可撤销。", "Split a full H3 prompt by its headings, or let AI expand a plain description into six fields using the selected references. Undo is available."));
  const importText = element("textarea");
  local(importText, "待导入的提示词", "Prompt to import", "ariaLabel");
  local(importText, "粘贴完整 H3 提示词，或直接描述人物、场景、动作、对白和时间安排…", "Paste a full H3 prompt, or describe the characters, scene, actions, dialogue and timing…", "placeholder");
  importText.rows = 5;
  importText.spellcheck = false;
  importText.oninput = () => { node.properties.h3_import_text = importText.value; changed(); };
  importer.append(importText);
  const importActions = element("div", "h3pb-row");
  importActions.style.marginTop = "7px";
  importer.append(importActions);
  button(["按标题拆分填入", "Split by headings"], () => {
    try {
      const values = parsePrompt(importText.value);
      saveUndo(); setFields({ ...fields(), ...values }); refresh(); changed();
      setStatus(t(`已填入 ${Object.keys(values).length} 个字段；未提供的字段保留原文。可撤销。`, `Filled ${Object.keys(values).length} fields; missing fields were kept. Undo is available.`));
    } catch (error) { setStatus(error.message); }
  }, importActions);
  const importAiBtn = button(["AI 转成六段", "AI to six fields"], () => {
    if (!importText.value.trim()) { setStatus(t("请先粘贴要转换的提示词。", "Paste the prompt to convert first.")); return; }
    void requestAI(importText.value);
  }, importActions);
  importAiBtn.classList.add("h3pb-primary");
  const importStatus = element("div", "h3pb-status");
  importer.append(importStatus);
  root.append(importer);
  root.append(row);
  const picker = element("input");
  picker.type = "file";
  picker.accept = "image/*";
  picker.multiple = true;
  picker.hidden = true;
  root.append(picker);
  let replacing = null;
  button(["＋ 添加图片", "＋ Add images"], () => { replacing = null; picker.multiple = true; picker.click(); });
  const count = element("small");
  row.append(count);
  const gallery = element("div", "h3pb-pictures");
  root.append(gallery, local(element("div", "h3pb-note"), "可多选、拖入或粘贴图片。点缩略图插入引用；拖动卡片或用箭头排序，正文编号同步更新。", "Select, drop or paste images. Click a thumbnail to insert its label; drag cards or use the arrows to reorder and the labels in the text follow."));
  const visionLabel = element("label", "h3pb-row");
  const visionInput = element("input");
  visionInput.type = "checkbox";
  visionInput.onchange = () => { widgets.ai_read_images.value = visionInput.checked; changed(); };
  visionLabel.append(visionInput, local(element("span", ""), "AI 识别参考图", "AI reads reference images"));
  root.append(visionLabel, local(element("div", "h3pb-note"), "识图时按图片顺序发送最长边 1024px 的 JPEG 副本；需要视觉模型。关闭后仅处理文字。", "Sends JPEG copies (longest side 1024px) in picture order; requires a vision model. Turn off to send text only."));
  const languageRow = element("div", "h3pb-row");
  const languageGroup = element("div", "h3pb-segment");
  languageGroup.setAttribute("role", "group");
  local(languageGroup, "AI 输出语言", "AI output language", "ariaLabel");
  const languageButtons = AI_LANGUAGES.map(value => button(value, () => {
    setLanguage(value);
    try { localStorage.setItem(LANGUAGE_KEY, value); } catch {}
    changed();
  }, languageGroup));
  const setLanguage = value => {
    widgets.ai_language.value = value;
    languageButtons.forEach((btn, index) => btn.setAttribute("aria-pressed", String(AI_LANGUAGES[index] === value)));
  };
  languageRow.append(local(element("span"), "AI 输出语言", "AI output language"), languageGroup);
  root.append(languageRow, local(element("div", "h3pb-note"), "AI 整理和转成六段时使用。English 符合 H3 官方 Ref2VA 格式；台词、歌词和画面文字始终保留原语言。", "Used by AI rewrite and AI to six fields. English follows the official H3 Ref2VA format; dialogue, lyrics and on-screen text keep their original language."));
  const logLabel = element("label", "h3pb-row");
  const logInput = element("input");
  logInput.type = "checkbox";
  logInput.onchange = () => { widgets.log_prompts.value = logInput.checked; changed(); };
  logLabel.append(logInput, local(element("span", ""), "保存提示词日志", "Save prompt logs"));
  const logLocation = element("div", "h3pb-note");
  const showLog = () => {
    logLocation.textContent = logPath === undefined
      ? t("日志目录：output/h3_prompt_logs。保存原文、最终提示词及 AI 输入/回复（TXT + JSON）。连接的 Prompt API 也需开启 log_prompts。", "Logs go to output/h3_prompt_logs: original, final prompt and AI requests/replies (TXT + JSON). The connected Prompt API must also enable log_prompts.")
      : logPath
        ? t(`本次日志：${logPath}（同名 JSON 保存结构化详情）`, `Log: ${logPath} (the JSON with the same name holds structured details)`)
        : t("本次未保存日志；请检查日志开关或控制台。", "No log saved this run; check the log switch or the console.");
  };
  showLog();
  logLocation.style.overflowWrap = "anywhere";
  root.append(logLabel, logLocation);
  const textareas = {};
  const menus = [];
  let lastField = "subject_definitions";
  let undo = null;
  let pending = null;
  let candidate = null;
  let uploading = false;
  let ignoreClickUntil = 0;
  const pictures = () => JSON.parse(widgets.pictures.value || "[]");
  const fields = () => Object.fromEntries(FIELDS.map(([name]) => [name, String(widgets[name].value ?? "")]));
  const snapshot = () => ({ fields: fields(), pictures: pictures() });
  const changed = () => { node.graph?.change(); node.graph?.setDirtyCanvas(true, true); };
  const setFields = values => {
    for (const [name] of FIELDS) widgets[name].value = textareas[name].value = values[name];
  };
  const saveUndo = () => { undo = snapshot(); undoBtn.disabled = false; };
  const insert = (value) => {
    const input = textareas[lastField];
    input.focus();
    input.setRangeText(value, input.selectionStart, input.selectionEnd, "end");
    input.dispatchEvent(new Event("input"));
  };
  function renderGallery() {
    gallery.replaceChildren();
    const paths = pictures();
    count.textContent = t(`${paths.length} 张 · 顺序对应 <Picture N>`, `${paths.length} images · order matches <Picture N>`);
    paths.forEach((path, index) => {
      const card = element("div", "h3pb-card");
      card.style.userSelect = "none";
      card.dataset.index = index;
      const img = element("img");
      img.src = viewUrl(path);
      img.alt = `<Picture ${index + 1}>`;
      img.title = `${path}\n${t("点击插入引用", "Click to insert label")}`;
      img.draggable = false;
      card.onclick = e => {
        if (!e.target.closest("button") && performance.now() >= ignoreClickUntil) insert(`<Picture ${index + 1}>`);
      };
      card.append(img, element("strong", "", `<Picture ${index + 1}>`));
      const actions = element("div", "h3pb-row");
      card.append(actions);
      const left = button("←", () => movePicture(index, index - 1), actions);
      left.title = t("向前移动", "Move earlier"); left.disabled = index === 0 || uploading;
      const right = button("→", () => movePicture(index, index + 1), actions);
      right.title = t("向后移动", "Move later"); right.disabled = index === paths.length - 1 || uploading;
      button(t("换", "Swap"), () => { replacing = index; picker.multiple = false; picker.click(); }, actions).title = t("替换图片，保留编号", "Replace image, keep its number");
      button("×", () => {
        if (uploading) return;
        saveUndo();
        const order = paths.map((_, i) => i).filter(i => i !== index);
        remapPictures(paths, order);
        setStatus(t("图片已移除；原有引用标为“已删除”，可撤销。", "Image removed; its labels are marked as deleted. Undo is available."));
      }, actions).title = t("移除图片", "Remove image");
      let drag = null;
      card.onpointerdown = e => {
        if (uploading || e.button !== 0 || e.target.closest("button")) return;
        drag = { x: e.clientX, y: e.clientY, moved: false };
        card.setPointerCapture(e.pointerId);
      };
      card.onpointermove = e => {
        if (!drag) return;
        if (Math.hypot(e.clientX - drag.x, e.clientY - drag.y) > 6) drag.moved = true;
        if (drag.moved) { e.preventDefault(); card.style.borderColor = "#8bdbcb"; }
      };
      card.onpointerup = e => {
        const moved = drag?.moved;
        drag = null; card.style.borderColor = "";
        if (!moved) return;
        ignoreClickUntil = performance.now() + 250;
        const target = document.elementFromPoint(e.clientX, e.clientY)?.closest(".h3pb-card");
        if (target && gallery.contains(target)) movePicture(index, Number(target.dataset.index));
      };
      card.onpointercancel = () => { drag = null; card.style.borderColor = ""; };
      card.ondragstart = e => e.preventDefault();
      gallery.append(card);
    });
    if (!paths.length) gallery.append(element("div", "h3pb-drop", t("＋ 将参考图片拖到这里，或点击添加图片", "＋ Drop reference images here, or click Add images")));
  }
  function remapPictures(paths, order) {
    const values = fields();
    for (const name in values) values[name] = values[name].replace(/<Picture\s+(\d+)>/g, (label, number) => {
      const old = Number(number) - 1;
      if (old >= paths.length) return label;
      const next = order.indexOf(old);
      return next < 0 ? t("<Picture 已删除>", "<Picture deleted>") : `<Picture ${next + 1}>`;
    });
    widgets.pictures.value = JSON.stringify(order.map(i => paths[i]));
    setFields(values);
    renderGallery(); refresh(); changed();
  }
  function movePicture(from, to) {
    const paths = pictures();
    if (uploading || from === to || from < 0 || to < 0 || from >= paths.length || to >= paths.length) return;
    saveUndo();
    const order = paths.map((_, i) => i);
    order.splice(to, 0, order.splice(from, 1)[0]);
    remapPictures(paths, order);
  }
  async function upload(files, replaceIndex = null) {
    if (uploading) return;
    const images = [...files].filter(f => f.type.startsWith("image/"));
    if (!images.length) return;
    uploading = true;
    saveUndo();
    setStatus(t("正在保存图片…", "Saving images…"));
    try {
      for (const file of images) {
        const form = new FormData();
        form.append("image", file); form.append("type", "input"); form.append("subfolder", "h3_prompt_builder");
        const response = await api.fetchApi("/upload/image", { method: "POST", body: form });
        if (!response.ok) throw new Error(t(`图片上传失败：HTTP ${response.status}`, `Image upload failed: HTTP ${response.status}`));
        const result = await response.json();
        const path = `${result.subfolder ? result.subfolder + "/" : ""}${result.name} [${result.type || "input"}]`;
        const paths = pictures();
        if (replaceIndex === null) paths.push(path); else paths[replaceIndex] = path;
        widgets.pictures.value = JSON.stringify(paths);
        if (replaceIndex !== null) break;
      }
      setStatus(t("图片已保存。可在输入框键入 <Pic 或点击缩略图引用。", "Images saved. Type <Pic in a field or click a thumbnail to insert a label."));
    } catch (error) { setStatus(error.message); }
    finally { uploading = false; renderGallery(); refresh(); changed(); }
  }
  picker.onchange = () => { void upload(picker.files, replacing); picker.value = ""; };
  root.addEventListener("dragover", e => { e.preventDefault(); e.stopPropagation(); });
  root.addEventListener("drop", e => { e.preventDefault(); e.stopPropagation(); void upload(e.dataTransfer.files); });
  root.addEventListener("paste", e => {
    if (e.clipboardData.files.length) { e.preventDefault(); e.stopPropagation(); void upload(e.clipboardData.files); }
  });
  for (const [name, titles, examples] of FIELDS) {
    const container = element("label", "h3pb-field");
    const label = element("div", "h3pb-label");
    label.append(local(element("span"), ...titles), element("code", "", name));
    const input = element("textarea");
    input.dataset.field = name;
    local(input, ...titles, "ariaLabel");
    local(input, ...examples, "placeholder");
    input.spellcheck = false;
    input.rows = name === "detailed_description" ? 6 : 2;
    textareas[name] = input;
    const menu = element("div", "h3pb-complete");
    menu.setAttribute("role", "listbox");
    menu.hidden = true;
    menus.push(menu);
    let matches = [], selected = 0, start = 0;
    const choose = index => {
      input.focus();
      input.setRangeText(matches[index].label, start, input.selectionStart, "end");
      widgets[name].value = input.value;
      menu.hidden = true; refresh(); changed();
    };
    const paintMenu = () => {
      menu.replaceChildren();
      matches.forEach((entry, index) => {
        const option = button("", () => choose(index), menu);
        option.setAttribute("role", "option");
        option.setAttribute("aria-selected", String(index === selected));
        option.onpointerdown = e => e.preventDefault();
        if (entry.path) { const thumb = element("img"); thumb.src = viewUrl(entry.path); thumb.alt = ""; option.append(thumb); }
        option.append(element("span", "", entry.label + (entry.description ? `  ${entry.description}` : "")));
      });
      menu.hidden = !matches.length;
    };
    const complete = () => {
      const prefix = input.value.slice(0, input.selectionStart).match(/<([A-Za-z]*(?:\s+\d*)?)$/);
      if (!prefix || input.selectionStart !== input.selectionEnd) { menu.hidden = true; return; }
      start = input.selectionStart - prefix[0].length;
      const entries = pictures().map((path, index) => ({ label: `<Picture ${index + 1}>`, path }));
      const ids = new Set();
      for (const match of textareas.subject_definitions.value.matchAll(/<Subject\s+(\d+)>[^\n]*/g)) {
        if (ids.has(match[1])) continue;
        ids.add(match[1]);
        entries.push({ label: `<Subject ${match[1]}>`, description: match[0].replace(/^<[^>]+>\s*/, "") });
      }
      matches = entries.filter(entry => entry.label.toLowerCase().startsWith(prefix[0].toLowerCase()));
      selected = 0; paintMenu();
    };
    input.onfocus = () => { lastField = name; menus.forEach(m => { m.hidden = true; }); };
    input.oninput = () => { widgets[name].value = input.value; refresh(); complete(); changed(); };
    input.onkeyup = e => { if (["ArrowLeft", "ArrowRight"].includes(e.key)) complete(); };
    input.onblur = () => { setTimeout(() => { menu.hidden = true; }, 150); };
    input.onkeydown = e => {
      if (e.isComposing || menu.hidden) return;
      if (e.key === "Escape") { e.preventDefault(); menu.hidden = true; }
      if (["ArrowDown", "ArrowUp"].includes(e.key)) {
        e.preventDefault(); selected = (selected + (e.key === "ArrowDown" ? 1 : -1) + matches.length) % matches.length; paintMenu();
      }
      if (["Enter", "Tab"].includes(e.key)) { e.preventDefault(); choose(selected); }
    };
    container.append(label, input, menu);
    if (name === "detailed_description") container.append(local(element("small", ""), "输入 <Pic / <Sub 补全 · ↑↓ 选择，Tab / Enter 插入。Shot 编号是镜头序号；At 00:06.000 表示第 6 秒切镜。", "Type <Pic / <Sub to complete · ↑↓ to choose, Tab / Enter to insert. Shot numbers count shots; At 00:06.000 cuts at 6 seconds."));
    root.append(container);
  }
  const warning = element("div", "h3pb-warning");
  root.append(warning);
  const actions = element("div", "h3pb-row");
  root.append(actions);
  button(["填入示例", "Fill example"], () => {
    saveUndo(); setFields(Object.fromEntries(FIELDS.map(([name, , examples]) => [name, t(...examples)]))); refresh(); changed();
    setStatus(t("示例已填入，可修改或撤销。示例人物需按你的参考图调整。", "Example filled; edit or undo it. Adjust the example character to your references."));
  }, actions);
  const undoBtn = button(["撤销上次操作", "Undo last change"], () => {
    if (!undo) return;
    setFields(undo.fields); widgets.pictures.value = JSON.stringify(undo.pictures);
    undo = null; undoBtn.disabled = true; renderGallery(); refresh(); changed();
    setStatus(t("已还原文本和图片顺序。", "Text and image order restored."));
  }, actions);
  undoBtn.disabled = true;
  const aiBtn = button(["AI 整理", "AI rewrite"], () => { void requestAI(); }, actions);
  async function requestAI(source = null) {
    if (pending || uploading) return;
    const configInput = node.inputs.find(i => i.name === "prompt_api");
    if (configInput?.link == null) { setStatus(t("连接 H3 Prompt API 后即可使用；手动编辑无需连接。", "Connect H3 Prompt API to use AI; manual editing needs no connection.")); return; }
    aiBtn.disabled = importAiBtn.disabled = true;
    try {
      const before = JSON.stringify(snapshot());
      const graph = await app.graphToPrompt();
      const id = String(node.id);
      if (!graph.output[id]) throw new Error(t("请在主画布中使用 AI 整理按钮。节点不能处于禁用状态。", "Use AI rewrite from the main canvas, with the node not bypassed or muted."));
      const output = {};
      function include(key) {
        if (output[key]) return;
        const entry = graph.output[key];
        if (!entry) throw new Error(t("未找到上游配置节点，请检查连接。", "Upstream configuration node not found; check the connection."));
        output[key] = structuredClone(entry);
        for (const value of Object.values(entry.inputs)) if (Array.isArray(value) && value.length === 2 && typeof value[0] === "string") include(value[0]);
      }
      include(id);
      if (source !== null) {
        for (const [name] of FIELDS) output[id].inputs[name] = "";
        output[id].inputs.detailed_description = source;
      }
      const request = Math.floor(Math.random() * 0x7ffffffe) + 1;
      output[id].inputs.ai_request = request;
      pending = { request, before, source, promptId: null };
      setStatus(source === null
        ? t("AI 整理已提交；仅运行此提示词节点。等待结果期间仍可编辑原文。", "AI rewrite queued; only this prompt node runs. You can keep editing while waiting.")
        : t("正在将导入的提示词转成六段；仅运行此提示词节点，完成后回填。", "Converting the imported prompt into six fields; only this prompt node runs and the result fills in when done."));
      const queued = await api.queuePrompt(0, { output, workflow: graph.workflow });
      if (pending?.request === request) pending.promptId = queued.prompt_id;
    } catch (error) { pending = null; aiBtn.disabled = importAiBtn.disabled = false; setStatus(error.message || t("AI 提交失败，请检查队列。", "AI request failed to queue; check the queue.")); }
  }
  aiBtn.classList.add("h3pb-primary");
  const applyBtn = button(["应用 AI 结果", "Apply AI result"], () => {
    if (!candidate) return;
    saveUndo(); setFields(candidate); candidate = null; applyBtn.hidden = true; refresh(); changed();
    setStatus(t("AI 结果已回填；可继续编辑或撤销。", "AI result applied; edit or undo it."));
  }, actions);
  applyBtn.hidden = true;
  root.append(local(element("div", "h3pb-note"), "AI 使用 prompt_api 连接的模型；开启识图时会读取参考图，远端模型会收到压缩图片。原始图片仍用于视频生成。", "AI uses the model connected to prompt_api. With image reading on, a remote model receives compressed copies; video generation still uses the originals."));
  const status = element("div", "h3pb-status");
  status.setAttribute("role", "status");
  root.append(status);
  function setStatus(message) { status.textContent = importStatus.textContent = message; }
  const details = element("details");
  details.append(local(element("summary", ""), "查看完整 H3 提示词", "View full H3 prompt"));
  const copyRow = element("div", "h3pb-row");
  details.append(copyRow);
  button(["复制完整提示词", "Copy full prompt"], async () => {
    try { await navigator.clipboard.writeText(preview.value); setStatus(t("完整提示词已复制。", "Full prompt copied.")); }
    catch { preview.focus(); preview.select(); setStatus(t("请按 Ctrl+C 复制已选中的提示词。", "Press Ctrl+C to copy the selected prompt.")); }
  }, copyRow);
  const preview = element("textarea", "h3pb-preview");
  preview.readOnly = true; local(preview, "完整 H3 提示词", "Full H3 prompt", "ariaLabel");
  details.append(preview); root.append(details);
  function refresh() {
    preview.value = FIELDS.map(([name]) => `${name}:\n${widgets[name].value ?? ""}`).join("\n\n");
    const total = pictures().length;
    const unresolved = [...new Set([...preview.value.matchAll(/<Picture\s+(\d+)>/g)].map(m => Number(m[1])).filter(n => n < 1 || n > total))];
    const messages = [];
    if (!total) messages.push(t("尚未选择参考图：可先编辑提示词；接入 Ref2VA 生成时请添加图片。", "No reference images yet: you can edit the prompt first; add images before Ref2VA generation."));
    if (unresolved.length) messages.push(t("缺少图片：", "Missing images: ") + unresolved.map(n => `<Picture ${n}>`).join(t("、", ", ")));
    if (DELETED_PICTURE.test(preview.value)) messages.push(t("有图片引用已删除，请替换正文中的 <Picture 已删除>。", "Some image labels were deleted; replace <Picture deleted> in the text."));
    warning.textContent = messages.join("\n");
  }
  function restore() {
    widgets.ai_request.value = 0;
    if (typeof widgets.ai_read_images.value !== "boolean") widgets.ai_read_images.value = true;
    visionInput.checked = widgets.ai_read_images.value;
    if (typeof widgets.log_prompts.value !== "boolean") widgets.log_prompts.value = true;
    logInput.checked = widgets.log_prompts.value;
    setLanguage(AI_LANGUAGES.includes(widgets.ai_language.value) ? widgets.ai_language.value : "English");
    importText.value = node.properties.h3_import_text || "";
    setFields(fields()); renderGallery(); refresh();
    syncWidth();
  }
  const oldConfigure = node.onConfigure;
  node.onConfigure = function (...args) { oldConfigure?.apply(this, args); restore(); };
  const oldExecuted = node.onExecuted;
  node.onExecuted = function (data) {
    oldExecuted?.apply(this, arguments);
    logPath = data.h3_log?.[0] ?? null;
    showLog();
    if (!pending || data.h3_ai_request?.[0] !== pending.request) return;
    const values = data.h3_fields?.[0];
    const unchanged = JSON.stringify(snapshot()) === pending.before && (pending.source === null || importText.value === pending.source);
    pending = null; aiBtn.disabled = importAiBtn.disabled = false;
    if (!values) { setStatus(t("AI 未返回可用字段，原文已保留。", "AI returned no usable fields; the original was kept.")); return; }
    if (unchanged) {
      saveUndo(); setFields(values); candidate = null; applyBtn.hidden = true; refresh(); changed();
      setStatus(t("AI 结果已回填六个输入框，可继续修改或撤销。", "AI result filled the six fields; edit or undo it."));
    } else {
      candidate = values; applyBtn.hidden = false;
      setStatus(t("AI 已完成。期间你修改过内容，原文已保留；点击“应用 AI 结果”可替换。", "AI finished. You edited meanwhile, so your text was kept; click \"Apply AI result\" to replace it."));
    }
  };
  const failed = e => {
    if (!pending || e.detail.prompt_id !== pending.promptId) return;
    pending = null; aiBtn.disabled = importAiBtn.disabled = false;
    setStatus(t("AI 执行失败或已中断，原文未改动。请查看队列错误信息。", "AI failed or was interrupted; the original is unchanged. Check the queue error."));
  };
  api.addEventListener("execution_error", failed);
  api.addEventListener("execution_interrupted", failed);
  const oldRemoved = node.onRemoved;
  node.onRemoved = function (...args) {
    api.removeEventListener("execution_error", failed); api.removeEventListener("execution_interrupted", failed);
    i18n.dispose();
    oldRemoved?.apply(this, args);
  };
  node.addDOMWidget("h3_ref_editor", "custom", root, {
    serialize: false, hideOnZoom: false, getMinHeight: () => 750, getHeight: () => 1030,
    onDraw: widget => { widget.width = node.size[0]; },
  });
  node.h3PromptBuilder = { root, restore };
  node.setSize([Math.max(640, node.size[0]), Math.max(1130, node.size[1])]);
  restore();
}

app.registerExtension({
  name: "H3MotionContext.PromptBuilder",
  nodeCreated(node) { if (node.comfyClass === "MiniMaxH3PromptBuilder") install(node); },
  loadedGraphNode(node) { if (node.comfyClass === "MiniMaxH3PromptBuilder") { install(node); node.h3PromptBuilder.restore(); } },
});
