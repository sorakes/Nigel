"""
ui/theme.py — Design system do Nigel: tema Grafite.

Paleta neutra em cinza-carvão. O dourado da identidade (#C9A84C, exatamente o RGB
do logo) é usado como ACENTO, nunca como superfície: aparece no logo, no anel de
foco, no orb "pensando" e no badge de notificação. Bordas, botões e hovers são cinza.

Regra: nenhum arquivo de UI deve escrever cor literal. Se falta um token aqui,
adicione aqui.
"""

from PyQt6.QtGui import QColor, QPen, QPainterPath
from PyQt6.QtCore import QRectF


def css(c: QColor, alpha: int | None = None) -> str:
    """QColor -> string 'rgba(r, g, b, a)' para stylesheet. `alpha` (0-255) sobrepõe."""
    a = c.alpha() if alpha is None else max(0, min(255, alpha))
    return f'rgba({c.red()}, {c.green()}, {c.blue()}, {a})'


# ---------------------------------------------------------------------------
# Superfícies
# ---------------------------------------------------------------------------
C_BG        = QColor(26, 27, 30, 246)    # fundo de janela/barra (translúcido)
C_BG_SOLID  = QColor(26, 27, 30)         # mesmo tom, opaco (popups, dropdowns)
C_SURFACE   = QColor(35, 37, 41)         # cards, bolhas da IA
C_RAISED    = QColor(42, 45, 50)         # inputs, hover, botão secundário
C_OVERLAY   = QColor(48, 52, 57)         # pressed, item selecionado

# ---------------------------------------------------------------------------
# Bordas
# ---------------------------------------------------------------------------
C_BORDER    = QColor(51, 54, 59)         # 1px padrão
C_BORDER_HI = QColor(74, 78, 85)         # hover / divisória forte

# ---------------------------------------------------------------------------
# Texto
# ---------------------------------------------------------------------------
C_TEXT      = QColor(232, 233, 235)      # primário   (~13:1 sobre C_BG)
C_TEXT_2    = QColor(155, 161, 170)      # secundário (~6:1 sobre C_SURFACE)
C_TEXT_MUTE = QColor(107, 112, 120)      # placeholder, timestamp, desabilitado
C_TEXT_ON_ACCENT = QColor(26, 27, 30)    # texto sobre preenchimento dourado

# ---------------------------------------------------------------------------
# Identidade — o dourado do logo. NÃO alterar o PNG em lugar nenhum.
# ---------------------------------------------------------------------------
C_GOLD      = QColor(201, 168, 76)       # RGB idêntico ao logo
C_GOLD_SOFT = QColor(223, 192, 102)      # dourado legível como texto sobre escuro
C_GOLD_DIM  = QColor(201, 168, 76, 26)   # fundo de destaque discreto

# ---------------------------------------------------------------------------
# Semânticos (dessaturados para fundo escuro)
# ---------------------------------------------------------------------------
C_SUCCESS   = QColor(82, 196, 126)
C_DANGER    = QColor(229, 100, 92)
C_WARNING   = QColor(221, 160, 90)
C_INFO      = QColor(91, 168, 196)
C_PERSONA   = QColor(155, 126, 222)      # bolha roxa da curiosidade

# ---------------------------------------------------------------------------
# Mensagens
# ---------------------------------------------------------------------------
C_USER_MSG    = C_RAISED
C_AI_MSG      = C_SURFACE
C_ERR_MSG     = QColor(229, 100, 92, 38)
C_PERSONA_MSG = QColor(155, 126, 222, 30)

# ---------------------------------------------------------------------------
# Tipografia
# ---------------------------------------------------------------------------
FONT_FAMILY = 'Segoe UI'                 # nome puro, para QFont(...)
FONT_MONO_FAMILY = 'Consolas'
FONT = "'Segoe UI', 'Inter', 'Arial', sans-serif"        # stack, para stylesheet
FONT_MONO = "'Consolas', 'Segoe UI Mono', monospace"

FS_XS, FS_SM, FS_MD, FS_BASE, FS_LG, FS_XL = 10, 11, 12, 13, 14, 16

