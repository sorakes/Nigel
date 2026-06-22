"""
ui/theme.py
Paleta centralizada e helpers de estilo — tema Baunilha & Ouro.
"""

from PyQt6.QtGui import QColor, QPen, QPainterPath
from PyQt6.QtCore import QRectF

# --- Cores Base ---
# Usadas para construir os estilos CSS e para pintura manual com QPainter.

# Cores de fundo
C_PANEL = QColor(250, 246, 238, 240)
C_CREAM = QColor(244, 239, 226, 248)
C_INPUT = QColor(255, 253, 247, 215)
C_HOVER = QColor(201, 168, 76, 28)

# Dourados
C_GOLD = QColor(201, 168, 76, 190)
C_GOLD_BRIGHT = QColor(218, 183, 60, 225)
C_GOLD_DEEP = QColor(158, 122, 22, 245)
C_GOLD_BTN = QColor(201, 168, 76, 215)
C_GOLD_BTN_H = QColor(220, 185, 70, 240)
C_GOLD_BTN_P = QColor(155, 118, 18, 245)
C_GOLD_TOGGLE = QColor(201, 168, 76, 200)

# Texto
C_TEXT = QColor(42, 30, 8, 222)
C_TEXT_MID = QColor(100, 78, 28, 185)
C_TEXT_LIGHT = QColor(155, 128, 65, 145)

# Outros
C_DIVIDER = QColor(201, 168, 76, 60)

# Mensagens
C_USER_MSG = QColor(201, 168, 76, 155)
C_AI_MSG = QColor(244, 239, 226, 240)
C_ERR_MSG = QColor(200, 60, 40, 90)


# --- Estilos CSS ---
# Usados para aplicar estilos a widgets com setStyleSheet().

PANEL_CSS = 'rgba(250, 246, 238, 240)'
CREAM_CSS = 'rgba(244, 239, 226, 248)'
INPUT_CSS = 'rgba(255, 253, 247, 215)'
GOLD_CSS = 'rgba(201, 168, 76,  190)'
GOLD_BRIGHT_CSS = 'rgba(218, 183, 60,  225)'
GOLD_BTN_CSS = 'rgba(201, 168, 76,  215)'
GOLD_BTN_H_CSS = 'rgba(220, 185, 70,  240)'
GOLD_BTN_P_CSS = 'rgba(155, 118, 18,  245)'
TEXT_CSS = 'rgba(42,  30,  8,  222)'
TEXT_MID_CSS = 'rgba(100, 78,  28, 185)'
TEXT_LIGHT_CSS = 'rgba(155, 128, 65, 145)'
DIVIDER_CSS = 'rgba(201, 168, 76,  60)'
HOVER_CSS = 'rgba(201, 168, 76,  28)'

FONT = "'Segoe UI', 'Inter', 'Arial', sans-serif"
FONT_MONO = "'Consolas', 'Segoe UI Mono', monospace"


# --- Estilos de Componentes (StyleSheets) ---

BTN_PRIMARY = f"""
    QPushButton {{
        background: {GOLD_BTN_CSS};
        color: {TEXT_CSS};
        border: 1px solid {GOLD_CSS};
        border-radius: 11px;
        padding: 9px 18px;
        font-size: 13px;
        font-weight: 600;
        font-family: {FONT};
    }}
    QPushButton:hover  {{ background: {GOLD_BTN_H_CSS}; border-color: {GOLD_BRIGHT_CSS}; }}
    QPushButton:pressed {{ background: {GOLD_BTN_P_CSS}; color: rgba(255,248,220,240); }}
    QPushButton:disabled {{ background: rgba(200,185,145,80); color: rgba(120,100,60,120); border-color: rgba(180,155,80,60); }}
"""

BTN_GHOST = f"""
    QPushButton {{
        background: transparent;
        color: {TEXT_MID_CSS};
        border: 1px solid {GOLD_CSS};
        border-radius: 8px;
        padding: 3px 10px;
        font-size: 11px;
        font-family: {FONT};
    }}
    QPushButton:hover  {{ background: {GOLD_BTN_CSS}; color: {TEXT_CSS}; }}
    QPushButton:pressed {{ background: {GOLD_BTN_P_CSS}; }}
"""

BTN_CLOSE = f"""
    QPushButton {{
        background: transparent;
        color: {TEXT_MID_CSS};
        border: none;
        border-radius: 13px;
        font-size: 12px;
        font-weight: bold;
    }}
    QPushButton:hover  {{ background: rgba(200, 50, 30, 70); color: rgba(255,80,60,220); }}
    QPushButton:pressed {{ background: rgba(200, 50, 30, 100); }}
"""


