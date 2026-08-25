"""
ui/settings.py  —  Janela de configurações (Vanilla & Gold) com suporte nativo e 100% assíncrono ao Composio.

Inclui:
- Seletor de provider e modelos LLM
- Gerenciamento de chaves do Composio e status de conexões OAuth (Notion, Google Calendar, Gmail, Outlook)
- Controle de tamanho da barra, memória e persona
- Execução não-bloqueante em background (zero travamento na interface)
"""
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QFrame, QScrollArea, QSpinBox, QGraphicsOpacityEffect,
    QStackedWidget, QButtonGroup, QTextEdit, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QRectF, QThread, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QColor, QPainter, QPen, QPainterPath

from ui.theme import (
    paint_panel, css, C_BG, C_SURFACE, C_RAISED, C_BORDER, C_BORDER_HI,
    
    C_SUCCESS, C_WARNING, FONT, FONT_MONO,
    FS_SM, R_SM,
    SURFACE_CSS, RAISED_CSS, OVERLAY_CSS, BORDER_CSS, BORDER_HI_CSS,
    TEXT_CSS, TEXT_2_CSS,
    SUCCESS_CSS, WARNING_CSS,
    BTN_PRIMARY, BTN_CLOSE, INPUT_STYLE,
    SPINBOX_STYLE, SCROLL_STYLE, TOGGLE_ON, TOGGLE_OFF,
    LABEL_TITLE, LABEL_SECTION, LABEL_SMALL,
)
from ui.icons import IconWidget, IconButton
from core.composio_manager import (
    ComposioManager, TOOLKIT_GOOGLECALENDAR,
    TOOLKIT_GMAIL, TOOLKIT_OUTLOOK, TOOLKIT_SLACK, TOOLKIT_NOTION,
    TOOLKIT_GOOGLEDRIVE, TOOLKIT_GITHUB, TOOLKIT_DISCORD, TOOLKIT_TRELLO,
    TOOLKIT_TODOIST, TOOLKIT_ASANA, ALL_TOOLKITS,
)

_TOGGLE_ON = TOGGLE_ON
_TOGGLE_OFF = TOGGLE_OFF


class ProviderCard(QWidget):
    def __init__(self, provider_key: str, info: dict, settings: dict, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.provider_key = provider_key
        self.env_key = info['env_key']
        self._models = info.get('models', [])

        current_val = settings.get(self.env_key, '').strip()
        self._is_on = bool(current_val) if provider_key != 'ollama' else bool(current_val)

        self._bg = C_SURFACE
        self._border = C_BORDER_HI if self._is_on else C_BORDER

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(7)

        row1 = QHBoxLayout()
        self.name_lbl = QLabel(info.get('name', provider_key.title()))
        self.name_lbl.setStyleSheet(f"color:{TEXT_CSS}; font-size:13px; font-weight:600; font-family:{FONT};")

        self.toggle = QPushButton('ON' if self._is_on else 'OFF')
        self.toggle.setFixedSize(44, 22)
        self.toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle.setStyleSheet(_TOGGLE_ON if self._is_on else _TOGGLE_OFF)
        self.toggle.clicked.connect(self._flip)

        row1.addWidget(self.name_lbl)
        row1.addStretch()
        row1.addWidget(self.toggle)

        key_lbl = QLabel('Endpoint URL:' if provider_key == 'ollama' else 'API Key:')
        key_lbl.setStyleSheet(LABEL_SMALL)

        self.key_input = QLineEdit(current_val)
        self.key_input.setStyleSheet(INPUT_STYLE)
        self.key_input.setEnabled(self._is_on)
        if provider_key == 'ollama':
            self.key_input.setPlaceholderText('http://localhost:11434')
        else:
            self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.key_input.setPlaceholderText(f"Chave de API do {info.get('name', '')}…")

        model_lbl = QLabel('Modelo:')
        model_lbl.setStyleSheet(LABEL_SMALL)

        model_env_key = f"NIGEL_{provider_key.upper()}_MODEL"
        current_model = settings.get(model_env_key, '').strip()
        default_model = info.get('default_model', '')

        self.model_widget = QLineEdit(current_model or default_model)
        self.model_widget.setStyleSheet(INPUT_STYLE)
        self.model_widget.setPlaceholderText(f"ex: {default_model}")
        self.model_widget.setEnabled(self._is_on)

        layout.addLayout(row1)
        layout.addWidget(key_lbl)
        layout.addWidget(self.key_input)
        layout.addWidget(model_lbl)
        layout.addWidget(self.model_widget)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, 12, 12)
        p.setPen(QPen(self._border, 1))
        p.setBrush(self._bg)
        p.drawPath(path)

    def _flip(self):
        self._is_on = not self._is_on
        self.toggle.setText('ON' if self._is_on else 'OFF')
        self.toggle.setStyleSheet(_TOGGLE_ON if self._is_on else _TOGGLE_OFF)
        self.key_input.setEnabled(self._is_on)
        self.model_widget.setEnabled(self._is_on)
        self._border = C_BORDER_HI if self._is_on else C_BORDER
        self.update()

    def get_key_value(self) -> str:
        return self.key_input.text().strip() if self._is_on else ''

    def get_model_value(self) -> str:
        return self.model_widget.text().strip()

    def is_on(self) -> bool:
        return self._is_on