# Espaçamento e raios
SP_1, SP_2, SP_3, SP_4, SP_5, SP_6 = 4, 8, 12, 16, 20, 24
R_SM, R_MD, R_LG, R_XL = 6, 10, 14, 18

# ---------------------------------------------------------------------------
# Atalhos CSS dos tokens mais usados
# ---------------------------------------------------------------------------
BG_CSS        = css(C_BG)
BG_SOLID_CSS  = css(C_BG_SOLID)
SURFACE_CSS   = css(C_SURFACE)
RAISED_CSS    = css(C_RAISED)
OVERLAY_CSS   = css(C_OVERLAY)
BORDER_CSS    = css(C_BORDER)
BORDER_HI_CSS = css(C_BORDER_HI)
TEXT_CSS      = css(C_TEXT)
TEXT_2_CSS    = css(C_TEXT_2)
TEXT_MUTE_CSS = css(C_TEXT_MUTE)
GOLD_CSS      = css(C_GOLD)
GOLD_SOFT_CSS = css(C_GOLD_SOFT)
GOLD_DIM_CSS  = css(C_GOLD_DIM)
SUCCESS_CSS   = css(C_SUCCESS)
DANGER_CSS    = css(C_DANGER)
WARNING_CSS   = css(C_WARNING)
INFO_CSS      = css(C_INFO)
PERSONA_CSS   = css(C_PERSONA)
SEL_CSS       = css(C_GOLD, 70)          # seleção de texto


# ---------------------------------------------------------------------------
# Botões
# ---------------------------------------------------------------------------
BTN_PRIMARY = f"""
    QPushButton {{
        background: {RAISED_CSS};
        color: {TEXT_CSS};
        border: 1px solid {BORDER_HI_CSS};
        border-radius: {R_MD}px;
        padding: 7px 16px;
        font-size: {FS_BASE}px;
        font-weight: 600;
        font-family: {FONT};
    }}
    QPushButton:hover   {{ background: {OVERLAY_CSS}; border-color: {css(C_GOLD, 120)}; }}
    QPushButton:pressed {{ background: {SURFACE_CSS}; }}
    QPushButton:disabled {{
        background: {css(C_SURFACE, 120)};
        color: {TEXT_MUTE_CSS};
        border-color: {css(C_BORDER, 140)};
    }}
"""

BTN_SECONDARY = f"""
    QPushButton {{
        background: transparent;
        color: {TEXT_2_CSS};
        border: 1px solid {BORDER_CSS};
        border-radius: {R_MD}px;
        padding: 8px 16px;
        font-size: {FS_MD}px;
        font-family: {FONT};
    }}
    QPushButton:hover   {{ background: {RAISED_CSS}; color: {TEXT_CSS}; border-color: {BORDER_HI_CSS}; }}
    QPushButton:pressed {{ background: {SURFACE_CSS}; }}
"""

BTN_GHOST = f"""
    QPushButton {{
        background: transparent;
        color: {TEXT_2_CSS};
        border: 1px solid {BORDER_CSS};
        border-radius: {R_SM}px;
        padding: 3px 10px;
        font-size: {FS_SM}px;
        font-family: {FONT};
    }}
    QPushButton:hover   {{ background: {RAISED_CSS}; color: {TEXT_CSS}; }}
    QPushButton:pressed {{ background: {SURFACE_CSS}; }}
"""

BTN_DANGER = f"""
    QPushButton {{
        background: transparent;
        color: {DANGER_CSS};
        border: 1px solid {css(C_DANGER, 90)};
        border-radius: {R_SM}px;
        padding: 3px 10px;
        font-size: {FS_SM}px;
        font-family: {FONT};
    }}
    QPushButton:hover   {{ background: {css(C_DANGER, 32)}; }}
    QPushButton:pressed {{ background: {css(C_DANGER, 60)}; }}
"""

# Botao quadrado de icone/glifo: BTN_PRIMARY tem padding lateral demais e
# esmaga o conteudo quando a largura e' fixa (ex.: o botao de enviar 32x32).
BTN_ICON = f"""
    QPushButton {{
        background: {RAISED_CSS};
        color: {TEXT_CSS};
        border: 1px solid {BORDER_CSS};
        border-radius: {R_SM}px;
        padding: 0;
        font-size: {FS_LG}px;
        font-family: {FONT};
    }}
    QPushButton:hover   {{ background: {OVERLAY_CSS}; border-color: {BORDER_HI_CSS}; }}
    QPushButton:pressed {{ background: {SURFACE_CSS}; }}
    QPushButton:disabled {{ color: {TEXT_MUTE_CSS}; }}
"""

