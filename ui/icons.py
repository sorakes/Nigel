"""
ui/icons.py — Ícones vetoriais premium (champagne & ouro).
Sem emoji nem cores saturadas; traço fino dourado.
"""
from __future__ import annotations
import math
import os
from PyQt6.QtCore import Qt, QRectF, pyqtSignal, QPointF
from PyQt6.QtGui import QPainter, QPen, QColor, QPainterPath, QFont, QPixmap, QIcon
from PyQt6.QtWidgets import QWidget
from ui.theme import (
    C_GOLD, C_GOLD_SOFT, C_TEXT, C_TEXT_2, C_TEXT_ON_ACCENT,
    C_RAISED, C_OVERLAY, C_INFO, FONT_FAMILY, R_SM,
)

_NIGEL_ICON_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets', 'nigel.png')
_nigel_pixmap: QPixmap | None = None

def _get_nigel_pixmap() -> QPixmap | None:
    global _nigel_pixmap
    if _nigel_pixmap is None and os.path.exists(_NIGEL_ICON_PATH):
        _nigel_pixmap = QPixmap(_NIGEL_ICON_PATH)
    return _nigel_pixmap

def _pen(color: QColor, w: float = 1.45) -> QPen:
    return QPen(color, w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)

def _paint_brand_svg(p: QPainter, rect: QRectF, hex_fill: str, viewbox: str, path_d: str):
    """Renderiza o path vetorial real da marca (Simple Icons, CC0) via QSvgRenderer
    — nao e' um desenho aproximado, e' a mesma geometria que o app real usa."""
    from PyQt6.QtSvg import QSvgRenderer
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}">'
           f'<path fill="#{hex_fill}" d="{path_d}"/></svg>')
    renderer = QSvgRenderer(bytes(svg, 'utf-8'))
    pad = min(rect.width(), rect.height()) * 0.09
    target = QRectF(rect.x() + pad, rect.y() + pad, rect.width() - 2 * pad, rect.height() - 2 * pad)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(p, target)
    p.restore()


