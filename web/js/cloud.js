// Templates in the same secret GitHub gist the Windows and iPhone apps use.
// Websites can't use GitHub's code sign-in, so the web version uses a personal token with only
// the "gist" permission, kept in this browser.
import * as store from "./store.js";

const API = "https://api.github.com";
const DESC = "Reel Maker templates (managed by the app)";
const INDEX = "_reelmaker_index.json";
export const TOKEN_URL = "https://github.com/settings/tokens/new?scopes=gist&description=Reel%20Maker%20web";

export const token = () => localStorage.getItem("rm.gh.token") || "";
export const setToken = (t) => (t ? localStorage.setItem("rm.gh.token", t.trim()) : localStorage.removeItem("rm.gh.token"));

async function api(method, path, body) {
  const r = await fetch(API + path, {
    method,
    headers: { Authorization: `Bearer ${token()}`, Accept: "application/vnd.github+json", ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  }).catch(() => { throw new Error("Couldn't reach GitHub. Check your connection."); });
  if (r.status === 401) throw new Error("GitHub didn't accept the token. Make a new one (with the gist box ticked) and paste it again.");
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error("GitHub: " + (j.message || r.status));
  return j;
}

export async function whoami() { return (await api("GET", "/user")).login; }

async function gist() {
  let id = localStorage.getItem("rm.gh.gist");
  if (id) { try { return await api("GET", `/gists/${id}`); } catch { id = null; } }
  for (let page = 1; ; page++) {
    const list = await api("GET", `/gists?per_page=100&page=${page}`);
    const g = list.find((g) => g.description === DESC && g.files && g.files[INDEX]);
    if (g) { localStorage.setItem("rm.gh.gist", g.id); return api("GET", `/gists/${g.id}`); }
    if (list.length < 100) break;
  }
  const g = await api("POST", "/gists", { description: DESC, public: false, files: { [INDEX]: { content: '{"templates": {}}' } } });
  localStorage.setItem("rm.gh.gist", g.id);
  return g;
}

async function text(f) {
  if (f.truncated || f.content == null) return (await fetch(f.raw_url)).text();
  return f.content;
}

/** Newer wins on each side. Returns a short summary. */
export async function sync() {
  const g = await gist();
  let idx = {};
  try { idx = JSON.parse(await text(g.files[INDEX])).templates || {}; } catch { /* empty index */ }
  const local = Object.fromEntries((await store.all()).map((t) => [t.file, t]));
  let down = 0, up = 0;
  const uploads = {};
  for (const [name, f] of Object.entries(g.files)) {
    if (name === INDEX || !name.toLowerCase().endsWith(".json")) continue;
    const rs = Number(idx[name] || 0), l = local[name];
    if (!l || rs > Number(l.json.saved_at || 0) + 0.5) { await store.put(name, await text(f)); down++; }
  }
  for (const [name, l] of Object.entries(local)) {
    const ls = Number(l.json.saved_at || 0);
    if (!g.files[name] || ls > Number(idx[name] || 0) + 0.5) { uploads[name] = { content: l.text }; idx[name] = ls; up++; }
  }
  if (up) {
    uploads[INDEX] = { content: JSON.stringify({ templates: idx }, null, 1) };
    await api("PATCH", `/gists/${g.id}`, { files: uploads });
  }
  return `Synced with GitHub: ${down} downloaded, ${up} uploaded.`;
}

export async function remove(file) {
  const g = await gist();
  let idx = {};
  try { idx = JSON.parse(await text(g.files[INDEX])).templates || {}; } catch { /* */ }
  delete idx[file];
  if (g.files[file]) await api("PATCH", `/gists/${g.id}`, { files: { [file]: null, [INDEX]: { content: JSON.stringify({ templates: idx }, null, 1) } } });
}
