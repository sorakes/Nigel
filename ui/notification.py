"""
ui/notification.py — Popup de lembrete do Nigel com Skills de Agenda.

ScheduleAlertDialog:
- Aparece no canto superior direito
- Mostra título + descrição do lembrete
- Botões fixos: Concluir | +10min | +1h | Cancelar
- Chat embutido com IA que TEM SKILLS REAIS para controlar a agenda
- A IA retorna JSON de ações; botões nativos garantem confirmação
- Auto-close após 90s sem interação
"""
import webbrowser
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QScrollArea, QFrame, QApplication, QTextEdit,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtCore import QThread
from PyQt6.QtGui import QPainter
from ui.theme import (
    paint_panel, css, C_BG, C_BORDER, C_TEXT_2, C_GOLD,
    C_SUCCESS,
    TEXT_CSS, TEXT_2_CSS, SURFACE_CSS, RAISED_CSS, OVERLAY_CSS,
    BORDER_CSS, BORDER_HI_CSS, WARNING_CSS, PERSONA_CSS, FONT, FS_SM, FS_MD, FS_BASE,
    R_SM, BTN_ICON, BTN_CLOSE, SCROLL_STYLE, INPUT_STYLE, TEXTEDIT_STYLE,
)
from ui.icons import IconWidget
from ui.agenda_skills import trigger_ui_update
from core.scheduler import parse_due_at

# Lembretes e alertas de e-mail empilham no MESMO canto da tela, um so
# gerenciador de posicao evita que um tipo cubra o outro quando os dois
# aparecem ao mesmo tempo.
_POPUP_STACK: list[QWidget] = []


def _register_popup(widget: QWidget) -> None:
    if widget not in _POPUP_STACK:
        _POPUP_STACK.append(widget)


def _unregister_popup(widget: QWidget) -> None:
    if widget in _POPUP_STACK:
        _POPUP_STACK.remove(widget)


def _reposition_popup_stack(anchor: QWidget | None = None) -> None:
    screen = None
    if anchor is not None:
        try:
            screen = QApplication.screenAt(anchor.frameGeometry().center())
        except Exception:
            screen = None
    if screen is None:
        for pop in _POPUP_STACK:
            a = getattr(pop, '_anchor', None)
            if a is not None:
                screen = QApplication.screenAt(a.frameGeometry().center())
                if screen is not None:
                    break
    if screen is None:
        screen = QApplication.primaryScreen()
    geom = screen.availableGeometry()
    current_y = geom.top() + 20
    for pop in _POPUP_STACK:
        if not pop.isVisible():
            continue
        pop.adjustSize()
        x = geom.right() - pop.width() - 20
        pop.move(x, current_y)
        current_y += pop.height() + 10


class _BgCall(QThread):
    """Roda uma chamada (ferramenta do Composio, LLM) fora da thread da UI.

    Sem isso o popup travaria durante um HTTP do Composio ou do provider —
    o mesmo motivo pelo qual o loop do agente roda em QThread na barra."""

    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            self.done.emit(self._fn())
        except Exception as e:
            self.failed.emit(f'{type(e).__name__}: {e}')


_BTN_ACTION = f"""
    QPushButton {{
        background: {RAISED_CSS};
        border: 1px solid {BORDER_CSS};
        color: {TEXT_CSS};
        font-size: {FS_SM}px;
        font-family: {FONT};
        border-radius: {R_SM}px;
        padding: 5px 8px;
        font-weight: 500;
    }}
    QPushButton:hover   {{ background: {OVERLAY_CSS}; border-color: {BORDER_HI_CSS}; }}
    QPushButton:pressed {{ background: {SURFACE_CSS}; }}
"""
_BTN_DYNAMIC = f"""
    QPushButton {{
        background: {OVERLAY_CSS};
        border: 1px solid {BORDER_HI_CSS};
        color: {TEXT_CSS};
        font-size: {FS_SM}px;
        font-family: {FONT};
        border-radius: {R_SM}px;
        padding: 5px 10px;
        font-weight: 600;
    }}
    QPushButton:hover {{ border-color: {css(C_GOLD, 130)}; }}
"""
_INPUT_STYLE = INPUT_STYLE
_AI_MSG_CSS = f"""
    QLabel {{
        color: {TEXT_CSS};
        font-size: {FS_MD}px;
        font-family: {FONT};
        background: {SURFACE_CSS};
        border: none;
        border-radius: {R_SM}px;
        padding: 8px 10px;
        line-height: 1.5;
    }}
"""
_USER_MSG_CSS = f"""
    QLabel {{
        color: {TEXT_CSS};
        font-size: {FS_MD}px;
        font-family: {FONT};
        background: {RAISED_CSS};
        border: 1px solid {BORDER_CSS};
        border-radius: {R_SM}px;
        padding: 8px 10px;
    }}
"""
_STATUS_CSS = f"""
    QLabel {{
        color: {css(C_SUCCESS, 220)};
        font-size: {FS_SM}px;
        font-family: {FONT};
        font-style: italic;
        background: transparent;
        border: none;
    }}
"""


