"""Keep Reel Maker templates in the user's Google Drive.

Templates live in the Drive *app data folder*: a hidden, private folder only
Reel Maker can see (scope drive.appdata). Sign-in uses Google's desktop flow:
the browser opens, the user approves, and Google redirects back to a tiny
web server on 127.0.0.1 that this module runs for a moment (with PKCE).

The OAuth client ID/secret come from google_client.json, which the GitHub
build writes from repository secrets. Google treats desktop-app secrets as
not confidential, but keeping them out of the public repo avoids noise.
"""

import base64
import hashlib
import http.server
import json
import os
import secrets
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from core import APPDATA, TEMPLATE_DIR, res_path

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
FILES_URL = "https://www.googleapis.com/drive/v3/files"
UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"
SCOPES = "https://www.googleapis.com/auth/drive.appdata openid email"
TOKEN_FILE = os.path.join(APPDATA, "cloud", "google.token")
MANIFEST_FILE = os.path.join(APPDATA, "cloud", "synced.json")


class CloudError(Exception):
    pass


# ---------------------------------------------------------------- secure storage
def _protect(data: bytes) -> bytes:
    """Encrypt with Windows DPAPI (only this Windows user can read it)."""
    if os.name != "nt":
        return b"plain:" + data
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
    src = BLOB(len(data), ctypes.cast(ctypes.create_string_buffer(data, len(data)), ctypes.POINTER(ctypes.c_char)))
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
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
    data = blob[6:]
    src = BLOB(len(data), ctypes.cast(ctypes.create_string_buffer(data, len(data)), ctypes.POINTER(ctypes.c_char)))
    out = BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(src), None, None, None, None, 0,
                                                    ctypes.byref(out)):
        raise CloudError("Saved sign-in is unreadable.")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


# ---------------------------------------------------------------- client config
def load_client():
    """Returns (client_id, client_secret) or None when cloud sync isn't set up in this build."""
    for path in (res_path("google_client.json"), os.path.join(APPDATA, "cloud", "google_client.json")):
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            d = d.get("installed", d)
            if d.get("client_id") and d.get("client_secret"):
                return d["client_id"], d["client_secret"]
        except (OSError, ValueError):
            pass
    return None


def _http(method, url, data=None, headers=None, timeout=30):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, socket.timeout, OSError) as e:
        raise CloudError("Couldn't reach Google. Check your internet connection.") from e


def _form(d):
    return urllib.parse.urlencode(d).encode()


