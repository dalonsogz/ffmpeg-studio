'use strict';

/* FFmpeg Studio — lógica de interfaz (pywebview + WebView2). */

let api = null;

const S = {
  boot: null,
  files: [],
  activeFile: null,
  task: 'video',
  outputDir: null,
  hardware: null,
  queue: { jobs: [], running: false, paused: false, currentId: null },
  logJobId: null,
  filterChain: '',
  audioFilter: '',
  subtitleFile: null,
  preview: { ok: false, preview: '', issues: [] },
};

const el = {};
let previewTimer = null;
let toastTimer = null;
let pollTimer = null;
let lastSignature = '';

/* ------------------------------------------------------------------ */
/* Puente con Python                                                   */
/* ------------------------------------------------------------------ */

function buildApi() {
  const bridge = window.pywebview.api;
  return {
    bootstrap: () => bridge.bootstrap(),
    initialFiles: () => bridge.initial_files(),
    pickFiles: () => bridge.pick_files(),
    pickOutputDir: () => bridge.pick_output_dir(),
    pickFfmpeg: () => bridge.pick_ffmpeg(),
    pickSubtitleFile: () => bridge.pick_subtitle_file(),
    subtitleLoad: (path) => bridge.subtitle_load(path),
    subtitleSave: (path, cues) => bridge.subtitle_save(path, cues),
    pickSavePath: (suggested) => bridge.pick_save_path(suggested),
    probe: (paths) => bridge.probe(paths),
    preview: (input, options) => bridge.preview(input, options),
    addToQueue: (files, options, outputDir) => bridge.add_to_queue(files, options, outputDir),
    addCapture: (options, outputDir) => bridge.add_capture(options, outputDir),
    startQueue: () => bridge.start_queue(),
    pauseQueue: () => bridge.pause_queue(),
    clearQueue: () => bridge.clear_queue(),
    cancelJob: (id) => bridge.cancel_job(id),
    removeJob: (id) => bridge.remove_job(id),
    queueState: () => bridge.queue_state(),
    saveSettings: (patch) => bridge.save_settings(patch),
    reveal: (target) => bridge.reveal(target),
    open: (target) => bridge.open_path(target),
    redetectHardware: () => bridge.redetect_hardware(),
    hardwareState: () => bridge.hardware_state(),
  };
}

/* ------------------------------------------------------------------ */
/* Utilidades                                                          */
/* ------------------------------------------------------------------ */

function $(id) { return document.getElementById(id); }

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function parseTime(value) {
  if (value === null || value === undefined) return null;
  const s = String(value).trim().replace(',', '.');
  if (!s) return null;
  const parts = s.split(':').map((p) => p.trim());
  if (parts.some((p) => p === '' || Number.isNaN(Number(p)))) return null;
  let total = 0;
  for (const part of parts) total = total * 60 + Number(part);
  return Number.isFinite(total) ? total : null;
}

function formatClock(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) seconds = 0;
  const total = Math.round(seconds * 1000);
  const ms = total % 1000;
  let rest = Math.floor(total / 1000);
  const h = Math.floor(rest / 3600);
  rest -= h * 3600;
  const m = Math.floor(rest / 60);
  const s = rest - m * 60;
  const pad = (n, size = 2) => String(n).padStart(size, '0');
  return `${pad(h)}:${pad(m)}:${pad(s)}.${pad(ms, 3)}`;
}

function formatSize(bytes) {
  if (!Number.isFinite(bytes)) return '—';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let value = bytes;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) { value /= 1024; index += 1; }
  return `${value >= 100 ? Math.round(value) : value.toFixed(1)} ${units[index]}`;
}

function formatEta(seconds) {
  if (!Number.isFinite(seconds)) return '';
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  return `${m} min ${String(s % 60).padStart(2, '0')} s`;
}

function toast(message, kind = '') {
  el.toast.textContent = message;
  el.toast.className = `toast ${kind}`;
  el.toast.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.toast.classList.add('hidden'), 4200);
}

function openModal(title, bodyHtml) {
  el.modalTitle.textContent = title;
  el.modalBody.innerHTML = bodyHtml;
  el.modal.classList.remove('hidden');
}

function closeModal() {
  el.modal.classList.add('hidden');
}

function copyText(text) {
  const done = () => toast('Copiado al portapapeles.', 'ok');
  const fail = () => toast('No se pudo copiar.', 'error');
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(done, fail);
    return;
  }
  const area = document.createElement('textarea');
  area.value = text;
  document.body.appendChild(area);
  area.select();
  try { document.execCommand('copy'); done(); } catch { fail(); }
  document.body.removeChild(area);
}

/* ------------------------------------------------------------------ */
/* Arranque                                                            */
/* ------------------------------------------------------------------ */

// ---------------------------------------------------------------------
// Editor de subtítulos
// ---------------------------------------------------------------------
const ED = { path: null, cues: [] };

function formatCueTime(milliseconds) {
  const total = Math.max(0, Math.round(Number(milliseconds) || 0));
  const hours = String(Math.floor(total / 3600000)).padStart(2, '0');
  const minutes = String(Math.floor((total % 3600000) / 60000)).padStart(2, '0');
  const seconds = String(Math.floor((total % 60000) / 1000)).padStart(2, '0');
  const millis = String(total % 1000).padStart(3, '0');
  return `${hours}:${minutes}:${seconds},${millis}`;
}

function parseCueTime(value) {
  const text = String(value || '').trim().replace('.', ',');
  let match = text.match(/^(\d{1,2}):(\d{2}):(\d{2}),(\d{1,3})$/);
  if (match) {
    return ((Number(match[1]) * 60 + Number(match[2])) * 60 + Number(match[3])) * 1000
      + Number(match[4].padEnd(3, '0'));
  }
  match = text.match(/^(\d{1,2}):(\d{2}),(\d{1,3})$/);
  if (match) {
    return (Number(match[1]) * 60 + Number(match[2])) * 1000 + Number(match[3].padEnd(3, '0'));
  }
  return null;
}

function updateEditorStats() {
  const last = ED.cues.reduce((max, cue) => Math.max(max, Number(cue.end) || 0), 0);
  el.editorStats.textContent = ED.cues.length === 1
    ? `1 subtítulo · hasta ${formatCueTime(last)}`
    : `${ED.cues.length} subtítulos · hasta ${formatCueTime(last)}`;
}

function renderEditor() {
  el.editorFile.textContent = ED.path || 'sin guardar';
  el.editorError.textContent = '';
  el.editorList.innerHTML = '';

  ED.cues.forEach((cue, index) => {
    const row = document.createElement('div');
    row.className = 'cue';

    const number = document.createElement('span');
    number.className = 'cue-index';
    number.textContent = String(index + 1);

    const start = document.createElement('input');
    start.className = 'cue-time';
    start.type = 'text';
    start.value = formatCueTime(cue.start || 0);
    start.spellcheck = false;
    start.addEventListener('input', () => {
      const value = parseCueTime(start.value);
      start.classList.toggle('invalid', value === null);
      cue.start = value;
      updateEditorStats();
    });

    const end = document.createElement('input');
    end.className = 'cue-time';
    end.type = 'text';
    end.value = formatCueTime(cue.end || 0);
    end.spellcheck = false;
    end.addEventListener('input', () => {
      const value = parseCueTime(end.value);
      end.classList.toggle('invalid', value === null);
      cue.end = value;
      updateEditorStats();
    });

    const text = document.createElement('textarea');
    text.rows = 2;
    text.value = cue.text || '';
    text.addEventListener('input', () => { cue.text = text.value; });

    const remove = document.createElement('button');
    remove.className = 'cue-remove';
    remove.type = 'button';
    remove.title = 'Quitar subtítulo';
    remove.textContent = '✕';
    remove.addEventListener('click', () => {
      ED.cues.splice(index, 1);
      renderEditor();
    });

    row.append(number, start, end, text, remove);
    el.editorList.appendChild(row);
  });

  updateEditorStats();
}