BTN_CLOSE = f"""
    QPushButton {{
        background: transparent;
        color: {TEXT_2_CSS};
        border: none;
        border-radius: {R_SM}px;
        font-size: {FS_MD}px;
        font-weight: bold;
    }}
    QPushButton:hover   {{ background: {css(C_DANGER, 45)}; color: {DANGER_CSS}; }}
    QPushButton:pressed {{ background: {css(C_DANGER, 80)}; }}
"""


# ---------------------------------------------------------------------------
# Campos de entrada
# ---------------------------------------------------------------------------
INPUT_STYLE = f"""
    QLineEdit {{
        background: {RAISED_CSS};
        color: {TEXT_CSS};
        border: 1px solid {BORDER_CSS};
        border-radius: {R_SM}px;
        padding: 6px 10px;
        font-size: {FS_MD}px;
        font-family: {FONT};
        selection-background-color: {SEL_CSS};
    }}
    QLineEdit:focus {{ border: 1px solid {GOLD_CSS}; background: {OVERLAY_CSS}; }}
"""

COMBOBOX_STYLE = f"""
    QComboBox {{
        background: {RAISED_CSS};
        color: {TEXT_CSS};
        border: 1px solid {BORDER_CSS};
        border-radius: {R_SM}px;
        padding: 5px 8px;
        font-size: {FS_MD}px;
        font-family: {FONT};
        selection-background-color: {SEL_CSS};
    }}
    QComboBox:hover {{ border-color: {BORDER_HI_CSS}; }}
    QComboBox:focus {{ border: 1px solid {GOLD_CSS}; }}
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 22px;
        border-left: 1px solid {BORDER_CSS};
        border-top-right-radius: {R_SM}px;
        border-bottom-right-radius: {R_SM}px;
        background: {css(C_OVERLAY, 160)};
    }}
    QComboBox::down-arrow {{ image: none; }}
    QComboBox QAbstractItemView {{
        background: {css(C_BG_SOLID)};
        border: 1px solid {BORDER_CSS};
        color: {TEXT_CSS};
        selection-background-color: {OVERLAY_CSS};
        outline: 0;
        padding: 4px;
        border-radius: {R_SM}px;
    }}
    QComboBox QAbstractItemView::item {{
        padding: 5px 8px;
        border-radius: 5px;
        min-height: 24px;
    }}
"""

SPINBOX_STYLE = f"""
    QSpinBox {{
        background: {RAISED_CSS};
        color: {TEXT_CSS};
        border: 1px solid {BORDER_CSS};
        border-radius: {R_SM}px;
        padding: 5px 8px;
        font-size: {FS_MD}px;
        font-family: {FONT};
        min-width: 70px;
    }}
    QSpinBox:focus {{ border: 1px solid {GOLD_CSS}; }}
    QSpinBox::up-button, QSpinBox::down-button {{
        width: 18px;
        background: {css(C_OVERLAY, 160)};
        border: none;
    }}
    QSpinBox::up-button   {{ border-top-right-radius: {R_SM}px; }}
    QSpinBox::down-button {{ border-bottom-right-radius: {R_SM}px; }}
    QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background: {BORDER_HI_CSS}; }}
    QSpinBox::up-arrow, QSpinBox::down-arrow {{ image: none; }}
"""

TEXTEDIT_STYLE = f"""
    QTextEdit, QPlainTextEdit {{
        background: {RAISED_CSS};
        color: {TEXT_CSS};
        border: 1px solid {BORDER_CSS};
        border-radius: {R_SM}px;
        padding: 8px;
        font-size: {FS_MD}px;
        font-family: {FONT};
        selection-background-color: {SEL_CSS};
    }}
    QTextEdit:focus, QPlainTextEdit:focus {{ border: 1px solid {GOLD_CSS}; }}
"""

