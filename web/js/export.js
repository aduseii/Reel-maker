// Export a 1080 × 1920 MP4 in the browser.
// Best path: WebCodecs (H.264 + AAC, set bitrate) into an MP4 file. Browsers without it record the
// canvas with MediaRecorder instead. Both play the clip once in real time to read its frames.
import { Muxer, ArrayBufferTarget } from "../vendor/mp4-muxer.mjs";
import { RW, RH, drawBackground, drawVideo } from "./render.js";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function makeVideo(url) {
  const v = document.createElement("video");
  v.playsInline = true; v.preload = "auto"; v.src = url; v.crossOrigin = "anonymous";
  // kept on screen (tiny, nearly invisible): browsers stop handing out frames of off-screen videos
  v.style.cssText = "position:fixed;left:0;bottom:0;width:16px;height:9px;opacity:0.01;pointer-events:none;z-index:-1";
  document.body.appendChild(v);
  return v;
}
const once = (el, ev) => new Promise((res, rej) => {
  el.addEventListener(ev, res, { once: true });
  el.addEventListener("error", () => rej(new Error("The video couldn't be read.")), { once: true });
});
async function seekTo(v, t) { v.currentTime = t; await once(v, "seeked"); }

export async function canWebCodecs() {
  if (!("VideoEncoder" in window && "AudioEncoder" in window && "VideoFrame" in window && "requestVideoFrameCallback" in HTMLVideoElement.prototype)) return null;
  for (const codec of ["avc1.640033", "avc1.640032", "avc1.4d0033", "avc1.42e033"]) {
    try {
      const s = await VideoEncoder.isConfigSupported({ codec, width: RW, height: RH, bitrate: 12e6, framerate: 30 });
      if (s.supported) return codec;
    } catch { /* try next */ }
  }
  return null;
}

/**
 * o: { url, file, S, trimStart, trimEnd, videoRect(ar), overlay (canvas), cover (canvas|null),
 *      fps: 30|60|"source", quality: 0|1|2, onProgress(f), signal: {cancel} }
 * Returns { blob, ext }.
 */
export async function exportReel(o) {
  const codec = await canWebCodecs();
  let audioBuf = null;
  try {
    const ac = new (window.AudioContext || window.webkitAudioContext)();
    audioBuf = await ac.decodeAudioData(await o.file.arrayBuffer());
    ac.close();
  } catch { audioBuf = null; }            // no sound track (or unreadable): export without sound
  let audioOK = !audioBuf;
  if (codec && audioBuf) {
    try {
      const s = await AudioEncoder.isConfigSupported({ codec: "mp4a.40.2", sampleRate: audioBuf.sampleRate, numberOfChannels: Math.min(2, audioBuf.numberOfChannels), bitrate: 192000 });
      audioOK = s.supported;
    } catch { audioOK = false; }
  }
  if (codec && audioOK) return webCodecsExport(o, codec, audioBuf);
  return recorderExport(o);
}

function composer(o, v) {
  const canvas = document.createElement("canvas");
  canvas.width = RW; canvas.height = RH;
  const ctx = canvas.getContext("2d", { alpha: false });
  const vr = o.videoRect(v.videoWidth / v.videoHeight);
  const draw = () => {
    drawBackground(ctx, o.S, v, v.videoWidth, v.videoHeight);
    drawVideo(ctx, v, vr, o.S.video.radius);
    ctx.drawImage(o.overlay, 0, 0);
  };
  return { canvas, ctx, draw };
}

