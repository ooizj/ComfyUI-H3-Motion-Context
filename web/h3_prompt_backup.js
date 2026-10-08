import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const css = document.createElement("style");
css.textContent = `
.h3-backup{box-sizing:border-box;display:flex;flex-direction:column;gap:10px;width:100%;height:100%;overflow:auto;padding:14px;background:#131b23;color:#e4ebf2;border:1px solid #344352;border-radius:9px;font:13px/1.5 system-ui,sans-serif;cursor:default}
.h3-backup *{box-sizing:border-box}.h3-backup button{border:1px solid #405366;background:#223343;border-radius:5px;padding:5px 10px;color:inherit;font:inherit;cursor:pointer}.h3-backup button:hover{background:#30485c}.h3-backup button:disabled{opacity:.4;cursor:default}.h3-backup button:focus-visible,.h3-backup textarea:focus{outline:1px solid #75cabc}
.h3-backup-row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.h3-backup-gallery{display:flex;gap:8px;flex-shrink:0;overflow-x:auto;min-height:150px;padding:4px 0 10px;scrollbar-color:#648f9f #0b131b}.h3-backup-card{flex:0 0 142px;border:1px solid #344d5d;border-radius:6px;padding:6px;background:#1b2732}.h3-backup-card img{display:block;width:128px;height:90px;object-fit:contain;background:#10161c;cursor:pointer}.h3-backup-card strong{display:block;color:#8bdbcb;text-align:center;font-size:12px}.h3-backup-card button{padding:2px 7px}.h3-backup-card .h3-backup-row{gap:3px;justify-content:center}
.h3-backup textarea{flex:1;min-height:180px;width:100%;resize:none;padding:10px;border:1px solid #344352;border-radius:5px;background:#0c141c;color:inherit;font:13px/1.6 system-ui,sans-serif}.h3-backup-path,.h3-backup-status{white-space:pre-wrap;overflow-wrap:anywhere;user-select:text;color:#a6b7c6;font-size:12px}.h3-backup .h3-backup-primary{background:#275b53;border-color:#559486}.h3-backup-empty{align-self:center;color:#a6b7c6}.h3-backup-status:empty{display:none}
.h3-backup-dialog{width:min(1000px,92vw);height:min(740px,88vh);max-width:92vw;max-height:88vh;margin:auto;padding:0;border:1px solid #405366;border-radius:10px;background:#131b23;color:#e4ebf2;font:13px/1.5 system-ui,sans-serif}.h3-backup-dialog::backdrop{background:#0009}.h3-backup-dialog *{box-sizing:border-box}.h3-backup-browser{height:100%;display:flex;flex-direction:column;gap:12px;padding:18px}.h3-backup-browser h3{margin:0;font-size:18px}.h3-backup-browser button{padding:7px 12px;border:1px solid #405366;border-radius:5px;background:#223343;color:inherit;font:inherit;cursor:pointer}.h3-backup-browser button:disabled{opacity:.45;cursor:default}.h3-backup-browser button:focus-visible,.h3-backup-preview textarea:focus{outline:2px solid #75cabc}.h3-backup-browser button[aria-pressed=true]{border-color:#8bdbcb;background:#275b53}
.h3-backup-browser-body{display:flex;gap:16px;flex:1;min-height:0}.h3-backup-list{flex:0 0 270px;overflow:auto;display:flex;flex-direction:column;gap:8px;padding:2px}.h3-backup-browser .h3-backup-entry{text-align:left;width:100%;padding:10px;flex-shrink:0;overflow-wrap:anywhere}.h3-backup-entry img{float:left;width:64px;height:52px;object-fit:contain;margin:0 8px 5px 0;background:#0c141c}.h3-backup-entry small{display:block;color:#a6b7c6}.h3-backup-snippet{clear:both;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;margin-top:6px;font-size:12px}
.h3-backup-preview{flex:1;min-width:0;min-height:0;display:flex;flex-direction:column;gap:10px;overflow:auto}.h3-backup-preview-images{display:flex;gap:8px;overflow:auto;flex-shrink:0;max-height:190px}.h3-backup-preview-images figure{margin:0;flex:0 0 160px}.h3-backup-preview-images img{display:block;width:160px;height:130px;object-fit:contain;background:#0c141c}.h3-backup-preview-images figcaption{text-align:center;color:#8bdbcb}.h3-backup-preview textarea{flex:1;min-height:180px;width:100%;resize:none;padding:10px;border:1px solid #344352;border-radius:5px;background:#0c141c;color:inherit;font:13px/1.6 system-ui,sans-serif}.h3-backup-browser-footer{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.h3-backup-browser-footer small{flex:1;color:#a6b7c6}.h3-backup-browser .h3-backup-primary{background:#275b53;border-color:#559486}
@media(max-width:650px){.h3-backup-browser-body{flex-direction:column}.h3-backup-list{flex:0 0 150px}.h3-backup-browser{padding:12px}.h3-backup-preview-images img{height:90px}.h3-backup-preview textarea{min-height:100px}}
`;
document.head.append(css);

