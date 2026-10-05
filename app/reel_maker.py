"""
Reel Maker — turn a 16:9 video into a 9:16 Instagram Reel.

Background (black / white / blurred / custom), safe-zone guides, trimming,
text boxes, logos and photos, reusable locked templates, a 9:16 cover
picked from the full 16:9 frame, and MP4 export through FFmpeg.
"""

import copy
import json
import os
import re
import sys
import tempfile

from PySide6.QtCore import Qt, QUrl, QRectF, QPointF, QTimer, QProcess, Signal, QSettings, QSize
from PySide6.QtGui import (QDesktopServices, QImage, QPainter, QColor, QPen, QFont, QPainterPath, QPixmap, QIcon, QLinearGradient,
                           QKeySequence, QShortcut, QFontMetricsF, QFontDatabase, QPalette, QAction)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QGridLayout, QPushButton,
    QButtonGroup, QComboBox, QSpinBox, QDoubleSpinBox, QSlider, QCheckBox, QLabel, QListWidget,
    QListWidgetItem, QFileDialog, QColorDialog, QLineEdit, QProgressBar, QScrollArea, QMessageBox,
    QSizePolicy, QFrame, QToolButton, QPlainTextEdit, QFontComboBox, QStackedWidget, QTabWidget,
    QMenu, QInputDialog, QProgressDialog)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoSink

from core import (__version__, check_for_update, download_update, W, H, ACCENT, DEFAULT_FONT, PRESETS, VIDEO_EXT, IMAGE_EXT, WEIGHTS, APPDATA,
                  TEMPLATE_DIR, EMOJI, ImageLayer, TextLayer, color_hex, res_path, fmt_time,
                  find_ffmpeg, download_ffmpeg)

# ---------------------------------------------------------------- theme
C = dict(bg="#0D0E10", panel="#141518", raised="#1C1D21", raised2="#26272C", field="#0F1012",
         line="#25262B", line2="#33343A", text="#ECECEF", muted="#8A8C93", faint="#5A5C63",
         accent="#F2B31B", accent_hi="#FFC53D", on_accent="#1A1400")


def make_png(path, size, painter_fn):
    img = QImage(size[0], size[1], QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    painter_fn(p)
    p.end()
    img.save(path, "PNG")
    return path.replace("\\", "/")


def build_style_assets(folder):
    """Small images the stylesheet uses (switches, chevron, check)."""
    def switch(on):
        def fn(p):
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(C["accent"] if on else C["line2"]))
            p.drawRoundedRect(QRectF(0, 0, 68, 40), 20, 20)
            p.setBrush(QColor("#FFFFFF" if on else "#C9CAD0"))
            p.drawEllipse(QRectF(32 if on else 4, 4, 32, 32))
        return fn

    def chevron(p):
        pen = QPen(QColor(C["muted"]), 3)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        path = QPainterPath()
        path.moveTo(6, 10)
        path.lineTo(14, 18)
        path.lineTo(22, 10)
        p.drawPath(path)

    return {
        "on": make_png(os.path.join(folder, "sw_on.png"), (68, 40), switch(True)),
        "off": make_png(os.path.join(folder, "sw_off.png"), (68, 40), switch(False)),
        "chev": make_png(os.path.join(folder, "chev.png"), (28, 28), chevron),
    }


def stylesheet(a):
    return f"""
* {{ font-family: "Inter Display", "Segoe UI", sans-serif; font-size: 13px; color: {C['text']}; }}
QMainWindow, #root, #canvasArea {{ background: {C['bg']}; }}
#topbar {{ background: {C['panel']}; border-bottom: 1px solid {C['line']}; }}
#side {{ background: {C['panel']}; border-left: 1px solid {C['line']}; }}
#transport {{ background: {C['bg']}; }}
#sidePage {{ background: {C['panel']}; }}
QLabel {{ background: transparent; }}
#appName {{ font-size: 15px; font-weight: 700; }}
QLabel[muted="true"] {{ color: {C['muted']}; }}
QLabel[faint="true"] {{ color: {C['faint']}; font-size: 12px; }}
#section {{ color: {C['muted']}; font-size: 11px; font-weight: 700; letter-spacing: 1.2px; padding-top: 6px; }}
#mono {{ font-family: "Cascadia Mono", Consolas, monospace; color: {C['muted']}; }}
#chip {{ background: rgba(242,179,27,0.13); color: {C['accent']}; border-radius: 11px; padding: 3px 10px; font-weight: 600; }}
#banner {{ background: rgba(242,179,27,0.09); border: 1px solid rgba(242,179,27,0.28); border-radius: 10px; padding: 10px 12px; color: {C['text']}; }}
#divider {{ background: {C['line']}; max-height: 1px; min-height: 1px; }}

QPushButton, QToolButton {{ background: {C['raised']}; border: 1px solid {C['line']}; border-radius: 9px; padding: 7px 12px; }}
QPushButton:hover, QToolButton:hover {{ background: {C['raised2']}; border-color: {C['line2']}; }}
QPushButton:pressed, QToolButton:pressed {{ background: {C['field']}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {C['faint']}; background: {C['panel']}; border-color: {C['line']}; }}
QPushButton#primary {{ background: {C['accent']}; color: {C['on_accent']}; border: none; font-weight: 700; padding: 8px 18px; }}
QPushButton#primary:hover {{ background: {C['accent_hi']}; }}
QPushButton#primary:disabled {{ background: #6E5A22; color: #2B2410; }}
QPushButton#ghost, QToolButton#ghost {{ background: transparent; border: 1px solid transparent; }}
QPushButton#ghost:hover, QToolButton#ghost:hover {{ background: {C['raised']}; border-color: {C['line']}; }}
QToolButton#round {{ border-radius: 19px; padding: 0; background: {C['text']}; border: none; }}
QToolButton#round:hover {{ background: #FFFFFF; }}
QToolButton#round:disabled {{ background: {C['line2']}; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}
QToolButton:checked#ghost {{ background: rgba(242,179,27,0.13); border-color: rgba(242,179,27,0.35); }}

#seg {{ background: {C['field']}; border: 1px solid {C['line']}; border-radius: 10px; }}
#seg QToolButton {{ background: transparent; border: none; border-radius: 7px; padding: 6px 4px; color: {C['muted']}; font-weight: 600; }}
#seg QToolButton:hover {{ color: {C['text']}; }}
#seg QToolButton:checked {{ background: {C['raised2']}; color: {C['text']}; }}
#seg QToolButton:disabled {{ color: {C['faint']}; }}

QLineEdit, QPlainTextEdit, QAbstractSpinBox, QComboBox {{
    background: {C['field']}; border: 1px solid {C['line']}; border-radius: 9px; padding: 6px 9px;
    selection-background-color: {C['accent']}; selection-color: {C['on_accent']}; }}
QLineEdit:focus, QPlainTextEdit:focus, QAbstractSpinBox:focus, QComboBox:focus {{ border-color: {C['accent']}; }}
QLineEdit:disabled, QPlainTextEdit:disabled, QAbstractSpinBox:disabled, QComboBox:disabled {{ color: {C['faint']}; }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ width: 0; border: none; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow {{ image: url({a['chev']}); width: 14px; height: 14px; }}
QComboBox QAbstractItemView {{ background: {C['raised']}; border: 1px solid {C['line2']}; padding: 4px;
    selection-background-color: {C['raised2']}; selection-color: {C['text']}; outline: none; }}

QSlider {{ min-height: 22px; }}
QSlider::groove:horizontal {{ height: 4px; background: {C['line2']}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {C['accent']}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: #FFFFFF; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }}
QSlider::sub-page:horizontal:disabled {{ background: {C['line2']}; }}
QSlider::handle:horizontal:disabled {{ background: {C['faint']}; }}

QCheckBox {{ spacing: 10px; }}
QCheckBox::indicator {{ width: 34px; height: 20px; }}
QCheckBox::indicator:unchecked {{ image: url({a['off']}); }}
QCheckBox::indicator:checked {{ image: url({a['on']}); }}
QCheckBox:disabled {{ color: {C['faint']}; }}

QListWidget {{ background: {C['field']}; border: 1px solid {C['line']}; border-radius: 10px; padding: 4px; outline: none; }}
QListWidget::item {{ padding: 8px 8px; border-radius: 7px; }}
QListWidget::item:hover {{ background: {C['raised']}; }}
QListWidget::item:selected {{ background: {C['raised2']}; color: {C['text']}; }}

QTabWidget::pane {{ border: none; background: {C['panel']}; }}
QTabBar {{ background: {C['panel']}; }}
QTabBar::tab {{ background: transparent; color: {C['muted']}; padding: 13px 4px 11px 4px; margin: 0 9px;
    border: none; border-bottom: 2px solid transparent; font-weight: 600; }}
QTabBar::tab:hover {{ color: {C['text']}; }}
QTabBar::tab:selected {{ color: {C['text']}; border-bottom: 2px solid {C['accent']}; }}

QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {C['line2']}; border-radius: 3px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QProgressBar {{ background: {C['field']}; border: none; border-radius: 3px; max-height: 6px; min-height: 6px; color: transparent; }}
QProgressBar::chunk {{ background: {C['accent']}; border-radius: 3px; }}

QMenu {{ background: {C['raised']}; border: 1px solid {C['line2']}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 8px 22px 8px 14px; border-radius: 7px; }}
QMenu::item:selected {{ background: {C['raised2']}; }}
QMenu::item:disabled {{ color: {C['faint']}; }}
QMenu::separator {{ height: 1px; background: {C['line2']}; margin: 5px 6px; }}
QToolTip {{ background: {C['raised']}; color: {C['text']}; border: 1px solid {C['line2']}; padding: 6px 8px; border-radius: 6px; }}
QStatusBar {{ background: {C['panel']}; color: {C['muted']}; border-top: 1px solid {C['line']}; font-size: 12px; }}
QStatusBar::item {{ border: none; }}
QMessageBox, QInputDialog, QColorDialog {{ background: {C['panel']}; }}
"""


def dark_palette():
    pal = QPalette()
    for role, col in ((QPalette.Window, C["panel"]), (QPalette.WindowText, C["text"]),
                      (QPalette.Base, C["field"]), (QPalette.AlternateBase, C["raised"]),
                      (QPalette.Text, C["text"]), (QPalette.Button, C["raised"]),
                      (QPalette.ButtonText, C["text"]), (QPalette.Highlight, C["accent"]),
                      (QPalette.HighlightedText, C["on_accent"]), (QPalette.ToolTipBase, C["raised"]),
                      (QPalette.ToolTipText, C["text"]), (QPalette.PlaceholderText, C["faint"]),
                      (QPalette.Mid, C["line2"])):
        pal.setColor(role, QColor(col))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(C["faint"]))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(C["faint"]))
    pal.setColor(QPalette.Disabled, QPalette.WindowText, QColor(C["faint"]))
    return pal


# ---------------------------------------------------------------- icons
def icon(kind, color=C["text"], size=20):
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(size * 2 / 24, size * 2 / 24)
    col = QColor(color)
    pen = QPen(col, 1.9)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    if kind == "play":
        path = QPainterPath()
        path.moveTo(8.5, 6)
        path.lineTo(18.5, 12)
        path.lineTo(8.5, 18)
        path.closeSubpath()
        p.setPen(QPen(col, 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(col)
        p.drawPath(path)
    elif kind == "pause":
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawRoundedRect(QRectF(7, 6, 3.6, 12), 1.2, 1.2)
        p.drawRoundedRect(QRectF(13.4, 6, 3.6, 12), 1.2, 1.2)
    elif kind in ("lock", "unlock"):
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(5, 11, 14, 9.5), 2.5, 2.5)
        path = QPainterPath()
        if kind == "lock":
            path.moveTo(8, 11)
            path.lineTo(8, 8)
            path.arcTo(QRectF(8, 4, 8, 8), 180, -180)
            path.lineTo(16, 11)
        else:
            path.moveTo(8, 11)
            path.lineTo(8, 8)
            path.arcTo(QRectF(8, 4, 8, 8), 180, -150)
        p.drawPath(path)
    elif kind == "plus":
        p.setPen(pen)
        p.drawLine(QPointF(12, 6), QPointF(12, 18))
        p.drawLine(QPointF(6, 12), QPointF(18, 12))
    elif kind == "text":
        p.setPen(pen)
        p.drawLine(QPointF(6, 7), QPointF(18, 7))
        p.drawLine(QPointF(12, 7), QPointF(12, 18))
    elif kind == "image":
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(4.5, 5.5, 15, 13), 2.5, 2.5)
        path = QPainterPath()
        path.moveTo(5, 16.5)
        path.lineTo(10, 11.5)
        path.lineTo(14, 15)
        path.lineTo(16, 13)
        path.lineTo(19.5, 16)
        p.drawPath(path)
        p.drawEllipse(QPointF(15, 9.5), 1.3, 1.3)
    elif kind == "folder":
        p.setPen(pen)
        path = QPainterPath()
        path.moveTo(4, 7.5)
        path.lineTo(9.5, 7.5)
        path.lineTo(11, 9)
        path.lineTo(20, 9)
        path.lineTo(20, 18)
        path.lineTo(4, 18)
        path.closeSubpath()
        p.drawPath(path)
    elif kind == "template":
        p.setPen(pen)
        p.drawRoundedRect(QRectF(7, 3.5, 10, 17), 2.5, 2.5)
        p.drawLine(QPointF(9.5, 8), QPointF(14.5, 8))
        p.drawLine(QPointF(9.5, 15.5), QPointF(14.5, 15.5))
    elif kind == "update":
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(5, 5, 14, 14), 60 * 16, 270 * 16)
        path = QPainterPath()
        path.moveTo(15.2, 3.6)
        path.lineTo(15.8, 7.4)
        path.lineTo(12, 7.9)
        p.drawPath(path)
    elif kind == "down":
        p.setPen(pen)
        path = QPainterPath()
        path.moveTo(7, 10)
        path.lineTo(12, 15)
        path.lineTo(17, 10)
        p.drawPath(path)
    elif kind == "logo":
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#111216"))
        p.drawRoundedRect(QRectF(0.5, 0.5, 23, 23), 6, 6)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 80), 0.9))
        p.drawRoundedRect(QRectF(3.9, 7.7, 16.2, 8.6), 1.4, 1.4)
        g = QLinearGradient(9, 4.5, 15, 19.5)
        g.setColorAt(0, QColor("#FFC53D"))
        g.setColorAt(1, QColor("#FF6A3D"))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(QRectF(8.5, 4.6, 7, 14.8), 1.6, 1.6)
        path = QPainterPath()
        path.moveTo(10.9, 9.9)
        path.lineTo(14.1, 12)
        path.lineTo(10.9, 14.1)
        path.closeSubpath()
        p.setBrush(QColor("#111216"))
        p.drawPath(path)
    p.end()
    return QIcon(pm)


# ---------------------------------------------------------------- small widgets
def label(text, kind=None):
    lb = QLabel(text)
    if kind == "section":
        lb.setObjectName("section")
        lb.setText(text.upper())
    elif kind:
        lb.setProperty(kind, True)
    return lb


def divider():
    f = QFrame()
    f.setObjectName("divider")
    return f


