"""
ui/bar.py  —  Barra flutuante com chat integrado (Vanilla & Gold)

Arquitetura:
- Quando colapsada : 60px  — só o prompt pill
- Quando expandida : 60px + 440px — chat aparece acima do prompt

Um único campo de input. Zero janelas extras.
"""
import math
import os
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLineEdit, QPushButton, QApplication, QFrame, QLabel, QScrollArea, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QPointF, QRectF, QObject, QEvent, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen, QPainterPath
from dotenv import load_dotenv
load_dotenv()
from core.api_client import APIClient
from ui.theme import (
    paint_panel, css, C_BG, C_RAISED, C_OVERLAY, C_BORDER, C_BORDER_HI,
    C_TEXT, C_TEXT_2, C_TEXT_MUTE, C_GOLD, C_GOLD_SOFT, C_PERSONA,
    C_DANGER, C_WARNING, C_INFO,
    C_AI_MSG, C_USER_MSG, C_ERR_MSG, C_PERSONA_MSG,
    TEXT_CSS, TEXT_2_CSS, TEXT_MUTE_CSS, RAISED_CSS, OVERLAY_CSS,
    BORDER_CSS, DANGER_CSS, PERSONA_CSS, SEL_CSS,
    FONT, FS_BASE,
    SCROLL_STYLE, BTN_GHOST, BTN_PRIMARY, LABEL_ACCENT, LABEL_STATUS,
)
from ui.icons import BrainButton, IconButton

_ACTIVE_BAR_WORKERS = set()

class ThinkingOrb(QWidget):
    """Indicador fluido: 3 gotas quicando, com transição de cor e dissolução."""
    COLORS = {
        'thinking': (C_GOLD, C_GOLD_SOFT),
        'review':   (C_PERSONA, QColor(190, 170, 240)),
        'gate':     (C_INFO, QColor(140, 200, 220)),
        'audit':    (C_WARNING, QColor(240, 190, 140)),
        'tool':     (C_INFO, QColor(140, 200, 220)),
        'subagent': (C_PERSONA, QColor(190, 170, 240)),
        'idle':     (C_TEXT_MUTE, C_TEXT_2),
    }
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
            p.setPen(QPen(QColor(C_TEXT.red(), C_TEXT.green(), C_TEXT.blue(), int(90 * alpha)), 1.0))
            p.drawEllipse(QPointF(x, cy), rx, ry)
            shine = QColor(255, 255, 255, int(70 * alpha))
            p.setBrush(shine)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(x - rx * 0.32, cy - ry * 0.34), rx * 0.26, ry * 0.26)

def md_to_html(text: str) -> str:
    """Converte o markdown basico que o modelo usa em HTML para o QLabel.

    Sem isso o usuario le `**Reuniao**` com os asteriscos na tela. O texto e'
    escapado ANTES da conversao: a resposta pode conter dados externos (assunto
    de e-mail, titulo de evento) e nao deve virar markup.
    """
    import html as _html
    import re as _re

    out = _html.escape(text or '')
    out = _re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', out, flags=_re.DOTALL)
    out = _re.sub(r'(?<![\w*])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\w*])', r'<i>\1</i>', out)
    out = _re.sub(r'`([^`]+)`', r'<code>\1</code>', out)
    out = _re.sub(r'^[ \t]*[-*+][ \t]+', '&#8226;&nbsp;', out, flags=_re.MULTILINE)
    return out.replace(chr(10), '<br>')


