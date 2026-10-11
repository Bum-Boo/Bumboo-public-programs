"""Small native painted surfaces; interactive controls remain standard Qt widgets."""

import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF, QTextLayout, QTextOption
from PySide6.QtWidgets import QApplication, QLabel, QMenu, QSizePolicy, QWidget

from .models import LABELS
from .skin import Skin
from .theme import PALETTES


def alpha(value, opacity):
    color = QColor(value)
    color.setAlphaF(max(0.0, min(1.0, opacity)))
    return color


def status_color(palette, state):
    return palette[
        {
            "working": "accent",
            "done": "success",
            "error": "error",
            "attention": "attention",
            "sleep": "muted",
        }.get(state, "audio")
    ]


def paint_spectrum(painter, rect, values, palette, gain=1.0):
    count = len(values)
    if not count:
        return
    slot = rect.width() / count
    width = max(2, slot * 0.48)
    painter.setPen(Qt.PenStyle.NoPen)
    for index, value in enumerate(values):
        height = max(2.0, min(1.0, value * gain) * rect.height())
        color = QColor(palette["audio"] if index < count * 0.62 else palette["accent"])
        color.setAlphaF(0.4 + 0.6 * min(1, value * 2 + 0.15))
        painter.setBrush(color)
        painter.drawRoundedRect(
            QRectF(
                rect.x() + index * slot + (slot - width) / 2, rect.bottom() - height, width, height
            ),
            width / 2,
            width / 2,
        )


class TaskTitle(QLabel):
    """Two complete lines with a visible ellipsis; tooltip/accessibility retain the title."""

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.full_title = " ".join(text.split())
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setToolTip(text)
        self.setAccessibleName(text)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        width = max(1, self.contentsRect().width())
        layout = QTextLayout(self.full_title, self.font())
        option = QTextOption()
        option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        layout.setTextOption(option)
        layout.beginLayout()
        line = layout.createLine()
        if line.isValid():
            line.setLineWidth(width)
            length = line.textLength()
        else:
            length = 0
        layout.endLayout()
        # Qt text offsets count UTF-16 code units, including two for emoji.
        encoded = self.full_title.encode("utf-16-le")
        first = encoded[: length * 2].decode("utf-16-le").rstrip()
        rest = encoded[length * 2 :].decode("utf-16-le").lstrip()
        second = self.fontMetrics().elidedText(rest, Qt.TextElideMode.ElideRight, width)
        self.setText(first + ("\n" + second if rest else ""))
        self.setFixedHeight(self.fontMetrics().lineSpacing() * (2 if rest else 1) + 2)