class Segmented(QWidget):
    changed = Signal(int)

    def __init__(self, options, checkable=True):
        super().__init__()
        self.setObjectName("seg")
        self.setAttribute(Qt.WA_StyledBackground, True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        self.group = QButtonGroup(self)
        self.group.setExclusive(checkable)
        self.buttons = []
        for i, opt in enumerate(options):
            b = QToolButton(text=opt)
            b.setCheckable(checkable)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.setCursor(Qt.PointingHandCursor)
            self.group.addButton(b, i)
            lay.addWidget(b)
            self.buttons.append(b)
        if checkable:
            self.buttons[0].setChecked(True)
            self.group.idToggled.connect(lambda i, on: on and self.changed.emit(i))
        else:
            self.group.idClicked.connect(self.changed.emit)

    def value(self):
        return self.group.checkedId()

    def setValue(self, i):
        b = self.group.button(i)
        if b and not b.isChecked():
            b.setChecked(True)


class Swatch(QToolButton):
    colorChanged = Signal(QColor)

    def __init__(self, color, title="Colour", alpha=False):
        super().__init__()
        self.title = title
        self.alpha = alpha
        self.setFixedSize(30, 30)
        self.setCursor(Qt.PointingHandCursor)
        self.clicked.connect(self.pick)
        self.setColor(color)

    def setColor(self, c):
        self.color = QColor(c)
        self.setStyleSheet(f"QToolButton{{background:{self.color.name()};border:2px solid {C['line2']};"
                           f"border-radius:15px;padding:0}} QToolButton:hover{{border-color:{C['muted']}}}")

    def pick(self):
        opts = QColorDialog.ShowAlphaChannel if self.alpha else QColorDialog.ColorDialogOption(0)
        c = QColorDialog.getColor(self.color, self.window(), self.title, opts)
        if c.isValid():
            self.setColor(c)
            self.colorChanged.emit(c)


def spin(lo, hi, val=0, suffix="", step=1):
    s = QSpinBox()
    s.setRange(lo, hi)
    s.setValue(val)
    s.setSingleStep(step)
    s.setSuffix(suffix)
    s.setButtonSymbols(QSpinBox.NoButtons)
    s.setAlignment(Qt.AlignRight)
    return s


def slider(lo, hi, val):
    s = QSlider(Qt.Horizontal)
    s.setRange(lo, hi)
    s.setValue(val)
    s.setCursor(Qt.PointingHandCursor)
    return s


def row(*widgets, stretch_index=None, spacing=8):
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(spacing)
    for i, x in enumerate(widgets):
        if x is None:
            lay.addStretch(1)
        elif isinstance(x, str):
            lb = label(x, "muted")
            lay.addWidget(lb)
        else:
            lay.addWidget(x, 1 if i == stretch_index else 0)
    return w


def field(name, widget):
    """Label on the left, control on the right."""
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(10)
    lb = label(name, "muted")
    lb.setFixedWidth(76)
    lay.addWidget(lb)
    lay.addWidget(widget, 1)
    return w


class SidePage(QScrollArea):
    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setObjectName("sidePage")
        self.lay = QVBoxLayout(inner)
        self.lay.setContentsMargins(20, 16, 20, 24)
        self.lay.setSpacing(10)
        self.setWidget(inner)

    def add(self, w):
        self.lay.addWidget(w)
        return w

    def section(self, title, first=False):
        if not first:
            self.lay.addSpacing(8)
            self.lay.addWidget(divider())
            self.lay.addSpacing(4)
        self.lay.addWidget(label(title, "section"))

    def finish(self):
        self.lay.addStretch(1)



# ---------------------------------------------------------------- emoji picker
SKIN_TONES = ["", "\U0001F3FB", "\U0001F3FC", "\U0001F3FD", "\U0001F3FE", "\U0001F3FF"]
CATEGORY_ICONS = {"Recent": "🕘", "Smileys & Emotion": "😀", "People & Body": "👋", "Animals & Nature": "🐻",
                  "Food & Drink": "🍔", "Travel & Places": "✈️", "Activities": "⚽", "Objects": "💡",
                  "Symbols": "❤️", "Flags": "🏁"}


def load_emoji_list():
    try:
        with open(res_path("emoji_list.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def with_tone(e, tone):
    if not tone:
        return e
    base = e.replace("\ufe0f", "", 1) if len(e) > 1 and e[1] == "\ufe0f" else e
    return base[0] + tone + base[1:]


class EmojiPicker(QFrame):
    """Pop-up emoji grid drawn in the emoji style the app is using."""
    picked = Signal(str)

    def __init__(self, app):
        super().__init__(app, Qt.Popup)
        self.app = app
        self.setObjectName("emojiPicker")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"#emojiPicker{{background:{C['raised']};border:1px solid {C['line2']};border-radius:12px}}"
                           "QListWidget{background:transparent;border:none;padding:0}"
                           f"QListWidget::item{{padding:0;border-radius:8px}}"
                           f"QListWidget::item:hover{{background:{C['raised2']}}}"
                           "QListWidget::item:selected{background:transparent}")
        self.setFixedSize(392, 420)
        self.data = load_emoji_list()
        self.names = {e: n for _, items in self.data for e, n, _ in items}
        self.skin = {e for _, items in self.data for e, _, sk in items if sk}
        self.icons = {}
        self.tone = SKIN_TONES[min(5, max(0, app.settings.value("skin_tone", 0, type=int)))]
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 10, 10, 8)
        v.setSpacing(8)
        top = QHBoxLayout()
        top.setSpacing(6)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search emoji")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.on_search)
        top.addWidget(self.search, 1)
        self.tone_btn = QToolButton()
        self.tone_btn.setObjectName("ghost")
        self.tone_btn.setToolTip("Skin tone")
        self.tone_btn.setIconSize(QSize(22, 22))
        self.tone_btn.setStyleSheet("QToolButton{padding:4px}")
        self.tone_btn.setPopupMode(QToolButton.InstantPopup)
        tm = QMenu(self.tone_btn)
        for i, t in enumerate(SKIN_TONES):
            a = tm.addAction(self.emoji_icon("👋" + t if t else "👋"), ["Default", "Light", "Medium-light", "Medium",
                                                                      "Medium-dark", "Dark"][i])
            a.triggered.connect(lambda _=False, t=t, i=i: self.set_tone(t, i))
        self.tone_btn.setMenu(tm)
        top.addWidget(self.tone_btn)
        v.addLayout(top)

        self.cats = QWidget()
        cl = QHBoxLayout(self.cats)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(2)
        self.cat_group = QButtonGroup(self)
        self.cat_names = ["Recent"] + [g for g, _ in self.data]
        for i, name in enumerate(self.cat_names):
            b = QToolButton()
            b.setObjectName("ghost")
            b.setCheckable(True)
            b.setToolTip(name.replace("&", "&&"))
            b.setIcon(self.emoji_icon(CATEGORY_ICONS.get(name, "😀")))
            b.setIconSize(QSize(20, 20))
            b.setFixedSize(34, 32)
            b.setStyleSheet("QToolButton{padding:2px}")
            b.setCursor(Qt.PointingHandCursor)
            self.cat_group.addButton(b, i)
            cl.addWidget(b)
        cl.addStretch(1)
        self.cat_group.idClicked.connect(self.show_category)
        v.addWidget(self.cats)

        self.title = label("", "section")
        v.addWidget(self.title)
        self.grid = QListWidget()
        self.grid.setViewMode(QListWidget.IconMode)
        self.grid.setIconSize(QSize(30, 30))
        self.grid.setGridSize(QSize(40, 40))
        self.grid.setUniformItemSizes(True)
        self.grid.setMovement(QListWidget.Static)
        self.grid.setResizeMode(QListWidget.Adjust)
        self.grid.setMouseTracking(True)
        self.grid.setCursor(Qt.PointingHandCursor)
        self.grid.itemClicked.connect(self.on_pick)
        self.grid.itemEntered.connect(lambda it: self.hint.setText(it.toolTip()))
        v.addWidget(self.grid, 1)
        self.hint = label("", "faint")
        v.addWidget(self.hint)
        self.update_tone_button()

    # ------------------------------------------------------------------
    def style_key(self):
        return (EMOJI.font_family, EMOJI.folder)

    def emoji_icon(self, e):
        key = (e, self.style_key())
        ic = self.icons.get(key)
        if ic is None:
            img = EMOJI.image(e)
            if img is None:
                pm = QPixmap(64, 64)
                pm.fill(Qt.transparent)
                p = QPainter(pm)
                f = QFont()
                f.setFamilies(["Segoe UI Emoji", "Noto Color Emoji"])
                f.setPixelSize(48)
                p.setFont(f)
                p.drawText(QRectF(0, 0, 64, 64), Qt.AlignCenter, e)
                p.end()
            else:
                pm = QPixmap.fromImage(img.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            ic = QIcon(pm)
            self.icons[key] = ic
        return ic

    def toned(self, e):
        if self.tone and e in self.skin:
            t = with_tone(e, self.tone)
            if EMOJI.image(t) is not None:
                return t
        return e

    def fill(self, emojis):
        self.grid.clear()
        for e in emojis:
            e2 = self.toned(e)
            it = QListWidgetItem(self.emoji_icon(e2), "")
            it.setData(Qt.UserRole, e2)
            it.setToolTip(self.names.get(e, "").capitalize())
            it.setSizeHint(QSize(40, 40))
            self.grid.addItem(it)
        self.grid.scrollToTop()

    def recent(self):
        return [e for e in (self.app.settings.value("recent_emoji", [], type=list) or []) if e]

    def show_category(self, i):
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        name = self.cat_names[i]
        self.cat_group.button(i).setChecked(True)
        self.title.setText(name.upper())
        if name == "Recent":
            items = self.recent()
            self.hint.setText("" if items else "Emoji you use will show up here.")
        else:
            items = [e for e, _, _ in dict(self.data)[name]]
            self.hint.setText("")
        self.fill(items)

    def on_search(self, text):
        q = text.strip().lower()
        if not q:
            self.show_category(max(0, self.cat_group.checkedId()))
            return
        words = q.split()

        def rank(n):
            if n == q:
                return 0
            if n.startswith(q):
                return 1
            if all(any(t.startswith(w) for t in n.replace("-", " ").split()) for w in words):
                return 2
            return 3
        hits = [(rank(n), i, e) for i, (e, n) in enumerate((e, n) for _, items in self.data for e, n, _ in items)
                if all(w in n for w in words)]
        hits = [e for _, _, e in sorted(hits)]
        self.title.setText(f"RESULTS FOR “{text.strip().upper()}”")
        self.hint.setText("" if hits else "No emoji found.")
        self.fill(hits[:240])

    def on_pick(self, it):
        e = it.data(Qt.UserRole)
        base = next((b for b in self.names if with_tone(b, self.tone) == e), e)
        rec = [base] + [x for x in self.recent() if x != base]
        self.app.settings.setValue("recent_emoji", rec[:40])
        self.picked.emit(e)

    def set_tone(self, t, i):
        self.tone = t
        self.app.settings.setValue("skin_tone", i)
        self.update_tone_button()
        if self.search.text().strip():
            self.on_search(self.search.text())
        else:
            self.show_category(max(0, self.cat_group.checkedId()))

    def update_tone_button(self):
        self.tone_btn.setIcon(self.emoji_icon("👋" + self.tone if self.tone else "👋"))

    def open_at(self, widget):
        # refresh category icons in case the emoji style changed
        for i, name in enumerate(self.cat_names):
            self.cat_group.button(i).setIcon(self.emoji_icon(CATEGORY_ICONS.get(name, "😀")))
        self.update_tone_button()
        self.show_category(0 if self.recent() else 1)
        pos = widget.mapToGlobal(widget.rect().bottomLeft())
        scr = widget.screen().availableGeometry()
        x = min(pos.x(), scr.right() - self.width() - 8)
        y = pos.y() + 6
        if y + self.height() > scr.bottom():
            y = widget.mapToGlobal(widget.rect().topLeft()).y() - self.height() - 6
        self.move(x, y)
        self.show()
        self.search.setFocus()


# ---------------------------------------------------------------- on-canvas text editing
class CanvasTextEdit(QPlainTextEdit):
    """Sits exactly over a text layer on the preview so you can type in place."""
    done = Signal()

    def __init__(self, canvas, layer):
        super().__init__(canvas)
        self.canvas = canvas
        self.layer = layer
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.document().setDocumentMargin(0)
        self.setContentsMargins(0, 0, 0, 0)
        self.setViewportMargins(0, 0, 0, 0)
        self.setPlainText(layer.text)
        self.style_from_layer()

    def style_from_layer(self):
        if getattr(self, "_styling", False):
            return
        self._styling = True
        was = self.blockSignals(True)
        try:
            self._apply_style()
        finally:
            self.blockSignals(was)
            self._styling = False

    def _apply_style(self):
        L = self.layer
        s, _, _ = self.canvas.geom()
        f = L.font()
        f.setPixelSize(max(6, round(L.size * s)))
        self.setFont(f)
        c = L.color
        self.setStyleSheet(
            "QPlainTextEdit{background:transparent;border:none;padding:0;"
            f"font-family:'{L.family}';font-size:{f.pixelSize()}px;font-weight:{L.weight};"
            f"color:rgba({c.red()},{c.green()},{c.blue()},{c.alpha()});"
            f"selection-background-color:{C['accent']};selection-color:{C['on_accent']}}}")
        opt = self.document().defaultTextOption()
        opt.setAlignment({"left": Qt.AlignLeft, "right": Qt.AlignRight}.get(L.align, Qt.AlignHCenter))
        opt.setWrapMode(opt.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.document().setDefaultTextOption(opt)
        # match the layer's line spacing
        fm = QFontMetricsF(f)
        lh = L.size * L.spacing * s
        cur = self.textCursor()
        cur.select(cur.SelectionType.Document)
        fmt = cur.blockFormat()
        fmt.setLineHeight(lh, 2)   # 2 = FixedHeight
        fmt.setAlignment(opt.alignment())
        cur.mergeBlockFormat(fmt)
        self._top_pad = max(0.0, (lh - fm.height()) / 2)
        self.place()

    def place(self):
        L = self.layer
        s, ox, oy = self.canvas.geom()
        r = L.rect()
        ip = L.inner_pad()
        top = r.top() + (L.pad if L.style == "box" else 0)
        lines, _w, lh, *_ = L.layout()
        x = ox + (r.left() + ip) * s
        y = oy + top * s + getattr(self, "_top_pad", 0) * 0
        w = (L.w - 2 * ip) * s + 4
        h = max(lh, len(lines) * lh) * s + lh * s
        self.setGeometry(int(x) - 2, int(y), int(w) + 2, int(h))

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape or (e.key() in (Qt.Key_Return, Qt.Key_Enter)
                                        and e.modifiers() & Qt.ControlModifier):
            self.done.emit()
            return
        super().keyPressEvent(e)

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        if e.reason() != Qt.PopupFocusReason:
            QTimer.singleShot(0, self.done.emit)

# ---------------------------------------------------------------- reel canvas
class Canvas(QWidget):
    """The 9:16 frame. Drag layers (or the video) to move them; drag a selected
    layer's corner to resize it. Locked templates can't be moved."""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setMinimumSize(240, 420)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.drag = None
        self.guides = []          # [("v"|"h", position, is_frame_centre)]
        self.setFocusPolicy(Qt.ClickFocus)

    # ---------------------------------------------------------- smart guides
    SNAP_PX = 8                   # screen pixels

    def snap_targets(self, exclude):
        """Lines things can line up with, in frame pixels."""
        a = self.app
        z = a.zone()
        xs = [(W / 2, True), (z.left(), False), (z.center().x(), False), (z.right(), False)]
        ys = [(H / 2, True), (z.top(), False), (z.center().y(), False), (z.bottom(), False)]
        rects = [o.rect() for o in a.layers if o is not exclude]
        if exclude != "video":
            rects.append(a.video_rect())
        for r in rects:
            xs += [(r.left(), False), (r.center().x(), False), (r.right(), False)]
            ys += [(r.top(), False), (r.center().y(), False), (r.bottom(), False)]
        return xs, ys

    def snap(self, rect, exclude, alt=False):
        """Return (dx, dy) that lines rect up with the nearest guide, and record
        the guides to draw. Hold Alt to move freely."""
        self.guides = []
        if alt or not self.app.snap_on.isChecked():
            return 0.0, 0.0
        s, _, _ = self.geom()
        tol = self.SNAP_PX / s
        xs, ys = self.snap_targets(exclude)

        def best(edges, targets):
            # The frame centre wins whenever it's in reach; otherwise the nearest line.
            hit = None
            for e in edges:
                for t, centre in targets:
                    d = t - e
                    if abs(d) > tol:
                        continue
                    if (hit is None or (centre and not hit[2])
                            or (centre == hit[2] and abs(d) < abs(hit[0]))):
                        hit = (d, t, centre)
            return hit
        hx = best((rect.left(), rect.center().x(), rect.right()), xs)
        hy = best((rect.top(), rect.center().y(), rect.bottom()), ys)
        dx = hx[0] if hx else 0.0
        dy = hy[0] if hy else 0.0
        moved = rect.translated(dx, dy)
        # show every guide the snapped rect now touches (one line per position)
        found = {}
        for kind, edges, targets in (("v", (moved.left(), moved.center().x(), moved.right()), xs),
                                     ("h", (moved.top(), moved.center().y(), moved.bottom()), ys)):
            for edge in edges:
                for t, centre in targets:
                    if abs(edge - t) < 0.5:
                        key = (kind, round(t, 1))
                        found[key] = found.get(key, False) or centre
        self.guides = [(k, pos, c) for (k, pos), c in found.items()]
        return dx, dy

    def draw_smart_guides(self, p, s):
        if not self.guides or not self.drag:
            return
        pink = QColor("#FF3EA5")
        f = QFont(DEFAULT_FONT)
        f.setPixelSize(max(11, int(11 / s)))
        f.setWeight(QFont.Bold)
        p.setFont(f)
        for kind, pos, centre in self.guides:
            pen = QPen(pink, (1.6 if centre else 1.1) / s)
            if not centre:
                pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            if kind == "v":
                p.drawLine(QPointF(pos, 0), QPointF(pos, H))
            else:
                p.drawLine(QPointF(0, pos), QPointF(W, pos))
            if centre:
                txt = "Centre"
                fm = QFontMetricsF(f)
                tw, th = fm.horizontalAdvance(txt) + 14 / s, fm.height() + 6 / s
                box = (QRectF(pos - tw / 2, 14 / s, tw, th) if kind == "v"
                       else QRectF(14 / s, pos - th / 2, tw, th))
                p.setPen(Qt.NoPen)
                p.setBrush(pink)
                p.drawRoundedRect(box, th / 2, th / 2)
                p.setPen(QColor("white"))
                p.drawText(box, Qt.AlignCenter, txt)

    def geom(self):
        m = 28
        s = min((self.width() - 2 * m) / W, (self.height() - 2 * m) / H)
        ox = (self.width() - W * s) / 2
        oy = (self.height() - H * s) / 2
        return s, ox, oy

    def to_frame(self, pos):
        s, ox, oy = self.geom()
        return QPointF((pos.x() - ox) / s, (pos.y() - oy) / s)

    def paintEvent(self, _):
        a = self.app
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(C["bg"]))
        s, ox, oy = self.geom()
        frame = QRectF(ox, oy, W * s, H * s)
        # soft shadow
        for i in range(10, 0, -2):
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 10))
            p.drawRoundedRect(frame.adjusted(-i, -i + 4, i, i + 4), 14 + i, 14 + i)
        clip = QPainterPath()
        clip.addRoundedRect(frame, 12, 12)
        p.setClipPath(clip)
        p.translate(ox, oy)
        p.scale(s, s)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        a.compose(p, a.frame, overlays=True)
        if a.show_guides.isChecked():
            self.draw_guides(p, s)
        o = a.selected()
        if o and not a.locked:
            r = o.rect()
            p.setPen(QPen(ACCENT, 2 / s))
            p.setBrush(Qt.NoBrush)
            p.drawRect(r)
            hs = 6 / s
            p.setBrush(QColor("#FFFFFF"))
            p.setPen(QPen(ACCENT, 1.5 / s))
            for c in (r.topLeft(), r.topRight(), r.bottomLeft(), r.bottomRight()):
                p.drawEllipse(c, hs, hs)
        elif o and a.locked:
            pen = QPen(QColor(255, 255, 255, 120), 1.5 / s)
            pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRect(o.rect())
        self.draw_smart_guides(p, s)
        p.end()

    def draw_guides(self, p, s):
        z = self.app.zone()
        path = QPainterPath()
        path.addRect(QRectF(0, 0, W, H))
        path.addRect(z)
        path.setFillRule(Qt.OddEvenFill)
        p.fillPath(path, QColor(0, 0, 0, 90))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 45))
        for i in range(4):
            p.drawEllipse(QPointF(W - 68, H - 860 + i * 150), 34, 34)
        for i, wdt in enumerate((520, 760, 420)):
            p.drawRoundedRect(QRectF(40, H - 330 + i * 52, wdt, 26), 13, 13)
        p.drawEllipse(QPointF(70, H - 400), 32, 32)
        p.drawRoundedRect(QRectF(40, 90, 200, 40), 20, 20)
        pen = QPen(QColor(242, 179, 27, 210), max(2, 1.5 / s))
        pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRect(z)
        if self.app.show_grid.isChecked():
            pen = QPen(QColor("#5ED3F3"), max(2, 1.5 / s))
            pen.setStyle(Qt.DotLine)
            p.setPen(pen)
            p.drawLine(0, 240, W, 240)
            p.drawLine(0, H - 240, W, H - 240)

    def mousePressEvent(self, e):
        a = self.app
        if self.editor:
            self.finish_edit()
        pt = self.to_frame(e.position())
        o = a.selected()
        s, _, _ = self.geom()
        grab = 14 / s
        if o and not a.locked:
            r = o.rect()
            for c in (r.topLeft(), r.topRight(), r.bottomLeft(), r.bottomRight()):
                if abs(pt.x() - c.x()) < grab and abs(pt.y() - c.y()) < grab:
                    self.drag = ("resize", o)
                    return
        for i in range(len(a.layers) - 1, -1, -1):
            ov = a.layers[i]
            if ov.rect().contains(pt):
                a.select_layer(i)
                a.tabs.setCurrentIndex(1)
                self.drag = None if a.locked else ("move", ov, pt.x() - ov.x, pt.y() - ov.y)
                return
        a.select_layer(-1)
        if not a.locked and a.video_rect().contains(pt):
            self.drag = ("video", pt, a.dx.value(), a.dy.value())
        else:
            self.drag = None

    def mouseDoubleClickEvent(self, e):
        a = self.app
        pt = self.to_frame(e.position())
        for i in range(len(a.layers) - 1, -1, -1):
            o = a.layers[i]
            if o.kind == "text" and o.rect().contains(pt):
                a.select_layer(i)
                self.start_edit(o)
                return

    # ---------------------------------------------------------- text editing
    editor = None

    def start_edit(self, layer, select_all=False):
        self.finish_edit()
        self.drag = None
        layer.editing = True
        ed = CanvasTextEdit(self, layer)
        ed.textChanged.connect(self.on_edit_text)
        ed.done.connect(self.finish_edit)
        self.editor = ed
        ed.show()
        ed.setFocus()
        cur = ed.textCursor()
        if select_all:
            cur.select(cur.SelectionType.Document)
        else:
            cur.movePosition(cur.MoveOperation.End)
        ed.setTextCursor(cur)
        self.app.tabs.setCurrentIndex(1)
        self.app.status("Typing on the canvas. Press Esc or click outside to finish.")
        self.update()

    def on_edit_text(self):
        ed = self.editor
        if not ed:
            return
        a = self.app
        ed.layer.text = ed.toPlainText()
        if a.selected() is ed.layer:
            a.txt_edit.blockSignals(True)
            a.txt_edit.setPlainText(ed.layer.text)
            a.txt_edit.blockSignals(False)
            item = a.layer_list.item(a.sel)
            if item:
                item.setText(ed.layer.label())
        ed.place()
        a.changed()

    def finish_edit(self):
        ed = self.editor
        if not ed:
            return
        self.editor = None
        ed.layer.editing = False
        ed.hide()
        ed.deleteLater()
        self.app.layer_changed()
        self.app.status("")
        self.update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.editor:
            self.editor.style_from_layer()

    def mouseMoveEvent(self, e):
        a = self.app
        pt = self.to_frame(e.position())
        if not self.drag:
            over_layer = any(ov.rect().contains(pt) for ov in a.layers)
            if a.locked:
                self.setCursor(Qt.PointingHandCursor if over_layer else Qt.ArrowCursor)
            else:
                self.setCursor(Qt.SizeAllCursor if over_layer or a.video_rect().contains(pt) else Qt.ArrowCursor)
            return
        kind = self.drag[0]
        alt = bool(e.modifiers() & Qt.AltModifier)
        if kind == "move":
            _, ov, ox, oy = self.drag
            ov.x, ov.y = pt.x() - ox, pt.y() - oy
            a.clamp_layer(ov)
            r = ov.rect()
            dx, dy = self.snap(r, ov, alt)
            ov.move_to(r.left() + dx, r.top() + dy)
            a.clamp_layer(ov)
            a.layer_changed(sync_panel=False)
        elif kind == "resize":
            ov = self.drag[1]
            if ov.kind == "text":
                ov.w = max(80.0, 2 * abs(pt.x() - ov.x))
            else:
                aspect = ov.img.width() / max(1, ov.img.height())
                ov.w = max(30.0, 2 * max(abs(pt.x() - ov.x), abs(pt.y() - ov.y) * aspect))
            a.clamp_layer(ov)
            a.layer_changed()
        elif kind == "video":
            _, start, dx0, dy0 = self.drag
            ndx, ndy = dx0 + pt.x() - start.x(), dy0 + pt.y() - start.y()
            r = a.video_rect().translated(ndx - a.dx.value(), ndy - a.dy.value())
            sx, sy = self.snap(r, "video", alt)
            a.dx.setValue(int(round(ndx + sx)))
            a.dy.setValue(int(round(ndy + sy)))
            self.update()

    def mouseReleaseEvent(self, e):
        if self.drag and self.drag[0] == "move":
            self.app.layer_changed()
        self.drag = None
        self.guides = []
        self.update()


