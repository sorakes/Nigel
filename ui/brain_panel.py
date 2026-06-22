"""
ui/brain_panel.py — Painel de Inteligência do SEQ.

Duas abas:
  Agenda — Lembretes e follow-ups (manual + IA)
  Grafo  — Visualização relacional estilo Obsidian
"""
from datetime import datetime, timedelta
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QScrollArea, QFrame, QLineEdit, QDialog,
                             QDateTimeEdit, QTextEdit, QApplication)
from PyQt6.QtCore import Qt, QDateTime, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush, QFont, QPixmap
from ui.theme import (paint_panel, C_PANEL, C_GOLD, C_TEXT, C_TEXT_MID, TEXT_CSS,
                      TEXT_MID_CSS, GOLD_BRIGHT_CSS, FONT, BTN_PRIMARY,
                      BTN_CLOSE, LABEL_SECTION, LABEL_SMALL, SCROLL_STYLE)
from ui.memory_graph import GraphTab
from ui.icons import IconWidget, IconButton, source_icon_name
_TAB_ON = f"""
    QPushButton {{
        background: rgba(201,168,76,40);
        border: none; border-radius: 8px;
        color: {GOLD_BRIGHT_CSS};
        font-family: {FONT}; font-size: 12px; font-weight: bold;
    }}
    QPushButton QLabel {{
        color: {GOLD_BRIGHT_CSS};
        font-weight: bold;
    }}
"""
_TAB_OFF = f"""
    QPushButton {{
        background: transparent;
        border: none; border-radius: 8px;
        color: {TEXT_MID_CSS};
        font-family: {FONT}; font-size: 12px;
    }}
    QPushButton:hover {{ background: rgba(201,168,76,15); color: {TEXT_CSS}; }}
    QPushButton QLabel {{ color: {TEXT_MID_CSS}; }}
    QPushButton:hover QLabel {{ color: {TEXT_CSS}; }}
"""
_CARD_CSS = """
    QFrame {
        background: rgba(201,168,76, 12);
        border: 1px solid rgba(201,168,76, 45);
        border-radius: 10px;
    }
    QLabel { border: none; background: transparent; }
"""

def _tab_button(icon: str, label: str) -> QPushButton:
    btn = QPushButton()
    btn.setMinimumSize(95, 34)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    row = QHBoxLayout(btn)
    row.setContentsMargins(10, 0, 14, 0)
    row.setSpacing(6)
    row.addWidget(IconWidget(icon, 14))
    lbl = QLabel(label)
    lbl.setStyleSheet(f"background: transparent; border: none; font-family: {FONT}; font-size: 12px;")
    row.addWidget(lbl)
    return btn