class ScheduleAlertDialog(QWidget):
    """Popup de lembrete: mesmo agente v2 dos outros popups (ver EmailAlertDialog),
    não mais o pipeline v1 de JSON-em-texto.

    Antes: uma chamada de LLM só pra dizer "seu lembrete venceu" (latência sem
    motivo — a UI já sabe disso), e um parser de JSON solto no texto pra achar
    botões. Agora: os 4 botões fixos disparam `schedule_*` direto (sem LLM
    nenhum — clicar "Concluir" já É a confirmação), e o campo de texto livre
    usa o mesmo `AgentWorker` com ferramentas `schedule_*` que todo o resto
    do app usa, com o mesmo mecanismo de confirmação quando precisar.
    """
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
        _register_popup(pop)
        _reposition_popup_stack(anchor)
        pop.show()
        pop.raise_()
        pop.activateWindow()
        print(f"[Nigel] Popup exibido: id={sid} — {item.get('title', '')[:50]}")

    def __init__(self, item: dict):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(380)
        self._item = item
        self._anchor = None
        self._ai_worker = None
        self._bg = None
        self._history: list[dict] = []
        self._build()
        self._auto_timer = QTimer(self)
        self._auto_timer.setSingleShot(True)
        self._auto_timer.timeout.connect(self._close)
        self._auto_timer.start(90000)

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        header = QHBoxLayout()
        ttype = self._item.get('task_type', 'reminder')
        icon_name = {'check_emails': 'email', 'daily_briefing': 'clock',
                     'agent_prompt': 'ai'}.get(ttype, 'bell')
        icon = IconWidget(icon_name, 16, color=C_TEXT_2)
        title_lbl = QLabel(self._item.get('title', 'Lembrete do Nigel'))
        title_lbl.setWordWrap(True)
        title_lbl.setStyleSheet(f"color: {TEXT_CSS}; font-family: {FONT}; font-size: {FS_BASE}px; font-weight: 600; background: transparent; border: none;")
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
            d.setStyleSheet(f"color: {TEXT_2_CSS}; font-size: 11px; font-family: {FONT}; background: transparent; border: none;")
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
            t = QLabel(time_str)
            t.setStyleSheet(f"color: {WARNING_CSS}; font-size: {FS_SM}px; font-family: {FONT}; background: transparent; border: none;")
            layout.addWidget(t)
        layout.addWidget(self._sep())
        action_row = QHBoxLayout()
        action_row.setSpacing(4)
        for label, fn in (('Concluir', self._on_done), ('+10 min', lambda: self._on_postpone(10)),
                          ('+1 hora', lambda: self._on_postpone(60)), ('Cancelar', self._on_cancel)):
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
        input_row = QHBoxLayout()
        input_row.setSpacing(6)
        self._input = QLineEdit()
        self._input.setPlaceholderText('Peça à IA para controlar seu lembrete…')
        self._input.setStyleSheet(_INPUT_STYLE)
        self._input.returnPressed.connect(self._on_ask_ai)
        self._input.textChanged.connect(self._reset_auto_timer)
        send_btn = QPushButton('→')
        send_btn.setFixedSize(32, 32)
        send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        send_btn.setStyleSheet(BTN_ICON)
        send_btn.clicked.connect(self._on_ask_ai)
        input_row.addWidget(self._input, 1)
        input_row.addWidget(send_btn)
        layout.addLayout(input_row)
        self.adjustSize()

    def _sep(self) -> QFrame:
        s = QFrame()
        s.setFrameShape(QFrame.Shape.HLine)
        s.setStyleSheet(f'background: {BORDER_CSS}; border: none;')
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
        self.adjustSize()
        _reposition_popup_stack(self._anchor)
        return lbl

    def _reset_auto_timer(self):
        self._auto_timer.start(90000)

    def _dispatch_tool(self, name: str, args: dict, ok_hint: str):
        def _do():
            from core.agent.loop import new_context
            from core.agent.registry import ToolRegistry
            from core.llm.types import ToolCall
            from core.tools import schedule_tools
            reg = ToolRegistry(schedule_tools.build_tools())
            return reg.dispatch(ToolCall('ui', name, args), new_context())

        def _done(result):
            self._add_msg(result.user_message or ('Feito.' if result.ok else result.error), is_user=False)
            if result.ok:
                self._auto_timer.stop()

        self._bg = _BgCall(_do)
        self._bg.done.connect(_done)
        self._bg.failed.connect(lambda e: self._add_msg(f'Erro: {e}', is_user=False))
        self._bg.start()

    def _on_done(self):
        self._dispatch_tool('schedule_complete', {'schedule_id': self._item.get('id')}, 'Concluído')

    def _on_postpone(self, mins: int):
        self._dispatch_tool('schedule_postpone', {'schedule_id': self._item.get('id'), 'minutes': mins}, 'Adiado')

    def _on_cancel(self):
        self._dispatch_tool('schedule_delete', {'schedule_id': self._item.get('id')}, 'Removido')

    def _on_ask_ai(self):
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()
        self._reset_auto_timer()
        self._add_msg(text, is_user=True)
        self._history.append({'role': 'user', 'content': text})
        ai_lbl = self._add_msg('…', is_user=False)

        item = self._item
        system = (
            "You are Nigel, handling ONE specific reminder the user is looking at right now. "
            f"Title: {item.get('title', '')}. Description: {item.get('description', '')}. "
            f"schedule_id={item.get('id')}. "
            "Use the schedule_* tools with this schedule_id directly - do not call schedule_list "
            "unless the user asks about a DIFFERENT reminder. "
            "Reply to the user in Brazilian Portuguese, short."
        )
        from ui.agent_worker import spawn
        from core.agent.registry import ToolRegistry
        from core.tools import schedule_tools
        registry = ToolRegistry(schedule_tools.build_tools())
        w = spawn(system, [{'role': 'user', 'content': text}], registry, max_iterations=4)
        self._ai_worker = w
        buf = {'text': ''}

        def on_delta(d):
            buf['text'] += d
            ai_lbl.setText(buf['text'] or '…')

        def on_tool_end(name, msg, ok):
            self._add_msg(('✓ ' if ok else '✗ ') + (msg or name), is_user=False)
            self._auto_timer.stop()

        def on_confirm(name, label, icon):
            self._add_confirm_buttons(w, label)

        def on_answer(txt):
            visible = (txt or buf['text'] or '...').strip() or '...'
            ai_lbl.setText(visible)
            self._history.append({'role': 'assistant', 'content': visible})
            self.adjustSize()
            _reposition_popup_stack(self._anchor)
            trigger_ui_update()

        def on_fail(msg):
            ai_lbl.setText(f'Erro: {msg}')

        w.text_delta.connect(on_delta)
        w.tool_finished.connect(on_tool_end)
        w.confirm_requested.connect(on_confirm)
        w.answer_ready.connect(on_answer)
        w.failed.connect(on_fail)
        w.start()

    def _add_confirm_buttons(self, worker, label: str):
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 2, 0, 2)
        h.setSpacing(6)
        h.addStretch()
        btn_no = QPushButton('Cancelar')
        btn_no.setStyleSheet(_BTN_ACTION)
        btn_no.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_yes = QPushButton('Confirmar')
        btn_yes.setStyleSheet(_BTN_DYNAMIC)
        btn_yes.setCursor(Qt.CursorShape.PointingHandCursor)
        h.addWidget(btn_no)
        h.addWidget(btn_yes)
        self._msg_layout.insertWidget(self._msg_layout.count() - 1, row)
        self.adjustSize()
        _reposition_popup_stack(self._anchor)

        def _cleanup():
            row.setParent(None)
            row.deleteLater()

        def _no():
            _cleanup()
            self._add_msg(f'Cancelado: {label}', is_user=False)

        def _yes():
            _cleanup()
            call = worker.result.pending_confirmation if worker and worker.result else None
            registry = getattr(worker, 'registry', None) if worker else None
            if not (call and registry):
                self._add_msg('Não consegui recuperar a ação para confirmar.', is_user=False)
                return
            self._add_msg(f'{label}…', is_user=False)

            def _do():
                from core.agent.loop import new_context
                return registry.dispatch(call, new_context())

            def _done(result):
                self._add_msg(result.user_message or ('Feito.' if result.ok else result.error),
                              is_user=False)
                self.adjustSize()
                _reposition_popup_stack(self._anchor)

            bg = _BgCall(_do)
            self._bg = bg
            bg.done.connect(_done)
            bg.start()

        btn_no.clicked.connect(_no)
        btn_yes.clicked.connect(_yes)

    def _close(self):
        if len(self._history) > 1:
            self._save_chat_history()
        if self._ai_worker is not None and self._ai_worker.isRunning():
            self._ai_worker.stop()
        if self in ScheduleAlertDialog._instances:
            ScheduleAlertDialog._instances.remove(self)
        _unregister_popup(self)
        self.close()
        _reposition_popup_stack(self._anchor)

    def _save_chat_history(self):
        from core.database import SeqDB
        import uuid
        chat_lines = []
        for msg in self._history:
            role = 'Nigel' if msg['role'] == 'assistant' else 'Você'
            chat_lines.append(f"{role}: {msg['content']}")
        transcript = '\n\n'.join(chat_lines)
        title = self._item.get('title', 'Lembrete')
        subject = f"Histórico: {title}"
        SeqDB.get_instance().save_important(item={'id': str(uuid.uuid4()), 'source': 'agenda_chat', 'subject': subject, 'sender': '', 'body_preview': transcript, 'ai_summary': f"Transcrição do chat sobre o lembrete '{title}'", 'ai_reason': 'Histórico de conversa salvo automaticamente após fechar a notificação', 'relevance_score': 40}, saved_by='ai')
        trigger_ui_update()

    def paintEvent(self, event):
        p = QPainter(self)
        paint_panel(self, p, radius=14, bg=C_BG, border=C_BORDER)