class LedIndicator(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(14, 14)
        self.on = False

    def set_state(self, state: bool):
        self.on = state
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.on:
            p.setBrush(C_SUCCESS)  # conectado
            p.setPen(QPen(QColor(120, 240, 160), 1))
        else:
            p.setBrush(C_RAISED)
            p.setPen(QPen(C_BORDER_HI, 1))
        p.drawEllipse(2, 2, 10, 10)


class SidebarButton(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(36)
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-radius: 8px;
                color: {TEXT_2_CSS};
                font-family: {FONT};
                font-size: 13px;
                font-weight: 500;
                text-align: left;
                padding-left: 12px;
            }}
            QPushButton:hover {{
                background: {css(C_RAISED, 150)};
                color: {TEXT_CSS};
            }}
            QPushButton:checked {{
                background: {RAISED_CSS};
                color: {TEXT_CSS};
                font-weight: 600;
            }}
        """)


_ACTIVE_STATUS_WORKERS = set()
_ACTIVE_AUTH_WORKERS = set()


class ComposioStatusCheckWorker(QThread):
    status_ready = pyqtSignal(dict)

    def run(self):
        try:
            from core.composio_manager import ComposioManager
            cm = ComposioManager.get_instance()
            if not cm.is_configured():
                self.status_ready.emit({})
                return
            statuses = cm.get_all_connection_statuses(force_refresh=True, toolkits=ALL_TOOLKITS)
            self.status_ready.emit(statuses)
        except Exception as e:
            print(f"[ComposioStatusCheckWorker] Erro: {e}")
            self.status_ready.emit({})


class ComposioAuthWorker(QThread):
    auth_opened = pyqtSignal(str)
    auth_success = pyqtSignal()
    auth_error = pyqtSignal(str)

    def __init__(self, toolkit: str):
        super().__init__()
        self.toolkit = toolkit
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            import time
            cm = ComposioManager.get_instance()
            if not cm.is_configured():
                self.auth_error.emit('Composio API Key não configurada.')
                return
            url = cm.authorize_toolkit(self.toolkit, open_browser=True)
            if not url:
                if cm.check_connection(self.toolkit, force_refresh=True):
                    self.auth_success.emit()
                    return
            self.auth_opened.emit(url or '')

            # Polling em background para verificar se o usuário autorizou no navegador
            for _ in range(45):  # até 90s
                if self._stop:
                    return
                time.sleep(2)
                if self._stop:
                    return
                if cm.check_connection(self.toolkit, force_refresh=True):
                    self.auth_success.emit()
                    return

            self.auth_error.emit('Tempo limite esgotado. Tente novamente.')
        except Exception as e:
            err_msg = str(e)
            if 'Multiple connected accounts' in err_msg or 'already exists' in err_msg:
                if cm.check_connection(self.toolkit, force_refresh=True):
                    self.auth_success.emit()
                    return
            self.auth_error.emit(err_msg)


class Toast(QLabel):
    """Confirmação flutuante e efêmera ("✓ Slack conectado"), some sozinha.

    Antes o único feedback de conexão era o texto do card mudar — fácil de
    não notar quando a lista tem 11 integrações e o card que mudou já saiu
    da área visível do scroll.
    """

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QLabel {{
                background: {css(C_SUCCESS, 235)};
                color: #0E1410;
                font-family: {FONT}; font-size: {FS_SM}px; font-weight: 700;
                border-radius: 14px;
                padding: 8px 16px;
            }}
        """)
        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)
        self.hide()
        self._anim_in = None
        self._anim_out = None

    def show_message(self, text: str, duration_ms: int = 2200):
        self.setText(f'✓ {text} conectado')
        self.adjustSize()
        parent_w = self.parentWidget().width()
        self.move((parent_w - self.width()) // 2, 54)
        self.show()
        self.raise_()

        self._anim_in = QPropertyAnimation(self._effect, b'opacity')
        self._anim_in.setDuration(180)
        self._anim_in.setStartValue(0.0)
        self._anim_in.setEndValue(1.0)
        self._anim_in.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim_in.start()

        QTimer.singleShot(duration_ms, self._fade_out)

    def _fade_out(self):
        self._anim_out = QPropertyAnimation(self._effect, b'opacity')
        self._anim_out.setDuration(320)
        self._anim_out.setStartValue(1.0)
        self._anim_out.setEndValue(0.0)
        self._anim_out.setEasingCurve(QEasingCurve.Type.InCubic)
        self._anim_out.finished.connect(self.hide)
        self._anim_out.start()


class ComposioToolkitCard(QFrame):
    status_changed = pyqtSignal()
    connected_ok = pyqtSignal(str)   # emite o titulo, pro toast do SettingsWindow

    def __init__(self, toolkit: str, title: str, subtitle: str, is_official_agenda: bool = False, icon: str = ''):
        super().__init__()
        self.toolkit = toolkit
        self.title = title
        self.subtitle = subtitle
        self.is_official_agenda = is_official_agenda
        self.worker = None
        self.setStyleSheet(f"""
            QFrame {{
                background: {SURFACE_CSS};
                border-radius: {R_SM}px;
                border: 1px solid {BORDER_CSS};
            }}
            QFrame:hover {{
                background: {RAISED_CSS};
                border: 1px solid {BORDER_HI_CSS};
            }}
            QLabel {{ border: none; background: transparent; }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        if icon:
            header.addWidget(IconWidget(icon, 20))
        self.led = LedIndicator()

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"color: {TEXT_CSS}; font-family: {FONT}; font-weight: bold; font-size: 13px;")

        header.addWidget(self.led)
        header.addWidget(title_lbl)

        if self.is_official_agenda:
            badge = QLabel("OFICIAL")
            badge.setStyleSheet(f"""
                background: {OVERLAY_CSS};
                color: {TEXT_CSS};
                font-size: 10px;
                font-weight: bold;
                padding: 2px 6px;
                border-radius: 4px;
                border: 1px solid {BORDER_HI_CSS};
            """)
            header.addWidget(badge)

        header.addStretch()
        layout.addLayout(header)

        sub_lbl = QLabel(subtitle)
        sub_lbl.setStyleSheet(f"color: {TEXT_2_CSS}; font-size: 11px;")
        sub_lbl.setWordWrap(True)
        layout.addWidget(sub_lbl)

        row2 = QHBoxLayout()
        self.status_lbl = QLabel('Aguardando verificação...')
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setStyleSheet(f"color: {TEXT_2_CSS}; font-size: 11px;")

        self.btn_action = QPushButton('Conectar')
        self.btn_action.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_action.setStyleSheet(BTN_CLOSE)
        self.btn_action.setFixedWidth(110)
        self.btn_action.clicked.connect(self._on_action_clicked)

        row2.addWidget(self.status_lbl, 1)
        row2.addSpacing(8)
        row2.addWidget(self.btn_action)
        layout.addLayout(row2)

    def set_connected(self, is_connected: bool):
        if self.worker and self.worker.isRunning():
            return
        self.led.set_state(is_connected)
        self.btn_action.setEnabled(True)
        if is_connected:
            self.status_lbl.setText('Conectado. Sincronização ativa.')
            self.status_lbl.setStyleSheet(f"color: {TEXT_2_CSS}; font-size: 11px;")
            self.btn_action.setText('Reconectar')
        else:
            self.status_lbl.setText('Desconectado')
            self.status_lbl.setStyleSheet(f"color: {TEXT_2_CSS}; font-size: 11px;")
            self.btn_action.setText('Conectar')

    def set_not_configured(self):
        if self.worker and self.worker.isRunning():
            return
        self.led.set_state(False)
        self.status_lbl.setText('Configure a Composio API Key acima')
        self.btn_action.setEnabled(False)

    def _on_action_clicked(self):
        cm = ComposioManager.get_instance()
        if not cm.is_configured():
            self.status_lbl.setText('Insira e salve a Composio API Key primeiro.')
            return

        if self.worker and self.worker.isRunning():
            self.status_lbl.setText('Autorização já em andamento. Conclua no navegador...')
            return

        self.worker = ComposioAuthWorker(self.toolkit)
        _ACTIVE_AUTH_WORKERS.add(self.worker)
        self.worker.auth_opened.connect(lambda url: self.status_lbl.setText('Autorize no navegador aberto...'))
        self.worker.auth_success.connect(self._on_success)
        self.worker.auth_error.connect(self._on_error)
        self.worker.finished.connect(lambda: _ACTIVE_AUTH_WORKERS.discard(self.worker))
        self.worker.start()

        self.btn_action.setEnabled(False)
        self.btn_action.setText('Aguardando...')
        self.led.set_state(False)

    def _on_success(self):
        self.status_lbl.setText('Conectado com sucesso!')
        self.status_lbl.setStyleSheet(f"color: {SUCCESS_CSS}; font-size: {FS_SM}px; font-weight: 600;")
        self.btn_action.setEnabled(True)
        self.btn_action.setText('Reconectar')
        self.led.set_state(True)
        self.status_changed.emit()
        self.connected_ok.emit(self.title)

    def _on_error(self, err):
        self.status_lbl.setText(f"Status: {err}")
        self.status_lbl.setStyleSheet(f"color: {WARNING_CSS}; font-size: {FS_SM}px;")
        self.btn_action.setEnabled(True)
        self.btn_action.setText('Conectar')


class SettingsWindow(QWidget):
    settings_saved = pyqtSignal()
    resize_bar = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(700, 560)
        self._drag_pos = None
        self._status_check_worker = None

        from core.api_client import APIClient, PROVIDERS
        self._api = APIClient()
        self._PROVIDERS = PROVIDERS
        self._cards = {}
        self._build()
        self._toast = Toast(self)

        # Altura padrao com folga sobre o que o layout pede, de proposito.
        #
        # Com 700x560 a janela abria MENOR do que o proprio layout queria e
        # esticava sozinha na primeira reorganizacao — era isso que aparecia
        # como "a janela redimensiona quando mexo nela", junto do aviso
        # "Unable to set geometry 700x560 ... Resulting geometry: 700x666" e
        # do clique caindo deslocado. O sizeHint tambem nao serve como alvo:
        # varia conforme o estilo termina de ser aplicado (664 no inicio, 681
        # depois), entao perseguir esse numero so' troca um pulo por outro.
        # Abrindo acima do teto observado, nada precisa crescer.
        #
        # NAO troque por setFixedSize nem por "corrigir" o tamanho num
        # resizeEvent: o Windows reaplica a altura dele, o handler responde a
        # sua, e o laco trava a interface inteira.
        alt = 700
        tela = QApplication.primaryScreen()
        if tela is not None:
            # Nunca mais alta que a area util — protege telas pequenas.
            alt = max(560, min(alt, tela.availableGeometry().height() - 40))
        self.resize(700, alt)

    def _build(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Barra de título / cabeçalho arrastável
        self.title_bar = QWidget()
        self.title_bar.setFixedHeight(46)
        self.title_bar.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        title_row = QHBoxLayout(self.title_bar)
        title_row.setContentsMargins(20, 10, 16, 0)
        title_row.addWidget(IconWidget('settings', 16))
        title = QLabel('Configurações')
        title.setStyleSheet(LABEL_TITLE)
        close_btn = IconButton('close', 28, 'Fechar')
        close_btn.clicked.connect(self.hide)
        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(close_btn)
        main_layout.addWidget(self.title_bar)

        body = QHBoxLayout()
        body.setContentsMargins(16, 10, 16, 16)
        body.setSpacing(16)

        sidebar = QWidget()
        sidebar.setFixedWidth(140)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(6)

        self.btn_gen = SidebarButton('Geral')
        self.btn_prov = SidebarButton('Provedores de IA')
        self.btn_sync = SidebarButton('Integrações')
        self.btn_memory = SidebarButton('Memória')
        self.btn_persona = SidebarButton('Persona')
        self.btn_prompts = SidebarButton('Instruções')

        self.btn_gen.setChecked(True)

        self.btn_group = QButtonGroup(self)
        self.btn_group.setExclusive(True)
        self.btn_group.addButton(self.btn_gen, 0)
        self.btn_group.addButton(self.btn_prov, 1)
        self.btn_group.addButton(self.btn_sync, 2)
        self.btn_group.addButton(self.btn_memory, 3)
        self.btn_group.addButton(self.btn_persona, 4)
        self.btn_group.addButton(self.btn_prompts, 5)
        self.btn_group.idClicked.connect(self._on_tab_clicked)

        side_layout.addWidget(self.btn_gen)
        side_layout.addWidget(self.btn_prov)
        side_layout.addWidget(self.btn_sync)
        side_layout.addWidget(self.btn_memory)
        side_layout.addWidget(self.btn_persona)
        side_layout.addWidget(self.btn_prompts)
        side_layout.addStretch()

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_page_general())
        self.stack.addWidget(self._build_page_providers())
        self.stack.addWidget(self._build_page_sync())
        self.memory_tab = self._build_page_memory()
        self.stack.addWidget(self.memory_tab)
        self.stack.addWidget(self._build_page_persona())
        self.stack.addWidget(self._build_page_prompts())

        body.addWidget(sidebar)

        div = QFrame()
        div.setFrameShape(QFrame.Shape.VLine)
        div.setFixedWidth(1)
        div.setStyleSheet(f'background: {BORDER_CSS};')
        body.addWidget(div)

        body.addWidget(self.stack, 1)
        main_layout.addLayout(body)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(16, 0, 16, 16)
        self.status_lbl = QLabel('')
        self.status_lbl.setStyleSheet(f"color: {TEXT_CSS}; font-family:{FONT}; font-weight:bold; font-size: 12px;")
        save_btn = QPushButton('Salvar Configurações')
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(BTN_PRIMARY)
        save_btn.setFixedWidth(200)
        save_btn.clicked.connect(self._save)

        bottom.addWidget(self.status_lbl)
        bottom.addStretch()
        bottom.addWidget(save_btn)
        main_layout.addLayout(bottom)

    def open_tab(self, tab_index: int):
        """Abre uma aba específica diretamente (ex: 2 para Sync)."""
        button = self.btn_group.button(tab_index)
        if button:
            button.setChecked(True)
        self._on_tab_clicked(tab_index)
        self.show()
        self.raise_()

    def _on_tab_clicked(self, idx):
        self.stack.setCurrentIndex(idx)
        if idx == 2:
            self._refresh_sync_tab()
        elif idx == 3 and hasattr(self, 'memory_tab_widget'):
            self.memory_tab_widget.refresh()

    def _build_page_memory(self) -> QWidget:
        from ui.brain_panel import MemoryTab
        self.memory_tab_widget = MemoryTab()
        return self.memory_tab_widget

    def _build_page_general(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)

        lbl = QLabel('TAMANHO DA BARRA')
        lbl.setStyleSheet(LABEL_SECTION)
        layout.addWidget(lbl)

        size_row = QHBoxLayout()
        w_lbl = QLabel('Largura:')
        w_lbl.setStyleSheet(LABEL_SMALL)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(380, 1000)
        self.width_spin.setSingleStep(10)
        self.width_spin.setValue(int(os.getenv('NIGEL_BAR_WIDTH', '600')))
        self.width_spin.setStyleSheet(SPINBOX_STYLE)
        self.width_spin.setSuffix(' px')
        self.width_spin.valueChanged.connect(self._on_size_changed)

        h_lbl = QLabel('Altura:')
        h_lbl.setStyleSheet(LABEL_SMALL)
        self.height_spin = QSpinBox()
        self.height_spin.setRange(44, 90)
        self.height_spin.setSingleStep(2)
        self.height_spin.setValue(int(os.getenv('NIGEL_BAR_HEIGHT', '60')))
        self.height_spin.setStyleSheet(SPINBOX_STYLE)
        self.height_spin.setSuffix(' px')
        self.height_spin.valueChanged.connect(self._on_size_changed)

        size_row.addWidget(w_lbl)
        size_row.addWidget(self.width_spin)
        size_row.addSpacing(16)
        size_row.addWidget(h_lbl)
        size_row.addWidget(self.height_spin)
        size_row.addStretch()

        layout.addLayout(size_row)
        layout.addStretch()
        return w

    def _build_page_providers(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)

        lbl = QLabel('PROVIDERS DE LLM')
        lbl.setStyleSheet(LABEL_SECTION)
        layout.addWidget(lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(SCROLL_STYLE)

        content = QWidget()
        content.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        cards_layout = QVBoxLayout(content)
        cards_layout.setContentsMargins(0, 0, 8, 0)
        cards_layout.setSpacing(8)

        settings = self._api.get_settings()
        for (key, info) in self._PROVIDERS.items():
            card = ProviderCard(key, info, settings)
            self._cards[key] = card
            cards_layout.addWidget(card)

        cards_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        return w

    def _build_page_sync(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        lbl = QLabel('COMPOSIO & INTEGRAÇÕES')
        lbl.setStyleSheet(LABEL_SECTION)
        layout.addWidget(lbl)

        # Banner de status da agenda obrigatória
        self.agenda_banner = QFrame()
        self.agenda_banner.setStyleSheet(f"""
            QFrame {{
                background: {RAISED_CSS};
                border: 1px solid {BORDER_HI_CSS};
                border-radius: {R_SM}px;
            }}
            QLabel {{ background: transparent; border: none; }}
        """)
        b_layout = QHBoxLayout(self.agenda_banner)
        b_layout.setContentsMargins(12, 8, 12, 8)
        self.agenda_banner_lbl = QLabel()
        self.agenda_banner_lbl.setStyleSheet(f"color: {TEXT_CSS}; font-size: {FS_SM}px; font-weight: 500;")
        self.agenda_banner_lbl.setWordWrap(True)
        b_layout.addWidget(self.agenda_banner_lbl)
        layout.addWidget(self.agenda_banner)

        # Card de Configuração da API Key do Composio
        key_frame = QFrame()
        key_frame.setStyleSheet(f"""
            QFrame {{
                background: {RAISED_CSS};
                border-radius: {R_SM}px;
                border: 1px solid {BORDER_CSS};
            }}
            QLabel {{ border: none; background: transparent; }}
        """)
        kf_layout = QVBoxLayout(key_frame)
        kf_layout.setContentsMargins(12, 10, 12, 10)
        kf_layout.setSpacing(6)

        kf_header = QHBoxLayout()
        kf_title = QLabel('Composio API Key:')
        kf_title.setStyleSheet(LABEL_SMALL)
        kf_header.addWidget(kf_title)
        kf_header.addStretch()
        kf_layout.addLayout(kf_header)

        kf_input_row = QHBoxLayout()
        self.composio_key_input = QLineEdit()
        self.composio_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.composio_key_input.setPlaceholderText('Cole sua COMPOSIO_API_KEY aqui…')
        self.composio_key_input.setStyleSheet(INPUT_STYLE)
        self.composio_key_input.setText(ComposioManager.get_instance().get_api_key())

        btn_save_key = QPushButton('Salvar Chave')
        btn_save_key.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save_key.setStyleSheet(BTN_CLOSE)
        btn_save_key.setFixedWidth(100)
        btn_save_key.clicked.connect(self._on_save_composio_key)

        kf_input_row.addWidget(self.composio_key_input, 1)
        kf_input_row.addWidget(btn_save_key)
        kf_layout.addLayout(kf_input_row)

        layout.addWidget(key_frame)

        # Busca: com 11 integracoes, rolar a lista inteira toda vez fica
        # cansativo — filtra por titulo/descricao conforme digita.
        self._toolkit_search = QLineEdit()
        self._toolkit_search.setPlaceholderText('Buscar integração…')
        self._toolkit_search.setStyleSheet(INPUT_STYLE)
        self._toolkit_search.textChanged.connect(self._on_toolkit_search)
        layout.addWidget(self._toolkit_search)

        # Scroll com os cards das integrações
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(SCROLL_STYLE)

        content = QWidget()
        content.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        grid = QVBoxLayout(content)
        grid.setContentsMargins(0, 0, 8, 0)
        grid.setSpacing(8)

        # Essenciais: sempre visiveis, sao o caminho de onboarding — em vez
        # de despejar as 11 integracoes de uma vez, so as 3 mais comuns
        # (agenda obrigatoria + Gmail + Slack, que ja tem especialista
        # proprio) aparecem abertas; o resto fica atras de "Mostrar mais".
        self.cal_card = ComposioToolkitCard(
            TOOLKIT_GOOGLECALENDAR,
            'Google Calendar (Google Agenda)',
            'Agenda oficial do Nigel. Sincroniza lembretes, compromissos e eventos em tempo real com sua conta Google.',
            is_official_agenda=True, icon='brand_gcal'
        )
        self.cal_card.status_changed.connect(self._refresh_sync_tab)
        grid.addWidget(self.cal_card)

        self.gmail_card = ComposioToolkitCard(
            TOOLKIT_GMAIL,
            'Gmail',
            'Leitura de e-mails em background via ferramentas do Composio.',
            icon='brand_gmail'
        )
        grid.addWidget(self.gmail_card)

        self.extra_cards: dict[str, ComposioToolkitCard] = {}
        slack_card = ComposioToolkitCard(
            TOOLKIT_SLACK, 'Slack',
            'Canais, mensagens e DMs — o chat_agent usa direto.', icon='brand_slack')
        self.extra_cards[TOOLKIT_SLACK] = slack_card
        grid.addWidget(slack_card)

        for card in (self.cal_card, self.gmail_card, slack_card):
            card.connected_ok.connect(self._show_toast)

        self._more_toggle = QPushButton('Mostrar mais (8)')
        self._more_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._more_toggle.setStyleSheet(BTN_CLOSE)
        self._more_toggle.clicked.connect(self._toggle_more_toolkits)
        grid.addWidget(self._more_toggle)

        self._more_container = QWidget()
        self._more_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        more_layout = QVBoxLayout(self._more_container)
        more_layout.setContentsMargins(0, 0, 0, 0)
        more_layout.setSpacing(8)
        self._more_container.hide()
        self._more_expanded = False

        # Mais conectores: cada um vira usavel pelo apps_agent assim que
        # conectado (descoberta dinamica), sem precisar de um core/tools/*.py
        # dedicado.
        self.outlook_card = ComposioToolkitCard(
            TOOLKIT_OUTLOOK,
            'Microsoft Outlook',
            'Leitura de e-mails do Outlook via ferramentas do Composio.',
            icon='brand_outlook'
        )
        more_layout.addWidget(self.outlook_card)
        self.outlook_card.connected_ok.connect(self._show_toast)

        for toolkit, title, subtitle, icon in (
            (TOOLKIT_NOTION, 'Notion',
             'Paginas e bancos de dados, via apps_agent.', 'brand_notion'),
            (TOOLKIT_GOOGLEDRIVE, 'Google Drive',
             'Arquivos e pastas, via apps_agent.', 'brand_googledrive'),
            (TOOLKIT_GITHUB, 'GitHub',
             'Issues, PRs e repositorios, via apps_agent.', 'brand_github'),
            (TOOLKIT_DISCORD, 'Discord',
             'Servidores e canais, via apps_agent.', 'brand_discord'),
            (TOOLKIT_TRELLO, 'Trello',
             'Quadros e cartoes, via apps_agent.', 'brand_trello'),
            (TOOLKIT_TODOIST, 'Todoist',
             'Tarefas e projetos, via apps_agent.', 'brand_todoist'),
            (TOOLKIT_ASANA, 'Asana',
             'Tarefas e projetos de equipe, via apps_agent.', 'brand_asana'),
        ):
            card = ComposioToolkitCard(toolkit, title, subtitle, icon=icon)
            card.connected_ok.connect(self._show_toast)
            self.extra_cards[toolkit] = card
            more_layout.addWidget(card)

        grid.addWidget(self._more_container)
        grid.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        # Dispara verificação assíncrona
        self._refresh_sync_tab()
        return w

    def _show_toast(self, title: str):
        self._toast.show_message(title)

    def _toggle_more_toolkits(self):
        self._more_expanded = not self._more_expanded
        self._more_container.setVisible(self._more_expanded)
        # extra_cards inclui o Slack, que fica fora do grupo "mais" (e' um
        # dos 3 essenciais) — o Outlook compensa, entao a contagem bate.
        n = len(self.extra_cards)
        self._more_toggle.setText('Mostrar menos' if self._more_expanded else f'Mostrar mais ({n})')

    def _on_toolkit_search(self, text: str):
        text = text.strip().lower()
        all_cards = [self.cal_card, self.gmail_card, self.outlook_card] + list(self.extra_cards.values())
        if not text:
            for card in all_cards:
                card.setVisible(True)
            self._more_container.setVisible(self._more_expanded)
            self._more_toggle.setVisible(True)
            return
        # Buscando: expande "mais integrações" pra nao esconder um resultado
        # que mora la dentro, e some com o botao de toggle (nao faz sentido
        # com o filtro ativo).
        self._more_container.show()
        self._more_toggle.setVisible(False)
        for card in all_cards:
            match = text in card.title.lower() or text in card.subtitle.lower()
            card.setVisible(match)

    def _on_save_composio_key(self):
        new_key = self.composio_key_input.text().strip()
        ComposioManager.get_instance().set_api_key(new_key)
        self.status_lbl.setText('Chave Composio salva!')
        QTimer.singleShot(2000, lambda: self.status_lbl.setText(''))
        self._refresh_sync_tab()

    def _refresh_sync_tab(self):
        cm = ComposioManager.get_instance()
        if not cm.is_configured():
            if hasattr(self, 'agenda_banner_lbl'):
                self.agenda_banner_lbl.setText('Insira sua Composio API Key e conecte o Google Calendar para começar.')
                self.agenda_banner.setStyleSheet(f"""
                    QFrame {{ background: {css(C_WARNING, 28)}; border: 1px solid {css(C_WARNING, 110)}; border-radius: {R_SM}px; }}
                """)
            if hasattr(self, 'cal_card'):
                self.cal_card.set_not_configured()
                self.gmail_card.set_not_configured()
                self.outlook_card.set_not_configured()
                for card in self.extra_cards.values():
                    card.set_not_configured()
            return

        if hasattr(self, 'agenda_banner_lbl'):
            self.agenda_banner_lbl.setText('Verificando conexões do Composio em segundo plano...')

        # Executa em background para não travar a interface gráfica
        if self._status_check_worker and self._status_check_worker.isRunning():
            return
        worker = ComposioStatusCheckWorker()
        self._status_check_worker = worker
        _ACTIVE_STATUS_WORKERS.add(worker)
        worker.status_ready.connect(self._on_status_check_done)
        worker.finished.connect(lambda: _ACTIVE_STATUS_WORKERS.discard(worker))
        worker.start()

    def _on_status_check_done(self, statuses: dict):
        if hasattr(self, 'cal_card'):
            self.cal_card.set_connected(bool(statuses.get(TOOLKIT_GOOGLECALENDAR, False)))
            self.gmail_card.set_connected(bool(statuses.get(TOOLKIT_GMAIL, False)))
            self.outlook_card.set_connected(bool(statuses.get(TOOLKIT_OUTLOOK, False)))
            for toolkit, card in self.extra_cards.items():
                card.set_connected(bool(statuses.get(toolkit, False)))

        if hasattr(self, 'agenda_banner_lbl'):
            has_agenda = bool(statuses.get(TOOLKIT_GOOGLECALENDAR))
            if has_agenda:
                self.agenda_banner_lbl.setText("✓ Agenda Oficial (Google Calendar) conectada e ativa.")
                self.agenda_banner.setStyleSheet(f"""
                    QFrame {{ background: {css(C_SUCCESS, 26)}; border: 1px solid {css(C_SUCCESS, 110)}; border-radius: {R_SM}px; }}
                """)
            else:
                self.agenda_banner_lbl.setText('Agenda obrigatória: Conecte o Google Calendar (Agenda Oficial) para sincronizar compromissos.')
                self.agenda_banner.setStyleSheet(f"""
                    QFrame {{ background: {RAISED_CSS}; border: 1px solid {BORDER_HI_CSS}; border-radius: {R_SM}px; }}
                """)

    def _build_page_persona(self) -> QWidget:
        from core.storage import load_config
        config = load_config()
        persona = config.get('persona', {})

        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        lbl = QLabel('PERSONA DO USUÁRIO')
        lbl.setStyleSheet(LABEL_SECTION)
        layout.addWidget(lbl)

        desc = QLabel('Esses dados viram nós roxos fixos no Grafo de Memória. Eles representam a pessoa e ancoram memórias relacionadas.')
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_2_CSS}; font-size: 11px; font-family: {FONT};")
        layout.addWidget(desc)

        def add_field(label: str, placeholder: str, value: str) -> QLineEdit:
            field_lbl = QLabel(label)
            field_lbl.setStyleSheet(LABEL_SMALL)
            layout.addWidget(field_lbl)
            inp = QLineEdit(value)
            inp.setPlaceholderText(placeholder)
            inp.setStyleSheet(INPUT_STYLE)
            layout.addWidget(inp)
            return inp

        self.persona_name_input = add_field('Nome:', 'ex: Seu nome', persona.get('name', ''))
        self.persona_age_input = add_field('Idade:', 'ex: 28', str(persona.get('age', '')) or '')
        self.persona_email_input = add_field('Email:', 'ex: voce@email.com', persona.get('email', ''))

        facts_header = QHBoxLayout()
        facts_lbl = QLabel('Informações adicionais:')
        facts_lbl.setStyleSheet(LABEL_SMALL)
        add_fact_btn = IconButton('add', 34, 'Adicionar informação à Persona')
        add_fact_btn.clicked.connect(lambda: self._add_persona_fact_row(''))
        facts_header.addWidget(facts_lbl)
        facts_header.addStretch()
        facts_header.addWidget(add_fact_btn)
        layout.addLayout(facts_header)

        self.persona_fact_inputs = []
        facts_scroll = QScrollArea()
        facts_scroll.setWidgetResizable(True)
        facts_scroll.setFrameShape(QFrame.Shape.NoFrame)
        facts_scroll.setFixedHeight(118)
        facts_scroll.setStyleSheet(SCROLL_STYLE)

        self.persona_facts_container = QWidget()
        self.persona_facts_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.persona_facts_layout = QVBoxLayout(self.persona_facts_container)
        self.persona_facts_layout.setContentsMargins(0, 0, 4, 0)
        self.persona_facts_layout.setSpacing(6)
        self.persona_facts_layout.addStretch()
        facts_scroll.setWidget(self.persona_facts_container)
        layout.addWidget(facts_scroll)

        facts = persona.get('facts', []) or []
        if facts:
            for fact in facts:
                self._add_persona_fact_row(str(fact))
        else:
            self._add_persona_fact_row('')

        layout.addStretch()
        return w

    def _add_persona_fact_row(self, text: str = ''):
        row = QWidget()
        row.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        inp = QLineEdit(text)
        inp.setPlaceholderText('ex: Prefiro reuniões pela manhã')
        inp.setMinimumHeight(34)
        inp.setStyleSheet(INPUT_STYLE)

        remove_btn = IconButton('close', 34, 'Remover informação')

        def _remove():
            if inp in self.persona_fact_inputs:
                self.persona_fact_inputs.remove(inp)
            row.deleteLater()

        remove_btn.clicked.connect(_remove)
        row_layout.addWidget(inp, 1)
        row_layout.addWidget(remove_btn)

        self.persona_fact_inputs.append(inp)
        self.persona_facts_layout.insertWidget(self.persona_facts_layout.count() - 1, row)

    def _build_page_prompts(self) -> QWidget:
        from core.storage import load_config
        from core.ai_triage import _DEFAULT_TRIAGE_PROMPT

        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        lbl = QLabel('FILTRO DE NOTIFICAÇÕES (IA)')
        lbl.setStyleSheet(LABEL_SECTION)
        layout.addWidget(lbl)

        desc = QLabel('Escreva em linguagem natural o que é importante para você.\nO Nigel usará a IA para filtrar e-mails e mensagens com base nessas regras.')
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_2_CSS}; font-size: 11px; font-family: {FONT};")
        layout.addWidget(desc)

        config = load_config()
        saved_prompt = config.get('triage_prompt', _DEFAULT_TRIAGE_PROMPT)

        self.prompt_editor = QTextEdit()
        self.prompt_editor.setPlainText(saved_prompt)
        self.prompt_editor.setStyleSheet(f"""
            QTextEdit {{
                background: {RAISED_CSS};
                border: 1px solid {BORDER_CSS};
                border-radius: 8px;
                color: {TEXT_CSS};
                font-family: {FONT_MONO};
                font-size: 11px;
                padding: 8px;
            }}
        """)
        layout.addWidget(self.prompt_editor, 1)
        return w

    def paintEvent(self, event):
        p = QPainter(self)
        paint_panel(self, p, radius=20, bg=C_BG, border=C_BORDER)

    def _on_size_changed(self):
        self.resize_bar.emit(self.width_spin.value(), self.height_spin.value())

    def _save(self):
        new_settings = {}
        active_provider = None
        for (key, card) in self._cards.items():
            info = self._PROVIDERS[key]
            val = card.get_key_value()
            new_settings[info['env_key']] = val
            new_settings[f"NIGEL_{key.upper()}_MODEL"] = card.get_model_value()
            if card.is_on() and val and not active_provider:
                active_provider = key

        if active_provider:
            new_settings['NIGEL_ACTIVE_PROVIDER'] = active_provider

        if hasattr(self, 'composio_key_input'):
            comp_key = self.composio_key_input.text().strip()
            ComposioManager.get_instance().set_api_key(comp_key)
            new_settings['COMPOSIO_API_KEY'] = comp_key

        w = self.width_spin.value()
        h = self.height_spin.value()
        new_settings['NIGEL_BAR_WIDTH'] = str(w)
        new_settings['NIGEL_BAR_HEIGHT'] = str(h)

        self._api.save_settings(new_settings)
        self.status_lbl.setText('Salvo com sucesso!')
        self.resize_bar.emit(w, h)

        if hasattr(self, 'prompt_editor'):
            from core.storage import save_config
            save_config({'triage_prompt': self.prompt_editor.toPlainText()})

        if hasattr(self, 'persona_name_input'):
            from core.storage import save_config
            from core.database import NigelDB
            persona = {
                'name': self.persona_name_input.text().strip(),
                'age': self.persona_age_input.text().strip(),
                'email': self.persona_email_input.text().strip(),
                'facts': [inp.text().strip() for inp in getattr(self, 'persona_fact_inputs', []) if inp.text().strip()]
            }
            save_config({'persona': persona})
            NigelDB.get_instance().sync_persona_profile(persona)

        QTimer.singleShot(2000, lambda: self.status_lbl.setText(''))
        self.settings_saved.emit()
        self._refresh_sync_tab()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = None
            pos = event.position().toPoint()
            # Só inicia drag se clicou na barra de cabeçalho superior (y < 46)
            if pos.y() <= 46:
                child = self.childAt(pos)
                if not isinstance(child, (QPushButton, QLineEdit, QSpinBox, IconButton)):
                    self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None:
            if not (event.buttons() & Qt.MouseButton.LeftButton):
                # Auto-recuperacao: se o botao ja foi solto mas o
                # mouseReleaseEvent nao chegou (frameless + sempre-no-topo
                # as vezes perde esse evento no Windows), sem isso o arraste
                # gruda e a janela pula pro cursor no proximo clique — o
                # clique some porque a janela se move debaixo dele antes.
                self._drag_pos = None
            else:
                self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)
