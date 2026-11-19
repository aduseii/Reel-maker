"""Export a reel with no window: the same engine, templates and "High" quality as the app.

Made so another tool (or an AI assistant) can turn a clip into a finished reel in one command:

    python app/headless_export.py --template "News" --video clip.mp4 --caption "Your headline" --out reel.mp4
    python app/headless_export.py --template "News" --x-url https://x.com/user/status/123 --out reel.mp4

Templates are looked up by name in ./templates (this repo), then in the app's own template folder
(%LOCALAPPDATA%\\ReelMaker\\templates); a path to a .json template file works too.
Run with --help for every option. Nothing in the app's saved settings is changed.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")    # no window, works on servers too
APP_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_TEMPLATES = os.path.join(os.path.dirname(APP_DIR), "templates")
sys.path.insert(0, APP_DIR)

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtGui import QImage, QFont  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import reel_maker as rm  # noqa: E402
from core import TEMPLATE_DIR, find_ffmpeg, W, H, DEFAULT_FONT  # noqa: E402
import x_import  # noqa: E402


def say(msg):
    print(msg, flush=True)


class Fail(Exception):
    pass


# ---------------------------------------------------------------- quiet, self-contained window
class _NoPlayer:
    """Stands in for the live video player: frames come from FFmpeg instead (the app's own fallback)."""
    def __getattr__(self, name):
        return lambda *a, **k: 0


def _isolate_settings():
    """Use a throwaway settings file so the app's real settings (last template, folders) aren't touched."""
    ini = os.path.join(tempfile.mkdtemp(prefix="reelmaker_headless_"), "settings.ini")
    rm.QSettings = lambda *a, **k: QSettings(ini, QSettings.IniFormat)


def _silence_window():
    rm.ReelMaker.check_updates = lambda self, *a, **k: None
    rm.ReelMaker.cloud_sync = lambda self, *a, **k: None
    rm.ReelMaker.restore_last_template = lambda self, *a, **k: None

    def box(*a, **k):
        text = next((x for x in a if isinstance(x, str) and len(x) > 20), "")
        if text:
            say("Note: " + text.replace("\n", " "))
        return QMessageBox.No
    for name in ("warning", "information", "critical", "question"):
        setattr(rm.QMessageBox, name, staticmethod(box))


# ---------------------------------------------------------------- templates
def template_files():
    out = {}
    for folder in (TEMPLATE_DIR, REPO_TEMPLATES):          # repo copies win over same-named local ones
        if os.path.isdir(folder):
            for f in sorted(os.listdir(folder)):
                if f.lower().endswith(".json"):
                    path = os.path.join(folder, f)
                    try:
                        with open(path, encoding="utf-8") as fh:
                            name = json.load(fh).get("name") or f[:-5]
                    except Exception:
                        continue
                    out[name] = path
    return out


def find_template(name):
    if os.path.isfile(name):
        return name
    files = template_files()
    key = name.strip().lower()
    for n, p in files.items():
        if n.lower() == key:
            return p
    matches = [p for n, p in files.items() if key in n.lower()]
    if len(matches) == 1:
        return matches[0]
    raise Fail(f"No template called “{name}”. Templates found: " + (", ".join(files) or "none") +
               ". Put template .json files in the repo's templates folder.")


# ---------------------------------------------------------------- automatic cover
def _gray(img, size=(192, 108)):
    """A small grayscale copy as rows of 0–255 values."""
    from PySide6.QtCore import Qt
    small = img.scaled(size[0], size[1], Qt.IgnoreAspectRatio, Qt.SmoothTransformation).convertToFormat(
        QImage.Format_Grayscale8)
    w, h, bpl = small.width(), small.height(), small.bytesPerLine()
    data = bytes(small.constBits())
    return [data[y * bpl:y * bpl + w] for y in range(h)], w, h


def best_window(img):
    """Where the 9:16 cover window should sit (0–1 across) and how good the frame is there.
    Looks for the most detailed part of the picture (faces and people are detailed, plain walls aren't),
    and checks that it's sharp and well exposed."""
    rows, w, h = _gray(img)
    col = [0.0] * w
    total = 0.0
    lum = 0
    for y in range(1, h - 1):
        r, up, dn = rows[y], rows[y - 1], rows[y + 1]
        for x in range(1, w - 1):
            g = abs(r[x + 1] - r[x - 1]) + abs(dn[x] - up[x])
            col[x] += g
            total += g
        lum += sum(r)
    win = max(2, min(w, round(w * (img.height() * 9 / 16) / img.width())))
    best, best_x = -1.0, 0
    s = sum(col[:win])
    for x in range(0, w - win + 1):
        if x:
            s += col[x + win - 1] - col[x - 1]
        # a slight pull toward the middle so a busy edge doesn't win over people in the centre
        centre = 1 - 0.25 * abs((x + win / 2) / w - 0.5) * 2
        if s * centre > best:
            best, best_x = s * centre, x
    cx = (best_x + win / 2) / w
    mean = lum / max(1, (h - 2) * w)
    exposure = 1 - min(1.0, abs(mean - 120) / 120)            # too dark or blown out scores lower
    sharp = total / max(1, (h - 2) * (w - 2))
    return cx, sharp * (0.4 + 0.6 * exposure)


def cover_candidates(w, n=12):
    """(time, frame) pairs spread over the trimmed clip, skipping the very start and end (fades, cuts)."""
    a, b = w.abs_start(), w.abs_end()
    pad = min(0.6, (b - a) * 0.1)
    a, b = a + pad, b - pad
    if b <= a:
        a = b = (w.abs_start() + w.abs_end()) / 2
    out = []
    for i in range(n):
        t = a + (b - a) * (i + 0.5) / n
        img = w.fb_frame_at(t)
        if img is not None:
            out.append((t, img))
    return out


def pick_cover(w, a):
    cands = cover_candidates(w)
    if not cands:
        return
    scored = []
    for t, img in cands:
        cx, score = best_window(img)
        scored.append((score, t, img, cx))
    scored.sort(key=lambda s: s[0], reverse=True)
    score, t, img, cx = scored[0]
    w.cover_frame = img
    w.cover_frame_t = t
    w.cover_cx, w.cover_cy = cx, 0.5
    say(f"Cover: picked the frame at {t - w.abs_start():.1f} s (sharpest, best lit, framed on the most detail)")


def cover_sheet(w, path, n=12):
    """Save the candidate covers side by side with their times, to choose one by eye."""
    from PySide6.QtCore import Qt, QRectF
    from PySide6.QtGui import QPainter, QColor
    cands = cover_candidates(w, n)
    cw, ch, cols = 270, 480, 6
    rows_n = (len(cands) + cols - 1) // cols
    sheet = QImage(cols * cw, rows_n * (ch + 34), QImage.Format_RGB32)
    sheet.fill(QColor("#111111"))
    p = QPainter(sheet)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    f = QFont(DEFAULT_FONT)
    f.setPixelSize(22)
    p.setFont(f)
    keep = (w.cover_cx, w.cover_cy)
    for i, (t, img) in enumerate(cands):
        cx, _ = best_window(img)
        w.cover_cx, w.cover_cy = cx, 0.5
        r = w.cover_crop(img)
        x, y = (i % cols) * cw, (i // cols) * (ch + 34)
        p.drawImage(QRectF(x + 4, y + 4, cw - 8, ch - 8), img, r)
        p.setPen(QColor("#FFFFFF"))
        p.drawText(QRectF(x, y + ch, cw, 30), Qt.AlignCenter, f"{t - w.abs_start():.1f} s  ·  x {cx:.2f}")
    p.end()
    w.cover_cx, w.cover_cy = keep
    sheet.save(path)
    say(f"Cover choices: {path}")


# ---------------------------------------------------------------- the export
def get_from_x(url):
    state = {}
    say("Getting the post from X…")
    post = x_import.get_post(url, state)
    say(f"Downloading the video from @{post.get('uploader_id') or 'unknown'}…")
    path = x_import.download_video(post, 0, state)
    return path, post.get("caption") or ""


def export(a):
    _isolate_settings()
    _silence_window()
    app = QApplication.instance() or QApplication(sys.argv[:1])
    rm.load_bundled_fonts()
    f = QFont(DEFAULT_FONT)
    f.setPixelSize(13)
    app.setFont(f)
    w = rm.ReelMaker()
    w.player = _NoPlayer()
    w.fb_timer.timeout.disconnect()
    w.load_timer.timeout.disconnect()

    if a.template:
        path = find_template(a.template)
        if not w.apply_template_file(path, quiet=True):
            raise Fail(f"Couldn't open the template {path}.")
        say(f"Template: {w.template_name}")

    caption = a.caption
    if a.x_url:
        video, x_caption = get_from_x(a.x_url)
        if caption is None:
            caption = x_caption
    else:
        video = os.path.abspath(a.video)
        if not os.path.isfile(video):
            raise Fail(f"Can't find the video {video}.")

    w.load_video(video)
    w.start_fallback()
    for _ in range(50):
        app.processEvents()
        if w.frame is not None:
            break
        time.sleep(0.05)
    if w.frame is None:
        raise Fail("The video couldn't be read. Try an MP4 or MOV.")
    say(f"Video: {os.path.basename(video)} ({w.frame.width()} × {w.frame.height()}, {w.duration:.1f} s)")

    if caption:
        w.fill_caption(caption.strip())
        say("Caption: " + caption.strip().replace("\n", " / "))

    # the caption sits on the video (like the app's "Sit on video" button), whatever the template says
    if a.sit_gap >= 0:
        for o in rm.caption_boxes(w.layers):
            o.attach_gap = float(a.sit_gap)
            w.sit_on_video(o, o.attach_gap)

    if a.start is not None:
        w.t_start.setValue(max(0.0, a.start))
    if a.end is not None:
        w.t_end.setValue(min(w.duration, a.end))
    if w.abs_end() - w.abs_start() < 0.2:
        raise Fail("The trim leaves less than 0.2 s of video.")

    if a.cover_image:
        img = QImage(a.cover_image)
        if img.isNull():
            raise Fail(f"Couldn't open the cover image {a.cover_image}.")
        w.cover_image = img
        w.cover_src_seg.blockSignals(True)
        w.cover_src_seg.setValue(1)
        w.cover_src_seg.blockSignals(False)
        w.cover_cx = w.cover_cy = 0.5
    elif a.cover_time is not None:
        img = w.fb_frame_at(w.abs_start() + max(0.0, a.cover_time))
        if img is not None:
            w.cover_frame = img
        w.cover_cx = a.cover_x if a.cover_x is not None else best_window(img)[0] if img is not None else 0.5
        say(f"Cover: frame at {a.cover_time:.1f} s")
    else:
        pick_cover(w, a)
    if a.cover_x is not None:
        w.cover_cx = min(1.0, max(0.0, a.cover_x))
    if a.cover_sheet:
        cover_sheet(w, a.cover_sheet)
    if a.cover_title is not None:
        w.title.setText(a.cover_title)
    if a.no_cover:
        w.cover_first.setChecked(False)
        w.cover_embed.setChecked(False)

    w.quality.setValue({"high": 0, "standard": 1, "small": 2}[a.quality])
    if a.fps:
        w.fps.setValue({"30": 0, "60": 1, "source": 2}[a.fps])

    out = os.path.abspath(a.out or os.path.splitext(video)[0] + "_reel.mp4")
    if os.path.abspath(out) == os.path.abspath(video):
        raise Fail("Pick a different output name so the original video isn't overwritten.")
    os.makedirs(os.path.dirname(out), exist_ok=True)

    if a.preview:
        img = QImage(W, H, QImage.Format_ARGB32_Premultiplied)
        p = rm.QPainter(img)
        w.compose(p, w.frame)
        p.end()
        img.save(a.preview)
        say(f"Preview frame: {a.preview}")
    if a.save_cover:
        cpath = os.path.splitext(out)[0] + "_cover.png"
        w.render_cover().save(cpath, "PNG")
        say(f"Cover: {cpath}")

    ff = find_ffmpeg()
    if not ff:
        raise Fail("FFmpeg isn't installed. Run: pip install imageio-ffmpeg")
    args, total = w.build_ffmpeg_args(out)
    say(f"Exporting {os.path.basename(out)} ({total:.1f} s)…")
    proc = subprocess.Popen([ff] + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    last = -10
    for line in proc.stdout:
        m = re.match(r"out_time_us=(\d+)", line.strip())
        if m and total > 0:
            pct = min(100, int(int(m.group(1)) / 1e6 / total * 100))
            if pct >= last + 10:
                say(f"  {pct}%")
                last = pct
    err = proc.stderr.read()
    if proc.wait() != 0 or not os.path.isfile(out):
        raise Fail("FFmpeg couldn't export the reel:\n" + err[-1500:])
    say(f"Done: {out} ({os.path.getsize(out) / 1048576:.1f} MB)")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Export an Instagram reel with Reel Maker, no window needed.")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--video", help="the video file to turn into a reel")
    src.add_argument("--x-url", help="a link to an X post: downloads its video and uses its text as the caption")
    ap.add_argument("--template", help="template name (from ./templates or the app) or a template .json file")
    ap.add_argument("--caption", help="words for the caption box (overrides the X post's text)")
    ap.add_argument("--out", help="where to save the MP4 (default: next to the video, *_reel.mp4)")
    ap.add_argument("--start", type=float, help="trim: start, in seconds")
    ap.add_argument("--end", type=float, help="trim: end, in seconds")
    ap.add_argument("--cover-time", type=float, help="cover: the video frame this many seconds after the start")
    ap.add_argument("--cover-image", help="cover: an image file instead of a video frame")
    ap.add_argument("--cover-x", type=float,
                    help="cover: where the 9:16 window sits across the frame, 0 (left) to 1 (right)")
    ap.add_argument("--cover-sheet", help="save the candidate cover frames side by side as a PNG, to pick by eye")
    ap.add_argument("--cover-title", help="cover: title text (empty string removes the template's title)")
    ap.add_argument("--no-cover", action="store_true", help="don't put a cover frame at the start")
    ap.add_argument("--save-cover", action="store_true", help="also save the cover as a PNG next to the reel")
    ap.add_argument("--sit-gap", type=float, default=16,
                    help="the caption sits this many px above the video (default 16, the app's default); "
                         "-1 keeps the template's own placement")
    ap.add_argument("--quality", choices=["high", "standard", "small"], default="high")
    ap.add_argument("--fps", choices=["30", "60", "source"], help="frame rate (default: the template's)")
    ap.add_argument("--preview", help="also save a still of the first frame with the layout, as a PNG")
    ap.add_argument("--list-templates", action="store_true", help="list the templates it can find, then stop")
    a = ap.parse_args(argv)
    if a.list_templates:
        for n, p in template_files().items():
            say(f"{n}  ({p})")
        return 0
    if not (a.video or a.x_url):
        ap.error("give --video or --x-url")
    try:
        export(a)
    except (Fail, x_import.ImportError_) as e:
        say(f"Error: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