function addCue() {
  const last = ED.cues.reduce((max, cue) => Math.max(max, Number(cue.end) || 0), 0);
  ED.cues.push({ start: last, end: last + 2000, text: '' });
  renderEditor();
  el.editorList.scrollTop = el.editorList.scrollHeight;
}

async function openEditorFromFile() {
  if (!S.subtitleFile) {
    toast('Elige primero un archivo .srt o .vtt.', 'error');
    return;
  }
  const result = await api.subtitleLoad(S.subtitleFile);
  if (!result.ok) {
    toast(result.error || 'No se pudo abrir el archivo.', 'error');
    return;
  }
  ED.path = result.path;
  ED.cues = (result.cues || []).map((cue) => ({ start: cue.start, end: cue.end, text: cue.text }));
  if (ED.cues.length === 0) {
    ED.cues.push({ start: 0, end: 2000, text: '' });
  }
  el.editor.classList.remove('hidden');
  renderEditor();
}

function newSubtitle() {
  ED.path = null;
  ED.cues = [{ start: 0, end: 2000, text: '' }];
  el.editor.classList.remove('hidden');
  renderEditor();
}

async function saveEditor(saveAs) {
  el.editorError.textContent = '';
  if (ED.cues.length === 0) {
    el.editorError.textContent = 'Añade al menos un subtítulo.';
    return;
  }
  for (let index = 0; index < ED.cues.length; index += 1) {
    const cue = ED.cues[index];
    if (cue.start === null || cue.end === null) {
      el.editorError.textContent = `Subtítulo ${index + 1}: la hora no es válida (usa 00:00:01,000).`;
      return;
    }
    if (cue.end <= cue.start) {
      el.editorError.textContent = `Subtítulo ${index + 1}: el fin debe ser posterior al inicio.`;
      return;
    }
  }

  let target = ED.path;
  if (saveAs || !target) {
    target = await api.pickSavePath(target ? target.split(/[\\/]/).pop() : 'subtitulos.srt');
    if (!target) return;
  }

  const result = await api.subtitleSave(target, ED.cues.map((cue) => ({
    start: cue.start, end: cue.end, text: cue.text,
  })));
  if (!result.ok) {
    el.editorError.textContent = result.error || 'No se pudo guardar.';
    return;
  }
  ED.path = result.path;
  el.editorFile.textContent = ED.path;
  toast(`${result.count} subtítulos guardados.`, 'ok');
}

async function init() {
  cacheElements();
  bindStaticEvents();

  try {
    S.boot = await api.bootstrap();
  } catch (error) {
    openModal('Error al iniciar', `<p class="error-line">${escapeHtml(error.message || error)}</p>`);
    return;
  }

  S.hardware = S.boot.hardware;
  S.outputDir = S.boot.settings.outputDir || null;

  if (S.boot.restored > 0) {
    toast(`${S.boot.restored} ${S.boot.restored === 1 ? 'trabajo pendiente restaurado' : 'trabajos pendientes restaurados'} de la sesión anterior.`, 'ok');
  }

  el.brandSub.textContent = 'Front-end de escritorio para FFmpeg';
  renderHeader();
  updateOutputDirLabel();
  populateSubsStaticOptions();
  updateSubsFileLabel();
  setTask('video', { silent: true });
  renderFiles();

  if (!S.boot.ok) showMissingFfmpeg();

  applySnapshot(await api.queueState());
  startPolling();

  try {
    const initial = await api.initialFiles();
    if (initial && initial.length) await addFiles(initial);
  } catch {
    /* sin archivos iniciales */
  }

  pollHardware();
}

/* ------------------------------------------------------------------ */
/* Hardware                                                            */
/* ------------------------------------------------------------------ */

function pollHardware() {
  if (S.hardware) return;
  setTimeout(async () => {
    try {
      const hardware = await api.hardwareState();
      if (hardware) {
        S.hardware = hardware;
        renderHeader();
        return;
      }
    } catch { /* seguimos intentando */ }
    pollHardware();
  }, 900);
}

function renderHeader() {
  const hw = S.hardware;
  if (!hw) {
    el.hwText.textContent = 'Comprobando hardware…';
    el.hwChip.className = 'chip';
  } else {
    el.hwText.textContent = hw.summary;
    el.hwChip.className = `chip ${hw.summary === 'Solo CPU' ? 'off' : 'ok'}`;
  }

  const version = S.boot && S.boot.ffmpeg.version;
  if (version) {
    const match = version.match(/ffmpeg version (\S+)/i);
    el.ffText.textContent = match ? `FFmpeg ${match[1].slice(0, 16)}` : 'FFmpeg';
    el.ffChip.className = 'chip ok';
  } else {
    el.ffText.textContent = 'FFmpeg no encontrado';
    el.ffChip.className = 'chip bad';
  }
}

function showMissingFfmpeg() {
  openModal('FFmpeg no encontrado', `
    <p style="margin-top:0">La aplicación necesita <code>ffmpeg.exe</code> y <code>ffprobe.exe</code>.</p>
    <p class="hint">Se han buscado junto al proyecto y en el PATH sin éxito. Selecciona el ejecutable manualmente.</p>
    <button class="btn btn-primary" id="modalPickFfmpeg" style="margin-top:10px">Elegir ffmpeg.exe…</button>
  `);
  const button = $('modalPickFfmpeg');
  if (button) button.addEventListener('click', pickFfmpeg);
}

/* ------------------------------------------------------------------ */
/* Eventos                                                             */
/* ------------------------------------------------------------------ */

function cacheElements() {
  const ids = [
    'brandSub', 'hwChip', 'hwText', 'ffChip', 'ffText', 'settingsBtn',
    'filesCount', 'dropzone', 'addFilesBtn', 'addFilesBtn2', 'fileList', 'selectedInfo',
    'taskTabs', 'preset', 'presetDesc', 'container', 'vcodec', 'quality', 'qualityLabel',
    'vpreset', 'resolution', 'acodec', 'abitrate', 'gifFps', 'gifWidth', 'imgTime', 'imgWidth',
    'speed', 'fps', 'rotate', 'flip', 'cropLeft', 'cropTop', 'cropRight', 'cropBottom',
    'sheetCount', 'sheetWidth',
    'captureSource', 'captureTitle', 'captureDevice', 'captureDuration', 'captureFps',
    'captureTitleField', 'captureDeviceField',
    'trimEnabled', 'trimBox', 'trimStart', 'trimEnd', 'trimMode', 'trimAllBtn', 'trimHint',
    'includeSubs', 'twoPass', 'qualityMode', 'bitrateField', 'videoBitrate', 'concatMode',
    'normalizeLoudness', 'loudnessField', 'loudnessTarget',
    'audioTrack', 'subtitleTrack', 'concatTransition', 'transitionDuration', 'transitionDurationField',
    'subsMode', 'subsTrack', 'subsFormat', 'subsFileBtn', 'subsFileLabel', 'subsFileClear',
    'subsLanguage', 'subsTitle', 'subsDefault', 'subsTrackField', 'subsFormatField',
    'subsFileField', 'subsMetaFields', 'subsDefaultField', 'burnStyleBox',
    'subsEditorActions', 'subsEditBtn', 'subsNewBtn',
    'editor', 'editorFile', 'editorList', 'editorStats', 'editorError',
    'cueAdd', 'editorSave', 'editorSaveAs', 'editorClose',
    'burnFont', 'burnSize', 'burnColor', 'burnPosition', 'burnBold',
    'commandPreview', 'copyCmdBtn', 'issueList', 'estimateInfo', 'outputDirBtn', 'outputDirLabel',
    'enqueueBtn', 'pauseBtn', 'clearBtn', 'queueList', 'logTitle', 'logOutput', 'copyLogBtn',
    'toast', 'modal', 'modalTitle', 'modalBody', 'modalClose', 'previewDetails',
  ];
  for (const id of ids) el[id] = $(id);
}

