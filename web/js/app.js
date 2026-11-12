import { RW, RH, PRESETS, WEIGHTS, css, toInput, fromInput, layout, heightOf, rectOf, moveTo, drawLayers,
         drawBackground, drawVideo, drawText, roundRect, setOnAssetLoaded } from "./render.js";
import { exportReel } from "./export.js";
import * as store from "./store.js";
import * as cloud from "./cloud.js";

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

// ---------------------------------------------------------------- state
// S is exactly a template (same keys as the Windows/iPhone apps). R is everything else.
const defaults = () => ({
  version: 1, name: "", background: { mode: "black", color: "#FF1F6F5C" }, preset: PRESETS[0][0],
  zone: [250, 450, 120, 120], video: { scale: 100, dx: 0, dy: 0, radius: 0 }, clamp: true, layers: [],
  cover: { title: "", title_size: 110, title_color: "#FFFFFFFF", title_y: 8, include_layers: false, zoom: 100, grid: true },
  export: { quality: 0, fps: 0, save_cover: false, cover_first: true, cover_embed: true },
});
let S = defaults();
const R = {
  sel: null, locked: false, showZone: true, tab: "layers", file: null, url: null, name: "",
  duration: 0, trimStart: 0, trimEnd: 0, playing: false, coverTime: 0, coverCX: 0.5, coverCY: 0.5,
  coverFrame: null, guideX: false,
};
let nextId = 1;
const video = $("#src");
const view = $("#view");
const ctx = view.getContext("2d");
const overlay = document.createElement("canvas");
overlay.width = RW; overlay.height = RH;

const newText = (text = "Your text here") => ({
  kind: "text", text, family: "Inter Display", weight: 700, size: 64, color: "#FFFFFFFF", align: "center", style: "box",
  box_color: "#FF000000", box_alpha: 0.55, radius: 28, pad: 30, spacing: 1.18, shadow: false, opacity: 1, w: 760,
  x: RW / 2, y: RH / 2, attach_gap: null, from_post: false, fit_one_line: false, _id: nextId++,
});
const selected = () => S.layers.find((l) => l._id === R.sel) || null;
const status = (m) => { $("#status").textContent = m; };

// ---------------------------------------------------------------- images
const imgCache = new Map();
function mimeOf(b64, svg) {
  if (svg) return "image/svg+xml";
  if (b64.startsWith("/9j/")) return "image/jpeg";
  if (b64.startsWith("UklGR")) return "image/webp";
  if (b64.startsWith("R0lG")) return "image/gif";
  return "image/png";
}
function attachImage(l) {
  const key = l.png;
  if (imgCache.has(key)) { l._img = imgCache.get(key); return; }
  const img = new Image();
  img.onload = () => refresh(false);
  img.src = `data:${mimeOf(l.png, l.svg)};base64,${l.png}`;
  imgCache.set(key, img);
  l._img = img;
}

// ---------------------------------------------------------------- geometry
const zoneRect = () => {
  const [t, b, l, r] = S.zone;
  return { x: l, y: t, w: Math.max(10, RW - l - r), h: Math.max(10, RH - t - b) };
};
const aspect = () => (video.videoWidth && video.videoHeight ? video.videoWidth / video.videoHeight : 16 / 9);
function videoRect(ar = aspect()) {
  const z = zoneRect();
  const bw = Math.min(z.w, z.h * ar), k = S.video.scale / 100;
  const w = bw * k, h = (bw / ar) * k;
  return { x: z.x + z.w / 2 + S.video.dx - w / 2, y: z.y + z.h / 2 + S.video.dy - h / 2, w, h };
}
const baseSize = (l) => l._fitBase ?? l.size;
const unfit = (l) => { if (l._fitBase != null) { l.size = l._fitBase; l._fitBase = null; } };
function sitOnVideo(l, gap) { const r = rectOf(l); moveTo(l, r.x, videoRect().y - gap - r.h); }

/** One-line text: as big as fits (max 140 px, using up to 55% of the room above the video),
 *  a little closer to the video than to the top of the safe zone. */
function fitOneLiner(l) {
  const base = baseSize(l);
  unfit(l);
  const vr = videoRect(), z = zoneRect();
  const text = (l.text || "").trim();
  const space = vr.y - z.y;
  if (!text || text.includes("\n") || layout(l).lines.length !== 1 || space <= heightOf(l) + 28) return false;
  let best = base;
  for (let s = base + 2; s <= 140; s += 2) {
    const t = { ...l, size: s };
    if (layout(t).lines.length > 1 || heightOf(t) > space * 0.55) break;
    best = s;
  }
  if (best !== base) { l.size = best; l._fitBase = base; }
  const free = vr.y - z.y - heightOf(l);
  moveTo(l, l.x - l.w / 2, vr.y - Math.max(28, free * 0.38) - heightOf(l));
  return true;
}
function place(l) {
  if (l.kind === "text" && l.fit_one_line) { if (!fitOneLiner(l)) sitOnVideo(l, l.attach_gap ?? 24); return; }
  if (l.attach_gap != null) sitOnVideo(l, l.attach_gap);
}
function clampLayer(l) {
  if (!S.clamp || R.locked) return;
  const z = zoneRect();
  if (l.w > z.w) l.w = z.w;
  const r = rectOf(l);
  moveTo(l, Math.min(Math.max(r.x, z.x), z.x + z.w - r.w), Math.min(Math.max(r.y, z.y), Math.max(z.y, z.y + z.h - r.h)));
}