class EmailAlertDialog(QWidget):
    """Popup de e-mail importante.

    Aparece sozinho quando a triagem em background classifica uma mensagem
    como relevante. Mostra por que importa e deixa agir na hora — responder,
    arquivar, marcar como lida, criar um lembrete de follow-up — sem abrir
    o Gmail. Um campo de texto livre no rodape delega ao mesmo agente com
    ferramentas de e-mail, para pedidos que os botoes fixos nao cobrem.
    """

    _instances: list['EmailAlertDialog'] = []

    @classmethod
    def show_alert(cls, item: dict, *, anchor: QWidget | None = None):
        eid = item.get('id')
        for pop in cls._instances:
            if pop._item.get('id') == eid and pop.isVisible():
                pop.raise_()
                pop.activateWindow()
                return
        pop = cls(item)
        pop._anchor = anchor
        cls._instances.append(pop)
        _register_popup(pop)
        _reposition_popup_stack(anchor)
        pop.show()
        pop.raise_()
        pop.activateWindow()
        print(f"[Nigel] Alerta de e-mail exibido: {item.get('subject', '')[:50]}")

    def __init__(self, item: dict):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(380)
        self._item = item
        self._anchor = None
        self._source = item.get('source', 'gmail')
        raw_id = str(item.get('id', ''))
        self._message_id = raw_id.split(':', 1)[1] if ':' in raw_id else raw_id
        self._thread_id = ''
        self._bg = None
        self._ai_worker = None
        self._compose_open = False
        self._build()
        self._auto_timer = QTimer(self)
        self._auto_timer.setSingleShot(True)
        self._auto_timer.timeout.connect(self._close)
        self._auto_timer.start(120000)
        if self._source == 'gmail':
            self._resolve_thread_id()

    def _person_context(self) -> str:
        try:
            from core.database import NigelDB
            return NigelDB.get_instance().find_person_context(self._item.get('sender', ''))
        except Exception:
            return ''

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        header = QHBoxLayout()
        brand = {'gmail': 'brand_gmail', 'outlook': 'brand_outlook'}.get(self._source, 'email')
        icon = IconWidget(brand, 16, color=C_TEXT_2)
        sender = self._item.get('sender', '') or '(remetente desconhecido)'
        title_lbl = QLabel(sender)
        title_lbl.setWordWrap(True)
        title_lbl.setStyleSheet(
            f"color: {TEXT_CSS}; font-family: {FONT}; font-size: {FS_BASE}px; "
            f"font-weight: 600; background: transparent; border: none;")
        close_btn = QPushButton('\u2715')
        close_btn.setFixedSize(22, 22)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(BTN_CLOSE)
        close_btn.clicked.connect(self._close)
        header.addWidget(icon)
        header.addWidget(title_lbl, 1)
        header.addWidget(close_btn)
        layout.addLayout(header)

        subject = self._item.get('subject', '') or '(sem assunto)'
        subj_lbl = QLabel(subject)
        subj_lbl.setWordWrap(True)
        subj_lbl.setStyleSheet(
            f"color: {TEXT_2_CSS}; font-size: {FS_SM}px; font-family: {FONT}; "
            f"background: transparent; border: none;")
        layout.addWidget(subj_lbl)

        reason = self._item.get('ai_reason', '')
        if reason:
            r = QLabel(f'Por que importa: {reason}')
            r.setWordWrap(True)
            r.setStyleSheet(
                f"color: {WARNING_CSS}; font-size: {FS_SM}px; font-family: {FONT}; "
                f"background: transparent; border: none; font-style: italic;")
            layout.addWidget(r)

        contexto = self._person_context()
        if contexto:
            c = QLabel(f'Já conhecido: {contexto}')
            c.setWordWrap(True)
            c.setStyleSheet(
                f"color: {PERSONA_CSS}; font-size: {FS_SM}px; font-family: {FONT}; "
                f"background: transparent; border: none;")
            layout.addWidget(c)

        layout.addWidget(self._sep())

        action_row = QHBoxLayout()
        action_row.setSpacing(4)
        actions = (
            ('Responder', self._toggle_compose),
            ('Arquivar', self._on_archive),
            ('Lida', self._on_mark_read),
            ('Lembrete', self._on_remind),
            ('Abrir', self._on_open),
        )
        for label, fn in actions:
            b = QPushButton(label)
            b.setStyleSheet(_BTN_ACTION)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(fn)
            action_row.addWidget(b)
        layout.addLayout(action_row)

        self._compose_box = QWidget()
        self._compose_box.hide()
        cl = QVBoxLayout(self._compose_box)
        cl.setContentsMargins(0, 4, 0, 0)
        cl.setSpacing(6)
        self._compose_text = QTextEdit()
        self._compose_text.setPlaceholderText('Escreva sua resposta\u2026')
        self._compose_text.setStyleSheet(TEXTEDIT_STYLE)
        self._compose_text.setFixedHeight(70)
        cl.addWidget(self._compose_text)
        compose_btns = QHBoxLayout()
        compose_btns.setSpacing(4)
        suggest_btn = QPushButton('Sugerir com IA')
        suggest_btn.setStyleSheet(_BTN_DYNAMIC)
        suggest_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        suggest_btn.clicked.connect(self._on_suggest_reply)
        cancel_btn = QPushButton('Cancelar')
        cancel_btn.setStyleSheet(_BTN_ACTION)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self._toggle_compose)
        send_reply_btn = QPushButton('Enviar')
        send_reply_btn.setStyleSheet(_BTN_ACTION)
        send_reply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        send_reply_btn.clicked.connect(self._on_send_reply)
        compose_btns.addWidget(suggest_btn)
        compose_btns.addStretch()
        compose_btns.addWidget(cancel_btn)
        compose_btns.addWidget(send_reply_btn)
        cl.addLayout(compose_btns)
        layout.addWidget(self._compose_box)

        layout.addWidget(self._sep())

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet(SCROLL_STYLE)
        self._scroll.setFixedHeight(90)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._msg_container = QWidget()
        self._msg_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._msg_layout = QVBoxLayout(self._msg_container)
        self._msg_layout.setContentsMargins(0, 2, 0, 2)
        self._msg_layout.setSpacing(5)
        self._msg_layout.addStretch()
        self._scroll.setWidget(self._msg_container)
        layout.addWidget(self._scroll)

        preview = self._item.get('ai_summary') or self._item.get('body_preview', '')
        if preview:
            self._add_msg(preview[:280], is_user=False)

        input_row = QHBoxLayout()
        input_row.setSpacing(6)
        self._input = QLineEdit()
        self._input.setPlaceholderText('Pe\u00e7a \u00e0 IA para lidar com este e-mail\u2026')
        self._input.setStyleSheet(_INPUT_STYLE)
        self._input.returnPressed.connect(self._on_ask_ai)
        self._input.textChanged.connect(self._reset_auto_timer)
        send_btn = QPushButton('\u2192')
        send_btn.setFixedSize(32, 32)
        send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        send_btn.setStyleSheet(BTN_ICON)
        send_btn.clicked.connect(self._on_ask_ai)
        input_row.addWidget(self._input, 1)
        input_row.addWidget(send_btn)
        layout.addLayout(input_row)
        self.adjustSize()

    def _sep(self) -> QFrame:
        s = QFrame()
        s.setFrameShape(QFrame.Shape.HLine)
        s.setStyleSheet(f'background: {BORDER_CSS}; border: none;')
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
        QTimer.singleShot(30, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()))
        self.adjustSize()
        _reposition_popup_stack(self._anchor)
        return lbl

    def _reset_auto_timer(self):
        self._auto_timer.start(120000)

    def _run_bg(self, fn, on_done, on_fail=None):
        self._reset_auto_timer()
        t = _BgCall(fn)
        self._bg = t
        t.done.connect(on_done)
        t.failed.connect(on_fail or (lambda e: self._add_msg(f'Erro: {e}', is_user=False)))
        t.finished.connect(lambda: setattr(self, '_bg', None))
        t.start()

    def _resolve_thread_id(self):
        def _do():
            from core.agent.loop import new_context
            from core.agent.registry import ToolRegistry
            from core.llm.types import ToolCall
            from core.tools.email_tools import build_tools
            reg = ToolRegistry(build_tools())
            r = reg.dispatch(ToolCall('ui', 'email_read_thread', {'message_id': self._message_id}), new_context())
            if r.ok:
                msgs = (r.data or {}).get('messages') or []
                if msgs:
                    return msgs[0].get('thread_id', '')
            return ''
        self._run_bg(_do, self._on_thread_resolved, on_fail=lambda e: None)

    def _on_thread_resolved(self, tid):
        self._thread_id = tid or ''

    def _dispatch_tool(self, toolset, name, args, ok_hint):
        def _do():
            from core.agent.loop import new_context
            from core.agent.registry import ToolRegistry
            from core.llm.types import ToolCall
            reg = ToolRegistry(toolset())
            return reg.dispatch(ToolCall('ui', name, args), new_context())

        def _done(result):
            self._add_msg(result.user_message or ('Feito.' if result.ok else result.error), is_user=False)
            if result.ok:
                self._auto_timer.stop()
                try:
                    from ui.agenda_skills import trigger_ui_update
                    trigger_ui_update()
                except Exception:
                    pass
        self._run_bg(_do, _done)

    def _on_archive(self):
        from core.tools.email_tools import build_tools
        self._dispatch_tool(build_tools, 'email_archive',
                            {'message_id': self._message_id, 'source': self._source}, 'Arquivado')

    def _on_mark_read(self):
        from core.tools.email_tools import build_tools
        self._dispatch_tool(build_tools, 'email_label',
                            {'message_id': self._message_id, 'label': 'UNREAD', 'remove': True,
                             'source': self._source},
                            'Marcado como lido')

    def _on_remind(self):
        from datetime import timedelta
        from core.tools.schedule_tools import build_tools
        subject = self._item.get('subject', '(sem assunto)')
        when = (datetime.now() + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M:%S')
        desc = self._item.get('ai_reason') or self._item.get('body_preview', '')
        self._dispatch_tool(build_tools, 'schedule_create',
                            {'title': f'Responder e-mail: {subject}'[:80], 'when': when, 'description': desc[:200]},
                            'Lembrete criado')

    def _on_open(self):
        if self._source == 'gmail' and self._message_id:
            url = f'https://mail.google.com/mail/u/0/#all/{self._message_id}'
        else:
            url = 'https://outlook.office.com/mail/inbox'
        webbrowser.open(url)

    def _toggle_compose(self):
        self._compose_open = not self._compose_open
        self._compose_box.setVisible(self._compose_open)
        if self._compose_open:
            self._compose_text.setFocus()
        self.adjustSize()
        _reposition_popup_stack(self._anchor)

    def _on_suggest_reply(self):
        def _do():
            from core.llm.client import LLMClient
            prompt = (
                "Escreva uma resposta curta e educada em portugues para este e-mail.\n\n"
                f"De: {self._item.get('sender', '')}\nAssunto: {self._item.get('subject', '')}\n"
                f"Trecho: {(self._item.get('ai_summary') or self._item.get('body_preview', ''))[:500]}\n\n"
                "Responda so com o texto do e-mail, sem saudacao tipo 'Prezado', "
                "direto ao ponto, no maximo 4 frases."
            )
            return LLMClient().text([{'role': 'user', 'content': prompt}], max_tokens=300)
        self._run_bg(_do, lambda txt: self._compose_text.setPlainText((txt or '').strip()))

    def _on_send_reply(self):
        body = self._compose_text.toPlainText().strip()
        if not body:
            return
        if self._source == 'outlook':
            # Outlook responde por message_id direto \u2014 nao precisa resolver thread.
            args = {'message_id': self._message_id, 'body': body, 'source': 'outlook'}
        else:
            if not self._thread_id:
                self._add_msg('Ainda resolvendo a conversa deste e-mail, tenta de novo em um instante\u2026', is_user=False)
                return
            args = {'thread_id': self._thread_id, 'body': body, 'source': 'gmail'}
        from core.tools.email_tools import build_tools
        self._add_msg(body, is_user=True)
        self._toggle_compose()
        self._dispatch_tool(build_tools, 'email_reply', args, 'Resposta enviada')

    def _on_ask_ai(self):
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()
        self._reset_auto_timer()
        self._add_msg(text, is_user=True)
        ai_lbl = self._add_msg('\u2026', is_user=False)

        item = self._item
        system = (
            "You are Nigel, handling ONE specific email the user is looking at right now. "
            f"From: {item.get('sender', '')}. Subject: {item.get('subject', '')}. "
            f"Preview: {(item.get('ai_summary') or item.get('body_preview', ''))[:400]}. "
            f"source={self._source}. message_id={self._message_id}"
            + (f", thread_id={self._thread_id}" if self._thread_id else '') + ". "
            "Use the email_* tools with these ids directly - do not call email_search. "
            "Always pass this source in every email_* call. "
            "Reply to the user in Brazilian Portuguese, short."
        )
        from ui.agent_worker import spawn
        from core.agent.registry import ToolRegistry
        from core.tools.email_tools import build_tools
        registry = ToolRegistry(build_tools())
        w = spawn(system, [{'role': 'user', 'content': text}], registry, max_iterations=4)
        self._ai_worker = w
        buf = {'text': ''}

        def on_delta(d):
            buf['text'] += d
            ai_lbl.setText(buf['text'] or '\u2026')

        def on_tool_end(name, msg, ok):
            self._add_msg(('\u2713 ' if ok else '\u2717 ') + (msg or name), is_user=False)

        def on_answer(txt):
            ai_lbl.setText((txt or buf['text'] or '...').strip() or '...')
            self.adjustSize()
            _reposition_popup_stack(self._anchor)
            try:
                from ui.agenda_skills import trigger_ui_update
                trigger_ui_update()
            except Exception:
                pass

        def on_fail(msg):
            ai_lbl.setText(f'Erro: {msg}')

        def on_confirm(name, label, icon):
            self._add_confirm_buttons(w, label)

        w.text_delta.connect(on_delta)
        w.tool_finished.connect(on_tool_end)
        w.confirm_requested.connect(on_confirm)
        w.answer_ready.connect(on_answer)
        w.failed.connect(on_fail)
        w.start()

    def _add_confirm_buttons(self, worker, label: str):
        # Mesma trava de `requires_confirmation` do chat principal: a caixa de
        # texto livre deste popup também aciona o loop do agente, então pode
        # pedir para enviar/apagar sem que o usuário tenha escrito isso —
        # aqui é onde ele confirma de verdade.
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 2, 0, 2)
        h.setSpacing(6)
        h.addStretch()
        btn_no = QPushButton('Cancelar')
        btn_no.setStyleSheet(_BTN_ACTION)
        btn_no.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_yes = QPushButton('Confirmar')
        btn_yes.setStyleSheet(_BTN_DYNAMIC)
        btn_yes.setCursor(Qt.CursorShape.PointingHandCursor)
        h.addWidget(btn_no)
        h.addWidget(btn_yes)
        self._msg_layout.insertWidget(self._msg_layout.count() - 1, row)
        self.adjustSize()
        _reposition_popup_stack(self._anchor)

        def _cleanup():
            row.setParent(None)
            row.deleteLater()

        def _no():
            _cleanup()
            self._add_msg(f'Cancelado: {label}', is_user=False)

        def _yes():
            _cleanup()
            call = worker.result.pending_confirmation if worker and worker.result else None
            registry = getattr(worker, 'registry', None) if worker else None
            if not (call and registry):
                self._add_msg('Não consegui recuperar a ação para confirmar.', is_user=False)
                return
            self._add_msg(f'{label}…', is_user=False)

            def _do():
                from core.agent.loop import new_context
                return registry.dispatch(call, new_context())

            def _done(result):
                self._add_msg(result.user_message or ('Feito.' if result.ok else result.error),
                              is_user=False)
                self.adjustSize()
                _reposition_popup_stack(self._anchor)

            self._run_bg(_do, _done)

        btn_no.clicked.connect(_no)
        btn_yes.clicked.connect(_yes)

    def _close(self):
        if self._bg is not None and self._bg.isRunning():
            self._bg.quit()
        if self._ai_worker is not None and self._ai_worker.isRunning():
            self._ai_worker.stop()
        if self in EmailAlertDialog._instances:
            EmailAlertDialog._instances.remove(self)
        _unregister_popup(self)
        self.close()
        _reposition_popup_stack(self._anchor)

    def paintEvent(self, event):
        p = QPainter(self)
        paint_panel(self, p, radius=14, bg=C_BG, border=C_BORDER)