function bindStaticEvents() {
  el.addFilesBtn.addEventListener('click', (event) => { event.stopPropagation(); pickFiles(); });
  el.addFilesBtn2.addEventListener('click', pickFiles);
  el.dropzone.addEventListener('click', pickFiles);
  el.dropzone.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') pickFiles();
  });

  el.taskTabs.addEventListener('click', (event) => {
    const tab = event.target.closest('[data-task]');
    if (tab) setTask(tab.dataset.task);
  });

  el.preset.addEventListener('change', onPresetChange);
  el.container.addEventListener('change', () => { refreshCodecSelects(); refreshPreview(); });
  el.vcodec.addEventListener('change', () => { refreshEncoderControls(); refreshPreview(); });
  el.acodec.addEventListener('change', () => { refreshAudioControls(); refreshPreview(); });
  el.quality.addEventListener('input', () => { paintQuality(); refreshPreview(); });
  el.vpreset.addEventListener('change', refreshPreview);
  el.resolution.addEventListener('change', refreshPreview);
  el.abitrate.addEventListener('change', refreshPreview);
  el.gifFps.addEventListener('change', refreshPreview);
  el.gifWidth.addEventListener('change', refreshPreview);
  el.imgTime.addEventListener('input', refreshPreview);
  el.imgWidth.addEventListener('change', refreshPreview);
  el.trimEnabled.addEventListener('change', onTrimToggle);
  el.trimStart.addEventListener('input', refreshPreview);
  el.trimEnd.addEventListener('input', refreshPreview);
  el.trimMode.addEventListener('change', refreshPreview);
  el.trimAllBtn.addEventListener('click', useFullDuration);
  el.twoPass.addEventListener('change', refreshPreview);
  el.normalizeLoudness.addEventListener('change', () => { updateLoudnessField(); refreshPreview(); });
  el.loudnessTarget.addEventListener('change', refreshPreview);
  el.qualityMode.addEventListener('change', onQualityModeChange);
  el.videoBitrate.addEventListener('change', refreshPreview);
  el.speed.addEventListener('change', refreshPreview);
  el.fps.addEventListener('change', refreshPreview);
  el.rotate.addEventListener('change', refreshPreview);
  el.flip.addEventListener('change', refreshPreview);
  for (const control of [el.cropLeft, el.cropTop, el.cropRight, el.cropBottom]) {
    control.addEventListener('input', refreshPreview);
  }
  el.sheetCount.addEventListener('change', refreshPreview);
  el.sheetWidth.addEventListener('change', refreshPreview);
  el.captureSource.addEventListener('change', () => { updateCaptureFields(); refreshPreview(); });
  el.captureTitle.addEventListener('input', refreshPreview);
  el.captureDevice.addEventListener('input', refreshPreview);
  el.captureDuration.addEventListener('change', refreshPreview);
  el.captureFps.addEventListener('change', refreshPreview);
  el.concatMode.addEventListener('change', () => { updateConcatControls(); refreshPreview(); });
  el.audioTrack.addEventListener('change', refreshPreview);
  el.subtitleTrack.addEventListener('change', refreshPreview);
  el.concatTransition.addEventListener('change', () => {
    if (el.concatTransition.value === 'fade' && el.concatMode.value === 'copy') {
      el.concatMode.value = 'reencode';
    }
    updateConcatControls();
    refreshPreview();
  });
  el.transitionDuration.addEventListener('change', refreshPreview);
  el.subsMode.addEventListener('change', () => { updateSubsControls(); refreshPreview(); });
  el.subsEditBtn.addEventListener('click', openEditorFromFile);
  el.subsNewBtn.addEventListener('click', newSubtitle);
  el.editorClose.addEventListener('click', () => el.editor.classList.add('hidden'));
  el.cueAdd.addEventListener('click', addCue);
  el.editorSave.addEventListener('click', () => saveEditor(false));
  el.editorSaveAs.addEventListener('click', () => saveEditor(true));
  el.subsTrack.addEventListener('change', refreshPreview);
  el.subsFormat.addEventListener('change', refreshPreview);
  el.subsLanguage.addEventListener('change', refreshPreview);
  el.subsTitle.addEventListener('input', refreshPreview);
  el.subsDefault.addEventListener('change', refreshPreview);
  el.subsFileBtn.addEventListener('click', pickSubtitleFile);
  el.subsFileClear.addEventListener('click', () => {
    S.subtitleFile = null;
    updateSubsFileLabel();
    refreshPreview();
  });
  for (const control of [el.burnFont, el.burnSize, el.burnColor, el.burnPosition, el.burnBold]) {
    control.addEventListener('change', refreshPreview);
  }

  el.outputDirBtn.addEventListener('click', chooseOutputDir);
  el.enqueueBtn.addEventListener('click', enqueue);
  el.copyCmdBtn.addEventListener('click', () => copyText(el.commandPreview.textContent));
  el.copyLogBtn.addEventListener('click', () => copyText(el.logOutput.textContent));
  el.pauseBtn.addEventListener('click', togglePause);
  el.clearBtn.addEventListener('click', async () => applySnapshot(await api.clearQueue()));
  el.settingsBtn.addEventListener('click', openSettings);
  el.previewDetails.addEventListener('toggle', () => {
    if (el.previewDetails.open) {
      setTimeout(() => el.previewDetails.scrollIntoView({ block: 'nearest', behavior: 'smooth' }), 60);
    }
  });
  el.modalClose.addEventListener('click', closeModal);
  el.modal.addEventListener('click', (event) => { if (event.target === el.modal) closeModal(); });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeModal();
  });
}

/* ------------------------------------------------------------------ */
/* Archivos                                                            */
/* ------------------------------------------------------------------ */

async function pickFiles() {
  try {
    const paths = await api.pickFiles();
    if (paths && paths.length) await addFiles(paths);
  } catch (error) {
    toast(`No se pudo abrir el diálogo: ${error.message || error}`, 'error');
  }
}

async function addFiles(paths) {
  const known = new Set(S.files.map((f) => f.path.toLowerCase()));
  const fresh = paths.filter((p) => !known.has(String(p).toLowerCase()));
  if (fresh.length === 0) {
    toast('Esos archivos ya están en la lista.');
    return;
  }

  const results = await api.probe(fresh);
  let firstAdded = null;
  for (const result of results) {
    const entry = result.ok
      ? { path: result.media.path, name: result.media.name, media: result.media, error: null }
      : { path: result.path, name: String(result.path).split(/[\\/]/).pop(), media: null, error: result.error };
    S.files.push(entry);
    if (!firstAdded && entry.media) firstAdded = entry;
  }

  if (!S.activeFile) S.activeFile = (firstAdded || S.files[0] || {}).path || null;

  renderFiles();
  refreshPreview();
}