# ---------------------------------------------------------------- cover canvas
class CoverCanvas(QWidget):
    """Shows the whole 16:9 frame with a 9:16 window on top. Drag the window to
    frame the cover; scroll to zoom."""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setMouseTracking(True)
        self.drag = None
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def geom(self, src):
        m = 36
        s = min((self.width() - 2 * m) / src.width(), (self.height() - 2 * m) / src.height())
        ox = (self.width() - src.width() * s) / 2
        oy = (self.height() - src.height() * s) / 2
        return s, ox, oy

    def paintEvent(self, _):
        a = self.app
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor(C["bg"]))
        src = a.cover_source()
        if src is None:
            p.setPen(QColor(C["muted"]))
            f = QFont(DEFAULT_FONT)
            f.setPixelSize(15)
            p.setFont(f)
            p.drawText(self.rect(), Qt.AlignCenter, "Open a video to pick a cover frame")
            p.end()
            return
        s, ox, oy = self.geom(src)
        img_r = QRectF(ox, oy, src.width() * s, src.height() * s)
        p.drawImage(img_r, src)
        cr = a.cover_crop(src)
        r = QRectF(ox + cr.x() * s, oy + cr.y() * s, cr.width() * s, cr.height() * s)
        path = QPainterPath()
        path.addRect(img_r)
        path.addRect(r)
        path.setFillRule(Qt.OddEvenFill)
        p.fillPath(path, QColor(0, 0, 0, 165))
        # thirds
        p.setPen(QPen(QColor(255, 255, 255, 55), 1))
        for i in (1, 2):
            p.drawLine(QPointF(r.left() + r.width() * i / 3, r.top()), QPointF(r.left() + r.width() * i / 3, r.bottom()))
            p.drawLine(QPointF(r.left(), r.top() + r.height() * i / 3), QPointF(r.right(), r.top() + r.height() * i / 3))
        if a.cover_grid.isChecked():
            gh = r.width() * 4 / 3
            pen = QPen(QColor("#5ED3F3"), 1.5)
            pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            p.drawRect(QRectF(r.left(), r.center().y() - gh / 2, r.width(), gh))
        p.setPen(QPen(ACCENT, 2))
        p.setBrush(Qt.NoBrush)
        p.drawRect(r)
        f = QFont(DEFAULT_FONT)
        f.setPixelSize(11)
        f.setWeight(QFont.Bold)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 1.2)
        p.setFont(f)
        tag = QRectF(r.left(), r.top() - 24, 92, 20)
        if tag.top() < 4:
            tag.moveTop(r.top() + 6)
            tag.moveLeft(r.left() + 6)
        p.setPen(Qt.NoPen)
        p.setBrush(ACCENT)
        p.drawRoundedRect(tag, 5, 5)
        p.setPen(QColor(C["on_accent"]))
        p.drawText(tag, Qt.AlignCenter, "COVER 9:16")
        p.end()

    def _crop_widget_rect(self):
        src = self.app.cover_source()
        if src is None:
            return None, None, None
        s, ox, oy = self.geom(src)
        cr = self.app.cover_crop(src)
        return src, s, QRectF(ox + cr.x() * s, oy + cr.y() * s, cr.width() * s, cr.height() * s)

    def mousePressEvent(self, e):
        src, s, r = self._crop_widget_rect()
        if src is None:
            return
        pos = e.position()
        if not r.contains(pos):   # click outside: jump the window there
            self.app.cover_cx = min(1, max(0, (pos.x() - (self.width() - src.width() * s) / 2) / (src.width() * s)))
            self.app.cover_changed()
            src, s, r = self._crop_widget_rect()
        self.drag = (pos, self.app.cover_cx, self.app.cover_cy, src.width() * s, src.height() * s)

    def mouseMoveEvent(self, e):
        src, s, r = self._crop_widget_rect()
        if self.drag is None:
            self.setCursor(Qt.SizeAllCursor if r is not None and r.contains(e.position()) else Qt.PointingHandCursor)
            return
        start, cx, cy, sw, sh = self.drag
        d = e.position() - start
        self.app.cover_cx = cx + d.x() / sw
        self.app.cover_cy = cy + d.y() / sh
        self.app.cover_changed()

    def mouseReleaseEvent(self, e):
        self.drag = None

    def wheelEvent(self, e):
        step = 8 if e.angleDelta().y() > 0 else -8
        self.app.cover_zoom.setValue(self.app.cover_zoom.value() + step)


# ---------------------------------------------------------------- timeline
class Timeline(QWidget):
    trimChanged = Signal(float, float)
    seek = Signal(float)

    def __init__(self):
        super().__init__()
        self.setFixedHeight(40)
        self.duration = 0.0
        self.start = 0.0
        self.end = 0.0
        self.pos = 0.0
        self.mode = None
        self.trim_enabled = True
        self.setCursor(Qt.PointingHandCursor)

    def x_of(self, t):
        if self.duration <= 0:
            return 10
        return 10 + (self.width() - 20) * t / self.duration

    def t_of(self, x):
        if self.duration <= 0:
            return 0
        return max(0.0, min(self.duration, (x - 10) / (self.width() - 20) * self.duration))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        track = QRectF(10, 12, self.width() - 20, 16)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(C["raised"]))
        p.drawRoundedRect(track, 8, 8)
        if self.duration > 0:
            xs, xe = self.x_of(self.start), self.x_of(self.end)
            c = QColor(ACCENT)
            c.setAlpha(60)
            p.setBrush(c)
            p.drawRoundedRect(QRectF(xs, 12, xe - xs, 16), 6, 6)
            pen = QPen(ACCENT, 2)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(xs, 12, xe - xs, 16), 6, 6)
            p.setPen(Qt.NoPen)
            p.setBrush(ACCENT)
            for x in (xs, xe):
                p.drawRoundedRect(QRectF(x - 4, 7, 8, 26), 4, 4)
                p.setBrush(QColor(C["on_accent"]))
                p.drawRoundedRect(QRectF(x - 1, 15, 2, 10), 1, 1)
                p.setBrush(ACCENT)
            px = self.x_of(self.pos)
            p.setBrush(QColor("#FFFFFF"))
            p.drawRoundedRect(QRectF(px - 1.5, 3, 3, 34), 1.5, 1.5)
            p.drawEllipse(QPointF(px, 4), 4, 4)
        p.end()

    def mousePressEvent(self, e):
        if self.duration <= 0:
            return
        x = e.position().x()
        if self.trim_enabled and abs(x - self.x_of(self.start)) < 10:
            self.mode = "start"
        elif self.trim_enabled and abs(x - self.x_of(self.end)) < 10:
            self.mode = "end"
        else:
            self.mode = "seek"
        self.mouseMoveEvent(e)

    def mouseMoveEvent(self, e):
        if not self.mode:
            return
        t = self.t_of(e.position().x())
        if self.mode == "start":
            self.start = min(t, self.end - 0.1)
            self.trimChanged.emit(self.start, self.end)
            self.seek.emit(self.start)
        elif self.mode == "end":
            self.end = max(t, self.start + 0.1)
            self.trimChanged.emit(self.start, self.end)
            self.seek.emit(self.end)
        else:
            self.seek.emit(t)
        self.update()

    def mouseReleaseEvent(self, e):
        self.mode = None