// ---------------------------------------------------------------- drawing
function renderOverlay() {
  const o = overlay.getContext("2d");
  o.clearRect(0, 0, RW, RH);
  drawLayers(o, S.layers);
}

function coverCrop(sw, sh, cx = R.coverCX, cy = R.coverCY) {
  const h = Math.min(sh, (sw * 16) / 9) / (S.cover.zoom / 100), w = (h * 9) / 16;
  const x = Math.min(Math.max(cx, w / 2 / sw), 1 - w / 2 / sw), y = Math.min(Math.max(cy, h / 2 / sh), 1 - h / 2 / sh);
  return { x: x * sw - w / 2, y: y * sh - h / 2, w, h, cx: x, cy: y };
}
function drawCover(c) {
  c.fillStyle = "#000"; c.fillRect(0, 0, RW, RH);
  const f = R.coverFrame;
  if (f) {
    const cr = coverCrop(f.width, f.height);
    c.imageSmoothingQuality = "high";
    c.drawImage(f, cr.x, cr.y, cr.w, cr.h, 0, 0, RW, RH);
  }
  if (S.cover.include_layers) drawLayers(c, S.layers);
  const text = S.cover.title.trim();
  if (text) {
    const z = zoneRect();
    const t = { ...newText(text), style: "plain", shadow: true, weight: 900, size: S.cover.title_size,
                color: S.cover.title_color, w: z.w - 40, x: z.x + z.w / 2 };
    t.y = z.y + ((z.h - heightOf(t)) * S.cover.title_y) / 100;
    drawText(c, t);
  }
}
function coverCanvas() {
  const c = document.createElement("canvas");
  c.width = RW; c.height = RH;
  drawCover(c.getContext("2d"));
  return c;
}

function draw() {
  if (R.tab === "cover") { drawCover(ctx); return; }
  const ready = R.url && video.readyState >= 2;
  drawBackground(ctx, S, ready ? video : null, video.videoWidth, video.videoHeight);
  const vr = videoRect();
  if (ready) drawVideo(ctx, video, vr, S.video.radius);
  else {
    ctx.fillStyle = "rgba(255,255,255,0.07)"; ctx.fillRect(vr.x, vr.y, vr.w, vr.h);
    ctx.fillStyle = "#8A8C93"; ctx.font = '500 38px "Inter Display", sans-serif'; ctx.textAlign = "center";
    ctx.fillText("Your 16:9 video goes here", vr.x + vr.w / 2, vr.y + vr.h / 2 + 12); ctx.textAlign = "start";
  }
  ctx.drawImage(overlay, 0, 0);
  if (R.showZone) {
    const z = zoneRect();
    ctx.save(); ctx.setLineDash([12, 10]); ctx.strokeStyle = "rgba(255,214,10,.7)"; ctx.lineWidth = 3;
    ctx.strokeRect(z.x, z.y, z.w, z.h); ctx.restore();
  }
  const s = selected();
  if (s) {
    const r = rectOf(s);
    ctx.save(); ctx.strokeStyle = "#FFA53A"; ctx.lineWidth = 4; ctx.strokeRect(r.x - 4, r.y - 4, r.w + 8, r.h + 8); ctx.restore();
  }
  if (R.guideX) { ctx.fillStyle = "#FF3D8B"; ctx.fillRect(RW / 2 - 1.5, 0, 3, RH); }
}

/** After any change: place attached layers, redraw, update the panel. */
function refresh(syncUI = true) {
  S.layers.forEach(place);
  renderOverlay();
  draw();
  if (syncUI) syncPanel();
}
setOnAssetLoaded(() => refresh(false));
document.fonts && document.fonts.ready.then(() => refresh(false));

// ---------------------------------------------------------------- history (undo / redo)
let history = [], future = [], histTimer = null;
const snapshot = () => JSON.stringify({ s: templateState(""), trim: [R.trimStart, R.trimEnd], sel: R.sel });
function resetHistory() { history = [snapshot()]; future = []; updateUndo(); }
function commit() {
  clearTimeout(histTimer);
  histTimer = setTimeout(() => {
    const s = snapshot();
    if (s !== history[history.length - 1]) { history.push(s); if (history.length > 150) history.shift(); future = []; }
    updateUndo();
  }, 250);
}
function updateUndo() { $("#undo").disabled = history.length < 2; $("#redo").disabled = !future.length; }
function restore(snap) {
  const d = JSON.parse(snap);
  const locked = R.locked;
  applyState(d.s);
  R.locked = locked;
  if (R.duration) { R.trimStart = d.trim[0]; R.trimEnd = d.trim[1]; }
  R.sel = S.layers.find((l) => l._id === d.sel) ? d.sel : null;
  refresh();
}
function undo() { if (history.length < 2) return; future.push(history.pop()); restore(history[history.length - 1]); updateUndo(); status("Undone."); }
function redo() { if (!future.length) return; const s = future.pop(); history.push(s); restore(s); updateUndo(); status("Redone."); }