function renderFiles() {
  el.filesCount.textContent = String(S.files.length);
  el.fileList.innerHTML = '';
  const isConcat = S.task === 'concat';

  S.files.forEach((entry, index) => {
    const li = document.createElement('li');
    li.className = `file-item${entry.path === S.activeFile ? ' active' : ''}`;
    li.dataset.path = entry.path;

    const meta = [];
    if (entry.media) {
      if (entry.media.duration) meta.push(formatClock(entry.media.duration).slice(0, 8));
      if (entry.media.video) meta.push(`${entry.media.video.width}×${entry.media.video.height}`);
      if (entry.media.video) meta.push(entry.media.video.codec);
      if (entry.media.audios && entry.media.audios.length) meta.push(`${entry.media.audios.length} audio`);
      if (entry.media.size) meta.push(formatSize(entry.media.size));
    }

    li.innerHTML = `
      <span class="file-name" title="${escapeHtml(entry.name)}">
        ${isConcat ? `<span class="clip-index">${index + 1}</span>` : ''}${escapeHtml(entry.name)}
      </span>
      <button class="file-remove" title="Quitar">✕</button>
      <span class="file-meta">${escapeHtml(meta.join(' · '))}</span>
      ${entry.error ? `<span class="file-error">${escapeHtml(entry.error)}</span>` : ''}
      ${isConcat ? `<div class="clip-actions">
        <button data-dir="up" title="Mover antes">↑ Subir</button>
        <button data-dir="down" title="Mover después">↓ Bajar</button>
      </div>` : ''}
    `;

    li.addEventListener('click', (event) => {
      if (event.target.closest('button')) return;
      S.activeFile = entry.path;
      renderFiles();
      refreshPreview();
    });
    li.querySelector('.file-remove').addEventListener('click', (event) => {
      event.stopPropagation();
      removeFile(entry.path);
    });
    for (const button of li.querySelectorAll('[data-dir]')) {
      button.addEventListener('click', (event) => {
        event.stopPropagation();
        moveFile(index, button.dataset.dir === 'up' ? -1 : 1);
      });
    }

    el.fileList.appendChild(li);
  });

  const active = S.files.find((f) => f.path === S.activeFile);
  el.selectedInfo.textContent = active && active.media
    ? `${formatSize(active.media.size)} · ${formatClock(active.media.duration || 0)}`
    : '';

  el.dropzone.classList.toggle('hidden', S.files.length > 0);
  updateTrackOptions();
  if (S.task === 'subs') updateSubsTrackOptions();
  updateEnqueueState();
}

function removeFile(path) {
  S.files = S.files.filter((f) => f.path !== path);
  if (S.activeFile === path) S.activeFile = S.files.length ? S.files[0].path : null;
  renderFiles();
  refreshPreview();
}

function moveFile(index, delta) {
  const target = index + delta;
  if (target < 0 || target >= S.files.length) return;
  const [item] = S.files.splice(index, 1);
  S.files.splice(target, 0, item);
  renderFiles();
  refreshPreview();
}

/* ------------------------------------------------------------------ */
/* Tareas y opciones                                                   */
/* ------------------------------------------------------------------ */

const TASK_KIND = { video: 'video', audio: 'audio', gif: 'animation', image: 'image', concat: 'video', subs: 'video', sheet: 'image', capture: 'video' };
const TASK_DEFAULT_CONTAINER = { video: 'mp4', audio: 'mp3', gif: 'gif', image: 'jpg', concat: 'mp4', subs: 'mp4', sheet: 'jpg', capture: 'mp4' };

function setTask(task, { silent = false } = {}) {
  S.task = task;
  S.filterChain = '';
  S.audioFilter = '';

  for (const tab of el.taskTabs.querySelectorAll('.tab')) {
    tab.classList.toggle('active', tab.dataset.task === task);
  }

  for (const node of document.querySelectorAll('[data-tasks]')) {
    const tasks = node.dataset.tasks.split(/\s+/);
    node.classList.toggle('hidden', !tasks.includes(task));
  }

  populateContainers();
  el.container.value = TASK_DEFAULT_CONTAINER[task];
  refreshCodecSelects();
  populatePresets();
  updateConcatControls();
  updateSubsControls();
  updateLoudnessField();
  updateCaptureFields();
  el.bitrateField.classList.toggle('hidden', el.qualityMode.value !== 'bitrate' || task !== 'video');

  if (task === 'image') {
    el.trimEnabled.checked = false;
    el.trimBox.classList.add('hidden');
  }

  renderFiles();
  if (!silent) refreshPreview();
}

function populateContainers() {
  const kind = TASK_KIND[S.task];
  el.container.innerHTML = '';
  for (const [id, meta] of Object.entries(S.boot.containers)) {
    if (meta.kind !== kind) continue;
    if (S.task === 'subs' && !meta.subtitles) continue;
    if (S.task === 'capture' && !['mp4', 'mkv', 'mov'].includes(id)) continue;
    const option = document.createElement('option');
    option.value = id;
    option.textContent = meta.label;
    el.container.appendChild(option);
  }
}

function refreshCodecSelects() {
  const container = S.boot.containers[el.container.value];
  if (!container) return;

  const previousVideo = el.vcodec.value;
  el.vcodec.innerHTML = '';
  for (const codecId of container.video) {
    const info = S.boot.videoEncoders[codecId];
    if (!info) continue;
    const option = document.createElement('option');
    option.value = codecId;
    option.textContent = info.label;
    el.vcodec.appendChild(option);
  }
  if ([...el.vcodec.options].some((o) => o.value === previousVideo)) el.vcodec.value = previousVideo;

  const previousAudio = el.acodec.value;
  el.acodec.innerHTML = '';
  for (const codecId of container.audio) {
    const info = S.boot.audioEncoders[codecId];
    if (!info) continue;
    const option = document.createElement('option');
    option.value = codecId;
    option.textContent = info.label;
    el.acodec.appendChild(option);
  }
  if ([...el.acodec.options].some((o) => o.value === previousAudio)) el.acodec.value = previousAudio;

  refreshEncoderControls();
  refreshAudioControls();
}

function refreshEncoderControls() {
  const codec = el.vcodec.value;
  const info = S.boot.videoEncoders[codec];
  if (!info) return;

  el.vpreset.innerHTML = '';
  const presets = info.presets || [];
  for (const preset of presets) {
    const option = document.createElement('option');
    option.value = preset;
    option.textContent = presetLabel(preset, codec);
    el.vpreset.appendChild(option);
  }
  if (info.default_preset && presets.includes(info.default_preset)) el.vpreset.value = info.default_preset;
  const presetField = el.vpreset.closest('.field');
  if (presetField) presetField.classList.toggle('hidden', presets.length === 0);

  if (info.quality) {
    el.quality.min = String(info.quality[0]);
    el.quality.max = String(info.quality[1]);
    const current = Number(el.quality.value);
    if (!Number.isFinite(current) || current < info.quality[0] || current > info.quality[1]) {
      el.quality.value = String(info.quality[2]);
    }
  }
  paintQuality();
}

function presetLabel(preset, codec) {
  if (codec === 'libsvtav1') return `Nivel ${preset}${preset === '8' ? ' (equilibrado)' : ''}`;
  if (codec.endsWith('_nvenc')) return String(preset).toUpperCase();
  return preset;
}

function refreshAudioControls() {
  const codec = el.acodec.value;
  const info = S.boot.audioEncoders[codec];
  const bitrates = info ? info.bitrates || [] : [];

  el.abitrate.innerHTML = '';
  for (const bitrate of bitrates) {
    const option = document.createElement('option');
    option.value = bitrate;
    option.textContent = bitrate.replace('k', ' kbps');
    el.abitrate.appendChild(option);
  }
  if (info && info.default_bitrate && bitrates.includes(info.default_bitrate)) {
    el.abitrate.value = info.default_bitrate;
  }
  const field = el.abitrate.closest('.field');
  if (field) field.classList.toggle('hidden', bitrates.length === 0);
}

function paintQuality() {
  const value = Number(el.quality.value);
  const min = Number(el.quality.min);
  const max = Number(el.quality.max);
  const percent = max > min ? ((value - min) / (max - min)) * 100 : 50;
  el.quality.style.setProperty('--fill', `${percent}%`);
  el.qualityLabel.textContent = String(value);
}

function onQualityModeChange() {
  const bitrate = el.qualityMode.value === 'bitrate';
  el.bitrateField.classList.toggle('hidden', !bitrate);
  el.quality.disabled = bitrate;
  refreshPreview();
}

