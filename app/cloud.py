"""Keep Reel Maker templates on the user's GitHub account.

Templates are stored as files in one *secret gist* ("Reel Maker templates")
on the user's account: free, unlisted and not shown on their profile.
Sign-in uses GitHub's device flow: the app shows a short code, the user
enters it at github.com/login/device, and the app receives a token limited
to the `gist` scope. No client secret is needed, so the OAuth app's client
ID can live in the code. The token is kept encrypted with Windows DPAPI.
"""

import json
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

from core import APPDATA, TEMPLATE_DIR, __version__

# Public OAuth App client ID (device flow enabled). Not a secret.
GITHUB_CLIENT_ID = "Ov23li12tITbgPr8zlzd"

DEVICE_URL = "https://github.com/login/device/code"
TOKEN_URL = "https://github.com/login/oauth/access_token"
API = "https://api.github.com"
GIST_DESCRIPTION = "Reel Maker templates (managed by the app)"
INDEX = "_reelmaker_index.json"
TOKEN_FILE = os.path.join(APPDATA, "cloud", "github.token")
MANIFEST_FILE = os.path.join(APPDATA, "cloud", "synced.json")


class CloudError(Exception):
    pass


# ---------------------------------------------------------------- secure storage
def _blob_type():
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
    return ctypes, BLOB


def _protect(data: bytes) -> bytes:
    """Encrypt with Windows DPAPI (only this Windows user can read it)."""
    if os.name != "nt":
        return b"plain:" + data
    ctypes, BLOB = _blob_type()
    buf = ctypes.create_string_buffer(data, len(data))
    src = BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    out = BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(src), "ReelMaker", None, None, None, 0,
                                                  ctypes.byref(out)):
        raise CloudError("Couldn't secure the sign-in on this PC.")
    try:
        return b"dpapi:" + ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def _unprotect(blob: bytes) -> bytes:
    if blob.startswith(b"plain:"):
        return blob[6:]
    if not blob.startswith(b"dpapi:") or os.name != "nt":
        raise CloudError("Saved sign-in is unreadable.")
    ctypes, BLOB = _blob_type()
    data = blob[6:]
    buf = ctypes.create_string_buffer(data, len(data))
    src = BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    out = BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(src), None, None, None, None, 0,
                                                    ctypes.byref(out)):
        raise CloudError("Saved sign-in is unreadable.")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


# ---------------------------------------------------------------- http
def _http(method, url, data=None, headers=None, timeout=30):
    h = {"User-Agent": f"ReelMaker/{__version__}", "Accept": "application/json"}
    h.update(headers or {})
    if isinstance(data, (dict, list)):
        data = json.dumps(data).encode()
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, socket.timeout, OSError) as e:
        raise CloudError("Couldn't reach GitHub. Check your internet connection.") from e


