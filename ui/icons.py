"""
ui/icons.py — Ícones vetoriais premium (champagne & ouro).
Sem emoji nem cores saturadas; traço fino dourado.
"""
from __future__ import annotations
import math
import os
from PyQt6.QtCore import Qt, QRectF, pyqtSignal, QPointF
from PyQt6.QtGui import QPainter, QPen, QColor, QPainterPath, QFont, QPixmap
from PyQt6.QtWidgets import QWidget
from ui.theme import C_GOLD, C_GOLD_BRIGHT, C_GOLD_DEEP, C_TEXT, C_TEXT_MID, FONT

_NIGEL_ICON_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets', 'nigel.png')
_nigel_pixmap: QPixmap | None = None

def _get_nigel_pixmap() -> QPixmap | None:
    global _nigel_pixmap
    if _nigel_pixmap is None and os.path.exists(_NIGEL_ICON_PATH):
        _nigel_pixmap = QPixmap(_NIGEL_ICON_PATH)
    return _nigel_pixmap

def _pen(color: QColor, w: float = 1.45) -> QPen:
    return QPen(color, w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)

def paint_icon(p: QPainter, rect: QRectF, name: str, color: QColor | None = None, stroke: float = 1.45):
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    c = color or C_GOLD_BRIGHT
    pen = _pen(c, stroke)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    pad = min(rect.width(), rect.height()) * 0.16
    r = QRectF(rect.x() + pad, rect.y() + pad, rect.width() - 2 * pad, rect.height() - 2 * pad)
    cx, cy = r.center().x(), r.center().y()
    w, h = r.width(), r.height()
    if name == 'close':
        m = min(w, h) * 0.28
        p.drawLine(QPointF(cx - m, cy - m), QPointF(cx + m, cy + m))
        p.drawLine(QPointF(cx + m, cy - m), QPointF(cx - m, cy + m))
    elif name == 'check':
        path = QPainterPath()
        path.moveTo(cx - w * 0.28, cy)
        path.lineTo(cx - w * 0.04, cy + h * 0.26)
        path.lineTo(cx + w * 0.32, cy - h * 0.24)
        p.drawPath(path)
    elif name == 'refresh':
        arc = QRectF(cx - w * 0.34, cy - h * 0.34, w * 0.68, h * 0.68)
        p.drawArc(arc, 880, 4320)
        tip = QPainterPath()
        tip.moveTo(cx + w * 0.22, cy - h * 0.38)
        tip.lineTo(cx + w * 0.34, cy - h * 0.12)
        tip.lineTo(cx + w * 0.08, cy - h * 0.08)
        p.drawPath(tip)
    elif name == 'settings':
        gear_r = min(w, h) * 0.22
        p.drawEllipse(QPointF(cx, cy), gear_r, gear_r)
        for i in range(8):
            a = i * math.pi / 4
            p.drawLine(QPointF(cx + math.cos(a) * gear_r * 1.15, cy + math.sin(a) * gear_r * 1.15), QPointF(cx + math.cos(a) * gear_r * 1.65, cy + math.sin(a) * gear_r * 1.65))
    elif name == 'brain':
        head = QRectF(cx - w * 0.32, cy - h * 0.18, w * 0.64, h * 0.48)
        p.drawRoundedRect(head, 3, 3)
        p.drawLine(QPointF(cx, cy - h * 0.18), QPointF(cx, cy - h * 0.35))
        p.setBrush(c)
        p.drawEllipse(QPointF(cx, cy - h * 0.38), 1.8, 1.8)
        p.drawEllipse(QPointF(cx - w * 0.12, cy + h * 0.02), 1.2, 1.2)
        p.drawEllipse(QPointF(cx + w * 0.12, cy + h * 0.02), 1.2, 1.2)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(cx - w * 0.1, cy + h * 0.16), QPointF(cx + w * 0.1, cy + h * 0.16))
    elif name == 'agenda':
        cal = QRectF(cx - w * 0.34, cy - h * 0.28, w * 0.68, h * 0.62)
        p.drawRoundedRect(cal, 2, 2)
        p.drawLine(QPointF(cal.left(), cal.top() + h * 0.18), QPointF(cal.right(), cal.top() + h * 0.18))
        p.drawLine(QPointF(cx - w * 0.12, cal.top() - h * 0.06), QPointF(cx - w * 0.12, cal.top() + h * 0.04))
        p.drawLine(QPointF(cx + w * 0.12, cal.top() - h * 0.06), QPointF(cx + w * 0.12, cal.top() + h * 0.04))
    elif name == 'memory':
        for i, dy in enumerate((0.0, h * 0.12, h * 0.24)):
            layer = QRectF(cx - w * 0.34, cy - h * 0.22 + dy, w * 0.68, h * 0.38)
            p.drawRoundedRect(layer, 3, 3)
    elif name == 'graph':
        pts = [(cx - w * 0.28, cy - h * 0.12), (cx + w * 0.26, cy - h * 0.22), (cx + w * 0.18, cy + h * 0.24), (cx - w * 0.22, cy + h * 0.18)]
        for i in range(len(pts)):
            p.drawLine(QPointF(*pts[i]), QPointF(*pts[(i + 1) % len(pts)]))
        p.setBrush(c)
        for px, py in pts:
            p.drawEllipse(QPointF(px, py), 2.0, 2.0)
    elif name == 'fit':
        p.drawEllipse(QPointF(cx, cy), w * 0.32, h * 0.32)
        p.drawLine(QPointF(cx - w * 0.44, cy), QPointF(cx - w * 0.14, cy))
        p.drawLine(QPointF(cx + w * 0.14, cy), QPointF(cx + w * 0.44, cy))
        p.drawLine(QPointF(cx, cy - h * 0.44), QPointF(cx, cy - h * 0.14))
        p.drawLine(QPointF(cx, cy + h * 0.14), QPointF(cx, cy + h * 0.44))
    elif name == 'add':
        p.drawLine(QPointF(cx - w * 0.28, cy), QPointF(cx + w * 0.28, cy))
        p.drawLine(QPointF(cx, cy - h * 0.28), QPointF(cx, cy + h * 0.28))
    elif name == 'clock':
        p.drawEllipse(QPointF(cx, cy), w * 0.34, h * 0.34)
        p.drawLine(QPointF(cx, cy), QPointF(cx, cy - h * 0.18))
        p.drawLine(QPointF(cx, cy), QPointF(cx + w * 0.14, cy + h * 0.06))
    elif name == 'bell':
        path = QPainterPath()
        path.moveTo(cx - w * 0.22, cy + h * 0.08)
        path.quadTo(cx - w * 0.22, cy - h * 0.28, cx, cy - h * 0.32)
        path.quadTo(cx + w * 0.22, cy - h * 0.28, cx + w * 0.22, cy + h * 0.08)
        p.drawPath(path)
        p.drawLine(QPointF(cx - w * 0.26, cy + h * 0.08), QPointF(cx + w * 0.26, cy + h * 0.08))
        p.drawLine(QPointF(cx - w * 0.08, cy + h * 0.16), QPointF(cx + w * 0.08, cy + h * 0.16))
    elif name == 'manual':
        p.drawLine(QPointF(cx - w * 0.24, cy + h * 0.28), QPointF(cx + w * 0.16, cy - h * 0.28))
        tip = QPainterPath()
        tip.moveTo(cx + w * 0.16, cy - h * 0.28)
        tip.lineTo(cx + w * 0.28, cy - h * 0.16)
        tip.lineTo(cx + w * 0.1, cy - h * 0.1)
        p.drawPath(tip)
    elif name == 'ai':
        path = QPainterPath()
        path.moveTo(cx, cy - h * 0.35)
        path.quadTo(cx, cy, cx + w * 0.35, cy)
        path.quadTo(cx, cy, cx, cy + h * 0.35)
        path.quadTo(cx, cy, cx - w * 0.35, cy)
        path.quadTo(cx, cy, cx, cy - h * 0.35)
        p.drawPath(path)
    elif name == 'email':
        mail = QRectF(cx - w * 0.34, cy - h * 0.18, w * 0.68, h * 0.42)
        p.drawRoundedRect(mail, 2, 2)
        p.drawLine(QPointF(mail.left() + 2, mail.top() + 2), QPointF(cx, cy + h * 0.06))
        p.drawLine(QPointF(mail.right() - 2, mail.top() + 2), QPointF(cx, cy + h * 0.06))
    elif name == 'send':
        path = QPainterPath()
        path.moveTo(cx - w * 0.22, cy)
        path.lineTo(cx + w * 0.08, cy)
        path.lineTo(cx + w * 0.08, cy - h * 0.14)
        path.lineTo(cx + w * 0.28, cy)
        path.lineTo(cx + w * 0.08, cy + h * 0.14)
        path.lineTo(cx + w * 0.08, cy)
        p.drawPath(path)
    elif name == 'saved':
        paint_icon(p, r, 'memory', c, stroke)
    p.restore()