function updateConcatControls() {
  const isConcat = S.task === 'concat';
  const copyMode = isConcat && el.concatMode.value === 'copy';
  for (const control of [el.vcodec, el.quality, el.vpreset, el.resolution, el.acodec, el.abitrate]) {
    if (control) control.disabled = copyMode;
  }
  const fading = isConcat && el.concatTransition.value === 'fade';
  if (el.transitionDurationField) {
    el.transitionDurationField.classList.toggle('hidden', !fading);
  }
}

function updateLoudnessField() {
  if (!el.loudnessField) return;
  el.loudnessField.classList.toggle('hidden', !el.normalizeLoudness.checked);
}

function updateCaptureFields() {
  if (!el.captureSource) return;
  const source = el.captureSource.value;
  el.captureTitleField.classList.toggle('hidden', source !== 'window');
  el.captureDeviceField.classList.toggle('hidden', source !== 'camera');
}

function updateTrackOptions() {
  const active = S.files.find((f) => f.path === S.activeFile);
  const media = active && active.media;
  const audios = (media && media.audios) || [];
  const subs = (media && media.subtitles) || [];

  const previousAudio = el.audioTrack.value;
  el.audioTrack.innerHTML = '';
  const autoOption = document.createElement('option');
  autoOption.value = '-1';
  autoOption.textContent = 'Automática (mejor pista)';
  el.audioTrack.appendChild(autoOption);
  const allOption = document.createElement('option');
  allOption.value = '-2';
  allOption.textContent = 'Todas las pistas';
  el.audioTrack.appendChild(allOption);
  audios.forEach((audio, index) => {
    const option = document.createElement('option');
    option.value = String(index);
    const parts = [String(index + 1), audio.codec];
    if (audio.language) parts.push(audio.language);
    if (audio.channels) parts.push(`${audio.channels} canales`);
    option.textContent = parts.join(' · ');
    el.audioTrack.appendChild(option);
  });
  if ([...el.audioTrack.options].some((o) => o.value === previousAudio)) {
    el.audioTrack.value = previousAudio;
  }

  const previousSub = el.subtitleTrack.value;
  el.subtitleTrack.innerHTML = '';
  const noneOption = document.createElement('option');
  noneOption.value = '-1';
  noneOption.textContent = 'Ninguno';
  el.subtitleTrack.appendChild(noneOption);
  subs.forEach((sub, index) => {
    const option = document.createElement('option');
    option.value = String(index);
    const parts = [String(index + 1), sub.codec];
    if (sub.language) parts.push(sub.language);
    if (sub.title) parts.push(sub.title);
    option.textContent = parts.join(' · ');
    el.subtitleTrack.appendChild(option);
  });
  if ([...el.subtitleTrack.options].some((o) => o.value === previousSub)) {
    el.subtitleTrack.value = previousSub;
  }
}

function populateSubsStaticOptions() {
  const languages = S.boot.subtitleLanguages || {};
  el.subsLanguage.innerHTML = '';
  for (const [code, label] of Object.entries(languages)) {
    const option = document.createElement('option');
    option.value = code;
    option.textContent = `${label} (${code})`;
    el.subsLanguage.appendChild(option);
  }

  el.burnFont.innerHTML = '';
  for (const font of S.boot.burnFonts || []) {
    const option = document.createElement('option');
    option.value = font;
    option.textContent = font;
    el.burnFont.appendChild(option);
  }

  const colorLabels = { blanco: 'Blanco', amarillo: 'Amarillo', cian: 'Cian', verde: 'Verde' };
  el.burnColor.innerHTML = '';
  for (const color of S.boot.burnColors || []) {
    const option = document.createElement('option');
    option.value = color;
    option.textContent = colorLabels[color] || color;
    el.burnColor.appendChild(option);
  }

  const positionLabels = { abajo: 'Abajo', centro: 'Centro', arriba: 'Arriba' };
  el.burnPosition.innerHTML = '';
  for (const position of S.boot.burnPositions || []) {
    const option = document.createElement('option');
    option.value = position;
    option.textContent = positionLabels[position] || position;
    el.burnPosition.appendChild(option);
  }
}

function updateSubsFileLabel() {
  const name = S.subtitleFile ? String(S.subtitleFile).split(/[\\/]/).pop() : 'Ninguno';
  el.subsFileLabel.textContent = name;
  el.subsFileLabel.title = S.subtitleFile || 'Ninguno';
}

async function pickSubtitleFile() {
  try {
    const path = await api.pickSubtitleFile();
    if (!path) return;
    S.subtitleFile = path;
    updateSubsFileLabel();
    refreshPreview();
  } catch (error) {
    toast(`No se pudo abrir el archivo: ${error.message || error}`, 'error');
  }
}

function updateSubsTrackOptions() {
  const active = S.files.find((f) => f.path === S.activeFile);
  const subs = (active && active.media && active.media.subtitles) || [];
  el.subsTrack.innerHTML = '';

  if (subs.length === 0) {
    const option = document.createElement('option');
    option.value = '';
    option.textContent = 'Sin pistas incrustadas';
    el.subsTrack.appendChild(option);
    el.subsTrack.disabled = true;
    return;
  }

  el.subsTrack.disabled = false;
  subs.forEach((sub, index) => {
    const option = document.createElement('option');
    option.value = String(index);
    const parts = [`${index + 1}`, sub.codec];
    if (sub.language) parts.push(sub.language);
    if (sub.title) parts.push(sub.title);
    option.textContent = parts.join(' · ');
    el.subsTrack.appendChild(option);
  });
}

function updateSubsControls() {
  if (S.task !== 'subs') return;
  const mode = el.subsMode.value;

  el.subsTrackField.classList.toggle('hidden', mode === 'mux' || mode === 'edit');
  el.subsFormatField.classList.toggle('hidden', mode !== 'extract');
  el.subsFileField.classList.toggle('hidden', mode === 'extract');
  el.subsMetaFields.classList.toggle('hidden', mode !== 'mux');
  el.subsDefaultField.classList.toggle('hidden', mode !== 'mux');
  el.burnStyleBox.classList.toggle('hidden', mode !== 'burn');
  el.subsEditorActions.classList.toggle('hidden', mode !== 'edit');

  const burning = mode === 'burn';
  for (const control of [el.vcodec, el.quality, el.vpreset, el.resolution]) {
    if (control) control.disabled = !burning;
  }
}

function populatePresets() {
  el.preset.innerHTML = '<option value="">Personalizado</option>';
  const presets = (S.boot.presets || []).filter((p) => p.task === S.task);
  for (const preset of presets) {
    const option = document.createElement('option');
    option.value = preset.id;
    option.textContent = preset.label;
    el.preset.appendChild(option);
  }
  el.presetDesc.textContent = presets.length
    ? 'Elige un perfil para rellenar los ajustes, o configúralo a tu gusto.'
    : 'Configura los ajustes a tu gusto.';
}

function onPresetChange() {
  const preset = (S.boot.presets || []).find((p) => p.id === el.preset.value);
  if (!preset) {
    el.presetDesc.textContent = 'Configuración personalizada.';
    S.filterChain = '';
    S.audioFilter = '';
    refreshPreview();
    return;
  }

  const options = preset.options;
  if (options.container && S.boot.containers[options.container]) {
    el.container.value = options.container;
  }
  refreshCodecSelects();

  if (options.videoCodec) el.vcodec.value = options.videoCodec;
  refreshEncoderControls();

  if (typeof options.quality === 'number') el.quality.value = String(options.quality);
  if (options.preset) {
    const exists = [...el.vpreset.options].some((o) => o.value === String(options.preset));
    if (exists) el.vpreset.value = String(options.preset);
  }

  if (options.maxWidth || options.maxHeight) {
    const target = options.maxHeight || options.maxWidth;
    const match = [...el.resolution.options].find((o) => Number(o.value) === Number(target));
    if (match) el.resolution.value = match.value;
  }

  if (options.audioCodec) el.acodec.value = options.audioCodec;
  refreshAudioControls();
  if (options.audioBitrate) {
    const exists = [...el.abitrate.options].some((o) => o.value === options.audioBitrate);
    if (exists) el.abitrate.value = options.audioBitrate;
  }

  el.twoPass.checked = Boolean(options.twoPass);
  if (S.task === 'concat' && options.concatMode) {
    el.concatMode.value = options.concatMode;
  }
  S.filterChain = options.filterChain || '';
  S.audioFilter = options.audioFilter || '';

  el.presetDesc.textContent = preset.description || '';
  paintQuality();
  updateConcatControls();
  refreshPreview();
}