class NewScheduleDialog(QDialog):

    def __init__(self, parent=None, prefill: dict | None = None):
        super().__init__(parent, Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(380, 300)
        self.result_data = None
        self._prefill = prefill or {}
        self._build()
        self._apply_prefill()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        title_lbl = QLabel('Novo Lembrete')
        title_lbl.setStyleSheet(f"color: {GOLD_BRIGHT_CSS}; font-size: 15px; font-weight: bold; font-family: {FONT};")
        layout.addWidget(title_lbl)
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText('Título do lembrete…')
        self.title_input.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(201,168,76,10); border: 1px solid rgba(201,168,76,50);
                border-radius: 8px; color: {TEXT_CSS}; font-family: {FONT}; font-size: 13px;
                padding: 8px 12px;
            }}
        """)
        layout.addWidget(self.title_input)
        self.desc_input = QTextEdit()
        self.desc_input.setPlaceholderText('Descrição (opcional)…')
        self.desc_input.setFixedHeight(70)
        self.desc_input.setStyleSheet(f"""
            QTextEdit {{
                background: rgba(201,168,76,10); border: 1px solid rgba(201,168,76,50);
                border-radius: 8px; color: {TEXT_CSS}; font-family: {FONT}; font-size: 12px;
                padding: 8px 12px;
            }}
        """)
        layout.addWidget(self.desc_input)
        dt_lbl = QLabel('Lembrar em:')
        dt_lbl.setStyleSheet(LABEL_SMALL)
        layout.addWidget(dt_lbl)
        self.dt_picker = QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600))
        self.dt_picker.setCalendarPopup(True)
        self.dt_picker.setStyleSheet(f"""
            QDateTimeEdit {{
                background: rgba(201,168,76,10); border: 1px solid rgba(201,168,76,50);
                border-radius: 8px; color: {TEXT_CSS}; font-family: {FONT};
                padding: 6px 12px;
            }}
        """)
        layout.addWidget(self.dt_picker)
        btns = QHBoxLayout()
        cancel_btn = QPushButton('Cancelar')
        cancel_btn.setStyleSheet(BTN_CLOSE)
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton('Salvar')
        save_btn.setStyleSheet(BTN_PRIMARY)
        save_btn.clicked.connect(self._save)
        btns.addStretch()
        btns.addWidget(cancel_btn)
        btns.addWidget(save_btn)
        layout.addLayout(btns)

    def _apply_prefill(self):
        if self._prefill.get('title'):
            self.title_input.setText(self._prefill['title'])
        if self._prefill.get('description'):
            self.desc_input.setPlainText(self._prefill['description'])
        due = self._prefill.get('due_at')
        if due:
            try:
                if isinstance(due, str):
                    due = datetime.fromisoformat(due)
                self.dt_picker.setDateTime(QDateTime(due))
                return
            except Exception:
                return

    def _save(self):
        self.result_data = {'title': self.title_input.text().strip(), 'description': self.desc_input.toPlainText().strip(), 'due_at': self.dt_picker.dateTime().toPyDateTime()}
        if self.result_data['title']:
            self.accept()
            return
        return

    def paintEvent(self, event):
        p = QPainter(self)
        paint_panel(self, p, radius=16, bg=C_PANEL, border=C_GOLD)

class AgendaTab(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)
        header = QHBoxLayout()
        header.addWidget(IconWidget('agenda', 16))
        lbl = QLabel('LEMBRETES & FOLLOW-UPS')
        lbl.setStyleSheet(LABEL_SECTION)
        add_btn = QPushButton('+ Novo')
        add_btn.setStyleSheet(BTN_PRIMARY)
        add_btn.setFixedHeight(32)
        add_btn.setMinimumWidth(80)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._new_schedule)
        header.addWidget(lbl)
        header.addStretch()
        header.addWidget(add_btn)
        layout.addLayout(header)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet(SCROLL_STYLE)
        self.container = QWidget()
        self.container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.list_layout = QVBoxLayout(self.container)
        self.list_layout.setContentsMargins(0, 0, 4, 0)
        self.list_layout.setSpacing(6)
        self.list_layout.addStretch()
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll, 1)
        self.refresh()

    def refresh(self):
        from core.scheduler import ScheduleManager
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        schedules = ScheduleManager.get_instance().get_all()
        if not schedules:
            empty = QLabel("Nenhum lembrete pendente.\nClique em '+ Novo' para criar um.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(f"color: {TEXT_MID_CSS}; font-size: 12px; font-family: {FONT};")
            self.list_layout.insertWidget(0, empty)
            return
        for s in schedules:
            self.list_layout.insertWidget(self.list_layout.count() - 1, self._make_card(s))

    def _make_card(self, s: dict) -> QFrame:
        card = QFrame()
        card.setStyleSheet(_CARD_CSS)
        lay = QHBoxLayout(card)
        lay.setContentsMargins(14, 10, 10, 10)
        lay.setSpacing(10)
        icon = IconWidget(source_icon_name(s.get('source', 'manual')), 18)
        icon.setFixedWidth(22)
        info = QVBoxLayout()
        info.setSpacing(2)
        t = QLabel(s['title'])
        t.setStyleSheet(f"color: {TEXT_CSS}; font-family: {FONT}; font-weight: bold; font-size: 13px;")
        t.setWordWrap(True)
        try:
            due = datetime.fromisoformat(s['due_at'])
            now = datetime.now()
            if due < now:
                time_str = f"Vencido em {due.strftime('%d/%m %H:%M')}"
                time_css = f"color: {GOLD_BRIGHT_CSS};"
            else:
                diff = due - now
                mins = int(diff.total_seconds() / 60)
                if mins < 60:
                    time_str = f"Em {mins}m — {due.strftime('%d/%m %H:%M')}"
                else:
                    time_str = f"Em {mins // 60}h {mins % 60}m — {due.strftime('%d/%m %H:%M')}"
                time_css = f"color: {TEXT_MID_CSS};"
        except Exception:
            time_str = s.get('due_at', '')
            time_css = f"color: {TEXT_MID_CSS};"
        sub = QLabel(time_str)
        sub.setStyleSheet(f"font-size: 11px; font-family: {FONT}; {time_css}")
        info.addWidget(t)
        info.addWidget(sub)
        done_btn = IconButton('check', 28, 'Marcar como concluído')
        sid = s['id']
        done_btn.clicked.connect(lambda i=sid: self._mark_done(i))
        del_btn = IconButton('close', 28, 'Deletar')
        del_btn.clicked.connect(lambda i=sid: self._delete(i))
        lay.addWidget(icon)
        lay.addLayout(info, 1)
        lay.addWidget(done_btn)
        lay.addWidget(del_btn)
        return card

    def _new_schedule(self):
        dlg = NewScheduleDialog(self)
        sc = QApplication.primaryScreen().availableGeometry()
        dlg.move(sc.width() // 2 - dlg.width() // 2, sc.height() // 2 - dlg.height() // 2)
        if dlg.exec() and dlg.result_data:
            from ui.agenda_skills import commit_schedule
            data = dlg.result_data
            commit_schedule(title=data['title'], description=data.get('description', ''), due_at=data['due_at'], source='manual')
            self.refresh()
            return
        return

    def _mark_done(self, schedule_id: int):
        from core.scheduler import ScheduleManager
        ScheduleManager.get_instance().mark_done(schedule_id)
        self.refresh()

    def _delete(self, schedule_id: int):
        from core.scheduler import ScheduleManager
        ScheduleManager.get_instance().delete(schedule_id)
        self.refresh()

class MemoryTab(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)
        header = QHBoxLayout()
        header.addWidget(IconWidget('memory', 16))
        lbl = QLabel('MEMÓRIA SALVA')
        lbl.setStyleSheet(LABEL_SECTION)
        refresh_btn = IconButton('refresh', 28, 'Atualizar')
        refresh_btn.clicked.connect(self.refresh)
        header.addWidget(lbl)
        header.addStretch()
        header.addWidget(refresh_btn)
        layout.addLayout(header)
        note_row = QHBoxLayout()
        self.note_input = QLineEdit()
        self.note_input.setPlaceholderText('Salvar nota manualmente…')
        self.note_input.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(201,168,76,10); border: 1px solid rgba(201,168,76,50);
                border-radius: 8px; color: {TEXT_CSS}; font-family: {FONT}; font-size: 12px;
                padding: 6px 12px;
            }}
        """)
        save_note_btn = QPushButton('Salvar')
        save_note_btn.setStyleSheet(BTN_PRIMARY)
        save_note_btn.setFixedHeight(34)
        save_note_btn.clicked.connect(self._save_note)
        note_row.addWidget(self.note_input, 1)
        note_row.addWidget(save_note_btn)
        layout.addLayout(note_row)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet(SCROLL_STYLE)
        self.container = QWidget()
        self.container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.list_layout = QVBoxLayout(self.container)
        self.list_layout.setContentsMargins(0, 0, 4, 0)
        self.list_layout.setSpacing(6)
        self.list_layout.addStretch()
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll, 1)
        self.refresh()

    def refresh(self):
        from core.database import SeqDB
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        items = SeqDB.get_instance().get_saved_items(include_persona=False)
        if not items:
            empty = QLabel('Nenhum item na memória ainda.\nItens importantes serão salvos automaticamente pela IA.')
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setWordWrap(True)
            empty.setStyleSheet(f"color: {TEXT_MID_CSS}; font-size: 12px; font-family: {FONT};")
            self.list_layout.insertWidget(0, empty)
            return
        for item in items:
            self.list_layout.insertWidget(self.list_layout.count() - 1, self._make_card(item))

    def _make_card(self, item: dict) -> QFrame:
        card = QFrame()
        card.setStyleSheet(_CARD_CSS)
        lay = QHBoxLayout(card)
        lay.setContentsMargins(14, 10, 10, 10)
        lay.setSpacing(10)
        icon = IconWidget(source_icon_name(item.get('source', 'manual')), 18)
        icon.setFixedWidth(22)
        info = QVBoxLayout()
        info.setSpacing(2)
        subj = item.get('subject') or item.get('ai_summary') or 'Nota'
        t = QLabel(subj)
        t.setStyleSheet(f"color: {TEXT_CSS}; font-weight: bold; font-size: 13px; font-family: {FONT};")
        t.setWordWrap(True)
        meta_parts = []
        if item.get('sender'):
            meta_parts.append(f"De: {item['sender']}")
        lay.addWidget(icon)
        title = item.get('subject') or item.get('ai_summary') or 'Nota'
        preview = item.get('body_preview', '')
        lbl = QLabel(f"<b>{title}</b><br/><span style='color:{TEXT_MID_CSS}'>{preview}</span>")
        lbl.setStyleSheet(f"color: {TEXT_CSS}; font-size: 13px; font-family: {FONT};")
        lbl.setWordWrap(True)
        lay.addWidget(lbl, 1)
        del_btn = IconButton('close', 28, 'Deletar memória')
        item_id = item['id']
        del_btn.clicked.connect(lambda i=item_id: self._delete_item(i))
        lay.addWidget(del_btn)
        return card

    def _delete_item(self, item_id: str):
        from core.database import SeqDB
        SeqDB.get_instance().delete_saved_item(item_id)
        self.refresh()

    def _save_note(self):
        text = self.note_input.text().strip()
        if not text:
            return
        from core.database import SeqDB
        import uuid
        SeqDB.get_instance().save_important({
            'id': str(uuid.uuid4()),
            'source': 'manual',
            'subject': text,
            'sender': '',
            'body_preview': '',
            'ai_summary': text,
            'ai_reason': 'Salvo manualmente pelo usuário',
        }, saved_by='user')
        self.note_input.clear()
        self.refresh()

