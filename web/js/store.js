// Templates saved in this browser (IndexedDB: room for logos, unlike localStorage).
const DB = "reelmaker", STORE = "templates";

function open() {
  return new Promise((res, rej) => {
    const r = indexedDB.open(DB, 1);
    r.onupgradeneeded = () => r.result.createObjectStore(STORE);
    r.onsuccess = () => res(r.result);
    r.onerror = () => rej(r.error);
  });
}
async function tx(mode, fn) {
  const db = await open();
  return new Promise((res, rej) => {
    const t = db.transaction(STORE, mode);
    const out = fn(t.objectStore(STORE));
    t.oncomplete = () => res(out && "result" in out ? out.result : undefined);
    t.onerror = () => rej(t.error);
  });
}

export const fileName = (name) => (name.replace(/[\\/:*?"<>|]+/g, "_").trim() || "template") + ".json";
export const put = (file, text) => tx("readwrite", (s) => s.put(text, file));
export const del = (file) => tx("readwrite", (s) => s.delete(file));
export const get = (file) => tx("readonly", (s) => s.get(file));
export async function all() {
  const keys = await tx("readonly", (s) => s.getAllKeys());
  const out = [];
  for (const k of keys || []) {
    const text = await get(k);
    try { out.push({ file: k, text, json: JSON.parse(text) }); } catch { /* skip broken */ }
  }
  return out.sort((a, b) => (a.json.name || a.file).localeCompare(b.json.name || b.file));
}
