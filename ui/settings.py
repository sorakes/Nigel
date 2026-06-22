"""
ui/settings.py  —  Janela de configurações (Vanilla & Gold)
Inclui: seletor de provider, seletor de modelo, controle de tamanho da barra.
"""
import os
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QFrame, QScrollArea, QSpinBox, QSizePolicy, QApplication, QGridLayout
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QRectF
from PyQt6.QtGui import QColor, QPainter, QPen, QPainterPath
from ui.theme import paint_panel, C_PANEL, C_CREAM, C_GOLD, C_GOLD_BRIGHT, C_GOLD_BTN, C_GOLD_BTN_H, C_GOLD_BTN_P, C_TEXT, C_TEXT_MID, C_TEXT_LIGHT, FONT, FONT_MONO, PANEL_CSS, CREAM_CSS, GOLD_CSS, GOLD_BRIGHT_CSS, TEXT_CSS, TEXT_MID_CSS, TEXT_LIGHT_CSS, BTN_PRIMARY, BTN_CLOSE, INPUT_STYLE, COMBOBOX_STYLE, SPINBOX_STYLE, SCROLL_STYLE, LABEL_TITLE, LABEL_SECTION, LABEL_SMALL, LABEL_MUTED
from ui.icons import IconWidget, IconButton

_TOGGLE_ON = '\n    QPushButton {\n        background: rgba(201,168,76,215);\n        color: rgba(42,30,8,230);\n        border: none;\n        border-radius: 10px;\n        font-size: 10px;\n        font-weight: bold;\n        min-width: 44px;\n        padding: 2px 6px;\n    }\n    QPushButton:hover { background: rgba(220,185,70,240); }\n'
_TOGGLE_OFF = '\n    QPushButton {\n        background: rgba(200,188,158,60);\n        color: rgba(140,110,55,160);\n        border: 1px solid rgba(201,168,76,70);\n        border-radius: 10px;\n        font-size: 10px;\n        min-width: 44px;\n        padding: 2px 6px;\n    }\n    QPushButton:hover { background: rgba(201,168,76,35); color: rgba(80,60,20,200); }\n'