class BrainPanel(QWidget):

    def __init__(self, parent=None):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(520, 560)
        self._drag_pos = None
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        title_row = QHBoxLayout()
        title_row.setContentsMargins(20, 14, 16, 0)
        import os
        _duck_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets', 'nigel.png')
        title_icon = QLabel()
        if os.path.exists(_duck_path):
            _pix = QPixmap(_duck_path).scaled(20, 20, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            title_icon.setPixmap(_pix)
        title_icon.setFixedSize(20, 20)
        title = QLabel('Nigel Intelligence')
        title.setStyleSheet(f"color: {GOLD_BRIGHT_CSS}; font-family: {FONT}; font-size: 14px; font-weight: bold;")
        close_btn = IconButton('close', 26, 'Fechar')
        close_btn.clicked.connect(self.hide)
        title_row.addWidget(title_icon)
        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(close_btn)
        layout.addLayout(title_row)
        tabs_row = QHBoxLayout()
        tabs_row.setContentsMargins(16, 10, 16, 0)
        tabs_row.setSpacing(4)
        self.tab_btns = []
        for (i, (icon, lbl)) in enumerate([('agenda', 'Agenda'), ('graph', 'Grafo')]):
            btn = _tab_button(icon, lbl)
            btn.clicked.connect(lambda checked=False, idx=i: self._switch_tab(idx))
            self.tab_btns.append(btn)
            tabs_row.addWidget(btn)
        tabs_row.addStretch()
        layout.addLayout(tabs_row)
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet('background: rgba(201,168,76,40); margin: 0 16px;')
        layout.addSpacing(8)
        layout.addWidget(sep)
        self.agenda_tab = AgendaTab()
        self.graph_tab = GraphTab()
        content = QWidget()
        content.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(16, 8, 16, 16)
        self.content_layout.addWidget(self.agenda_tab)
        self.content_layout.addWidget(self.graph_tab)
        layout.addWidget(content, 1)
        self._switch_tab(0)

    def _switch_tab(self, idx: int):
        self.agenda_tab.setVisible(idx == 0)
        self.graph_tab.setVisible(idx == 1)
        for (i, btn) in enumerate(self.tab_btns):
            btn.setStyleSheet(_TAB_ON if i == idx else _TAB_OFF)
        if idx == 0:
            self.agenda_tab.refresh()
            return
        if idx == 1:
            self.graph_tab.refresh()
            return

    def paintEvent(self, event):
        p = QPainter(self)
        paint_panel(self, p, radius=20, bg=C_PANEL, border=C_GOLD)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            return
        return

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            return
        return

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def show_near_bar(self, bar_widget: QWidget):
        bar_geo = bar_widget.geometry()
        bar_global = bar_widget.mapToGlobal(bar_geo.topLeft()) if hasattr(bar_widget, 'pos') else bar_geo.topLeft()
        bar_pos = bar_widget.pos()
        sc = QApplication.primaryScreen().availableGeometry()
        x = max(sc.left(), min(bar_pos.x(), sc.right() - self.width()))
        y = bar_pos.y() - self.height() - 12
        if y < sc.top():
            y = bar_pos.y() + bar_widget.height() + 12
        self.move(x, y)
        self.show()
        self.raise_()
