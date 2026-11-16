// Templates in the same secret GitHub gist the Windows and iPhone apps use.
// Websites can't use GitHub's code sign-in, so the web version uses a personal token with only
// the "gist" permission, kept in this browser.
import * as store from "./store.js";

const API = "https://api.github.com";
const DESC = "Reel Maker templates (managed by the app)";
const INDEX = "_reelmaker_index.json";
export const TOKEN_URL = "https://github.com/settings/tokens/new?scopes=gist&description=Reel%20Maker%20web";

export const token = () => localStorage.getItem("rm.gh.token") || "";
export function setToken(t) {
  // a new connection (maybe another account) starts fresh: nothing here counts as synced yet
  localStorage.removeItem("rm.gh.synced"); localStorage.removeItem("rm.gh.gist");
  if (t) localStorage.setItem("rm.gh.token", t.trim()); else localStorage.removeItem("rm.gh.token");
}

async function api(method, path, body) {
  const r = await fetch(API + path, {
    method,
    cache: "no-store",       // GitHub lets browsers reuse answers for 60 s: always ask for the latest
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
  if (f.truncated || f.content == null) return (await fetch(f.raw_url, { cache: "no-store" })).text();
  return f.content;
}

/** Newer wins on each side, and a template renamed or deleted on one side goes on the other.
 *  Returns { message, downloaded: [file names that came down], removed: [file names removed here] }.
 *  One sync at a time: one asked for while another runs starts when that one ends. */
let chain = Promise.resolve();
export function sync() {
  const run = chain.then(syncOnce, syncOnce);
  chain = run.catch(() => {});
  return run;
}
// the template files that were both here and in the cloud after the last sync: one of them missing
// from one side now means it was renamed or deleted there
const SYNCED = "rm.gh.synced";
function synced() { try { return new Set(JSON.parse(localStorage.getItem(SYNCED) || "[]")); } catch { return new Set(); } }
async function syncOnce() {
  const g = await gist();
  let idx = {};
  try { idx = JSON.parse(await text(g.files[INDEX])).templates || {}; } catch { /* empty index */ }
  const local = Object.fromEntries((await store.all()).map((t) => [t.file, t]));
  const was = synced();
  const remote = Object.keys(g.files).filter((n) => n !== INDEX && n.toLowerCase().endsWith(".json"));
  let down = 0, up = 0;
  const changes = {}, downloaded = [], removed = [], now = new Set();
  for (const name of remote) {
    const rs = Number(idx[name] || 0), l = local[name];
    if (!l && was.has(name)) { changes[name] = null; delete idx[name]; continue; }   // deleted here
    if (!l || rs > Number(l.json.saved_at || 0) + 0.5) { await store.put(name, await text(g.files[name])); down++; downloaded.push(name); }
    now.add(name);
  }
  for (const [name, l] of Object.entries(local)) {
    if (!g.files[name] && was.has(name)) { await store.del(name); removed.push(name); continue; }  // gone elsewhere
    const ls = Number(l.json.saved_at || 0);
    if (!g.files[name] || ls > Number(idx[name] || 0) + 0.5) { changes[name] = { content: l.text }; idx[name] = ls; up++; }
    now.add(name);
  }
  if (Object.keys(changes).length) {
    changes[INDEX] = { content: JSON.stringify({ templates: idx }, null, 1) };
    await api("PATCH", `/gists/${g.id}`, { files: changes });
  }
  localStorage.setItem(SYNCED, JSON.stringify([...now]));
  const gone = removed.length ? `, ${removed.length} removed` : "";
  return { message: `Synced with GitHub: ${down} downloaded, ${up} uploaded${gone}.`, downloaded, removed };
}

export async function remove(file) {
  const g = await gist();
  let idx = {};
  try { idx = JSON.parse(await text(g.files[INDEX])).templates || {}; } catch { /* */ }
  delete idx[file];
  if (g.files[file]) await api("PATCH", `/gists/${g.id}`, { files: { [file]: null, [INDEX]: { content: JSON.stringify({ templates: idx }, null, 1) } } });
}