class IconWidget(QWidget):
    """Ícone estático."""

    def __init__(self, icon: str, size: int = 18, color: QColor | None = None, parent=None):
        super().__init__(parent)
        self._icon = icon
        self._color = color
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def paintEvent(self, e):
        p = QPainter(self)
        paint_icon(p, QRectF(self.rect()), self._icon, self._color)

class IconButton(QWidget):
    """Botão com ícone vetorial dourado."""
    clicked = pyqtSignal()

    def __init__(self, icon: str, size: int = 28, tooltip: str = '', parent=None):
        super().__init__(parent)
        self._icon = icon
        self._hov = False
        self._prs = False
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setToolTip(tooltip)
        self.setMouseTracking(True)

    def enterEvent(self, e):
        self._hov = True
        self.update()

    def leaveEvent(self, e):
        self._hov = False
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._prs = True
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._prs:
            self._prs = False
            self.update()
            if self.rect().contains(e.position().toPoint()):
                self.clicked.emit()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._prs:
            p.setBrush(QColor(201, 168, 76, 55))
        elif self._hov:
            p.setBrush(QColor(201, 168, 76, 28))
        else:
            p.setBrush(Qt.GlobalColor.transparent)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(1, 1, self.width() - 2, self.height() - 2, 6, 6)
        if self._prs:
            color = C_GOLD_DEEP
        elif self._hov:
            color = C_GOLD_BRIGHT
        else:
            color = C_GOLD_BRIGHT
        paint_icon(p, QRectF(self.rect()), self._icon, color)

