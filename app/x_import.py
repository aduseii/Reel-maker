"""Import a video and its post text from an X (Twitter) link.

Downloading uses yt-dlp. A copy ships with the app, and because X changes its
site often the app keeps a newer copy in %LOCALAPPDATA%\\ReelMaker\\ytdlp,
checked against PyPI at most once a day (and again whenever a download fails).
"""

import glob
import hashlib
import html
import json
import os
import re
import shutil
import sys
import time
import urllib.request
import zipfile

from core import APPDATA, __version__, find_ffmpeg, version_tuple

YTDLP_DIR = os.path.join(APPDATA, "ytdlp")
POINTER = os.path.join(YTDLP_DIR, "current.json")
PYPI_URL = "https://pypi.org/pypi/yt-dlp/json"
CHECK_EVERY = 24 * 3600

URL_RE = re.compile(
    r"https?://(?:www\.|mobile\.|m\.)?(?:x|twitter|fxtwitter|vxtwitter|fixupx|fixvx|twittpr)\.com/"
    r"(?:[A-Za-z0-9_]{1,30}|i(?:/web)?)/status(?:es)?/(\d{5,25})(?:/(?:video|photo)/(\d))?", re.I)


class ImportError_(Exception):
    """An error with a message that is fine to show the user."""


class Cancelled(Exception):
    pass


# ---------------------------------------------------------------- links
def find_link(text):
    """The first X/Twitter post link in text, normalised to https://x.com/i/status/<id>, or None."""
    m = URL_RE.search(text or "")
    if not m:
        return None
    url = f"https://x.com/i/status/{m.group(1)}"
    if m.group(2):
        url += f"/video/{m.group(2)}"
    return url


# ---------------------------------------------------------------- caption
TCO = re.compile(r"\s*https?://t\.co/\w+")


def clean_caption(text):
    """Post text ready for a text box: no t.co links, no leading @replies, tidy spacing."""
    t = html.unescape(text or "").replace("\r\n", "\n")
    t = TCO.sub("", t)
    t = re.sub(r"^(?:@\w{1,15}\s+)+(?=\S)", "", t.strip())   # "@a @b actual text" (a reply)
    t = "\n".join(line.rstrip() for line in t.split("\n"))
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


# ---------------------------------------------------------------- yt-dlp copies
def _read_version(folder):
    try:
        with open(os.path.join(folder, "yt_dlp", "version.py"), encoding="utf-8") as f:
            m = re.search(r"__version__\s*=\s*['\"]([^'\"]+)", f.read())
        return m.group(1) if m else None
    except OSError:
        return None


def _bundled_folder():
    for p in sys.path:
        if p and os.path.isfile(os.path.join(p, "yt_dlp", "version.py")) and not p.startswith(YTDLP_DIR):
            return p
    return None


def _downloaded():
    try:
        with open(POINTER, encoding="utf-8") as f:
            d = json.load(f)
        if _read_version(d["path"]) == d["version"]:
            return d
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def active_copy():
    """(version, folder) of the yt-dlp copy to use: the newer of the bundled and the downloaded one."""
    best = None
    b = _bundled_folder()
    if b:
        best = (_read_version(b), b)
    d = _downloaded()
    if d and (not best or version_tuple(d["version"]) > version_tuple(best[0])):
        best = (d["version"], d["path"])
    return best


def _forget_loaded():
    for name in list(sys.modules):
        if name == "yt_dlp" or name.startswith("yt_dlp."):
            del sys.modules[name]


def load_ytdlp():
    """Import the newest available yt-dlp copy (re-importing if a newer one arrived)."""
    copy = active_copy()
    if not copy:
        raise ImportError_("The downloader is missing. Reinstall Reel Maker or check your internet "
                           "connection so it can be downloaded.")
    version, folder = copy
    mod = sys.modules.get("yt_dlp")
    if mod and os.path.dirname(os.path.dirname(os.path.abspath(mod.__file__))) == os.path.abspath(folder):
        return mod
    _forget_loaded()
    for p in list(sys.path):
        if p.startswith(YTDLP_DIR):
            sys.path.remove(p)
    if folder.startswith(YTDLP_DIR):
        sys.path.insert(0, folder)
    import yt_dlp
    return yt_dlp


