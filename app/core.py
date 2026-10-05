"""Reel Maker engine: encoder lookup, emoji, text layout and layers."""

__version__ = "1.1.0"

import os
import re
import sys
import tempfile

import base64
import json

from PySide6.QtCore import Qt, QUrl, QRectF, QPointF, QTimer, QProcess, Signal, QSettings, QByteArray, QBuffer, QIODevice
from PySide6.QtGui import (QImage, QPainter, QColor, QPen, QFont, QPainterPath,
                           QPixmap, QKeySequence, QShortcut, QFontMetricsF, QFontDatabase)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QGridLayout,
    QFormLayout, QGroupBox, QPushButton, QRadioButton, QButtonGroup, QComboBox,
    QSpinBox, QDoubleSpinBox, QSlider, QCheckBox, QLabel, QListWidget,
    QListWidgetItem, QFileDialog, QColorDialog, QLineEdit, QProgressBar,
    QScrollArea, QMessageBox, QSizePolicy, QFrame, QToolButton, QPlainTextEdit,
    QFontComboBox, QStackedWidget)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoSink

# The Windows installer fetches FFmpeg (the video encoder) from the official
# imageio-ffmpeg package. If that didn't happen, the app downloads it once.
FFMPEG_WHEEL = ("https://files.pythonhosted.org/packages/2c/c6/fa760e12a2483469e2bf5058c5faff664acf66cadb4df2ad6205b016a73d/"
                "imageio_ffmpeg-0.6.0-py3-none-win_amd64.whl")
FFMPEG_SHA256 = "02fa47c83703c37df6bfe4896aab339013f62bf02c5ebf2dce6da56af04ffc0a"
APPDATA = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "ReelMaker")
LOCAL_FFMPEG = os.path.join(APPDATA, "ffmpeg", "ffmpeg.exe")


def find_ffmpeg():
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.isfile(exe):
            return exe
    except Exception:
        pass
    if os.path.isfile(LOCAL_FFMPEG):
        return LOCAL_FFMPEG
    import shutil
    return shutil.which("ffmpeg")


def download_ffmpeg(state):
    """Runs in a background thread. Updates state['done'], state['total'], state['error']."""
    import hashlib
    import urllib.request
    import zipfile
    try:
        os.makedirs(os.path.dirname(LOCAL_FFMPEG), exist_ok=True)
        tmp = LOCAL_FFMPEG + ".download"
        h = hashlib.sha256()
        with urllib.request.urlopen(FFMPEG_WHEEL, timeout=60) as r, open(tmp, "wb") as f:
            state["total"] = int(r.headers.get("Content-Length") or 0)
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
                state["done"] += len(chunk)
        if h.hexdigest() != FFMPEG_SHA256:
            raise RuntimeError("The download was damaged. Please try again.")
        with zipfile.ZipFile(tmp) as z:
            name = next(n for n in z.namelist() if n.startswith("imageio_ffmpeg/binaries/") and n.endswith(".exe"))
            with z.open(name) as src, open(LOCAL_FFMPEG + ".part", "wb") as dst:
                dst.write(src.read())
        os.replace(LOCAL_FFMPEG + ".part", LOCAL_FFMPEG)
        os.remove(tmp)
    except Exception as e:  # noqa
        state["error"] = str(e) or e.__class__.__name__
    finally:
        state["finished"] = True

W, H = 1080, 1920
ACCENT = QColor("#F2B31B")
TEMPLATE_DIR = os.path.join(APPDATA, "templates")
DEFAULT_FONT = "Inter Display"
EMOJI_FONTS = ["Segoe UI Emoji", "Apple Color Emoji", "Noto Color Emoji"]

# Safe zones in pixels on a 1080x1920 frame: (top, bottom, left, right)
PRESETS = {
    "Level 1 — clear of all Instagram UI": (250, 450, 120, 120),
    "Level 2 — looser": (160, 340, 60, 60),
    "Profile grid crop (3:4)": (240, 240, 0, 0),
    "Full frame": (0, 0, 0, 0),
    "Custom": None,
}
VIDEO_EXT = "Videos (*.mp4 *.mov *.m4v *.mkv *.avi *.webm *.wmv)"
IMAGE_EXT = "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif)"
WEIGHTS = [("Regular", 400), ("Medium", 500), ("Semibold", 600), ("Bold", 700),
           ("Heavy", 800), ("Black", 900)]


