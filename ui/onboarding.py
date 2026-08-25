"""
ui/onboarding.py — Fluxo de primeira abertura do Nigel.

Antes, "onboarding" era só abrir a aba de Integrações direto — sem explicar
o que é o Composio, sem dizer onde pegar uma chave de LLM, sem contexto
nenhum. Isso é sustentável quando é você mesmo rodando o projeto, mas não
pra alguém baixando o repositório open source sem ninguém do lado explicando.

Este assistente guia por 4 passos (LLM → Composio → conectar o essencial →
pronto) e usa exatamente os mesmos mecanismos de salvamento que
`ui/settings.py` já usa (`APIClient.save_settings`, `ComposioManager`,
`ComposioToolkitCard`) — não é um caminho de configuração paralelo.
"""

from __future__ import annotations

import webbrowser

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QFrame, QStackedWidget, QApplication,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QPixmap

from ui.theme import (
    paint_panel, css, C_BG, C_BORDER, C_BORDER_HI, C_SUCCESS, C_TEXT,
    TEXT_CSS, TEXT_2_CSS, TEXT_MUTE_CSS, BORDER_CSS, SUCCESS_CSS,
    FONT, FS_XL, FS_BASE, FS_SM,
    BTN_PRIMARY, BTN_GHOST, INPUT_STYLE, LABEL_TITLE,
)
from ui.icons import IconWidget

# Provider recomendado por padrao — free tier generoso e rapido (ver README).
_DEFAULT_PROVIDER = 'groq'
_ONBOARDING_PROVIDER_LINKS = {
    'groq': 'https://console.groq.com/keys',
    'openai': 'https://platform.openai.com/api-keys',
    'gemini': 'https://aistudio.google.com/apikey',
    'openrouter': 'https://openrouter.ai/keys',
    'ollama_cloud': 'https://ollama.com/settings/keys',
}


def _step_dots(current: int, total: int) -> QWidget:
    row = QWidget()
    row.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    h = QHBoxLayout(row)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(6)
    h.addStretch()
    for i in range(total):
        dot = QLabel()
        dot.setFixedSize(7, 7)
        color = C_SUCCESS if i <= current else C_BORDER_HI
        dot.setStyleSheet(f"background: {css(color)}; border-radius: 3px;")
        h.addWidget(dot)
    h.addStretch()
    return row


