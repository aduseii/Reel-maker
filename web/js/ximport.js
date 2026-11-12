// Import a video and its text from an X (Twitter) post link.
// X's own post lookup only answers X's embed widget, so websites ask FxTwitter (or vxTwitter),
// free public services that read the post and allow websites to use the answer. The video file
// itself comes straight from X's video server, which does allow websites.
const LINK = /https?:\/\/(?:www\.|mobile\.|m\.)?(?:x|twitter|fxtwitter|vxtwitter|fixupx|fixvx)\.com\/(?:[A-Za-z0-9_]{1,30}|i(?:\/web)?)\/status(?:es)?\/(\d{5,25})(?:\/(?:video|photo)\/(\d))?/i;

export function findPost(text) {
  const m = LINK.exec(text || "");
  return m ? { id: m[1], index: m[2] ? Number(m[2]) : null } : null;
}

export function cleanCaption(s) {
  const t = document.createElement("textarea");
  t.innerHTML = s || "";                          // decode &amp; and friends
  let x = t.value.replace(/\r\n/g, "\n").replace(/\s*https?:\/\/t\.co\/\w+/g, "").trim();
  x = x.replace(/^(?:@\w{1,15}\s+)+(?=\S)/, "");  // "@a @b actual text" (a reply)
  x = x.split("\n").map((l) => l.replace(/\s+$/, "")).join("\n").replace(/[ \t]{2,}/g, " ").replace(/\n{3,}/g, "\n\n");
  return x.trim();
}

class XError extends Error {}

async function lookup(id) {
  const tries = [
    async () => {
      const r = await fetch(`https://api.fxtwitter.com/i/status/${id}`);
      const j = await r.json().catch(() => ({}));
      if (j.code === 404 || r.status === 404) throw new XError("That post isn't available. It may be deleted or from a protected account.");
      const t = j.tweet;
      if (!t) throw new Error("no answer");
      const videos = ((t.media && t.media.videos) || []).map((v) => v.url).filter(Boolean);
      return { text: t.text || "", user: (t.author && t.author.screen_name) || "post", videos };
    },
    async () => {
      const r = await fetch(`https://api.vxtwitter.com/i/status/${id}`);
      const j = await r.json();
      const videos = (j.media_extended || []).filter((m) => m.type === "video" || m.type === "gif").map((m) => m.url);
      return { text: j.text || "", user: j.user_screen_name || "post", videos };
    },
  ];
  let last;
  for (const t of tries) {
    try { return await t(); } catch (e) { if (e instanceof XError) throw e; last = e; }
  }
  throw new XError("Couldn't look up that post right now. Check your connection and try again in a minute." + (last ? "" : ""));
}

/** Returns { caption, user, id, videos: [url] }. */
export async function getPost(link) {
  const p = findPost(link);
  if (!p) throw new XError("That doesn't look like a link to an X post.");
  const info = await lookup(p.id);
  if (!info.videos.length) throw new XError("That post doesn't have a video.");
  return { id: p.id, index: p.index, user: info.user, caption: cleanCaption(info.text), videos: info.videos };
}

/** Download one video as a File, reporting progress 0..1. */
export async function download(url, name, onProgress) {
  const r = await fetch(url).catch(() => { throw new XError("Couldn't download the video. Check your connection."); });
  if (!r.ok) throw new XError("X didn't send the video (" + r.status + ").");
  const total = Number(r.headers.get("content-length")) || 0;
  const reader = r.body.getReader();
  const parts = [];
  let got = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    parts.push(value); got += value.length;
    if (total) onProgress(got / total);
  }
  return new File(parts, name + ".mp4", { type: "video/mp4" });
}
