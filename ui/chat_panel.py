__doc__ = '\nui/chat_panel.py  —  Painel de chat flutuante (Vanilla & Gold)\n'
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel, QPushButton, QFrame, QSizePolicy, QTextEdit
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QRectF
from PyQt6.QtGui import QColor, QPainter, QPen, QPainterPath
from ui.theme import paint_panel, C_PANEL, C_CREAM, C_GOLD, C_GOLD_BRIGHT, C_AI_MSG, C_USER_MSG, C_ERR_MSG, C_TEXT, C_TEXT_MID, C_TEXT_LIGHT, PANEL_CSS, CREAM_CSS, GOLD_CSS, GOLD_BRIGHT_CSS, TEXT_CSS, TEXT_MID_CSS, TEXT_LIGHT_CSS, FONT, SCROLL_STYLE, BTN_GHOST, BTN_CLOSE, LABEL_GOLD

class ChatInput(QTextEdit):
    enter_pressed = pyqtSignal()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                self.enter_pressed.emit()
                return
        super().keyPressEvent(event)

class MessageBubble(QFrame):

    def __init__(self, text: str, is_user: bool = False, is_error: bool = False, parent=None):
        super().__init__(parent)
        self.is_user = is_user
        self.is_error = is_error
        self._raw = text
        if self.is_error:
            self._bg = C_ERR_MSG
            self._border = QColor(200, 60, 40, 120)
            text_css = 'rgba(200,60,40,220)'
        elif self.is_user:
            self._bg = C_USER_MSG
            self._border = QColor(218, 183, 60, 160)
            text_css = TEXT_CSS
        else:
            self._bg = C_AI_MSG
            self._border = QColor(201, 168, 76, 80)
            text_css = TEXT_CSS
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 3, 0, 3)
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.label.setMaximumWidth(400)
        self.label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.label.setStyleSheet(f'\n            QLabel {{\n                color: {text_css};\n                padding: 10px 14px;\n                font-size: 13px;\n                font-family: {FONT};\n                line-height: 1.5;\n                background: transparent;\n            }}\n        ')
        if self.is_user:
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
        lrect = QRectF(lbl.x() - 0.5, 0.5, lbl.width() + 1, self.height() - 1)
        path = QPainterPath()
        path.addRoundedRect(lrect, 14, 14)
        p.setPen(QPen(self._border, 1))
        p.setBrush(self._bg)
        p.drawPath(path)

    def append_text(self, chunk: str):
        self._raw += chunk
        self.label.setText(self._raw)

    def set_text(self, text: str):
        self._raw = text
        self.label.setText(text)

    @property
    def full_text(self) -> str:
        return self._raw

