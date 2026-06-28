"""
ui/bar.py  —  Barra flutuante com chat integrado (Vanilla & Gold)

Arquitetura:
- Quando colapsada : 60px  — só o prompt pill
- Quando expandida : 60px + 440px — chat aparece acima do prompt

Um único campo de input. Zero janelas extras.
"""
import json
import math
import os
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLineEdit, QPushButton, QApplication, QFrame, QLabel, QScrollArea, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QPointF, QRectF, QObject, QEvent, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen, QPainterPath
from dotenv import load_dotenv
load_dotenv()
from core.api_client import APIClient
from ui.theme import paint_panel, C_PANEL, C_CREAM, C_GOLD, C_GOLD_BRIGHT, C_GOLD_BTN, C_GOLD_BTN_H, C_GOLD_BTN_P, C_AI_MSG, C_USER_MSG, C_ERR_MSG, C_TEXT, C_TEXT_MID, TEXT_CSS, TEXT_MID_CSS, FONT, SCROLL_STYLE, BTN_GHOST, BTN_CLOSE, LABEL_GOLD, GOLD_BTN_CSS, GOLD_BTN_H_CSS, GOLD_BTN_P_CSS, GOLD_BRIGHT_CSS
from ui.icons import BrainButton, IconButton

class ThinkingOrb(QWidget):
    """Indicador fluido: 3 gotas quicando, com transição de cor e dissolução."""
    COLORS = {'thinking': (QColor(212, 175, 80), QColor(240, 212, 110)), 'review': (QColor(156, 104, 230), QColor(205, 158, 255)), 'gate': (QColor(72, 168, 148), QColor(130, 220, 200)), 'audit': (QColor(220, 140, 70), QColor(255, 190, 120)), 'tool': (QColor(74, 192, 118), QColor(150, 235, 175)), 'idle': (QColor(212, 175, 80), QColor(240, 212, 110))}
    _DT = 0.016
    _PERIOD = 0.62
    _AMP = 15.0

    def __init__(self, parent=None, *, phase: str = 'thinking'):
        super().__init__(parent)
        self._phase = phase
        m, g = self.COLORS.get(phase, self.COLORS['idle'])
        self._cur_main = QColor(m)
        self._cur_glow = QColor(g)
        self._src_main = QColor(m)
        self._src_glow = QColor(g)
        self._dst_main = QColor(m)
        self._dst_glow = QColor(g)
        self._t = 0.0
        self._trans = 1.0
        self._burst_spawned = False
        self._dissolve = -1.0
        self._dissolve_cb = None
        self._dissolve_ripple = False
        self._ripples = []
        self._burst_parts = []
        self._burst_flash = 0.0
        self._burst_y = 0.0
        self._last_u = [0.0, 0.0, 0.0]
        self._dots = []
        self.setFixedSize(84, 42)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def set_phase(self, phase: str):
        if phase == self._phase:
            return
        self._phase = phase
        self._src_main = QColor(self._cur_main)
        self._src_glow = QColor(self._cur_glow)
        self._dst_main, self._dst_glow = (QColor(c) for c in self.COLORS.get(phase, self.COLORS['idle']))
        self._trans = 0.0
        self._burst_spawned = False

    def start_dissolve(self, on_done=None):
        if self._dissolve >= 0.0:
            return
        self._dissolve = 0.0
        self._dissolve_cb = on_done
        self._dissolve_ripple = False

    @property
    def _xs(self):
        cx = self.width() / 2
        return (cx - 14, cx, cx + 14)

    @staticmethod
    def _smooth(t: float) -> float:
        t = max(0.0, min(1.0, t))
        return t * t * (3 - 2 * t)

    def _mix(self, a: QColor, b: QColor, t: float) -> QColor:
        t = max(0.0, min(1.0, t))
        return QColor(int(a.red() + (b.red() - a.red()) * t), int(a.green() + (b.green() - a.green()) * t), int(a.blue() + (b.blue() - a.blue()) * t))

    def pulse(self):
        dt = self._DT
        floor_y = self.height() - 9
        cx_center = self.width() / 2
        gather_cy = floor_y - self._AMP * 0.9
        in_trans = self._trans < 1.0
        conv = 0.0
        emerge = -1.0
        if in_trans:
            self._trans = min(1.0, self._trans + dt / 1.7)
            tr = self._trans
            color_t = self._smooth(max(0.0, (tr - 0.55) / 0.12))
            self._cur_main = self._mix(self._src_main, self._dst_main, color_t)
            self._cur_glow = self._mix(self._src_glow, self._dst_glow, color_t)
            if tr < 0.55:
                conv = self._smooth(tr / 0.55)
            else:
                if not self._burst_spawned:
                    self._burst_spawned = True
                    self._t = 0.5 * self._PERIOD
                    self._last_u = [self._t / self._PERIOD + i * 0.18 % 1.0 for i in range(3)]
                    self._burst_flash = 1.0
                    self._burst_y = gather_cy
                    for k in range(9):
                        a = math.pi * (0.06 + 0.88 * k / 8.0)
                        spd = 60.0 + 26.0 * (k % 3)
                        self._burst_parts.append({'x': cx_center, 'y': gather_cy, 'vx': math.cos(a) * spd, 'vy': -math.sin(a) * spd, 'life': 1.0, 'r': 1.5 + 1.1 * (k * 5 % 3) / 2.0})
                else:
                    self._t += dt
                emerge = (tr - 0.55) / 0.45
        elif self._dissolve < 0.0:
            self._t += dt
        if self._burst_flash > 0.0:
            self._burst_flash = max(0.0, self._burst_flash - dt / 0.45)
        for pt in self._burst_parts:
            pt['x'] += pt['vx'] * dt
            pt['y'] += pt['vy'] * dt
            pt['vy'] += 250.0 * dt
            pt['life'] -= dt / 0.55
        self._burst_parts = [pt for pt in self._burst_parts if pt['life'] > 0.0]
        diss_gather = 0.0
        diss_melt = 0.0
        if self._dissolve >= 0.0:
            self._dissolve = min(1.0, self._dissolve + dt / 1.1)
            d = self._dissolve
            if d < 0.45:
                diss_gather = self._smooth(d / 0.45)
            else:
                diss_gather = 1.0
                diss_melt = self._smooth((d - 0.45) / 0.55)
                if not self._dissolve_ripple:
                    self._dissolve_ripple = True
                    self._ripples.append({'x': cx_center, 'life': 1.0, 'max_r': 30.0, 'w': 4.0})
            if self._dissolve >= 1.0 and self._dissolve_cb:
                cb = self._dissolve_cb
                self._dissolve_cb = None
                cb()
                return
        self._dots = []
        for i in range(3):
            u = (self._t / self._PERIOD + i * 0.18) % 1.0
            if u < self._last_u[i] and not in_trans and self._dissolve < 0.0:
                self._ripples.append({'x': self._xs[i], 'life': 1.0, 'max_r': 14.0, 'w': 1.6})
            self._last_u[i] = u
            height = 4.0 * u * (1.0 - u)
            contact = max(0.0, 1.0 - height * 7.0)
            target = self._xs[i]
            x = target
            cy = floor_y - height * self._AMP
            sx = 1.0 + 0.5 * contact
            sy = 1.0 - 0.34 * contact
            alpha = 1.0
            if conv > 0.0:
                x = target + (cx_center - target) * conv
                cy = cy + (gather_cy - cy) * conv
                s = 1.0 - 0.22 * conv
                sx = sy = s
            elif emerge >= 0.0:
                e = min(1.0, emerge)
                launch = 1.0 - (1.0 - e) ** 2.2
                x = cx_center + (target - cx_center) * launch
                cy = gather_cy + (cy - gather_cy) * launch
                s = 0.85 + 0.15 * launch
                sx = sy = s
            if diss_gather > 0.0:
                x = x + (cx_center - x) * diss_gather
                cy = cy + (floor_y - cy) * diss_gather
                if diss_melt > 0.0:
                    sx *= 1.0 + diss_melt * 2.4
                    sy *= 1.0 - diss_melt * 0.9
                    alpha = 1.0 - diss_melt
            self._dots.append((x, cy, sx, sy, alpha))
        for r in self._ripples:
            r['life'] -= dt / 0.62
        self._ripples = [r for r in self._ripples if r['life'] > 0.0]
        self.update()

    def paintEvent(self, event):
        if not self._dots:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        floor_y = self.height() - 9
        main, glow = self._cur_main, self._cur_glow
        for r in self._ripples:
            life = r['life']
            ease = 1.0 - (1.0 - life) ** 2
            rad = (1.0 - life) * r['max_r'] + 2.0
            haze = QColor(glow)
            haze.setAlpha(int(46 * ease))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(haze)
            p.drawEllipse(QPointF(r['x'], floor_y + 1.0), rad, rad * 0.34)
            ring = QColor(glow)
            ring.setAlpha(int(150 * ease))
            p.setPen(QPen(ring, r['w'] * ease + 0.4))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(r['x'], floor_y + 1.0), rad, rad * 0.34)
        if self._burst_flash > 0.0:
            f = self._burst_flash
            ease = 1.0 - f
            cxc = self.width() / 2
            rad = 3.0 + ease * 16.0
            haze = QColor(glow)
            haze.setAlpha(int(70 * f))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(haze)
            p.drawEllipse(QPointF(cxc, self._burst_y), rad, rad)
            ring = QColor(glow)
            ring.setAlpha(int(180 * f))
            p.setPen(QPen(ring, 2.0 * f + 0.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(cxc, self._burst_y), rad, rad)
        for pt in self._burst_parts:
            life = max(0.0, pt['life'])
            drop = QColor(main)
            drop.setAlpha(int(230 * life))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(drop)
            p.drawEllipse(QPointF(pt['x'], pt['y']), pt['r'], pt['r'])
        for x, cy, sx, sy, alpha in self._dots:
            if alpha <= 0.02:
                continue
            base = 5.0
            rx, ry = base * sx, base * sy
            halo = QColor(glow)
            halo.setAlpha(int(70 * alpha))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(halo)
            p.drawEllipse(QPointF(x, cy), rx + 2.6, ry + 2.6)
            body = QColor(main)
            body.setAlpha(int(235 * alpha))
            p.setBrush(body)
            p.setPen(QPen(QColor(255, 246, 220, int(150 * alpha)), 1.0))
            p.drawEllipse(QPointF(x, cy), rx, ry)
            shine = QColor(255, 255, 255, int(95 * alpha))
            p.setBrush(shine)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(x - rx * 0.32, cy - ry * 0.34), rx * 0.26, ry * 0.26)

