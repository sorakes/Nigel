"""
ui/notification.py — Popup de lembrete premium do SEQ com Skills de Agenda.

ScheduleAlertDialog:
- Aparece no canto superior direito
- Mostra título + descrição do lembrete
- Botões fixos: Concluir | +10min | +1h | Cancelar
- Chat embutido com IA que TEM SKILLS REAIS para controlar a agenda
- A IA retorna JSON de ações; botões nativos garantem confirmação
- Auto-close após 90s sem interação
"""
import uuid
from datetime import datetime
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QScrollArea, QFrame, QApplication, QSizePolicy
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter, QColor, QFont
from ui.theme import paint_panel, C_PANEL, C_GOLD, C_GOLD_BRIGHT, C_TEXT, C_TEXT_MID, TEXT_CSS, TEXT_MID_CSS, GOLD_BRIGHT_CSS, FONT, BTN_PRIMARY, BTN_CLOSE, SCROLL_STYLE
from ui.agenda_skills import AgendaSkillExecutor, build_notification_system_prompt, visible_text, parse_skills_json, trigger_ui_update
from core.scheduler import parse_due_at

_BTN_ACTION = f"""
    QPushButton {{
        background: rgba(201,168,76, 18);
        border: 1px solid rgba(201,168,76, 70);
        color: {TEXT_CSS};
        font-size: 11px;
        font-family: {FONT};
        border-radius: 7px;
        padding: 5px 8px;
        font-weight: 500;
    }}
    QPushButton:hover {{ background: rgba(201,168,76, 55); color: {GOLD_BRIGHT_CSS}; }}
    QPushButton:pressed {{ background: rgba(201,168,76, 80); }}
"""
_BTN_DYNAMIC = f"""
    QPushButton {{
        background: rgba(201,168,76, 30);
        border: 1px solid rgba(201,168,76, 120);
        color: {GOLD_BRIGHT_CSS};
        font-size: 11px;
        font-family: {FONT};
        border-radius: 7px;
        padding: 5px 10px;
        font-weight: bold;
    }}
    QPushButton:hover {{ background: rgba(201,168,76, 70); }}
"""
_INPUT_STYLE = f"""
    QLineEdit {{
        background: rgba(201,168,76, 10);
        border: 1px solid rgba(201,168,76, 60);
        border-radius: 8px;
        color: {TEXT_CSS};
        font-size: 12px;
        font-family: {FONT};
        padding: 6px 10px;
    }}
    QLineEdit:focus {{ border: 1px solid rgba(201,168,76, 150); }}
"""
_AI_MSG_CSS = f"""
    QLabel {{
        color: {TEXT_CSS};
        font-size: 12px;
        font-family: {FONT};
        background: rgba(201,168,76, 8);
        border: 1px solid rgba(201,168,76, 35);
        border-radius: 8px;
        padding: 8px 10px;
        line-height: 1.5;
    }}
"""
_USER_MSG_CSS = f"""
    QLabel {{
        color: {TEXT_CSS};
        font-size: 12px;
        font-family: {FONT};
        background: rgba(255,255,255, 6);
        border: 1px solid rgba(255,255,255, 20);
        border-radius: 8px;
        padding: 8px 10px;
    }}
"""
_STATUS_CSS = f"""
    QLabel {{
        color: rgba(100,200,100,200);
        font-size: 11px;
        font-family: {FONT};
        font-style: italic;
        background: transparent;
        border: none;
        padding: 2px 0px;
    }}
"""