# ---------------------------------------------------------------- main window
class ReelMaker(QMainWindow):
    def __init__(self):
        super().__init__()
        from core import __version__
        self.setWindowTitle(f"Reel Maker {__version__}")
        self.resize(1440, 920)
        self.setMinimumSize(1100, 700)
        self.settings = QSettings("ReelMaker", "ReelMaker")
        self.src_path = None
        self.frame = None
        self.src_ar = 16 / 9
        self.duration = 0.0
        self.layers = []
        self.sel = -1
        self.locked = False
        self.template_name = None
        self.bg_color = QColor("#1F6F5C")
        self.cover_frame = None
        self.cover_frame_t = 0.0
        self.cover_image = None
        self.cover_cx = 0.5
        self.cover_cy = 0.5
        self.proc = None
        self.cancelled = False
        self._syncing = False
        self.tmpdir = tempfile.mkdtemp(prefix="reelmaker_")
        self._priming = False
        self.fallback = False
        self.fb_pos = 0.0

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.sink = QVideoSink(self)
        self.player.setVideoOutput(self.sink)
        self.sink.videoFrameChanged.connect(self.on_frame)
        self.player.positionChanged.connect(self.on_position)
        self.player.durationChanged.connect(self.on_duration)
        self.player.mediaStatusChanged.connect(self.on_status)
        self.player.playbackStateChanged.connect(self.on_state)
        self.player.errorOccurred.connect(self.on_player_error)
        self.fb_timer = QTimer(self, singleShot=True, interval=120)
        self.fb_timer.timeout.connect(self.fb_show_frame)
        self.load_timer = QTimer(self, singleShot=True, interval=5000)
        self.load_timer.timeout.connect(self.check_loaded)
        self.cover_timer = QTimer(self, singleShot=True, interval=150)
        self.cover_timer.timeout.connect(self.render_cover_preview)

        self.build_ui()
        self.apply_preset()
        self.restore_user_assets()
        self.restore_last_template()
        self.update_lock_ui()
        self.setAcceptDrops(True)
        self.update_info = None
        self.update_busy = False
        import cloud
        self.cloud = cloud.GoogleDrive()
        self.cloud_busy = False
        if self.cloud.available and self.cloud.signed_in:
            QTimer.singleShot(3000, lambda: self.cloud_sync(quiet=True))
        QTimer.singleShot(2500, lambda: self.check_updates(quiet=True))

    # ============================================================ layout
    def build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.setCentralWidget(root)
        outer.addWidget(self.build_topbar())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        outer.addLayout(body, 1)

        center = QWidget()
        center.setObjectName("canvasArea")
        cl = QVBoxLayout(center)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        self.canvas = Canvas(self)
        self.cover_canvas = CoverCanvas(self)
        self.view_stack = QStackedWidget()
        self.view_stack.addWidget(self.canvas)
        self.view_stack.addWidget(self.cover_canvas)
        cl.addWidget(self.view_stack, 1)
        cl.addWidget(self.build_transport())
        body.addWidget(center, 1)

        side = QWidget()
        side.setObjectName("side")
        side.setAttribute(Qt.WA_StyledBackground, True)
        side.setFixedWidth(372)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self.page_frame(), "Frame")
        self.tabs.addTab(self.page_layers(), "Layers")
        self.tabs.addTab(self.page_cover(), "Cover")
        self.tabs.addTab(self.page_export(), "Export")
        self.tabs.tabBar().setExpanding(False)
        self.tabs.tabBar().setCursor(Qt.PointingHandCursor)
        self.tabs.currentChanged.connect(self.on_tab)
        sl.addWidget(self.tabs)
        body.addWidget(side)

        self.statusBar().showMessage("Open a 16:9 video to start.")
        sc = QShortcut(QKeySequence(Qt.Key_Space), self)
        sc.activated.connect(self.space_pressed)
        dl = QShortcut(QKeySequence(Qt.Key_Delete), self.canvas)
        dl.activated.connect(self.remove_layer)
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self.open_video)
        QShortcut(QKeySequence("Ctrl+E"), self, activated=self.export)

    def build_topbar(self):
        bar = QWidget()
        bar.setObjectName("topbar")
        bar.setAttribute(Qt.WA_StyledBackground, True)
        bar.setFixedHeight(58)
        l = QHBoxLayout(bar)
        l.setContentsMargins(16, 0, 16, 0)
        l.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(icon("logo", size=24).pixmap(24, 24))
        l.addWidget(logo)
        name = QLabel("Reel Maker")
        name.setObjectName("appName")
        l.addWidget(name)
        l.addSpacing(18)
        open_btn = QPushButton(" Open video")
        open_btn.setIcon(icon("folder", C["text"], 16))
        open_btn.setObjectName("ghost")
        open_btn.setCursor(Qt.PointingHandCursor)
        open_btn.clicked.connect(self.open_video)
        l.addWidget(open_btn)
        self.file_label = label("No video loaded", "muted")
        l.addWidget(self.file_label, 1)

        self.template_chip = QLabel()
        self.template_chip.setObjectName("chip")
        self.template_chip.setFixedHeight(24)
        self.template_chip.hide()
        l.addWidget(self.template_chip)
        self.lock_btn = QToolButton()
        self.lock_btn.setObjectName("ghost")
        self.lock_btn.setCheckable(True)
        self.lock_btn.setIconSize(QSize(18, 18))
        self.lock_btn.setCursor(Qt.PointingHandCursor)
        self.lock_btn.toggled.connect(self.set_locked)
        l.addWidget(self.lock_btn)

        self.update_btn = QToolButton()
        self.update_btn.setObjectName("ghost")
        self.update_btn.setIcon(icon("update", C["muted"], 18))
        self.update_btn.setIconSize(QSize(18, 18))
        self.update_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.update_btn.setCursor(Qt.PointingHandCursor)
        self.update_btn.setToolTip(f"Reel Maker {__version__}. Click to check for updates")
        self.update_btn.clicked.connect(self.on_update_clicked)
        l.addWidget(self.update_btn)

        self.tpl_btn = QToolButton()
        self.tpl_btn.setText(" Templates ")
        self.tpl_btn.setIcon(icon("template", C["text"], 16))
        self.tpl_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.tpl_btn.setObjectName("ghost")
        self.tpl_btn.setCursor(Qt.PointingHandCursor)
        self.tpl_menu = QMenu(self)
        self.tpl_menu.aboutToShow.connect(self.fill_template_menu)
        self.tpl_btn.setMenu(self.tpl_menu)
        self.tpl_btn.setPopupMode(QToolButton.InstantPopup)
        l.addWidget(self.tpl_btn)
        l.addSpacing(6)
        self.top_export = QPushButton("Export reel")
        self.top_export.setObjectName("primary")
        self.top_export.setCursor(Qt.PointingHandCursor)
        self.top_export.clicked.connect(self.export)
        l.addWidget(self.top_export)
        return bar

    def build_transport(self):
        w = QWidget()
        w.setObjectName("transport")
        w.setAttribute(Qt.WA_StyledBackground, True)
        v = QVBoxLayout(w)
        v.setContentsMargins(24, 4, 24, 16)
        v.setSpacing(6)
        top = QHBoxLayout()
        top.setSpacing(14)
        self.play_btn = QToolButton()
        self.play_btn.setObjectName("round")
        self.play_btn.setFixedSize(38, 38)
        self.play_btn.setIcon(icon("play", C["bg"], 18))
        self.play_btn.setIconSize(QSize(18, 18))
        self.play_btn.setCursor(Qt.PointingHandCursor)
        self.play_btn.setToolTip("Play / pause (Space)")
        self.play_btn.clicked.connect(self.toggle_play)
        top.addWidget(self.play_btn)
        self.time_label = QLabel("0:00.00")
        self.time_label.setObjectName("mono")
        self.time_label.setFixedWidth(64)
        top.addWidget(self.time_label)
        self.timeline = Timeline()
        self.timeline.trimChanged.connect(self.on_timeline_trim)
        self.timeline.seek.connect(self.seek_to)
        top.addWidget(self.timeline, 1)
        self.dur_label = QLabel("0:00.00")
        self.dur_label.setObjectName("mono")
        top.addWidget(self.dur_label)
        v.addLayout(top)

        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        bottom.addSpacing(52)
        self.t_start = QDoubleSpinBox()
        self.t_end = QDoubleSpinBox()
        for sb in (self.t_start, self.t_end):
            sb.setDecimals(2)
            sb.setMaximum(99999)
            sb.setSuffix(" s")
            sb.setButtonSymbols(QDoubleSpinBox.NoButtons)
            sb.setFixedWidth(84)
            sb.setAlignment(Qt.AlignRight)
            sb.valueChanged.connect(self.on_trim_spin)
        b1 = QPushButton("Set in")
        b1.setObjectName("ghost")
        b1.setToolTip("Start the reel at the playhead")
        b1.clicked.connect(lambda: self.t_start.setValue(self.current_time()))
        b2 = QPushButton("Set out")
        b2.setObjectName("ghost")
        b2.setToolTip("End the reel at the playhead")
        b2.clicked.connect(lambda: self.t_end.setValue(self.current_time()))
        self.trim_widgets = [self.t_start, self.t_end, b1, b2]
        bottom.addWidget(label("In", "muted"))
        bottom.addWidget(self.t_start)
        bottom.addWidget(b1)
        bottom.addSpacing(10)
        bottom.addWidget(label("Out", "muted"))
        bottom.addWidget(self.t_end)
        bottom.addWidget(b2)
        bottom.addSpacing(10)
        self.len_label = QLabel("Length 0:00.00")
        self.len_label.setObjectName("mono")
        bottom.addWidget(self.len_label)
        bottom.addStretch(1)
        self.mute = QCheckBox("Mute")
        self.mute.toggled.connect(lambda m: self.audio.setMuted(m))
        bottom.addWidget(self.mute)
        bottom.addSpacing(10)
        self.show_guides = QCheckBox("Guides")
        self.show_guides.setChecked(True)
        self.show_guides.toggled.connect(self.canvas.update)
        bottom.addWidget(self.show_guides)
        bottom.addSpacing(10)
        self.snap_on = QCheckBox("Snap")
        self.snap_on.setToolTip("Line things up with the centre, the safe zone and each other. Hold Alt to move freely.")
        self.snap_on.setChecked(self.settings.value("snap", True, type=bool))
        self.snap_on.toggled.connect(lambda v: self.settings.setValue("snap", v))
        bottom.addWidget(self.snap_on)
        v.addLayout(bottom)
        return w

    # ------------------------------------------------------------ Frame tab
    def page_frame(self):
        pg = SidePage()
        self.frame_banner = pg.add(self.make_lock_banner())
        pg.section("Background", first=True)
        self.bg_seg = Segmented(["Black", "White", "Blur", "Colour"])
        self.bg_seg.changed.connect(lambda *_: self.changed())
        self.bg_swatch = Swatch(self.bg_color, "Background colour")
        self.bg_swatch.colorChanged.connect(self.on_bg_color)
        pg.add(row(self.bg_seg, self.bg_swatch, stretch_index=0))

        pg.section("Safe zone")
        self.preset = QComboBox()
        self.preset.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.preset.setMinimumContentsLength(10)
        self.preset.addItems(PRESETS.keys())
        self.preset.currentTextChanged.connect(lambda *_: self.apply_preset())
        pg.add(self.preset)
        grid = QWidget()
        gl = QGridLayout(grid)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setHorizontalSpacing(10)
        gl.setVerticalSpacing(8)
        self.z = {}
        for i, (k, mx) in enumerate((("Top", 900), ("Bottom", 1000), ("Left", 500), ("Right", 500))):
            sb = spin(0, mx, 0, " px", 10)
            sb.valueChanged.connect(self.on_zone_spin)
            self.z[k] = sb
            lb = label(k, "muted")
            gl.addWidget(lb, i // 2, (i % 2) * 2)
            gl.addWidget(sb, i // 2, (i % 2) * 2 + 1)
        gl.setColumnStretch(1, 1)
        gl.setColumnStretch(3, 1)
        pg.add(grid)
        self.show_grid = QCheckBox("Show profile grid crop (3:4)")
        self.show_grid.toggled.connect(self.canvas.update)
        pg.add(self.show_grid)

        pg.section("Video")
        self.place_seg = Segmented(["Fit zone", "Fill width", "Centre"], checkable=False)
        self.place_seg.changed.connect(lambda i: (self.fit_zone, self.fill_width, self.center_video)[i]())
        pg.add(self.place_seg)
        self.scale = slider(40, 300, 100)
        self.scale_label = QLabel("100%")
        self.scale_label.setObjectName("mono")
        self.scale_label.setFixedWidth(44)
        self.scale_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.scale.valueChanged.connect(lambda v: (self.scale_label.setText(f"{v}%"), self.changed()))
        pg.add(field("Size", row(self.scale, self.scale_label, stretch_index=0)))
        self.dx = spin(-1080, 1080, 0, " px", 5)
        self.dy = spin(-1920, 1920, 0, " px", 5)
        self.radius = spin(0, 200, 0, " px", 4)
        for sb in (self.dx, self.dy, self.radius):
            sb.valueChanged.connect(lambda *_: self.changed())
        pg.add(field("Position", row(label("X", "faint"), self.dx, label("Y", "faint"), self.dy,
                                     stretch_index=None)))
        pg.add(field("Corners", self.radius))
        pg.add(label("Drag the video in the preview to move it.", "faint"))
        self.frame_geometry = [self.preset, *self.z.values(), self.place_seg, self.scale, self.dx,
                               self.dy, self.radius, self.bg_seg, self.bg_swatch]
        pg.finish()
        return pg

    def make_lock_banner(self):
        w = QLabel()
        w.setObjectName("banner")
        w.setWordWrap(True)
        w.hide()
        return w

    # ------------------------------------------------------------ Layers tab
    def page_layers(self):
        pg = SidePage()
        self.layers_banner = pg.add(self.make_lock_banner())
        pg.section("Layers", first=True)
        self.add_text_btn = QPushButton(" Text")
        self.add_text_btn.setIcon(icon("text", C["text"], 16))
        self.add_text_btn.clicked.connect(self.add_text)
        self.add_img_btn = QPushButton(" Logo or photo")
        self.add_img_btn.setIcon(icon("image", C["text"], 16))
        self.add_img_btn.clicked.connect(self.add_image_dialog)
        pg.add(row(self.add_text_btn, self.add_img_btn, None))
        self.layer_list = QListWidget()
        self.layer_list.setFixedHeight(116)
        self.layer_list.setIconSize(QSize(18, 18))
        self.layer_list.currentRowChanged.connect(self.select_layer)
        pg.add(self.layer_list)
        self.clamp = QCheckBox("Keep inside safe zone")
        self.clamp.setChecked(True)
        self.clamp.toggled.connect(lambda *_: self.after_zone())
        pg.add(self.clamp)

        self.stack = QStackedWidget()
        empty = label("Select a layer to edit it.", "faint")
        empty.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.stack.addWidget(empty)
        self.stack.addWidget(self.image_controls())
        self.stack.addWidget(self.text_controls())
        pg.add(self.stack)

        self.common_box = QWidget()
        cv = QVBoxLayout(self.common_box)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(10)
        self.ly_op = slider(5, 100, 100)
        self.ly_op.valueChanged.connect(self.on_layer_controls)
        cv.addWidget(field("Opacity", self.ly_op))
        self.snap_seg = Segmented(["↖", "↑", "↗", "●", "↙", "↓", "↘"], checkable=False)
        keys = ["tl", "tc", "tr", "c", "bl", "bc", "br"]
        names = ["Top left", "Top centre", "Top right", "Centre", "Bottom left", "Bottom centre", "Bottom right"]
        for b, n in zip(self.snap_seg.buttons, names):
            b.setToolTip(n + " of the safe zone")
        self.snap_seg.changed.connect(lambda i: self.place_layer(keys[i]))
        cv.addWidget(field("Snap to", self.snap_seg))
        self.dup_btn = QPushButton("Duplicate")
        self.dup_btn.clicked.connect(self.duplicate_layer)
        self.fwd_btn = QPushButton("Bring forward")
        self.fwd_btn.clicked.connect(self.bring_forward)
        self.rm_btn = QPushButton("Remove")
        self.rm_btn.clicked.connect(self.remove_layer)
        cv.addWidget(row(self.dup_btn, self.fwd_btn, self.rm_btn, None))
        self.common_box.setEnabled(False)
        pg.add(self.common_box)
        pg.finish()
        return pg

    def image_controls(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 4, 0, 0)
        v.setSpacing(10)
        v.addWidget(label("Image", "section"))
        self.img_size = spin(30, 2000, 240, " px", 10)
        self.img_size.valueChanged.connect(self.on_layer_controls)
        v.addWidget(field("Width", self.img_size))
        self.replace_btn = QPushButton("Replace image…")
        self.replace_btn.setToolTip("Swap the picture but keep its exact size and position")
        self.replace_btn.clicked.connect(self.replace_image)
        v.addWidget(row(self.replace_btn, None))
        return w

    def text_controls(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 4, 0, 0)
        v.setSpacing(10)
        v.addWidget(label("Text", "section"))
        self.txt_edit = QPlainTextEdit()
        self.txt_edit.setFixedHeight(132)
        self.txt_edit.setStyleSheet("QPlainTextEdit{font-size:15px;padding:10px 12px}")
        self.txt_edit.setPlaceholderText("Type here, or double-click the text on the preview")
        self.txt_edit.textChanged.connect(self.on_layer_controls)
        v.addWidget(self.txt_edit)
        self.emoji_btn = QToolButton()
        self.emoji_btn.setText(" Emoji")
        self.emoji_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.emoji_btn.setIconSize(QSize(18, 18))
        self.emoji_btn.setCursor(Qt.PointingHandCursor)
        self.emoji_btn.setToolTip("Insert an emoji at the cursor")
        self.emoji_btn.clicked.connect(self.open_emoji_picker)
        v.addWidget(row(self.emoji_btn, None))

        self.txt_font = QFontComboBox()
        self.txt_font.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.txt_font.setMinimumContentsLength(6)
        self.txt_font.setMinimumWidth(60)
        self.txt_font.setCurrentFont(QFont(DEFAULT_FONT))
        self.txt_font.currentFontChanged.connect(self.on_layer_controls)
        self.load_font_btn = QToolButton(text="+")
        self.load_font_btn.setToolTip("Load a .ttf / .otf font file")
        self.load_font_btn.setFixedWidth(34)
        self.load_font_btn.clicked.connect(self.load_font_file)
        v.addWidget(field("Font", row(self.txt_font, self.load_font_btn, stretch_index=0)))

        self.txt_weight = QComboBox()
        self.txt_weight.setMinimumWidth(60)
        self.txt_weight.addItems([n for n, _ in WEIGHTS])
        self.txt_weight.setCurrentIndex(3)
        self.txt_weight.currentIndexChanged.connect(self.on_layer_controls)
        self.txt_size = spin(12, 300, 64, " px")
        self.txt_size.setFixedWidth(78)
        self.txt_color = Swatch(QColor("white"), "Text colour")
        self.txt_color.colorChanged.connect(lambda c: self.set_layer_attr("color", c))
        self.txt_size.valueChanged.connect(self.on_layer_controls)
        v.addWidget(field("Style", row(self.txt_weight, self.txt_size, self.txt_color, stretch_index=0)))

        self.align_seg = Segmented(["Left", "Centre", "Right"])
        self.align_seg.setValue(1)
        self.align_seg.changed.connect(lambda *_: self.on_layer_controls())
        v.addWidget(field("Align", self.align_seg))

        self.txt_width = spin(80, 1080, 760, " px", 10)
        self.txt_width.setToolTip("The box keeps this width. Longer text moves to the next line.")
        self.txt_width.valueChanged.connect(self.on_layer_controls)
        self.txt_spacing = QDoubleSpinBox()
        self.txt_spacing.setRange(0.8, 2.5)
        self.txt_spacing.setSingleStep(0.05)
        self.txt_spacing.setValue(1.18)
        self.txt_spacing.setSuffix("×")
        self.txt_spacing.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.txt_spacing.setAlignment(Qt.AlignRight)
        self.txt_spacing.setToolTip("Line spacing")
        self.txt_spacing.valueChanged.connect(self.on_layer_controls)
        v.addWidget(field("Box width", row(self.txt_width, label("Lines", "faint"), self.txt_spacing,
                                           stretch_index=0)))

        self.txt_style = Segmented(["Box", "Highlight", "None"])
        self.txt_style.changed.connect(lambda *_: self.on_layer_controls())
        v.addWidget(field("Background", self.txt_style))
        self.txt_box_color = Swatch(QColor("black"), "Background colour")
        self.txt_box_color.colorChanged.connect(lambda c: self.set_layer_attr("box_color", c))
        self.txt_box_alpha = slider(0, 100, 55)
        self.txt_box_alpha.setToolTip("Background opacity")
        self.txt_box_alpha.valueChanged.connect(self.on_layer_controls)
        v.addWidget(field("", row(self.txt_box_color, self.txt_box_alpha, stretch_index=1)))
        self.txt_radius = spin(0, 200, 28, " px")
        self.txt_radius.valueChanged.connect(self.on_layer_controls)
        self.txt_pad = spin(0, 200, 30, " px")
        self.txt_pad.valueChanged.connect(self.on_layer_controls)
        v.addWidget(field("Corners", row(self.txt_radius, label("Padding", "faint"), self.txt_pad,
                                         stretch_index=0)))
        self.txt_shadow = QCheckBox("Shadow")
        self.txt_shadow.toggled.connect(self.on_layer_controls)
        v.addWidget(self.txt_shadow)

        self.emoji_label = label("Built-in emoji", "faint")
        eb = QToolButton()
        eb.setText("Change  ")
        eb.setIcon(icon("down", C["muted"], 14))
        eb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        eb.setLayoutDirection(Qt.RightToLeft)
        eb.setObjectName("ghost")
        eb.setPopupMode(QToolButton.InstantPopup)
        em = QMenu(eb)
        em.addAction("Use an emoji font file…", self.pick_emoji_font)
        em.addAction("Use a folder of emoji images…", self.pick_emoji_folder)
        em.addSeparator()
        em.addAction("Back to built-in emoji", self.clear_emoji_folder)
        eb.setMenu(em)
        v.addWidget(field("Emoji", row(self.emoji_label, None, eb)))
        self.text_style_controls = [self.txt_font, self.load_font_btn, self.txt_weight, self.txt_size,
                                    self.txt_color, self.align_seg, self.txt_width, self.txt_spacing,
                                    self.txt_style, self.txt_box_color, self.txt_box_alpha,
                                    self.txt_radius, self.txt_pad, self.txt_shadow]
        return w

    # ------------------------------------------------------------ Cover tab
    def page_cover(self):
        pg = SidePage()
        pg.section("Cover", first=True)
        pg.add(label("Scrub the timeline to choose a frame, then drag the 9:16 window over the "
                     "full 16:9 picture. Scroll to zoom.", "faint")).setWordWrap(True)
        self.cover_src_seg = Segmented(["Video frame", "Image"])
        self.cover_src_seg.changed.connect(self.on_cover_src)
        pg.add(self.cover_src_seg)
        self.cover_info = label("Frame at 0:00.00", "faint")
        pg.add(self.cover_info)
        self.cover_zoom = slider(100, 400, 100)
        self.cover_zoom_label = QLabel("100%")
        self.cover_zoom_label.setObjectName("mono")
        self.cover_zoom_label.setFixedWidth(44)
        self.cover_zoom_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.cover_zoom.valueChanged.connect(lambda v: (self.cover_zoom_label.setText(f"{v}%"),
                                                        self.cover_changed()))
        pg.add(field("Zoom", row(self.cover_zoom, self.cover_zoom_label, stretch_index=0)))
        cb = QPushButton("Centre")
        cb.clicked.connect(self.center_cover)
        self.cover_grid = QCheckBox("Show profile grid crop")
        self.cover_grid.setChecked(True)
        self.cover_grid.toggled.connect(lambda *_: self.cover_canvas.update())
        pg.add(row(cb, None, self.cover_grid))

        pg.section("Title")
        self.title = QLineEdit()
        self.title.setPlaceholderText("Optional cover title")
        self.title.textChanged.connect(lambda *_: self.cover_timer.start())
        pg.add(self.title)
        self.title_size = spin(30, 260, 110, " px")
        self.title_size.valueChanged.connect(lambda *_: self.cover_timer.start())
        self.title_color = Swatch(QColor("white"), "Title colour")
        self.title_color.colorChanged.connect(lambda *_: self.cover_timer.start())
        pg.add(field("Size", row(self.title_size, self.title_color, stretch_index=0)))
        self.title_y = slider(0, 100, 8)
        self.title_y.valueChanged.connect(lambda *_: self.cover_timer.start())
        pg.add(field("Position", self.title_y))
        self.cover_ovs = QCheckBox("Include text, logos and photos")
        self.cover_ovs.setChecked(False)
        self.cover_ovs.toggled.connect(lambda *_: self.cover_timer.start())
        pg.add(self.cover_ovs)

        pg.section("Preview")
        prev_row = QWidget()
        pr = QHBoxLayout(prev_row)
        pr.setContentsMargins(0, 0, 0, 0)
        pr.setSpacing(16)
        self.cover_prev = QLabel()
        self.cover_prev.setFixedSize(135, 240)
        pr.addWidget(self.cover_prev)
        side = QVBoxLayout()
        side.setSpacing(8)
        save = QPushButton("Save cover")
        save.setObjectName("primary")
        save.clicked.connect(self.save_cover)
        side.addWidget(save)
        side.addWidget(label("1080 × 1920 PNG.\nIn Instagram: Edit cover →\nAdd from camera roll.", "faint"))
        side.addStretch(1)
        pr.addLayout(side, 1)
        pg.add(prev_row)
        pg.finish()
        return pg

    # ------------------------------------------------------------ Export tab
    def page_export(self):
        pg = SidePage()
        pg.section("Output", first=True)
        pg.add(label("1080 × 1920 · H.264 MP4 · AAC audio", "faint"))
        self.quality = Segmented(["High", "Standard", "Small"])
        pg.add(field("Quality", self.quality))
        self.fps = Segmented(["30 fps", "60 fps", "Source"])
        pg.add(field("Frame rate", self.fps))
        self.save_cover_too = QCheckBox("Also save the cover next to the video")
        self.save_cover_too.setChecked(True)
        pg.add(self.save_cover_too)
        pg.lay.addSpacing(6)
        self.export_btn = QPushButton("Export reel")
        self.export_btn.setObjectName("primary")
        self.export_btn.setMinimumHeight(40)
        self.export_btn.clicked.connect(self.export)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_export)
        pg.add(row(self.export_btn, self.cancel_btn, stretch_index=0))
        self.progress = QProgressBar()
        self.progress.setValue(0)
        pg.add(self.progress)
        self.export_info = label("", "faint")
        self.export_info.setWordWrap(True)
        pg.add(self.export_info)
        self.play_out_btn = QPushButton(" Play video")
        self.play_out_btn.setIcon(icon("play", C["on_accent"], 16))
        self.play_out_btn.setObjectName("primary")
        self.play_out_btn.setCursor(Qt.PointingHandCursor)
        self.play_out_btn.setToolTip("Open the exported reel in your video player")
        self.play_out_btn.clicked.connect(self.play_export)
        self.show_out_btn = QPushButton(" Show in folder")
        self.show_out_btn.setIcon(icon("folder", C["text"], 16))
        self.show_out_btn.setCursor(Qt.PointingHandCursor)
        self.show_out_btn.clicked.connect(self.show_export_in_folder)
        self.done_row = row(self.play_out_btn, self.show_out_btn, None)
        self.done_row.hide()
        pg.add(self.done_row)
        pg.finish()
        return pg

    # ============================================================ helpers
    def status(self, msg):
        self.statusBar().showMessage(msg)

    def changed(self):
        ed = self.canvas.editor
        if ed and not ed.hasFocus():
            if ed.toPlainText() != ed.layer.text:
                ed.blockSignals(True)
                ed.setPlainText(ed.layer.text)
                ed.blockSignals(False)
        if ed:
            ed.style_from_layer()
        self.canvas.update()
        self.cover_timer.start()
        key = (EMOJI.font_family, EMOJI.folder)
        if getattr(self, "_emoji_style", None) != key:
            self._emoji_style = key
            self.refresh_emoji_button()

    def space_pressed(self):
        if isinstance(QApplication.focusWidget(), (QLineEdit, QPlainTextEdit, QAbstractSpinBoxType)):
            return
        self.toggle_play()

    def zone(self):
        t, b, l, r = (self.z[k].value() for k in ("Top", "Bottom", "Left", "Right"))
        return QRectF(l, t, max(10, W - l - r), max(10, H - t - b))

    def base_size(self, ar):
        z = self.zone()
        w = min(z.width(), z.height() * ar)
        return w, w / ar

    def video_rect(self, ar=None):
        ar = ar or self.src_ar
        z = self.zone()
        bw, bh = self.base_size(ar)
        k = self.scale.value() / 100
        w, h = bw * k, bh * k
        cx = z.center().x() + self.dx.value()
        cy = z.center().y() + self.dy.value()
        return QRectF(cx - w / 2, cy - h / 2, w, h)

    def bg_mode(self):
        return ("black", "white", "blur", "custom")[max(0, self.bg_seg.value())]

    def on_bg_color(self, c):
        self.bg_color = QColor(c)
        self.bg_seg.setValue(3)
        self.changed()

    def on_tab(self, i):
        self.view_stack.setCurrentIndex(1 if i == 2 else 0)
        self.timeline.trim_enabled = i != 2
        for w_ in self.trim_widgets:
            w_.setEnabled(i != 2)
        if i == 2:
            self.player.pause()
            if self.cover_src_seg.value() == 0 and self.frame is not None:
                self.grab_cover_frame()
            self.render_cover_preview()
        self.timeline.update()

    # ------------------------------------------------------------ fonts & emoji
    def restore_user_assets(self):
        for path in self.settings.value("fonts", [], type=list) or []:
            if os.path.exists(path):
                QFontDatabase.addApplicationFont(path)
        folder = self.settings.value("emoji_folder", "", type=str)
        if folder and os.path.isdir(folder) and EMOJI.load(folder):
            self.emoji_label.setText(f"Your folder ({len(EMOJI.index):,})")
        else:
            self.use_builtin_emoji()
        font = self.settings.value("emoji_font", "", type=str)
        if font and os.path.isfile(font) and EMOJI.load_font(font):
            self.emoji_label.setText(os.path.basename(font))

    def use_builtin_emoji(self):
        n = EMOJI.load(res_path("emoji"))
        self.emoji_label.setText(f"Built-in ({n:,})" if n else "System emoji")

    def load_font_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load font", "", "Fonts (*.ttf *.otf *.ttc)")
        if not path:
            return
        fid = QFontDatabase.addApplicationFont(path)
        fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
        if not fams:
            self.status("That font file couldn't be loaded.")
            return
        saved = self.settings.value("fonts", [], type=list) or []
        if path not in saved:
            saved.append(path)
            self.settings.setValue("fonts", saved)
        self.txt_font.setCurrentFont(QFont(fams[0]))
        self.status(f"Loaded font: {fams[0]}")

    def pick_emoji_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Folder of emoji images")
        if not folder:
            return
        EMOJI.clear_font()
        self.settings.setValue("emoji_font", "")
        n = EMOJI.load(folder)
        if not n:
            self.use_builtin_emoji()
            self.status("No emoji images found. Files must be named by code point, e.g. 1f600.png.")
            return
        self.settings.setValue("emoji_folder", folder)
        self.emoji_label.setText(f"Your folder ({n:,})")
        self.changed()

    def open_emoji_picker(self):
        if not hasattr(self, "emoji_picker"):
            self.emoji_picker = EmojiPicker(self)
            self.emoji_picker.picked.connect(self.insert_emoji)
        self.emoji_picker.open_at(self.emoji_btn)

    def insert_emoji(self, e):
        self.txt_edit.insertPlainText(e)
        self.txt_edit.ensureCursorVisible()

    def refresh_emoji_button(self):
        img = EMOJI.image("😀")
        if img is not None and hasattr(self, "emoji_btn"):
            self.emoji_btn.setIcon(QIcon(QPixmap.fromImage(img.scaled(48, 48, Qt.KeepAspectRatio,
                                                                      Qt.SmoothTransformation))))

    def pick_emoji_font(self):
        path, _ = QFileDialog.getOpenFileName(self, "Emoji font", "", "Fonts (*.ttf *.otf *.ttc)")
        if not path:
            return
        fam = EMOJI.load_font(path)
        if not fam or EMOJI.font_image("😀") is None:
            EMOJI.clear_font()
            QMessageBox.warning(self, "Emoji font", "That file doesn't look like a colour emoji font, "
                                "so Reel Maker will keep using the current emoji.")
            return
        self.settings.setValue("emoji_font", path)
        self.emoji_label.setText(os.path.basename(path))
        self.status(f"Using emoji from {os.path.basename(path)}. Anything it doesn't have falls back to the built-in set.")
        self.changed()

    def clear_emoji_folder(self):
        self.settings.setValue("emoji_folder", "")
        self.settings.setValue("emoji_font", "")
        EMOJI.clear_font()
        self.use_builtin_emoji()
        self.changed()

    # ------------------------------------------------------------ drawing
    def draw_background(self, p, src):
        mode = self.bg_mode()
        if mode == "blur" and src is not None and not src.isNull():
            p.fillRect(QRectF(0, 0, W, H), Qt.black)
            small = src.scaled(max(1, src.width() // 24), max(1, src.height() // 24),
                               Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            s = max(W / src.width(), H / src.height()) * 1.08
            w, h = src.width() * s, src.height() * s
            p.drawImage(QRectF((W - w) / 2, (H - h) / 2, w, h), small)
            p.fillRect(QRectF(0, 0, W, H), QColor(0, 0, 0, 90))
        else:
            c = {"black": QColor("black"), "white": QColor("white"),
                 "custom": self.bg_color}.get(mode, QColor("black"))
            p.fillRect(QRectF(0, 0, W, H), c)

    def draw_media(self, p, src, rect):
        p.save()
        r = self.radius.value()
        if r > 0:
            path = QPainterPath()
            path.addRoundedRect(rect, r, r)
            p.setClipPath(path, Qt.IntersectClip)
        p.drawImage(rect, src)
        p.restore()

    def draw_layers(self, p):
        for o in self.layers:
            o.draw(p)

    def compose(self, p, src, overlays=True):
        has = src is not None and not src.isNull()
        self.draw_background(p, src if has else None)
        if has:
            self.draw_media(p, src, self.video_rect(src.width() / src.height()))
        else:
            r = self.video_rect()
            p.fillRect(r, QColor(255, 255, 255, 18))
            p.setPen(QColor(C["muted"]))
            f = QFont(DEFAULT_FONT)
            f.setPixelSize(38)
            p.setFont(f)
            p.drawText(r, Qt.AlignCenter, "Your 16:9 video goes here")
        if overlays:
            self.draw_layers(p)

    # ============================================================ video
    def open_video(self):
        start = self.settings.value("last_dir", "", type=str)
        path, _ = QFileDialog.getOpenFileName(self, "Open video", start, VIDEO_EXT)
        if path:
            self.settings.setValue("last_dir", os.path.dirname(path))
            self.load_video(path)

    def load_video(self, path):
        self.src_path = path
        self.frame = None
        self.cover_frame = None
        self.fallback = False
        self.play_btn.setEnabled(True)
        self.file_label.setText(os.path.basename(path))
        self.file_label.setProperty("muted", False)
        self.file_label.style().unpolish(self.file_label)
        self.file_label.style().polish(self.file_label)
        self._priming = True
        self.audio.setMuted(True)
        self.player.setSource(QUrl.fromLocalFile(path))
        self.status("Loading video…")
        self.load_timer.start()

    def on_status(self, st):
        if st == QMediaPlayer.LoadedMedia and self._priming:
            self.player.play()
        elif st == QMediaPlayer.InvalidMedia:
            self.start_fallback()

    def on_player_error(self, _err, _msg):
        if self.src_path and self.frame is None:
            self.start_fallback()

    def check_loaded(self):
        if self.src_path and self.frame is None:
            self.start_fallback()

    def frame_arrived(self, img, first):
        self.frame = img
        self.src_ar = img.width() / img.height()
        if first or (self.tabs.currentIndex() == 2 and self.cover_src_seg.value() == 0):
            self.grab_cover_frame()
        self.canvas.update()
        self.cover_canvas.update()

    def grab_cover_frame(self):
        if self.frame is None:
            return
        self.cover_frame = self.frame.copy()
        self.cover_frame_t = self.current_time()
        if self.cover_src_seg.value() == 0:
            self.cover_info.setText(f"Frame at {fmt_time(self.cover_frame_t)}")
        self.cover_timer.start()

    def on_frame(self, vf):
        img = vf.toImage()
        if img.isNull():
            return
        first = False
        if self._priming:
            self._priming = False
            first = True
            self.load_timer.stop()
            self.player.pause()
            self.player.setPosition(0)
            self.audio.setMuted(self.mute.isChecked())
            ar = img.width() / img.height()
            note = "" if abs(ar - 16 / 9) < 0.05 else f" (this video is {ar:.2f}:1, not 16:9)"
            self.status(f"{img.width()} × {img.height()} loaded{note}. Space plays and pauses.")
        self.frame_arrived(img, first)

    # Preview without Windows' video player: show still frames using FFmpeg.
    def run_ffmpeg(self, args, timeout=20):
        import subprocess
        ff = find_ffmpeg()
        if not ff:
            return None
        kw = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
        try:
            return subprocess.run([ff, "-hide_banner"] + args, capture_output=True, timeout=timeout, **kw)
        except Exception:
            return None

    def start_fallback(self):
        if self.fallback or not self.src_path:
            return
        self.load_timer.stop()
        self.player.stop()
        self._priming = False
        r = self.run_ffmpeg(["-i", self.src_path])
        if r is None:
            self.status("Preview needs the video encoder. Press Export once to download it, then reopen the video.")
            return
        info = r.stderr.decode(errors="ignore")
        m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", info)
        if not m or "Video:" not in info:
            self.status("This file couldn't be opened. Try an MP4 or MOV.")
            return
        self.fallback = True
        self.play_btn.setEnabled(False)
        dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
        self.on_duration(int(dur * 1000))
        self.fb_pos = 0.0
        self.fb_show_frame(first=True)

    def fb_frame_at(self, t):
        r = self.run_ffmpeg(["-ss", f"{max(0.0, t):.3f}", "-i", self.src_path, "-frames:v", "1",
                             "-f", "image2pipe", "-vcodec", "png", "-"])
        if r is None or r.returncode != 0 or not r.stdout:
            return None
        img = QImage.fromData(r.stdout, "PNG")
        return None if img.isNull() else img

    def fb_show_frame(self, first=False):
        img = self.fb_frame_at(min(self.fb_pos, max(0.0, self.duration - 0.05)))
        if img is None:
            return
        if first:
            self.status(f"{img.width()} × {img.height()} loaded. Live playback isn't available on this PC, "
                        "so drag along the timeline to preview. Export works normally.")
        self.frame_arrived(img, first)

    def current_time(self):
        return self.fb_pos if self.fallback else self.player.position() / 1000

    def seek_to(self, t):
        if self.fallback:
            self.fb_pos = t
            self.set_playhead(t)
            self.fb_timer.start()
        else:
            self.player.setPosition(int(t * 1000))

    def set_playhead(self, t):
        self.timeline.pos = t
        self.timeline.update()
        self.time_label.setText(fmt_time(t))

    def on_duration(self, ms):
        self.duration = ms / 1000
        self.timeline.duration = self.duration
        for sb in (self.t_start, self.t_end):
            sb.blockSignals(True)
            sb.setMaximum(self.duration)
        self.t_start.setValue(0)
        self.t_end.setValue(self.duration)
        for sb in (self.t_start, self.t_end):
            sb.blockSignals(False)
        self.timeline.start, self.timeline.end = 0, self.duration
        self.dur_label.setText(fmt_time(self.duration))
        self.set_playhead(0)
        self.update_trim_labels()

    def on_position(self, ms):
        t = ms / 1000
        if (self.player.playbackState() == QMediaPlayer.PlayingState and not self._priming
                and self.tabs.currentIndex() != 2 and t >= self.t_end.value() - 0.02):
            self.player.setPosition(int(self.t_start.value() * 1000))
            return
        self.set_playhead(t)

    def on_state(self, st):
        playing = st == QMediaPlayer.PlayingState
        self.play_btn.setIcon(icon("pause" if playing else "play", C["bg"], 18))

    def toggle_play(self):
        if not self.src_path:
            self.open_video()
            return
        if self.fallback:
            return
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            t = self.player.position() / 1000
            if self.tabs.currentIndex() != 2 and (t < self.t_start.value() or t >= self.t_end.value() - 0.05):
                self.player.setPosition(int(self.t_start.value() * 1000))
            self.player.play()

    def on_timeline_trim(self, s, e):
        for sb, v in ((self.t_start, s), (self.t_end, e)):
            sb.blockSignals(True)
            sb.setValue(v)
            sb.blockSignals(False)
        self.update_trim_labels()

    def on_trim_spin(self):
        s, e = self.t_start.value(), self.t_end.value()
        if e <= s + 0.1:
            if self.sender() is self.t_start:
                s = max(0, e - 0.1)
                self.t_start.blockSignals(True)
                self.t_start.setValue(s)
                self.t_start.blockSignals(False)
            else:
                e = min(self.duration, s + 0.1)
                self.t_end.blockSignals(True)
                self.t_end.setValue(e)
                self.t_end.blockSignals(False)
        self.timeline.start, self.timeline.end = s, e
        self.timeline.update()
        self.update_trim_labels()

    def update_trim_labels(self):
        L = self.t_end.value() - self.t_start.value()
        self.len_label.setText(f"Length {fmt_time(L)}" + ("  · over 3:00" if L > 180 else ""))

    # ============================================================ zone & placement
    def apply_preset(self):
        vals = PRESETS.get(self.preset.currentText())
        if vals is None:
            return
        for k, v in zip(("Top", "Bottom", "Left", "Right"), vals):
            self.z[k].blockSignals(True)
            self.z[k].setValue(v)
            self.z[k].blockSignals(False)
        self.after_zone()

    def on_zone_spin(self):
        self.preset.blockSignals(True)
        self.preset.setCurrentText("Custom")
        self.preset.blockSignals(False)
        self.after_zone()

    def after_zone(self):
        for o in self.layers:
            self.clamp_layer(o)
        self.sync_layer_controls()
        self.changed()

    def fit_zone(self):
        self.scale.setValue(100)
        self.dx.setValue(0)
        self.dy.setValue(0)

    def fill_width(self):
        bw, _ = self.base_size(self.src_ar)
        self.scale.setValue(min(300, round(W / bw * 100 + 0.5)))
        self.dx.setValue(int(W / 2 - self.zone().center().x()))

    def center_video(self):
        z = self.zone()
        self.dx.setValue(int(W / 2 - z.center().x()))
        self.dy.setValue(int(H / 2 - z.center().y()))

    # ============================================================ layers
    def selected(self):
        return self.layers[self.sel] if 0 <= self.sel < len(self.layers) else None

    def add_image_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Add logo or photo", "", IMAGE_EXT)
        for p in paths:
            self.add_image(p)

    def load_image(self, path):
        img = QImage(path)
        if img.isNull():
            self.status(f"Couldn't read {os.path.basename(path)}")
            return None
        return img.convertToFormat(QImage.Format_ARGB32_Premultiplied)

    def add_image(self, path):
        if self.locked:
            return
        img = self.load_image(path)
        if img is None:
            return
        o = ImageLayer(img, path)
        o.w = min(self.zone().width() * 0.3, float(img.width()))
        self.layers.append(o)
        self.place_layer("tr" if sum(l.kind == "image" for l in self.layers) == 1 else "c", o)
        self.refresh_list()
        self.select_layer(len(self.layers) - 1)

    def replace_image(self):
        o = self.selected()
        if not o or o.kind != "image":
            return
        path, _ = QFileDialog.getOpenFileName(self, "Replace image", "", IMAGE_EXT)
        img = self.load_image(path) if path else None
        if img is None:
            return
        top_left = o.rect().topLeft()
        cx, cy = o.x, o.y
        o.img, o.name = img, os.path.basename(path)
        o.x, o.y = cx, cy   # keep centre and width; height follows the new picture
        self.refresh_list()
        self.changed()

    def add_text(self):
        if self.locked:
            return
        t = TextLayer()
        t.w = max(200.0, self.zone().width() - 80)
        self.layers.append(t)
        self.place_layer("bc", t)
        self.refresh_list()
        self.select_layer(len(self.layers) - 1)
        self.tabs.setCurrentIndex(1)
        self.view_stack.setCurrentIndex(0)
        self.canvas.start_edit(t, select_all=True)

    def refresh_list(self):
        self.layer_list.blockSignals(True)
        self.layer_list.clear()
        for o in self.layers:
            it = QListWidgetItem(o.label())
            if o.kind == "image":
                it.setIcon(QIcon(QPixmap.fromImage(o.img.scaled(36, 36, Qt.KeepAspectRatio, Qt.SmoothTransformation))))
            else:
                it.setIcon(icon("text", C["muted"], 18))
            self.layer_list.addItem(it)
        self.layer_list.setCurrentRow(self.sel)
        self.layer_list.blockSignals(False)

    def select_layer(self, i):
        self.sel = i
        self.layer_list.blockSignals(True)
        self.layer_list.setCurrentRow(i)
        self.layer_list.blockSignals(False)
        o = self.selected()
        self.common_box.setEnabled(o is not None and not self.locked)
        self.stack.setCurrentIndex(0 if o is None else (1 if o.kind == "image" else 2))
        self.sync_layer_controls()
        self.update_lock_ui()
        self.canvas.update()

    def sync_layer_controls(self):
        o = self.selected()
        if not o:
            return
        self._syncing = True
        try:
            self.ly_op.setValue(int(o.opacity * 100))
            if o.kind == "image":
                self.img_size.setValue(int(o.w))
            else:
                if self.txt_edit.toPlainText() != o.text:
                    self.txt_edit.setPlainText(o.text)
                self.txt_font.setCurrentFont(QFont(o.family))
                self.txt_weight.setCurrentIndex([w for _, w in WEIGHTS].index(o.weight))
                self.txt_size.setValue(o.size)
                self.txt_color.setColor(o.color)
                self.align_seg.setValue(("left", "center", "right").index(o.align))
                self.txt_shadow.setChecked(o.shadow)
                self.txt_width.setValue(int(o.w))
                self.txt_spacing.setValue(o.spacing)
                self.txt_style.setValue(("box", "highlight", "plain").index(o.style))
                self.txt_box_color.setColor(o.box_color)
                self.txt_box_alpha.setValue(int(o.box_alpha * 100))
                self.txt_radius.setValue(o.radius)
                self.txt_pad.setValue(o.pad)
                self.txt_pad.setEnabled(o.style == "box" and not self.locked)
        finally:
            self._syncing = False

    def on_layer_controls(self, *_):
        if self._syncing:
            return
        o = self.selected()
        if not o:
            return
        if o.kind == "text":
            o.text = self.txt_edit.toPlainText()
            item = self.layer_list.item(self.sel)
            if item:
                item.setText(o.label())
        if self.locked:          # only the words can change in a locked template
            self.changed()
            return
        o.opacity = self.ly_op.value() / 100
        if o.kind == "image":
            o.w = float(self.img_size.value())
        else:
            o.family = self.txt_font.currentFont().family()
            o.weight = WEIGHTS[self.txt_weight.currentIndex()][1]
            o.size = self.txt_size.value()
            o.align = ("left", "center", "right")[max(0, self.align_seg.value())]
            o.shadow = self.txt_shadow.isChecked()
            o.w = float(self.txt_width.value())
            o.spacing = self.txt_spacing.value()
            o.style = ("box", "highlight", "plain")[max(0, self.txt_style.value())]
            o.box_alpha = self.txt_box_alpha.value() / 100
            o.radius = self.txt_radius.value()
            o.pad = self.txt_pad.value()
            self.txt_pad.setEnabled(o.style == "box")
        self.clamp_layer(o)
        self.changed()

    def set_layer_attr(self, attr, value):
        o = self.selected()
        if o and o.kind == "text" and not self.locked:
            setattr(o, attr, QColor(value))
            self.changed()

    def layer_changed(self, sync_panel=True):
        if sync_panel:
            self.sync_layer_controls()
        self.changed()

    def clamp_layer(self, o):
        if not self.clamp.isChecked() or self.locked:
            return
        z = self.zone()
        if o.w > z.width():
            o.w = z.width()
        if o.kind == "image" and o.h > z.height():
            o.w = z.height() * o.img.width() / o.img.height()
        r = o.rect()
        left = min(max(r.left(), z.left()), z.right() - r.width())
        top = min(max(r.top(), z.top()), max(z.top(), z.bottom() - r.height()))
        o.move_to(left, top)

    def place_layer(self, key, o=None):
        o = o or self.selected()
        if not o or (self.locked and o is self.selected()):
            return
        z = self.zone()
        m = 24
        r = o.rect()
        xs = {"l": z.left() + m, "c": z.center().x() - r.width() / 2, "r": z.right() - m - r.width()}
        ys = {"t": z.top() + m, "c": z.center().y() - r.height() / 2, "b": z.bottom() - m - r.height()}
        if key == "c":
            o.move_to(xs["c"], ys["c"])
        else:
            o.move_to(xs[key[1]], ys[key[0]])
        self.clamp_layer(o)
        self.layer_changed()

    def duplicate_layer(self):
        o = self.selected()
        if not o or self.locked:
            return
        d = copy.copy(o)
        if o.kind == "text":
            d.color, d.box_color = QColor(o.color), QColor(o.box_color)
            d._cache_key = None
        d.y += 60
        self.clamp_layer(d)
        self.layers.append(d)
        self.refresh_list()
        self.select_layer(len(self.layers) - 1)
        self.changed()

    def remove_layer(self):
        if self.selected() is None or self.locked:
            return
        del self.layers[self.sel]
        self.sel = -1
        self.refresh_list()
        self.select_layer(-1)
        self.changed()

    def bring_forward(self):
        i = self.sel
        if not self.locked and 0 <= i < len(self.layers) - 1:
            self.layers[i], self.layers[i + 1] = self.layers[i + 1], self.layers[i]
            self.sel = i + 1
            self.refresh_list()
            self.changed()

    # ============================================================ templates
    def template_state(self, name):
        return {
            "version": 1, "name": name, "saved_at": __import__("time").time(),
            "background": {"mode": self.bg_mode(), "color": color_hex(self.bg_color)},
            "preset": self.preset.currentText(),
            "zone": [self.z[k].value() for k in ("Top", "Bottom", "Left", "Right")],
            "video": {"scale": self.scale.value(), "dx": self.dx.value(), "dy": self.dy.value(),
                      "radius": self.radius.value()},
            "clamp": self.clamp.isChecked(),
            "layers": [o.to_dict() for o in self.layers],
            "cover": {"title": self.title.text(), "title_size": self.title_size.value(),
                      "title_color": color_hex(self.title_color.color), "title_y": self.title_y.value(),
                      "include_layers": self.cover_ovs.isChecked(), "zoom": self.cover_zoom.value(),
                      "grid": self.cover_grid.isChecked()},
            "export": {"quality": self.quality.value(), "fps": self.fps.value(),
                       "save_cover": self.save_cover_too.isChecked()},
        }

    @staticmethod
    def template_path(name):
        safe = re.sub(r'[\\/:*?"<>|]+', "_", name).strip() or "template"
        return os.path.join(TEMPLATE_DIR, safe + ".json")

    def list_templates(self):
        out = []
        if os.path.isdir(TEMPLATE_DIR):
            for f in sorted(os.listdir(TEMPLATE_DIR), key=str.lower):
                if f.lower().endswith(".json"):
                    try:
                        with open(os.path.join(TEMPLATE_DIR, f), encoding="utf-8") as fh:
                            out.append((json.load(fh).get("name") or f[:-5], os.path.join(TEMPLATE_DIR, f)))
                    except Exception:
                        pass
        return out

    def fill_template_menu(self):
        m = self.tpl_menu
        m.clear()
        save = m.addAction("Save current layout as template…")
        save.triggered.connect(self.save_template)
        if self.template_name:
            upd = m.addAction(f"Update “{self.template_name}”")
            upd.triggered.connect(lambda: self.save_template(self.template_name))
        m.addSeparator()
        tpls = self.list_templates()
        if not tpls:
            a = m.addAction("No templates yet")
            a.setEnabled(False)
        for name, path in tpls:
            a = m.addAction(("✓  " if name == self.template_name else "     ") + name)
            a.triggered.connect(lambda _=False, p=path: self.apply_template_file(p))
        if tpls:
            m.addSeparator()
            dm = m.addMenu("Delete template")
            for name, path in tpls:
                a = dm.addAction(name)
                a.triggered.connect(lambda _=False, n=name, p=path: self.delete_template(n, p))
        if self.template_name:
            m.addSeparator()
            off = m.addAction("Stop using template")
            off.triggered.connect(self.detach_template)
        m.addSeparator()
        head = m.addAction("Google Drive")
        head.setEnabled(False)
        cl = self.cloud
        if not cl.available:
            a = m.addAction("Cloud sync isn't set up in this version")
            a.setEnabled(False)
        elif not cl.signed_in:
            m.addAction("Sign in with Google to sync templates…", self.cloud_sign_in)
        else:
            a = m.addAction(f"Signed in as {cl.email or 'your Google account'}")
            a.setEnabled(False)
            m.addAction("Syncing…" if self.cloud_busy else "Sync now", lambda: self.cloud_sync(quiet=False)) \
                .setEnabled(not self.cloud_busy)
            m.addAction("Sign out", self.cloud_sign_out)

    def save_template(self, name=None):
        if not name:
            name, ok = QInputDialog.getText(self, "Save template", "Template name:",
                                            text=self.template_name or "My reel layout")
            if not ok or not name.strip():
                return
            name = name.strip()
            path = self.template_path(name)
            if os.path.exists(path) and name != self.template_name:
                r = QMessageBox.question(self, "Save template", f"Replace the template “{name}”?")
                if r != QMessageBox.Yes:
                    return
        os.makedirs(TEMPLATE_DIR, exist_ok=True)
        path = self.template_path(name)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.template_state(name), f)
        except OSError as e:
            QMessageBox.warning(self, "Save template", f"Couldn't save the template:\n{e}")
            return
        self.template_name = name
        self.settings.setValue("last_template", path)
        self.lock_btn.setChecked(True)
        self.update_lock_ui()
        self.status(f"Saved template “{name}”. The layout is locked; unlock it to make changes.")
        self.cloud_sync(quiet=True)

    def apply_template_file(self, path, quiet=False):
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
        except Exception as e:
            if not quiet:
                QMessageBox.warning(self, "Templates", f"Couldn't open that template:\n{e}")
            return False
        self.set_locked(False)
        bg = d.get("background", {})
        self.bg_color = QColor(bg.get("color", "#FF1F6F5C"))
        self.bg_swatch.setColor(self.bg_color)
        self.bg_seg.setValue(("black", "white", "blur", "custom").index(bg.get("mode", "black")))
        self.preset.blockSignals(True)
        self.preset.setCurrentText(d.get("preset", "Custom"))
        self.preset.blockSignals(False)
        for k, v in zip(("Top", "Bottom", "Left", "Right"), d.get("zone", [250, 450, 120, 120])):
            self.z[k].blockSignals(True)
            self.z[k].setValue(v)
            self.z[k].blockSignals(False)
        vid = d.get("video", {})
        self.scale.setValue(vid.get("scale", 100))
        self.dx.setValue(vid.get("dx", 0))
        self.dy.setValue(vid.get("dy", 0))
        self.radius.setValue(vid.get("radius", 0))
        self.clamp.blockSignals(True)
        self.clamp.setChecked(d.get("clamp", True))
        self.clamp.blockSignals(False)
        self.layers = []
        for ld in d.get("layers", []):
            try:
                self.layers.append(ImageLayer.from_dict(ld) if ld.get("kind") == "image" else TextLayer.from_dict(ld))
            except Exception:
                pass
        cv = d.get("cover", {})
        self.title.setText(cv.get("title", ""))
        self.title_size.setValue(cv.get("title_size", 110))
        self.title_color.setColor(QColor(cv.get("title_color", "#FFFFFFFF")))
        self.title_y.setValue(cv.get("title_y", 8))
        self.cover_ovs.setChecked(cv.get("include_layers", False))
        self.cover_zoom.setValue(cv.get("zoom", 100))
        self.cover_grid.setChecked(cv.get("grid", True))
        ex = d.get("export", {})
        self.quality.setValue(ex.get("quality", 0))
        self.fps.setValue(ex.get("fps", 0))
        self.save_cover_too.setChecked(ex.get("save_cover", True))
        self.template_name = d.get("name") or os.path.splitext(os.path.basename(path))[0]
        self.settings.setValue("last_template", path)
        self.sel = -1
        self.refresh_list()
        self.select_layer(-1)
        self.lock_btn.setChecked(True)
        self.set_locked(True)
        self.changed()
        if not quiet:
            self.status(f"Using template “{self.template_name}”. Layout locked; you can still change the words.")
        return True

    def restore_last_template(self):
        path = self.settings.value("last_template", "", type=str)
        if path and os.path.exists(path):
            self.apply_template_file(path, quiet=True)
            self.status(f"Template “{self.template_name}” is ready. Open a video to start.")

    def delete_template(self, name, path):
        r = QMessageBox.question(self, "Delete template", f"Delete the template “{name}”? This can't be undone.")
        if r != QMessageBox.Yes:
            return
        try:
            os.remove(path)
        except OSError:
            pass
        if name == self.template_name:
            self.detach_template()
        self.status(f"Deleted template “{name}”.")
        self.cloud_sync(quiet=True)

    def detach_template(self):
        self.template_name = None
        self.settings.setValue("last_template", "")
        self.lock_btn.setChecked(False)
        self.update_lock_ui()

    def set_locked(self, on):
        self.locked = bool(on)
        if self.lock_btn.isChecked() != self.locked:
            self.lock_btn.blockSignals(True)
            self.lock_btn.setChecked(self.locked)
            self.lock_btn.blockSignals(False)
        self.update_lock_ui()
        self.canvas.update()

    def update_lock_ui(self):
        if not hasattr(self, "lock_btn"):
            return
        lk = self.locked
        self.lock_btn.setIcon(icon("lock" if lk else "unlock", C["accent"] if lk else C["muted"], 18))
        self.lock_btn.setToolTip("Layout locked. Click to unlock and edit." if lk
                                 else "Lock the layout so nothing can be moved")
        if self.template_name:
            self.template_chip.setText(self.template_name)
            self.template_chip.show()
        else:
            self.template_chip.hide()
        for w_ in self.frame_geometry:
            w_.setEnabled(not lk)
        self.add_text_btn.setEnabled(not lk)
        self.add_img_btn.setEnabled(not lk)
        self.clamp.setEnabled(not lk)
        self.common_box.setEnabled(self.selected() is not None and not lk)
        for w_ in self.text_style_controls:
            w_.setEnabled(not lk)
        self.img_size.setEnabled(not lk)
        if lk:
            o = self.selected()
            self.txt_pad.setEnabled(False)
            name = f"“{self.template_name}”" if self.template_name else "this layout"
            msg = (f"<b>Layout locked</b> · {name}<br>Positions, sizes and styles are fixed. "
                   "You can still change the words and swap images.")
            for b in (self.frame_banner, self.layers_banner):
                b.setText(msg)
                b.show()
        else:
            for b in (self.frame_banner, self.layers_banner):
                b.hide()
            o = self.selected()
            if o and o.kind == "text":
                self.txt_pad.setEnabled(o.style == "box")

    # ============================================================ cover
    def on_cover_src(self, i):
        if i == 1:
            if self.cover_image is None:
                path, _ = QFileDialog.getOpenFileName(self, "Cover image", "", IMAGE_EXT)
                img = QImage(path) if path else QImage()
                if img.isNull():
                    self.cover_src_seg.setValue(0)
                    return
                self.cover_image = img
                self.cover_info.setText(os.path.basename(path) + "  ·  click Image again to change")
                self.center_cover()
            else:
                path, _ = QFileDialog.getOpenFileName(self, "Cover image", "", IMAGE_EXT)
                img = QImage(path) if path else QImage()
                if not img.isNull():
                    self.cover_image = img
                    self.cover_info.setText(os.path.basename(path))
                    self.center_cover()
        else:
            self.grab_cover_frame()
            self.cover_info.setText(f"Frame at {fmt_time(self.cover_frame_t)}")
        self.cover_changed()

    def cover_source(self):
        if self.cover_src_seg.value() == 1 and self.cover_image is not None:
            return self.cover_image
        return self.cover_frame if self.cover_frame is not None else self.frame

    def cover_crop(self, src):
        """The 9:16 window in source pixels."""
        sw, sh = src.width(), src.height()
        z = self.cover_zoom.value() / 100
        h = min(sh, sw * 16 / 9) / z
        w = h * 9 / 16
        self.cover_cx = min(max(self.cover_cx, (w / 2) / sw), 1 - (w / 2) / sw)
        self.cover_cy = min(max(self.cover_cy, (h / 2) / sh), 1 - (h / 2) / sh)
        return QRectF(self.cover_cx * sw - w / 2, self.cover_cy * sh - h / 2, w, h)

    def center_cover(self):
        self.cover_cx = self.cover_cy = 0.5
        self.cover_changed()

    def cover_changed(self):
        self.cover_canvas.update()
        self.cover_timer.start()

    def render_cover(self):
        out = QImage(W, H, QImage.Format_ARGB32_Premultiplied)
        out.fill(Qt.black)
        p = QPainter(out)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        src = self.cover_source()
        if src is not None:
            p.drawImage(QRectF(0, 0, W, H), src, self.cover_crop(src))
        if self.cover_ovs.isChecked():
            self.draw_layers(p)
        text = self.title.text().strip()
        if text:
            z = self.zone()
            t = TextLayer(text)
            t.style, t.shadow, t.weight, t.size = "plain", True, 900, self.title_size.value()
            t.color = self.title_color.color
            t.w = z.width() - 40
            t.x = z.center().x()
            t.y = z.top() + (z.height() - t.h) * self.title_y.value() / 100
            t.draw(p)
        p.end()
        return out

    def render_cover_preview(self):
        img = self.render_cover().scaled(self.cover_prev.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        pm = QPixmap(img.size())
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, img.width(), img.height()), 10, 10)
        p.setClipPath(path)
        p.drawImage(0, 0, img)
        p.end()
        self.cover_prev.setPixmap(pm)

    def default_name(self, suffix, ext):
        base = os.path.splitext(self.src_path)[0] if self.src_path else os.path.join(os.path.expanduser("~"), "reel")
        return f"{base}{suffix}.{ext}"

    def save_cover(self):
        if self.cover_source() is None:
            self.status("Open a video first.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save cover", self.default_name("_cover", "png"), "PNG (*.png)")
        if not path:
            return
        if self.render_cover().save(path, "PNG"):
            self.status(f"Cover saved: {path}")
        else:
            self.status("Couldn't save the cover there. Pick another folder.")

    # ============================================================ export
    def build_ffmpeg_args(self, out_path):
        start = self.t_start.value()
        dur = max(0.1, self.t_end.value() - start)
        r = self.video_rect(self.src_ar)
        vw = max(2, int(round(r.width() / 2)) * 2)
        vh = max(2, int(round(r.height() / 2)) * 2)
        x, y = int(round(r.x())), int(round(r.y()))

        ov_png = os.path.join(self.tmpdir, "overlays.png")
        img = QImage(W, H, QImage.Format_ARGB32_Premultiplied)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        self.draw_layers(p)
        p.end()
        img.save(ov_png, "PNG")

        args = ["-y", "-hide_banner", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", self.src_path,
                "-loop", "1", "-t", f"{dur:.3f}", "-i", ov_png]
        fc = []
        mode = self.bg_mode()
        if mode == "blur":
            fc.append("[0:v]split=2[src][bgsrc]")
            fc.append(f"[bgsrc]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                      f"boxblur=luma_radius=40:luma_power=2,eq=brightness=-0.12,setsar=1[bg]")
            vin = "[src]"
        else:
            c = {"black": "000000", "white": "FFFFFF"}.get(mode, self.bg_color.name()[1:])
            fc.append(f"color=c=0x{c}:s={W}x{H}:r=30:d={dur:.3f}[bg]")
            vin = "[0:v]"
        fc.append(f"{vin}scale={vw}:{vh}:flags=lanczos,setsar=1[v]")
        vlabel = "[v]"
        rad = self.radius.value()
        if rad > 0:
            mask = os.path.join(self.tmpdir, "mask.png")
            m = QImage(vw, vh, QImage.Format_Grayscale8)
            m.fill(Qt.black)
            mp = QPainter(m)
            mp.setRenderHint(QPainter.Antialiasing)
            mp.setPen(Qt.NoPen)
            mp.setBrush(Qt.white)
            k = vw / max(1, r.width())
            mp.drawRoundedRect(QRectF(0, 0, vw, vh), rad * k, rad * k)
            mp.end()
            m.save(mask, "PNG")
            args += ["-loop", "1", "-t", f"{dur:.3f}", "-i", mask]
            fc.append("[v]format=rgba[va]")
            fc.append("[2:v]format=gray[m]")
            fc.append("[va][m]alphamerge[vr]")
            vlabel = "[vr]"
        fps = {0: "30", 1: "60"}.get(self.fps.value())
        tail = f",fps={fps}" if fps else ""
        fc.append(f"[bg]{vlabel}overlay=x={x}:y={y}:shortest=1[b1]")
        fc.append(f"[b1][1:v]overlay=0:0:shortest=1{tail},format=yuv420p[out]")
        crf = {0: "18", 1: "21", 2: "25"}.get(self.quality.value(), "18")
        args += ["-filter_complex", ";".join(fc), "-map", "[out]", "-map", "0:a?",
                 "-c:v", "libx264", "-preset", "medium", "-crf", crf, "-profile:v", "high",
                 "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                 "-t", f"{dur:.3f}", "-movflags", "+faststart",
                 "-progress", "pipe:1", "-nostats", out_path]
        return args, dur

    def export(self):
        if not self.src_path:
            self.status("Open a video first.")
            self.open_video()
            return
        if self.proc and self.proc.state() != QProcess.NotRunning:
            return
        out, _ = QFileDialog.getSaveFileName(self, "Export reel", self.default_name("_reel", "mp4"), "MP4 video (*.mp4)")
        if not out:
            return
        if not out.lower().endswith(".mp4"):
            out += ".mp4"
        if os.path.abspath(out) == os.path.abspath(self.src_path):
            QMessageBox.warning(self, "Reel Maker", "Pick a different file name so the original isn't overwritten.")
            return
        self.player.pause()
        self.tabs.setCurrentIndex(3)
        ff = find_ffmpeg()
        if not ff:
            ok = QMessageBox.question(
                self, "Reel Maker",
                "Reel Maker needs to download its video encoder (about 30 MB). "
                "This only happens once.\n\nDownload it now?")
            if ok == QMessageBox.Yes:
                self.fetch_ffmpeg_then(out)
            return
        self.start_export(out, ff)

    def fetch_ffmpeg_then(self, out):
        import threading
        state = {"done": 0, "total": 0, "error": None, "finished": False}
        threading.Thread(target=download_ffmpeg, args=(state,), daemon=True).start()
        self.set_exporting(True)
        self.export_info.setText("Downloading the video encoder…")
        timer = QTimer(self)

        def poll():
            if state["total"]:
                self.progress.setValue(int(100 * state["done"] / state["total"]))
            if not state["finished"]:
                return
            timer.stop()
            self.set_exporting(False)
            self.progress.setValue(0)
            ff = find_ffmpeg()
            if state["error"] or not ff:
                self.export_info.setText("Couldn't download the video encoder. Check your internet "
                                         f"connection and try again. {state['error'] or ''}")
                return
            self.start_export(out, ff)
        timer.timeout.connect(poll)
        timer.start(150)

    def set_exporting(self, on):
        self.export_btn.setEnabled(not on)
        self.top_export.setEnabled(not on)
        self.cancel_btn.setEnabled(on)

    def play_export(self):
        path = getattr(self, "last_export", None)
        if not path or not os.path.exists(path):
            self.status("The exported video isn't there any more.")
            self.done_row.hide()
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(path)):
            self.status("Windows has no video player set for MP4 files.")

    def show_export_in_folder(self):
        path = getattr(self, "last_export", None)
        if not path or not os.path.exists(path):
            self.status("The exported video isn't there any more.")
            return
        if sys.platform == "win32":
            import subprocess
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))

    def start_export(self, out, ff):
        args, self.export_dur = self.build_ffmpeg_args(out)
        self.export_out = out
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.SeparateChannels)
        self.proc.readyReadStandardOutput.connect(self.on_ffmpeg_progress)
        self.proc.finished.connect(self.on_ffmpeg_done)
        self.err_tail = ""
        self.proc.readyReadStandardError.connect(self.on_ffmpeg_err)
        if sys.platform == "win32":
            try:
                def no_window(a):
                    a.flags |= 0x08000000  # CREATE_NO_WINDOW
                self.proc.setCreateProcessArgumentsModifier(no_window)
            except Exception:
                pass
        self.proc.start(ff, args)
        self.set_exporting(True)
        self.progress.setValue(0)
        self.done_row.hide()
        self.export_info.setText(f"Exporting {os.path.basename(out)}…")
        self.status("Exporting…")

    def on_ffmpeg_err(self):
        self.err_tail = (self.err_tail + bytes(self.proc.readAllStandardError()).decode(errors="ignore"))[-3000:]

    def on_ffmpeg_progress(self):
        data = bytes(self.proc.readAllStandardOutput()).decode(errors="ignore")
        for m in re.finditer(r"out_time_(?:ms|us)=(\d+)", data):
            t = int(m.group(1)) / 1_000_000
            self.progress.setValue(min(100, int(100 * t / self.export_dur)))

    def cancel_export(self):
        if self.proc and self.proc.state() != QProcess.NotRunning:
            self.cancelled = True
            self.proc.kill()

    def on_ffmpeg_done(self, code, _status):
        self.set_exporting(False)
        if self.cancelled:
            self.cancelled = False
            self.progress.setValue(0)
            self.export_info.setText("Export cancelled.")
            try:
                os.remove(self.export_out)
            except OSError:
                pass
            return
        if code == 0:
            self.progress.setValue(100)
            extra = ""
            if self.save_cover_too.isChecked() and self.cover_source() is not None:
                cpath = os.path.splitext(self.export_out)[0] + "_cover.png"
                if self.render_cover().save(cpath, "PNG"):
                    extra = f"\nCover: {os.path.basename(cpath)}"
            self.export_info.setText(f"Saved {os.path.basename(self.export_out)}{extra}\n"
                                     f"in {os.path.dirname(self.export_out)}")
            self.status(f"Saved: {self.export_out}")
            self.last_export = self.export_out
            self.done_row.show()
            self.tabs.setCurrentIndex(3)
        else:
            self.export_info.setText("Export failed.")
            QMessageBox.warning(self, "Export failed", "FFmpeg stopped with an error:\n\n" + self.err_tail[-1200:])

    # ============================================================ cloud templates
    def cloud_sign_in(self):
        if self.cloud_busy:
            return
        self.cloud_busy = True
        self.status("Opening Google sign-in in your browser…")
        opener = lambda url: QTimer.singleShot(0, lambda: QDesktopServices.openUrl(QUrl(url)))
        def done(email, error):
            self.cloud_busy = False
            if error:
                QMessageBox.warning(self, "Google Drive", error)
                self.status("Google sign-in didn't finish.")
                return
            self.status(f"Signed in as {email or 'your Google account'}. Syncing templates…")
            self.cloud_sync(quiet=False)
        self.run_in_thread(lambda: self.cloud.sign_in(opener), done)

    def cloud_sign_out(self):
        r = QMessageBox.question(self, "Google Drive", "Sign out of Google Drive? Your templates stay on this PC "
                                 "and in your Drive.")
        if r == QMessageBox.Yes:
            self.cloud.sign_out()
            self.status("Signed out of Google Drive.")

    def cloud_sync(self, quiet=True):
        if self.cloud_busy or not (self.cloud.available and self.cloud.signed_in):
            return
        import cloud
        self.cloud_busy = True
        if not quiet:
            self.status("Syncing templates with Google Drive…")
        before = self.template_name and self.template_path(self.template_name)
        stamp = os.path.getmtime(before) if before and os.path.exists(before) else None

        def done(res, error):
            self.cloud_busy = False
            if error:
                self.status(f"Template sync failed: {error}")
                if not quiet:
                    QMessageBox.warning(self, "Google Drive", error)
                return
            # if the template in use was changed on another computer, reload it
            if before and self.locked:
                if os.path.exists(before) and os.path.getmtime(before) != stamp:
                    self.apply_template_file(before, quiet=True)
                elif not os.path.exists(before):
                    self.detach_template()
            n = res["total"]
            msg = f"Templates synced with Google Drive ({n} template{'s' if n != 1 else ''})"
            changes = [f"{res['downloaded']} downloaded" if res["downloaded"] else "",
                       f"{res['uploaded']} uploaded" if res["uploaded"] else "",
                       f"{res['removed']} removed" if res["removed"] else ""]
            changes = ", ".join(c for c in changes if c)
            self.status(msg + (f": {changes}." if changes else "."))
        self.run_in_thread(lambda: cloud.sync_templates(self.cloud), done)

    # ============================================================ updates
    def run_in_thread(self, fn, done):
        """Run fn() in a background thread, then call done(result, error) on the UI thread."""
        import threading
        box = {}

        def work():
            try:
                box["result"] = fn()
            except Exception as e:  # noqa
                box["error"] = str(e) or e.__class__.__name__
            box["finished"] = True
        threading.Thread(target=work, daemon=True).start()
        timer = QTimer(self)

        def poll():
            if box.get("finished"):
                timer.stop()
                done(box.get("result"), box.get("error"))
        timer.timeout.connect(poll)
        timer.start(100)

    def check_updates(self, quiet=False):
        if self.update_busy:
            return
        self.update_busy = True
        if not quiet:
            self.status("Checking for updates…")

        def done(info, error):
            self.update_busy = False
            if error:
                if not quiet:
                    QMessageBox.warning(self, "Updates", "Couldn't check for updates. "
                                        f"Check your internet connection and try again.\n\n{error}")
                    self.status("Couldn't check for updates.")
                return
            self.update_info = info
            self.show_update_state()
            if info and not quiet:
                self.offer_update(info)
            elif not quiet:
                self.status(f"You're up to date (Reel Maker {__version__}).")
                QMessageBox.information(self, "Updates", f"You have the latest version, Reel Maker {__version__}.")
        self.run_in_thread(check_for_update, done)

    def show_update_state(self):
        info = self.update_info
        if info:
            self.update_btn.setText(f" Update to {info['version']}")
            self.update_btn.setIcon(icon("update", C["accent"], 18))
            self.update_btn.setStyleSheet(f"QToolButton{{color:{C['accent']};font-weight:700;"
                                          "background:rgba(242,179,27,0.12);border:1px solid rgba(242,179,27,0.35)}")
            self.update_btn.setToolTip(f"Reel Maker {info['version']} is ready to install")
        else:
            self.update_btn.setText("")
            self.update_btn.setStyleSheet("")
            self.update_btn.setIcon(icon("update", C["muted"], 18))

    def on_update_clicked(self):
        if self.update_info:
            self.offer_update(self.update_info)
        else:
            self.check_updates(quiet=False)

    def offer_update(self, info):
        if self.proc and self.proc.state() != QProcess.NotRunning:
            QMessageBox.information(self, "Updates", "Wait for the export to finish, then update.")
            return
        notes = info.get("notes") or ""
        notes = re.sub(r"\*\*|__|`|#+ ", "", notes)
        if len(notes) > 700:
            notes = notes[:700].rsplit("\n", 1)[0] + "\n…"
        mb = QMessageBox(self)
        mb.setWindowTitle("Update available")
        mb.setIcon(QMessageBox.NoIcon)
        mb.setText(f"<b>Reel Maker {info['version']} is available</b><br>You have {__version__}.")
        size = f" ({info['size'] / 1048576:.0f} MB)" if info.get("size") else ""
        mb.setInformativeText(f"Update now{size}? Reel Maker will close, install the update and reopen. "
                              "Your templates are kept.")
        if notes:
            mb.setDetailedText(notes)
        go = mb.addButton("Update now", QMessageBox.AcceptRole)
        mb.addButton("Later", QMessageBox.RejectRole)
        mb.setDefaultButton(go)
        mb.exec()
        if mb.clickedButton() is go:
            self.download_and_install(info)

    def download_and_install(self, info):
        import threading
        state = {"done": 0, "total": 0, "error": None, "finished": False, "path": None}
        dlg = QProgressDialog(f"Downloading Reel Maker {info['version']}…", "Cancel", 0, 100, self)
        dlg.setWindowTitle("Updating")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setMinimumWidth(380)
        dlg.setValue(0)
        dlg.canceled.connect(lambda: None if state["finished"] else state.__setitem__("cancel", True))
        threading.Thread(target=download_update, args=(info, state), daemon=True).start()
        timer = QTimer(self)

        def poll():
            if state["total"]:
                dlg.setValue(min(99, int(100 * state["done"] / state["total"])))
                dlg.setLabelText(f"Downloading Reel Maker {info['version']}…  "
                                 f"{state['done'] / 1048576:.1f} of {state['total'] / 1048576:.1f} MB")
            if not state["finished"]:
                return
            timer.stop()
            dlg.canceled.disconnect()
            dlg.close()
            if state["path"]:
                self.launch_installer(state["path"])
                return
            if state.get("cancel"):
                self.status("Update cancelled.")
                return
            if state["error"] or not state["path"]:
                QMessageBox.warning(self, "Updates", f"The update couldn't be downloaded.\n\n{state['error'] or ''}")
        timer.timeout.connect(poll)
        timer.start(120)

    def launch_installer(self, path):
        import subprocess
        try:
            if sys.platform == "win32":
                # /S = silent install; the installer waits for this window to close,
                # replaces the files and reopens Reel Maker.
                subprocess.Popen([path, "/S"], close_fds=True,
                                 creationflags=0x00000008 | 0x00000200)  # DETACHED_PROCESS | NEW_PROCESS_GROUP
            else:
                subprocess.Popen([path])
        except Exception as e:  # noqa
            QMessageBox.warning(self, "Updates", f"Couldn't start the installer:\n{e}\n\nIt's saved at:\n{path}")
            return
        self.player.stop()
        QApplication.quit()

    # ============================================================ drag & drop / keys
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            path = url.toLocalFile()
            ext = os.path.splitext(path)[1].lower()
            if ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"):
                self.add_image(path)
            elif ext in (".ttf", ".otf"):
                fid = QFontDatabase.addApplicationFont(path)
                if fid >= 0:
                    self.status("Font loaded: " + ", ".join(QFontDatabase.applicationFontFamilies(fid)))
            elif ext == ".json":
                self.apply_template_file(path)
            elif ext:
                self.load_video(path)

    def keyPressEvent(self, e):
        o = self.selected()
        if o and not self.locked and e.key() in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            step = 20 if e.modifiers() & Qt.ShiftModifier else 2
            o.x += {Qt.Key_Left: -step, Qt.Key_Right: step}.get(e.key(), 0)
            o.y += {Qt.Key_Up: -step, Qt.Key_Down: step}.get(e.key(), 0)
            self.clamp_layer(o)
            self.layer_changed()
        else:
            super().keyPressEvent(e)