class MessageBubble(QFrame):

    def __init__(self, text: str, is_user: bool = False, is_error: bool = False, tone: str = 'normal', max_width: int = 420, parent=None):
        super().__init__(parent)
        self.is_user = is_user
        self.is_error = is_error
        self.tone = tone
        self._raw = text
        if is_error:
            self._bg = C_ERR_MSG
            self._border = QColor(200, 60, 40, 120)
            txt_css = 'rgba(200,60,40,220)'
        elif is_user:
            self._bg = C_USER_MSG
            self._border = QColor(218, 183, 60, 155)
            txt_css = TEXT_CSS
        elif tone == 'persona':
            self._bg = QColor(244, 235, 252, 238)
            self._border = QColor(156, 104, 230, 150)
            txt_css = 'rgba(74, 42, 112, 230)'
        else:
            self._bg = C_AI_MSG
            self._border = QColor(201, 168, 76, 80)
            txt_css = TEXT_CSS
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 3, 0, 3)
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.label.setMaximumWidth(max_width)
        self.label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.label.setStyleSheet(f"QLabel {{ color:{txt_css}; padding:10px 14px; font-size:13px; font-family:{FONT}; line-height:1.5; background:transparent; }}")
        if is_user:
            layout.addStretch()
            layout.addWidget(self.label)
        else:
            layout.addWidget(self.label)
            layout.addStretch()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        lbl = self.label
        rect = QRectF(lbl.x() - 0.5, 0.5, lbl.width() + 1, self.height() - 1)
        path = QPainterPath()
        path.addRoundedRect(rect, 14, 14)
        p.setPen(QPen(self._border, 1))
        p.setBrush(self._bg)
        p.drawPath(path)

    def append_text(self, chunk: str):
        self._raw += chunk
        self.label.setText(self._raw)

    def set_text(self, text: str):
        self._raw = text
        self.label.setText(text)

    def set_persona_tone(self):
        self.tone = 'persona'
        self._bg = QColor(244, 235, 252, 238)
        self._border = QColor(156, 104, 230, 150)
        self.label.setStyleSheet(f"QLabel {{ color:rgba(74, 42, 112, 230); padding:10px 14px; font-size:13px; font-family:{FONT}; line-height:1.5; background:transparent; }}")
        self.update()

    @property
    def full_text(self) -> str:
        return self._raw

class DragFilter(QObject):
    """
    Instalado em widgets filhos para permitir arrastar a barra inteira.
    Threshold de 8px evita ativar drag em cliques normais (ex: clicar no input).
    """

    def __init__(self, bar: 'Bar'):
        super().__init__(bar)
        self._bar = bar
        self._press = None
        self._dragging = False

    def eventFilter(self, obj, event):
        t = event.type()
        if t == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self._press = event.globalPosition().toPoint()
            self._dragging = False
            self._bar._drag_pos = self._press - self._bar.frameGeometry().topLeft()
            return False
        if t == QEvent.Type.MouseMove and event.buttons() == Qt.MouseButton.LeftButton:
            if self._press is not None:
                moved = (event.globalPosition().toPoint() - self._press).manhattanLength()
                if moved > 8:
                    self._dragging = True
            if self._dragging and self._bar._drag_pos is not None:
                self._bar._move_clamped(event.globalPosition().toPoint() - self._bar._drag_pos)
                return True
            return False
        if t == QEvent.Type.MouseButtonRelease:
            if not self._dragging and isinstance(obj, QLineEdit):
                obj.setFocus()
            self._press = None
            self._dragging = False
            self._bar._drag_pos = None
        return False