SCROLL_STYLE = f"""
    QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
    QScrollBar:vertical {{
        background: transparent;
        width: 6px;
        border-radius: 3px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {css(C_BORDER_HI, 170)};
        border-radius: 3px;
        min-height: 24px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {css(C_TEXT_MUTE, 200)}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
"""


# ---------------------------------------------------------------------------
# Cards, abas, sidebar, toggles
# ---------------------------------------------------------------------------
CARD_STYLE = f"""
    QFrame {{
        background: {SURFACE_CSS};
        border: 1px solid {BORDER_CSS};
        border-radius: {R_MD}px;
    }}
"""

TAB_ON = f"""
    QPushButton {{
        background: {RAISED_CSS};
        color: {TEXT_CSS};
        border: 1px solid {BORDER_HI_CSS};
        border-radius: {R_SM}px;
        font-size: {FS_MD}px;
        font-weight: 600;
        font-family: {FONT};
        text-align: left;
    }}
"""

TAB_OFF = f"""
    QPushButton {{
        background: transparent;
        color: {TEXT_2_CSS};
        border: 1px solid transparent;
        border-radius: {R_SM}px;
        font-size: {FS_MD}px;
        font-family: {FONT};
        text-align: left;
    }}
    QPushButton:hover {{ background: {css(C_RAISED, 140)}; color: {TEXT_CSS}; }}
"""

SIDEBAR_BTN = f"""
    QPushButton {{
        background: transparent;
        color: {TEXT_2_CSS};
        border: none;
        border-radius: {R_SM}px;
        font-size: {FS_BASE}px;
        font-weight: 500;
        font-family: {FONT};
        text-align: left;
        padding-left: 12px;
    }}
    QPushButton:hover   {{ background: {css(C_RAISED, 150)}; color: {TEXT_CSS}; }}
    QPushButton:checked {{ background: {RAISED_CSS}; color: {TEXT_CSS}; font-weight: 600; }}
"""

TOGGLE_ON = f"""
    QPushButton {{
        background: {css(C_SUCCESS, 45)};
        color: {SUCCESS_CSS};
        border: 1px solid {css(C_SUCCESS, 120)};
        border-radius: {R_SM}px;
        font-size: {FS_XS}px;
        font-weight: 700;
        font-family: {FONT};
    }}
    QPushButton:hover {{ background: {css(C_SUCCESS, 70)}; }}
"""

TOGGLE_OFF = f"""
    QPushButton {{
        background: {RAISED_CSS};
        color: {TEXT_MUTE_CSS};
        border: 1px solid {BORDER_CSS};
        border-radius: {R_SM}px;
        font-size: {FS_XS}px;
        font-weight: 700;
        font-family: {FONT};
    }}
    QPushButton:hover {{ background: {OVERLAY_CSS}; color: {TEXT_2_CSS}; }}
"""


# ---------------------------------------------------------------------------
# Bolhas de chat
# ---------------------------------------------------------------------------
def _bubble(bg: str, fg: str, border: str = 'transparent') -> str:
    return (f"background: {bg}; color: {fg}; border: 1px solid {border};"
            f" border-radius: 12px; padding: 9px 13px;"
            f" font-size: {FS_BASE}px; font-family: {FONT};")

BUBBLE_AI      = _bubble(SURFACE_CSS, TEXT_CSS)
BUBBLE_USER    = _bubble(RAISED_CSS, TEXT_CSS, BORDER_CSS)
BUBBLE_PERSONA = _bubble(css(C_PERSONA_MSG), TEXT_CSS, css(C_PERSONA, 110))
BUBBLE_ERROR   = _bubble(css(C_ERR_MSG), DANGER_CSS, css(C_DANGER, 90))


# ---------------------------------------------------------------------------
# Dias do calendário
# ---------------------------------------------------------------------------
def _day(bg: str, fg: str, border: str = 'transparent', weight: int = 400) -> str:
    return f"""
    QPushButton {{
        background: {bg}; color: {fg};
        border: 1px solid {border};
        border-radius: {R_SM}px;
        font-size: {FS_SM}px; font-weight: {weight};
        font-family: {FONT};
    }}
    QPushButton:hover {{ background: {OVERLAY_CSS}; color: {TEXT_CSS}; }}
    """