// ---------------------------------------------------------------- templates
function templateState(name) {
  const out = JSON.parse(JSON.stringify({ ...S, layers: [] }));
  out.name = name; out.saved_at = Date.now() / 1000;
  out.layers = S.layers.map((l) => {
    const d = {};
    for (const [k, v] of Object.entries(l)) if (!k.startsWith("_")) d[k] = v;
    if (l.kind === "text") d.size = baseSize(l);
    return d;
  });
  return out;
}
function applyState(d) {
  const base = defaults();
  S = { ...base, ...d, background: { ...base.background, ...(d.background || {}) }, video: { ...base.video, ...(d.video || {}) },
        cover: { ...base.cover, ...(d.cover || {}) }, export: { ...base.export, ...(d.export || {}) } };
  S.layers = (d.layers || []).map((l) => {
    const x = l.kind === "image" ? { ...l, _id: l._id || nextId++ } : { ...newText(""), ...l, _id: l._id || nextId++ };
    delete x.saved_at;
    if (x.kind === "image") attachImage(x);
    return x;
  });
  S.layers.forEach((l) => { if (l._id >= nextId) nextId = l._id + 1; });
}
function useTemplate(json) {
  applyState(json);
  R.sel = null; R.locked = true;
  $("#tplName").textContent = json.name || "Template";
  localStorage.setItem("rm.lastTemplate", json.name || "");
  refresh();
  commit();
  status(`Using “${json.name || "template"}”. Layout locked; you can still change the words.`);
}

// ---------------------------------------------------------------- video
const fmt = (t) => { t = Math.max(0, t); return `${Math.floor(t / 60)}:${(t % 60).toFixed(1).padStart(4, "0")}`; };
async function openVideo(file) {
  if (R.url) URL.revokeObjectURL(R.url);
  R.file = file; R.url = URL.createObjectURL(file); R.name = file.name;
  $("#fileName").textContent = file.name;
  video.src = R.url;
  status("Loading the video…");
  await new Promise((res) => video.addEventListener("loadedmetadata", res, { once: true }));
  R.duration = video.duration; R.trimStart = 0; R.trimEnd = video.duration; R.coverTime = Math.min(0.5, video.duration);
  // iPhones only decode frames after a play: start muted and stop straight away
  video.muted = true;
  await video.play().catch(() => {});
  video.pause(); video.muted = false;
  video.currentTime = 0;
  await new Promise((res) => video.addEventListener("seeked", res, { once: true }));
  $("#play").disabled = false;
  status(`${video.videoWidth} × ${video.videoHeight} loaded. Trim it, then pick a cover and export.`);
  refresh();
  resetHistory();
}
function loop() {
  if (!R.playing) return;
  if (video.currentTime >= R.trimEnd - 0.03 || video.currentTime < R.trimStart - 0.25) video.currentTime = R.trimStart;
  draw();
  updateTransport();
  if (video.requestVideoFrameCallback) video.requestVideoFrameCallback(loop); else requestAnimationFrame(loop);
}
function play() {
  if (!R.url) return;
  if (video.currentTime < R.trimStart || video.currentTime >= R.trimEnd - 0.05) video.currentTime = R.trimStart;
  video.play().then(() => { R.playing = true; setPlayIcon(); loop(); }).catch(() => {});
}
function pause() { video.pause(); R.playing = false; setPlayIcon(); draw(); }
const togglePlay = () => (R.playing ? pause() : play());
function setPlayIcon() { $("#playIcon").setAttribute("d", R.playing ? "M7 5h3v14H7zM14 5h3v14h-3z" : "M8 5v14l11-7z"); }
video.addEventListener("seeked", () => { if (!R.playing) draw(); updateTransport(); });
video.addEventListener("ended", () => { if (R.playing) { video.currentTime = R.trimStart; video.play(); } });

function updateTransport() {
  const d = R.duration || 1;
  const pct = (t) => `${(100 * t) / d}%`;
  $(".trim .sel").style.left = pct(R.trimStart);
  $(".trim .sel").style.width = pct(R.trimEnd - R.trimStart);
  $(".trim .hs").style.left = pct(R.trimStart);
  $(".trim .he").style.left = pct(R.trimEnd);
  $(".trim .ph").style.left = pct(video.currentTime || 0);
  $("#tNow").textContent = fmt((video.currentTime || 0) - R.trimStart);
  $("#tClip").textContent = "Clip " + fmt(R.trimEnd - R.trimStart);
}