class DotsButton(QWidget):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(36, 36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hov = self._prs = False
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
            return
        return

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._prs:
            self._prs = False
            self.update()
            if self.rect().contains(e.position().toPoint()):
                self.clicked.emit()
                return
            return
        return

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._prs:
            p.setBrush(QColor(201, 168, 76, 55))
        elif self._hov:
            p.setBrush(QColor(201, 168, 76, 28))
        else:
            p.setBrush(Qt.GlobalColor.transparent)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(2, 2, 32, 32)
        dot_c = C_GOLD_BRIGHT if self._hov else C_GOLD_BTN
        p.setBrush(dot_c)
        dot, gap = (5, 4)
        ox = (self.width() - dot * 2 - gap) // 2
        oy = (self.height() - dot * 2 - gap) // 2
        for r in range(2):
            for c in range(2):
                p.drawEllipse(ox + c * (dot + gap), oy + r * (dot + gap), dot, dot)

class SendButton(QWidget):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(32, 32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hov = False
        self._prs = False
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
            return
        return

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._prs:
            self._prs = False
            self.update()
            if self.rect().contains(e.position().toPoint()):
                self.clicked.emit()
                return
            return
        return

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._prs:
            c = C_GOLD_BTN_P
        elif self._hov:
            c = C_GOLD_BTN_H
        else:
            c = C_GOLD_BTN
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        path = QPainterPath()
        path.moveTo(8, 14.5)
        path.lineTo(17, 14.5)
        path.lineTo(17, 9)
        path.lineTo(25, 16)
        path.lineTo(17, 23)
        path.lineTo(17, 17.5)
        path.lineTo(8, 17.5)
        path.closeSubpath()
        p.drawPath(path)

class SmoothToggle(QWidget):
    toggled = pyqtSignal(bool)

    def __init__(self, checked=True, parent=None):
        super().__init__(parent)
        self.setFixedSize(34, 20)
        self._checked = checked
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._checked = not self._checked
            self.update()
            self.toggled.emit(self._checked)
            return
        return

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0, 0, self.width(), self.height())
        path = QPainterPath()
        path.addRoundedRect(rect, 10, 10)
        if self._checked:
            p.setBrush(QColor(201, 168, 76, 180))
            p.setPen(Qt.PenStyle.NoPen)
        else:
            p.setBrush(QColor(201, 168, 76, 40))
            p.setPen(Qt.PenStyle.NoPen)
        p.drawPath(path)
        p.setBrush(QColor(250, 246, 238))
        if self._checked:
            p.drawEllipse(QRectF(self.width() - 18, 2, 16, 16))
            return
        p.drawEllipse(QRectF(2, 2, 16, 16))

class FlyoutMenu(QWidget):
    settings_requested = pyqtSignal()
    quit_requested = pyqtSignal()
    always_on_top_toggled = pyqtSignal(bool)

    def __init__(self, always_on_top: bool = True):
        super().__init__(None, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setFixedWidth(192)
        self._aot = always_on_top
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(3)

        def _s(color, hbg, hcolor):
            return f"\n                QPushButton {{\n                    background:transparent; border:none; border-radius:8px;\n                    padding:8px 14px 8px 10px; text-align:left;\n                    font-size:13px; font-family:{FONT}; color:{color};\n                }}\n                QPushButton:hover {{ background:{hbg}; color:{hcolor}; }}\n                QPushButton:pressed {{ background:rgba(201,168,76,60); }}\n            "
        self.btn_settings = QPushButton('Settings')
        self.btn_settings.setStyleSheet(_s(TEXT_CSS, 'rgba(201,168,76,35)', TEXT_CSS))
        self.btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_settings.clicked.connect(lambda : (self.hide(), self.settings_requested.emit()))
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet('background:rgba(201,168,76,60); margin:2px 4px;')
        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(4, 2, 2, 2)
        bottom_row.setSpacing(8)
        self.pin_toggle = SmoothToggle(self._aot)
        self.pin_toggle.toggled.connect(self._toggle_pin)
        pin_lbl = QLabel('Sempre visível')
        pin_lbl.setStyleSheet(f"color: {TEXT_CSS}; font-size: 11px; font-family: {FONT};")
        self.btn_quit = QPushButton('Quit')
        self.btn_quit.setStyleSheet(_s('rgba(180,50,30,190)', 'rgba(200,50,30,40)', 'rgba(200,50,30,230)'))
        self.btn_quit.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_quit.clicked.connect(lambda : (self.hide(), self.quit_requested.emit()))
        bottom_row.addWidget(self.pin_toggle)
        bottom_row.addWidget(pin_lbl)
        bottom_row.addStretch()
        bottom_row.addWidget(self.btn_quit)
        layout.addWidget(self.btn_settings)
        layout.addWidget(sep)
        layout.addLayout(bottom_row)

    def paintEvent(self, event):
        p = QPainter(self)
        paint_panel(self, p, radius=14, bg=C_PANEL, border=C_GOLD)

    def _toggle_pin(self, checked: bool):
        self._aot = checked
        self.hide()
        self.always_on_top_toggled.emit(self._aot)

    def show_smart(self, bar: 'Bar'):
        self.adjustSize()
        h = max(self.sizeHint().height(), 96)
        self.setFixedHeight(h)
        dots_g = bar.dots_btn.mapToGlobal(QPoint(0, 0))
        screen_h = QApplication.primaryScreen().availableGeometry().height()
        if dots_g.y() < screen_h // 2:
            self.move(dots_g.x() - 4, dots_g.y() + bar.dots_btn.height() + 8)
        else:
            self.move(dots_g.x() - 4, dots_g.y() - h - 8)
        self.show()

class Bar(QWidget):
    _PROMPT_H = None
    _CHAT_H = 440

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._BAR_W = int(os.getenv('NIGEL_BAR_WIDTH', '600'))
        self._BAR_H = int(os.getenv('NIGEL_BAR_HEIGHT', '60'))
        self._aot = os.getenv('NIGEL_ALWAYS_ON_TOP', 'true').lower() != 'false'
        self._collapsed = True
        self._expands_down = False
        self._drag_pos = None
        self._flyout = None
        self._settings = None
        self._api = APIClient()
        self._history = []
        self._worker = None
        self._ai_bub = None
        self._thinking_orb = None
        self._stream_buf = ''
        self._stream_phase = 'idle'
        self._draft_buf = ''
        self._last_full_history = []
        self._thinking_timer = QTimer(self)
        self._thinking_timer.timeout.connect(self._tick_thinking)
        self._thinking_step = 0
        self._last_user_text = ''
        self._pending_persona_clarification = None
        self._continuation_pending_buttons = []
        self._continuation_subject = ''
        self._auto_execute_next_single_agenda = False
        self._allow_next_persona_save = False
        self._gate_worker = None
        self._compliance_worker = None
        self._compliance_must_execute = False
        self._compliance_fix_attempts = 0
        self._gate_mode = 'conversation'
        self._gate_persona_ui = False
        self._gate_curiosity_subject = ''
        self._review_buf = ''
        self._tool_fix_attempts = 0
        self._force_execute_after_clarification = False
        self._detective_original_request = ''
        self._detective_pending_buttons = []
        self._detective_learned = []
        self._response_revealed = False
        self._reveal_safety_timer = QTimer(self)
        self._reveal_safety_timer.setSingleShot(True)
        self._reveal_safety_timer.timeout.connect(self._on_reveal_safety_timeout)
        self._pending_reveal = None
        self._brain = None
        self._agenda_executor = None
        self._drag_filter = DragFilter(self)
        self._schedule_checker = None
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.width() // 2 - self._BAR_W // 2, screen.height() - 120)
        self._build()
        self.setFixedSize(self._BAR_W, self._BAR_H)

    def _build(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        self.chat_widget = QWidget()
        self.chat_widget.setVisible(False)
        self.chat_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        chat_layout = QVBoxLayout(self.chat_widget)
        chat_layout.setContentsMargins(14, 12, 14, 8)
        chat_layout.setSpacing(6)
        header = QHBoxLayout()
        self.provider_lbl = QLabel()
        self.provider_lbl.setStyleSheet(LABEL_GOLD)
        self._refresh_provider_label()
        self.status_lbl = QLabel('')
        self.status_lbl.setStyleSheet(f"color:rgba(160,126,30,180); font-size:11px; font-style:italic; font-family:{FONT};")
        self.clear_btn = QPushButton('Clear')
        self.clear_btn.setStyleSheet(BTN_GHOST)
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.clicked.connect(self._clear_chat)
        self.close_chat_btn = IconButton('close', 24, 'Fechar chat')
        self.close_chat_btn.clicked.connect(self._collapse)
        header.addWidget(self.provider_lbl)
        header.addStretch()
        header.addWidget(self.status_lbl)
        header.addSpacing(8)
        header.addWidget(self.clear_btn)
        header.addWidget(self.close_chat_btn)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(SCROLL_STYLE)
        self.msg_container = QWidget()
        self.msg_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.msg_layout = QVBoxLayout(self.msg_container)
        self.msg_layout.setContentsMargins(2, 4, 2, 4)
        self.msg_layout.setSpacing(6)
        self.msg_layout.addStretch()
        self.scroll.setWidget(self.msg_container)
        div_chat = QFrame()
        div_chat.setFrameShape(QFrame.Shape.HLine)
        div_chat.setFixedHeight(1)
        div_chat.setStyleSheet('background:rgba(201,168,76,60);')
        chat_layout.addLayout(header)
        chat_layout.addWidget(div_chat)
        chat_layout.addWidget(self.scroll, 1)
        self._btn_container = QWidget()
        self._btn_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._btn_layout = QHBoxLayout(self._btn_container)
        self._btn_layout.setContentsMargins(4, 0, 4, 4)
        self._btn_layout.setSpacing(6)
        self._btn_layout.addStretch()
        self._btn_container.hide()
        chat_layout.addWidget(self._btn_container)
        self.prompt_row = QWidget()
        self.prompt_row.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.prompt_row.setFixedHeight(self._BAR_H)
        prompt = QHBoxLayout(self.prompt_row)
        prompt.setContentsMargins(12, 0, 12, 0)
        prompt.setSpacing(8)
        self.dots_btn = DotsButton()
        self.dots_btn.clicked.connect(self._toggle_menu)
        self.brain_btn = BrainButton()
        self.brain_btn.clicked.connect(self._toggle_brain)
        self.input = QLineEdit()
        self.input.setPlaceholderText('Ask anything…')
        self.input.setStyleSheet(f"\n            QLineEdit {{\n                background: transparent;\n                border: none;\n                color: {TEXT_CSS};\n                font-size: 14px;\n                font-family: {FONT};\n                selection-background-color: rgba(201,168,76,110);\n            }}\n        ")
        self.input.returnPressed.connect(self._on_send)
        self.input.installEventFilter(self._drag_filter)
        self.send_btn = SendButton()
        self.send_btn.clicked.connect(self._on_send)
        self.send_btn.installEventFilter(self._drag_filter)
        prompt.addWidget(self.dots_btn)
        prompt.addWidget(self.brain_btn)
        prompt.addWidget(self.input, 1)
        prompt.addWidget(self.send_btn)
        main.addWidget(self.chat_widget, 1)
        main.addWidget(self.prompt_row)

    def paintEvent(self, event):
        p = QPainter(self)
        r = float(self._BAR_H // 2) if self._collapsed else 18.0
        paint_panel(self, p, radius=r, bg=C_PANEL, border=C_GOLD)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self._move_clamped(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def _move_clamped(self, new_pos):
        screen = QApplication.screenAt(new_pos)
        if screen is None:
            screen = QApplication.primaryScreen()
        geom = screen.availableGeometry()
        min_x = geom.left()
        max_x = geom.right() - self.width() + 1
        if max_x < min_x:
            max_x = min_x
        new_x = max(min_x, min(new_pos.x(), max_x))
        min_y = geom.top()
        max_y = geom.bottom() - self.height() + 1
        if max_y < min_y:
            max_y = min_y
        new_y = max(min_y, min(new_pos.y(), max_y))
        self.move(new_x, new_y)

    def moveEvent(self, event):
        super().moveEvent(event)
        if self._flyout and self._flyout.isVisible():
            self._flyout.show_smart(self)
            return
        return

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def _expand(self):
        if not self._collapsed:
            return
        self._collapsed = False
        screen_h = QApplication.primaryScreen().availableGeometry().height()
        self._expands_down = self.pos().y() < screen_h // 2
        total_h = self._BAR_H + self._CHAT_H
        pos = self.pos()
        self.chat_widget.setVisible(True)
        self.setFixedSize(self._BAR_W, total_h)
        if not self._expands_down:
            self.move(pos.x(), pos.y() - self._CHAT_H)
        self.update()

    def _collapse(self):
        if self._collapsed:
            return
        pos = self.pos()
        self._collapsed = True
        self.chat_widget.setVisible(False)
        self.setFixedSize(self._BAR_W, self._BAR_H)
        if not self._expands_down:
            self.move(pos.x(), pos.y() + self._CHAT_H)
        self.update()

    def _on_send(self):
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self._expand()
        self._send_message(text)

    def _send_message(self, text: str):
        self._clear_dynamic_buttons()
        if self._gate_worker is not None and self._gate_worker.isRunning():
            self._gate_worker.wait(2000)
            self._gate_worker = None
        if self._compliance_worker is not None and self._compliance_worker.isRunning():
            self._compliance_worker.wait(2000)
            self._compliance_worker = None
        self._add_bubble(text, is_user=True)
        self._history.append({'role': 'user', 'content': text})
        self._last_user_text = text
        if self._handle_pending_persona_reply(text):
            return
        if not self._api.get_active_provider():
            self._add_bubble('Nenhum provider configurado.\nAbra Settings (4 pontinhos) e adicione uma chave de API.', is_user=False, is_error=True)
            return
        self._start_stream()

    def _build_full_history(self):
        from core.database import SeqDB
        from ui.agenda_skills import build_chat_agenda_prompt
        from datetime import datetime
        db = SeqDB.get_instance()
        items = db.get_saved_items()
        graph = db.get_knowledge_graph(limit=40)
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        sys_msg = 'You are Nigel, an intelligent personal assistant. Always reply to the user in the language they wrote in (usually Portuguese), but reason internally in English. You have access to the following memory (saved information) about the user and their context:\n'
        if not items:
            sys_msg += '- No information in memory yet.\n'
        else:
            for i in items:
                subj = i.get('subject') or i.get('ai_summary') or ''
                preview = (i.get('body_preview') or i.get('ai_reason') or '').replace('\n', ' ').strip()
                source = i.get('source', 'memória')
                if preview:
                    sys_msg += f"- [{source}] {subj}: {preview}\n"
                else:
                    sys_msg += f"- [{source}] {subj}\n"
        sys_msg += self._knowledge_graph_context(graph)
        sys_msg += (
            "\nIf the user asks something about themselves or about information in the memory above, answer naturally using that data.\n\n"
            "You also act as a personal knowledge engine:\n"
            "- Your memory must grow through detective curiosity. Scan every request for ALL unknown people, "
            "places, objects, relationships and context — not just the first name. Ask one question per turn "
            "(purple bubble), save answers, keep asking until enough is known, THEN schedule.\n"
            "- During the conversation, notice relevant facts worth adding to the user's memory graph.\n"
            "- Value small details with future value: important people, preferences, recurring problems, work context, important messages, relevant meetings, broken objects, commitments and decisions.\n"
            "- When you detect something relevant, use save_memory in the tools JSON as described below.\n"
            "- Do not invent data. Only save what the user stated or what is clearly in context.\n"
            "- The app is global: never assume data about a person, place or thing that is not in memory or in the current message.\n"
            "- Do NOT let persona curiosity block objective commands about existing reminders (cancel, reschedule, complete, postpone). In those cases use the agenda and the graph/memory/chat to resolve the reference, and only ask if needed to pick the right reminder.\n"
            "- A bare name is not persona. Persona needs a relationship, preference, habit, role or clear fact stated by the user.\n"
            "- Your intelligence grows through good questions at the right moment, never through assumptions or fixed lists.\n"
            "- TWO UI MODES — keep them separate:\n"
            "  • Curiosity mode (PURPLE bubble): unknown person/place/thing in memory → ask with clarification JSON. Nothing scheduled yet unless already done before.\n"
            "  • Schedule mode (normal bubble): enough context → agenda action in actions. Runs immediately.\n"
            "  When curious, ALWAYS emit clarification in the JSON so the app shows the purple bubble.\n"
            "- After a clarification answer, save useful facts with save_memory, then complete any pending agenda.\n"
            "- After a clarification answer, judge whether it actually teaches something useful. Never save raw answers like \"no\", \"yes\", \"maybe\" or context-free phrases.\n"
            "- If the answer opens another relevant gap, ask one more short question before saving. Do not use invented examples or names.\n\n"
            f"{build_chat_agenda_prompt(now)}\n"
        )
        return [{'role': 'system', 'content': sys_msg}] + self._history

    def _knowledge_graph_context(self, graph: dict) -> str:
        nodes = graph.get('nodes', []) or []
        edges = graph.get('edges', []) or []
        if not nodes:
            return '\n## KNOWLEDGE GRAPH: empty.\n'
        by_id = {n.get('id'): n for n in nodes}
        lines = ['\n## KNOWLEDGE GRAPH (relevant nodes and connections)']
        for n in nodes[:18]:
            title = n.get('title') or n.get('id') or 'Node'
            body = (n.get('body') or '').replace('\n', ' ').strip()
            node_type = n.get('node_type', 'note')
            source = n.get('source', '')
            snippet = f": {body[:100]}" if body else ''
            lines.append(f"- [{node_type}/{source}] {title}{snippet}")
        if edges:
            lines.append('Connections:')
            for e in edges[:24]:
                a = by_id.get(e.get('source_id'), {})
                b = by_id.get(e.get('target_id'), {})
                at = a.get('title') or e.get('source_id')
                bt = b.get('title') or e.get('target_id')
                rel = e.get('relation', 'related')
                strength = e.get('strength', '')
                lines.append(f"- {at} --{rel}/{strength}--> {bt}")
        return '\n'.join(lines) + '\n'

    def _review_history_for_draft(self, draft: str):
        review_sys = (
            "You are Nigel's review layer, running before the reply is shown to the user. "
            "Read the user's message and the draft below. Return ONLY the corrected final reply "
            "(user-facing text in their language + tools JSON when needed).\n\n"
            "Your job is to align the reply with what the user actually needs right now:\n"
            "- If they want something on the agenda and the intent/time are understandable, the reply "
            "must include the agenda tool JSON in \"actions\" — plain words alone do not create reminders.\n"
            "- If the request names someone/something important and that is not in memory, shift to curiosity: clarification + pending_buttons, NOT actions.\n"
            "- After ONE answer, scan the ORIGINAL request again — places, objects, ownership, timelines may still be unknown. Keep asking (purple) before scheduling.\n"
            "- If Nigel asks the user to teach who/what something is, include clarification JSON so the app shows the purple bubble.\n"
            "- If the user asks a question (who is X?) and X is not in memory, answer briefly then ask them to teach you — with clarification JSON and persona_ui moment.\n"
            "- Never emit mark_done, delete_schedule or reschedule unless the user explicitly asked to change an existing reminder.\n"
            "- If the user is managing an existing reminder, handle the agenda directly — do not turn that "
            "into persona curiosity.\n"
            "- Never mix curiosity and immediate scheduling in the same reply.\n"
            "Do not describe your review. Do not cite rules.\n"
        )
        hist = list(self._last_full_history)
        if hist and hist[0]['role'] == 'system':
            hist[0] = {'role': 'system', 'content': review_sys + '\n\n=== NIGEL GENERAL TOOL RULES ===\n' + hist[0]['content']}
        else:
            hist.insert(0, {'role': 'system', 'content': review_sys})
        return hist + [{'role': 'assistant', 'content': f"DRAFT TO REVIEW:\n{draft}"}, {'role': 'user', 'content': 'Critically review and deliver Nigel\'s final reply now. Include ```json tools when scheduling, curiosity (clarification), or save_memory is needed.'}]

    def _bubble_max_width(self) -> int:
        return max(260, self._BAR_W - 88)

    def _start_stream(self, phase: str = 'draft', messages: list[dict] | None = None):
        if self._worker and self._worker.isRunning():
            return
        self._response_revealed = False
        self._pending_reveal = None
        if self._reveal_safety_timer.isActive():
            self._reveal_safety_timer.stop()
        self.send_btn.setEnabled(False)
        self.status_lbl.setText('')
        self._show_thinking_orb({'draft': 'thinking', 'review': 'review', 'fix': 'gate', 'gate': 'gate', 'compliance_fix': 'audit', 'audit': 'audit'}.get(phase, 'thinking'))
        self._stream_buf = ''
        self._stream_phase = phase
        self._clear_dynamic_buttons()
        if phase == 'draft':
            self._last_full_history = messages or self._build_full_history()
            self._tool_fix_attempts = 0
            self._compliance_fix_attempts = 0
            self._compliance_must_execute = False
        full_history = messages or self._last_full_history
        self._thinking_timer.start(16)
        try:
            self._worker = self._api.create_worker(full_history)
            self._worker.chunk_received.connect(self._on_chunk)
            self._worker.finished.connect(self._on_stream_done)
            self._worker.error_occurred.connect(self._on_error)
            self._worker.start()
        except ValueError as e:
            self._on_error(str(e))

    def _on_chunk(self, text: str):
        if self._thinking_orb is None:
            return
        self._stream_buf += text

    def _tick_thinking(self):
        if self._thinking_orb is None:
            return
        self._thinking_step += 1
        self._thinking_orb.set_phase({'review': 'review', 'fix': 'gate', 'gate': 'gate', 'compliance_fix': 'audit', 'audit': 'audit'}.get(self._stream_phase, 'thinking'))
        self._thinking_orb.pulse()
        self._scroll_bottom()

    def _on_stream_done(self):
        if self._stream_phase == 'draft':
            self._draft_buf = self._stream_buf
            self._stream_buf = ''
            old_worker = self._worker
            self._worker = None
            if old_worker:
                old_worker.deleteLater()
            self._start_stream(phase='review', messages=self._review_history_for_draft(self._draft_buf))
            return
        if self._stream_phase == 'fix':
            self._review_buf = self._stream_buf
            self._stream_buf = ''
            old_worker = self._worker
            self._worker = None
            if old_worker:
                old_worker.deleteLater()
            self._start_intent_gate()
            return
        if self._stream_phase == 'compliance_fix':
            self._review_buf = self._stream_buf
            self._stream_buf = ''
            old_worker = self._worker
            self._worker = None
            if old_worker:
                old_worker.deleteLater()
            self._start_compliance_audit()
            return
        if self._stream_phase == 'review':
            self._review_buf = self._stream_buf
            self._stream_buf = ''
            old_worker = self._worker
            self._worker = None
            if old_worker:
                old_worker.deleteLater()
            self._start_intent_gate()
            return
        self._thinking_timer.stop()
        self._remove_thinking_orb()
        self.status_lbl.setText('')
        self.send_btn.setEnabled(True)
        self._stream_buf = ''
        self._stream_phase = 'idle'

    def _start_intent_gate(self):
        if self._gate_worker is not None and self._gate_worker.isRunning():
            return
        self._stream_phase = 'gate'
        self._show_thinking_orb('gate')
        if not self._thinking_timer.isActive():
            self._thinking_timer.start(16)
        from core.polling_engine import IntentGateWorker
        self._gate_worker = IntentGateWorker(
            user_text=getattr(self, '_last_user_text', ''),
            assistant_reply=self._review_buf,
            learned_facts=self._detective_learned_summary(),
        )
        self._gate_worker.result_ready.connect(self._on_gate_result)
        self._gate_worker.start()

    def _on_gate_result(self, result: dict):
        self._gate_worker = None
        mode = result.get('mode', 'conversation')
        needs_fix = bool(result.get('needs_tool_fix', False))
        fix_hint = result.get('fix_hint', '')
        self._gate_persona_ui = bool(result.get('persona_ui', False))
        self._gate_curiosity_subject = str(result.get('curiosity_subject') or '').strip()
        if getattr(self, '_force_execute_after_clarification', False):
            mode = 'execute_agenda'
            needs_fix = False
            self._gate_persona_ui = False
        self._gate_mode = mode

        if needs_fix and mode in ('execute_agenda', 'ask_context') and self._tool_fix_attempts < 1:
            self._tool_fix_attempts += 1
            self._start_tool_fix_stream(mode, fix_hint)
            return

        self._start_compliance_audit()

    def _start_compliance_audit(self):
        if self._compliance_worker is not None and self._compliance_worker.isRunning():
            return
        self._stream_phase = 'audit'
        self._show_thinking_orb('audit')
        if not self._thinking_timer.isActive():
            self._thinking_timer.start(16)
        from core.polling_engine import ComplianceAuditWorker
        self._compliance_worker = ComplianceAuditWorker(
            user_text=getattr(self, '_last_user_text', ''),
            assistant_reply=self._review_buf,
            gate_mode=getattr(self, '_gate_mode', 'conversation'),
            learned_facts=self._detective_learned_summary(),
            detective_original=self._detective_original_request,
        )
        self._compliance_worker.result_ready.connect(self._on_compliance_result)
        self._compliance_worker.start()

    def _on_compliance_result(self, result: dict):
        self._compliance_worker = None
        override = result.get('override_gate_mode')
        if override in ('execute_agenda', 'ask_context', 'conversation'):
            self._gate_mode = override
            if override == 'execute_agenda':
                self._gate_persona_ui = False
        self._compliance_must_execute = bool(result.get('must_execute_agenda', False))

        needs_fix = bool(result.get('needs_fix', False))
        fix_hint = result.get('fix_hint', '')
        if needs_fix and self._compliance_fix_attempts < 1:
            self._compliance_fix_attempts += 1
            self._start_compliance_fix_stream(fix_hint)
            return

        if self._compliance_must_execute and not result.get('has_valid_agenda_json'):
            if self._compliance_fix_attempts < 1:
                self._compliance_fix_attempts += 1
                self._start_compliance_fix_stream(fix_hint or 'Add create_schedule in actions JSON.')
                return

        self._finish_gated_response()

    def _start_compliance_fix_stream(self, fix_hint: str = ''):
        from core.chat_compliance import build_compliance_fix_messages
        messages = build_compliance_fix_messages(
            user_text=getattr(self, '_last_user_text', ''),
            draft=self._review_buf,
            fix_hint=fix_hint,
        )
        self._start_stream(phase='compliance_fix', messages=messages)

    def _start_tool_fix_stream(self, mode: str, fix_hint: str = ''):
        from core.chat_intent_gate import build_tool_fix_messages
        messages = build_tool_fix_messages(
            user_text=getattr(self, '_last_user_text', ''),
            draft=self._review_buf,
            mode=mode,
            fix_hint=fix_hint,
        )
        self._start_stream(phase='fix', messages=messages)

    def _finish_gated_response(self):
        from ui.agenda_skills import visible_text, augment_ai_text_for_duplicates
        full = augment_ai_text_for_duplicates(self._review_buf)
        visible = visible_text(full) or full
        visible, deferred = self._apply_gate_to_response(full, visible)
        self.status_lbl.setText('')
        self.send_btn.setEnabled(True)
        # Keep timer running — dissolve animation is driven by _tick_thinking.
        if not self._thinking_timer.isActive():
            self._thinking_timer.start(16)
        if self._thinking_orb is not None:
            self._pending_reveal = (visible, deferred, full)
            self._thinking_orb.start_dissolve(on_done=self._on_dissolve_done)
            self._reveal_safety_timer.start(3500)
            return
        self._reveal_response(visible, deferred, full)

    def _on_dissolve_done(self):
        if self._pending_reveal:
            visible, deferred, full = self._pending_reveal
            self._pending_reveal = None
            self._reveal_response(visible, deferred, full)

    def _on_reveal_safety_timeout(self):
        if self._response_revealed:
            return
        if self._pending_reveal:
            visible, deferred, full = self._pending_reveal
            self._pending_reveal = None
            self._reveal_response(visible, deferred, full)
            return
        if self._thinking_orb is not None:
            self._remove_thinking_orb()
            self.send_btn.setEnabled(True)
            self._stream_phase = 'idle'

    def _apply_gate_to_response(self, full_text: str, visible: str) -> tuple[str, bool]:
        if getattr(self, '_force_execute_after_clarification', False):
            self._force_execute_after_clarification = False
            self._gate_mode = 'execute_agenda'
            self._gate_persona_ui = False
            return (visible, False)
        mode = getattr(self, '_gate_mode', 'conversation')
        if mode == 'execute_agenda':
            return (visible, False)

        from ui.agenda_skills import parse_skills_json, expand_chat_buttons

        if getattr(self, '_gate_persona_ui', False) or mode == 'ask_context':
            visible, deferred = self._maybe_defer_for_persona_clarification(full_text, visible)
            if deferred:
                return (visible, True)
            data = parse_skills_json(full_text) or {}
            clarification = data.get('clarification') if isinstance(data.get('clarification'), dict) else {}
            subject = (
                (clarification.get('subject') if clarification else '')
                or getattr(self, '_gate_curiosity_subject', '')
                or 'esse contexto'
            )
            question = (clarification.get('question') if clarification else '') or visible.strip()
            raw_buttons = data.get('pending_buttons') or data.get('buttons', [])
            buttons = expand_chat_buttons(user_text=getattr(self, '_last_user_text', ''), buttons=raw_buttons)
            self._pending_persona_clarification = {
                'name': subject,
                'question': question,
                'buttons': buttons,
                'user_text': getattr(self, '_last_user_text', '') if buttons else '',
                'learn_only': not bool(buttons),
            }
            if buttons and getattr(self, '_last_user_text', ''):
                self._begin_detective_case(getattr(self, '_last_user_text', ''), buttons)
            self._clear_dynamic_buttons()
            return (question or visible, True)

        visible, deferred = self._maybe_defer_for_persona_clarification(full_text, visible)
        if deferred:
            return (visible, True)
        if mode == 'conversation':
            return (visible, False)
        visible, deferred = self._maybe_defer_contradictory_question(full_text, visible)
        return (visible, deferred)

    def _reveal_response(self, visible: str, deferred: bool, full: str):
        if self._response_revealed:
            return
        self._response_revealed = True
        self._pending_reveal = None
        if self._reveal_safety_timer.isActive():
            self._reveal_safety_timer.stop()
        self._thinking_timer.stop()
        self._remove_thinking_orb()
        self._ai_bub = self._add_bubble(visible, is_user=False, tone='persona' if deferred else 'normal')
        self._history.append({'role': 'assistant', 'content': visible if deferred else full})
        if not deferred:
            self._parse_and_execute(full, auto_execute=False)
        else:
            self._compliance_must_execute = False
        self._ai_bub = None
        self._stream_buf = ''
        self._stream_phase = 'idle'

    def _on_error(self, msg: str):
        self._thinking_timer.stop()
        self._remove_thinking_orb()
        self._gate_worker = None
        self._force_execute_after_clarification = False
        self.status_lbl.setText('')
        self.send_btn.setEnabled(True)
        if self._ai_bub:
            self._ai_bub.is_error = True
            self._ai_bub._bg = C_ERR_MSG
            self._ai_bub._border = QColor(200, 60, 40, 120)
            self._ai_bub.label.setStyleSheet(f"QLabel {{ color:rgba(200,60,40,220); padding:10px 14px; font-size:13px; font-family:{FONT}; background:transparent; }}")
            self._ai_bub.set_text(f"Erro: {msg}")
        self._ai_bub = None
        self._stream_phase = 'idle'
        self._worker = None

    def _add_bubble(self, text: str, is_user: bool = False, is_error: bool = False, tone: str = 'normal') -> MessageBubble:
        bub = MessageBubble(text, is_user=is_user, is_error=is_error, tone=tone, max_width=self._bubble_max_width())
        self.msg_layout.insertWidget(self.msg_layout.count() - 1, bub)
        self._scroll_bottom()
        return bub

    def _show_thinking_orb(self, phase: str = 'thinking'):
        if self._thinking_orb is None:
            self._thinking_orb = ThinkingOrb(phase=phase)
            row = QWidget()
            row.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            lay = QHBoxLayout(row)
            lay.setContentsMargins(8, 2, 0, 4)
            lay.addWidget(self._thinking_orb)
            lay.addStretch()
            row._seq_orb_row = True
            self.msg_layout.insertWidget(self.msg_layout.count() - 1, row)
        self._thinking_orb.set_phase(phase)
        self._scroll_bottom()

    def _remove_thinking_orb(self):
        if self._thinking_orb is None:
            return
        orb = self._thinking_orb
        self._thinking_orb = None
        parent = orb.parentWidget()
        if parent:
            parent.deleteLater()
            return
        orb.deleteLater()

    def _add_action_indicator(self, text: str, tone: str = 'normal'):
        from PyQt6.QtWidgets import QLabel
        from ui.theme import FONT
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setMaximumWidth(self._bubble_max_width())
        lbl.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        color = 'rgba(156, 104, 230, 190)' if tone == 'persona' else 'rgba(201, 168, 76, 180)'
        lbl.setStyleSheet(f"color: {color}; font-family: {FONT}; font-size: 11px; padding: 2px 20px 4px 20px; background: transparent;")
        lbl.setContentsMargins(0, 0, 0, 4)
        self.msg_layout.insertWidget(self.msg_layout.count() - 1, lbl)
        self._scroll_bottom()

    def _clear_chat(self):
        self._history.clear()
        if self._worker and self._worker.isRunning():
            self._worker.stop()
        self._worker = None
        if self._gate_worker is not None and self._gate_worker.isRunning():
            self._gate_worker.wait(2000)
        self._gate_worker = None
        if self._compliance_worker is not None and self._compliance_worker.isRunning():
            self._compliance_worker.wait(2000)
        self._compliance_worker = None
        self._ai_bub = None
        self._remove_thinking_orb()
        self._stream_phase = 'idle'
        self._thinking_timer.stop()
        self._pending_persona_clarification = None
        self._continuation_pending_buttons = []
        self._continuation_subject = ''
        self._auto_execute_next_single_agenda = False
        self._allow_next_persona_save = False
        self._gate_mode = 'conversation'
        self._gate_persona_ui = False
        self._gate_curiosity_subject = ''
        self._review_buf = ''
        self._tool_fix_attempts = 0
        self._compliance_fix_attempts = 0
        self._compliance_must_execute = False
        self._force_execute_after_clarification = False
        self._detective_original_request = ''
        self._detective_pending_buttons = []
        self._detective_learned = []
        self._clear_dynamic_buttons()
        self.status_lbl.setText('')
        self.send_btn.setEnabled(True)
        while self.msg_layout.count() > 1:
            item = self.msg_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        return

    def _clear_dynamic_buttons(self):
        if hasattr(self, '_btn_container') and self._btn_container:
            while self._btn_layout.count() > 1:
                item = self._btn_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self._btn_container.hide()
            return
        return

    def _agenda_executor_instance(self):
        if self._agenda_executor is None:
            from ui.agenda_skills import AgendaSkillExecutor
            self._agenda_executor = AgendaSkillExecutor()
        return self._agenda_executor

    def _extract_button_action(self, btn_def: dict) -> dict | None:
        action = btn_def.get('confirm_action')
        if isinstance(action, dict):
            return action
        raw = btn_def.get('action')
        if isinstance(raw, dict):
            return raw
        if raw:
            return {'type': raw}
        return None

    def _action_type_str(self, action: dict | None) -> str:
        if not isinstance(action, dict):
            return ''
        t = action.get('type', '')
        if isinstance(t, dict):
            return str(t.get('type') or '')
        return str(t or '')

    def _agenda_actions_from_buttons(self, buttons: list) -> list[dict]:
        actions = []
        for btn_def in buttons or []:
            action = self._extract_button_action(btn_def)
            if isinstance(action, dict) and self._action_type_str(action) in frozenset({'update_schedule', 'create_schedule', 'delete_schedule', 'postpone', 'mark_done', 'reschedule'}):
                actions.append(action)
        return actions

    def _actions_require_new_context(self, buttons: list) -> bool:
        actions = self._agenda_actions_from_buttons(buttons)
        if not actions:
            return False
        return any((self._action_type_str(a) == 'create_schedule' for a in actions))

    def _raw_buttons_are_existing_agenda_ops(self, buttons: list) -> bool:
        raw_types = set()
        for btn_def in buttons or []:
            action = self._extract_button_action(btn_def)
            if isinstance(action, dict):
                atype = self._action_type_str(action)
                if atype:
                    raw_types.add(atype)
        existing_ops = frozenset({'reschedule', 'update_schedule', 'postpone', 'mark_done', 'delete_schedule'})
        return bool(raw_types) and raw_types.issubset(existing_ops)

    def _simple_person_subject(self, text: str) -> str | None:
        text = (text or '').strip().strip('.!?,;:')
        text = text.removeprefix('Pessoa importante:').strip()
        if not text:
            return None
        import re
        if re.match('^[A-Za-zÀ-ÿ]{2,}(?:\\s+[A-Za-zÀ-ÿ]{2,}){0,2}$', text):
            return text[0].upper() + text[1:]
        return None

    def _maybe_defer_for_persona_clarification(self, full_text: str, visible: str) -> tuple[str, bool]:
        from ui.agenda_skills import parse_skills_json, expand_chat_buttons
        data = parse_skills_json(full_text)
        if not data:
            return (visible, False)
        clarification = data.get('clarification') if isinstance(data.get('clarification'), dict) else None
        if not clarification:
            return (visible, False)
        if self._auto_execute_next_single_agenda and self._continuation_pending_buttons:
            self._execute_continuation_pending_agenda()
            return ('Agendei o que você pediu. Deixo essa curiosidade de Persona para depois, para não travar sua agenda agora.', True)
        raw_buttons = data.get('pending_buttons') or data.get('buttons', [])
        if self._raw_buttons_are_existing_agenda_ops(raw_buttons):
            return (visible, False)
        buttons = expand_chat_buttons(user_text=getattr(self, '_last_user_text', ''), buttons=raw_buttons)
        if buttons and not self._actions_require_new_context(buttons):
            return (visible, False)
        name = (clarification.get('subject') or 'esse contexto').strip()
        question = (clarification.get('question') or '').strip()
        if not question:
            question = f"Antes de continuar, me conta melhor sobre {name}?"
        self._pending_persona_clarification = {'name': name, 'question': question, 'buttons': buttons, 'user_text': getattr(self, '_last_user_text', '')}
        if buttons and getattr(self, '_last_user_text', ''):
            self._begin_detective_case(getattr(self, '_last_user_text', ''), buttons)
        self._clear_dynamic_buttons()
        return (question, True)

    def _begin_detective_case(self, original_request: str, buttons: list):
        self._detective_original_request = (original_request or '').strip()
        self._detective_pending_buttons = list(buttons or [])
        if not self._detective_learned:
            self._detective_learned = []

    def _detective_learned_summary(self) -> list[str]:
        return [f"{item.get('subject', '')}: {item.get('answer', '')}" for item in getattr(self, '_detective_learned', []) if item.get('answer')]

    def _memory_category_for_subject(self, subject: str) -> str:
        return 'persona' if self._simple_person_subject(subject) else 'general'

    def _append_detective_fact(self, subject: str, answer: str):
        subject = (subject or '').strip() or 'contexto'
        answer = (answer or '').strip()
        if not answer:
            return
        self._detective_learned.append({'subject': subject, 'answer': answer})

    def _clear_detective_case(self):
        self._detective_original_request = ''
        self._detective_pending_buttons = []
        self._detective_learned = []

    def _detective_continuation_prompt(self, latest_subject: str, latest_answer: str) -> str:
        original = self._detective_original_request or getattr(self, '_last_user_text', '')
        learned_lines = '\n'.join(f"- {s}" for s in self._detective_learned_summary()) or '- nothing yet'
        pending_json = json.dumps(self._detective_pending_buttons or [], ensure_ascii=False)
        return f"""[Detective continuation — build the user's map BEFORE scheduling]
Original request: {original}
Latest answer: {latest_subject} = {latest_answer}

What you learned this thread:
{learned_lines}

You are Nigel — curious like a detective. Re-read the ORIGINAL request and find what still is NOT 
in memory and NOT covered above: places, apartments, objects, ownership, relationships, timelines, 
context. One answer rarely fills every gap.

If ANY meaningful unknown remains → curiosity path: ask ONE natural question about the biggest gap.
Use clarification JSON + keep the deferred agenda in pending_buttons. Do NOT schedule yet.

Only when you honestly know enough about everything that matters → schedule path: save_memory for 
new facts + create_schedule in actions.

Preserve this deferred agenda until you schedule:
{pending_json}"""

    def _execute_continuation_pending_agenda(self) -> bool:
        actions = self._agenda_actions_from_buttons(self._continuation_pending_buttons)
        if len(actions) != 1:
            return False
        executor = self._agenda_executor_instance()
        from ui.agenda_skills import normalize_action
        user_text = getattr(self, '_last_user_text', '')
        action = normalize_action(actions[0], user_text)
        result = executor.execute(action, user_text=user_text)
        self._add_bubble(result, is_user=False)
        self._auto_execute_next_single_agenda = False
        self._allow_next_persona_save = False
        self._continuation_pending_buttons = []
        self._continuation_subject = ''
        return True

    def _maybe_defer_contradictory_question(self, full_text: str, visible: str) -> tuple[str, bool]:
        if '?' in visible:
            return (visible, False)
        from ui.agenda_skills import parse_skills_json, expand_chat_buttons
        data = parse_skills_json(full_text)
        if not data or isinstance(data.get('clarification'), dict):
            return (visible, False)
        raw_buttons = data.get('buttons', [])
        if self._raw_buttons_are_existing_agenda_ops(raw_buttons):
            return (visible, False)
        buttons = expand_chat_buttons(user_text=getattr(self, '_last_user_text', ''), buttons=raw_buttons)
        if not self._agenda_actions_from_buttons(buttons) or not self._actions_require_new_context(buttons):
            return (visible, False)
        self._pending_persona_clarification = {'name': 'esse contexto', 'question': visible, 'buttons': buttons, 'user_text': getattr(self, '_last_user_text', '')}
        self._clear_dynamic_buttons()
        return (visible, True)

    def _handle_pending_persona_reply(self, text: str) -> bool:
        pending = self._pending_persona_clarification
        if not pending:
            return False
        self._pending_persona_clarification = None
        name = pending.get('name', 'essa pessoa')
        answer = text.strip()
        buttons = pending.get('buttons', [])

        if answer and len(answer) > 2:
            try:
                executor = self._agenda_executor_instance()
                category = self._memory_category_for_subject(name)
                executor.execute({
                    'type': 'save_memory',
                    'category': category,
                    'subject': name,
                    'note': answer
                }, user_text=answer)
                label = 'Persona' if category == 'persona' else 'Memória'
                self._add_action_indicator(f'{label} atualizada: "{name}".', tone='persona')
            except Exception:
                pass

        self._append_detective_fact(name, answer)
        original = pending.get('user_text', '') or self._detective_original_request

        if pending.get('learn_only'):
            self._add_bubble(f'Anotado sobre {name}.', is_user=False, tone='persona')
        elif original and (buttons or self._detective_pending_buttons):
            self._continue_after_persona_clarification(
                name=name, answer=answer,
                question=pending.get('question', ''),
                original_request=original,
                pending_buttons=buttons or self._detective_pending_buttons,
            )
        elif original:
            self._continue_after_persona_clarification(
                name=name, answer=answer,
                question=pending.get('question', ''),
                original_request=original,
                pending_buttons=[],
            )
        else:
            self._add_bubble(f'Anotado sobre {name}.', is_user=False, tone='persona')
        self._scroll_bottom()
        return True

    def _retry_original_request_with_context(self, original_request: str, context_note: str):
        if not original_request:
            return
        if not self._api.get_active_provider():
            self._add_bubble('Entendi o contexto, mas preciso de um provider configurado para continuar o pedido.', is_user=False, is_error=True)
            return
        self._append_detective_fact('contexto', context_note)
        self._last_user_text = original_request
        self._allow_next_persona_save = True
        self._auto_execute_next_single_agenda = False
        prompt = self._detective_continuation_prompt('contexto', context_note)
        self._history.append({'role': 'user', 'content': prompt})
        self._start_stream()

    def _continue_after_persona_clarification(self, name: str, answer: str, question: str, original_request: str, pending_buttons: list | None = None, can_auto_execute: bool = False):
        if not original_request:
            return
        if not self._api.get_active_provider():
            self._add_bubble('Entendi o contexto, mas preciso de um provider configurado para continuar o pedido.', is_user=False, is_error=True)
            return
        if not self._detective_original_request:
            self._begin_detective_case(original_request, pending_buttons or [])
        elif pending_buttons:
            self._detective_pending_buttons = list(pending_buttons)
        self._last_user_text = original_request
        self._auto_execute_next_single_agenda = False
        self._allow_next_persona_save = True
        self._continuation_pending_buttons = list(pending_buttons or self._detective_pending_buttons or [])
        self._continuation_subject = name
        prompt = self._detective_continuation_prompt(name, answer)
        self._history.append({'role': 'user', 'content': prompt})
        self._start_stream()

    def _should_hold_persona_save(self, action: dict) -> str | None:
        if not isinstance(action, dict) or action.get('type') != 'save_memory':
            return None
        if (action.get('category') or '').strip().lower() != 'persona':
            return None
        try:
            from core.database import SeqDB
            text = ' '.join([getattr(self, '_last_user_text', ''), str(action.get('subject') or ''), str(action.get('note') or '')])
            db = SeqDB.get_instance()
            subject_name = self._simple_person_subject(str(action.get('subject') or ''))
            if subject_name and not db.persona_has_person_relation(subject_name):
                return subject_name
            return None
        except Exception:
            return None

    def _render_action_buttons(self, buttons: list):
        if not buttons:
            return
        self._clear_dynamic_buttons()
        btn_css = f"\n            QPushButton {{\n                background: rgba(201,168,76, 30);\n                border: 1px solid rgba(201,168,76, 120);\n                color: {GOLD_BRIGHT_CSS};\n                font-size: 11px;\n                font-family: {FONT};\n                border-radius: 7px;\n                padding: 6px 12px;\n                font-weight: bold;\n            }}\n            QPushButton:hover {{ background: rgba(201,168,76, 70); }}\n        "
        persona_btn_css = f"\n            QPushButton {{\n                background: rgba(156,104,230, 28);\n                border: 1px solid rgba(156,104,230, 125);\n                color: rgba(112, 61, 166, 230);\n                font-size: 11px;\n                font-family: {FONT};\n                border-radius: 7px;\n                padding: 6px 12px;\n                font-weight: bold;\n            }}\n            QPushButton:hover {{ background: rgba(156,104,230, 58); }}\n        "
        for btn_def in buttons[:3]:
            label = btn_def.get('label', 'Ação')
            confirm_action = self._extract_button_action(btn_def)
            btn = QPushButton(label)
            is_persona_action = isinstance(confirm_action, dict) and self._action_type_str(confirm_action) == 'ask_person_relation'
            btn.setStyleSheet(persona_btn_css if is_persona_action else btn_css)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if confirm_action:
                btn.clicked.connect(lambda checked=False, a=confirm_action: self._on_button_action(a))
            self._btn_layout.insertWidget(self._btn_layout.count() - 1, btn)
        self._btn_container.show()
        self._scroll_bottom()

    def _parse_and_execute(self, text: str, auto_execute: bool = True):
        from ui.agenda_skills import parse_skills_json, expand_chat_buttons
        data = parse_skills_json(text)
        if not data:
            return
        executor = self._agenda_executor_instance()
        has_tools = bool(data.get('actions') or data.get('buttons'))
        if has_tools:
            self._show_thinking_orb('tool')
            QApplication.processEvents()
        if isinstance(data.get('clarification'), dict) and getattr(self, '_gate_mode', '') != 'execute_agenda':
            self._remove_thinking_orb()
            return
        
        all_buttons = data.get('buttons', []) + data.get('pending_buttons', [])
        buttons = expand_chat_buttons(user_text=getattr(self, '_last_user_text', ''), buttons=all_buttons)[:3]
        
        if self._auto_execute_next_single_agenda:
            agenda_actions = [a for a in data.get('actions', []) if a.get('type') in {'create_schedule', 'update_schedule', 'reschedule', 'mark_done', 'delete_schedule', 'postpone'}]
            if agenda_actions and not buttons:
                buttons = [{'confirm_action': agenda_actions[0]}]
                
        user_text = getattr(self, '_last_user_text', '')
        from ui.agenda_skills import normalize_action
        _AGENDA_TYPES = {'create_schedule', 'update_schedule', 'reschedule', 'mark_done', 'delete_schedule', 'postpone'}
        agenda_acted = False
        for action in data.get('actions', []):
            held_name = None
            if getattr(self, '_gate_mode', '') != 'execute_agenda':
                held_name = None if self._allow_next_persona_save else self._should_hold_persona_save(action)
            if held_name:
                self._pending_persona_clarification = {'name': held_name, 'buttons': buttons, 'user_text': user_text}
                self._add_bubble(f"Isso parece importante para sua Persona, mas antes preciso entender melhor: quem é {held_name} para você?", is_user=False, tone='persona')
                self._remove_thinking_orb()
                return
            atype = normalize_action(action, user_text).get('type', '')
            gate_mode = getattr(self, '_gate_mode', 'conversation')
            if atype in _AGENDA_TYPES:
                if gate_mode != 'execute_agenda' and not getattr(self, '_compliance_must_execute', False):
                    continue
                result = executor.execute(normalize_action(action, user_text), user_text=user_text)
                self._add_action_indicator(result, tone='normal')
                agenda_acted = True
                self._compliance_must_execute = False
            elif auto_execute or action.get('type') == 'save_memory':
                result = executor.execute(normalize_action(action, user_text), user_text=user_text)
                tone = 'persona' if (action.get('category') or '').strip().lower() == 'persona' else 'normal'
                self._add_action_indicator(result, tone=tone)
        # If the AI already created the agenda via "actions", don't also show create-buttons
        if agenda_acted:
            self._auto_execute_next_single_agenda = False
            self._allow_next_persona_save = False
            self._continuation_pending_buttons = []
            self._continuation_subject = ''
            self._clear_detective_case()
            self._remove_thinking_orb()
            return
        if buttons:
            actions = self._agenda_actions_from_buttons(buttons)
            if self._auto_execute_next_single_agenda and len(actions) == 1:
                action = normalize_action(actions[0], user_text)
                result = executor.execute(action, user_text=user_text)
                self._add_bubble(result, is_user=False)
                self._auto_execute_next_single_agenda = False
                self._allow_next_persona_save = False
                self._continuation_pending_buttons = []
                self._continuation_subject = ''
                self._remove_thinking_orb()
                return
            self._render_action_buttons(buttons)
        self._auto_execute_next_single_agenda = False
        self._allow_next_persona_save = False
        self._remove_thinking_orb()

    def _on_button_action(self, action):
        self._clear_dynamic_buttons()
        if isinstance(action, dict) and action.get('type') == 'ask_person_relation':
            name = action.get('name', 'essa pessoa')
            self._add_bubble(f"Quem é {name} para você? Pode me responder do seu jeito, em uma frase curta.", is_user=False, tone='persona')
            self._scroll_bottom()
            return
        executor = self._agenda_executor_instance()
        from ui.agenda_skills import normalize_action
        user_text = getattr(self, '_last_user_text', '')
        self._show_thinking_orb('tool')
        QApplication.processEvents()
        if isinstance(action, list):
            results = [executor.execute(normalize_action(a, user_text), user_text=user_text) for a in action]
            result = ' / '.join(results)
        else:
            result = executor.execute(normalize_action(action, user_text), user_text=user_text)
        self._remove_thinking_orb()
        self._add_bubble(result, is_user=False)
        self._scroll_bottom()

    def _scroll_bottom(self):
        QTimer.singleShot(40, lambda : self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum()))

    def _refresh_provider_label(self):
        provider = self._api.get_active_provider()
        if provider:
            info = self._api.get_provider_info(provider)
            self.provider_lbl.setText(f"Nigel  |  {info.get('name', provider.title())}")
            return
        self.provider_lbl.setText('Nigel  |  Configure um provider')

    def _toggle_menu(self):
        if self._flyout is None:
            self._flyout = FlyoutMenu(always_on_top=self._aot)
            self._flyout.settings_requested.connect(self._open_settings)
            self._flyout.quit_requested.connect(QApplication.quit)
            self._flyout.always_on_top_toggled.connect(self._set_always_on_top)
        if self._flyout.isVisible():
            self._flyout.hide()
            return
        self._flyout.show_smart(self)

    def _open_settings(self):
        from ui.settings import SettingsWindow
        if self._settings is None:
            self._settings = SettingsWindow()
            self._settings.settings_saved.connect(self._on_settings_saved)
            self._settings.resize_bar.connect(self._apply_resize)
        sc = QApplication.primaryScreen().availableGeometry()
        sw = self._settings
        sw.move(sc.width() // 2 - sw.width() // 2, sc.height() // 2 - sw.height() // 2)
        sw.show()
        sw.raise_()

    def _on_settings_saved(self):
        self._api.reload()
        self._refresh_provider_label()

    def _apply_resize(self, w: int, h: int):
        self._BAR_W = w
        self._BAR_H = h
        self.prompt_row.setFixedHeight(h)
        if self._collapsed:
            self.setFixedSize(w, h)
        else:
            self.setFixedSize(w, h + self._CHAT_H)
        self.update()

    def _set_always_on_top(self, enabled: bool):
        self._aot = enabled
        flags = self.windowFlags()
        if enabled:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()
        self.raise_()
        from core.api_client import APIClient
        APIClient().save_settings({'NIGEL_ALWAYS_ON_TOP': 'true' if enabled else 'false'})

    def _toggle_brain(self):
        self.brain_btn.clear_badge()
        from ui.brain_panel import BrainPanel
        if self._brain is None:
            self._brain = BrainPanel()
        if self._brain.isVisible():
            self._brain.hide()
            return
        self._brain.show_near_bar(self)

    def set_schedule_checker(self, checker):
        self._schedule_checker = checker

    def show_schedule_notification(self, count: int):
        self.brain_btn.set_badge(count)

    def handle_overdue(self, items: list):
        self.show_schedule_notification(len(items))
        from ui.notification import ScheduleAlertDialog
        for item in items:
            ScheduleAlertDialog.show_alert(item, anchor=self)