def update_ytdlp(force=False, timeout=20):
    """Fetch a newer yt-dlp from PyPI if there is one. Returns the new version, or None.
    Without force this checks at most once a day."""
    os.makedirs(YTDLP_DIR, exist_ok=True)
    stamp = os.path.join(YTDLP_DIR, "last_check")
    if not force:
        try:
            if time.time() - os.path.getmtime(stamp) < CHECK_EVERY:
                return None
        except OSError:
            pass
    req = urllib.request.Request(PYPI_URL, headers={"User-Agent": f"ReelMaker/{__version__}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        meta = json.loads(r.read().decode("utf-8"))
    with open(stamp, "w") as f:
        f.write(str(time.time()))
    latest = meta["info"]["version"]
    current = active_copy()
    if current and version_tuple(latest) <= version_tuple(current[0]):
        return None
    wheel = next((u for u in meta.get("urls", []) if u.get("packagetype") == "bdist_wheel"
                  and u["filename"].endswith("-py3-none-any.whl")), None)
    if not wheel:
        return None
    tmp = os.path.join(YTDLP_DIR, "download.whl")
    h = hashlib.sha256()
    req = urllib.request.Request(wheel["url"], headers={"User-Agent": f"ReelMaker/{__version__}"})
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
            h.update(chunk)
    if h.hexdigest() != wheel["digests"]["sha256"]:
        os.remove(tmp)
        raise RuntimeError("The downloader update was damaged.")
    dest = os.path.join(YTDLP_DIR, latest)
    part = dest + ".part"
    shutil.rmtree(part, ignore_errors=True)
    with zipfile.ZipFile(tmp) as z:
        for n in z.namelist():
            if n.startswith("yt_dlp/") and not n.endswith("/"):
                z.extract(n, part)
    os.remove(tmp)
    shutil.rmtree(dest, ignore_errors=True)
    os.replace(part, dest)
    with open(POINTER + ".part", "w", encoding="utf-8") as f:
        json.dump({"version": latest, "path": dest}, f)
    os.replace(POINTER + ".part", POINTER)
    # keep the new copy and the one before it (it may still be loaded)
    keep = {os.path.abspath(dest)}
    mod = sys.modules.get("yt_dlp")
    if mod:
        keep.add(os.path.dirname(os.path.dirname(os.path.abspath(mod.__file__))))
    for d in glob.glob(os.path.join(YTDLP_DIR, "*")):
        if os.path.isdir(d) and os.path.abspath(d) not in keep:
            shutil.rmtree(d, ignore_errors=True)
    return latest


# ---------------------------------------------------------------- download
class _Log:
    def __init__(self):
        self.lines = []

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        self.lines.append(msg)

    def error(self, msg):
        self.lines.append(msg)


def save_folder():
    home = os.path.expanduser("~")
    videos = os.path.join(home, "Videos")
    return os.path.join(videos if os.path.isdir(videos) else home, "Reel Maker", "From X")


def friendly(err):
    """Turn a yt-dlp error into something a person can act on."""
    s = re.sub(r"^(ERROR:\s*)?(\[\w+\]\s*)?(\d+:\s*)?", "", str(err)).strip()
    low = s.lower()
    if "no video could be found" in low or "no video formats" in low or "there's no video" in low:
        return "That post doesn't have a video."
    if any(k in low for k in ("login", "log in", "sign in", "authentication", "nsfw", "age-restricted",
                              "sensitive", "protected")):
        return ("X only shows this post to signed-in people (it may be marked sensitive or the account is "
                "protected), so Reel Maker can't download it.")
    if any(k in low for k in ("does not exist", "not found", "no status found", "404", "deleted", "suspended", "unavailable")):
        return "That post isn't available. It may have been deleted, or the account is private or suspended."
    if any(k in low for k in ("urlopen error", "getaddrinfo", "timed out", "connection", "network",
                              "temporary failure", "ssl")):
        return "Couldn't reach X. Check your internet connection and try again."
    if "rate" in low and "limit" in low:
        return "X is limiting downloads right now. Wait a few minutes and try again."
    return s[:400] or "The download failed."


def _opts(state, log, folder):
    def hook(d):
        if state.get("cancel"):
            raise Cancelled()
        if d.get("status") == "downloading":
            state["stage"] = "download"
            state["done"] = int(d.get("downloaded_bytes") or 0)
            state["total"] = int(d.get("total_bytes") or d.get("total_bytes_estimate") or 0)
        elif d.get("status") == "finished":
            state["stage"] = "finishing"

    o = {
        "quiet": True, "no_warnings": True, "noprogress": True, "logger": log,
        "noplaylist": False, "ignoreerrors": False, "socket_timeout": 30, "retries": 3,
        # an H.264 MP4 plays everywhere; fall back to the best video + audio merged into MP4
        "format": "best[ext=mp4][vcodec^=?avc]/best[ext=mp4]/bestvideo*+bestaudio/best",
        "merge_output_format": "mp4",
        "outtmpl": os.path.join(folder, "%(uploader_id|post)s_%(id)s.%(ext)s"),
        "restrictfilenames": False, "windowsfilenames": True, "overwrites": True,
        "progress_hooks": [hook], "postprocessor_hooks": [hook],
    }
    ff = find_ffmpeg()
    if ff:
        o["ffmpeg_location"] = ff
    return o


def _videos(info):
    if info.get("_type") in ("playlist", "multi_video"):
        return [e for e in (info.get("entries") or []) if e]
    return [info]


def get_post(url, state):
    """Look up the post. Returns {'videos': [...], 'caption', 'uploader', 'uploader_id', 'id'}.
    Runs in a background thread; updates state['stage']."""
    tried_update = False
    state["stage"] = "updater"
    try:
        update_ytdlp()
    except Exception:
        pass                                 # offline PyPI isn't a reason to stop; the bundled copy may work
    while True:
        yt_dlp = load_ytdlp()
        log = _Log()
        state["stage"] = "lookup"
        try:
            with yt_dlp.YoutubeDL(_opts(state, log, save_folder())) as ydl:
                info = ydl.extract_info(url, download=False)
            break
        except Cancelled:
            raise
        except Exception as e:  # noqa
            # X changes often: a fresh yt-dlp usually fixes "it stopped working"
            if not tried_update:
                tried_update = True
                state["stage"] = "updater"
                try:
                    if update_ytdlp(force=True):
                        continue
                except Exception:
                    pass
            raise ImportError_(friendly(e)) from e
    vids = _videos(info)
    if not vids:
        raise ImportError_("That post doesn't have a video.")
    first = vids[0]
    text = info.get("description") or first.get("description") or ""
    return {"info": info, "videos": vids, "caption": clean_caption(text),
            "uploader": first.get("uploader") or info.get("uploader") or "",
            "uploader_id": first.get("uploader_id") or info.get("uploader_id") or "",
            "id": info.get("id") or first.get("id") or "", "version": active_copy()[0]}


def download_video(post, index, state):
    """Download post['videos'][index]. Returns the saved file's path."""
    yt_dlp = load_ytdlp()
    folder = save_folder()
    os.makedirs(folder, exist_ok=True)
    entry = dict(post["videos"][index])
    if len(post["videos"]) > 1:
        entry["id"] = f"{post['id']}_{index + 1}"
    log = _Log()
    state["stage"] = "download"
    try:
        with yt_dlp.YoutubeDL(_opts(state, log, folder)) as ydl:
            res = ydl.process_ie_result(entry, download=True)
    except Cancelled:
        raise
    except Exception as e:  # noqa
        raise ImportError_(friendly(e)) from e
    path = (traverse(res, "requested_downloads", 0, "filepath") or res.get("filepath")
            or res.get("_filename"))
    if not path or not os.path.isfile(path):
        raise ImportError_("The video didn't download. " + (log.lines[-1] if log.lines else ""))
    return path


def traverse(obj, *keys):
    for k in keys:
        try:
            obj = obj[k]
        except (KeyError, IndexError, TypeError):
            return None
    return obj