async function webCodecsExport(o, codec, audioBuf) {
  const v = makeVideo(o.url);
  v.muted = true;
  try {
    await once(v, "loadeddata");
    const srcFps = 30;
    const fps = o.fps === 60 ? 60 : o.fps === "source" ? srcFps : 30;
    const fd = 1 / fps;
    const bitrate = [16e6, 10e6, 5e6][o.quality] || 16e6;
    const target = new ArrayBufferTarget();
    const channels = audioBuf ? Math.min(2, audioBuf.numberOfChannels) : 0;
    const muxer = new Muxer({
      target, fastStart: "in-memory", firstTimestampBehavior: "cross-track-offset",
      video: { codec: "avc", width: RW, height: RH, frameRate: fps },
      ...(audioBuf ? { audio: { codec: "aac", numberOfChannels: channels, sampleRate: audioBuf.sampleRate } } : {}),
    });
    let failed = null;
    const venc = new VideoEncoder({ output: (c, m) => muxer.addVideoChunk(c, m), error: (e) => { failed = e; } });
    venc.configure({ codec, width: RW, height: RH, bitrate, framerate: fps, latencyMode: "quality", avc: { format: "avc" } });

    const offset = o.cover ? fd : 0;       // the cover is the first frame; everything else starts one frame later
    const dur = Math.max(0.1, o.trimEnd - o.trimStart);

    // sound: the trimmed part, one frame late when the cover leads
    if (audioBuf) {
      const aenc = new AudioEncoder({ output: (c, m) => muxer.addAudioChunk(c, m), error: (e) => { failed = e; } });
      aenc.configure({ codec: "mp4a.40.2", sampleRate: audioBuf.sampleRate, numberOfChannels: channels, bitrate: 192000 });
      const sr = audioBuf.sampleRate;
      const a0 = Math.floor(o.trimStart * sr), a1 = Math.min(audioBuf.length, Math.ceil(o.trimEnd * sr));
      const chans = Array.from({ length: channels }, (_, i) => audioBuf.getChannelData(i));
      for (let i = a0; i < a1; i += 4096) {
        const n = Math.min(4096, a1 - i);
        const data = new Float32Array(n * channels);
        chans.forEach((ch, c) => data.set(ch.subarray(i, i + n), c * n));
        const ad = new AudioData({ format: "f32-planar", sampleRate: sr, numberOfFrames: n, numberOfChannels: channels,
                                   timestamp: Math.round((offset + (i - a0) / sr) * 1e6), data });
        aenc.encode(ad); ad.close();
      }
      await aenc.flush();
      aenc.close();
    }

    const { canvas, draw } = composer(o, v);
    let n = 0;
    const encode = (ts) => {
      const f = new VideoFrame(canvas, { timestamp: Math.round(ts * 1e6), duration: Math.round(fd * 1e6) });
      venc.encode(f, { keyFrame: n % (fps * 2) === 0 });
      f.close();
      n++;
    };
    if (o.cover) {
      canvas.getContext("2d").drawImage(o.cover, 0, 0, RW, RH);
      encode(0);
    }
    await seekTo(v, o.trimStart);
    draw();
    encode(offset);
    let last = o.trimStart;
    await new Promise((resolve, reject) => {
      const stop = () => { v.pause(); resolve(); };
      const onFrame = (_now, meta) => {
        if (o.signal.cancel) { v.pause(); reject(new Error("Export cancelled.")); return; }
        if (failed) { v.pause(); reject(failed); return; }
        const t = meta.mediaTime;
        if (t >= o.trimEnd - 0.001) { stop(); return; }
        if (t - last >= fd * 0.9 && venc.encodeQueueSize < 24) {
          draw();
          encode(offset + (t - o.trimStart));
          last = t;
        }
        o.onProgress(Math.min(0.99, (t - o.trimStart) / dur));
        v.requestVideoFrameCallback(onFrame);
      };
      v.requestVideoFrameCallback(onFrame);
      v.addEventListener("ended", stop, { once: true });
      v.play().catch(reject);
    });
    await venc.flush();
    venc.close();
    if (failed) throw failed;
    muxer.finalize();
    return { blob: new Blob([target.buffer], { type: "video/mp4" }), ext: "mp4" };
  } finally {
    v.remove();
  }
}

async function recorderExport(o) {
  if (!("MediaRecorder" in window) || !HTMLCanvasElement.prototype.captureStream) {
    throw new Error("This browser can't make videos. Use Chrome, Edge or Safari.");
  }
  // H.264 MP4 first: it's what Instagram expects
  const types = ["video/mp4;codecs=avc1.640028,mp4a.40.2", "video/mp4;codecs=avc1.42E01E,mp4a.40.2", "video/mp4;codecs=avc1,mp4a.40.2",
                 "video/mp4;codecs=avc1", "video/mp4", "video/webm;codecs=vp9,opus", "video/webm"];
  const mime = types.find((t) => MediaRecorder.isTypeSupported(t)) || "";
  const v = makeVideo(o.url);
  try {
    await once(v, "loadeddata");
    await seekTo(v, o.trimStart);
    const fps = o.fps === 60 ? 60 : 30;
    const { canvas, ctx, draw } = composer(o, v);
    const stream = canvas.captureStream(fps);
    const ac = new (window.AudioContext || window.webkitAudioContext)();
    const dest = ac.createMediaStreamDestination();
    ac.createMediaElementSource(v).connect(dest);
    dest.stream.getAudioTracks().forEach((t) => stream.addTrack(t));
    const rec = new MediaRecorder(stream, { mimeType: mime || undefined, videoBitsPerSecond: [14e6, 9e6, 4e6][o.quality] || 14e6 });
    const chunks = [];
    rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    const done = new Promise((r) => (rec.onstop = r));
    if (o.cover) ctx.drawImage(o.cover, 0, 0, RW, RH); else draw();
    rec.start(250);
    await sleep(o.cover ? 120 : 30);
    const dur = Math.max(0.1, o.trimEnd - o.trimStart);
    await new Promise((resolve, reject) => {
      const loop = () => {
        if (o.signal.cancel) { v.pause(); reject(new Error("Export cancelled.")); return; }
        if (v.currentTime >= o.trimEnd - 0.02 || v.ended) { v.pause(); resolve(); return; }
        draw();
        o.onProgress(Math.min(0.99, (v.currentTime - o.trimStart) / dur));
        if (v.requestVideoFrameCallback) v.requestVideoFrameCallback(loop); else requestAnimationFrame(loop);
      };
      v.play().then(loop, reject);
    }).finally(() => { if (rec.state !== "inactive") rec.stop(); });
    await done;
    ac.close();
    const type = rec.mimeType || mime || "video/webm";
    return { blob: new Blob(chunks, { type }), ext: type.includes("mp4") ? "mp4" : "webm" };
  } finally {
    v.remove();
  }
}