def res_path(*parts):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def fmt_time(sec):
    sec = max(0.0, sec)
    m = int(sec // 60)
    return f"{m}:{sec - m * 60:05.2f}"


# ---------------------------------------------------------------- emoji
def _is_joiner(cp):
    return (cp in (0x200D, 0xFE0F, 0xFE0E, 0x20E3) or 0x1F3FB <= cp <= 0x1F3FF
            or 0xE0020 <= cp <= 0xE007F or 0x0300 <= cp <= 0x036F)


def clusters(text):
    """Split text into user-perceived characters, keeping emoji sequences whole."""
    out = []
    i, n = 0, len(text)
    while i < n:
        j = i + 1
        cp = ord(text[i])
        if 0x1F1E6 <= cp <= 0x1F1FF and j < n and 0x1F1E6 <= ord(text[j]) <= 0x1F1FF:
            j += 1  # flag = two regional indicators
        else:
            while j < n:
                c = ord(text[j])
                if c == 0x200D and j + 1 < n:
                    j += 2
                elif _is_joiner(c):
                    j += 1
                else:
                    break
        out.append(text[i:j])
        i = j
    return out


def is_emoji(cl):
    cps = [ord(c) for c in cl]
    first = cps[0]
    if first >= 0x1F000 or 0xFE0F in cps or 0x20E3 in cps:
        return True
    return (0x2600 <= first <= 0x27BF or 0x2300 <= first <= 0x23FF or 0x2B00 <= first <= 0x2BFF
            or first in (0x3030, 0x303D, 0x3297, 0x3299, 0x2122, 0x2139, 0x24C2, 0x203C, 0x2049))


def emoji_key(cl):
    return "-".join(f"{ord(c):x}" for c in cl if ord(c) != 0xFE0F)


class EmojiSet:
    """Optional folder of emoji images named by code point (e.g. 1f600.png,
    1f469-200d-1f4bb.png, emoji_u1f600.png). Without one, the system emoji font is used."""

    def __init__(self):
        self.folder = None
        self.index = {}
        self.cache = {}

    def load(self, folder):
        index = {}
        for root, _dirs, files in os.walk(folder):
            for f in files:
                stem, ext = os.path.splitext(f)
                if ext.lower() not in (".png", ".webp"):
                    continue
                stem = stem.lower().replace("emoji_u", "").replace("_", "-")
                if not re.fullmatch(r"[0-9a-f]{2,6}(-[0-9a-f]{2,6})*", stem):
                    continue
                key = "-".join(p for p in stem.split("-") if p != "fe0f")
                index.setdefault(key, os.path.join(root, f))
        self.folder = folder if index else None
        self.index = index
        self.cache = {}
        return len(index)

    def clear(self):
        self.folder, self.index, self.cache = None, {}, {}

    def image(self, cl):
        if not self.index:
            return None
        key = emoji_key(cl)
        if key not in self.cache:
            path = self.index.get(key)
            if path is None:
                parts = key.split("-")
                path = self.index.get(parts[0]) if len(parts) > 1 and "200d" not in parts else None
            img = QImage(path) if path else None
            self.cache[key] = img if img is not None and not img.isNull() else None
        return self.cache[key]


EMOJI = EmojiSet()


# ---------------------------------------------------------------- layers
def color_hex(c):
    return c.name(QColor.HexArgb)


class ImageLayer:
    """A logo or photo. (x, y) is the centre."""
    kind = "image"

    def __init__(self, img, path):
        self.img = img
        self.name = os.path.basename(path)
        self.w = 240.0
        self.x = W / 2
        self.y = H / 2
        self.opacity = 1.0

    def move_to(self, left, top):
        self.x = left + self.w / 2
        self.y = top + self.h / 2

    def to_dict(self):
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        self.img.save(buf, "PNG")
        return {"kind": "image", "name": self.name, "w": self.w, "x": self.x, "y": self.y,
                "opacity": self.opacity, "png": base64.b64encode(bytes(buf.data())).decode()}

    @classmethod
    def from_dict(cls, d):
        img = QImage.fromData(QByteArray(base64.b64decode(d["png"])), "PNG")
        img = img.convertToFormat(QImage.Format_ARGB32_Premultiplied)
        o = cls(img, d.get("name", "image.png"))
        o.w, o.x, o.y, o.opacity = d["w"], d["x"], d["y"], d.get("opacity", 1.0)
        return o

    @property
    def h(self):
        return self.w * self.img.height() / max(1, self.img.width())

    def rect(self):
        return QRectF(self.x - self.w / 2, self.y - self.h / 2, self.w, self.h)

    def label(self):
        return self.name

    def draw(self, p):
        p.save()
        p.setOpacity(self.opacity)
        p.drawImage(self.rect(), self.img)
        p.restore()


class TextLayer:
    """A fixed-width text box: the width never grows, long text wraps to new lines.
    (x, y) is the centre of the top edge, so extra lines grow downward."""
    kind = "text"
    FIELDS = ("text", "family", "weight", "size", "align", "style", "box_alpha", "radius", "pad",
              "spacing", "shadow", "opacity", "w", "x", "y")

    def __init__(self, text="Your text here"):
        self.text = text
        self.family = DEFAULT_FONT
        self.weight = 700
        self.size = 64
        self.color = QColor("#FFFFFF")
        self.align = "center"
        self.style = "box"           # plain | box | highlight
        self.box_color = QColor("#000000")
        self.box_alpha = 0.55
        self.radius = 28
        self.pad = 30
        self.spacing = 1.18
        self.shadow = False
        self.opacity = 1.0
        self.w = 760.0
        self.x = W / 2
        self.y = H / 2
        self._cache_key = None
        self._layout = None

    def label(self):
        t = " ".join(self.text.split())
        return t[:30] + "…" if len(t) > 30 else t or "Empty text"

    def move_to(self, left, top):
        self.x = left + self.w / 2
        self.y = top

    def to_dict(self):
        d = {k: getattr(self, k) for k in self.FIELDS}
        d.update(kind="text", color=color_hex(self.color), box_color=color_hex(self.box_color))
        return d

    @classmethod
    def from_dict(cls, d):
        o = cls(d.get("text", ""))
        for k in cls.FIELDS:
            if k in d:
                setattr(o, k, d[k])
        o.color = QColor(d.get("color", "#FFFFFFFF"))
        o.box_color = QColor(d.get("box_color", "#FF000000"))
        return o

    def font(self):
        f = QFont(self.family)
        f.setPixelSize(self.size)
        f.setWeight(QFont.Weight(self.weight))
        f.setHintingPreference(QFont.PreferNoHinting)
        return f

    def emoji_font(self):
        f = QFont()
        f.setFamilies(EMOJI_FONTS)
        f.setPixelSize(int(self.size * 0.92))
        return f

    def inner_pad(self):
        return self.pad if self.style == "box" else (self.size * 0.32 if self.style == "highlight" else 0)

    # layout --------------------------------------------------------
    def layout(self):
        key = (self.text, self.family, self.weight, self.size, self.w, self.style, self.pad,
               self.spacing, EMOJI.folder)
        if key == self._cache_key:
            return self._layout
        fm = QFontMetricsF(self.font())
        ew = self.size * 1.12
        maxw = max(20.0, self.w - 2 * self.inner_pad())
        space_w = fm.horizontalAdvance(" ")

        # tokens: ("nl",) ("sp", w) ("word", text, w) ("emoji", cluster, w)
        tokens, word = [], ""

        def flush():
            nonlocal word
            if word:
                tokens.append(("word", word, fm.horizontalAdvance(word)))
                word = ""
        for cl in clusters(self.text):
            if cl == "\n":
                flush()
                tokens.append(("nl",))
            elif cl in (" ", "\t"):
                flush()
                tokens.append(("sp", space_w))
            elif is_emoji(cl):
                flush()
                tokens.append(("emoji", cl, ew))
            else:
                word += cl
        flush()

        lines = [[]]
        x = 0.0

        def newline():
            nonlocal x
            while lines[-1] and lines[-1][-1][0] == "sp":
                lines[-1].pop()
            lines.append([])
            x = 0.0

        for t in tokens:
            if t[0] == "nl":
                newline()
                continue
            if t[0] == "sp":
                if x > 0:
                    lines[-1].append(t)
                    x += t[1]
                continue
            tw = t[-1]
            if x > 0 and x + tw > maxw:
                newline()
            if t[0] == "word" and tw > maxw:          # one very long word: break it
                chunk = ""
                for ch in clusters(t[1]):
                    if fm.horizontalAdvance(chunk + ch) > maxw and chunk:
                        lines[-1].append(("word", chunk, fm.horizontalAdvance(chunk)))
                        newline()
                        chunk = ""
                    chunk += ch
                t = ("word", chunk, fm.horizontalAdvance(chunk))
                tw = t[2]
            lines[-1].append(t)
            x += tw
        while lines[-1] and lines[-1][-1][0] == "sp":
            lines[-1].pop()

        widths = [sum(t[-1] for t in ln) for ln in lines]
        lh = self.size * self.spacing
        self._layout = (lines, widths, lh, fm.ascent(), fm.descent(), maxw)
        self._cache_key = key
        return self._layout

    @property
    def h(self):
        lines, _w, lh, *_ = self.layout()
        return len(lines) * lh + 2 * (self.pad if self.style == "box" else 0)

    def rect(self):
        return QRectF(self.x - self.w / 2, self.y, self.w, self.h)

    def draw(self, p):
        lines, widths, lh, asc, desc, maxw = self.layout()
        r = self.rect()
        ip = self.inner_pad()
        top = r.top() + (self.pad if self.style == "box" else 0)
        left = r.left() + ip
        p.save()
        p.setOpacity(self.opacity)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        bc = QColor(self.box_color)
        bc.setAlphaF(self.box_alpha)
        if self.style == "box":
            p.setPen(Qt.NoPen)
            p.setBrush(bc)
            p.drawRoundedRect(r, self.radius, self.radius)

        def line_x(i):
            if self.align == "left":
                return left
            if self.align == "right":
                return left + maxw - widths[i]
            return left + (maxw - widths[i]) / 2

        if self.style == "highlight":
            p.setPen(Qt.NoPen)
            p.setBrush(bc)
            hp = self.size * 0.32
            path = QPainterPath()
            for i, ln in enumerate(lines):
                if not ln:
                    continue
                lx = line_x(i)
                path.addRoundedRect(QRectF(lx - hp, top + i * lh - lh * 0.02, widths[i] + 2 * hp, lh * 1.04),
                                    min(self.radius, lh / 2), min(self.radius, lh / 2))
            p.drawPath(path.simplified())

        font, efont = self.font(), self.emoji_font()
        text_h = asc + desc
        passes = [(QColor(0, 0, 0, 120), self.size * 0.05)] if self.shadow else []
        passes.append((self.color, 0))
        for color, off in passes:
            for i, ln in enumerate(lines):
                x = line_x(i)
                base = top + i * lh + (lh - text_h) / 2 + asc
                for t in ln:
                    if t[0] == "word":
                        p.setFont(font)
                        p.setPen(color)
                        p.drawText(QPointF(x + off, base + off), t[1])
                    elif t[0] == "emoji" and off == 0:
                        img = EMOJI.image(t[1])
                        es = self.size * 1.02
                        ey = top + i * lh + (lh - es) / 2
                        if img is not None:
                            p.drawImage(QRectF(x + (t[2] - es) / 2, ey, es, es), img)
                        else:
                            p.setFont(efont)
                            p.setPen(color)
                            p.drawText(QRectF(x, top + i * lh, t[2], lh), Qt.AlignCenter, t[1])
                    x += t[-1]
        p.restore()