class MessageBubble(QFrame):

    def __init__(self, text: str, is_user: bool = False, is_error: bool = False, tone: str = 'normal', max_width: int = 420, parent=None):
        super().__init__(parent)
        self.is_user = is_user
        self.is_error = is_error
        self.tone = tone
        self._raw = text
        if is_error:
            self._bg = C_ERR_MSG
            self._border = C_DANGER
            txt_css = DANGER_CSS
        elif is_user:
            self._bg = C_USER_MSG
            self._border = C_BORDER_HI
            txt_css = TEXT_CSS
        elif tone == 'persona':
            self._bg = C_PERSONA_MSG
            self._border = QColor(C_PERSONA.red(), C_PERSONA.green(), C_PERSONA.blue(), 130)
            txt_css = TEXT_CSS
        else:
            self._bg = C_AI_MSG
            self._border = C_BORDER
            txt_css = TEXT_CSS
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 3, 0, 3)
        self.label = QLabel(md_to_html(text))
        self.label.setTextFormat(Qt.TextFormat.RichText)
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
        self.label.setText(md_to_html(self._raw))

    def set_text(self, text: str):
        self._raw = text
        self.label.setText(md_to_html(text))

    def set_persona_tone(self):
        self.tone = 'persona'
        self._bg = C_PERSONA_MSG
        self._border = QColor(C_PERSONA.red(), C_PERSONA.green(), C_PERSONA.blue(), 130)
        self.label.setStyleSheet(f"QLabel {{ color:{TEXT_CSS}; padding:9px 13px; font-size:{FS_BASE}px; font-family:{FONT}; line-height:1.5; background:transparent; }}")
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
            p.setBrush(C_OVERLAY)
        elif self._hov:
            p.setBrush(C_RAISED)
        else:
            p.setBrush(Qt.GlobalColor.transparent)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(2, 2, 32, 32)
        dot_c = C_GOLD_SOFT if self._hov else C_RAISED
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
            c = C_GOLD
        elif self._hov:
            c = C_TEXT
        else:
            c = C_TEXT_MUTE
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
            p.setBrush(C_BORDER_HI)
            p.setPen(Qt.PenStyle.NoPen)
        else:
            p.setBrush(C_RAISED)
            p.setPen(Qt.PenStyle.NoPen)
        p.drawPath(path)
        p.setBrush(C_TEXT)
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
            return f"\n                QPushButton {{\n                    background:transparent; border:none; border-radius:8px;\n                    padding:8px 14px 8px 10px; text-align:left;\n                    font-size:13px; font-family:{FONT}; color:{color};\n                }}\n                QPushButton:hover {{ background:{hbg}; color:{hcolor}; }}\n                QPushButton:pressed {{ background:{OVERLAY_CSS}; }}\n            "
        self.btn_settings = QPushButton('Configurações')
        self.btn_settings.setStyleSheet(_s(TEXT_2_CSS, RAISED_CSS, TEXT_CSS))
        self.btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_settings.clicked.connect(lambda : (self.hide(), self.settings_requested.emit()))
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f'background:{BORDER_CSS}; margin:2px 4px;')
        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(4, 2, 2, 2)
        bottom_row.setSpacing(8)
        self.pin_toggle = SmoothToggle(self._aot)
        self.pin_toggle.toggled.connect(self._toggle_pin)
        pin_lbl = QLabel('Sempre visível')
        pin_lbl.setStyleSheet(f"color: {TEXT_CSS}; font-size: 11px; font-family: {FONT};")
        self.btn_quit = QPushButton('Sair')
        self.btn_quit.setStyleSheet(_s(css(C_DANGER, 190), css(C_DANGER, 40), DANGER_CSS))
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
        paint_panel(self, p, radius=14, bg=C_BG, border=C_BORDER)

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
        # Loop com function calling nativo + subagentes (ver secao "Agente v2" abaixo).
        self._agent_worker = None
        self._agent_registry = None
        self._event_refs = None
        self._pending_confirm = None
        self._bg_call = None
        self._agent_buf = ''
        self._agent_asked = None
        self._pending_agent_reveal = None
        self._thinking_orb = None
        self._stream_phase = 'idle'
        self._thinking_timer = QTimer(self)
        self._thinking_timer.timeout.connect(self._tick_thinking)
        self._thinking_step = 0
        self._last_user_text = ''
        self._response_revealed = False
        self._reveal_safety_timer = QTimer(self)
        self._reveal_safety_timer.setSingleShot(True)
        self._reveal_safety_timer.timeout.connect(self._on_reveal_safety_timeout)
        self._brain = None
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
        self.provider_lbl.setStyleSheet(LABEL_ACCENT)
        self._refresh_provider_label()
        self.status_lbl = QLabel('')
        self.status_lbl.setStyleSheet(LABEL_STATUS)
        self.clear_btn = QPushButton('Limpar')
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
        div_chat.setStyleSheet(f'background:{BORDER_CSS};')
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
        self.input.setPlaceholderText('Pergunte qualquer coisa…')
        self.input.setStyleSheet(f"\n            QLineEdit {{\n                background: transparent;\n                border: none;\n                color: {TEXT_CSS};\n                font-size: 14px;\n                font-family: {FONT};\n                selection-background-color: {SEL_CSS};\n            }}\n        ")
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
        paint_panel(self, p, radius=r, bg=C_BG, border=C_BORDER)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None:
            if not (event.buttons() & Qt.MouseButton.LeftButton):
                # O botao ja foi solto mas o mouseReleaseEvent nao chegou —
                # acontece com janela sem moldura + sempre-no-topo em certas
                # condicoes no Windows. Sem isso o arraste "gruda": a janela
                # continua pulando pro cursor a cada clique seguinte, mesmo
                # sem o botao pressionado, e o clique nunca chega no widget
                # de baixo porque a janela se move debaixo do cursor antes.
                self._drag_pos = None
            else:
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
        if self._agent_worker is not None and self._agent_worker.isRunning():
            self._agent_worker.stop()
            self._agent_worker = None
        self._add_bubble(text, is_user=True)
        self._history.append({'role': 'user', 'content': text})
        self._last_user_text = text
        if not self._api.get_active_provider():
            self._add_bubble('Nenhum provider de IA configurado.\nAbra Configurações (4 pontinhos) e adicione uma chave de API.',
                             is_user=False, is_error=True)
            return
        self._start_agent()

    # ------------------------------------------------------------------
    # Agente v2 — loop com function calling nativo e subagentes
    # ------------------------------------------------------------------

    def _agent_system_prompt(self) -> str:
        from core.agent.prompts import orchestrator_prompt
        persona_txt, known_txt = '', ''
        try:
            from core.storage import load_config
            p = load_config().get('persona') or {}
            partes = [f"Nome: {p['name']}" for _ in (1,) if p.get('name')]
            if p.get('email'):
                partes.append(f"E-mail: {p['email']}")
            for fato in (p.get('facts') or [])[:12]:
                partes.append(f"- {fato}")
            persona_txt = chr(10).join(partes)
        except Exception:
            pass
        try:
            # Só um índice curto de nomes: o detalhe o memory_agent busca sob
            # demanda, em vez de inflar o prompt de toda mensagem.
            from core.database import NigelDB
            graph = NigelDB.get_instance().get_knowledge_graph(limit=80)
            nomes = [ (n.get('title') or n.get('subject') or '').strip()
                      for n in graph.get('nodes', []) ]
            nomes = [n for n in nomes if n][:40]
            if nomes:
                known_txt = ', '.join(nomes)
        except Exception:
            pass
        return orchestrator_prompt(persona_txt, known_txt)

    def _start_agent(self):
        from ui.agent_worker import spawn
        from core.tools import build_orchestrator_registry
        from core.tools.refs import EventRefCache

        if self._agent_worker is not None and self._agent_worker.isRunning():
            self._agent_worker.stop()
        if self._agent_registry is None:
            try:
                self._agent_registry = build_orchestrator_registry()
            except Exception as e:
                self._add_bubble(f'Não consegui montar as ferramentas: {e}',
                                 is_user=False, is_error=True)
                return
        if self._event_refs is None:
            self._event_refs = EventRefCache()

        self._response_revealed = False
        self._agent_buf = ''
        self._agent_asked = None
        self._pending_confirm = None
        self._clear_dynamic_buttons()
        self.send_btn.setEnabled(False)
        self.status_lbl.setText('pensando…')
        self._show_thinking_orb()
        self._stream_phase = 'thinking'
        if self._thinking_orb is not None:
            self._thinking_orb.set_phase('thinking')
        if not self._thinking_timer.isActive():
            self._thinking_timer.start(16)

        w = spawn(self._agent_system_prompt(), list(self._history),
                  self._agent_registry, event_refs=self._event_refs)
        w.text_delta.connect(self._on_agent_text)
        w.tool_started.connect(self._on_agent_tool_start)
        w.tool_finished.connect(self._on_agent_tool_end)
        w.phase_changed.connect(self._on_agent_phase)
        w.asked.connect(self._on_agent_ask)
        w.confirm_requested.connect(self._on_agent_confirm)
        w.answer_ready.connect(self._on_agent_answer)
        w.failed.connect(self._on_agent_failed)
        self._agent_worker = w
        w.start()

    def _on_agent_text(self, delta: str):
        # Texto de uma iteração que ainda vai chamar ferramenta é preâmbulo
        # ("deixa eu ver sua agenda…"): vira status, não balão. Só a resposta
        # final vira bolha — senão sairiam dois ou três balões por mensagem.
        self._agent_buf += delta

    def _on_agent_phase(self, phase: str):
        self._stream_phase = phase
        if self._thinking_orb is not None:
            self._thinking_orb.set_phase(phase)

    def _on_agent_tool_start(self, name: str, label: str, icon: str):
        self.status_lbl.setText(f'{label}…')

    def _on_agent_tool_end(self, name: str, msg: str, ok: bool, icon: str):
        if msg:
            self._add_action_indicator(('✓ ' if ok else '✕ ') + msg,
                                       tone='normal' if ok else 'error', icon=icon)
        self.status_lbl.setText('')

    def _on_agent_ask(self, data: dict):
        self._agent_asked = data or {}

    def _on_agent_confirm(self, name: str, label: str, icon: str):
        # Ferramenta irreversível (enviar e-mail, apagar...): o loop já parou
        # sozinho e devolveu a pergunta como texto de resposta normal (vira
        # bolha via _on_agent_answer). Aqui só guardamos o que confirmar e
        # desenhamos os botões — reaproveitando o _btn_container que ficou
        # parado desde a limpeza do pipeline antigo justamente para isso.
        self._pending_confirm = {'worker': self._agent_worker, 'name': name,
                                  'label': label, 'icon': icon}
        self._render_confirm_buttons()

    def _render_confirm_buttons(self):
        self._clear_dynamic_buttons()
        btn_yes = QPushButton('Confirmar')
        btn_yes.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_yes.setStyleSheet(BTN_PRIMARY)
        btn_yes.clicked.connect(self._on_confirm_yes)
        btn_no = QPushButton('Cancelar')
        btn_no.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_no.setStyleSheet(BTN_GHOST)
        btn_no.clicked.connect(self._on_confirm_no)
        self._btn_layout.insertWidget(0, btn_no)
        self._btn_layout.insertWidget(0, btn_yes)
        self._btn_container.show()

    def _on_confirm_no(self):
        self._clear_dynamic_buttons()
        pc, self._pending_confirm = self._pending_confirm, None
        if not pc:
            return
        self._add_action_indicator(f'✕ Cancelado: {pc["label"]}', tone='error')
        self._history.append({'role': 'user',
                              'content': f'Não, não faça isso: {pc["label"]}.'})

    def _on_confirm_yes(self):
        self._clear_dynamic_buttons()
        pc, self._pending_confirm = self._pending_confirm, None
        if not pc:
            return
        worker = pc['worker']
        call = worker.result.pending_confirmation if worker and worker.result else None
        registry = getattr(worker, 'registry', None) if worker else None
        ctx = getattr(worker, 'ctx', None) if worker else None
        if not (call and registry and ctx):
            self._add_bubble('Não consegui recuperar a ação para confirmar — tenta de novo.',
                             is_user=False, is_error=True)
            return
        self.status_lbl.setText(f'{pc["label"]}…')
        from ui.agent_worker import BgCall
        bg = BgCall(lambda: registry.dispatch(call, ctx))

        def _done(result):
            self.status_lbl.setText('')
            msg = result.user_message or ('ok' if result.ok else (result.error or 'falhou'))
            self._add_action_indicator(('✓ ' if result.ok else '✕ ') + msg,
                                       tone='normal' if result.ok else 'error',
                                       icon=result.icon or pc['icon'])
            self._history.append({'role': 'user',
                                  'content': f'[Ação confirmada: {pc["label"]}] Resultado: {msg}'})
            self._bg_call = None
            self._start_agent()

        def _fail(err):
            self.status_lbl.setText('')
            self._add_bubble(f'Falha ao executar: {err}', is_user=False, is_error=True)
            self._bg_call = None

        bg.done.connect(_done)
        bg.failed.connect(_fail)
        self._bg_call = bg
        bg.start()

    def _on_agent_answer(self, text: str):
        visible = (text or '').strip() or (self._agent_buf or '').strip()
        if not visible:
            visible = 'Não consegui produzir uma resposta agora.'
        deferred = self._agent_asked is not None
        self._finish_agent(visible, deferred)

    def _on_agent_failed(self, msg: str):
        self._finish_agent(msg or 'Falha ao falar com a IA.', False, is_error=True)

    def _finish_agent(self, visible: str, deferred: bool, is_error: bool = False):
        if self._response_revealed:
            return
        self.status_lbl.setText('')
        self.send_btn.setEnabled(True)
        self._pending_agent_reveal = (visible, deferred, is_error)
        if not self._thinking_timer.isActive():
            self._thinking_timer.start(16)
        if self._thinking_orb is not None:
            # Revela pelo que vier primeiro: fim da animação ou 400 ms. O
            # timer antigo de 3,5 s era a única garantia de que o usuário
            # veria a resposta — aqui a garantia não depende da animação.
            self._thinking_orb.start_dissolve(on_done=self._reveal_agent)
            self._reveal_safety_timer.start(400)
            return
        self._reveal_agent()

    def _reveal_agent(self):
        if self._response_revealed or not getattr(self, '_pending_agent_reveal', None):
            return
        visible, deferred, is_error = self._pending_agent_reveal
        self._pending_agent_reveal = None
        self._response_revealed = True
        if self._reveal_safety_timer.isActive():
            self._reveal_safety_timer.stop()
        self._thinking_timer.stop()
        self._remove_thinking_orb()
        tone = 'persona' if deferred else 'normal'
        self._add_bubble(visible, is_user=False, is_error=is_error, tone=tone)
        if not is_error:
            self._history.append({'role': 'assistant', 'content': visible})
        self._agent_buf = ''
        self._stream_phase = 'idle'
        try:
            from ui.agenda_skills import trigger_ui_update
            trigger_ui_update()
        except Exception:
            pass

    def _bubble_max_width(self) -> int:
        return max(260, self._BAR_W - 88)

    def _tick_thinking(self):
        if self._thinking_orb is None:
            return
        self._thinking_step += 1
        # As fases do orb (thinking/tool/subagent/...) ja vem prontas de
        # `_on_agent_phase`. O pulso periodico so precisa manter a MESMA fase
        # em vez de reescreve-la — antes havia aqui uma traducao de nomes do
        # pipeline antigo que nao conhecia 'tool'/'subagent' e revertia a cor
        # do orb para dourado a cada 16ms, escondendo o feedback de ferramenta.
        self._thinking_orb.set_phase(self._stream_phase or 'thinking')
        self._thinking_orb.pulse()
        self._scroll_bottom()

    def _on_reveal_safety_timeout(self):
        if self._response_revealed:
            return
        if self._pending_agent_reveal:
            self._reveal_agent()
            return
        if self._thinking_orb is not None:
            self._remove_thinking_orb()
            self.send_btn.setEnabled(True)
            self._stream_phase = 'idle'

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

    def _add_action_indicator(self, text: str, tone: str = 'normal', icon: str = ''):
        from PyQt6.QtWidgets import QLabel, QWidget, QHBoxLayout
        from ui.theme import FONT
        row = QWidget()
        row.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        h = QHBoxLayout(row)
        h.setContentsMargins(20, 2, 20, 4)
        h.setSpacing(7)
        if icon:
            from ui.icons import IconWidget
            ic = IconWidget(icon, 16)
            ic.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            h.addWidget(ic, 0, Qt.AlignmentFlag.AlignVCenter)
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setMaximumWidth(self._bubble_max_width())
        lbl.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        color = {'persona': PERSONA_CSS, 'error': DANGER_CSS}.get(tone, TEXT_MUTE_CSS)
        lbl.setStyleSheet(f"color: {color}; font-family: {FONT}; font-size: 11px; background: transparent;")
        lbl.setContentsMargins(0, 0, 0, 0)
        h.addWidget(lbl, 1)
        self.msg_layout.insertWidget(self.msg_layout.count() - 1, row)
        self._scroll_bottom()

    def _clear_chat(self):
        self._history.clear()
        if self._agent_worker is not None and self._agent_worker.isRunning():
            self._agent_worker.stop()
        self._agent_worker = None
        if self._event_refs is not None:
            self._event_refs.clear()
        self._agent_buf = ''
        self._agent_asked = None
        self._pending_confirm = None
        self._pending_agent_reveal = None
        self._remove_thinking_orb()
        self._stream_phase = 'idle'
        self._thinking_timer.stop()
        self._clear_dynamic_buttons()
        self.status_lbl.setText('')
        self.send_btn.setEnabled(True)
        while self.msg_layout.count() > 1:
            item = self.msg_layout.takeAt(0)
            if item.widget():
                _w = item.widget()
                _w.setParent(None)   # tira da tela JA; deleteLater() so' libera depois
                _w.deleteLater()
        return

    def _clear_dynamic_buttons(self):
        if hasattr(self, '_btn_container') and self._btn_container:
            while self._btn_layout.count() > 1:
                item = self._btn_layout.takeAt(0)
                if item.widget():
                    _w = item.widget()
                    _w.setParent(None)   # tira da tela JA; deleteLater() so' libera depois
                    _w.deleteLater()
            self._btn_container.hide()
            return
        return
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

    def _open_settings(self, tab_index: int | None = None):
        from ui.settings import SettingsWindow
        if self._settings is None:
            self._settings = SettingsWindow()
            self._settings.settings_saved.connect(self._on_settings_saved)
            self._settings.resize_bar.connect(self._apply_resize)
        sc = QApplication.primaryScreen().availableGeometry()
        sw = self._settings
        sw.move(sc.width() // 2 - sw.width() // 2, sc.height() // 2 - sw.height() // 2)
        if tab_index is not None:
            sw.open_tab(tab_index)
        else:
            sw.show()
            sw.raise_()

    def open_sync_settings_onboarding(self):
        """Abre as configurações diretamente na aba de Sync e Composio para onboarding."""
        self._open_settings(tab_index=2)

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

    def handle_important_item(self, item: dict, source: str = ''):
        """Um e-mail importante chegou pelo polling: acende o badge e, se ligado,
        mostra um popup com o motivo e acoes rapidas — o Nigel age antes de ser
        perguntado, em vez de so avisar que algo aconteceu."""
        summary = item.get('ai_summary') or item.get('subject', '')
        print(f"[Nigel] {source}: {summary}" if source else f"[Nigel] {summary}")
        self.brain_btn.bump_badge()
        if os.getenv('NIGEL_EMAIL_POPUPS', '1').strip().lower() not in ('0', 'false', 'no'):
            from ui.notification import EmailAlertDialog
            EmailAlertDialog.show_alert(item, anchor=self)

    def handle_task_result(self, result: dict):
        """Uma tarefa autonoma (briefing matinal, verificacao de e-mail em
        background, prompt agendado) terminou. Sem isso o resumo so existia
        em `schedules.last_result` no banco — o sinal `task_executed` nunca
        tinha ouvinte nenhum na UI."""
        summary = (result.get('summary') or '').strip()
        if not result.get('success', True) or not summary:
            return
        ttype = result.get('type', '')
        if ttype not in ('daily_briefing', 'check_emails', 'agent_prompt'):
            return
        print(f"[Nigel] Tarefa concluida [{ttype}]: {summary[:80]}")
        self.brain_btn.bump_badge()
        from ui.notification import BriefingAlertDialog
        BriefingAlertDialog.show_alert(result, anchor=self)

    def handle_meeting_prep(self, event: dict, summary: str):
        """Uma reuniao real esta prestes a comecar: mostra o resumo que o
        MeetingPrepWorker montou (e-mails relacionados, contexto conhecido)
        antes que o usuario precise entrar as cegas."""
        print(f"[Nigel] Preparacao de reuniao: {event.get('summary','')} — {summary[:80]}")
        self.brain_btn.bump_badge()
        from ui.notification import BriefingAlertDialog
        BriefingAlertDialog.show_alert(
            {'type': 'meeting_prep', 'summary': summary, 'event': event, 'success': True},
            anchor=self)

    def handle_agenda_conflict(self, event_a: dict, event_b: dict):
        """Dois compromissos reais se sobrepoem no Google Calendar: avisa antes
        que o usuario descubra sozinho em cima da hora."""
        print(f"[Nigel] Conflito de agenda: {event_a.get('summary','')} x {event_b.get('summary','')}")
        self.brain_btn.bump_badge()
        if os.getenv('NIGEL_CONFLICT_POPUPS', '1').strip().lower() not in ('0', 'false', 'no'):
            from ui.notification import ConflictAlertDialog
            ConflictAlertDialog.show_alert(event_a, event_b, anchor=self)