class Spectrum(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.values = [0.0] * 32
        self.palette_values = PALETTES["night"]
        self.gain = 1.0
        self.setMinimumHeight(65)
        self.setAccessibleName("현재 재생 소리의 스펙트럼")

    def set_frame(self, values):
        if values == self.values:
            return
        self.values = values
        if self.isVisible():
            self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint_spectrum(
            painter,
            QRectF(10, 8, self.width() - 20, self.height() - 18),
            self.values,
            self.palette_values,
            self.gain,
        )


class CharacterStage(QWidget):
    def __init__(self, parent=None, compact=False):
        super().__init__(parent)
        self.compact = compact
        self.state = "idle"
        self.skin = Skin()
        self.palette_values = PALETTES["night"]
        self.reduced = False
        self.values = [0.0] * 32
        self.gain = 1.0
        self.phase = 0.0
        self._sprite_key = None
        self._scaled_sprite = None
        self.setAccessibleName("동반자 상태")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.clock = QTimer(self)
        self.clock.timeout.connect(self.tick)
        self.clock.start(166)
        if not compact:
            self.setMinimumSize(340, 300)

    def tick(self):
        if self.isVisible() and not self.reduced:
            self.phase = time.monotonic()
            self.update()

    def configure(self, settings, skin=None):
        self.palette_values = PALETTES[settings["theme"]]
        self.reduced = settings["reduced_motion"]
        self.gain = settings["gain"]
        if self.reduced:
            self.clock.stop()
        else:
            self.clock.start(166 if self.state in ("idle", "sleep", "attention") else 83)
        if skin:
            self.skin = skin
        self.update()

    def set_state(self, state):
        if self.state == state:
            return
        self.state = state
        self.setAccessibleDescription(LABELS[state])
        self.setToolTip(LABELS[state])
        if not self.reduced:
            self.clock.setInterval(166 if state in ("idle", "sleep", "attention") else 83)
        self.update()

    def set_frame(self, values):
        if values == self.values:
            return
        self.values = values
        if self.isVisible():
            self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self.palette_values
        w, h = self.width(), self.height()
        top = 44 if self.compact else 8
        bottom = 42 if self.compact else 32
        size = min(w - (10 if self.compact else 24), h - top - bottom)
        cx = w / 2
        cy = top + size / 2
        bob = (
            0
            if self.reduced or self.state == "attention"
            else round(math.sin(self.phase * 1.5) * 2)
        )
        color = status_color(palette, self.state)

        # Concentric spell circles are quiet structure, not a full-window effect.
        energy = min(1.0, sum(self.values) / len(self.values) * self.gain)
        p.setPen(QPen(alpha(color, 0.13 + energy * 0.22), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        for factor in (0.79, 0.91):
            radius = size * factor / 2
            p.drawEllipse(QPointF(cx, cy + 10), radius, radius)
        p.setPen(QPen(alpha(color, 0.23), 1))
        p.drawEllipse(QRectF(cx - size * 0.32, top + size * 0.85, size * 0.64, size * 0.07))
        spin = 0 if self.reduced or self.state == "attention" else self.phase * 0.16
        for i in range(5):
            angle = i * math.tau / 5 + spin
            x, y = cx + math.cos(angle) * size * 0.435, cy + 10 + math.sin(angle) * size * 0.435
            p.setBrush(alpha(color, 0.50))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPolygon(
                QPolygonF(
                    [QPointF(x, y - 3), QPointF(x + 2, y), QPointF(x, y + 3), QPointF(x - 2, y)]
                )
            )

        frame = self.skin.frame(self.state)
        if frame:
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
            dpr = self.devicePixelRatioF()
            key = (frame.cacheKey(), round(size * dpr), dpr)
            if key != self._sprite_key:
                self._scaled_sprite = frame.scaled(
                    key[1],
                    key[1],
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.FastTransformation,
                )
                self._scaled_sprite.setDevicePixelRatio(dpr)
                self._sprite_key = key
            p.drawPixmap(QPointF(round(cx - size / 2), top + bob), self._scaled_sprite)
        else:
            self.paint_familiar(p, cx, cy + bob, size * 0.68, color)

        if self.compact:
            p.setPen(QPen(alpha(palette["line"], 0.85), 1))
            p.setBrush(QColor(palette["surface"]))
            p.drawRoundedRect(QRectF(8, 3, w - 16, 34), 12, 12)
            p.setPen(QColor(palette["text"]))
            font = QFont("Noto Sans CJK KR")
            font.setPixelSize(12)
            p.setFont(font)
            caption = p.fontMetrics().elidedText(
                LABELS[self.state], Qt.TextElideMode.ElideRight, w - 30
            )
            p.drawText(QRectF(14, 3, w - 28, 34), Qt.AlignmentFlag.AlignCenter, caption)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(palette["surface"]))
            p.drawRoundedRect(QRectF(22, h - 35, w - 44, 28), 12, 12)
            paint_spectrum(p, QRectF(32, h - 30, w - 64, 17), self.values, palette, self.gain)
        elif self.state in ("done", "attention", "error"):
            p.setPen(QColor(color))
            font = QFont("Noto Sans CJK KR")
            font.setPixelSize(13)
            p.setFont(font)
            p.drawText(QRectF(0, h - 29, w, 25), Qt.AlignmentFlag.AlignCenter, LABELS[self.state])
        p.end()

    def paint_familiar(self, p, cx, cy, size, color):
        # Original pixel-book familiar; entirely authored here, safe to redistribute.
        p.save()
        unit = max(2, round(size / 40))
        p.translate(round(cx - 18 * unit), round(cy - 17 * unit))
        p.scale(unit, unit)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.setPen(Qt.PenStyle.NoPen)
        pixels = [
            (6, 5, 25, 27, "#11111B"),
            (4, 7, 3, 21, "#11111B"),
            (7, 4, 22, 2, "#11111B"),
            (7, 6, 22, 23, "#454060"),
            (8, 7, 3, 22, "#675879"),
            (12, 7, 16, 19, "#807096"),
            (13, 8, 14, 17, "#57506E"),
            (6, 29, 25, 3, "#A999AB"),
            (8, 29, 22, 1, "#F5EBDD"),
            (8, 31, 22, 1, "#C2AB92"),
            (7, 6, 22, 1, "#D9BE88"),
            (28, 7, 1, 19, "#D9BE88"),
            (12, 25, 16, 1, "#D9BE88"),
            (12, 8, 1, 17, "#D9BE88"),
            (8, 4, 2, 3, "#F9E2AF"),
            (27, 4, 2, 3, "#F9E2AF"),
            (19, 10, 2, 3, color),
            (17, 12, 6, 2, color),
            (19, 14, 2, 3, color),
            (15, 20, 2, 2, "#CDD6F4"),
            (23, 20, 2, 2, "#CDD6F4"),
            (18, 23, 4, 1, "#F5C2E7"),
            (24, 31, 3, 5, "#CBA6F7"),
            (1, 15, 3, 2, "#B4BEFE"),
            (0, 12, 2, 3, "#CDD6F4"),
            (31, 15, 3, 2, "#B4BEFE"),
            (33, 12, 2, 3, "#CDD6F4"),
        ]
        for x, y, w, h, c in pixels:
            if self.state == "sleep" and y == 20:
                h = 1
            p.fillRect(x, y, w, h, QColor(c))
        p.restore()


class Companion(CharacterStage):
    activated = Signal()
    moved = Signal(list)
    hideRequested = Signal()
    quietRequested = Signal()
    restRequested = Signal()

    def __init__(self):
        super().__init__(compact=True)
        self.setWindowTitle("Grimoire Companion")
        self.setObjectName("companion")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("#companion {background: transparent;}")
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.press_global = None
        self.start_pos = None
        self.dragged = False
        self.resize(260, 325)

    def configure(self, settings, skin=None):
        visible = self.isVisible()
        flags = Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
        if settings["always_on_top"]:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        if self.windowFlags() != flags:
            self.setWindowFlags(flags)
            if visible:
                self.show()
        self.resize(round(260 * settings["scale"]), round(325 * settings["scale"]))
        super().configure(settings, skin)
        self.clamp_position()

    def place(self, position=None):
        area = QApplication.primaryScreen().availableGeometry()
        if position:
            self.move(*position)
        else:
            self.move(area.right() - self.width() - 28, area.bottom() - self.height() - 24)
        self.clamp_position()

    def clamp_position(self):
        center = self.frameGeometry().center()
        screen = QApplication.screenAt(center) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        x = max(area.left(), min(self.x(), area.right() - self.width() + 1))
        y = max(area.top(), min(self.y(), area.bottom() - self.height() + 1))
        self.move(x, y)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.press_global = event.globalPosition().toPoint()
            self.start_pos = self.pos()
            self.dragged = False
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self.press_global is not None and event.buttons() & Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self.press_global
            if delta.manhattanLength() > QApplication.startDragDistance():
                self.dragged = True
            if self.dragged:
                self.move(self.start_pos + delta)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.press_global is not None:
            if self.dragged:
                self.clamp_position()
                self.moved.emit([self.x(), self.y()])
            else:
                self.activated.emit()
            self.press_global = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.addAction("여정 열기", self.activated.emit)
        menu.addAction("조용히 / 알림 받기", self.quietRequested.emit)
        menu.addAction("쉬기 / 돌아오기", self.restRequested.emit)
        menu.addSeparator()
        menu.addAction("동반자 숨기기", self.hideRequested.emit)
        menu.exec(event.globalPos())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hideRequested.emit()
        else:
            super().keyPressEvent(event)
