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
from PySide6.QtGui import (QImage, QPainter, QColor, QPen, QFont, QPainterPath, QPixmap, QIcon, QLinearGradient,
                           QKeySequence, QShortcut, QFontMetricsF, QFontDatabase, QPalette, QAction)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QGridLayout, QPushButton,
    QButtonGroup, QComboBox, QSpinBox, QDoubleSpinBox, QSlider, QCheckBox, QLabel, QListWidget,
    QListWidgetItem, QFileDialog, QColorDialog, QLineEdit, QProgressBar, QScrollArea, QMessageBox,
    QSizePolicy, QFrame, QToolButton, QPlainTextEdit, QFontComboBox, QStackedWidget, QTabWidget,
    QMenu, QInputDialog)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoSink

from core import (W, H, ACCENT, DEFAULT_FONT, PRESETS, VIDEO_EXT, IMAGE_EXT, WEIGHTS, APPDATA,
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
        self.setFocusPolicy(Qt.ClickFocus)

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
        o = self.app.selected()
        if o and o.kind == "text":
            self.app.tabs.setCurrentIndex(1)
            self.app.txt_edit.setFocus()
            self.app.txt_edit.selectAll()

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
        if kind == "move":
            _, ov, ox, oy = self.drag
            ov.x, ov.y = pt.x() - ox, pt.y() - oy
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
            a.dx.setValue(int(dx0 + pt.x() - start.x()))
            a.dy.setValue(int(dy0 + pt.y() - start.y()))

    def mouseReleaseEvent(self, e):
        if self.drag and self.drag[0] == "move":
            self.app.layer_changed()
        self.drag = None


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
        self.txt_edit.setFixedHeight(84)
        self.txt_edit.setPlaceholderText("Type here. Win + . opens the emoji picker")
        self.txt_edit.textChanged.connect(self.on_layer_controls)
        v.addWidget(self.txt_edit)

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
        eb = QPushButton("Change…")
        eb.setObjectName("ghost")
        eb.setToolTip("Use a folder of emoji PNGs named by code point, e.g. 1f600.png")
        eb.clicked.connect(self.pick_emoji_folder)
        ec = QPushButton("Reset")
        ec.setObjectName("ghost")
        ec.clicked.connect(self.clear_emoji_folder)
        v.addWidget(field("Emoji", row(self.emoji_label, None, eb, ec)))
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
        pg.finish()
        return pg

    # ============================================================ helpers
    def status(self, msg):
        self.statusBar().showMessage(msg)

    def changed(self):
        self.canvas.update()
        self.cover_timer.start()

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
        n = EMOJI.load(folder)
        if not n:
            self.use_builtin_emoji()
            self.status("No emoji images found. Files must be named by code point, e.g. 1f600.png.")
            return
        self.settings.setValue("emoji_folder", folder)
        self.emoji_label.setText(f"Your folder ({n:,})")
        self.changed()

    def clear_emoji_folder(self):
        self.settings.setValue("emoji_folder", "")
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
        self.txt_edit.setFocus()
        self.txt_edit.selectAll()

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
            "version": 1, "name": name,
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
        else:
            self.export_info.setText("Export failed.")
            QMessageBox.warning(self, "Export failed", "FFmpeg stopped with an error:\n\n" + self.err_tail[-1200:])

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
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ReelMaker.App")
        except Exception:
            pass
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