// trim bar
(() => {
  const el = $("#trim");
  let mode = null, was = false;
  const tAt = (e) => { const b = el.getBoundingClientRect(); return Math.min(1, Math.max(0, (e.clientX - b.left) / b.width)) * R.duration; };
  el.addEventListener("pointerdown", (e) => {
    if (!R.duration) return;
    el.setPointerCapture(e.pointerId);
    const b = el.getBoundingClientRect(), x = e.clientX - b.left;
    const xs = (R.trimStart / R.duration) * b.width, xe = (R.trimEnd / R.duration) * b.width;
    mode = Math.abs(x - xs) < 22 ? "s" : Math.abs(x - xe) < 22 ? "e" : "seek";
    was = R.playing; if (was) pause();
    move(e);
  });
  const move = (e) => {
    if (!mode) return;
    const t = tAt(e);
    if (mode === "s") { R.trimStart = Math.min(t, R.trimEnd - 0.2); video.currentTime = R.trimStart; }
    else if (mode === "e") { R.trimEnd = Math.max(t, R.trimStart + 0.2); video.currentTime = R.trimEnd; }
    else video.currentTime = t;
    updateTransport();
  };
  el.addEventListener("pointermove", move);
  el.addEventListener("pointerup", () => {
    if (mode === "s" || mode === "e") { video.currentTime = R.trimStart; R.coverTime = Math.min(Math.max(R.coverTime, R.trimStart), R.trimEnd); commit(); }
    mode = null;
    if (was) play();
  });
})();

// ---------------------------------------------------------------- canvas: select, drag, cover framing
(() => {
  let drag = null;
  const pt = (e) => { const b = view.getBoundingClientRect(); return { x: ((e.clientX - b.left) / b.width) * RW, y: ((e.clientY - b.top) / b.height) * RH }; };
  view.addEventListener("pointerdown", (e) => {
    view.setPointerCapture(e.pointerId);
    const p = pt(e);
    if (R.tab === "cover") { drag = { cover: true, p, cx: R.coverCX, cy: R.coverCY }; return; }
    const hit = [...S.layers].reverse().find((l) => { const r = rectOf(l); return p.x >= r.x - 12 && p.x <= r.x + r.w + 12 && p.y >= r.y - 12 && p.y <= r.y + r.h + 12; });
    R.sel = hit ? hit._id : null;
    drag = hit ? { id: hit._id, gx: p.x - hit.x, gy: p.y - hit.y } : null;
    if (hit) showTab("layers");
    refresh();
  });
  view.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const p = pt(e);
    if (drag.cover) {
      const f = R.coverFrame; if (!f) return;
      const cr = coverCrop(f.width, f.height, drag.cx, drag.cy);
      const c = coverCrop(f.width, f.height, drag.cx - ((p.x - drag.p.x) * cr.w) / RW / f.width, drag.cy - ((p.y - drag.p.y) * cr.h) / RH / f.height);
      R.coverCX = c.cx; R.coverCY = c.cy; draw(); return;
    }
    const l = S.layers.find((x) => x._id === drag.id);
    if (!l || R.locked) return;
    let nx = p.x - drag.gx; const ny = p.y - drag.gy;
    R.guideX = Math.abs(nx - RW / 2) < 10; if (R.guideX) nx = RW / 2;
    l.x = nx;
    const held = l.attach_gap != null || l.fit_one_line;
    if (!(held && Math.abs(ny - l.y) < 12)) {        // small wobble keeps an attached layer in place
      if (held) { l.attach_gap = null; l.fit_one_line = false; unfit(l); }
      l.y = ny;
      clampLayer(l);
    }
    refresh(false);
  });
  const end = () => { if (drag) { R.guideX = false; refresh(); commit(); } drag = null; };
  view.addEventListener("pointerup", end);
  view.addEventListener("pointercancel", end);
  view.addEventListener("dblclick", () => { if (selected()?.kind === "text") { showTab("layers"); $("#words").focus(); } });
})();

