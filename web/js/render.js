// Drawing for Reel Maker on the web. Same 1080 × 1920 layout and text rules as the Windows app,
// so templates look the same everywhere.
export const RW = 1080, RH = 1920;

export const PRESETS = [
  ["Level 1 — clear of all Instagram UI", [250, 450, 120, 120]],
  ["Level 2 — looser", [160, 340, 60, 60]],
  ["Profile grid crop (3:4)", [240, 240, 0, 0]],
  ["Full frame", [0, 0, 0, 0]],
  ["Custom", null],
];

// Apple devices have Apple's emoji font; elsewhere the bundled emoji pictures are used.
export const APPLE = /iPhone|iPad|iPod|Macintosh/.test(navigator.userAgent);

// ---------------------------------------------------------------- colours
/** "#AARRGGBB" (Qt) or "#RRGGBB" → CSS colour */
export function css(hex, alphaMul = 1) {
  let h = (hex || "#000000").replace("#", "");
  let a = 1;
  if (h.length === 8) { a = parseInt(h.slice(0, 2), 16) / 255; h = h.slice(2); }
  const n = parseInt(h, 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${(a * alphaMul).toFixed(3)})`;
}
export const toInput = (hex) => "#" + (hex || "#000000").replace("#", "").slice(-6);
export const fromInput = (v) => "#FF" + v.replace("#", "").toUpperCase();

// ---------------------------------------------------------------- text
const seg = typeof Intl !== "undefined" && Intl.Segmenter ? new Intl.Segmenter(undefined, { granularity: "grapheme" }) : null;
export const clusters = (t) => (seg ? Array.from(seg.segment(t), (s) => s.segment) : Array.from(t));

export function isEmoji(cl) {
  const cps = Array.from(cl, (c) => c.codePointAt(0));
  const f = cps[0];
  if (f >= 0x1f000 || cps.includes(0xfe0f) || cps.includes(0x20e3)) return true;
  return (f >= 0x2600 && f <= 0x27bf) || (f >= 0x2300 && f <= 0x23ff) || (f >= 0x2b00 && f <= 0x2bff) ||
    [0x3030, 0x303d, 0x3297, 0x3299, 0x2122, 0x2139, 0x24c2, 0x203c, 0x2049].includes(f);
}
export const emojiKey = (cl) => Array.from(cl).map((c) => c.codePointAt(0)).filter((c) => c !== 0xfe0f).map((c) => c.toString(16)).join("-");

const mctx = document.createElement("canvas").getContext("2d");
export const WEIGHTS = [[400, "Regular"], [500, "Medium"], [600, "Semibold"], [700, "Bold"], [800, "Heavy"], [900, "Black"]];
export function fontOf(l, size = l.size) {
  const w = WEIGHTS.map((x) => x[0]).reduce((a, b) => (Math.abs(b - l.weight) < Math.abs(a - l.weight) ? b : a));
  const fam = l.family && l.family !== "Inter Display" ? `"${l.family}", "Inter Display"` : `"Inter Display"`;
  return `${l.italic ? "italic " : ""}${w} ${size}px ${fam}, system-ui, sans-serif`;
}
/** The text's own opacity (words and emoji) is the alpha of its colour, "#AARRGGBB", as in the Windows app. */
export function textAlpha(l) {
  const h = (l.color || "").replace("#", "");
  return h.length === 8 ? parseInt(h.slice(0, 2), 16) / 255 : 1;
}
export function withAlpha(hex, a) {
  const rgb = (hex || "#FFFFFF").replace("#", "").slice(-6).toUpperCase();
  return "#" + Math.round(Math.max(0, Math.min(1, a)) * 255).toString(16).padStart(2, "0").toUpperCase() + rgb;
}
export const innerPad = (l) => (l.style === "box" ? l.pad : l.style === "highlight" ? l.size * 0.32 : 0);

const layoutCache = new Map();
// Canvas text only uses a web font once the browser has loaded it, so load every weight (upright and
// italic) up front, then measure again.
if (document.fonts) {
  Promise.allSettled(WEIGHTS.flatMap(([w]) => ["", "italic "].map((st) => document.fonts.load(`${st}${w} 64px "Inter Display"`))))
    .then(() => { layoutCache.clear(); onAssetLoaded(); });
}
export function layout(l) {
  const key = [l.text, l.family, l.weight, l.italic ? 1 : 0, l.size, l.w, l.style, l.pad, l.spacing].join("|");
  const hit = layoutCache.get(key);
  if (hit) return hit;
  mctx.font = fontOf(l);
  const m = mctx.measureText("Hg");
  const asc = m.fontBoundingBoxAscent ?? l.size * 0.969;
  const desc = m.fontBoundingBoxDescent ?? l.size * 0.242;
  const W = (s) => mctx.measureText(s).width;
  const ew = l.size * 1.12;
  const maxw = Math.max(20, l.w - 2 * innerPad(l));
  const spaceW = W(" ");
  const tokens = [];
  let word = "";
  const flush = () => { if (word) { tokens.push({ t: "word", s: word, w: W(word) }); word = ""; } };
  for (const cl of clusters(l.text || "")) {
    if (cl === "\n" || cl === "\r\n") { flush(); tokens.push({ t: "nl" }); }
    else if (cl === " " || cl === "\t") { flush(); tokens.push({ t: "sp", w: spaceW }); }
    else if (isEmoji(cl)) { flush(); tokens.push({ t: "emoji", s: cl, w: ew }); }
    else word += cl;
  }
  flush();
  const lines = [[]];
  let x = 0;
  const trim = () => { const ln = lines[lines.length - 1]; while (ln.length && ln[ln.length - 1].t === "sp") ln.pop(); };
  const newline = () => { trim(); lines.push([]); x = 0; };
  for (let tk of tokens) {
    if (tk.t === "nl") { newline(); continue; }
    if (tk.t === "sp") { if (x > 0) { lines[lines.length - 1].push(tk); x += tk.w; } continue; }
    if (x > 0 && x + tk.w > maxw) newline();
    if (tk.t === "word" && tk.w > maxw) {           // one very long word: break it
      let chunk = "";
      for (const ch of clusters(tk.s)) {
        if (W(chunk + ch) > maxw && chunk) { lines[lines.length - 1].push({ t: "word", s: chunk, w: W(chunk) }); newline(); chunk = ""; }
        chunk += ch;
      }
      tk = { t: "word", s: chunk, w: W(chunk) };
    }
    lines[lines.length - 1].push(tk);
    x += tk.w;
  }
  trim();
  const res = { lines, widths: lines.map((ln) => ln.reduce((a, t) => a + t.w, 0)), lh: l.size * l.spacing, asc, desc, maxw };
  if (layoutCache.size > 500) layoutCache.clear();
  layoutCache.set(key, res);
  return res;
}

export function heightOf(l) {
  if (l.kind === "image") {
    const img = l._img;
    return img && img.naturalWidth ? (l.w * img.naturalHeight) / img.naturalWidth : l.w;
  }
  const lay = layout(l);
  return lay.lines.length * lay.lh + 2 * (l.style === "box" ? l.pad : 0);
}
export function rectOf(l) {
  const h = heightOf(l);
  return l.kind === "text" ? { x: l.x - l.w / 2, y: l.y, w: l.w, h } : { x: l.x - l.w / 2, y: l.y - h / 2, w: l.w, h };
}
export function moveTo(l, left, top) {
  l.x = left + l.w / 2;
  l.y = l.kind === "text" ? top : top + heightOf(l) / 2;
}

// emoji pictures (non-Apple devices)
let emojiIndex = null;
const emojiImgs = new Map();
export let onAssetLoaded = () => {};
export function setOnAssetLoaded(f) { onAssetLoaded = f; }
fetch("emoji/index.json").then((r) => (r.ok ? r.json() : {})).then((j) => { emojiIndex = j; onAssetLoaded(); }).catch(() => { emojiIndex = {}; });
function emojiImage(cl) {
  if (!emojiIndex) return null;
  const key = emojiKey(cl);
  if (emojiImgs.has(key)) return emojiImgs.get(key);
  let file = emojiIndex[key];
  if (!file) { const parts = key.split("-"); if (parts.length > 1 && !parts.includes("200d")) file = emojiIndex[parts[0]]; }
  if (!file) { emojiImgs.set(key, null); return null; }
  const img = new Image();
  img.onload = () => onAssetLoaded();
  img.src = "emoji/" + file;
  emojiImgs.set(key, img);
  return img;
}

function roundRect(ctx, x, y, w, h, r) {
  r = Math.max(0, Math.min(r, w / 2, h / 2));
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}
export { roundRect };

export function drawText(ctx, l) {
  const lay = layout(l), r = rectOf(l), ip = innerPad(l);
  const top = r.y + (l.style === "box" ? l.pad : 0), left = r.x + ip;
  ctx.save();
  ctx.globalAlpha = l.opacity ?? 1;
  const bc = css(l.box_color, l.box_alpha);
  if (l.style === "box") { ctx.fillStyle = bc; ctx.beginPath(); roundRect(ctx, r.x, r.y, r.w, r.h, l.radius); ctx.fill(); }
  const lineX = (i) => (l.align === "left" ? left : l.align === "right" ? left + lay.maxw - lay.widths[i] : left + (lay.maxw - lay.widths[i]) / 2);
  if (l.style === "highlight") {
    const hp = l.size * 0.32;
    ctx.fillStyle = bc;
    ctx.beginPath();          // one path, non-zero fill: overlapping lines don't double the colour
    lay.lines.forEach((ln, i) => {
      if (!ln.length) return;
      roundRect(ctx, lineX(i) - hp, top + i * lay.lh - lay.lh * 0.02, lay.widths[i] + 2 * hp, lay.lh * 1.04, Math.min(l.radius, lay.lh / 2));
    });
    ctx.fill("nonzero");
  }
  if (!l._editing) {
    ctx.textBaseline = "alphabetic";
    const textH = lay.asc + lay.desc;
    const ta = textAlpha(l);                         // the shadow and emoji fade with the words
    const passes = l.shadow ? [[`rgba(0,0,0,${(0.47 * ta).toFixed(3)})`, l.size * 0.05]] : [];
    passes.push([css(l.color), 0]);
    for (const [color, off] of passes) {
      lay.lines.forEach((ln, i) => {
        let x = lineX(i);
        const lineTop = top + i * lay.lh;
        const base = lineTop + (lay.lh - textH) / 2 + lay.asc;
        for (const t of ln) {
          if (t.t === "word") { ctx.font = fontOf(l); ctx.fillStyle = color; ctx.fillText(t.s, x + off, base + off); }
          else if (t.t === "emoji" && off === 0) {
            const es = l.size * 1.02, ey = lineTop + (lay.lh - es) / 2;
            const img = APPLE ? null : emojiImage(t.s);
            if (img && img.complete && img.naturalWidth) {
              ctx.imageSmoothingQuality = "high";
              ctx.globalAlpha = (l.opacity ?? 1) * ta;
              ctx.drawImage(img, x + (t.w - es) / 2, ey, es, es);
              ctx.globalAlpha = l.opacity ?? 1;
            } else if (APPLE || !img) {
              ctx.font = `${es * 0.84}px "Apple Color Emoji", "Segoe UI Emoji", "Noto Color Emoji", sans-serif`;
              ctx.fillStyle = color; ctx.textAlign = "center"; ctx.textBaseline = "middle";
              ctx.fillText(t.s, x + t.w / 2, lineTop + lay.lh / 2);
              ctx.textAlign = "start"; ctx.textBaseline = "alphabetic";
            }
          }
          x += t.w;
        }
      });
    }
  }
  ctx.restore();
}

/** Pixel for pixel near the picture's own size, otherwise one high-quality resize; whole pixels. */
export function drawImageLayer(ctx, l) {
  const img = l._img;
  if (!img || !img.naturalWidth) return;
  const r = rectOf(l);
  let w = Math.round(r.w), h = Math.round(r.h);
  if (!l.svg) {
    const iw = img.naturalWidth, ih = img.naturalHeight;
    if (Math.abs(w - iw) <= Math.max(1, iw * 0.02) && Math.abs(h - ih) <= Math.max(1, ih * 0.02)) { w = iw; h = ih; }
  }
  ctx.save();
  ctx.globalAlpha = l.opacity ?? 1;
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(img, Math.round(r.x + r.w / 2 - w / 2), Math.round(r.y + r.h / 2 - h / 2), w, h);
  ctx.restore();
}

export function drawLayers(ctx, layers) {
  for (const l of layers) (l.kind === "text" ? drawText : drawImageLayer)(ctx, l);
}

// ---------------------------------------------------------------- background / video
const tiny = document.createElement("canvas");
/** Blurred, dimmed background from a frame: shrink a lot, then stretch (the Windows app's look). */
export function drawBlur(ctx, src, sw, sh) {
  const tw = Math.max(1, Math.round(sw / 24)), th = Math.max(1, Math.round(sh / 24));
  tiny.width = tw; tiny.height = th;
  const t = tiny.getContext("2d");
  t.imageSmoothingQuality = "high";
  t.drawImage(src, 0, 0, tw, th);
  const s = Math.max(RW / sw, RH / sh) * 1.08;
  const w = sw * s, h = sh * s;
  ctx.fillStyle = "#000"; ctx.fillRect(0, 0, RW, RH);
  ctx.imageSmoothingEnabled = true;
  ctx.drawImage(tiny, (RW - w) / 2, (RH - h) / 2, w, h);
  ctx.fillStyle = "rgba(0,0,0,0.353)"; ctx.fillRect(0, 0, RW, RH);
}

export function drawBackground(ctx, S, src, sw, sh) {
  const mode = S.background.mode;
  if (mode === "blur" && src && sw) drawBlur(ctx, src, sw, sh);
  else { ctx.fillStyle = mode === "white" ? "#fff" : mode === "custom" ? css(S.background.color) : "#000"; ctx.fillRect(0, 0, RW, RH); }
}

export function drawVideo(ctx, src, vr, radius) {
  ctx.save();
  if (radius > 0) { ctx.beginPath(); roundRect(ctx, vr.x, vr.y, vr.w, vr.h, radius); ctx.clip(); }
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(src, vr.x, vr.y, vr.w, vr.h);
  ctx.restore();
}