INPUT_STYLE = f"""
    QLineEdit {{
        background: {INPUT_CSS};
        color: {TEXT_CSS};
        border: 1px solid {GOLD_CSS};
        border-radius: 8px;
        color: {TEXT_CSS};
        padding: 6px 10px;
        font-size: 12px;
        font-family: {FONT_MONO};
        selection-background-color: rgba(201,168,76,110);
    }}
    QLineEdit:focus {{
        border: 1.5px solid {GOLD_BRIGHT_CSS};
        background: rgba(255,254,249,240);
    }}
"""

COMBOBOX_STYLE = f"""
    QComboBox {{
        background: {INPUT_CSS};
        color: {TEXT_CSS};
        border: 1px solid {GOLD_CSS};
        border-radius: 8px;
        color: {TEXT_CSS};
        padding: 5px 8px;
        font-size: 12px;
        font-family: {FONT};
        selection-background-color: rgba(201,168,76,110);
    }}
    QComboBox:focus {{ border: 1.5px solid {GOLD_BRIGHT_CSS}; }}
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 22px;
        border-left: 1px solid {GOLD_CSS};
        border-top-right-radius: 8px;
        border-bottom-right-radius: 8px;
        background: rgba(201,168,76,30);
    }}
    QComboBox::down-arrow {{
        image: none;
    }}
    QComboBox QAbstractItemView {{
        background: rgba(252,248,240,255);
        border: 1px solid {GOLD_CSS};
        color: {TEXT_CSS};
        selection-background-color: rgba(201,168,76,90);
        outline: 0;
        padding: 4px;
        border-radius: 8px;
    }}
    QComboBox QAbstractItemView::item {{
        padding: 5px 8px;
        border-radius: 5px;
        min-height: 24px;
    }}
"""

SPINBOX_STYLE = f"""
    QSpinBox {{
        background: {INPUT_CSS};
        color: {TEXT_CSS};
        border: 1px solid {GOLD_CSS};
        border-radius: 8px;
        color: {TEXT_CSS};
        padding: 5px 8px;
        font-size: 12px;
        font-family: {FONT};
        min-width: 70px;
    }}
    QSpinBox:focus {{ border: 1.5px solid {GOLD_BRIGHT_CSS}; }}
    QSpinBox::up-button, QSpinBox::down-button {{
        width: 18px;
        background: rgba(201,168,76,35);
        border: none;
    }}
    QSpinBox::up-button   {{ border-top-right-radius: 8px; }}
    QSpinBox::down-button {{ border-bottom-right-radius: 8px; }}
    QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
        background: rgba(201,168,76,75);
    }}
    QSpinBox::up-arrow  {{ image: none; }}
    QSpinBox::down-arrow {{ image: none; }}
"""

SCROLL_STYLE = """
    QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; border: none; }
    QScrollBar:vertical {
        background: rgba(201,168,76,18);
        width: 5px;
        border-radius: 2px;
        margin: 0;
    }
    QScrollBar::handle:vertical {
        background: rgba(201,168,76,130);
        border-radius: 2px;
        min-height: 20px;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""

# --- Estilos de Texto (para QLabel) ---

LABEL_TITLE = f"color: {TEXT_CSS}; font-size: 16px; font-weight: 700; font-family: {FONT};"
LABEL_SECTION = f"color: {TEXT_MID_CSS}; font-size: 10px; font-weight: 700; font-family: {FONT}; letter-spacing: 1.4px;"
LABEL_BODY = f"color: {TEXT_CSS}; font-size: 13px; font-family: {FONT};"
LABEL_SMALL = f"color: {TEXT_MID_CSS}; font-size: 11px; font-family: {FONT};"
LABEL_MUTED = f"color: {TEXT_LIGHT_CSS}; font-size: 11px; font-style: italic; font-family: {FONT};"
LABEL_GOLD = f"color: {GOLD_BTN_P_CSS}; font-size: 13px; font-weight: 600; font-family: {FONT};"


# --- Funções de Pintura (QPainter) ---

def paint_panel(widget, painter, radius: float = 20.0, bg: QColor | None = None, border: QColor | None = None, border_width: float = 1.0):
    """
    Pinta um painel com fundo, borda e cantos arredondados.
    Usado como um helper para o paintEvent de widgets customizados.

    Args:
        widget: O widget no qual desenhar (para obter o rect).
        painter: O QPainter a ser usado.
        radius: O raio dos cantos.
        bg: A cor de fundo (QColor). Padrão: C_PANEL.
        border: A cor da borda (QColor). Padrão: C_GOLD.
        border_width: A largura da borda.
    """
    from PyQt6.QtGui import QPainter
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    _bg = bg or C_PANEL
    _border = border or C_GOLD

    rect = QRectF(widget.rect()).adjusted(
        border_width / 2, border_width / 2,
        -border_width / 2, -border_width / 2
    )

    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)

    painter.setPen(QPen(_border, border_width))
    painter.setBrush(_bg)
    painter.drawPath(path)