// ---------------------------------------------------------------- panels
function showTab(t) {
  R.tab = t;
  $$(".tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === t));
  ["frame", "layers", "cover", "export"].forEach((n) => ($(`#p-${n}`).hidden = n !== t));
  if (t === "cover") { if (R.playing) pause(); grabCover(); }
  draw();
}
$$(".tabs button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));

async function grabCover() {
  if (!R.url) return;
  video.currentTime = R.coverTime;
  await new Promise((r) => video.addEventListener("seeked", r, { once: true }));
  const c = R.coverFrame && R.coverFrame.width === video.videoWidth ? R.coverFrame : document.createElement("canvas");
  c.width = video.videoWidth; c.height = video.videoHeight;
  c.getContext("2d").drawImage(video, 0, 0);
  R.coverFrame = c;
  draw();
}

// generic sliders: data-k = "video.scale" | "cover.zoom" | "l.size" …
function getK(k) {
  const [a, b] = k.split(".");
  if (a === "l") { const l = selected(); return l ? (b === "size" ? baseSize(l) : l[b]) : 0; }
  return S[a][b];
}
function setK(k, v) {
  const [a, b] = k.split(".");
  if (a === "l") {
    const l = selected(); if (!l) return;
    if (b === "size" && l._fitBase != null) l._fitBase = v; else l[b] = v;
  } else S[a][b] = v;
}
$$(".slider").forEach((el) => {
  const scale = Number(el.dataset.scale || 1);
  el.innerHTML = `<div class="lab"><span>${el.dataset.label}</span><span class="v"></span></div>
    <input type="range" min="${el.dataset.min}" max="${el.dataset.max}" step="${el.dataset.step || 1}">`;
  const input = el.querySelector("input");
  el._sync = () => { const v = getK(el.dataset.k) * scale; input.value = v; el.querySelector(".v").textContent = Math.round(v) + (el.dataset.suffix || ""); };
  input.addEventListener("input", () => {
    setK(el.dataset.k, Number(input.value) / scale);
    el.querySelector(".v").textContent = Math.round(input.value) + (el.dataset.suffix || "");
    refresh(false);
  });
  input.addEventListener("change", commit);
});

function seg(id, get, set) {
  const el = $(id);
  el.addEventListener("click", (e) => { const b = e.target.closest("button"); if (!b) return; set(b.dataset.v); refresh(); commit(); });
  el._sync = () => el.querySelectorAll("button").forEach((b) => b.classList.toggle("on", String(get()) === b.dataset.v));
  return el;
}
const segs = [
  seg("#bgSeg", () => S.background.mode, (v) => (S.background.mode = v)),
  seg("#alignSeg", () => selected()?.align, (v) => { if (selected()) selected().align = v; }),
  seg("#styleSeg", () => selected()?.style, (v) => { if (selected()) selected().style = v; }),
  seg("#qualSeg", () => S.export.quality, (v) => (S.export.quality = Number(v))),
  seg("#fpsSeg", () => S.export.fps, (v) => (S.export.fps = Number(v))),
];

function bindCheck(id, get, set) {
  const el = $(id);
  el.addEventListener("change", () => { set(el.checked); refresh(); commit(); });
  el._sync = () => (el.checked = !!get());
  return el;
}
const checks = [
  bindCheck("#showZone", () => R.showZone, (v) => (R.showZone = v)),
  bindCheck("#clamp", () => S.clamp, (v) => (S.clamp = v)),
  bindCheck("#shadow", () => selected()?.shadow, (v) => (selected().shadow = v)),
  bindCheck("#tSit", () => selected()?.attach_gap != null, (v) => (selected().attach_gap = v ? 24 : null)),
  bindCheck("#iSit", () => selected()?.attach_gap != null, (v) => (selected().attach_gap = v ? 24 : null)),
  bindCheck("#tFit", () => selected()?.fit_one_line, (v) => { const l = selected(); l.fit_one_line = v; if (!v) unfit(l); }),
  bindCheck("#tPost", () => selected()?.from_post, (v) => (selected().from_post = v)),
  bindCheck("#coverLayers", () => S.cover.include_layers, (v) => (S.cover.include_layers = v)),
  bindCheck("#coverFirst", () => S.export.cover_first, (v) => (S.export.cover_first = v)),
];

function bindColor(id, get, set) {
  const el = $(id);
  el.addEventListener("input", () => { set(fromInput(el.value)); refresh(false); });
  el.addEventListener("change", commit);
  el._sync = () => (el.value = toInput(get()));
  return el;
}
const colors = [
  bindColor("#bgColor", () => S.background.color, (v) => { S.background.color = v; S.background.mode = "custom"; }),
  bindColor("#tColor", () => selected()?.color, (v) => (selected().color = v)),
  bindColor("#boxColor", () => selected()?.box_color, (v) => (selected().box_color = v)),
  bindColor("#titleColor", () => S.cover.title_color, (v) => (S.cover.title_color = v)),
];

// presets and custom zone
$("#preset").innerHTML = PRESETS.map(([n]) => `<option>${n}</option>`).join("");
$("#preset").addEventListener("change", (e) => {
  S.preset = e.target.value;
  const z = PRESETS.find((p) => p[0] === S.preset)[1];
  if (z) S.zone = [...z];
  refresh(); commit();
});
$("#zoneCustom").innerHTML = ["Top", "Bottom", "Left", "Right"].map((n, i) =>
  `<label class="slider"><div class="lab"><span>${n}</span><span class="v"></span></div><input type="range" min="0" max="900" step="5" data-i="${i}"></label>`).join("");
$$("#zoneCustom input").forEach((inp) => {
  inp.addEventListener("input", () => { S.zone[inp.dataset.i] = Number(inp.value); refresh(false); syncZone(); });
  inp.addEventListener("change", commit);
});
function syncZone() { $$("#zoneCustom input").forEach((inp) => { inp.value = S.zone[inp.dataset.i]; inp.parentElement.querySelector(".v").textContent = S.zone[inp.dataset.i] + " px"; }); }

$("#weight").innerHTML = WEIGHTS.map(([w, n]) => `<option value="${w}">${n}</option>`).join("");
$("#weight").addEventListener("change", (e) => { const l = selected(); if (l) { l.weight = Number(e.target.value); refresh(); commit(); } });
$("#words").addEventListener("input", (e) => { const l = selected(); if (l) { l.text = e.target.value; refresh(false); renderList(); commit(); } });
$("#resetVideo").addEventListener("click", () => { Object.assign(S.video, { scale: 100, dx: 0, dy: 0 }); refresh(); commit(); });
$("#coverTitle").addEventListener("input", (e) => { S.cover.title = e.target.value; $("#titleCtl").hidden = !S.cover.title; draw(); commit(); });
$("#coverTime").addEventListener("change", (e) => { R.coverTime = Number(e.target.value); grabCover(); });
$("#coverTime").addEventListener("input", (e) => { R.coverTime = Number(e.target.value); video.currentTime = R.coverTime; });
$("#saveCover").addEventListener("click", () => {
  coverCanvas().toBlob((b) => saveBlob(b, (R.name.replace(/\.[^.]+$/, "") || "reel") + "_cover.png"), "image/png");
});
$("#unlockBtn").addEventListener("click", () => { R.locked = false; syncPanel(); });
$("#lock").addEventListener("click", () => { R.locked = !R.locked; syncPanel(); status(R.locked ? "Layout locked." : "Layout unlocked."); });

function renderList() {
  const ul = $("#layerList");
  ul.innerHTML = "";
  [...S.layers].reverse().forEach((l) => {
    const li = document.createElement("li");
    li.className = l._id === R.sel ? "on" : "";
    const label = l.kind === "image" ? l.name || "image" : (l.text || "").replace(/\s+/g, " ").trim().slice(0, 40) || "Empty text";
    li.innerHTML = `<span>${l.kind === "image" ? "🖼" : "T"}</span><span class="t"></span>${l.from_post ? '<span class="tag">X caption</span>' : ""}`;
    li.querySelector(".t").textContent = label;
    li.addEventListener("click", () => { R.sel = l._id; refresh(); });
    ul.appendChild(li);
  });
  $("#layersEmpty").hidden = S.layers.length > 0;
}

function syncPanel() {
  const l = selected();
  $("#textCtl").hidden = !(l && l.kind === "text");
  $("#imgCtl").hidden = !(l && l.kind === "image");
  if (l && l.kind === "text" && document.activeElement !== $("#words")) $("#words").value = l.text;
  if (l && l.kind === "text") $("#weight").value = String([400, 500, 600, 700, 800, 900].reduce((a, b) => (Math.abs(b - l.weight) < Math.abs(a - l.weight) ? b : a)));
  if (l && l.kind === "image") {
    const img = l._img, px = img?.naturalWidth || 0;
    $("#imgNote").textContent = l.svg ? "Vector logo (SVG): drawn sharp at any size."
      : px && l.w > px * 1.1 ? `This picture is only ${px} px wide but is shown ${Math.round(l.w)} px wide, so it will look soft. Use a bigger file.`
      : px && Math.abs(l.w / px - 1) <= 0.02 ? `Pixel-perfect: shown at its own size (${px} px).` : "";
    $("#crispBtn").hidden = !!l.svg;
  }
  $$(".slider[data-k]").forEach((el) => el._sync && el._sync());
  [...segs, ...checks, ...colors].forEach((x) => x._sync());
  $("#preset").value = S.preset;
  $("#zoneCustom").hidden = S.preset !== "Custom";
  syncZone();
  $("#bgColorRow").hidden = S.background.mode !== "custom";
  $("#coverTitle").value = S.cover.title;
  $("#titleCtl").hidden = !S.cover.title;
  const ct = $("#coverTime");
  ct.min = R.trimStart; ct.max = Math.max(R.trimStart + 0.01, R.trimEnd); ct.value = R.coverTime;
  // locked: the layout can't change, the words can
  $("#lockedNote").hidden = !R.locked;
  $("#lock").classList.toggle("on", R.locked);
  $("#lockShackle").setAttribute("d", R.locked ? "M8 11V7a4 4 0 0 1 8 0v4" : "M8 11V7a4 4 0 0 1 7.5-2");
  for (const sel of ["#p-frame", "#textCtl .styleCtl", "#imgCtl", "#p-layers .toolbar"]) {
    const el = $(sel);
    el.style.opacity = R.locked ? 0.45 : "";
    el.style.pointerEvents = R.locked ? "none" : "";
  }
  renderList();
  updateTransport();
}

// ---------------------------------------------------------------- layers: add / remove / order
$("#addText").addEventListener("click", () => {
  const t = newText(), z = zoneRect();
  t.w = Math.min(760, z.w - 40);
  moveTo(t, z.x + z.w / 2 - t.w / 2, z.y + 40);
  t.attach_gap = 24;
  S.layers.push(t); R.sel = t._id;
  refresh(); commit();
  $("#words").focus(); $("#words").select();
});
$("#addImage").addEventListener("change", async (e) => {
  const f = e.target.files[0]; e.target.value = "";
  if (!f) return;
  const b64 = await new Promise((res) => { const r = new FileReader(); r.onload = () => res(String(r.result).split(",")[1]); r.readAsDataURL(f); });
  const svg = f.type === "image/svg+xml" || /\.svg$/i.test(f.name);
  const l = { kind: "image", name: f.name, png: b64, svg, w: 240, x: RW / 2, y: RH / 2, opacity: 1, attach_gap: null, _id: nextId++ };
  attachImage(l);
  await new Promise((res) => { if (l._img.complete && l._img.naturalWidth) res(); else { l._img.addEventListener("load", res, { once: true }); l._img.addEventListener("error", res, { once: true }); } });
  if (!l._img.naturalWidth) { status("Couldn't read that picture."); return; }
  const z = zoneRect();
  l.w = svg ? z.w * 0.3 : Math.min(z.w * 0.3, l._img.naturalWidth);
  moveTo(l, z.x + z.w - l.w, z.y);
  S.layers.push(l); R.sel = l._id;
  refresh(); commit();
});
$("#layerDel").addEventListener("click", () => { if (R.locked) return; S.layers = S.layers.filter((l) => l._id !== R.sel); R.sel = null; refresh(); commit(); });
const reorder = (by) => {
  const i = S.layers.findIndex((l) => l._id === R.sel), j = i + by;
  if (i < 0 || j < 0 || j >= S.layers.length || R.locked) return;
  [S.layers[i], S.layers[j]] = [S.layers[j], S.layers[i]];
  refresh(); commit();
};
$("#layerUp").addEventListener("click", () => reorder(1));
$("#layerDown").addEventListener("click", () => reorder(-1));
$("#crispBtn").addEventListener("click", () => {
  const l = selected(); if (!l || !l._img) return;
  const px = l._img.naturalWidth, z = zoneRect();
  const opts = Array.from({ length: 40 }, (_, k) => px / (k + 1)).filter((w) => w <= z.w + 0.01 && w >= 30);
  if (!opts.length) return;
  l.w = opts.reduce((a, b) => (Math.abs(b - l.w) < Math.abs(a - l.w) ? b : a));
  refresh(); commit();
  status(`Now ${Math.round(l.w)} px wide: the sharpest size near what you had.`);
});

// ---------------------------------------------------------------- files in
$("#openVideo").addEventListener("change", (e) => { const f = e.target.files[0]; e.target.value = ""; if (f) openVideo(f); });
document.addEventListener("dragover", (e) => e.preventDefault());
document.addEventListener("drop", (e) => {
  e.preventDefault();
  const f = [...(e.dataTransfer?.files || [])][0];
  if (f && f.type.startsWith("video/")) openVideo(f);
});
$("#play").addEventListener("click", togglePlay);
$("#undo").addEventListener("click", undo);
$("#redo").addEventListener("click", redo);
document.addEventListener("keydown", (e) => {
  const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName || "");
  if (typing) return;
  if (e.code === "Space") { e.preventDefault(); if (!e.repeat) togglePlay(); }
  else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") { e.preventDefault(); e.shiftKey ? redo() : undo(); }
  else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y") { e.preventDefault(); redo(); }
  else if ((e.key === "Delete" || e.key === "Backspace") && R.sel && !R.locked) { $("#layerDel").click(); }
});

// ---------------------------------------------------------------- templates dialog
const tplDialog = $("#tplDialog");
async function renderTemplates() {
  const list = await store.all();
  const ul = $("#tplList");
  ul.innerHTML = list.length ? "" : '<li class="muted">No templates yet. Save one, import a file, or connect GitHub to bring yours over.</li>';
  for (const t of list) {
    const li = document.createElement("li");
    li.innerHTML = `<b></b><button type="button" class="btn">Use</button><button type="button" class="icon danger" title="Delete"><svg viewBox="0 0 24 24"><path d="M4 7h16M6 7l1 13h10l1-13M9 7V4h6v3"/></svg></button>`;
    li.querySelector("b").textContent = t.json.name || t.file.replace(/\.json$/, "");
    const use = () => { useTemplate(t.json); tplDialog.close(); };
    li.querySelector("b").addEventListener("click", use);
    li.querySelector(".btn").addEventListener("click", use);
    li.querySelector(".icon").addEventListener("click", async () => {
      if (!confirm(`Delete the template “${t.json.name || t.file}”${cloud.token() ? " here and in your GitHub cloud" : ""}?`)) return;
      await store.del(t.file);
      if (cloud.token()) await cloud.remove(t.file).catch((e) => status(e.message));
      renderTemplates();
    });
    ul.appendChild(li);
  }
  const on = !!cloud.token();
  $("#cloudSetup").hidden = on; $("#cloudOn").hidden = !on;
  $("#cloudInfo").textContent = on
    ? `Connected${localStorage.getItem("rm.gh.login") ? " as " + localStorage.getItem("rm.gh.login") : ""}. Templates sync with your PC and iPhone through a secret gist.`
    : "Connect the same GitHub account as on your PC to use your templates here.";
}
$("#tokenLink").href = cloud.TOKEN_URL;
$("#tplBtn").addEventListener("click", () => { renderTemplates(); tplDialog.showModal(); });
$("#tplSave").addEventListener("click", async () => {
  const name = prompt("Template name", S.name || $("#tplName").textContent.replace(/^Templates$/, ""));
  if (!name) return;
  const d = templateState(name.trim());
  S.name = d.name;
  await store.put(store.fileName(d.name), JSON.stringify(d, null, 1));
  R.locked = true; $("#tplName").textContent = d.name;
  syncPanel(); renderTemplates();
  status(`Saved “${d.name}”.`);
  if (cloud.token()) cloud.sync().then(status, (e) => status(e.message));
});
$("#tplImport").addEventListener("change", async (e) => {
  const f = e.target.files[0]; e.target.value = "";
  if (!f) return;
  try {
    const j = JSON.parse(await f.text());
    j.name = j.name || f.name.replace(/\.json$/i, "");
    await store.put(store.fileName(j.name), JSON.stringify(j, null, 1));
    renderTemplates(); status(`Added “${j.name}”.`);
  } catch { status("That file isn't a Reel Maker template."); }
});
$("#tplDownload").addEventListener("click", () => {
  const name = S.name || "template";
  saveBlob(new Blob([JSON.stringify(templateState(name), null, 1)], { type: "application/json" }), store.fileName(name));
});
$("#tokenSave").addEventListener("click", async () => {
  const t = $("#tokenInput").value.trim(); if (!t) return;
  cloud.setToken(t);
  try {
    localStorage.setItem("rm.gh.login", await cloud.whoami());
    $("#tokenInput").value = "";
    status(await cloud.sync());
  } catch (e) { cloud.setToken(""); status(e.message); alert(e.message); }
  renderTemplates();
});
$("#cloudSync").addEventListener("click", async () => {
  status("Syncing…");
  try { status(await cloud.sync()); } catch (e) { status(e.message); }
  renderTemplates();
});
$("#cloudOff").addEventListener("click", () => { cloud.setToken(""); localStorage.removeItem("rm.gh.login"); renderTemplates(); });

// ---------------------------------------------------------------- export
function saveBlob(blob, name) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 60000);
}
const exDialog = $("#exportDialog");
let exSignal = null, exResult = null;
async function doExport() {
  if (!R.url) { status("Open a video first."); return; }
  pause();
  exSignal = { cancel: false };
  $("#exTitle").textContent = "Exporting…";
  $("#exRun").hidden = false; $("#exDone").hidden = true;
  $("#exProg").value = 0; $("#exMsg").textContent = "Getting ready…";
  exDialog.showModal();
  const t0 = performance.now();
  try {
    const res = await exportReel({
      url: R.url, file: R.file, S, trimStart: R.trimStart, trimEnd: R.trimEnd, videoRect, overlay,
      cover: S.export.cover_first ? coverCanvas() : null, fps: S.export.fps === 1 ? 60 : 30, quality: S.export.quality,
      signal: exSignal,
      onProgress: (f) => { $("#exProg").value = f; $("#exMsg").textContent = `${Math.round(f * 100)}% · keep this tab open and in front`; },
    });
    const name = `${R.name.replace(/\.[^.]+$/, "") || "reel"}_reel.${res.ext}`;
    exResult = new File([res.blob], name, { type: res.blob.type });
    const url = URL.createObjectURL(res.blob);
    $("#exVideo").src = url;
    $("#exDownload").href = url; $("#exDownload").download = name;
    $("#exTitle").textContent = "Your reel is ready";
    $("#exRun").hidden = true; $("#exDone").hidden = false;
    const canShare = navigator.canShare && navigator.canShare({ files: [exResult] });
    $("#exShare").hidden = !canShare;
    $("#exHint").textContent = (canShare ? "“Save or share…” lets you save it to Photos or send it straight to Instagram. " : "")
      + `${(res.blob.size / 1048576).toFixed(1)} MB${res.ext === "webm" ? " (WebM: this browser can't make MP4s; Chrome, Edge or Safari can)" : ""} · made in ${Math.round((performance.now() - t0) / 1000)} s`;
    status("Reel exported.");
  } catch (e) {
    exDialog.close();
    status(e.message || "The export failed.");
    if (!exSignal.cancel) alert(e.message || "The export failed.");
  }
}
$("#exportBtn").addEventListener("click", doExport);
$("#exportBtn2").addEventListener("click", doExport);
$("#exCancel").addEventListener("click", () => { exSignal.cancel = true; });
$("#exClose").addEventListener("click", () => exDialog.close());
$("#exShare").addEventListener("click", () => { navigator.share({ files: [exResult] }).catch(() => {}); });

// ---------------------------------------------------------------- start
syncPanel();
refresh();
resetHistory();
if ("serviceWorker" in navigator && location.protocol === "https:") navigator.serviceWorker.register("sw.js").catch(() => {});
(async () => {   // pick up where you left off: the last template used
  const last = localStorage.getItem("rm.lastTemplate");
  if (!last) return;
  const t = (await store.all()).find((x) => x.json.name === last);
  if (t) { useTemplate(t.json); resetHistory(); }
})();