class BriefingAlertDialog(QWidget):
    """Popup do resultado de uma tarefa autônoma do Nigel (briefing matinal,
    verificação de e-mail em background, prompt agendado).

    Sem isso o resumo só existia em `schedules.last_result`, no banco — o
    `task_executed` do `ScheduleCheckerWorker` nunca tinha um ouvinte na UI.
    Um campo de texto livre delega ao orquestrador completo (agenda + e-mail +
    memória), reaproveitando o mesmo mecanismo de confirmação dos outros popups.
    """

    _instances: list['BriefingAlertDialog'] = []
    _ICONS = {'daily_briefing': 'clock', 'check_emails': 'email', 'agent_prompt': 'ai',
             'meeting_prep': 'brand_gcal'}
    _TITLES = {'daily_briefing': 'Briefing matinal', 'check_emails': 'Verificação de e-mail',
              'agent_prompt': 'Tarefa em background', 'meeting_prep': 'Preparação de reunião'}

    @classmethod
    def show_alert(cls, result: dict, *, anchor: QWidget | None = None):
        pop = cls(result)
        pop._anchor = anchor
        cls._instances.append(pop)
        _register_popup(pop)
        _reposition_popup_stack(anchor)
        pop.show()
        pop.raise_()
        pop.activateWindow()
        print(f"[Nigel] Tarefa concluída: {result.get('type','')} — {(result.get('summary','') or '')[:50]}")

    def __init__(self, result: dict):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(380)
        self._result = result
        self._ttype = result.get('type', '')
        self._anchor = None
        self._ai_worker = None
        self._bg = None
        self._build()
        self._auto_timer = QTimer(self)
        self._auto_timer.setSingleShot(True)
        self._auto_timer.timeout.connect(self._close)
        self._auto_timer.start(90000)

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        header = QHBoxLayout()
        icon = IconWidget(self._ICONS.get(self._ttype, 'ai'), 16, color=C_TEXT_2)
        title_txt = self._TITLES.get(self._ttype, 'Nigel')
        ev_title = ((self._result.get('event') or {}).get('summary') or '').strip()
        if ev_title:
            title_txt = f'{title_txt}: {ev_title}'
        title_lbl = QLabel(title_txt)
        title_lbl.setStyleSheet(
            f"color: {TEXT_CSS}; font-family: {FONT}; font-size: {FS_BASE}px; "
            f"font-weight: 600; background: transparent; border: none;")
        close_btn = QPushButton('✕')
        close_btn.setFixedSize(22, 22)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(BTN_CLOSE)
        close_btn.clicked.connect(self._close)
        header.addWidget(icon)
        header.addWidget(title_lbl, 1)
        header.addWidget(close_btn)
        layout.addLayout(header)

        layout.addWidget(self._sep())

        self._msg_container = QWidget()
        self._msg_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._msg_layout = QVBoxLayout(self._msg_container)
        self._msg_layout.setContentsMargins(0, 2, 0, 2)
        self._msg_layout.setSpacing(5)
        self._msg_layout.addStretch()
        layout.addWidget(self._msg_container)
        self._add_msg((self._result.get('summary') or '').strip() or 'Sem novidades.', is_user=False)

        input_row = QHBoxLayout()
        input_row.setSpacing(6)
        self._input = QLineEdit()
        self._input.setPlaceholderText('Pergunte mais ao Nigel…')
        self._input.setStyleSheet(INPUT_STYLE)
        self._input.returnPressed.connect(self._on_ask_ai)
        send_btn = QPushButton('→')
        send_btn.setFixedSize(32, 32)
        send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        send_btn.setStyleSheet(BTN_ICON)
        send_btn.clicked.connect(self._on_ask_ai)
        input_row.addWidget(self._input, 1)
        input_row.addWidget(send_btn)
        layout.addLayout(input_row)
        self.adjustSize()

    def _sep(self) -> QFrame:
        s = QFrame()
        s.setFrameShape(QFrame.Shape.HLine)
        s.setStyleSheet(f'background: {BORDER_CSS}; border: none;')
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
        self.adjustSize()
        _reposition_popup_stack(self._anchor)
        return lbl

    def _on_ask_ai(self):
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()
        self._auto_timer.start(90000)
        self._add_msg(text, is_user=True)
        ai_lbl = self._add_msg('…', is_user=False)

        from ui.agent_worker import spawn
        from core.tools import build_orchestrator_registry
        from core.agent.prompts import orchestrator_prompt
        registry = build_orchestrator_registry()
        history = [{'role': 'assistant', 'content': self._result.get('summary', '')},
                  {'role': 'user', 'content': text}]
        w = spawn(orchestrator_prompt(), history, registry, max_iterations=6)
        self._ai_worker = w
        buf = {'text': ''}

        def on_delta(d):
            buf['text'] += d
            ai_lbl.setText(buf['text'] or '…')

        def on_tool_end(name, msg, ok):
            self._add_msg(('✓ ' if ok else '✗ ') + (msg or name), is_user=False)

        def on_confirm(name, label, icon):
            self._add_confirm_buttons(w, label)

        def on_answer(txt):
            ai_lbl.setText((txt or buf['text'] or '...').strip() or '...')
            self.adjustSize()
            _reposition_popup_stack(self._anchor)
            try:
                trigger_ui_update()
            except Exception:
                pass

        def on_fail(msg):
            ai_lbl.setText(f'Erro: {msg}')

        w.text_delta.connect(on_delta)
        w.tool_finished.connect(on_tool_end)
        w.confirm_requested.connect(on_confirm)
        w.answer_ready.connect(on_answer)
        w.failed.connect(on_fail)
        w.start()

    def _add_confirm_buttons(self, worker, label: str):
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 2, 0, 2)
        h.setSpacing(6)
        h.addStretch()
        btn_no = QPushButton('Cancelar')
        btn_no.setStyleSheet(_BTN_ACTION)
        btn_no.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_yes = QPushButton('Confirmar')
        btn_yes.setStyleSheet(_BTN_DYNAMIC)
        btn_yes.setCursor(Qt.CursorShape.PointingHandCursor)
        h.addWidget(btn_no)
        h.addWidget(btn_yes)
        self._msg_layout.insertWidget(self._msg_layout.count() - 1, row)
        self.adjustSize()
        _reposition_popup_stack(self._anchor)

        def _cleanup():
            row.setParent(None)
            row.deleteLater()

        def _no():
            _cleanup()
            self._add_msg(f'Cancelado: {label}', is_user=False)

        def _yes():
            _cleanup()
            call = worker.result.pending_confirmation if worker and worker.result else None
            registry = getattr(worker, 'registry', None) if worker else None
            if not (call and registry):
                self._add_msg('Não consegui recuperar a ação para confirmar.', is_user=False)
                return
            self._add_msg(f'{label}…', is_user=False)

            def _do():
                from core.agent.loop import new_context
                return registry.dispatch(call, new_context())

            def _done(result):
                self._add_msg(result.user_message or ('Feito.' if result.ok else result.error),
                              is_user=False)
                self.adjustSize()
                _reposition_popup_stack(self._anchor)

            bg = _BgCall(_do)
            self._bg = bg
            bg.done.connect(_done)
            bg.start()

        btn_no.clicked.connect(_no)
        btn_yes.clicked.connect(_yes)

    def _close(self):
        if self._ai_worker is not None and self._ai_worker.isRunning():
            self._ai_worker.stop()
        if self in BriefingAlertDialog._instances:
            BriefingAlertDialog._instances.remove(self)
        _unregister_popup(self)
        self.close()
        _reposition_popup_stack(self._anchor)

    def paintEvent(self, event):
        p = QPainter(self)
        paint_panel(self, p, radius=14, bg=C_BG, border=C_BORDER)