def _paint_lettermark(p: QPainter, rect: QRectF, hex_color: str, letter: str):
    """Chip com a cor oficial da marca + inicial, para marcas sem path CC0
    disponivel (ver ui/brand_svgs.py) — nao tenta imitar a logo exata."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    side = min(rect.width(), rect.height()) * 0.86
    box = QRectF(rect.center().x() - side / 2, rect.center().y() - side / 2, side, side)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(f'#{hex_color}'))
    p.drawRoundedRect(box, side * 0.26, side * 0.26)
    p.setPen(QColor(255, 255, 255, 240))
    p.setFont(QFont(FONT_FAMILY, max(6, int(side * 0.5)), QFont.Weight.Bold))
    p.drawText(box, Qt.AlignmentFlag.AlignCenter, letter)
    p.restore()


def _paint_ui_svg(p: QPainter, rect: QRectF, viewbox: str, path_d: str, color: QColor):
    """Renderiza um icone de interface do Material Symbols na cor do tema.

    Diferente de `_paint_brand_svg`, a cor NAO e' fixa: icone de UI e' parte
    do tema, entao segue o `color` pedido como qualquer outro elemento.
    """
    from PyQt6.QtSvg import QSvgRenderer
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}">'
           f'<path fill="{color.name()}" d="{path_d}"/></svg>')
    renderer = QSvgRenderer(bytes(svg, 'utf-8'))
    pad = min(rect.width(), rect.height()) * 0.10
    target = QRectF(rect.x() + pad, rect.y() + pad, rect.width() - 2 * pad, rect.height() - 2 * pad)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(p, target)
    p.restore()


def paint_icon(p: QPainter, rect: QRectF, name: str, color: QColor | None = None, stroke: float = 1.5):
    """Desenha um icone vetorial num grid consistente, estilo Feather/Lucide:
    traco fino uniforme, cantos arredondados, sem preenchimentos solidos
    (exceto onde o preenchimento e' a propria convencao, como o play)."""
    if name.startswith('brand_'):
        brand = name[len('brand_'):]
        from ui.brand_svgs import BRAND_SVGS, LETTERMARKS
        if brand in BRAND_SVGS:
            _paint_brand_svg(p, rect, *BRAND_SVGS[brand])
            return
        if brand in LETTERMARKS:
            _paint_lettermark(p, rect, *LETTERMARKS[brand])
            return

    # Icones de interface reais (Material Symbols) — ver ui/ui_svgs.py. Os
    # desenhos a mao abaixo ficam como fallback pro que ainda nao migrou.
    from ui.ui_svgs import UI_SVGS
    if name in UI_SVGS:
        _paint_ui_svg(p, rect, *UI_SVGS[name], color or C_TEXT_2)
        return

    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    c = color or C_TEXT_2
    pen = _pen(c, stroke)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    pad = min(rect.width(), rect.height()) * 0.16
    r = QRectF(rect.x() + pad, rect.y() + pad, rect.width() - 2 * pad, rect.height() - 2 * pad)
    cx, cy = r.center().x(), r.center().y()
    w, h = r.width(), r.height()
    hw, hh = w / 2, h / 2

    if name == 'close':
        m = min(w, h) * 0.32
        p.drawLine(QPointF(cx - m, cy - m), QPointF(cx + m, cy + m))
        p.drawLine(QPointF(cx + m, cy - m), QPointF(cx - m, cy + m))

    elif name == 'check':
        path = QPainterPath()
        path.moveTo(cx - hw * 0.65, cy + hh * 0.05)
        path.lineTo(cx - hw * 0.15, cy + hh * 0.55)
        path.lineTo(cx + hw * 0.70, cy - hh * 0.50)
        p.drawPath(path)

    elif name == 'refresh':
        rr = min(w, h) * 0.36
        arc = QRectF(cx - rr, cy - rr, rr * 2, rr * 2)
        p.drawArc(arc, -40 * 16, 280 * 16)
        ax, ay = cx + rr * math.cos(math.radians(-40)), cy - rr * math.sin(math.radians(-40))
        tip = QPainterPath()
        tip.moveTo(ax, ay)
        tip.lineTo(ax - rr * 0.42, ay - rr * 0.06)
        tip.lineTo(ax - rr * 0.02, ay + rr * 0.46)
        p.drawPath(tip)

    elif name == 'settings':
        ring_r = min(w, h) * 0.24
        p.drawEllipse(QPointF(cx, cy), ring_r, ring_r)
        tooth_w, tooth_len = ring_r * 0.62, ring_r * 0.58
        for i in range(6):
            p.save()
            p.translate(cx, cy)
            p.rotate(i * 60)
            p.drawRoundedRect(QRectF(-tooth_w / 2, -(ring_r + tooth_len), tooth_w, tooth_len), 1, 1)
            p.restore()

    elif name == 'brain':
        # Chip de inteligencia: usado so no fallback (o logo real e' um bitmap).
        outer = QRectF(cx - hw * 0.62, cy - hh * 0.62, w * 0.62, h * 0.62)
        p.drawRoundedRect(outer, 2.2, 2.2)
        inner = QRectF(cx - hw * 0.30, cy - hh * 0.30, w * 0.30, h * 0.30)
        p.drawRoundedRect(inner, 1, 1)
        pin = hh * 0.20
        for dx, dy in ((0, -1), (0, 1)):
            p.drawLine(QPointF(cx - hw * 0.20, cy + dy * (hh * 0.62 + pin)),
                       QPointF(cx - hw * 0.20, cy + dy * hh * 0.62))
            p.drawLine(QPointF(cx + hw * 0.20, cy + dy * (hh * 0.62 + pin)),
                       QPointF(cx + hw * 0.20, cy + dy * hh * 0.62))
        for dx, dy in ((-1, 0), (1, 0)):
            p.drawLine(QPointF(cx + dx * (hw * 0.62 + pin), cy - hh * 0.20),
                       QPointF(cx + dx * hw * 0.62, cy - hh * 0.20))
            p.drawLine(QPointF(cx + dx * (hw * 0.62 + pin), cy + hh * 0.20),
                       QPointF(cx + dx * hw * 0.62, cy + hh * 0.20))

    elif name in ('calendar', 'gcalendar', 'agenda'):
        cal = QRectF(cx - hw * 0.62, cy - hh * 0.46, w * 0.62, h * 0.72)
        p.drawRoundedRect(cal, 2.2, 2.2)
        header_y = cal.top() + h * 0.20
        p.drawLine(QPointF(cal.left(), header_y), QPointF(cal.right(), header_y))
        p.drawLine(QPointF(cx - hw * 0.30, cal.top() - h * 0.10), QPointF(cx - hw * 0.30, header_y - h * 0.02))
        p.drawLine(QPointF(cx + hw * 0.30, cal.top() - h * 0.10), QPointF(cx + hw * 0.30, header_y - h * 0.02))

    elif name in ('memory', 'saved'):
        # "Camadas": chevrons abertos empilhados (nao fechados, para nao virar losango).
        def _layer(y):
            path = QPainterPath()
            path.moveTo(cx - hw * 0.60, y)
            path.lineTo(cx, y + hh * 0.20)
            path.lineTo(cx + hw * 0.60, y)
            p.drawPath(path)
        for dy in (-0.38, 0.0, 0.38):
            _layer(cy + dy * h)

    elif name == 'graph':
        pts = [(cx, cy - hh * 0.62), (cx + hw * 0.60, cy + hh * 0.42), (cx - hw * 0.60, cy + hh * 0.42)]
        for i in range(3):
            p.drawLine(QPointF(*pts[i]), QPointF(*pts[(i + 1) % 3]))
        node_r = min(w, h) * 0.09
        for px, py in pts:
            p.drawEllipse(QPointF(px, py), node_r, node_r)

    elif name == 'fit':
        m = min(w, h) * 0.06
        L = min(w, h) * 0.22
        corners = ((cx - hw + m, cy - hh + m, 1, 1), (cx + hw - m, cy - hh + m, -1, 1),
                   (cx - hw + m, cy + hh - m, 1, -1), (cx + hw - m, cy + hh - m, -1, -1))
        for x, y, sx, sy in corners:
            p.drawLine(QPointF(x, y), QPointF(x + L * sx, y))
            p.drawLine(QPointF(x, y), QPointF(x, y + L * sy))

    elif name == 'add':
        m = min(w, h) * 0.34
        p.drawLine(QPointF(cx - m, cy), QPointF(cx + m, cy))
        p.drawLine(QPointF(cx, cy - m), QPointF(cx, cy + m))

    elif name == 'clock':
        rr = min(w, h) * 0.40
        p.drawEllipse(QPointF(cx, cy), rr, rr)
        p.drawLine(QPointF(cx, cy), QPointF(cx, cy - rr * 0.55))
        p.drawLine(QPointF(cx, cy), QPointF(cx + rr * 0.42, cy + rr * 0.12))

    elif name == 'bell':
        path = QPainterPath()
        path.moveTo(cx - hw * 0.46, cy + hh * 0.18)
        path.lineTo(cx - hw * 0.46, cy - hh * 0.05)
        path.arcTo(QRectF(cx - hw * 0.46, cy - hh * 0.62, hw * 0.92, hh * 0.92), 180, -180)
        path.lineTo(cx + hw * 0.46, cy + hh * 0.18)
        p.drawPath(path)
        p.drawLine(QPointF(cx - hw * 0.58, cy + hh * 0.18), QPointF(cx + hw * 0.58, cy + hh * 0.18))
        clap = QPainterPath()
        clap.moveTo(cx - hw * 0.16, cy + hh * 0.34)
        clap.quadTo(cx, cy + hh * 0.56, cx + hw * 0.16, cy + hh * 0.34)
        p.drawPath(clap)

    elif name == 'manual':
        # Lapis: corpo + ponta, na diagonal classica de edicao.
        p.save()
        p.translate(cx, cy)
        p.rotate(-45)
        bl = min(w, h) * 0.56
        body = QRectF(-bl * 0.14, -bl * 0.62, bl * 0.28, bl * 1.0)
        p.drawRoundedRect(body, 1.2, 1.2)
        tip = QPainterPath()
        tip.moveTo(body.left(), body.bottom())
        tip.lineTo(body.right(), body.bottom())
        tip.lineTo(0, body.bottom() + bl * 0.30)
        tip.closeSubpath()
        p.drawPath(tip)
        p.drawLine(QPointF(body.left(), body.top() + bl * 0.16), QPointF(body.right(), body.top() + bl * 0.16))
        p.restore()

    elif name == 'ai':
        # Sparkle de 4 pontas.
        def _spark(px, py, r1, r2):
            path = QPainterPath()
            path.moveTo(px, py - r1)
            path.quadTo(px + r2 * 0.28, py - r2 * 0.28, px + r1, py)
            path.quadTo(px + r2 * 0.28, py + r2 * 0.28, px, py + r1)
            path.quadTo(px - r2 * 0.28, py + r2 * 0.28, px - r1, py)
            path.quadTo(px - r2 * 0.28, py - r2 * 0.28, px, py - r1)
            p.drawPath(path)
        _spark(cx, cy, min(w, h) * 0.44, min(w, h) * 0.44)

    elif name == 'email':
        mail = QRectF(cx - hw * 0.62, cy - hh * 0.42, w * 0.62, h * 0.60)
        p.drawRoundedRect(mail, 2, 2)
        p.drawLine(QPointF(mail.left() + 1, mail.top() + 1), QPointF(cx, cy + hh * 0.08))
        p.drawLine(QPointF(mail.right() - 1, mail.top() + 1), QPointF(cx, cy + hh * 0.08))

    elif name == 'send':
        # Aviaozinho de papel, preenchido — mais legivel em traco fino pequeno.
        path = QPainterPath()
        path.moveTo(cx - hw * 0.60, cy - hh * 0.02)
        path.lineTo(cx + hw * 0.62, cy - hh * 0.58)
        path.lineTo(cx + hw * 0.02, cy + hh * 0.60)
        path.lineTo(cx - hw * 0.14, cy + hh * 0.06)
        path.closeSubpath()
        p.setBrush(c)
        p.drawPath(path)
        p.drawLine(QPointF(cx - hw * 0.14, cy + hh * 0.06), QPointF(cx + hw * 0.62, cy - hh * 0.58))

    elif name == 'play':
        path = QPainterPath()
        path.moveTo(cx - hw * 0.30, cy - hh * 0.55)
        path.lineTo(cx + hw * 0.58, cy)
        path.lineTo(cx - hw * 0.30, cy + hh * 0.55)
        path.closeSubpath()
        p.setBrush(c)
        p.drawPath(path)

    elif name == 'pause':
        p.setBrush(c)
        bar_w, bar_h = w * 0.16, h * 0.60
        p.drawRoundedRect(QRectF(cx - hw * 0.46, cy - bar_h / 2, bar_w, bar_h), 1, 1)
        p.drawRoundedRect(QRectF(cx + hw * 0.46 - bar_w, cy - bar_h / 2, bar_w, bar_h), 1, 1)

    elif name == 'brand_web':
        rr = min(w, h) * 0.40
        p.setPen(_pen(C_INFO, stroke))
        p.drawEllipse(QPointF(cx, cy), rr, rr)
        p.drawEllipse(QRectF(cx - rr * 0.42, cy - rr, rr * 0.84, rr * 2))
        p.drawLine(QPointF(cx - rr, cy), QPointF(cx + rr, cy))

    elif name == 'brand_app':
        # Grid de apps (2x2 pontos): simbolo universal para "outro app
        # conectado" sem marca propria desenhada (Notion, Drive...).
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(C_INFO)
        dot_r = min(w, h) * 0.11
        for dx in (-1, 1):
            for dy in (-1, 1):
                p.drawEllipse(QPointF(cx + dx * hw * 0.34, cy + dy * hh * 0.34), dot_r, dot_r)

    elif name in ('task', 'tasks'):
        card = QRectF(cx - hw * 0.58, cy - hh * 0.62, w * 0.58, h * 0.62)
        p.drawRoundedRect(card, 2.2, 2.2)
        for i, frac in enumerate((0.28, 0.54, 0.80)):
            ly = card.top() + card.height() * frac
            lw = card.width() * (0.66 if i < 2 else 0.42)
            p.drawLine(QPointF(card.left() + card.width() * 0.16, ly), QPointF(card.left() + card.width() * 0.16 + lw, ly))

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
            p.setBrush(C_OVERLAY)
        elif self._hov:
            p.setBrush(C_RAISED)
        else:
            p.setBrush(Qt.GlobalColor.transparent)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(1, 1, self.width() - 2, self.height() - 2, R_SM, R_SM)
        # Icone segue a hierarquia de texto: apagado em repouso, claro sob o cursor.
        color = C_TEXT if (self._hov or self._prs) else C_TEXT_2
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

    def bump_badge(self, delta: int = 1):
        self.set_badge(self._badge + delta)

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
            # Ha algo novo: unico estado que ganha o dourado da identidade.
            p.setBrush(C_RAISED)
            p.setPen(QPen(C_GOLD, 1))
        elif self._prs:
            p.setBrush(C_OVERLAY)
            p.setPen(Qt.PenStyle.NoPen)
        elif self._hov:
            p.setBrush(C_RAISED)
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
            paint_icon(p, QRectF(4, 4, 24, 24), 'brain', C_GOLD_SOFT)
        if self._badge > 0:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(C_GOLD_SOFT)
            badge_rect = QRectF(self.width() - 14, -2, 14, 14)
            p.drawEllipse(badge_rect)
            p.setPen(QPen(C_TEXT_ON_ACCENT))
            f = QFont(FONT_FAMILY, 8)
            f.setBold(True)
            p.setFont(f)
            txt = str(self._badge) if self._badge < 10 else '9+'
            p.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, txt)

def source_icon_name(source: str, task_type: str = '') -> str:
    if task_type:
        tt = task_type.lower()
        if tt == 'check_emails':
            return 'email'
        if tt == 'daily_briefing':
            return 'agenda'
        if tt == 'agent_prompt':
            return 'ai'
        if tt == 'reminder':
            return 'bell'
    return {'manual': 'manual', 'ai': 'ai', 'outlook': 'email', 'gmail': 'email', 'googlecalendar': 'calendar'}.get(source, 'bell')



def make_icon(name: str, size: int = 14, color: QColor | None = None) -> QIcon:
    """Renderiza um icone vetorial num QIcon, para uso nativo em QPushButton/QAction.

    Necessario porque o sizeHint de um QPushButton ignora layouts filhos: botoes
    montados com um IconWidget dentro colapsam para uma largura minima.
    """
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    paint_icon(p, QRectF(0, 0, size, size), name, color or C_TEXT_2)
    p.end()
    return QIcon(pm)