class ProviderCard(QWidget):

    def __init__(self, provider_key: str, info: dict, settings: dict, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.provider_key = provider_key
        self.env_key = info['env_key']
        self._models = info.get('models', [])
        current_val = settings.get(self.env_key, '').strip()
        self._is_on = bool(current_val) if provider_key != 'ollama' else bool(current_val)
        self._bg = C_CREAM
        self._border = C_GOLD if self._is_on else QColor(201, 168, 76, 55)
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
        model_env_key = f"SEQ_{provider_key.upper()}_MODEL"
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
        self._border = C_GOLD if self._is_on else QColor(201, 168, 76, 55)
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
            p.setBrush(C_GOLD_BRIGHT)
            p.setPen(QPen(C_GOLD, 1))
        else:
            p.setBrush(QColor(201, 168, 76, 50))
            p.setPen(QPen(QColor(201, 168, 76, 90), 1))
        p.drawEllipse(2, 2, 10, 10)

class SidebarButton(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(36)
        self.setStyleSheet(f'\n            QPushButton {{\n                background: transparent;\n                border: none;\n                border-radius: 8px;\n                color: {TEXT_MID_CSS};\n                font-family: {FONT};\n                font-size: 13px;\n                font-weight: 500;\n                text-align: left;\n                padding-left: 12px;\n            }}\n            QPushButton:hover {{\n                background: rgba(201,168,76, 20);\n                color: {TEXT_CSS};\n            }}\n            QPushButton:checked {{\n                background: rgba(201,168,76, 40);\n                color: {GOLD_BRIGHT_CSS};\n                font-weight: bold;\n            }}\n        ')

from PyQt6.QtCore import QThread, pyqtSignal

class GenericAuthWorker(QThread):
    auth_success = pyqtSignal()
    auth_error = pyqtSignal(str)

    def __init__(self, provider_instance):
        super().__init__()
        self.provider = provider_instance

    def run(self):
        try:
            if self.provider.login_interactive():
                self.auth_success.emit()
                return
            self.auth_error.emit('Falha no login ou cancelado pelo usuário.')
            return
        except Exception as e:
            self.auth_error.emit(str(e))
            return

class MicrosoftAuthCard(QFrame):
    def __init__(self):
        super().__init__()
        self.setStyleSheet('\n            QFrame { background: rgba(201,168,76, 15); border-radius: 8px; border: 1px solid rgba(201,168,76, 50); }\n            QLabel { border: none; background: transparent; }\n        ')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        from core.microsoft_auth import MicrosoftAuth
        self.auth = MicrosoftAuth.get_instance()
        header = QHBoxLayout()
        self.led = LedIndicator()
        title = QLabel('Microsoft Graph (Teams & Outlook)')
        title.setStyleSheet(f"color: {GOLD_BRIGHT_CSS}; font-family: {FONT}; font-weight: bold; font-size: 13px;")
        header.addWidget(self.led)
        header.addWidget(title, 1)
        layout.addLayout(header)
        row2 = QHBoxLayout()
        self.status_lbl = QLabel('Aguardando conexão...')
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setStyleSheet(f"color: {TEXT_MID_CSS}; font-size: 11px;")
        self.btn_login = QPushButton('Conectar')
        self.btn_login.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_login.setStyleSheet(BTN_CLOSE)
        self.btn_login.setFixedWidth(100)
        self.btn_login.clicked.connect(self._on_login)
        row2.addWidget(self.status_lbl, 1)
        row2.addSpacing(8)
        row2.addWidget(self.btn_login)
        layout.addLayout(row2)
        self.worker = None
        self._check_initial_status()

    def _check_initial_status(self):
        if self.auth.get_token_silent():
            self.led.set_state(True)
            self.status_lbl.setText('Conectado. Sincronização ativa.')
            self.btn_login.setText('Reconectar')
            return
        return

    def _on_login(self):
        if self.worker:
            self.worker.deleteLater()
        self.worker = GenericAuthWorker(self.auth)
        self.worker.auth_success.connect(self._on_success)
        self.worker.auth_error.connect(self._on_error)
        self.worker.start()
        self.btn_login.setEnabled(False)
        self.btn_login.setText('Aguardando...')
        self.led.set_state(False)

    def _on_success(self):
        self.status_lbl.setText('Conectado. Sincronização ativa.')
        self.status_lbl.setStyleSheet(f"color: {TEXT_MID_CSS}; font-size: 11px;")
        self.btn_login.setEnabled(True)
        self.btn_login.setText('Reconectar')
        self.led.set_state(True)

    def _on_error(self, err):
        self.status_lbl.setText(f"Erro: {err}")
        self.status_lbl.setStyleSheet('color: rgba(180,50,30,200); font-size: 11px;')
        self.btn_login.setEnabled(True)
        self.btn_login.setText('Conectar')
        self.led.set_state(False)

class GoogleAuthCard(QFrame):
    def __init__(self):
        super().__init__()
        self.setStyleSheet('\n            QFrame { background: rgba(201,168,76, 15); border-radius: 8px; border: 1px solid rgba(201,168,76, 50); }\n            QLabel { border: none; background: transparent; }\n        ')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        from core.google_auth import GoogleAuth
        self.auth = GoogleAuth.get_instance()
        header = QHBoxLayout()
        self.led = LedIndicator()
        title = QLabel('Google Workspace (GMail)')
        title.setStyleSheet(f"color: {GOLD_BRIGHT_CSS}; font-family: {FONT}; font-weight: bold; font-size: 13px;")
        header.addWidget(self.led)
        header.addWidget(title, 1)
        layout.addLayout(header)
        row2 = QHBoxLayout()
        self.status_lbl = QLabel('Aguardando conexão...')
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setStyleSheet(f"color: {TEXT_MID_CSS}; font-size: 11px;")
        self.btn_login = QPushButton('Conectar')
        self.btn_login.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_login.setStyleSheet(BTN_CLOSE)
        self.btn_login.setFixedWidth(100)
        self.btn_login.clicked.connect(self._on_login)
        row2.addWidget(self.status_lbl, 1)
        row2.addSpacing(8)
        row2.addWidget(self.btn_login)
        layout.addLayout(row2)
        self.worker = None
        self._check_initial_status()

    def _check_initial_status(self):
        if self.auth.is_connected():
            self.led.set_state(True)
            self.status_lbl.setText('Conectado. Sincronização ativa.')
            self.btn_login.setText('Reconectar')
            return
        return

    def _on_login(self):
        if self.worker:
            self.worker.deleteLater()
        self.worker = GenericAuthWorker(self.auth)
        self.worker.auth_success.connect(self._on_success)
        self.worker.auth_error.connect(self._on_error)
        self.worker.start()
        self.btn_login.setEnabled(False)
        self.btn_login.setText('Aguardando...')
        self.led.set_state(False)

    def _on_success(self):
        self.status_lbl.setText('Conectado. Sincronização ativa.')
        self.status_lbl.setStyleSheet(f"color: {TEXT_MID_CSS}; font-size: 11px;")
        self.btn_login.setEnabled(True)
        self.btn_login.setText('Reconectar')
        self.led.set_state(True)

    def _on_error(self, err):
        self.status_lbl.setText(f"Erro: {err}")
        self.status_lbl.setStyleSheet('color: rgba(180,50,30,200); font-size: 11px;')
        self.btn_login.setEnabled(True)
        self.btn_login.setText('Conectar')
        self.led.set_state(False)

from PyQt6.QtWidgets import QStackedWidget, QButtonGroup

class SettingsWindow(QWidget):
    settings_saved = pyqtSignal()
    resize_bar = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(680, 520)
        self._drag_pos = None
        from core.api_client import APIClient, PROVIDERS
        self._api = APIClient()
        self._PROVIDERS = PROVIDERS
        self._cards = {}
        self._build()

    def _build(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        title_row = QHBoxLayout()
        title_row.setContentsMargins(20, 16, 16, 0)
        title_row.addWidget(IconWidget('settings', 16))
        title = QLabel('Settings')
        title.setStyleSheet(LABEL_TITLE)
        close_btn = IconButton('close', 28, 'Fechar')
        close_btn.clicked.connect(self.hide)
        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(close_btn)
        main_layout.addLayout(title_row)
        body = QHBoxLayout()
        body.setContentsMargins(16, 16, 16, 16)
        body.setSpacing(16)
        sidebar = QWidget()
        sidebar.setFixedWidth(140)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(6)
        self.btn_gen = SidebarButton('General')
        self.btn_prov = SidebarButton('LLM Providers')
        self.btn_sync = SidebarButton('Sync')
        self.btn_memory = SidebarButton('Memory')
        self.btn_persona = SidebarButton('Persona')
        self.btn_prompts = SidebarButton('Prompts')
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
        div.setStyleSheet('background: rgba(201,168,76,40);')
        body.addWidget(div)
        body.addWidget(self.stack, 1)
        main_layout.addLayout(body)
        bottom = QHBoxLayout()
        bottom.setContentsMargins(16, 0, 16, 16)
        self.status_lbl = QLabel('')
        self.status_lbl.setStyleSheet(f"color: {GOLD_BRIGHT_CSS}; font-family:{FONT}; font-weight:bold; font-size: 12px;")
        save_btn = QPushButton('Salvar Configurações')
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(BTN_PRIMARY)
        save_btn.setFixedWidth(200)
        save_btn.clicked.connect(self._save)
        bottom.addWidget(self.status_lbl)
        bottom.addStretch()
        bottom.addWidget(save_btn)
        main_layout.addLayout(bottom)

    def _on_tab_clicked(self, idx):
        self.stack.setCurrentIndex(idx)
        if idx == 3 and hasattr(self, 'memory_tab_widget'):
            self.memory_tab_widget.refresh()
            return
        return

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
        self.width_spin.setValue(int(os.getenv('SEQ_BAR_WIDTH', '600')))
        self.width_spin.setStyleSheet(SPINBOX_STYLE)
        self.width_spin.setSuffix(' px')
        self.width_spin.valueChanged.connect(self._on_size_changed)
        h_lbl = QLabel('Altura:')
        h_lbl.setStyleSheet(LABEL_SMALL)
        self.height_spin = QSpinBox()
        self.height_spin.setRange(44, 90)
        self.height_spin.setSingleStep(2)
        self.height_spin.setValue(int(os.getenv('SEQ_BAR_HEIGHT', '60')))
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
        lbl = QLabel('INTEGRAÇÕES (SYNC)')
        lbl.setStyleSheet(LABEL_SECTION)
        layout.addWidget(lbl)
        grid = QGridLayout()
        grid.setSpacing(12)
        self.ms_card = MicrosoftAuthCard()
        grid.addWidget(self.ms_card, 0, 0)
        self.google_card = GoogleAuthCard()
        grid.addWidget(self.google_card, 1, 0)
        grid.setRowStretch(2, 1)
        layout.addLayout(grid)
        return w

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
        desc.setStyleSheet(f"color: {TEXT_MID_CSS}; font-size: 11px; font-family: {FONT};")
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
        from PyQt6.QtWidgets import QTextEdit
        from core.storage import load_config
        from core.ai_triage import _DEFAULT_TRIAGE_PROMPT
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        lbl = QLabel('FILTRO DE NOTIFICAÇÕES (IA)')
        lbl.setStyleSheet(LABEL_SECTION)
        layout.addWidget(lbl)
        desc = QLabel('Escreva em linguagem natural o que é importante para você.\nO SEQ usará a IA para filtrar e-mails e mensagens com base nessas regras.')
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_MID_CSS}; font-size: 11px; font-family: {FONT};")
        layout.addWidget(desc)
        config = load_config()
        saved_prompt = config.get('triage_prompt', _DEFAULT_TRIAGE_PROMPT)
        self.prompt_editor = QTextEdit()
        self.prompt_editor.setPlainText(saved_prompt)
        self.prompt_editor.setStyleSheet(f'\n            QTextEdit {{\n                background: rgba(201,168,76, 10);\n                border: 1px solid rgba(201,168,76, 50);\n                border-radius: 8px;\n                color: {TEXT_CSS};\n                font-family: {FONT_MONO};\n                font-size: 11px;\n                padding: 8px;\n            }}\n        ')
        layout.addWidget(self.prompt_editor, 1)
        return w

    def paintEvent(self, event):
        p = QPainter(self)
        paint_panel(self, p, radius=20, bg=C_PANEL, border=C_GOLD)

    def _on_size_changed(self):
        self.resize_bar.emit(self.width_spin.value(), self.height_spin.value())

    def _save(self):
        new_settings = {}
        for (key, card) in self._cards.items():
            info = self._PROVIDERS[key]
            new_settings[info['env_key']] = card.get_key_value()
            new_settings[f"SEQ_{key.upper()}_MODEL"] = card.get_model_value()
        w = self.width_spin.value()
        h = self.height_spin.value()
        new_settings['SEQ_BAR_WIDTH'] = str(w)
        new_settings['SEQ_BAR_HEIGHT'] = str(h)
        self._api.save_settings(new_settings)
        self.status_lbl.setText('Salvo com sucesso!')
        self.resize_bar.emit(w, h)
        if hasattr(self, 'prompt_editor'):
            from core.storage import save_config
            save_config({'triage_prompt': self.prompt_editor.toPlainText()})
        if hasattr(self, 'persona_name_input'):
            from core.storage import save_config
            from core.database import SeqDB
            persona = {'name': self.persona_name_input.text().strip(), 'age': self.persona_age_input.text().strip(), 'email': self.persona_email_input.text().strip(), 'facts': [inp.text().strip() for inp in getattr(self, 'persona_fact_inputs', []) if inp.text().strip()]}
            save_config({'persona': persona})
            SeqDB.get_instance().sync_persona_profile(persona)
        QTimer.singleShot(2000, lambda: self.status_lbl.setText(''))
        self.settings_saved.emit()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(event.position().toPoint())
            if not isinstance(child, (QPushButton, QLineEdit, QSpinBox)):
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)