function element(tag, className = "", text = "") {
  const el = document.createElement(tag);
  el.className = className;
  el.textContent = text;
  return el;
}

function viewUrl(path) {
  const match = path.match(/ \[(input|output|temp)\]$/);
  const name = (match ? path.slice(0, match.index) : path).replaceAll("\\", "/");
  const slash = name.lastIndexOf("/");
  return api.apiURL(`/view?${new URLSearchParams({
    filename: name.slice(slash + 1), subfolder: name.slice(0, Math.max(0, slash)), type: match?.[1] || "input",
  })}`);
}

function install(node) {
  if (node.h3PromptBackup) return;
  const widgets = Object.fromEntries(node.widgets.map(widget => [widget.name, widget]));
  for (const name of ["pictures", "prompt"]) {
    const widget = widgets[name];
    widget.hidden = true;
    widget.options = { ...widget.options, hidden: true };
    widget.draw = () => {};
    widget.computeSize = () => [0, -4];
    if (widget.inputEl) widget.inputEl.hidden = true;
    if (widget.element) widget.element.hidden = true;
  }
  const root = element("div", "h3-backup");
  root.tabIndex = 0;
  for (const type of ["pointerdown", "pointermove", "pointerup", "mousedown", "dblclick", "keydown", "keyup", "wheel"]) {
    root.addEventListener(type, e => {
      if (type === "keydown" && (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") return;
      e.stopPropagation();
    });
  }
  let busy = false;
  let replacing = null;
  const pictures = () => JSON.parse(widgets.pictures.value || "[]");
  const changed = () => { node.graph?.change(); node.setDirtyCanvas(true); };
  const button = (label, action, parent) => {
    const control = element("button", "", label);
    control.type = "button";
    control.onclick = action;
    parent.append(control);
    return control;
  };
  const toolbar = element("div", "h3-backup-row");
  const picker = element("input");
  picker.type = "file";
  picker.accept = "image/*";
  picker.hidden = true;
  const add = button("＋ 添加图片", () => { replacing = null; picker.multiple = true; picker.click(); }, toolbar);
  const count = element("span");
  toolbar.append(count, picker);
  const gallery = element("div", "h3-backup-gallery");
  const label = element("label", "", "提示词");
  const prompt = element("textarea");
  prompt.placeholder = "输入或粘贴提示词…";
  prompt.setAttribute("aria-label", "提示词");
  prompt.spellcheck = false;
  prompt.oninput = () => { widgets.prompt.value = prompt.value; changed(); };
  const footer = element("div", "h3-backup-row");
  const backup = button("backup", () => void save(), footer);
  backup.className = "h3-backup-primary";
  const load = button("load", () => void browseBackups(), footer);
  let backupDialog = null;
  const location = element("div", "h3-backup-path", "备份目录：output/h3_prompt_backups");
  const status = element("div", "h3-backup-status");
  status.setAttribute("role", "status");
  root.append(toolbar, gallery, label, prompt, footer, location, status);

  function renderGallery() {
    gallery.replaceChildren();
    const paths = pictures();
    count.textContent = `${paths.length} 张`;
    paths.forEach((path, index) => {
      const card = element("div", "h3-backup-card");
      const img = element("img");
      img.src = viewUrl(path);
      img.alt = `<Picture ${index + 1}>`;
      img.title = `${path}\n点击插入图片引用`;
      img.draggable = false;
      img.onclick = () => {
        if (busy) return;
        prompt.focus();
        prompt.setRangeText(img.alt, prompt.selectionStart, prompt.selectionEnd, "end");
        prompt.dispatchEvent(new Event("input"));
      };
      const actions = element("div", "h3-backup-row");
      card.append(img, element("strong", "", img.alt), actions);
      const left = button("←", () => move(index, index - 1), actions);
      left.title = "向前移动"; left.disabled = busy || index === 0;
      const right = button("→", () => move(index, index + 1), actions);
      right.title = "向后移动"; right.disabled = busy || index === paths.length - 1;
      button("换", () => { replacing = index; picker.multiple = false; picker.click(); }, actions).disabled = busy;
      button("×", () => reorder(paths.map((_, i) => i).filter(i => i !== index)), actions).disabled = busy;
      gallery.append(card);
    });
    if (!paths.length) gallery.append(element("div", "h3-backup-empty", "添加、拖入或粘贴图片"));
    add.disabled = backup.disabled = load.disabled = prompt.readOnly = busy;
  }

  function reorder(order) {
    if (busy) return;
    const paths = pictures();
    prompt.value = prompt.value.replace(/<Picture\s+(\d+)>/g, (label, number) => {
      const old = Number(number) - 1;
      if (old < 0 || old >= paths.length) return label;
      const next = order.indexOf(old);
      return next < 0 ? "<Picture 已删除>" : `<Picture ${next + 1}>`;
    });
    widgets.prompt.value = prompt.value;
    widgets.pictures.value = JSON.stringify(order.map(index => paths[index]));
    renderGallery(); changed();
  }

  function move(from, to) {
    const order = pictures().map((_, index) => index);
    order.splice(to, 0, order.splice(from, 1)[0]);
    reorder(order);
  }

  async function upload(files, replaceIndex = null) {
    if (busy) return;
    const images = [...files].filter(file => file.type.startsWith("image/"));
    if (!images.length) return;
    busy = true; renderGallery();
    status.textContent = "正在添加图片…";
    try {
      for (const file of images) {
        const form = new FormData();
        form.append("image", file); form.append("type", "input"); form.append("subfolder", "h3_prompt_backup");
        const response = await api.fetchApi("/upload/image", { method: "POST", body: form });
        if (!response.ok) throw new Error(`图片上传失败：HTTP ${response.status}`);
        const result = await response.json();
        const path = `${result.subfolder ? result.subfolder + "/" : ""}${result.name} [${result.type || "input"}]`;
        const paths = pictures();
        if (replaceIndex === null) paths.push(path); else paths[replaceIndex] = path;
        widgets.pictures.value = JSON.stringify(paths);
        if (replaceIndex !== null) break;
      }
      status.textContent = "";
    } catch (error) { status.textContent = error.message; }
    finally { busy = false; renderGallery(); changed(); }
  }
  picker.onchange = () => { void upload(picker.files, replacing); picker.value = ""; };
  root.addEventListener("dragover", e => { e.preventDefault(); e.stopPropagation(); });
  root.addEventListener("drop", e => { e.preventDefault(); e.stopPropagation(); void upload(e.dataTransfer.files); });
  root.addEventListener("paste", e => {
    if (e.clipboardData.files.length) { e.preventDefault(); e.stopPropagation(); void upload(e.clipboardData.files); }
  });

  async function save() {
    if (busy) return;
    busy = true; renderGallery();
    status.textContent = "正在备份…";
    try {
      const response = await api.fetchApi("/h3_motion_context/prompt_backup", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: prompt.value, pictures: pictures() }),
      });
      if (response.status === 404) throw new Error("请重启 ComfyUI 并刷新页面，以加载备份功能。");
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || `备份失败：HTTP ${response.status}`);
      location.textContent = `备份目录：${result.directory}`;
      status.textContent = `已备份 ${result.image_count} 张图片和提示词\n${result.backup_path}`;
      node.properties.h3_backup_path = result.backup_path;
      changed();
    } catch (error) { status.textContent = error.message; }
    finally { busy = false; renderGallery(); }
  }

  async function browseBackups() {
    if (busy) return;
    busy = true; renderGallery();
    const dialog = element("dialog", "h3-backup-dialog");
    backupDialog = dialog;
    dialog.setAttribute("aria-label", "预览并载入备份");
    const browser = element("div", "h3-backup-browser");
    const body = element("div", "h3-backup-browser-body");
    const list = element("div", "h3-backup-list", "正在读取备份…");
    const preview = element("div", "h3-backup-preview");
    const detail = element("div", "h3-backup-path", "选择左侧备份以预览");
    const images = element("div", "h3-backup-preview-images");
    const text = element("textarea");
    text.readOnly = true;
    text.setAttribute("aria-label", "备份提示词预览");
    text.placeholder = "提示词预览";
    preview.append(detail, images, text);
    body.append(list, preview);
    const actions = element("div", "h3-backup-browser-footer");
    actions.append(element("small", "", "载入将替换当前节点中的图片和提示词。"));
    let selected = null;
    let previewController = null;
    const listController = new AbortController();
    const apply = button("载入所选备份", () => {
      if (!selected) return;
      widgets.pictures.value = JSON.stringify(selected.pictures);
      widgets.prompt.value = prompt.value = selected.prompt;
      node.properties.h3_backup_path = selected.backup_path;
      status.textContent = `已载入 ${selected.pictures.length} 张图片和提示词\n${selected.backup_path}`;
      changed();
      dialog.close();
    }, actions);
    apply.className = "h3-backup-primary";
    apply.disabled = true;
    button("取消", () => dialog.close(), actions);
    browser.append(element("h3", "", "加载备份"), body, actions);
    dialog.append(browser);
    for (const type of ["pointerdown", "pointermove", "pointerup", "mousedown", "dblclick", "keydown", "keyup", "wheel"]) {
      dialog.addEventListener(type, e => e.stopPropagation());
    }
    dialog.addEventListener("close", () => {
      listController.abort(); previewController?.abort();
      dialog.remove(); backupDialog = null;
      busy = false; renderGallery();
    }, { once: true });
    document.body.append(dialog);
    dialog.showModal();

    async function previewEntry(entry, control) {
      previewController?.abort();
      const controller = new AbortController();
      previewController = controller;
      selected = null; apply.disabled = true;
      for (const item of list.children) item.setAttribute("aria-pressed", String(item === control));
      detail.textContent = "正在读取预览…";
      images.replaceChildren(); text.value = "";
      try {
        const response = await api.fetchApi(`/h3_motion_context/prompt_backups/${encodeURIComponent(entry.id)}`, {
          signal: controller.signal, cache: "no-store",
        });
        const result = await response.json();
        if (controller.signal.aborted || !dialog.open) return;
        if (!response.ok) throw new Error(result.error || `读取失败：HTTP ${response.status}`);
        detail.textContent = `${result.pictures.length} 张图片\n${result.backup_path}`;
        text.value = result.prompt;
        for (const [index, path] of result.pictures.entries()) {
          const figure = element("figure");
          const img = element("img");
          img.src = viewUrl(path); img.alt = `<Picture ${index + 1}>`;
          figure.append(img, element("figcaption", "", img.alt));
          images.append(figure);
        }
        if (!result.pictures.length) images.append(element("div", "h3-backup-empty", "此备份仅包含提示词"));
        selected = result; apply.disabled = false;
      } catch (error) {
        if (!controller.signal.aborted && dialog.open) detail.textContent = error.message;
      }
    }

    try {
      const response = await api.fetchApi("/h3_motion_context/prompt_backups", {
        signal: listController.signal, cache: "no-store",
      });
      if (response.status === 404) throw new Error("请重启 ComfyUI 并刷新页面，以加载备份列表。");
      const result = await response.json();
      if (listController.signal.aborted || !dialog.open) return;
      if (!response.ok) throw new Error(result.error || `读取失败：HTTP ${response.status}`);
      list.replaceChildren();
      let first = null;
      for (const entry of result.backups) {
        const control = button("", () => void previewEntry(entry, control), list);
        control.className = "h3-backup-entry";
        control.setAttribute("aria-pressed", "false");
        control.title = entry.id;
        if (entry.cover) {
          const cover = element("img");
          cover.src = viewUrl(entry.cover); cover.alt = "备份缩略图"; cover.loading = "lazy";
          control.append(cover);
        }
        const time = new Date(entry.created_at);
        control.append(element("strong", "", Number.isNaN(time.getTime()) ? entry.id : time.toLocaleString()));
        if (entry.error) {
          control.append(element("small", "", entry.error)); control.disabled = true;
        } else {
          control.append(element("small", "", `${entry.image_count} 张图片`),
            element("div", "h3-backup-snippet", entry.prompt_preview || "（空提示词）"));
          first ??= { entry, control };
        }
      }
      if (first) void previewEntry(first.entry, first.control);
      else detail.textContent = result.backups.length ? "没有可载入的备份，请检查列表中的错误。" : "暂无备份，先点击 backup 保存。";
    } catch (error) {
      if (!listController.signal.aborted && dialog.open) list.textContent = error.message;
    }
  }

  const oldRemoved = node.onRemoved;
  node.onRemoved = function (...args) {
    backupDialog?.close();
    oldRemoved?.apply(this, args);
  };

  const syncWidth = () => { root.style.width = `${Math.max(1, node.size[0] - 20)}px`; };
  const oldResize = node.onResize;
  node.onResize = function (...args) { oldResize?.apply(this, args); syncWidth(); };
  function restore() {
    if (node.title === "H3 Image & Prompt Backup") node.title = "H3 Image & Prompt";
    prompt.value = widgets.prompt.value ?? "";
    status.textContent = node.properties.h3_backup_path ? `上次备份：${node.properties.h3_backup_path}` : "";
    renderGallery(); syncWidth();
  }
  const oldConfigure = node.onConfigure;
  node.onConfigure = function (...args) { oldConfigure?.apply(this, args); restore(); };
  node.addDOMWidget("h3_backup_editor", "custom", root, {
    serialize: false, hideOnZoom: false, getMinHeight: () => 480, getHeight: () => 570,
    onDraw: widget => { widget.width = node.size[0]; },
  });
  node.h3PromptBackup = { restore };
  node.setSize([Math.max(600, node.size[0]), Math.max(650, node.size[1])]);
  restore();
  void (async () => {
    try {
      const response = await api.fetchApi("/h3_motion_context/prompt_backup");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const result = await response.json();
      location.textContent = `备份目录：${result.directory}`;
    } catch { status.textContent = "无法读取备份目录，请重启 ComfyUI 并刷新页面。"; }
  })();
}

app.registerExtension({
  name: "H3MotionContext.PromptBackup",
  nodeCreated(node) { if (node.comfyClass === "MiniMaxH3PromptBackup") install(node); },
  loadedGraphNode(node) { if (node.comfyClass === "MiniMaxH3PromptBackup") { install(node); node.h3PromptBackup.restore(); } },
});