CALENDAR_DAY          = _day('transparent', TEXT_2_CSS)
CALENDAR_DAY_TODAY    = _day(GOLD_DIM_CSS, GOLD_SOFT_CSS, css(C_GOLD, 110), 700)
CALENDAR_DAY_OTHER    = _day('transparent', TEXT_MUTE_CSS)
CALENDAR_DAY_SELECTED = _day(RAISED_CSS, TEXT_CSS, BORDER_HI_CSS, 600)


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------
LABEL_TITLE   = f"color: {TEXT_CSS}; font-size: {FS_XL}px; font-weight: 700; font-family: {FONT};"
LABEL_SECTION = (f"color: {TEXT_MUTE_CSS}; font-size: {FS_XS}px; font-weight: 700;"
                 f" font-family: {FONT}; letter-spacing: 1.4px;")
LABEL_BODY    = f"color: {TEXT_CSS}; font-size: {FS_BASE}px; font-family: {FONT};"
LABEL_SMALL   = f"color: {TEXT_2_CSS}; font-size: {FS_SM}px; font-family: {FONT};"
LABEL_MUTED   = f"color: {TEXT_MUTE_CSS}; font-size: {FS_SM}px; font-style: italic; font-family: {FONT};"
LABEL_ACCENT  = f"color: {GOLD_SOFT_CSS}; font-size: {FS_BASE}px; font-weight: 600; font-family: {FONT};"
LABEL_STATUS  = f"color: {TEXT_MUTE_CSS}; font-size: {FS_SM}px; font-style: italic; font-family: {FONT};"


# ---------------------------------------------------------------------------
# Pintura (QPainter)
# ---------------------------------------------------------------------------
def paint_panel(widget, painter, radius: float = R_XL, bg: QColor | None = None,
                border: QColor | None = None, border_width: float = 1.0):
    """Pinta um painel com fundo, borda e cantos arredondados (helper de paintEvent)."""
    from PyQt6.QtGui import QPainter
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    _bg = bg if bg is not None else C_BG
    _border = border if border is not None else C_BORDER

    rect = QRectF(widget.rect()).adjusted(
        border_width / 2, border_width / 2,
        -border_width / 2, -border_width / 2,
    )
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)

    painter.setPen(QPen(_border, border_width))
    painter.setBrush(_bg)
    painter.drawPath(path)


# ---------------------------------------------------------------------------
# Compatibilidade — nomes do tema antigo (Baunilha & Ouro).
# Mapeados para o papel SEMÂNTICO que exerciam, não para "dourado -> dourado":
# a maior parte do uso de C_GOLD era borda/hover estrutural, que agora é cinza.
# Remover conforme cada arquivo de UI for migrado.
# ---------------------------------------------------------------------------
C_PANEL      = C_BG
C_CREAM      = C_SURFACE
C_INPUT      = C_RAISED
C_HOVER      = QColor(42, 45, 50, 150)
C_GOLD_BRIGHT = C_GOLD_SOFT
C_GOLD_DEEP   = C_GOLD
C_GOLD_BTN    = C_RAISED
C_GOLD_BTN_H  = C_OVERLAY
C_GOLD_BTN_P  = C_SURFACE
C_GOLD_TOGGLE = C_BORDER_HI
C_TEXT_MID    = C_TEXT_2
C_TEXT_LIGHT  = C_TEXT_MUTE
C_DIVIDER     = C_BORDER

PANEL_CSS       = BG_CSS
CREAM_CSS       = SURFACE_CSS
INPUT_CSS       = RAISED_CSS
GOLD_BRIGHT_CSS = GOLD_SOFT_CSS
GOLD_BTN_CSS    = RAISED_CSS
GOLD_BTN_H_CSS  = OVERLAY_CSS
GOLD_BTN_P_CSS  = SURFACE_CSS
TEXT_MID_CSS    = TEXT_2_CSS
TEXT_LIGHT_CSS  = TEXT_MUTE_CSS
DIVIDER_CSS     = BORDER_CSS
HOVER_CSS       = css(C_RAISED, 150)

LABEL_GOLD = LABEL_ACCENT
_TAB_ON, _TAB_OFF = TAB_ON, TAB_OFF