from PySide6.QtWidgets import QAbstractSpinBox as QAbstractSpinBoxType  # noqa: E402


def load_bundled_fonts():
    folder = res_path("fonts")
    if os.path.isdir(folder):
        for f in os.listdir(folder):
            if f.lower().endswith((".ttf", ".otf")):
                QFontDatabase.addApplicationFont(os.path.join(folder, f))


def install_error_log():
    """pythonw has no console, so save crashes to a log and show a message."""
    import traceback
    log_dir = APPDATA
    os.makedirs(log_dir, exist_ok=True)
    log = os.path.join(log_dir, "error.log")

    def hook(t, v, tb):
        text = "".join(traceback.format_exception(t, v, tb))
        try:
            with open(log, "a", encoding="utf-8") as f:
                f.write(text + "\n")
        except OSError:
            pass
        try:
            QMessageBox.critical(None, "Reel Maker", f"Something went wrong:\n{v}\n\nDetails saved to:\n{log}")
        except Exception:
            pass
    sys.excepthook = hook


def main():
    if sys.platform == "win32":
        # No explicit AppUserModelID: Windows identifies the app by ReelMaker.exe,
        # so a pinned taskbar icon shows the Reel Maker logo and relaunches correctly.
        import PySide6
        plug = os.path.join(os.path.dirname(PySide6.__file__), "plugins", "multimedia", "ffmpegmediaplugin.dll")
        if not os.path.exists(plug):
            os.environ.setdefault("QT_MEDIA_BACKEND", "windows")
    install_error_log()
    app = QApplication(sys.argv)
    app.setApplicationName("Reel Maker")
    app.setStyle("Fusion")
    load_bundled_fonts()
    app.setPalette(dark_palette())
    f = QFont(DEFAULT_FONT)
    f.setPixelSize(13)
    app.setFont(f)
    assets = build_style_assets(tempfile.mkdtemp(prefix="reelmaker_ui_"))
    app.setStyleSheet(stylesheet(assets))
    ico = res_path("icon.ico")
    if os.path.exists(ico):
        app.setWindowIcon(QIcon(ico))
    win = ReelMaker()
    win.show()
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        win.load_video(sys.argv[1])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