function onTrimToggle() {
  const enabled = el.trimEnabled.checked;
  el.trimBox.classList.toggle('hidden', !enabled);
  if (enabled) {
    const entry = S.files.find((f) => f.path === S.activeFile);
    const duration = entry && entry.media ? entry.media.duration : null;
    if (duration && (!el.trimEnd.value || parseTime(el.trimEnd.value) === 0)) {
      el.trimEnd.value = formatClock(duration);
    }
    updateTrimHint();
  }
  refreshPreview();
}

function useFullDuration() {
  const entry = S.files.find((f) => f.path === S.activeFile);
  const duration = entry && entry.media ? entry.media.duration : null;
  if (duration) {
    el.trimStart.value = '00:00:00.000';
    el.trimEnd.value = formatClock(duration);
    updateTrimHint();
    refreshPreview();
  }
}

function updateTrimHint() {
  const start = parseTime(el.trimStart.value) || 0;
  const end = parseTime(el.trimEnd.value) || 0;
  if (end > start) {
    el.trimHint.textContent = `Duración resultante: ${formatClock(end - start)}`;
  } else {
    el.trimHint.textContent = 'El fin debe ser mayor que el inicio.';
  }
}

function collectOptions() {
  const task = S.task;
  const resolution = Number(el.resolution.value) || 0;
  // «1080p» significa caja de 1920x1080 (no limitar ancho y alto al mismo valor).
  const maxWidth = task === 'image' ? Number(el.imgWidth.value) : (resolution ? Math.round((resolution * 16) / 9) : null);
  const maxHeight = task === 'image' ? null : (resolution || null);

  return {
    task,
    container: el.container.value,
    videoCodec: task === 'audio' ? 'none' : (task === 'image' ? 'mjpeg' : el.vcodec.value),
    quality: Number(el.quality.value),
    qualityMode: el.qualityMode.value,
    videoBitrate: el.videoBitrate.value,
    preset: el.vpreset.value || null,
    maxWidth,
    maxHeight,
    audioCodec: task === 'image' || task === 'gif' ? 'none' : el.acodec.value,
    audioBitrate: el.abitrate.value || null,
    audioTrack: Number(el.audioTrack.value ?? -1),
    subtitleTrack: Number(el.subtitleTrack.value ?? -1),
    normalizeLoudness: el.normalizeLoudness.checked,
    loudnessTarget: Number(el.loudnessTarget.value) || -16,
    captureSource: el.captureSource.value,
    captureTitle: el.captureTitle.value.trim(),
    captureDevice: el.captureDevice.value.trim(),
    captureDuration: Number(el.captureDuration.value) || 0,
    captureFps: Number(el.captureFps.value) || 30,
    twoPass: task === 'video' && el.twoPass.checked,
    trim: {
      enabled: task !== 'image' && el.trimEnabled.checked,
      start: parseTime(el.trimStart.value) || 0,
      end: parseTime(el.trimEnd.value) || 0,
      mode: el.trimMode.value,
    },
    gifFps: Number(el.gifFps.value),
    gifWidth: Number(el.gifWidth.value),
    imageTime: Number(el.imgTime.value) || 0,
    speed: Number(el.speed.value) || 1,
    fps: Number(el.fps.value) || 0,
    rotate: Number(el.rotate.value) || 0,
    flip: el.flip.value || 'none',
    crop: {
      left: Number(el.cropLeft.value) || 0,
      top: Number(el.cropTop.value) || 0,
      right: Number(el.cropRight.value) || 0,
      bottom: Number(el.cropBottom.value) || 0,
    },
    sheetCount: Number(el.sheetCount.value) || 9,
    sheetWidth: Number(el.sheetWidth.value) || 480,
    concatMode: el.concatMode.value || 'copy',
    concatTransition: el.concatTransition.value || 'none',
    concatTransitionDuration: Number(el.transitionDuration.value) || 1,
    subsMode: el.subsMode.value,
    subtitleStream: Number(el.subsTrack.value) || 0,
    subtitleFormat: el.subsFormat.value,
    subtitleFile: S.subtitleFile || null,
    subtitleLanguage: el.subsLanguage.value || null,
    subtitleTitle: el.subsTitle.value.trim(),
    subtitleDefault: el.subsDefault.checked,
    burnStyle: {
      font: el.burnFont.value || 'Arial',
      size: Number(el.burnSize.value) || 24,
      color: el.burnColor.value || 'blanco',
      position: el.burnPosition.value || 'abajo',
      bold: el.burnBold.checked,
    },
    filterChain: S.filterChain,
    audioFilter: S.audioFilter,
  };
}

/* ------------------------------------------------------------------ */
/* Vista previa                                                        */
/* ------------------------------------------------------------------ */

function refreshPreview() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(runPreview, 220);
}

async function runPreview() {
  const options = collectOptions();

  if (options.task === 'subs' && options.subsMode === 'edit') {
    S.preview.ok = true;
    S.preview.issues = [];
    el.commandPreview.textContent = 'Editor de subtítulos: aquí no se ejecuta FFmpeg. '
      + 'Abre el editor, ajusta textos y tiempos, y guarda el archivo.';
    renderIssues([]);
    updateEstimate({ estimatedBytes: 0, duration: null });
    updateEnqueueState();
    return;
  }

  const active = S.files.find((f) => f.path === S.activeFile);
  const isCapture = options.task === 'capture';
  const targets = isCapture
    ? []
    : (options.task === 'concat'
      ? S.files.filter((f) => f.media).map((f) => f.path)
      : (active && active.media ? [active.path] : []));

  if (targets.length === 0 && !isCapture) {
    el.commandPreview.textContent = S.boot.ok
      ? (options.task === 'concat'
        ? 'Añade al menos dos clips para unirlos.'
        : 'Elige un archivo para ver el comando.')
      : 'FFmpeg no está disponible.';
    el.issueList.innerHTML = '';
    S.preview = { ok: false, issues: [] };
    renderEstimate(null);
    updateEnqueueState();
    return;
  }

  try {
    const result = await api.preview(targets, options);
    S.preview = result;
    el.commandPreview.textContent = result.preview || 'No se pudo generar el comando.';
    renderIssues(result.issues || []);
    renderEstimate(result);
  } catch (error) {
    el.commandPreview.textContent = `Error: ${error.message || error}`;
    renderIssues([{ level: 'error', message: String(error.message || error) }]);
    renderEstimate(null);
  }
  updateEnqueueState();
}

function renderEstimate(result) {
  if (!result || !result.ok || !result.estimatedBytes) {
    el.estimateInfo.classList.add('hidden');
    return;
  }
  const size = formatSize(result.estimatedBytes);
  const duration = Number.isFinite(result.duration) && result.duration > 0
    ? ` · ${formatClock(result.duration)}`
    : '';
  el.estimateInfo.innerHTML = `Salida estimada: <strong>~${size}</strong>${duration}`;
  el.estimateInfo.classList.remove('hidden');
}

function renderIssues(issues) {
  el.issueList.innerHTML = '';
  for (const issue of issues) {
    const div = document.createElement('div');
    div.className = `issue ${issue.level}`;
    div.textContent = issue.message;
    el.issueList.appendChild(div);
  }
}