def _fmt_event_time(ev: dict) -> str:
    try:
        start = datetime.fromisoformat((ev.get('start') or '').replace('Z', '+00:00'))
        end = datetime.fromisoformat((ev.get('end') or '').replace('Z', '+00:00'))
        same_day = start.date() == end.date()
        if same_day:
            return f"{start.strftime('%d/%m %H:%M')}–{end.strftime('%H:%M')}"
        return f"{start.strftime('%d/%m %H:%M')} – {end.strftime('%d/%m %H:%M')}"
    except (ValueError, TypeError):
        return ev.get('start', '') or ''


class ConflictAlertDialog(QWidget):
    """Popup de conflito de agenda: dois compromissos reais que se sobrepoem.

    Proativo, como o popup de e-mail: a `AgendaConflictWorker` acha o par
    sozinha e avisa antes do usuario perguntar. Um campo de texto livre delega
    ao `agenda_agent` (via `calendar_tools`) para resolver — "remarca a
    reuniao com o Joao para as 15h" — reaproveitando o mesmo mecanismo de
    confirmacao do popup de e-mail para qualquer acao que vier a exigir.
    """

    _instances: list['ConflictAlertDialog'] = []

    @classmethod
    def show_alert(cls, event_a: dict, event_b: dict, *, anchor: QWidget | None = None):
        key = frozenset({event_a.get('event_id'), event_b.get('event_id')})
        for pop in cls._instances:
            if pop._key == key and pop.isVisible():
                pop.raise_()
                pop.activateWindow()
                return
        pop = cls(event_a, event_b)
        pop._anchor = anchor
        cls._instances.append(pop)
        _register_popup(pop)
        _reposition_popup_stack(anchor)
        pop.show()
        pop.raise_()
        pop.activateWindow()
        print(f"[Nigel] Conflito de agenda: {event_a.get('summary','')[:30]} x {event_b.get('summary','')[:30]}")

    def __init__(self, event_a: dict, event_b: dict):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(380)
        self._event_a = event_a
        self._event_b = event_b
        self._key = frozenset({event_a.get('event_id'), event_b.get('event_id')})
        self._anchor = None
        self._ai_worker = None
        self._bg = None
        self._build()
        self._auto_timer = QTimer(self)
        self._auto_timer.setSingleShot(True)
        self._auto_timer.timeout.connect(self._close)
        self._auto_timer.start(120000)

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        header = QHBoxLayout()
        icon = IconWidget('brand_gcal', 16, color=C_TEXT_2)
        title_lbl = QLabel('Conflito na agenda')
        title_lbl.setStyleSheet(
            f"color: {TEXT_CSS}; font-family: {FONT}; font-size: {FS_BASE}px; "
            f"font-weight: 600; background: transparent; border: none;")
        close_btn = QPushButton('✕')
        close_btn.setFixedSize(22, 22)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(BTN_CLOSE)
        close_btn.clicked.connect(self._close)
        header.addWidget(icon)
        header.addWidget(title_lbl, 1)
        header.addWidget(close_btn)
        layout.addLayout(header)

        msg = QLabel('Dois compromissos no mesmo horario:')
        msg.setStyleSheet(
            f"color: {WARNING_CSS}; font-size: {FS_SM}px; font-family: {FONT}; "
            f"background: transparent; border: none; font-style: italic;")
        layout.addWidget(msg)

        for ev in (self._event_a, self._event_b):
            row = QLabel(f"• {ev.get('summary', '(sem titulo)')}  —  {_fmt_event_time(ev)}")
            row.setWordWrap(True)
            row.setStyleSheet(
                f"color: {TEXT_2_CSS}; font-size: {FS_SM}px; font-family: {FONT}; "
                f"background: transparent; border: none;")
            layout.addWidget(row)

        layout.addWidget(self._sep())

        action_row = QHBoxLayout()
        action_row.setSpacing(4)
        for label, fn in (('Abrir agenda', self._on_open), ('Ignorar', self._close)):
            b = QPushButton(label)
            b.setStyleSheet(_BTN_ACTION)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(fn)
            action_row.addWidget(b)
        layout.addLayout(action_row)

        self._msg_container = QWidget()
        self._msg_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._msg_layout = QVBoxLayout(self._msg_container)
        self._msg_layout.setContentsMargins(0, 2, 0, 2)
        self._msg_layout.setSpacing(5)
        self._msg_layout.addStretch()
        layout.addWidget(self._msg_container)

        input_row = QHBoxLayout()
        input_row.setSpacing(6)
        self._input = QLineEdit()
        self._input.setPlaceholderText('Peca pro Nigel resolver: "remarca a segunda reuniao"…')
        self._input.setStyleSheet(INPUT_STYLE)
        self._input.returnPressed.connect(self._on_ask_ai)
        send_btn = QPushButton('→')
        send_btn.setFixedSize(32, 32)
        send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        send_btn.setStyleSheet(BTN_ICON)
        send_btn.clicked.connect(self._on_ask_ai)
        input_row.addWidget(self._input, 1)
        input_row.addWidget(send_btn)
        layout.addLayout(input_row)
        self.adjustSize()

    def _sep(self) -> QFrame:
        s = QFrame()
        s.setFrameShape(QFrame.Shape.HLine)
        s.setStyleSheet(f'background: {BORDER_CSS}; border: none;')
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
        self.adjustSize()
        _reposition_popup_stack(self._anchor)
        return lbl

    def _on_open(self):
        webbrowser.open('https://calendar.google.com/calendar/r')

    def _on_ask_ai(self):
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()
        self._auto_timer.start(120000)
        self._add_msg(text, is_user=True)
        ai_lbl = self._add_msg('…', is_user=False)

        a, b = self._event_a, self._event_b
        system = (
            "You are Nigel, resolving a scheduling conflict the user is looking at right now. "
            f"Event A: '{a.get('summary','')}' ({a.get('start','')} to {a.get('end','')}, "
            f"event_id={a.get('event_id','')}). "
            f"Event B: '{b.get('summary','')}' ({b.get('start','')} to {b.get('end','')}, "
            f"event_id={b.get('event_id','')}). "
            "Use the calendar_* tools with these event_ids directly - do not call calendar_find_events "
            "unless the user names a THIRD event. Reply to the user in Brazilian Portuguese, short."
        )
        from ui.agent_worker import spawn
        from core.agent.registry import ToolRegistry
        from core.tools.calendar_tools import build_tools
        registry = ToolRegistry(build_tools())
        w = spawn(system, [{'role': 'user', 'content': text}], registry, max_iterations=4)
        self._ai_worker = w
        buf = {'text': ''}

        def on_delta(d):
            buf['text'] += d
            ai_lbl.setText(buf['text'] or '…')

        def on_tool_end(name, msg, ok):
            self._add_msg(('✓ ' if ok else '✗ ') + (msg or name), is_user=False)

        def on_confirm(name, label, icon):
            self._add_confirm_buttons(w, label)

        def on_answer(txt):
            ai_lbl.setText((txt or buf['text'] or '...').strip() or '...')
            self.adjustSize()
            _reposition_popup_stack(self._anchor)
            try:
                trigger_ui_update()
            except Exception:
                pass

        def on_fail(msg):
            ai_lbl.setText(f'Erro: {msg}')

        w.text_delta.connect(on_delta)
        w.tool_finished.connect(on_tool_end)
        w.confirm_requested.connect(on_confirm)
        w.answer_ready.connect(on_answer)
        w.failed.connect(on_fail)
        w.start()

    def _add_confirm_buttons(self, worker, label: str):
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 2, 0, 2)
        h.setSpacing(6)
        h.addStretch()
        btn_no = QPushButton('Cancelar')
        btn_no.setStyleSheet(_BTN_ACTION)
        btn_no.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_yes = QPushButton('Confirmar')
        btn_yes.setStyleSheet(_BTN_DYNAMIC)
        btn_yes.setCursor(Qt.CursorShape.PointingHandCursor)
        h.addWidget(btn_no)
        h.addWidget(btn_yes)
        self._msg_layout.insertWidget(self._msg_layout.count() - 1, row)
        self.adjustSize()
        _reposition_popup_stack(self._anchor)

        def _cleanup():
            row.setParent(None)
            row.deleteLater()

        def _no():
            _cleanup()
            self._add_msg(f'Cancelado: {label}', is_user=False)

        def _yes():
            _cleanup()
            call = worker.result.pending_confirmation if worker and worker.result else None
            registry = getattr(worker, 'registry', None) if worker else None
            if not (call and registry):
                self._add_msg('Nao consegui recuperar a acao para confirmar.', is_user=False)
                return
            self._add_msg(f'{label}…', is_user=False)

            def _do():
                from core.agent.loop import new_context
                return registry.dispatch(call, new_context())

            def _done(result):
                self._add_msg(result.user_message or ('Feito.' if result.ok else result.error),
                              is_user=False)
                self.adjustSize()
                _reposition_popup_stack(self._anchor)

            bg = _BgCall(_do)
            self._bg = bg
            bg.done.connect(_done)
            bg.start()

        btn_no.clicked.connect(_no)
        btn_yes.clicked.connect(_yes)

    def _close(self):
        if self._ai_worker is not None and self._ai_worker.isRunning():
            self._ai_worker.stop()
        if self in ConflictAlertDialog._instances:
            ConflictAlertDialog._instances.remove(self)
        _unregister_popup(self)
        self.close()
        _reposition_popup_stack(self._anchor)

    def paintEvent(self, event):
        p = QPainter(self)
        paint_panel(self, p, radius=14, bg=C_BG, border=C_BORDER)