class ScheduleAlertDialog(QWidget):
    """Popup rico de lembrete com chat IA e skills de agenda."""
    _instances: list['ScheduleAlertDialog'] = []

    @classmethod
    def show_alert(cls, item: dict, *, anchor: QWidget | None = None):
        sid = item.get('id')
        for pop in cls._instances:
            if pop._item.get('id') == sid and pop.isVisible():
                pop.raise_()
                pop.activateWindow()
                return
        pop = cls(item)
        pop._anchor = anchor
        cls._instances.append(pop)
        pop._reposition_all()
        pop.show()
        pop.raise_()
        pop.activateWindow()
        print(f"[SEQ] Popup exibido: id={sid} — {item.get('title', '')[:50]}")

    def __init__(self, item: dict):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(380)
        self._item = item
        self._anchor = None
        self._worker = None
        self._last_user_text = ''
        self._ai_buffer = ''
        self._ai_label = None
        self._history = []
        self._executor = AgendaSkillExecutor(item=item, dialog=self)
        self._system_prompt = build_notification_system_prompt(item)
        self._build()
        self._start_ai_greeting()
        self._auto_timer = QTimer(self)
        self._auto_timer.setSingleShot(True)
        self._auto_timer.timeout.connect(self._close)
        self._auto_timer.start(90000)

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        header = QHBoxLayout()
        icon = QLabel('⏰')
        icon.setStyleSheet('font-size: 18px; background: transparent; border: none;')
        title_lbl = QLabel(self._item.get('title', 'Lembrete'))
        title_lbl.setWordWrap(True)
        title_lbl.setStyleSheet(f"color: {GOLD_BRIGHT_CSS}; font-family: {FONT}; font-size: 13px; font-weight: bold; background: transparent; border: none;")
        close_btn = QPushButton('✕')
        close_btn.setFixedSize(22, 22)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(BTN_CLOSE)
        close_btn.clicked.connect(self._close)
        header.addWidget(icon)
        header.addWidget(title_lbl, 1)
        header.addWidget(close_btn)
        layout.addLayout(header)
        desc = self._item.get('description', '')
        if desc:
            d = QLabel(desc)
            d.setWordWrap(True)
            d.setStyleSheet(f"color: {TEXT_MID_CSS}; font-size: 11px; font-family: {FONT}; background: transparent; border: none;")
            layout.addWidget(d)
        try:
            due = parse_due_at(self._item.get('due_at', ''))
            diff_sec = int((datetime.now() - due).total_seconds())
            if diff_sec < 60:
                time_str = 'Venceu agora!'
            elif diff_sec < 3600:
                time_str = f"Venceu há {diff_sec // 60} min"
            else:
                time_str = f"Venceu às {due.strftime('%H:%M')}"
        except Exception:
            time_str = ''
        if time_str:
            t = QLabel(f"🕐 {time_str}")
            t.setStyleSheet(f"color: rgba(200,80,50,220); font-size: 11px; font-family: {FONT}; background: transparent; border: none;")
            layout.addWidget(t)
        layout.addWidget(self._sep())
        action_row = QHBoxLayout()
        action_row.setSpacing(4)
        for label, fn in (('✅ Concluir', self._on_done), ('⏳ +10 min', lambda : self._on_postpone(10)), ('⏳ +1 hora', lambda : self._on_postpone(60)), ('❌ Cancelar', self._on_cancel)):
            b = QPushButton(label)
            b.setStyleSheet(_BTN_ACTION)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(fn)
            action_row.addWidget(b)
        layout.addLayout(action_row)
        layout.addWidget(self._sep())
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet(SCROLL_STYLE)
        self._scroll.setFixedHeight(130)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._msg_container = QWidget()
        self._msg_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._msg_layout = QVBoxLayout(self._msg_container)
        self._msg_layout.setContentsMargins(0, 2, 0, 2)
        self._msg_layout.setSpacing(5)
        self._msg_layout.addStretch()
        self._scroll.setWidget(self._msg_container)
        layout.addWidget(self._scroll)
        self._dynamic_container = QWidget()
        self._dynamic_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._dynamic_layout = QHBoxLayout(self._dynamic_container)
        self._dynamic_layout.setContentsMargins(0, 0, 0, 0)
        self._dynamic_layout.setSpacing(5)
        self._dynamic_layout.addStretch()
        self._dynamic_container.hide()
        layout.addWidget(self._dynamic_container)
        self._status_lbl = QLabel('')
        self._status_lbl.setStyleSheet(_STATUS_CSS)
        self._status_lbl.hide()
        layout.addWidget(self._status_lbl)
        input_row = QHBoxLayout()
        input_row.setSpacing(6)
        self._input = QLineEdit()
        self._input.setPlaceholderText('Peça à IA para controlar seu lembrete…')
        self._input.setStyleSheet(_INPUT_STYLE)
        self._input.returnPressed.connect(self._on_user_send)
        self._input.textChanged.connect(self._reset_auto_timer)
        send_btn = QPushButton('→')
        send_btn.setFixedSize(32, 32)
        send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        send_btn.setStyleSheet(BTN_PRIMARY)
        send_btn.clicked.connect(self._on_user_send)
        input_row.addWidget(self._input, 1)
        input_row.addWidget(send_btn)
        layout.addLayout(input_row)
        self.adjustSize()

    def _sep(self) -> QFrame:
        s = QFrame()
        s.setFrameShape(QFrame.Shape.HLine)
        s.setStyleSheet('background: rgba(201,168,76,40); border: none;')
        s.setFixedHeight(1)
        return s

    def _add_msg(self, text: str, is_user: bool) -> QLabel:
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lbl.setStyleSheet(_USER_MSG_CSS if is_user else _AI_MSG_CSS)
        if is_user:
            row = QHBoxLayout()
            row.addStretch()
            row.addWidget(lbl)
            self._msg_layout.insertLayout(self._msg_layout.count() - 1, row)
        else:
            self._msg_layout.insertWidget(self._msg_layout.count() - 1, lbl)
        self._scroll_bottom()
        return lbl

    def _add_status(self, text: str):
        self._status_lbl.setText(text)
        self._status_lbl.show()
        QTimer.singleShot(3000, lambda : (self._status_lbl.hide(), self._status_lbl.setText('')))

    def _scroll_bottom(self):
        QTimer.singleShot(30, lambda : self._scroll.verticalScrollBar().setValue(self._scroll.verticalScrollBar().maximum()))

    def _start_ai_greeting(self):
        from core.api_client import APIClient
        title = self._item.get('title', 'Lembrete')
        desc = self._item.get('description', '')
        greeting_prompt = f"O lembrete '{title}' acabou de vencer." + (f" Contexto: {desc}." if desc else '') + ' Dê uma mensagem EXTREMAMENTE curta (1 linha) avisando.' + " REGRA: NÃO gere nenhum JSON ou 'buttons' agora. Apenas avise o vencimento e espere o usuário dizer o que quer."
        self._history = [{'role': 'user', 'content': greeting_prompt}]
        self._ai_label = self._add_msg('🧠 …', is_user=False)
        self._ai_buffer = ''
        api = APIClient()
        self._worker = api.create_worker([{'role': 'system', 'content': self._system_prompt}, {'role': 'user', 'content': greeting_prompt}])
        self._worker.chunk_received.connect(self._on_greeting_chunk)
        self._worker.finished.connect(self._on_greeting_done)
        self._worker.error_occurred.connect(self._on_ai_error)
        self._worker.start()

    def _on_user_send(self):
        text = self._input.text().strip()
        if not text or (self._worker and self._worker.isRunning()):
            return
        self._input.clear()
        self._reset_auto_timer()
        self._clear_dynamic_buttons()
        self._last_user_text = text
        self._executor._user_text = text
        self._add_msg(text, is_user=True)
        self._history.append({'role': 'user', 'content': text})
        self._ai_label = self._add_msg('🧠 …', is_user=False)
        self._ai_buffer = ''
        from core.api_client import APIClient
        messages = [{'role': 'system', 'content': self._system_prompt}] + self._history
        api = APIClient()
        self._worker = api.create_worker(messages)
        self._worker.chunk_received.connect(self._on_user_chunk)
        self._worker.finished.connect(self._on_user_done)
        self._worker.error_occurred.connect(self._on_ai_error)
        self._worker.start()

    def _visible_text(self, buf: str) -> str:
        return visible_text(buf)

    def _on_greeting_chunk(self, text: str):
        self._ai_buffer += text
        if self._ai_label:
            self._ai_label.setText(self._visible_text(self._ai_buffer) or '🧠 …')
        self._scroll_bottom()

    def _on_greeting_done(self):
        self._worker = None
        visible = self._visible_text(self._ai_buffer)
        if self._ai_label:
            self._ai_label.setText(visible or '🧠 O que deseja fazer com este lembrete?')
        self._history.append({'role': 'assistant', 'content': self._ai_buffer})
        self._parse_and_execute(self._ai_buffer, auto_execute=False)
        self.adjustSize()
        self._reposition_all()

    def _on_user_chunk(self, text: str):
        self._ai_buffer += text
        if self._ai_label:
            self._ai_label.setText(self._visible_text(self._ai_buffer) or '🧠 …')
        self._scroll_bottom()

    def _on_user_done(self):
        self._worker = None
        visible = self._visible_text(self._ai_buffer)
        if self._ai_label:
            self._ai_label.setText(visible or '🧠 Ação pronta para confirmação:')
        self._history.append({'role': 'assistant', 'content': self._ai_buffer})
        self._parse_and_execute(self._ai_buffer, auto_execute=True)
        self.adjustSize()
        self._reposition_all()

    def _on_chunk(self, text: str):
        self._on_greeting_chunk(text)

    def _on_ai_done(self):
        self._on_greeting_done()

    def _on_ai_error(self, err: str):
        self._worker = None
        if self._ai_label:
            self._ai_label.setText('⚠️ Sem conexão com IA. Use os botões acima.')
            return
        return

    def _parse_and_execute(self, text: str, auto_execute: bool = True):
        from ui.agenda_skills import parse_skills_json, normalize_action
        data = parse_skills_json(text)
        if not data:
            return
        user_text = self._last_user_text
        if auto_execute:
            for action in data.get('actions', []):
                result = self._executor.execute(normalize_action(action, user_text), user_text=user_text)
                self._add_msg(result, is_user=False)
                self._add_status(result)
                self._auto_timer.stop()
        buttons = data.get('buttons', [])[:3]
        if buttons:
            self._clear_dynamic_buttons()
            for btn_def in buttons:
                label = btn_def.get('label', 'Ação')
                confirm_action = btn_def.get('confirm_action')
                if not confirm_action and 'action' in btn_def:
                    confirm_action = {'type': btn_def['action']}
                btn = QPushButton(label)
                btn.setStyleSheet(_BTN_DYNAMIC)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                if confirm_action:
                    btn.clicked.connect(lambda checked, a=confirm_action: self._on_button_action(a))
                self._dynamic_layout.insertWidget(self._dynamic_layout.count() - 1, btn)
            self._dynamic_container.show()
            return
        return

    def _on_button_action(self, action):
        from ui.agenda_skills import normalize_action
        self._clear_dynamic_buttons()
        self._auto_timer.stop()
        user_text = self._last_user_text
        if isinstance(action, list):
            results = [self._executor.execute(normalize_action(a, user_text), user_text=user_text) for a in action]
            result = ' / '.join(results)
        else:
            result = self._executor.execute(normalize_action(action, user_text), user_text=user_text)
        self._add_msg(result, is_user=False)
        self._add_status(result)
        self.adjustSize()
        self._reposition_all()

    def _clear_dynamic_buttons(self):
        while self._dynamic_layout.count() > 1:
            item = self._dynamic_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._dynamic_container.hide()

    def _on_done(self):
        self._auto_timer.stop()
        result = self._executor.execute({'type': 'mark_done'})
        self._add_msg(result, is_user=False)
        self._add_status(result)

    def _on_postpone(self, mins: int):
        self._auto_timer.stop()
        result = self._executor.execute({'type': 'postpone', 'minutes': mins})
        self._add_msg(result, is_user=False)
        self._add_status(result)

    def _on_cancel(self):
        self._auto_timer.stop()
        result = self._executor.execute({'type': 'delete_current'})
        self._add_msg(result, is_user=False)
        self._add_status(result)

    def _reset_auto_timer(self):
        self._auto_timer.start(90000)

    def _close(self):
        if len(self._history) > 1:
            self._save_chat_history()
        if self._worker and self._worker.isRunning():
            self._worker.quit()
        if self in ScheduleAlertDialog._instances:
            ScheduleAlertDialog._instances.remove(self)
        self.close()
        ScheduleAlertDialog._reposition_all()

    def _save_chat_history(self):
        from core.database import SeqDB
        import uuid
        chat_lines = []
        for msg in self._history:
            if msg['role'] == 'system':
                continue
            role = 'SEQ' if msg['role'] == 'assistant' else 'Você'
            content = msg['content']
            if role == 'SEQ':
                content = self._visible_text(content) or '[Gerou ações/botões]'
            chat_lines.append(f"{role}: {content}")
        transcript = '\n\n'.join(chat_lines)
        title = self._item.get('title', 'Lembrete')
        subject = f"Histórico: {title}"
        SeqDB.get_instance().save_important(item={'id': str(uuid.uuid4()), 'source': 'agenda_chat', 'subject': subject, 'sender': '', 'body_preview': transcript, 'ai_summary': f"Transcrição do chat sobre o lembrete '{title}'", 'ai_reason': 'Histórico de conversa salvo automaticamente após fechar a notificação', 'relevance_score': 40}, saved_by='ai')
        trigger_ui_update()

    def paintEvent(self, event):
        p = QPainter(self)
        paint_panel(self, p, radius=14, bg=C_PANEL, border=C_GOLD)

    @classmethod
    def _reposition_all(cls):
        anchor = None
        for pop in cls._instances:
            if getattr(pop, '_anchor', None) is not None:
                anchor = pop._anchor
                break
        if anchor is not None:
            screen = QApplication.screenAt(anchor.frameGeometry().center())
        else:
            screen = None
        if screen is None:
            screen = QApplication.primaryScreen()
        geom = screen.availableGeometry()
        current_y = geom.top() + 20
        for pop in cls._instances:
            pop.adjustSize()
            x = geom.right() - pop.width() - 20
            pop.move(x, current_y)
            current_y += pop.height() + 10

class NotificationPopup:
    @classmethod
    def show_msg(cls, item: dict, anchor: QWidget | None = None):
        ScheduleAlertDialog.show_alert(item, anchor=anchor)