class ChatPanel(QWidget):
    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(580, 480)
        from core.api_client import APIClient
        self._api = APIClient()
        self._history = []
        self._worker = None
        self._ai_bub = None
        self._drag_pos = None
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        header = QHBoxLayout()
        header.setSpacing(8)
        self.provider_lbl = QLabel()
        self.provider_lbl.setStyleSheet(LABEL_GOLD)
        self._refresh_provider_label()
        self.clear_btn = QPushButton('Clear')
        self.clear_btn.setStyleSheet(BTN_GHOST)
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.clicked.connect(self._clear_chat)
        self.close_btn = QPushButton('✕')
        self.close_btn.setFixedSize(26, 26)
        self.close_btn.setStyleSheet(BTN_CLOSE)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.clicked.connect(self._on_close)
        header.addWidget(self.provider_lbl)
        header.addStretch()
        header.addWidget(self.clear_btn)
        header.addWidget(self.close_btn)
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setFixedHeight(1)
        div.setStyleSheet('background: rgba(201,168,76,70);')
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
        self.status_lbl = QLabel('')
        self.status_lbl.setStyleSheet(f'color: rgba(160,126,30,180); font-size: 11px; font-style: italic; font-family: {FONT}; padding-left: 4px;')
        self.input_frame = _InputFrame()
        inner = QHBoxLayout(self.input_frame)
        inner.setContentsMargins(10, 4, 4, 4)
        inner.setSpacing(4)
        self.chat_input = ChatInput()
        self.chat_input.setPlaceholderText('Continue a conversa… (Enter envia · Shift+Enter quebra linha)')
        self.chat_input.setMaximumHeight(64)
        self.chat_input.setMinimumHeight(36)
        self.chat_input.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.chat_input.setStyleSheet(f'\n            QTextEdit {{\n                background: transparent;\n                border: none;\n                color: {TEXT_CSS};\n                font-size: 13px;\n                font-family: {FONT};\n            }}\n        ')
        self.chat_input.enter_pressed.connect(self._on_chat_send)
        self.chat_send = QPushButton('▶')
        self.chat_send.setFixedSize(32, 32)
        self.chat_send.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chat_send.setStyleSheet('\n            QPushButton {\n                background: rgba(201,168,76,215);\n                color: rgba(42,30,8,220);\n                border: none;\n                border-radius: 16px;\n                font-size: 11px;\n                font-weight: bold;\n            }\n            QPushButton:hover  { background: rgba(220,185,70,240); }\n            QPushButton:pressed { background: rgba(155,118,18,245); color: rgba(255,248,220,240); }\n            QPushButton:disabled { background: rgba(201,168,76,60); color: rgba(120,100,60,100); }\n        ')
        self.chat_send.clicked.connect(self._on_chat_send)
        inner.addWidget(self.chat_input, 1)
        inner.addWidget(self.chat_send)
        layout.addLayout(header)
        layout.addWidget(div)
        layout.addWidget(self.scroll, 1)
        layout.addWidget(self.status_lbl)
        layout.addWidget(self.input_frame)

    def paintEvent(self, event):
        p = QPainter(self)
        paint_panel(self, p, radius=20, bg=C_PANEL, border=C_GOLD)

    def _refresh_provider_label(self):
        provider = self._api.get_active_provider()
        if provider:
            info = self._api.get_provider_info(provider)
            self.provider_lbl.setText(f"✦ Seq  ·  {info.get('name', provider.title())}")
            return
        self.provider_lbl.setText('✦ Seq  ·  ⚠ Configure um provider')

    def refresh_provider(self):
        self._api.reload()
        self._refresh_provider_label()

    def send_message(self, text: str):
        text = text.strip()
        if not text:
            return
        self._add_bubble(text, is_user=True)
        self._history.append({'role': 'user', 'content': text})
        if not self._api.get_active_provider():
            self._add_bubble('⚠  Nenhum provider configurado.\nClique nos 4 pontinhos → ⚙ Settings e adicione uma chave de API.', is_user=False, is_error=True)
            return
        self._start_stream()

    def _start_stream(self):
        if self._worker and self._worker.isRunning():
            return
        self.chat_send.setEnabled(False)
        self.status_lbl.setText('Pensando…')
        self._ai_bub = self._add_bubble('▍', is_user=False)
        try:
            self._worker = self._api.create_worker(self._history)
            self._worker.chunk_received.connect(self._on_chunk)
            self._worker.finished.connect(self._on_done)
            self._worker.error_occurred.connect(self._on_error)
            self._worker.start()
        except ValueError as e:
            self._on_error(str(e))

    def _on_chunk(self, text: str):
        if self._ai_bub is None:
            return
        if self._ai_bub.full_text == '▍':
            self._ai_bub.set_text(text)
        else:
            self._ai_bub.append_text(text)
        self._scroll_bottom()

    def _on_done(self):
        self.status_lbl.setText('')
        self.chat_send.setEnabled(True)
        if self._ai_bub and self._ai_bub.full_text not in ('', '▍'):
            self._history.append({'role': 'assistant', 'content': self._ai_bub.full_text})
        self._ai_bub = None
        self._worker = None

    def _on_error(self, msg: str):
        self.status_lbl.setText('')
        self.chat_send.setEnabled(True)
        if self._ai_bub:
            self._ai_bub.is_error = True
            self._ai_bub._bg = C_ERR_MSG
            self._ai_bub._border = QColor(200, 60, 40, 120)
            self._ai_bub.label.setStyleSheet(f'QLabel {{ color: rgba(200,60,40,220); padding:10px 14px; font-size:13px; font-family:{FONT}; background:transparent; }}')
            self._ai_bub.set_text(f'⚠ {msg}')
        self._ai_bub = None
        self._worker = None

    def _add_bubble(self, text: str, is_user: bool = False, is_error: bool = False) -> MessageBubble:
        bub = MessageBubble(text, is_user=is_user, is_error=is_error)
        self.msg_layout.insertWidget(self.msg_layout.count() - 1, bub)
        self._scroll_bottom()
        return bub

    def _clear_chat(self):
        self._history.clear()
        while self.msg_layout.count() > 1:
            item = self.msg_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _scroll_bottom(self):
        QTimer.singleShot(40, lambda: self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum()))

    def _on_chat_send(self):
        text = self.chat_input.toPlainText().strip()
        if text:
            self.chat_input.clear()
            self.send_message(text)
            return
        return

    def _on_close(self):
        if self._worker and self._worker.isRunning():
            self._worker.stop()
        self.hide()
        self.closed.emit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._on_close()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(event.position().toPoint())
            if not isinstance(child, (QPushButton, QTextEdit)):
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

class _InputFrame(QWidget):
    """Contêiner do input de chat com borda dourada antialiased."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def paintEvent(self, event):
        p = QPainter(self)
        paint_panel(self, p, radius=12, bg=QColor(255, 253, 247, 200), border=QColor(201, 168, 76, 160))