class BrainButton(QWidget):
    """Botão do painel Intelligence — ícone de rede + badge opcional."""
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hov = False
        self._prs = False
        self._badge = 0
        self.setFixedSize(32, 32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setToolTip('Agenda e Grafo')
        self.setMouseTracking(True)

    def set_badge(self, count: int):
        self._badge = max(0, count)
        self.update()

    def clear_badge(self):
        self._badge = 0
        self.update()

    def enterEvent(self, e):
        self._hov = True
        self.update()

    def leaveEvent(self, e):
        self._hov = False
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._prs = True
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._prs:
            self._prs = False
            self.update()
            if self.rect().contains(e.position().toPoint()):
                self.clicked.emit()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._badge > 0:
            p.setBrush(QColor(201, 168, 76, 45))
            p.setPen(QPen(C_GOLD, 1))
        elif self._prs:
            p.setBrush(QColor(201, 168, 76, 55))
            p.setPen(Qt.PenStyle.NoPen)
        elif self._hov:
            p.setBrush(QColor(201, 168, 76, 28))
            p.setPen(Qt.PenStyle.NoPen)
        else:
            p.setBrush(Qt.GlobalColor.transparent)
            p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 0, self.width(), self.height(), 8, 8)
        pix = _get_nigel_pixmap()
        if pix and not pix.isNull():
            scaled = pix.scaled(24, 24, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            p.drawPixmap(x, y, scaled)
        else:
            paint_icon(p, QRectF(4, 4, 24, 24), 'brain', C_GOLD_BRIGHT)
        if self._badge > 0:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(C_GOLD_BRIGHT)
            badge_rect = QRectF(self.width() - 14, -2, 14, 14)
            p.drawEllipse(badge_rect)
            p.setPen(QPen(C_GOLD_DEEP))
            f = QFont(FONT.split(',')[0].strip("'"), 8)
            f.setBold(True)
            p.setFont(f)
            txt = str(self._badge) if self._badge < 10 else '9+'
            p.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, txt)

def source_icon_name(source: str) -> str:
    return {'manual': 'manual', 'ai': 'ai', 'outlook': 'email', 'gmail': 'email'}.get(source, 'saved')