# ---------------------------------------------------------------- Google Drive
class GoogleDrive:
    def __init__(self):
        self.client = load_client()
        self.refresh_token = None
        self.email = None
        self._access = None
        self._expires = 0
        self._load()

    # ---- account
    @property
    def available(self):
        return self.client is not None

    @property
    def signed_in(self):
        return bool(self.refresh_token)

    def _load(self):
        try:
            with open(TOKEN_FILE, "rb") as f:
                d = json.loads(_unprotect(f.read()).decode())
            self.refresh_token, self.email = d.get("refresh_token"), d.get("email")
        except (OSError, ValueError, CloudError):
            self.refresh_token = self.email = None

    def _save(self):
        os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
        with open(TOKEN_FILE, "wb") as f:
            f.write(_protect(json.dumps({"refresh_token": self.refresh_token, "email": self.email}).encode()))

    def sign_in(self, open_browser, timeout=300):
        """Blocking: opens the browser and waits for Google to send the user back."""
        if not self.client:
            raise CloudError("Cloud sync isn't set up in this version of Reel Maker.")
        cid, csecret = self.client
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        state = secrets.token_urlsafe(16)
        result = {}

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                if q.get("state", [""])[0] != state:
                    self.send_response(400)
                    self.end_headers()
                    return
                result["code"] = q.get("code", [None])[0]
                result["error"] = q.get("error", [None])[0]
                ok = bool(result["code"])
                body = (("<h2>You're signed in to Reel Maker.</h2><p>You can close this tab and go back to the app.</p>"
                         if ok else "<h2>Sign-in was cancelled.</h2><p>You can close this tab.</p>"))
                page = ("<!doctype html><meta charset=utf-8><title>Reel Maker</title><body style=\"font-family:"
                        "system-ui,sans-serif;background:#0d0e10;color:#ececef;display:grid;place-items:center;"
                        f"height:90vh;text-align:center\"><div>{body}</div>").encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(page)

            def log_message(self, *a):
                pass

        srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        redirect = f"http://127.0.0.1:{srv.server_port}"
        url = AUTH_URL + "?" + urllib.parse.urlencode({
            "client_id": cid, "redirect_uri": redirect, "response_type": "code", "scope": SCOPES,
            "code_challenge": challenge, "code_challenge_method": "S256", "state": state,
            "access_type": "offline", "prompt": "consent select_account"})
        srv.timeout = 1
        open_browser(url)
        end = time.time() + timeout
        try:
            while "code" not in result and time.time() < end:
                srv.handle_request()
        finally:
            srv.server_close()
        if not result.get("code"):
            raise CloudError("Sign-in was cancelled." if result.get("error") or "code" in result
                             else "Sign-in timed out. Please try again.")
        st, body = _http("POST", TOKEN_URL, _form({
            "client_id": cid, "client_secret": csecret, "code": result["code"], "code_verifier": verifier,
            "grant_type": "authorization_code", "redirect_uri": redirect}),
            {"Content-Type": "application/x-www-form-urlencoded"})
        tok = json.loads(body or b"{}")
        if st != 200 or "refresh_token" not in tok:
            raise CloudError("Google didn't accept the sign-in: " + tok.get("error_description", tok.get("error", str(st))))
        self.refresh_token = tok["refresh_token"]
        self._access, self._expires = tok["access_token"], time.time() + tok.get("expires_in", 3600) - 60
        self.email = _email_from_id_token(tok.get("id_token", ""))
        self._save()
        return self.email

    def sign_out(self):
        if self.refresh_token:
            try:
                _http("POST", REVOKE_URL, _form({"token": self.refresh_token}),
                      {"Content-Type": "application/x-www-form-urlencoded"}, timeout=10)
            except CloudError:
                pass
        self.refresh_token = self.email = self._access = None
        for p in (TOKEN_FILE, MANIFEST_FILE):
            try:
                os.remove(p)
            except OSError:
                pass

    def _token(self):
        if self._access and time.time() < self._expires:
            return self._access
        if not self.refresh_token:
            raise CloudError("Not signed in.")
        cid, csecret = self.client
        st, body = _http("POST", TOKEN_URL, _form({
            "client_id": cid, "client_secret": csecret, "refresh_token": self.refresh_token,
            "grant_type": "refresh_token"}), {"Content-Type": "application/x-www-form-urlencoded"})
        tok = json.loads(body or b"{}")
        if st != 200:
            if tok.get("error") == "invalid_grant":
                self.refresh_token = None
                try:
                    os.remove(TOKEN_FILE)
                except OSError:
                    pass
                raise CloudError("Your Google sign-in expired. Please sign in again.")
            raise CloudError("Google refused the request: " + tok.get("error_description", str(st)))
        self._access, self._expires = tok["access_token"], time.time() + tok.get("expires_in", 3600) - 60
        return self._access

    def _api(self, method, url, data=None, headers=None):
        h = {"Authorization": f"Bearer {self._token()}"}
        h.update(headers or {})
        st, body = _http(method, url, data, h)
        if st >= 400:
            try:
                msg = json.loads(body)["error"]["message"]
            except Exception:
                msg = f"HTTP {st}"
            raise CloudError(f"Google Drive: {msg}")
        return body

    # ---- files (in the hidden app folder)
    def list(self):
        files, page = [], None
        while True:
            q = {"spaces": "appDataFolder", "pageSize": 200,
                 "fields": "nextPageToken,files(id,name,modifiedTime,appProperties)"}
            if page:
                q["pageToken"] = page
            d = json.loads(self._api("GET", FILES_URL + "?" + urllib.parse.urlencode(q)))
            files += d.get("files", [])
            page = d.get("nextPageToken")
            if not page:
                return files

    def download(self, fid):
        return self._api("GET", f"{FILES_URL}/{fid}?alt=media")

    def upload(self, name, data: bytes, fid=None, props=None):
        meta = {"name": name, "mimeType": "application/json"}
        if props:
            meta["appProperties"] = props
        if not fid:
            meta["parents"] = ["appDataFolder"]
        boundary = "reelmaker" + secrets.token_hex(8)
        body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(meta)}\r\n"
                f"--{boundary}\r\nContent-Type: application/json\r\n\r\n").encode() + data + f"\r\n--{boundary}--".encode()
        url = (f"{UPLOAD_URL}/{fid}" if fid else UPLOAD_URL) + "?uploadType=multipart&fields=id,modifiedTime"
        d = json.loads(self._api("PATCH" if fid else "POST", url, body,
                                 {"Content-Type": f"multipart/related; boundary={boundary}"}))
        return d["id"]

    def delete(self, fid):
        self._api("DELETE", f"{FILES_URL}/{fid}")


def _email_from_id_token(tok):
    try:
        payload = tok.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload)).get("email")
    except Exception:
        return None


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


def sync_templates(drive, folder=TEMPLATE_DIR):
    """Two-way sync of *.json templates between `folder` and Drive.
    Newest saved_at wins; a template deleted on one side is deleted on the other.
    Returns a short summary dict."""
    os.makedirs(folder, exist_ok=True)
    manifest = _load_manifest()          # {filename: {"id":..., "stamp":...}} as of the last sync
    remote = {f["name"]: f for f in drive.list() if f["name"].lower().endswith(".json")}
    local = {n: os.path.join(folder, n) for n in os.listdir(folder) if n.lower().endswith(".json")}
    up = down = removed = 0
    new_manifest = {}

    for name in sorted(set(remote) | set(local) | set(manifest)):
        r, lp, m = remote.get(name), local.get(name), manifest.get(name)
        if r and lp:
            ls = _stamp(lp)
            rs = float((r.get("appProperties") or {}).get("saved_at") or 0)
            if ls > rs + 0.5:
                with open(lp, "rb") as f:
                    fid = drive.upload(name, f.read(), r["id"], {"saved_at": str(ls)})
                new_manifest[name] = {"id": fid, "stamp": ls}
                up += 1
            elif rs > ls + 0.5:
                with open(lp, "wb") as f:
                    f.write(drive.download(r["id"]))
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
                    fid = drive.upload(name, f.read(), None, {"saved_at": str(ls)})
                new_manifest[name] = {"id": fid, "stamp": ls}
                up += 1
        elif r and not lp:
            if m:                        # was synced before, now gone locally: deleted here
                drive.delete(r["id"])
                removed += 1
            else:
                rs = float((r.get("appProperties") or {}).get("saved_at") or 0)
                with open(os.path.join(folder, name), "wb") as f:
                    f.write(drive.download(r["id"]))
                new_manifest[name] = {"id": r["id"], "stamp": rs}
                down += 1
    _save_manifest(new_manifest)
    return {"uploaded": up, "downloaded": down, "removed": removed, "total": len(new_manifest)}