class OnboardingWindow(QWidget):
    """Assistente de primeira abertura — LLM, Composio, conectar o essencial."""

    finished_flow = pyqtSignal()

    _STEP_TITLES = ('Bem-vindo', 'Modelo de IA', 'Composio', 'Conectar contas', 'Pronto')

    def __init__(self, parent=None):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # Ver o comentario em ui/settings.py: minimo + resize, sem tamanho
        # fixo e sem "corrigir" o tamanho num resizeEvent (isso trava a UI).
        self.setMinimumSize(460, 520)
        self.resize(460, 520)
        self._selected_provider = _DEFAULT_PROVIDER
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(16)

        header = QHBoxLayout()
        close_btn = QPushButton('✕')
        close_btn.setFixedSize(22, 22)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {TEXT_MUTE_CSS}; border: none; font-size: 13px; }}
            QPushButton:hover {{ color: {TEXT_CSS}; }}
        """)
        close_btn.clicked.connect(self._finish)
        header.addStretch()
        header.addWidget(close_btn)
        outer.addLayout(header)

        self._dots_slot = QVBoxLayout()
        outer.addLayout(self._dots_slot)

        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)

        self.stack.addWidget(self._page_welcome())
        self.stack.addWidget(self._page_llm())
        self.stack.addWidget(self._page_composio())
        self.stack.addWidget(self._page_connect())
        self.stack.addWidget(self._page_done())

        self._refresh_dots()

    def _refresh_dots(self):
        while self._dots_slot.count():
            item = self._dots_slot.takeAt(0)
            if item.widget():
                _w = item.widget()
                _w.setParent(None)   # tira da tela JA; deleteLater() so' libera depois
                _w.deleteLater()
        self._dots_slot.addWidget(_step_dots(self.stack.currentIndex(), len(self._STEP_TITLES)))

    def _goto(self, idx: int):
        self.stack.setCurrentIndex(idx)
        self._refresh_dots()
        if idx == 3:
            self._refresh_connect_status()

    # ------------------------------------------------------------ paginas

    def _page_welcome(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)
        lay.addStretch()

        import os
        logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets', 'nigel.png')
        if os.path.exists(logo_path):
            logo_lbl = QLabel()
            pix = QPixmap(logo_path).scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            logo_lbl.setPixmap(pix)
            logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(logo_lbl)

        title = QLabel('Bem-vindo ao Nigel')
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(LABEL_TITLE)
        lay.addWidget(title)

        desc = QLabel(
            'Seu assistente pessoal, com acesso à sua agenda, e-mail, Slack e mais — '
            'sempre com sua permissão antes de qualquer ação irreversível.\n\n'
            'Leva menos de 2 minutos pra configurar. Você pode pular qualquer '
            'passo e voltar depois em Configurações.'
        )
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet(f"color: {TEXT_2_CSS}; font-size: {FS_BASE}px; font-family: {FONT};")
        lay.addWidget(desc)
        lay.addStretch()

        next_btn = QPushButton('Começar')
        next_btn.setStyleSheet(BTN_PRIMARY)
        next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        next_btn.setFixedHeight(38)
        next_btn.clicked.connect(lambda: self._goto(1))
        lay.addWidget(next_btn)
        return w

    def _page_llm(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)

        lay.addWidget(self._step_title('Escolha um modelo de IA'))
        desc = QLabel(
            'O Nigel usa a chave de API que você fornecer — você paga só o que usar, '
            'direto com o provedor, sem intermediário. Groq tem um plano gratuito '
            'generoso e é rápido, por isso é a recomendação padrão.'
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_2_CSS}; font-size: {FS_SM}px; font-family: {FONT};")
        lay.addWidget(desc)

        picker_row = QHBoxLayout()
        picker_row.setSpacing(6)
        self._provider_btns = {}
        from core.api_client import PROVIDERS
        for key in ('groq', 'openai', 'gemini', 'openrouter', 'ollama_cloud'):
            info = PROVIDERS[key]
            btn = QPushButton(info['name'])
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setCheckable(True)
            btn.setChecked(key == self._selected_provider)
            btn.clicked.connect(lambda checked, k=key: self._select_provider(k))
            self._provider_btns[key] = btn
            picker_row.addWidget(btn)
        lay.addLayout(picker_row)
        self._restyle_provider_btns()

        key_lbl = QLabel('Chave de API:')
        key_lbl.setStyleSheet(f"color: {TEXT_2_CSS}; font-size: {FS_SM}px; font-family: {FONT};")
        lay.addWidget(key_lbl)

        key_row = QHBoxLayout()
        self._llm_key_input = QLineEdit()
        self._llm_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._llm_key_input.setStyleSheet(INPUT_STYLE)
        self._llm_key_input.setPlaceholderText('Cole sua chave aqui…')
        get_key_btn = QPushButton('Pegar chave ↗')
        get_key_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        get_key_btn.setStyleSheet(BTN_GHOST)
        get_key_btn.clicked.connect(self._open_provider_key_page)
        key_row.addWidget(self._llm_key_input, 1)
        key_row.addWidget(get_key_btn)
        lay.addLayout(key_row)

        lay.addStretch()
        lay.addLayout(self._nav_row(back_to=0, on_next=self._save_llm_and_continue))
        return w

    def _restyle_provider_btns(self):
        for key, btn in self._provider_btns.items():
            on = key == self._selected_provider
            btn.setChecked(on)
            btn.setStyleSheet(BTN_PRIMARY if on else BTN_GHOST)

    def _select_provider(self, key: str):
        self._selected_provider = key
        self._restyle_provider_btns()

    def _open_provider_key_page(self):
        url = _ONBOARDING_PROVIDER_LINKS.get(self._selected_provider)
        if url:
            webbrowser.open(url)

    def _save_llm_and_continue(self):
        from core.api_client import APIClient, PROVIDERS
        key = self._llm_key_input.text().strip()
        info = PROVIDERS[self._selected_provider]
        if key:
            APIClient().save_settings({
                info['env_key']: key,
                f"NIGEL_{self._selected_provider.upper()}_MODEL": info['default_model'],
                'NIGEL_ACTIVE_PROVIDER': self._selected_provider,
            })
        self._goto(2)

    def _page_composio(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)

        lay.addWidget(self._step_title('Conecte suas contas com o Composio'))
        desc = QLabel(
            'O Nigel usa o Composio para conectar com segurança sua agenda, '
            'e-mail e outros apps — ele nunca vê nem guarda suas senhas, só '
            'gerencia a permissão que você concede a cada serviço. É gratuito '
            'para começar, sem cartão de crédito.'
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_2_CSS}; font-size: {FS_SM}px; font-family: {FONT};")
        lay.addWidget(desc)

        key_lbl = QLabel('Composio API Key:')
        key_lbl.setStyleSheet(f"color: {TEXT_2_CSS}; font-size: {FS_SM}px; font-family: {FONT};")
        lay.addWidget(key_lbl)

        key_row = QHBoxLayout()
        self._composio_key_input = QLineEdit()
        self._composio_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._composio_key_input.setStyleSheet(INPUT_STYLE)
        self._composio_key_input.setPlaceholderText('Cole sua chave aqui…')
        get_key_btn = QPushButton('Pegar chave ↗')
        get_key_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        get_key_btn.setStyleSheet(BTN_GHOST)
        get_key_btn.clicked.connect(lambda: webbrowser.open('https://app.composio.dev'))
        key_row.addWidget(self._composio_key_input, 1)
        key_row.addWidget(get_key_btn)
        lay.addLayout(key_row)

        lay.addStretch()
        lay.addLayout(self._nav_row(back_to=1, on_next=self._save_composio_and_continue))
        return w

    def _save_composio_and_continue(self):
        from core.composio_manager import ComposioManager
        from core.api_client import APIClient
        key = self._composio_key_input.text().strip()
        if key:
            ComposioManager.get_instance().set_api_key(key)
            APIClient().save_settings({'COMPOSIO_API_KEY': key})
        self._goto(3)

    def _page_connect(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)

        lay.addWidget(self._step_title('Conecte o essencial'))
        desc = QLabel('Google Calendar é a agenda oficial do Nigel. Gmail e Slack são opcionais, dá pra conectar depois em Configurações.')
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_2_CSS}; font-size: {FS_SM}px; font-family: {FONT};")
        lay.addWidget(desc)

        from ui.settings import ComposioToolkitCard
        from core.composio_manager import TOOLKIT_GOOGLECALENDAR, TOOLKIT_GMAIL, TOOLKIT_SLACK
        self._connect_cards = [
            ComposioToolkitCard(TOOLKIT_GOOGLECALENDAR, 'Google Calendar', 'Agenda oficial do Nigel.',
                                is_official_agenda=True, icon='brand_gcal'),
            ComposioToolkitCard(TOOLKIT_GMAIL, 'Gmail', 'Leitura de e-mails.', icon='brand_gmail'),
            ComposioToolkitCard(TOOLKIT_SLACK, 'Slack', 'Canais e mensagens.', icon='brand_slack'),
        ]
        for card in self._connect_cards:
            lay.addWidget(card)

        lay.addStretch()
        lay.addLayout(self._nav_row(back_to=2, on_next=lambda: self._goto(4), next_label='Concluir'))
        return w

    def _refresh_connect_status(self):
        from core.composio_manager import ComposioManager
        cm = ComposioManager.get_instance()
        if not cm.is_configured():
            for card in getattr(self, '_connect_cards', []):
                card.set_not_configured()
            return
        for card in self._connect_cards:
            try:
                card.set_connected(cm.check_connection(card.toolkit, force_refresh=True))
            except Exception:
                pass

    def _page_done(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)
        lay.addStretch()

        icon = IconWidget('check', 40, color=C_SUCCESS)
        icon_row = QHBoxLayout()
        icon_row.addStretch()
        icon_row.addWidget(icon)
        icon_row.addStretch()
        lay.addLayout(icon_row)

        title = QLabel('Tudo pronto!')
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(LABEL_TITLE)
        lay.addWidget(title)

        desc = QLabel('O Nigel já está funcionando. Qualquer coisa que faltar conectar, '
                      'você encontra em Configurações → Integrações.')
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet(f"color: {TEXT_2_CSS}; font-size: {FS_BASE}px; font-family: {FONT};")
        lay.addWidget(desc)
        lay.addStretch()

        done_btn = QPushButton('Começar a usar')
        done_btn.setStyleSheet(BTN_PRIMARY)
        done_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        done_btn.setFixedHeight(38)
        done_btn.clicked.connect(self._finish)
        lay.addWidget(done_btn)
        return w

    # ------------------------------------------------------------ helpers

    def _step_title(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {TEXT_CSS}; font-family: {FONT}; font-size: {FS_XL}px; font-weight: 700;")
        return lbl

    def _nav_row(self, *, back_to: int, on_next, next_label: str = 'Continuar') -> QHBoxLayout:
        row = QHBoxLayout()
        back_btn = QPushButton('Voltar')
        back_btn.setStyleSheet(BTN_GHOST)
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(lambda: self._goto(back_to))
        skip_btn = QPushButton('Pular')
        skip_btn.setStyleSheet(BTN_GHOST)
        skip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        skip_btn.clicked.connect(lambda: self._goto(min(back_to + 2, 4)))
        next_btn = QPushButton(next_label)
        next_btn.setStyleSheet(BTN_PRIMARY)
        next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        next_btn.clicked.connect(on_next)
        row.addWidget(back_btn)
        row.addWidget(skip_btn)
        row.addStretch()
        row.addWidget(next_btn)
        return row

    def _finish(self):
        from core.storage import save_config
        save_config({'onboarding_completed': True})
        self.finished_flow.emit()
        self.close()

    def show_centered(self):
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.center().x() - self.width() // 2
        y = screen.center().y() - self.height() // 2
        self.move(x, y)
        # Modal pro app inteiro: a Bar tambem e' "sempre no topo", e duas
        # janelas do Nigel com a mesma prioridade disputando o clique e'
        # o jeito mais provavel do clique cair na janela errada. Modal
        # tambem faz sentido de UX — nao devia dar pra usar a barra no
        # meio do primeiro setup mesmo.
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.show()
        self.raise_()
        self.activateWindow()

    def paintEvent(self, event):
        p = QPainter(self)
        paint_panel(self, p, radius=20, bg=C_BG, border=C_BORDER)
