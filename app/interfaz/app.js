"use strict";

const $ = id => document.getElementById(id);
const selected = new Set();
let state = {items: [], busy: false};
let currentId = null;
let populatedId = null;
let view = "compare";
let videoKey = "";
let uploading = false;
let requestBusy = false;
let closed = false;
let listSignature = "";
let toastTimer;
let pollTimer;
let saving = Promise.resolve();
let tailCursor = 0;

function toast(message, error = false) {
  $("toast").textContent = message;
  $("toast").classList.toggle("error", error);
  $("toast").classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $("toast").classList.add("hidden"), error ? 8000 : 4000);
}

async function api(path, body) {
  const response = await fetch(path, body === undefined ? {credentials: "same-origin"} : {
    method: "POST", headers: {"Content-Type": "application/json"},
    credentials: "same-origin", body: JSON.stringify(body)
  });
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || "No se pudo completar la acción.");
  return value;
}

function duration(seconds) {
  if (seconds == null) return "Por revisar";
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${Math.floor(seconds % 60).toString().padStart(2,"0")}`;
}

function bytes(size) {
  return size < 1024 * 1024 ? `${Math.max(1, Math.round(size / 1024))} KB` : `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function current() { return state.items.find(item => item.id === currentId); }
function pendingIds() { return state.items.filter(item => selected.has(item.id) && item.state !== "done" && item.width).map(item => item.id); }

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function settingsFromControls() {
  const frames = $("trim-frames").valueAsNumber;
  const seconds = $("trim-seconds").valueAsNumber;
  const validFrames = Number.isSafeInteger(frames) && frames >= 0;
  const validSeconds = Number.isFinite(seconds) && seconds >= 0;
  if ($("trim").checked && (($("trim-mode").value === "fotogramas" && !validFrames) ||
      ($("trim-mode").value === "segundos" && !validSeconds))) {
    throw new Error("Introduce una cantidad válida: fotogramas enteros o segundos iguales o mayores que cero.");
  }
  return {perfil: $("profile").value, modo: $("quality").value, recortar: $("trim").checked,
    recorte_modo: $("trim-mode").value,
    recorte_fotogramas: validFrames ? frames : current()?.settings.recorte_fotogramas ?? 90,
    recorte_segundos: validSeconds ? seconds : current()?.settings.recorte_segundos ?? 3,
    inteligente: $("smart").checked, rtl: $("rtl").checked, rect: $("region").value.trim()};
}

function trimLabel(settings) {
  if (!settings.recortar) return "Sin recorte";
  if (settings.recorte_modo === "fotogramas") return `Recorte: ${settings.recorte_fotogramas} fotogramas`;
  if (settings.recorte_modo === "segundos") return `Recorte: ${settings.recorte_segundos} s`;
  return "Recorte automático";
}

function renderTrim() {
  const item = current();
  const enabled = $("trim").checked;
  const mode = $("trim-mode").value;
  const locked = !item || !item.width || state.busy || state.closing || uploading || requestBusy;
  $("trim-options").classList.toggle("hidden", !enabled);
  $("trim-frames-field").classList.toggle("hidden", mode !== "fotogramas");
  $("trim-seconds-field").classList.toggle("hidden", mode !== "segundos");
  $("trim-mode").disabled = locked || !enabled;
  $("trim-frames").disabled = locked || !enabled || mode !== "fotogramas";
  $("trim-seconds").disabled = locked || !enabled || mode !== "segundos";
  const summary = $("trim-summary");
  summary.classList.remove("invalid");
  if (!enabled) { summary.textContent = "Se conservará todo el cierre del vídeo."; return; }
  if (!item?.width) { summary.textContent = "Selecciona un vídeo para ajustar su recorte final."; return; }
  let frames;
  let seconds;
  if (mode === "auto") {
    let profile = $("profile").value;
    if (profile === "auto") profile = item.height > item.width ? "short" : Math.abs(item.fps - 24) <= .1 ? "explainer" : Math.abs(item.fps - 30) <= .1 ? "cinematic" : "";
    if (!profile) { summary.textContent = "Selecciona un formato para calcular el recorte automático."; return; }
    frames = profile === "explainer" ? 72 : profile === "legacy" ? 60 : profile === "manual" ? 0 : 90;
    seconds = frames / item.fps;
  } else {
    const input = mode === "fotogramas" ? $("trim-frames") : $("trim-seconds");
    // Inactive controls are also read while processing a video.
    const value = input.valueAsNumber;
    if (!Number.isFinite(value) || value < 0 || (mode === "fotogramas" && !Number.isInteger(value))) {
      summary.textContent = "Introduce una cantidad válida para recortar.";
      summary.classList.add("invalid"); return;
    }
    frames = mode === "fotogramas" ? value : null;
    seconds = frames === null ? value : value / item.fps;
  }
  const time = value => Number(value.toFixed(3)).toLocaleString("es");
  if (seconds >= item.duration) {
    summary.textContent = "Este recorte eliminaría todo el vídeo. Reduce la cantidad.";
    summary.classList.add("invalid");
  } else if (!seconds) {
    summary.textContent = "Con 0 se conserva todo el cierre del vídeo.";
  } else {
    summary.textContent = frames === null ? `Se quitarán ${time(seconds)} s del final.` : `Se quitarán ${frames} fotogramas del final (≈ ${time(seconds)} s).`;
    summary.textContent += ` Duración estimada: ${time(item.duration - seconds)} s.`;
  }
}

function clockTime(seconds) {
  const ms = Math.max(0, Math.round(seconds * 1000));
  return `${Math.floor(ms / 60000).toString().padStart(2,"0")}:${(Math.floor(ms / 1000) % 60).toString().padStart(2,"0")}.${(ms % 1000).toString().padStart(3,"0")}`;
}

function tailCut(item) {
  const settings = settingsFromControls();
  const total = item.tail_total_frames;
  if (!settings.recortar) return {keep:total, seconds:0};
  if (settings.recorte_modo === "segundos") return {keep:Math.ceil((item.duration - settings.recorte_segundos) * item.fps - 1e-6), seconds:settings.recorte_segundos};
  let frames = settings.recorte_fotogramas;
  if (settings.recorte_modo === "auto") {
    let profile = settings.perfil;
    if (profile === "auto") {
      const ratio = item.width / item.height;
      profile = item.height > item.width && Math.abs(ratio - 406/720) < .04 ? "short" :
        Math.abs(ratio - 16/9) < .04 && Math.abs(item.fps - 24) <= .1 ? "explainer" :
        Math.abs(ratio - 16/9) < .04 && Math.abs(item.fps - 30) <= .1 ? "cinematic" : null;
    }
    if (!profile) throw new Error("Elige un formato o un recorte personalizado para marcar el corte.");
    frames = profile === "explainer" ? 72 : profile === "legacy" ? 60 : profile === "manual" ? 0 : 90;
  }
  return {keep:total - frames, seconds:frames / item.fps};
}

function renderTail() {
  const item = current();
  const visible = view === "tail";
  $("tail-panel").classList.toggle("hidden", !visible);
  $("compare-caption").classList.toggle("hidden", visible);
  $("compare-controls").classList.toggle("hidden", visible);
  if (!visible) return;
  const locked = !item?.width || state.busy || state.closing || uploading || requestBusy;
  $("tail-window").disabled = locked;
  $("tail-load").disabled = locked;
  $("tail-load").textContent = item?.tail ? "Actualizar cierre" : "Preparar cierre";
  const available = !!item?.tail;
  $("tail-editor").classList.toggle("hidden", !available);
  for (const id of ["tail-position","tail-back","tail-forward","tail-set-cut","tail-jump-cut"]) $(id).disabled = locked || !available;
  $("tail-error").classList.toggle("hidden", !item?.tail_error);
  $("tail-error").textContent = item?.tail_error || "";
  if (!available) return;
  const first = item.tail_precise ? item.tail_start_frame : Math.round(item.tail_start * item.fps);
  const last = item.tail_total_frames - 1;
  tailCursor = Math.min(last, Math.max(first, tailCursor));
  $("tail-position").min = first;
  $("tail-position").max = last;
  $("tail-position").value = tailCursor;
  $("tail-position-label").textContent = `${clockTime(item.tail_start + (tailCursor - first) / item.fps)} · #${tailCursor + 1}`;
  $("tail-start").textContent = clockTime(item.tail_start);
  $("tail-end").textContent = clockTime(item.duration);
  $("tail-back").disabled ||= tailCursor <= first;
  $("tail-forward").disabled ||= tailCursor >= last;
  try {
    const cut = tailCut(item);
    const percent = Math.max(0, Math.min(100, (cut.keep - first) / (last + 1 - first) * 100));
    $("tail-timeline").style.setProperty("--cut", `${percent}%`);
    $("tail-cut-marker").style.left = `${percent}%`;
    $("tail-cut-summary").textContent = cut.keep <= 0 ? "El corte actual eliminaría todo el vídeo. Elige otro punto." :
      cut.keep < first ? "El corte está antes de este tramo. Amplía los segundos de la vista." :
      `Último fotograma conservado: #${Math.min(last + 1, cut.keep)}. Se quitarán ${Number(cut.seconds.toFixed(3)).toLocaleString("es")} s del final.`;
    if (!item.tail_precise) $("tail-cut-summary").textContent += " Tiempos aproximados: el vídeo no declara una cadencia constante y un total fiable. Se guardará el corte en segundos.";
    $("tail-jump-cut").disabled ||= cut.keep <= first || cut.keep > last + 1;
  } catch(error) {
    $("tail-cut-summary").textContent = error.message;
    $("tail-jump-cut").disabled = true;
  }
}

function seekTail(frame) {
  const item = current();
  if (!item?.tail || view !== "tail") return;
  const first = item.tail_precise ? item.tail_start_frame : Math.round(item.tail_start * item.fps);
  tailCursor = Math.min(item.tail_total_frames - 1, Math.max(first, Math.round(frame)));
  $("player").pause();
  const seconds = (tailCursor - first + .25) / item.fps;
  if ($("player").readyState) $("player").currentTime = Math.min(seconds, Math.max(0, $("player").duration - .001));
  renderTail();
}

async function generateTail() {
  if (state.busy || requestBusy || !current()?.width) return;
  requestBusy = true;
  view = "tail";
  render();
  try {
    await saving.catch(() => {});
    await api("/api/tail", {id:currentId, seconds:Number($("tail-window").value)});
    await refresh();
  } catch(error) { toast(error.message,true); }
  finally { requestBusy = false; render(); }
}

async function saveCurrent() {
  const item = current();
  if (!item || state.busy) return;
  const id = item.id;
  const settings = settingsFromControls();
  $("saved-state").textContent = "Guardando…";
  const task = saving.catch(() => {}).then(() => api("/api/settings", {id, settings}));
  saving = task;
  try {
    await task;
    item.settings = settings;
    if (id === currentId) $("saved-state").textContent = "Guardado";
  } catch (error) {
    if (id === currentId) $("saved-state").textContent = "Revisa los ajustes";
    throw error;
  }
}

function renderRows() {
  const signature = JSON.stringify([state.items, currentId, [...selected], state.busy]);
  if (signature === listSignature) return;
  listSignature = signature;
  const fragment = document.createDocumentFragment();
  for (const item of state.items) {
    const row = element("tr", `item-row${item.id === currentId ? " active" : ""}`);
    row.tabIndex = 0;
    row.setAttribute("aria-label", `Revisar ${item.name}`);
    row.addEventListener("click", () => choose(item.id));
    row.addEventListener("keydown", event => { if (event.key === "Enter") choose(item.id); });
    const checkCell = element("td");
    const check = document.createElement("input");
    check.type = "checkbox";
    check.checked = selected.has(item.id);
    check.disabled = state.busy;
    check.setAttribute("aria-label", `Seleccionar ${item.name}`);
    check.addEventListener("click", event => event.stopPropagation());
    check.addEventListener("change", () => { check.checked ? selected.add(item.id) : selected.delete(item.id); render(); });
    checkCell.append(check);
    const nameCell = element("td");
    const file = element("div", "file-cell");
    const icon = element("span", "file-icon", item.height > item.width ? "▯" : "▭");
    icon.setAttribute("aria-hidden", "true");
    const info = element("div", "file-info");
    const name = element("strong", "", item.name);
    name.title = item.name;
    info.append(name, element("small", "", `${duration(item.duration)} · ${bytes(item.size)}`));
    info.append(element("small", "trim-label", trimLabel(item.settings)));
    file.append(icon, info); nameCell.append(file);
    const formatCell = element("td");
    let format = item.format;
    if (format.startsWith("Horizontal")) format = format.replace("Horizontal · ", "");
    const badge = element("span", `format-badge${item.width > item.height ? " horizontal" : ""}`, format);
    badge.title = item.width ? `${item.width} × ${item.height} · ${item.fps.toFixed(2)} fps` : item.error;
    formatCell.append(badge);
    const statusCell = element("td");
    const labels = {ready:"Pendiente", queued:"En espera", processing:`Procesando ${Math.round(item.progress)}%`, previewing:"Preparando vista…", tailing:"Preparando cierre…", done:"✓ Terminado", error:"Revisar", cancelled:"Detenido"};
    const status = element("span", `status ${item.state}`, labels[item.state] || item.message);
    status.title = item.error || item.message;
    statusCell.append(status);
    if (item.state === "processing") {
      const progress = element("progress", "row-progress"); progress.max = 100; progress.value = item.progress;
      statusCell.append(progress);
    }
    const actions = element("td");
    if (item.result) {
      const download = element("a", "row-action", "↓");
      download.href = `/download/${item.id}/result`; download.download = item.result;
      download.setAttribute("aria-label", `Descargar ${item.name}`);
      download.addEventListener("click", event => event.stopPropagation());
      actions.append(download);
    }
    row.append(checkCell, nameCell, formatCell, statusCell, actions);
    fragment.append(row);
  }
  $("items").replaceChildren(fragment);
}

function renderPreview() {
  const item = current();
  const locked = state.busy || state.closing || uploading || requestBusy;
  for (const id of ["preview", "profile", "quality", "trim", "smart", "rtl", "region", "preview-second", "apply-all"]) {
    $(id).disabled = !item || locked || !item.width;
  }
  $("selected-name").textContent = item ? item.name : "Previsualización";
  $("selected-name").title = item ? item.name : "";
  $("selected-meta").textContent = item && item.width ? `${item.width} × ${item.height} · ${item.fps.toFixed(2)} fps · ${duration(item.duration)}` : "Selecciona un vídeo de la lista.";
  if (item && populatedId !== item.id) {
    populatedId = item.id;
    $("profile").value = item.settings.perfil;
    $("quality").value = item.settings.modo;
    $("trim").checked = item.settings.recortar;
    $("trim-mode").value = item.settings.recorte_modo;
    $("trim-frames").value = item.settings.recorte_fotogramas;
    $("trim-seconds").value = item.settings.recorte_segundos;
    $("smart").checked = item.settings.inteligente;
    $("rtl").checked = item.settings.rtl;
    $("region").value = item.settings.rect;
    $("preview-second").max = Math.max(0, (item.duration || 1) - .05).toFixed(2);
    $("preview-second").value = item.preview_at ?? Math.min(1, Math.max(0, (item.duration || 1) / 2)).toFixed(1);
    $("saved-state").textContent = "Guardado automático";
  }
  if (!item) populatedId = null;
  renderTrim();
  $("tab-original").disabled = !item || !item.width;
  $("tab-result").disabled = !item || !item.result;
  $("tab-tail").disabled = !item?.width;
  for (const tab of ["compare", "original", "tail", "result"]) $("tab-"+tab).setAttribute("aria-selected", String(tab === view));
  $("comparison").hidden = true;
  $("player").hidden = true;
  $("preview-empty").hidden = false;
  $("preview-loading").classList.toggle("hidden", !(item && (item.state === "previewing" || item.state === "tailing")));
  $("preview-loading-text").textContent = item?.state === "tailing" ? "Preparando el cierre original…" : "Generando previsualización…";
  if (item && view === "compare" && item.preview) {
    $("comparison").hidden = false;
    $("preview-empty").hidden = true;
    if ($("comparison").getAttribute("src") !== item.preview) $("comparison").src = item.preview;
  } else if (item && item.width && (view === "original" || (view === "result" && item.result) || (view === "tail" && item.tail))) {
    const key = `${item.id}/${view}/${view === "tail" ? item.tail : item.result || ""}`;
    if (videoKey !== key) {
      $("player").src = view === "tail" ? item.tail : `/media/${item.id}/${view === "result" ? "result" : "original"}`;
      if (view === "tail") tailCursor = item.tail_start_frame;
      $("player").load();
      videoKey = key;
    }
    $("player").hidden = false;
    $("preview-empty").hidden = true;
  } else {
    $("preview-empty").querySelector("p").textContent = item ? view === "tail" ? "Pulsa Preparar cierre para revisar los últimos segundos." : "Pulsa Actualizar vista para comprobar la zona del logo." : "Añade un vídeo para ver el antes y después.";
  }
  if ($("player").hidden) $("player").pause();
  $("preview-stale").classList.toggle("hidden", !(item && item.preview && item.preview_stale && view === "compare"));
  $("selected-error").classList.toggle("hidden", !(item && item.error));
  $("selected-error").textContent = item ? item.error : "";
  renderTail();
}

function render() {
  const ids = new Set(state.items.map(item => item.id));
  for (const id of selected) if (!ids.has(id)) selected.delete(id);
  if (!ids.has(currentId)) currentId = state.items[0]?.id || null;
  $("queue-count").textContent = state.items.length;
  $("empty-list").classList.toggle("hidden", state.items.length > 0);
  $("selection-count").textContent = `${selected.size} seleccionados`;
  $("select-all").checked = state.items.length > 0 && selected.size === state.items.length;
  $("select-all").indeterminate = selected.size > 0 && selected.size < state.items.length;
  $("select-all").disabled = state.busy || state.closing || !state.items.length;
  $("remove").disabled = state.busy || state.closing || !selected.size || uploading;
  $("add").disabled = uploading || closed || state.closing;
  const results = state.items.filter(item => item.result).length;
  $("queue-summary").textContent = state.items.length ? `${state.items.length} vídeos · ${results} resultados temporales listos` : "Sin vídeos todavía";
  $("download-all").classList.toggle("disabled", results === 0);
  $("download-all").setAttribute("aria-disabled", String(results === 0));
  $("tools-alert").classList.toggle("hidden", !state.tools_error);
  $("tools-alert").textContent = state.tools_error || "";
  const progress = state.job_kind === "batch" ? state.job_progress : 0;
  $("overall-progress").value = progress || 0;
  $("overall-percent").textContent = `${Math.round(progress || 0)}%`;
  $("job-message").textContent = state.message || "Añade tus vídeos para comenzar.";
  $("batch-title").textContent = state.busy ? state.job_kind === "tail" ? "Preparando el cierre del vídeo" : state.job_kind === "preview" ? "Comprobando el antes y después" : `Procesando ${Math.min(state.job_finished+1,state.job_total)} de ${state.job_total}` : state.job_kind === "batch" && state.job_total ? "Tu lote ha terminado" : "Todo preparado para empezar";
  const pending = pendingIds();
  $("process").disabled = state.busy || state.closing || uploading || requestBusy || !pending.length || !!state.tools_error;
  $("process").textContent = pending.length ? `Procesar seleccionados (${pending.length}) →` : results && selected.size ? "Todo listo ✓" : "Procesar seleccionados →";
  $("cancel").classList.toggle("hidden", !state.busy);
  renderRows();
  renderPreview();
}

async function refresh() {
  state = await api("/api/state");
  render();
}

async function choose(id) {
  if (currentId === id) return;
  try { await saveCurrent(); } catch(error) { toast(error.message,true); return; }
  currentId = id; view = view === "tail" ? "tail" : "compare"; populatedId = null;
  render();
  if (view === "tail" && !current()?.tail && !state.busy) await generateTail();
}

function upload(file, index, total) {
  return new Promise((resolve,reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", `/api/upload?name=${encodeURIComponent(file.name)}`);
    request.setRequestHeader("Content-Type", "application/octet-stream");
    request.upload.onprogress = event => {
      const percent = event.lengthComputable ? event.loaded / event.total * 100 : 0;
      $("upload-progress").value = percent;
      $("upload-message").textContent = `${index} de ${total} · ${file.name} · ${Math.round(percent)}%`;
    };
    request.onload = () => {
      try {
        const data = JSON.parse(request.responseText);
        request.status >= 200 && request.status < 300 ? resolve(data.id) : reject(new Error(data.error || "No se pudo añadir el archivo."));
      } catch { reject(new Error("No se pudo leer la respuesta al añadir el vídeo.")); }
    };
    request.onerror = () => reject(new Error("Se interrumpió la copia local. Comprueba que la aplicación sigue abierta."));
    request.send(file);
  });
}

async function addFiles(files) {
  if (uploading || closed) return;
  files = [...files].filter(file => /\.(mp4|mov|mkv|webm)$/i.test(file.name));
  if (!files.length) { toast("Selecciona vídeos MP4, MOV, MKV o WebM.",true); return; }
  uploading = true;
  $("upload-feedback").classList.remove("hidden"); render();
  const wasEmpty = !state.items.length;
  let first;
  try {
    for (const [index,file] of files.entries()) {
      $("upload-message").textContent = `${index+1} de ${files.length} · Añadiendo ${file.name}`;
      try {
        const id = await upload(file,index+1,files.length);
        selected.add(id); if (!first) first = id;
        await refresh();
      } catch(error) { toast(`${file.name}: ${error.message}`,true); }
    }
  } finally {
    uploading = false; $("files").value = "";
    $("upload-feedback").classList.add("hidden");
    if (wasEmpty && first) { currentId = first; populatedId = null; }
    await refresh();
  }
  if (wasEmpty && first && !state.busy) await generatePreview();
}

async function generatePreview() {
  if (state.busy || requestBusy || !current()) return;
  requestBusy = true; render();
  try {
    await saveCurrent();
    const second = Number($("preview-second").value);
    if (!Number.isFinite(second) || second < 0) throw new Error("Introduce un segundo válido.");
    view = "compare";
    await api("/api/preview", {id: currentId, second});
    await refresh();
  } catch(error) { toast(error.message,true); }
  finally { requestBusy = false; render(); }
}

$("add").addEventListener("click", () => $("files").click());
$("drop-zone").addEventListener("click", () => { if (!uploading) $("files").click(); });
$("drop-zone").addEventListener("keydown", event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); $("files").click(); } });
$("files").addEventListener("change", event => addFiles(event.target.files));
for (const event of ["dragenter","dragover"]) $("drop-zone").addEventListener(event, e => { e.preventDefault(); $("drop-zone").classList.add("dragging"); });
for (const event of ["dragleave","drop"]) $("drop-zone").addEventListener(event, e => { e.preventDefault(); $("drop-zone").classList.remove("dragging"); });
$("drop-zone").addEventListener("drop", event => addFiles(event.dataTransfer.files));
document.addEventListener("dragover", event => event.preventDefault());
document.addEventListener("drop", event => event.preventDefault());
$("select-all").addEventListener("change", () => { selected.clear(); if ($("select-all").checked) state.items.forEach(item => selected.add(item.id)); render(); });
$("remove").addEventListener("click", async () => {
  try { await api("/api/remove", {ids:[...selected]}); selected.clear(); await refresh(); }
  catch(error) { toast(error.message,true); }
});
for (const id of ["profile","quality","trim","trim-mode","trim-frames","trim-seconds","smart","rtl","region"]) $(id).addEventListener("change", async () => {
  renderTrim();
  renderTail();
  try { await saveCurrent(); await refresh(); }
  catch(error) { toast(error.message,true); }
});
$("region").addEventListener("input", () => $("saved-state").textContent = "Sin guardar");
for (const id of ["trim-frames","trim-seconds"]) $(id).addEventListener("input", () => {
  $("saved-state").textContent = "Sin guardar";
  renderTrim();
  renderTail();
});
$("apply-all").addEventListener("click", async () => {
  if (!selected.size) { toast("Selecciona los vídeos que recibirán estos ajustes.",true); return; }
  requestBusy = true; render();
  try {
    await saveCurrent();
    const settings = settingsFromControls();
    await api("/api/settings-many", {ids:[...selected], settings});
    await refresh(); toast(`Ajustes aplicados a ${selected.size} vídeos.`);
  } catch(error) { toast(error.message,true); }
  finally { requestBusy = false; render(); }
});
$("preview").addEventListener("click", generatePreview);
for (const tab of ["compare","original","result"]) $("tab-"+tab).addEventListener("click", () => { view = tab; renderPreview(); });
$("tab-tail").addEventListener("click", async () => {
  view = "tail"; renderPreview();
  if (!current()?.tail) await generateTail();
});
$("tail-load").addEventListener("click", generateTail);
$("tail-window").addEventListener("change", generateTail);
$("tail-position").addEventListener("input", () => seekTail(Number($("tail-position").value)));
$("tail-back").addEventListener("click", () => seekTail(tailCursor - 1));
$("tail-forward").addEventListener("click", () => seekTail(tailCursor + 1));
$("tail-jump-cut").addEventListener("click", () => {
  try { seekTail(tailCut(current()).keep - 1); }
  catch(error) { toast(error.message,true); }
});
$("player").addEventListener("loadedmetadata", () => { if (view === "tail") seekTail(tailCursor); });
for (const event of ["timeupdate","seeked"]) $("player").addEventListener(event, () => {
  const item = current();
  if (view !== "tail" || !item?.tail || !$("player").readyState) return;
  const first = item.tail_precise ? item.tail_start_frame : Math.round(item.tail_start * item.fps);
  tailCursor = Math.min(item.tail_total_frames - 1, first + Math.floor($("player").currentTime * item.fps + 1e-4));
  renderTail();
});
$("player").addEventListener("error", () => {
  if (view === "tail") {
    $("tail-error").textContent = "No se pudo reproducir este cierre. Pulsa Actualizar cierre para generarlo de nuevo.";
    $("tail-error").classList.remove("hidden");
  }
});
$("tail-set-cut").addEventListener("click", async () => {
  const item = current();
  if (!item?.tail || state.busy || requestBusy) return;
  $("player").pause();
  $("trim").checked = true;
  if (item.tail_precise) {
    $("trim-mode").value = "fotogramas";
    $("trim-frames").value = Math.max(0, item.tail_total_frames - tailCursor - 1);
  } else {
    const first = Math.round(item.tail_start * item.fps);
    const end = item.tail_start + (tailCursor - first + 1) / item.fps;
    $("trim-mode").value = "segundos";
    $("trim-seconds").value = Math.max(0, item.duration - end).toFixed(6);
  }
  requestBusy = true; render();
  try {
    await saveCurrent(); await refresh();
    toast("Punto final guardado para este vídeo. El fotograma elegido se conserva.");
  } catch(error) { toast(error.message,true); }
  finally { requestBusy = false; render(); }
});
$("process").addEventListener("click", async () => {
  requestBusy = true; render();
  try {
    await saveCurrent(); await refresh();
    await api("/api/run", {ids:pendingIds()}); await refresh();
  } catch(error) { toast(error.message,true); }
  finally { requestBusy = false; render(); }
});
$("cancel").addEventListener("click", async () => {
  try { await api("/api/cancel",{}); await refresh(); }
  catch(error) { toast(error.message,true); }
});
$("exit").addEventListener("click", () => {
  const results = state.items.filter(item => item.result).length;
  $("close-summary").textContent = `${results ? `Hay ${results} resultados en esta sesión. ` : ""}Se eliminarán todos los vídeos generados y las previsualizaciones de la sesión. Los resultados sin descargar se perderán.`;
  $("close-download").classList.toggle("hidden", !results);
  $("confirm-exit").showModal();
});
$("keep-open").addEventListener("click", () => $("confirm-exit").close());
$("close-now").addEventListener("click", async () => {
  closed = true; requestBusy = true; clearTimeout(pollTimer);
  $("close-now").disabled = $("keep-open").disabled = true;
  $("close-now").textContent = "Eliminando sesión…";
  $("close-download").classList.add("disabled");
  $("player").pause(); $("player").removeAttribute("src"); $("player").load();
  try {
    const result = await api("/api/shutdown",{});
    if (!result.session_deleted) throw new Error("No se pudo confirmar la limpieza de la sesión.");
    $("confirm-exit").close();
    selected.clear(); currentId = null;
    state = {...state, items:[], busy:false, closing:true, job_total:0, job_finished:0,
      message:"Sesión eliminada. Solo permanecen las copias que descargaste."};
    render();
    $("comparison").removeAttribute("src");
    document.querySelectorAll("button,input,select").forEach(control => control.disabled = true);
    $("download-all").classList.add("disabled");
    $("job-message").textContent = "Sesión eliminada. Solo permanecen las copias que descargaste.";
    toast("Sesión eliminada y cierre solicitado. Tus descargas se conservan.");
  } catch(error) {
    closed = false; requestBusy = false;
    $("close-now").disabled = $("keep-open").disabled = false;
    $("close-now").textContent = "Reintentar limpieza y cierre";
    toast(error.message,true);
    pollTimer = setTimeout(poll,1000);
  }
});

async function poll() {
  if (closed) return;
  try { await refresh(); }
  catch(error) { $("job-message").textContent = "La aplicación local no responde. Vuelve a abrirla desde el acceso de inicio."; }
  pollTimer = setTimeout(poll, state.busy ? 700 : 1400);
}

(async function initialize() {
  try {
    const token = location.hash.slice(1);
    if (token) {
      await api("/api/session", {token});
      history.replaceState(null,"",location.pathname);
    }
    await refresh();
    pollTimer = setTimeout(poll,1000);
  } catch(error) {
    $("tools-alert").classList.remove("hidden"); $("tools-alert").textContent = error.message;
    document.querySelectorAll("button,input,select").forEach(control => control.disabled = true);
  }
})();