# ---------------------------------------------------------------- GitHub gist storage
class GitHubCloud:
    name = "GitHub"

    def __init__(self, client_id=None):
        self.client_id = client_id if client_id is not None else GITHUB_CLIENT_ID
        self.token = None
        self.login = None
        self.gist_id = None
        self._load()

    @property
    def available(self):
        return bool(self.client_id)

    @property
    def signed_in(self):
        return bool(self.token)

    @property
    def account(self):
        return self.login

    def _load(self):
        try:
            with open(TOKEN_FILE, "rb") as f:
                d = json.loads(_unprotect(f.read()).decode())
            self.token, self.login, self.gist_id = d.get("token"), d.get("login"), d.get("gist_id")
        except (OSError, ValueError, CloudError):
            self.token = self.login = self.gist_id = None

    def _save(self):
        os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
        with open(TOKEN_FILE, "wb") as f:
            f.write(_protect(json.dumps({"token": self.token, "login": self.login,
                                         "gist_id": self.gist_id}).encode()))

    # ---- sign-in (device flow)
    def start_sign_in(self):
        """Step 1. Returns {"user_code", "verification_uri", "device_code", "interval", "expires_in"}."""
        if not self.client_id:
            raise CloudError("Cloud sync isn't set up in this version of Reel Maker.")
        st, body = _http("POST", DEVICE_URL, urllib.parse.urlencode(
            {"client_id": self.client_id, "scope": "gist"}).encode(),
            {"Content-Type": "application/x-www-form-urlencoded"})
        d = json.loads(body or b"{}")
        if st != 200 or "device_code" not in d:
            raise CloudError("GitHub didn't start the sign-in: " + d.get("error_description", d.get("error", str(st))))
        return d

    def finish_sign_in(self, start, cancelled=lambda: False):
        """Step 2 (blocking). Polls until the user approves, denies or the code expires."""
        interval = int(start.get("interval", 5))
        end = time.time() + int(start.get("expires_in", 900))
        while time.time() < end:
            for _ in range(interval * 10):
                if cancelled():
                    raise CloudError("Sign-in was cancelled.")
                time.sleep(0.1)
            st, body = _http("POST", TOKEN_URL, urllib.parse.urlencode({
                "client_id": self.client_id, "device_code": start["device_code"],
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code"}).encode(),
                {"Content-Type": "application/x-www-form-urlencoded"})
            d = json.loads(body or b"{}")
            if d.get("access_token"):
                self.token = d["access_token"]
                break
            err = d.get("error")
            if err == "authorization_pending":
                continue
            if err == "slow_down":
                interval = int(d.get("interval", interval + 5))
                continue
            if err == "access_denied":
                raise CloudError("Sign-in was cancelled on GitHub.")
            if err == "expired_token":
                raise CloudError("The code expired. Please try again.")
            raise CloudError("GitHub refused the sign-in: " + d.get("error_description", err or str(st)))
        else:
            raise CloudError("The code expired. Please try again.")
        me = json.loads(self._api("GET", f"{API}/user"))
        self.login = me.get("login")
        self.gist_id = None
        self._save()
        return self.login

    def sign_out(self):
        self.token = self.login = self.gist_id = None
        for p in (TOKEN_FILE, MANIFEST_FILE):
            try:
                os.remove(p)
            except OSError:
                pass

    def _api(self, method, url, data=None):
        if not self.token:
            raise CloudError("Not signed in.")
        st, body = _http(method, url, data, {"Authorization": f"Bearer {self.token}",
                                             "Accept": "application/vnd.github+json",
                                             "X-GitHub-Api-Version": "2022-11-28"})
        if st == 401:
            self.sign_out()
            raise CloudError("Your GitHub sign-in is no longer valid. Please sign in again.")
        if st >= 400:
            try:
                msg = json.loads(body).get("message")
            except Exception:
                msg = None
            raise CloudError(f"GitHub: {msg or f'HTTP {st}'}")
        return body

    # ---- the templates gist
    def _gist(self):
        """The gist holding templates (found or created). Returns its JSON."""
        if self.gist_id:
            try:
                return json.loads(self._api("GET", f"{API}/gists/{self.gist_id}"))
            except CloudError:
                self.gist_id = None
        page = 1
        while True:
            gists = json.loads(self._api("GET", f"{API}/gists?per_page=100&page={page}"))
            for g in gists:
                if g.get("description") == GIST_DESCRIPTION and INDEX in g.get("files", {}):
                    self.gist_id = g["id"]
                    self._save()
                    return json.loads(self._api("GET", f"{API}/gists/{self.gist_id}"))
            if len(gists) < 100:
                break
            page += 1
        g = json.loads(self._api("POST", f"{API}/gists", {
            "description": GIST_DESCRIPTION, "public": False,
            "files": {INDEX: {"content": json.dumps({"templates": {}}, indent=1)}}}))
        self.gist_id = g["id"]
        self._save()
        return g

    def _file_text(self, f):
        if f.get("truncated") or f.get("content") is None:
            st, body = _http("GET", f["raw_url"], headers={"Authorization": f"Bearer {self.token}"})
            if st != 200:
                raise CloudError(f"GitHub: couldn't download {f.get('filename')}")
            return body.decode("utf-8")
        return f["content"]

    def _index(self, g):
        f = g["files"].get(INDEX)
        try:
            return json.loads(self._file_text(f)).get("templates", {}) if f else {}
        except ValueError:
            return {}

    # ---- the interface sync_templates uses
    def list(self):
        g = self._gist()
        self._cache = g
        idx = self._index(g)
        return [{"id": name, "name": name, "appProperties": {"saved_at": str(idx.get(name, 0))}}
                for name in g["files"] if name != INDEX]

    def download(self, fid):
        g = getattr(self, "_cache", None) or self._gist()
        f = g["files"].get(fid)
        if not f:
            raise CloudError(f"{fid} is missing from the cloud.")
        return self._file_text(f).encode("utf-8")

    def _patch(self, files, index_change):
        g = getattr(self, "_cache", None) or self._gist()
        idx = self._index(g)
        for k, v in index_change.items():
            if v is None:
                idx.pop(k, None)
            else:
                idx[k] = v
        files = dict(files)
        files[INDEX] = {"content": json.dumps({"templates": idx}, indent=1)}
        self._cache = json.loads(self._api("PATCH", f"{API}/gists/{self.gist_id}", {"files": files}))

    def upload(self, name, data: bytes, fid=None, props=None):
        stamp = float((props or {}).get("saved_at") or time.time())
        self._patch({name: {"content": data.decode("utf-8")}}, {name: stamp})
        return name

    def delete(self, fid):
        self._patch({fid: None}, {fid: None})


# ---------------------------------------------------------------- template sync
def _load_manifest():
    try:
        with open(MANIFEST_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_manifest(m):
    os.makedirs(os.path.dirname(MANIFEST_FILE), exist_ok=True)
    with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(m, f)


def _stamp(path):
    """A template's own 'saved_at' time (falls back to the file time)."""
    try:
        with open(path, encoding="utf-8") as f:
            return float(json.load(f).get("saved_at") or os.path.getmtime(path))
    except (OSError, ValueError):
        return 0.0


def sync_templates(store, folder=TEMPLATE_DIR):
    """Two-way sync of *.json templates between `folder` and the cloud store.
    Newest saved_at wins; a template deleted on one side is deleted on the other."""
    os.makedirs(folder, exist_ok=True)
    manifest = _load_manifest()          # {filename: {...}} as of the last sync
    remote = {f["name"]: f for f in store.list() if f["name"].lower().endswith(".json")}
    local = {n: os.path.join(folder, n) for n in os.listdir(folder) if n.lower().endswith(".json")}
    up = down = removed = 0
    new_manifest = {}

    def rstamp(r):
        return float((r.get("appProperties") or {}).get("saved_at") or 0)

    for name in sorted(set(remote) | set(local) | set(manifest)):
        r, lp, m = remote.get(name), local.get(name), manifest.get(name)
        if r and lp:
            ls, rs = _stamp(lp), rstamp(r)
            if ls > rs + 0.5:
                with open(lp, "rb") as f:
                    fid = store.upload(name, f.read(), r["id"], {"saved_at": str(ls)})
                new_manifest[name] = {"id": fid, "stamp": ls}
                up += 1
            elif rs > ls + 0.5:
                with open(lp, "wb") as f:
                    f.write(store.download(r["id"]))
                new_manifest[name] = {"id": r["id"], "stamp": rs}
                down += 1
            else:
                new_manifest[name] = {"id": r["id"], "stamp": ls}
        elif lp and not r:
            if m:                        # was synced before, now gone from the cloud: deleted elsewhere
                os.remove(lp)
                removed += 1
            else:
                ls = _stamp(lp)
                with open(lp, "rb") as f:
                    fid = store.upload(name, f.read(), None, {"saved_at": str(ls)})
                new_manifest[name] = {"id": fid, "stamp": ls}
                up += 1
        elif r and not lp:
            if m:                        # was synced before, now gone locally: deleted here
                store.delete(r["id"])
                removed += 1
            else:
                with open(os.path.join(folder, name), "wb") as f:
                    f.write(store.download(r["id"]))
                new_manifest[name] = {"id": r["id"], "stamp": rstamp(r)}
                down += 1
    _save_manifest(new_manifest)
    return {"uploaded": up, "downloaded": down, "removed": removed, "total": len(new_manifest)}