function updateEnqueueState() {
  const valid = S.files.filter((f) => f.media);
  const hasErrors = (S.preview.issues || []).some((i) => i.level === 'error');
  const isCapture = S.task === 'capture';
  const editing = S.task === 'subs' && el.subsMode.value === 'edit';
  const enoughFiles = isCapture
    ? true
    : (S.task === 'concat' ? valid.length >= 2 : valid.length > 0);
  const activeReady = isCapture
    ? true
    : (S.task !== 'subs' || Boolean(S.activeFile && valid.some((f) => f.path === S.activeFile)));

  el.enqueueBtn.disabled = editing || !enoughFiles || !activeReady || hasErrors || !S.boot.ok;
  if (editing) {
    el.enqueueBtn.textContent = 'Editor activo';
  } else if (isCapture) {
    el.enqueueBtn.textContent = 'Iniciar grabación';
  } else if (S.task === 'concat') {
    el.enqueueBtn.textContent = `Unir ${valid.length} ${valid.length === 1 ? 'clip' : 'clips'}`;
  } else {
    el.enqueueBtn.textContent = 'Añadir a la cola';
  }
}

/* ------------------------------------------------------------------ */
/* Encolar                                                             */
/* ------------------------------------------------------------------ */

async function enqueue() {
  const options = collectOptions();

  if (options.task === 'capture') {
    el.enqueueBtn.disabled = true;
    try {
      const result = await api.addCapture(options, S.outputDir);
      if (result.added > 0) toast('Grabación añadida a la cola.', 'ok');
      if (result.rejected && result.rejected.length > 0) {
        const rows = result.rejected.map((item) => `
          <div class="field">
            <p><strong>Grabación</strong></p>
            ${item.messages.map((m) => `<p class="error-line">${escapeHtml(m)}</p>`).join('')}
          </div>`).join('');
        openModal('No se pudo iniciar la grabación', rows);
      }
      applySnapshot(result.snapshot);
    } catch (error) {
      toast(`No se pudo iniciar: ${error.message || error}`, 'error');
    } finally {
      updateEnqueueState();
    }
    return;
  }

  const active = S.files.find((f) => f.path === S.activeFile);
  const validFiles = S.files.filter((f) => f.media).map((f) => f.path);
  const files = options.task === 'subs'
    ? (active && active.media ? [active.path] : [])
    : validFiles;

  if (files.length === 0) {
    toast('Añade al menos un archivo válido.', 'error');
    return;
  }
  if (options.task === 'concat' && files.length < 2) {
    toast('Para unir hacen falta al menos dos clips.', 'error');
    return;
  }

  el.enqueueBtn.disabled = true;
  try {
    const result = await api.addToQueue(files, options, S.outputDir);
    if (result.added > 0) {
      const message = options.task === 'concat'
        ? `Unión de ${files.length} clips añadida a la cola.`
        : `${result.added} ${result.added === 1 ? 'trabajo añadido' : 'trabajos añadidos'} a la cola.`;
      toast(message, 'ok');
    }
    if (result.rejected && result.rejected.length > 0) {
      const rows = result.rejected.map((item) => `
        <div class="field">
          <p><strong>${escapeHtml(String(item.file).split(/[\\/]/).pop())}</strong></p>
          ${item.messages.map((m) => `<p class="error-line">${escapeHtml(m)}</p>`).join('')}
        </div>
      `).join('');
      openModal('No se pudieron añadir algunos archivos', rows);
    }
    applySnapshot(result.snapshot);
  } catch (error) {
    toast(`No se pudo encolar: ${error.message || error}`, 'error');
  } finally {
    updateEnqueueState();
  }
}

/* ------------------------------------------------------------------ */
/* Cola y registro                                                     */
/* ------------------------------------------------------------------ */

function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(async () => {
    try {
      const snapshot = await api.queueState();
      applySnapshot(snapshot);
    } catch {
      /* la ventana puede estar cerrándose */
    }
  }, 700);
}

function applySnapshot(snapshot) {
  if (!snapshot) return;
  const previous = new Map((S.queue.jobs || []).map((job) => [job.id, job.status]));
  const signature = (snapshot.jobs || [])
    .map((job) => `${job.id}:${job.status}:${job.error ? job.error.title : ''}`)
    .join('|') + `#${snapshot.paused}#${snapshot.running}`;

  S.queue = snapshot;

  if (signature !== lastSignature) {
    lastSignature = signature;
    renderQueue(snapshot);
  } else {
    for (const job of snapshot.jobs) updateJobNode(job);
    renderLog();
    updatePauseButton();
  }

  for (const job of snapshot.jobs) {
    const before = previous.get(job.id);
    if (before && before !== job.status) notifyFinished(job);
  }
}

function notifyFinished(job) {
  if (job.status === 'done') {
    toast(`Terminado: ${job.inputName}`, 'ok');
  } else if (job.status === 'error') {
    toast(`Error en ${job.inputName}: ${job.error ? job.error.title : ''}`, 'error');
  }
}

function renderQueue(snapshot) {
  const jobs = snapshot.jobs || [];

  if (jobs.length === 0) {
    el.queueList.innerHTML = `
      <div class="empty">
        <p>Los trabajos aparecerán aquí.</p>
        <span class="muted">Se procesan de uno en uno para no saturar el equipo.</span>
      </div>`;
    updatePauseButton();
    return;
  }

  el.queueList.innerHTML = jobs.map((job) => jobMarkup(job)).join('');

  for (const node of el.queueList.querySelectorAll('.job')) {
    node.addEventListener('click', (event) => {
      if (event.target.dataset.action) return;
      selectLogJob(node.dataset.id);
    });
  }

  for (const button of el.queueList.querySelectorAll('[data-action]')) {
    button.addEventListener('click', async (event) => {
      event.stopPropagation();
      const { id, action } = event.target.dataset;
      if (action === 'cancel') applySnapshot(await api.cancelJob(id));
      if (action === 'remove') applySnapshot(await api.removeJob(id));
      if (action === 'reveal') api.reveal(button.dataset.path);
      if (action === 'play') api.open(button.dataset.path);
    });
  }

  if (!S.logJobId || !jobs.some((j) => j.id === S.logJobId)) {
    const current = jobs.find((j) => j.status === 'running') || jobs[jobs.length - 1];
    S.logJobId = current ? current.id : null;
  }
  renderLog();
  updatePauseButton();
}

function jobMarkup(job) {
  let statusLabel = {
    pending: 'En espera', running: 'Procesando', done: 'Listo', error: 'Error', cancelled: 'Cancelado',
  }[job.status] || job.status;
  if (job.status === 'running' && job.retrying) statusLabel = 'CPU';

  const percent = job.status === 'done' ? 100 : job.percent || 0;
  const speed = job.speed ? `${job.speed.toFixed(1)}×` : '';
  const eta = job.etaSeconds ? `faltan ${formatEta(job.etaSeconds)}` : '';
  const pass = job.passCount > 1 ? ` · pasada ${job.pass}/${job.passCount}` : '';
  const elapsed = job.startedAt && job.finishedAt
    ? ` · ${((job.finishedAt - job.startedAt) / 1000).toFixed(1)} s`
    : '';

  const actions = [];
  if (job.status === 'running' || job.status === 'pending') {
    actions.push(`<button class="link-btn" data-action="cancel" data-id="${job.id}">Cancelar</button>`);
  }
  if (job.status === 'pending') {
    actions.push(`<button class="link-btn" data-action="remove" data-id="${job.id}">Quitar</button>`);
  }
  if (job.status === 'done') {
    actions.push(`<button class="link-btn" data-action="reveal" data-path="${escapeHtml(job.output)}">Abrir carpeta</button>`);
    actions.push(`<button class="link-btn" data-action="play" data-path="${escapeHtml(job.output)}">Reproducir</button>`);
  }
  if (job.status === 'error') {
    actions.push(`<button class="link-btn" data-action="remove" data-id="${job.id}">Quitar</button>`);
  }

  return `
    <div class="job ${job.status}${job.id === S.logJobId ? ' active' : ''}" data-id="${job.id}">
      <div class="job-top">
        <div style="min-width:0">
          <div class="job-name" title="${escapeHtml(job.input)}">${escapeHtml(job.inputName)}</div>
          <div class="job-sub" title="${escapeHtml(job.output)}">${escapeHtml(job.output)}</div>
        </div>
        <span class="badge ${job.status}">${statusLabel}</span>
      </div>
      <div class="progress"><span style="width:${percent}%"></span></div>
      <div class="job-stats">
        <span>${percent.toFixed(0)}%${pass}</span>
        <span>${job.status === 'running' ? [speed, eta].filter(Boolean).join(' · ') : elapsed}</span>
      </div>
      ${job.error ? `<div class="job-error">${escapeHtml(job.error.title)}</div>` : ''}
      ${actions.length ? `<div class="job-actions">${actions.join('')}</div>` : ''}
    </div>
  `;
}

function updateJobNode(job) {
  const node = el.queueList.querySelector(`.job[data-id="${job.id}"]`);
  if (!node) return;
  const percent = job.status === 'done' ? 100 : job.percent || 0;
  const bar = node.querySelector('.progress > span');
  if (bar) bar.style.width = `${percent}%`;

  const stats = node.querySelector('.job-stats');
  if (stats) {
    const pass = job.passCount > 1 ? ` · pasada ${job.pass}/${job.passCount}` : '';
    const speed = job.speed ? `${job.speed.toFixed(1)}×` : '';
    const eta = job.etaSeconds ? `faltan ${formatEta(job.etaSeconds)}` : '';
    stats.innerHTML = `<span>${percent.toFixed(0)}%${pass}</span><span>${[speed, eta].filter(Boolean).join(' · ')}</span>`;
  }
}

function selectLogJob(jobId) {
  S.logJobId = jobId;
  for (const node of el.queueList.querySelectorAll('.job')) {
    node.classList.toggle('active', node.dataset.id === jobId);
  }
  renderLog();
}

function renderLog() {
  const job = S.queue.jobs.find((j) => j.id === S.logJobId);
  if (!job) {
    el.logTitle.textContent = 'Registro';
    el.logOutput.textContent = 'Sin actividad todavía.';
    return;
  }
  el.logTitle.textContent = `Registro · ${job.inputName}`;
  let lines = job.logTail && job.logTail.length ? job.logTail : [];
  if (lines.length === 0) {
    if (job.status === 'done') {
      const seconds = job.startedAt && job.finishedAt
        ? ` en ${((job.finishedAt - job.startedAt) / 1000).toFixed(1)} s`
        : '';
      lines = [`Trabajo completado sin incidencias${seconds}.`, `Salida: ${job.output}`];
    } else if (job.status === 'queued' || job.status === 'pending') {
      lines = ['En espera de turno.'];
    } else {
      lines = ['(sin mensajes)'];
    }
  }
  const text = lines.join('\n');
  if (el.logOutput.textContent !== text) el.logOutput.textContent = text;
  el.logOutput.scrollTop = el.logOutput.scrollHeight;
}

async function togglePause() {
  const hasPending = S.queue.jobs.some((job) => job.status === 'pending');
  if (S.queue.paused || (!S.queue.running && hasPending)) {
    applySnapshot(await api.startQueue());
  } else {
    applySnapshot(await api.pauseQueue());
  }
}

function updatePauseButton() {
  const paused = S.queue.paused;
  el.pauseBtn.textContent = paused ? '▶' : '⏸';
  el.pauseBtn.title = paused ? 'Reanudar cola' : 'Pausar cola';
}

/* ------------------------------------------------------------------ */
/* Ajustes                                                             */
/* ------------------------------------------------------------------ */

async function chooseOutputDir() {
  const dir = await api.pickOutputDir();
  if (!dir) return;
  S.outputDir = dir;
  await api.saveSettings({ outputDir: dir });
  updateOutputDirLabel();
  refreshPreview();
}

function updateOutputDirLabel() {
  el.outputDirLabel.textContent = S.outputDir || 'Junto al original';
  el.outputDirLabel.title = S.outputDir || 'Junto al original';
}

function openSettings() {
  const version = S.boot.ffmpeg.version ? escapeHtml(S.boot.ffmpeg.version) : 'No detectado';
  const hw = S.hardware ? escapeHtml(S.hardware.summary) : 'Comprobando…';
  openModal('Ajustes', `
    <div class="modal-row">
      <div>
        <p>FFmpeg</p>
        <p class="hint" style="max-width:380px;word-break:break-all">${escapeHtml(S.boot.ffmpeg.path || 'No encontrado')}</p>
        <p class="hint">${version}</p>
      </div>
      <button class="btn btn-ghost btn-sm" id="settingsPickFfmpeg">Cambiar…</button>
    </div>
    <div class="modal-row">
      <div>
        <p>Aceleración por hardware</p>
        <p class="hint">${hw}</p>
      </div>
      <button class="btn btn-ghost btn-sm" id="settingsRedetect">Volver a detectar</button>
    </div>
    <div class="modal-row">
      <div>
        <p>Carpeta de salida</p>
        <p class="hint" style="max-width:380px;word-break:break-all">${escapeHtml(S.outputDir || 'Junto al archivo original')}</p>
      </div>
      <div style="display:flex;gap:6px">
        <button class="btn btn-ghost btn-sm" id="settingsResetOutput">Original</button>
        <button class="btn btn-ghost btn-sm" id="settingsPickOutput">Cambiar…</button>
      </div>
    </div>
    <div class="modal-row">
      <div>
        <p>Abrir la carpeta al terminar</p>
        <p class="hint">Muestra el archivo generado en el Explorador.</p>
      </div>
      <input type="checkbox" id="settingsOpenWhenDone" ${S.boot.settings.openOutputWhenDone ? 'checked' : ''} />
    </div>
  `);

  $('settingsPickFfmpeg').addEventListener('click', pickFfmpeg);
  $('settingsPickOutput').addEventListener('click', async () => { closeModal(); await chooseOutputDir(); });
  $('settingsResetOutput').addEventListener('click', async () => {
    S.outputDir = null;
    await api.saveSettings({ outputDir: null });
    updateOutputDirLabel();
    closeModal();
    refreshPreview();
  });
  $('settingsRedetect').addEventListener('click', async () => {
    const button = $('settingsRedetect');
    button.textContent = 'Detectando…';
    button.disabled = true;
    const hardware = await api.redetectHardware();
    S.hardware = hardware;
    renderHeader();
    closeModal();
    toast(`Hardware: ${hardware.summary}`, 'ok');
  });
  $('settingsOpenWhenDone').addEventListener('change', async (event) => {
    S.boot.settings.openOutputWhenDone = event.target.checked;
    await api.saveSettings({ openOutputWhenDone: event.target.checked });
  });
}

async function pickFfmpeg() {
  const result = await api.pickFfmpeg();
  if (!result || !result.ok) {
    toast((result && result.message) || 'No se pudo usar ese ejecutable.', 'error');
    return;
  }
  S.boot = { ...S.boot, ...result };
  S.hardware = result.hardware;
  renderHeader();
  closeModal();
  toast('FFmpeg actualizado.', 'ok');
  if (!S.hardware) pollHardware();
  refreshPreview();
}

/* ------------------------------------------------------------------ */
/* Arranque del documento                                              */
/* ------------------------------------------------------------------ */

function start() {
  api = buildApi();
  window.addEventListener('error', (event) => {
    if (el.toast) toast(`Error de interfaz: ${event.message}`, 'error');
  });
  init();
}

if (window.pywebview && window.pywebview.api) {
  start();
} else {
  window.addEventListener('pywebviewready', start);
}
