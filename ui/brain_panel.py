"""
ui/brain_panel.py — Painel de Inteligência e Automação do Nigel.

Três abas centrais:
  1. Schedules       — Motor de tarefas e automações autônomas do Nigel (estilo Manus)
  2. Google Calendar — Agenda Oficial Espelhada (Grid Mensal, Lista, Dia, sincronizado ao vivo via Composio)
  3. Grafo           — Visualização relacional da memória e inteligência
"""

import calendar
import threading
from datetime import datetime, timedelta, date
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QLineEdit, QDialog, QGridLayout,
    QDateTimeEdit, QTextEdit, QComboBox, QApplication
)
from PyQt6.QtCore import Qt, QDateTime, QTimer, QSize, pyqtSignal
from PyQt6.QtGui import QPainter, QPixmap

from ui.theme import (
    paint_panel, css, C_BG, C_BORDER, C_TEXT, C_TEXT_2,
    
    TEXT_CSS, TEXT_2_CSS, TEXT_MUTE_CSS, SURFACE_CSS, RAISED_CSS, OVERLAY_CSS,
    BORDER_CSS, BORDER_HI_CSS, GOLD_SOFT_CSS, BG_SOLID_CSS,
    FS_XS, FS_LG, FS_BASE, FONT, FS_SM, FS_MD, R_SM, R_MD,
    BTN_PRIMARY, BTN_CLOSE, LABEL_SECTION, LABEL_SMALL,
    SCROLL_STYLE,
    CALENDAR_DAY, CALENDAR_DAY_TODAY, CALENDAR_DAY_OTHER, CALENDAR_DAY_SELECTED,
)
from ui.memory_graph import GraphTab
from ui.icons import IconWidget, IconButton, source_icon_name, make_icon
from core.scheduler import (
    ScheduleManager, TASK_REMINDER, TASK_CHECK_EMAILS,
    TASK_DAILY_BRIEFING, TASK_AGENT_PROMPT,
    REPEAT_NONE, REPEAT_HOURLY, REPEAT_DAILY, REPEAT_WEEKDAYS, REPEAT_WEEKLY,
    parse_due_at
)
from core.composio_manager import ComposioManager, TOOLKIT_GOOGLECALENDAR

_TAB_ON = f"""
    QPushButton {{
        background: {RAISED_CSS};
        border: 1px solid {BORDER_HI_CSS}; border-radius: {R_SM}px;
        color: {TEXT_CSS};
        font-family: {FONT}; font-size: {FS_MD}px; font-weight: 600;
    }}
    QPushButton QLabel {{ color: {TEXT_CSS}; font-weight: 600; }}
"""
_TAB_OFF = f"""
    QPushButton {{
        background: transparent;
        border: 1px solid transparent; border-radius: {R_SM}px;
        color: {TEXT_2_CSS};
        font-family: {FONT}; font-size: {FS_MD}px;
    }}
    QPushButton:hover {{ background: {css(C_TEXT, 18)}; color: {TEXT_CSS}; }}
    QPushButton QLabel {{ color: {TEXT_2_CSS}; }}
    QPushButton:hover QLabel {{ color: {TEXT_CSS}; }}
"""
_CARD_CSS = f"""
    QFrame {{
        background: {SURFACE_CSS};
        border: 1px solid {BORDER_CSS};
        border-radius: {R_MD}px;
    }}
    QLabel {{ border: none; background: transparent; }}
"""

_MESES_PT = [
    '', 'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
]


def _tab_button(icon: str, label: str) -> QPushButton:
    # Texto e icone nativos do QPushButton: um QHBoxLayout filho nao entra no
    # sizeHint do botao, e a aba colapsava para poucos pixels de largura.
    btn = QPushButton(f'  {label}')
    btn.setIcon(make_icon(icon, 14, C_TEXT_2))
    btn.setIconSize(QSize(14, 14))
    btn.setFixedHeight(32)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    return btn


# =============================================================================
# Diálogo: Nova Tarefa / Schedule do Agente (Manus-style)
# =============================================================================

class NewAgentTaskDialog(QDialog):
    """Diálogo para agendar tarefas executivas que o Nigel executa no tempo."""

    def __init__(self, parent=None, prefill: dict | None = None):
        super().__init__(parent, Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(420, 420)
        self.result_data = None
        self._prefill = prefill or {}
        self._build()
        self._apply_prefill()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(10)

        title_lbl = QLabel('Novo Schedule / Tarefa do Nigel')
        title_lbl.setStyleSheet(f"color: {TEXT_CSS}; font-size: {FS_LG}px; font-weight: 600; font-family: {FONT};")
        layout.addWidget(title_lbl)

        # Tipo de Tarefa
        type_lbl = QLabel('Tipo de Ação Autônoma:')
        type_lbl.setStyleSheet(LABEL_SMALL)
        layout.addWidget(type_lbl)

        self.type_combo = QComboBox()
        self.type_combo.addItem('Lembrete / Chamada ao Usuário', TASK_REMINDER)
        self.type_combo.addItem('Verificar E-mails (Gmail/Outlook)', TASK_CHECK_EMAILS)
        self.type_combo.addItem('Daily Briefing (Resumo do Dia)', TASK_DAILY_BRIEFING)
        self.type_combo.addItem('Executar Prompt / Pesquisa IA', TASK_AGENT_PROMPT)
        self.type_combo.setStyleSheet(f"""
            QComboBox {{
                background: {RAISED_CSS}; border: 1px solid {BORDER_CSS};
                border-radius: 8px; color: {TEXT_CSS}; font-family: {FONT}; font-size: 12px;
                padding: 6px 10px;
            }}
            QComboBox QAbstractItemView {{
                background: {BG_SOLID_CSS}; color: {TEXT_CSS}; selection-background-color: {OVERLAY_CSS};
            }}
        """)
        self.type_combo.currentIndexChanged.connect(self._on_type_change)
        layout.addWidget(self.type_combo)

        # Título
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText('Título da tarefa (ex: Verificar e-mails de clientes)...')
        self.title_input.setStyleSheet(f"""
            QLineEdit {{
                background: {RAISED_CSS}; border: 1px solid {BORDER_CSS};
                border-radius: 8px; color: {TEXT_CSS}; font-family: {FONT}; font-size: 13px;
                padding: 8px 12px;
            }}
        """)
        layout.addWidget(self.title_input)

        # Detalhes / Prompt adicional
        self.desc_input = QTextEdit()
        self.desc_input.setPlaceholderText('Instruções ou prompt adicional para a IA (opcional)...')
        self.desc_input.setFixedHeight(65)
        self.desc_input.setStyleSheet(f"""
            QTextEdit {{
                background: {RAISED_CSS}; border: 1px solid {BORDER_CSS};
                border-radius: 8px; color: {TEXT_CSS}; font-family: {FONT}; font-size: 12px;
                padding: 8px 12px;
            }}
        """)
        layout.addWidget(self.desc_input)

        # Horário e Repetição
        row_opts = QHBoxLayout()

        col_time = QVBoxLayout()
        dt_lbl = QLabel('Executar em:')
        dt_lbl.setStyleSheet(LABEL_SMALL)
        col_time.addWidget(dt_lbl)
        self.dt_picker = QDateTimeEdit(QDateTime.currentDateTime().addSecs(1800))
        self.dt_picker.setCalendarPopup(True)
        self.dt_picker.setStyleSheet(f"""
            QDateTimeEdit {{
                background: {RAISED_CSS}; border: 1px solid {BORDER_CSS};
                border-radius: 8px; color: {TEXT_CSS}; font-family: {FONT};
                padding: 6px 10px; font-size: 12px;
            }}
        """)
        col_time.addWidget(self.dt_picker)
        row_opts.addLayout(col_time, 2)

        col_rep = QVBoxLayout()
        rep_lbl = QLabel('Repetição:')
        rep_lbl.setStyleSheet(LABEL_SMALL)
        col_rep.addWidget(rep_lbl)
        self.rep_combo = QComboBox()
        self.rep_combo.addItem('Não repetir (Única)', REPEAT_NONE)
        self.rep_combo.addItem('A cada hora', REPEAT_HOURLY)
        self.rep_combo.addItem('Diariamente', REPEAT_DAILY)
        self.rep_combo.addItem('Dias úteis (Seg-Sex)', REPEAT_WEEKDAYS)
        self.rep_combo.addItem('Semanalmente', REPEAT_WEEKLY)
        self.rep_combo.setStyleSheet(f"""
            QComboBox {{
                background: {RAISED_CSS}; border: 1px solid {BORDER_CSS};
                border-radius: 8px; color: {TEXT_CSS}; font-family: {FONT}; font-size: 12px;
                padding: 6px 10px;
            }}
            QComboBox QAbstractItemView {{
                background: {BG_SOLID_CSS}; color: {TEXT_CSS}; selection-background-color: {OVERLAY_CSS};
            }}
        """)
        col_rep.addWidget(self.rep_combo)
        row_opts.addLayout(col_rep, 2)

        layout.addLayout(row_opts)

        # Botões
        btns = QHBoxLayout()
        cancel_btn = QPushButton('Cancelar')
        cancel_btn.setStyleSheet(BTN_CLOSE)
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton('Agendar Tarefa')
        save_btn.setStyleSheet(BTN_PRIMARY)
        save_btn.clicked.connect(self._save)

        btns.addStretch()
        btns.addWidget(cancel_btn)
        btns.addWidget(save_btn)
        layout.addLayout(btns)

    def _on_type_change(self):
        task_type = self.type_combo.currentData()
        if not self.title_input.text():
            if task_type == TASK_CHECK_EMAILS:
                self.title_input.setText('Verificar caixas de entrada (Gmail/Outlook)')
            elif task_type == TASK_DAILY_BRIEFING:
                self.title_input.setText('Briefing do Dia com Agenda Google')
            elif task_type == TASK_AGENT_PROMPT:
                self.title_input.setText('Pesquisa/Execução IA em Segundo Plano')

    def _apply_prefill(self):
        if self._prefill.get('title'):
            self.title_input.setText(self._prefill['title'])
        if self._prefill.get('description'):
            self.desc_input.setPlainText(self._prefill['description'])
        if self._prefill.get('task_type'):
            idx = self.type_combo.findData(self._prefill['task_type'])
            if idx >= 0:
                self.type_combo.setCurrentIndex(idx)
        if self._prefill.get('repeat'):
            idx = self.rep_combo.findData(self._prefill['repeat'])
            if idx >= 0:
                self.rep_combo.setCurrentIndex(idx)
        due = self._prefill.get('due_at')
        if due:
            try:
                if isinstance(due, str):
                    due = datetime.fromisoformat(due)
                self.dt_picker.setDateTime(QDateTime(due))
            except Exception:
                pass

    def _save(self):
        title = self.title_input.text().strip()
        if not title:
            return
        self.result_data = {
            'title': title,
            'description': self.desc_input.toPlainText().strip(),
            'task_type': self.type_combo.currentData(),
            'repeat': self.rep_combo.currentData(),
            'due_at': self.dt_picker.dateTime().toPyDateTime()
        }
        self.accept()

    def paintEvent(self, event):
        p = QPainter(self)
        paint_panel(self, p, radius=16, bg=C_BG, border=C_BORDER)


# =============================================================================
# Diálogo: Novo Evento no Google Calendar Oficial
# =============================================================================

class NewGoogleCalendarEventDialog(QDialog):
    """Diálogo para criar eventos na Agenda Oficial do Google Calendar via Composio."""

    def __init__(self, parent=None, default_date: date | None = None):
        super().__init__(parent, Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(410, 380)
        self.result_data = None
        self._default_date = default_date or date.today()
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(10)

        title_lbl = QLabel('Novo Evento no Google Calendar')
        title_lbl.setStyleSheet(f"color: {TEXT_CSS}; font-size: {FS_LG}px; font-weight: 600; font-family: {FONT};")
        layout.addWidget(title_lbl)

        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText('Título da reunião ou compromisso...')
        self.title_input.setStyleSheet(f"""
            QLineEdit {{
                background: {RAISED_CSS}; border: 1px solid {BORDER_CSS};
                border-radius: 8px; color: {TEXT_CSS}; font-family: {FONT}; font-size: 13px;
                padding: 8px 12px;
            }}
        """)
        layout.addWidget(self.title_input)

        self.desc_input = QTextEdit()
        self.desc_input.setPlaceholderText('Descrição, pauta, link do Meet ou local (opcional)...')
        self.desc_input.setFixedHeight(65)
        self.desc_input.setStyleSheet(f"""
            QTextEdit {{
                background: {RAISED_CSS}; border: 1px solid {BORDER_CSS};
                border-radius: 8px; color: {TEXT_CSS}; font-family: {FONT}; font-size: 12px;
                padding: 8px 12px;
            }}
        """)
        layout.addWidget(self.desc_input)

        row_time = QHBoxLayout()
        col_dt = QVBoxLayout()
        dt_lbl = QLabel('Data e Hora de Início:')
        dt_lbl.setStyleSheet(LABEL_SMALL)
        col_dt.addWidget(dt_lbl)

        init_dt = datetime.combine(self._default_date, datetime.now().time().replace(minute=0, second=0)) + timedelta(hours=1)
        self.dt_picker = QDateTimeEdit(QDateTime(init_dt))
        self.dt_picker.setCalendarPopup(True)
        self.dt_picker.setStyleSheet(f"""
            QDateTimeEdit {{
                background: {RAISED_CSS}; border: 1px solid {BORDER_CSS};
                border-radius: 8px; color: {TEXT_CSS}; font-family: {FONT};
                padding: 6px 10px; font-size: 12px;
            }}
        """)
        col_dt.addWidget(self.dt_picker)
        row_time.addLayout(col_dt, 2)

        col_dur = QVBoxLayout()
        dur_lbl = QLabel('Duração:')
        dur_lbl.setStyleSheet(LABEL_SMALL)
        col_dur.addWidget(dur_lbl)
        self.dur_combo = QComboBox()
        self.dur_combo.addItem('15 minutos', 15)
        self.dur_combo.addItem('30 minutos', 30)
        self.dur_combo.addItem('45 minutos', 45)
        self.dur_combo.addItem('50 minutos', 50)
        self.dur_combo.addItem('60 minutos (1h)', 60)
        self.dur_combo.setCurrentIndex(1)
        self.dur_combo.setStyleSheet(f"""
            QComboBox {{
                background: {RAISED_CSS}; border: 1px solid {BORDER_CSS};
                border-radius: 8px; color: {TEXT_CSS}; font-family: {FONT}; font-size: 12px;
                padding: 6px 10px;
            }}
            QComboBox QAbstractItemView {{
                background: {BG_SOLID_CSS}; color: {TEXT_CSS}; selection-background-color: {OVERLAY_CSS};
            }}
        """)
        col_dur.addWidget(self.dur_combo)
        row_time.addLayout(col_dur, 1)

        layout.addLayout(row_time)

        btns = QHBoxLayout()
        cancel_btn = QPushButton('Cancelar')
        cancel_btn.setStyleSheet(BTN_CLOSE)
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton('Salvar no Google Calendar')
        save_btn.setStyleSheet(BTN_PRIMARY)
        save_btn.clicked.connect(self._save)

        btns.addStretch()
        btns.addWidget(cancel_btn)
        btns.addWidget(save_btn)
        layout.addLayout(btns)

    def _save(self):
        title = self.title_input.text().strip()
        if not title:
            return
        self.result_data = {
            'title': title,
            'description': self.desc_input.toPlainText().strip(),
            'start_time': self.dt_picker.dateTime().toPyDateTime(),
            'duration_minutes': self.dur_combo.currentData()
        }
        self.accept()

    def paintEvent(self, event):
        p = QPainter(self)
        paint_panel(self, p, radius=16, bg=C_BG, border=C_BORDER)


# =============================================================================
# Aba 1: Schedules (Tarefas Autônomas do Nigel estilo Manus)
# =============================================================================

class SchedulesTab(QWidget):
    """
    Aba de tarefas agendadas e rotinas autônomas que o Nigel executa
    (Lembretes inteligentes, checagens de e-mail, briefings e prompts).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.addWidget(IconWidget('tasks', 16))
        lbl = QLabel('SCHEDULES & TAREFAS DO NIGEL')
        lbl.setStyleSheet(LABEL_SECTION)

        add_btn = QPushButton('+ Nova Tarefa')
        add_btn.setStyleSheet(BTN_PRIMARY)
        add_btn.setFixedHeight(34)
        add_btn.setMinimumWidth(110)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._new_task)

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
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            if item.widget():
                _w = item.widget()
                _w.setParent(None)   # tira da tela JA; deleteLater() so' libera depois
                _w.deleteLater()

        tasks = ScheduleManager.get_instance().get_all(include_done=False)
        if not tasks:
            empty = QLabel(
                "Nenhum schedule do Nigel ativo.\n"
                "Tarefas agendadas, briefings e checagens autônomas aparecem aqui."
            )
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(f"color: {TEXT_2_CSS}; font-size: 12px; font-family: {FONT}; padding: 30px;")
            self.list_layout.insertWidget(0, empty)
            return

        for t in tasks:
            self.list_layout.insertWidget(self.list_layout.count() - 1, self._make_card(t))

    def _make_card(self, t: dict) -> QFrame:
        card = QFrame()
        card.setStyleSheet(_CARD_CSS)
        lay = QHBoxLayout(card)
        lay.setContentsMargins(14, 10, 10, 10)
        lay.setSpacing(10)

        task_type = t.get('task_type', TASK_REMINDER)
        icon_name = source_icon_name(t.get('source', 'manual'), task_type=task_type)
        icon = IconWidget(icon_name, 18)
        icon.setFixedWidth(22)

        info = QVBoxLayout()
        info.setSpacing(2)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)

        t_lbl = QLabel(t['title'])
        t_lbl.setStyleSheet(f"color: {TEXT_CSS}; font-family: {FONT}; font-weight: bold; font-size: 13px;")
        t_lbl.setWordWrap(True)
        title_row.addWidget(t_lbl)

        # Type badge
        type_tag = {
            TASK_REMINDER: 'Lembrete',
            TASK_CHECK_EMAILS: 'E-mails',
            TASK_DAILY_BRIEFING: 'Briefing',
            TASK_AGENT_PROMPT: 'IA Task'
        }.get(task_type, 'Tarefa')
        badge = QLabel(f"[{type_tag}]")
        badge.setStyleSheet(f"color: {TEXT_MUTE_CSS}; font-size: {FS_XS}px; font-family: {FONT};")
        title_row.addWidget(badge)
        title_row.addStretch()

        info.addLayout(title_row)

        # Horário e repetição
        due = parse_due_at(t['due_at'])
        now = datetime.now()
        repeat = t.get('repeat', REPEAT_NONE)
        rep_text = f" • Repete: {repeat}" if repeat != REPEAT_NONE else ""

        if due < now:
            time_str = f"Disparando ({due.strftime('%d/%m %H:%M')}){rep_text}"
            time_css = f"color: {TEXT_CSS};"
        else:
            diff = due - now
            mins = int(diff.total_seconds() / 60)
            if mins < 60:
                time_str = f"Em {mins}m — {due.strftime('%d/%m %H:%M')}{rep_text}"
            else:
                time_str = f"Em {mins // 60}h {mins % 60}m — {due.strftime('%d/%m %H:%M')}{rep_text}"
            time_css = f"color: {TEXT_2_CSS};"

        sub = QLabel(time_str)
        sub.setStyleSheet(f"font-size: 11px; font-family: {FONT}; {time_css}")
        info.addWidget(sub)

        # Detalhes se existirem
        if t.get('description'):
            desc = QLabel(t['description'])
            desc.setStyleSheet(f"color: {TEXT_2_CSS}; font-size: 11px; font-family: {FONT};")
            desc.setWordWrap(True)
            info.addWidget(desc)

        # Ações rápidas
        tid = t['id']
        run_btn = IconButton('play', 28, 'Executar agora')
        run_btn.clicked.connect(lambda i=tid: self._run_now(i))

        done_btn = IconButton('check', 28, 'Concluir')
        done_btn.clicked.connect(lambda i=tid: self._mark_done(i))

        del_btn = IconButton('close', 28, 'Deletar')
        del_btn.clicked.connect(lambda i=tid: self._delete(i))

        lay.addWidget(icon)
        lay.addLayout(info, 1)
        lay.addWidget(run_btn)
        lay.addWidget(done_btn)
        lay.addWidget(del_btn)

        return card

    def _new_task(self):
        dlg = NewAgentTaskDialog(self)
        sc = QApplication.primaryScreen().availableGeometry()
        dlg.move(sc.width() // 2 - dlg.width() // 2, sc.height() // 2 - dlg.height() // 2)
        if dlg.exec() and dlg.result_data:
            data = dlg.result_data
            ScheduleManager.get_instance().add(
                title=data['title'],
                description=data.get('description', ''),
                due_at=data['due_at'],
                task_type=data.get('task_type', TASK_REMINDER),
                repeat=data.get('repeat', REPEAT_NONE),
                source='manual'
            )
            self.refresh()

    def _run_now(self, task_id: int):
        task = ScheduleManager.get_instance().get_by_id(task_id)
        if task:
            def _exec():
                ScheduleManager.get_instance().execute_task(task)
                QTimer.singleShot(500, self.refresh)
            threading.Thread(target=_exec, daemon=True).start()

    def _mark_done(self, task_id: int):
        ScheduleManager.get_instance().mark_done(task_id)
        self.refresh()

    def _delete(self, task_id: int):
        ScheduleManager.get_instance().delete(task_id)
        self.refresh()


# =============================================================================
# Componente: Grade do Mês Espelhada do Google Calendar
# =============================================================================

class MonthCalendarGridWidget(QWidget):
    """Grade interativa dos dias do mês com marcação de compromissos."""
    day_selected = pyqtSignal(object)
    create_requested = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.current_year = datetime.now().year
        self.current_month = datetime.now().month
        self.selected_date = date.today()
        self.events_by_date: dict[str, list[dict]] = {}
        self._build()

    def set_events(self, events: list[dict]):
        self.events_by_date = {}
        for ev in events:
            start_raw = ev.get('start', '')
            if start_raw:
                try:
                    ev_date_str = start_raw[:10]
                    self.events_by_date.setdefault(ev_date_str, []).append(ev)
                except Exception:
                    pass
        self.render_days()

    def set_year_month(self, year: int, month: int):
        self.current_year = year
        self.current_month = month
        self.render_days()

    def _build(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(4)

        # Header dos dias da semana
        day_names = ['DOM', 'SEG', 'TER', 'QUA', 'QUI', 'SEX', 'SÁB']
        days_header = QHBoxLayout()
        days_header.setSpacing(2)
        for name in day_names:
            lbl = QLabel(name)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"color: {TEXT_2_CSS}; font-size: 10px; font-weight: bold; font-family: {FONT};")
            days_header.addWidget(lbl, 1)
        self.main_layout.addLayout(days_header)

        # Grid 7x6
        self.grid_widget = QWidget()
        self.grid_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(3)
        self.main_layout.addWidget(self.grid_widget)

        self.render_days()

    def render_days(self):
        while self.grid_layout.count() > 0:
            item = self.grid_layout.takeAt(0)
            if item.widget():
                _w = item.widget()
                _w.setParent(None)   # tira da tela JA; deleteLater() so' libera depois
                _w.deleteLater()

        cal = calendar.Calendar(firstweekday=6)  # Sunday first
        month_days = cal.monthdatescalendar(self.current_year, self.current_month)

        today = date.today()

        for row_idx, week in enumerate(month_days):
            for col_idx, d in enumerate(week):
                is_curr_month = (d.month == self.current_month)
                is_today = (d == today)
                is_selected = (d == self.selected_date)

                date_str = d.strftime('%Y-%m-%d')
                day_events = self.events_by_date.get(date_str, [])

                btn = QPushButton()
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setFixedHeight(34)

                btn_lay = QVBoxLayout(btn)
                btn_lay.setContentsMargins(2, 2, 2, 2)
                btn_lay.setSpacing(1)

                day_num = QLabel(str(d.day))
                day_num.setAlignment(Qt.AlignmentFlag.AlignCenter)

                # Os estilos vem de ui.theme. Antes eram strings nao-f com chaves
                # duplicadas ({{ }}), que o Qt recebia literalmente e descartava —
                # so o ramo "selecionado" tinha estilo de verdade.
                if is_selected:
                    btn.setStyleSheet(CALENDAR_DAY_SELECTED)
                    day_num.setStyleSheet(
                        f"color: {TEXT_CSS}; font-weight: 600; font-size: {FS_SM}px; font-family: {FONT};")
                elif is_today:
                    btn.setStyleSheet(CALENDAR_DAY_TODAY)
                    day_num.setStyleSheet(
                        f"color: {GOLD_SOFT_CSS}; font-weight: 700; font-size: {FS_SM}px; font-family: {FONT};")
                elif is_curr_month:
                    btn.setStyleSheet(CALENDAR_DAY)
                    day_num.setStyleSheet(
                        f"color: {TEXT_CSS}; font-size: {FS_SM}px; font-family: {FONT};")
                else:
                    btn.setStyleSheet(CALENDAR_DAY_OTHER)
                    day_num.setStyleSheet(
                        f"color: {TEXT_MUTE_CSS}; font-size: {FS_SM}px; font-family: {FONT};")

                btn_lay.addWidget(day_num)

                # Indicador de eventos
                if day_events:
                    dot = QLabel(f"● {len(day_events)}" if len(day_events) > 1 else "●")
                    dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    dot.setStyleSheet(f"color: {GOLD_SOFT_CSS}; font-size: 8px; font-weight: bold; font-family: {FONT};")
                    btn_lay.addWidget(dot)

                btn.clicked.connect(lambda checked=False, target_date=d: self._on_date_clicked(target_date))
                self.grid_layout.addWidget(btn, row_idx, col_idx)

    def _on_date_clicked(self, target_date: date):
        self.selected_date = target_date
        self.render_days()
        self.day_selected.emit(target_date)


# =============================================================================
# Aba 2: Google Calendar (Agenda Oficial Espelhada via Composio)
# =============================================================================

class GoogleCalendarTab(QWidget):
    """
    Aba da Agenda Oficial no Google Calendar.
    Lê e gerencia eventos reais da conta Google via Composio com espelhamento completo.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.current_year = datetime.now().year
        self.current_month = datetime.now().month
        self.selected_date = date.today()
        self.view_mode = 'month'  # 'month', 'list', 'day'
        self.all_events: list[dict] = []
        self._is_loading = False

        self._build()
        self.refresh()

    def _build(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 8, 0, 0)
        self.layout.setSpacing(8)

        # Header Principal com Título e Ações
        header = QHBoxLayout()
        # Marca real do Google Calendar (SVG oficial, ver ui/brand_svgs.py) em
        # vez do 'calendar' generico desenhado a mao — a secao fala de UM
        # servico especifico, entao mostra a marca dele.
        header.addWidget(IconWidget('brand_gcal', 16))
        lbl = QLabel('GOOGLE CALENDAR (AGENDA OFICIAL)')
        lbl.setStyleSheet(LABEL_SECTION)

        self.sync_btn = IconButton('refresh', 28, 'Sincronizar com Google Agenda')
        self.sync_btn.clicked.connect(self.refresh)

        add_btn = QPushButton('+ Novo Evento')
        add_btn.setStyleSheet(BTN_PRIMARY)
        add_btn.setFixedHeight(30)
        add_btn.setMinimumWidth(125)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(lambda: self._new_calendar_event(self.selected_date))

        header.addWidget(lbl)
        header.addStretch()
        header.addWidget(self.sync_btn)
        header.addWidget(add_btn)
        self.layout.addLayout(header)

        # Barra de Navegação de Data e Modos de Visualização
        nav_row = QHBoxLayout()
        nav_row.setSpacing(6)

        self.prev_btn = QPushButton('◀')
        self.prev_btn.setFixedSize(28, 28)
        self.prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.prev_btn.setStyleSheet(f"""
            QPushButton {{
                background: {RAISED_CSS}; border: 1px solid {BORDER_CSS};
                border-radius: {R_SM}px; color: {TEXT_CSS}; font-size: {FS_SM}px;
            }}
            QPushButton:hover {{ background: {OVERLAY_CSS}; }}
        """)
        self.prev_btn.clicked.connect(self._prev_month)

        self.month_lbl = QLabel(f"{_MESES_PT[self.current_month]} {self.current_year}")
        self.month_lbl.setStyleSheet(f"color: {TEXT_CSS}; font-size: {FS_BASE}px; font-weight: 600; font-family: {FONT};")
        self.month_lbl.setMinimumWidth(140)
        self.month_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.next_btn = QPushButton('▶')
        self.next_btn.setFixedSize(28, 28)
        self.next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_btn.setStyleSheet(f"""
            QPushButton {{
                background: {RAISED_CSS}; border: 1px solid {BORDER_CSS};
                border-radius: {R_SM}px; color: {TEXT_CSS}; font-size: {FS_SM}px;
            }}
            QPushButton:hover {{ background: {OVERLAY_CSS}; }}
        """)
        self.next_btn.clicked.connect(self._next_month)

        today_btn = QPushButton('Hoje')
        today_btn.setFixedHeight(28)
        today_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        today_btn.setStyleSheet(f"""
            QPushButton {{
                background: {RAISED_CSS}; border: 1px solid {BORDER_CSS};
                border-radius: 6px; color: {TEXT_CSS}; font-size: 11px; font-family: {FONT};
                padding: 0 12px;
            }}
            QPushButton:hover {{ background: {OVERLAY_CSS}; color: {TEXT_CSS}; }}
        """)
        today_btn.clicked.connect(self._go_today)

        nav_row.addWidget(self.prev_btn)
        nav_row.addWidget(self.month_lbl)
        nav_row.addWidget(self.next_btn)
        nav_row.addWidget(today_btn)
        nav_row.addStretch()

        # View Mode Selector (Mês | Lista | Dia)
        self.btn_view_month = QPushButton('Mês')
        self.btn_view_list = QPushButton('Lista')
        self.btn_view_day = QPushButton('Dia')

        for vbtn, vmode in [(self.btn_view_month, 'month'), (self.btn_view_list, 'list'), (self.btn_view_day, 'day')]:
            vbtn.setFixedHeight(28)
            vbtn.setMinimumWidth(55)
            vbtn.setCursor(Qt.CursorShape.PointingHandCursor)
            vbtn.clicked.connect(lambda checked=False, m=vmode: self._set_view_mode(m))
            nav_row.addWidget(vbtn)

        self._update_view_mode_buttons()
        self.layout.addLayout(nav_row)

        # Status / Feedback de Sincronização
        self.status_sync_lbl = QLabel('')
        self.status_sync_lbl.setStyleSheet(f"color: {TEXT_2_CSS}; font-size: 11px; font-style: italic; font-family: {FONT};")
        self.layout.addWidget(self.status_sync_lbl)


        # Área de Conteúdo
        self.calendar_grid = MonthCalendarGridWidget()
        self.calendar_grid.day_selected.connect(self._on_calendar_day_selected)
        self.calendar_grid.create_requested.connect(self._new_calendar_event)
        self.layout.addWidget(self.calendar_grid)

        # Lista de Eventos Scrollável
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

        self.layout.addWidget(self.scroll, 1)

    def _set_view_mode(self, mode: str):
        self.view_mode = mode
        self._update_view_mode_buttons()
        self.calendar_grid.setVisible(mode == 'month')
        self._render_events_view()

    def _update_view_mode_buttons(self):
        style_on = f"background: {RAISED_CSS}; border: 1px solid {BORDER_HI_CSS}; border-radius: {R_SM}px; color: {TEXT_CSS}; font-size: {FS_SM}px; font-weight: 600; padding: 0 8px;"
        style_off = f"background: transparent; border: 1px solid {BORDER_CSS}; border-radius: {R_SM}px; color: {TEXT_2_CSS}; font-size: {FS_SM}px; padding: 0 8px;"

        self.btn_view_month.setStyleSheet(style_on if self.view_mode == 'month' else style_off)
        self.btn_view_list.setStyleSheet(style_on if self.view_mode == 'list' else style_off)
        self.btn_view_day.setStyleSheet(style_on if self.view_mode == 'day' else style_off)

    def _prev_month(self):
        if self.current_month == 1:
            self.current_month = 12
            self.current_year -= 1
        else:
            self.current_month -= 1
        self.month_lbl.setText(f"{_MESES_PT[self.current_month]} {self.current_year}")
        self.calendar_grid.set_year_month(self.current_year, self.current_month)
        self.refresh()

    def _next_month(self):
        if self.current_month == 12:
            self.current_month = 1
            self.current_year += 1
        else:
            self.current_month += 1
        self.month_lbl.setText(f"{_MESES_PT[self.current_month]} {self.current_year}")
        self.calendar_grid.set_year_month(self.current_year, self.current_month)
        self.refresh()

    def _go_today(self):
        today = date.today()
        self.current_year = today.year
        self.current_month = today.month
        self.selected_date = today
        self.month_lbl.setText(f"{_MESES_PT[self.current_month]} {self.current_year}")
        self.calendar_grid.selected_date = today
        self.calendar_grid.set_year_month(self.current_year, self.current_month)
        self.refresh()

    def _on_calendar_day_selected(self, target_date: date):
        self.selected_date = target_date
        self._render_events_view()

    def refresh(self):
        if self._is_loading:
            return

        cm = ComposioManager.get_instance()
        if not cm.is_configured() or not cm.check_connection(TOOLKIT_GOOGLECALENDAR):
            self.calendar_grid.setVisible(False)
            self._render_disconnected_state()
            return

        self._is_loading = True
        self.status_sync_lbl.setText('Espelhando compromissos do Google Calendar...')
        self.calendar_grid.setVisible(self.view_mode == 'month')

        def _fetch():
            try:
                # Período do mês atual com folga de 7 dias antes/depois
                first_day = date(self.current_year, self.current_month, 1) - timedelta(days=7)
                last_day = date(self.current_year, self.current_month, 28) + timedelta(days=14)

                time_min = datetime.combine(first_day, datetime.min.time())
                time_max = datetime.combine(last_day, datetime.max.time())

                events = cm.calendar_list_events(limit=150, time_min=time_min, time_max=time_max)
                self.all_events = events
            except Exception as e:
                print(f"[GoogleCalendarTab] Erro ao sincronizar: {e}")
                self.all_events = []
            finally:
                self._is_loading = False
                QTimer.singleShot(0, self._on_sync_complete)

        threading.Thread(target=_fetch, daemon=True).start()

    def _on_sync_complete(self):
        self.status_sync_lbl.setText(f"✓ Sincronizado com Google Calendar ({len(self.all_events)} eventos no período).")
        self.calendar_grid.set_events(self.all_events)
        self._render_events_view()

    def _render_disconnected_state(self):
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            if item.widget():
                _w = item.widget()
                _w.setParent(None)   # tira da tela JA; deleteLater() so' libera depois
                _w.deleteLater()

        card = QFrame()
        card.setStyleSheet(_CARD_CSS)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(10)

        title = QLabel("Google Calendar Desconectado")
        title.setStyleSheet(f"color: {TEXT_CSS}; font-weight: 600; font-size: {FS_LG}px; font-family: {FONT};")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        desc = QLabel(
            "O Nigel utiliza o Google Calendar como sua agenda oficial.\n"
            "Conecte sua conta Google para espelhar suas reuniões e compromissos reais."
        )
        desc.setStyleSheet(f"color: {TEXT_2_CSS}; font-size: 12px; font-family: {FONT};")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)

        conn_btn = QPushButton("Conectar Google Calendar Agora")
        conn_btn.setStyleSheet(BTN_PRIMARY)
        conn_btn.setFixedHeight(34)
        conn_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        conn_btn.clicked.connect(self._connect_google)

        lay.addWidget(title)
        lay.addWidget(desc)
        lay.addWidget(conn_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        self.list_layout.insertWidget(0, card)

    def _render_events_view(self):
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            if item.widget():
                _w = item.widget()
                _w.setParent(None)   # tira da tela JA; deleteLater() so' libera depois
                _w.deleteLater()

        cm = ComposioManager.get_instance()
        if not cm.is_configured() or not cm.check_connection(TOOLKIT_GOOGLECALENDAR):
            return

        if self.view_mode == 'month':
            # Mostra eventos do dia selecionado
            sel_str = self.selected_date.strftime('%Y-%m-%d')
            day_events = [ev for ev in self.all_events if (ev.get('start', '')[:10] == sel_str)]

            header_lbl = QLabel(f"Compromissos em {self.selected_date.strftime('%d/%m/%Y')} ({len(day_events)}):")
            header_lbl.setStyleSheet(f"color: {TEXT_2_CSS}; font-weight: 600; font-size: {FS_MD}px; font-family: {FONT};")
            self.list_layout.insertWidget(0, header_lbl)

            if not day_events:
                empty = QLabel(f"Nenhum compromisso marcado para {self.selected_date.strftime('%d/%m/%Y')}.")
                empty.setStyleSheet(f"color: {TEXT_2_CSS}; font-size: 11px; font-family: {FONT}; padding: 10px 0;")
                self.list_layout.insertWidget(1, empty)
            else:
                for idx, ev in enumerate(day_events):
                    self.list_layout.insertWidget(idx + 1, self._make_event_card(ev))

        elif self.view_mode == 'list':
            # Lista todos os eventos ordenados
            if not self.all_events:
                empty = QLabel("Nenhum evento encontrado no período selecionado.")
                empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
                empty.setStyleSheet(f"color: {TEXT_2_CSS}; font-size: 12px; font-family: {FONT}; padding: 20px;")
                self.list_layout.insertWidget(0, empty)
                return

            for idx, ev in enumerate(self.all_events):
                self.list_layout.insertWidget(idx, self._make_event_card(ev, show_full_date=True))

        elif self.view_mode == 'day':
            # Visão detalhada do dia
            sel_str = self.selected_date.strftime('%Y-%m-%d')
            day_events = [ev for ev in self.all_events if (ev.get('start', '')[:10] == sel_str)]

            header_lbl = QLabel(f"Agenda do Dia — {self.selected_date.strftime('%A, %d de %B de %Y')}:")
            header_lbl.setStyleSheet(f"color: {TEXT_CSS}; font-weight: 600; font-size: {FS_BASE}px; font-family: {FONT};")
            self.list_layout.insertWidget(0, header_lbl)

            if not day_events:
                empty = QLabel("Dia livre! Nenhum compromisso agendado.")
                empty.setStyleSheet(f"color: {TEXT_2_CSS}; font-size: 12px; font-family: {FONT}; padding: 15px 0;")
                self.list_layout.insertWidget(1, empty)
            else:
                for idx, ev in enumerate(day_events):
                    self.list_layout.insertWidget(idx + 1, self._make_event_card(ev, detailed=True))

    def _make_event_card(self, ev: dict, show_full_date: bool = False, detailed: bool = False) -> QFrame:
        card = QFrame()
        card.setStyleSheet(_CARD_CSS)
        lay = QHBoxLayout(card)
        lay.setContentsMargins(14, 10, 10, 10)
        lay.setSpacing(10)

        icon = IconWidget('calendar', 18)
        icon.setFixedWidth(22)

        info = QVBoxLayout()
        info.setSpacing(2)

        t = QLabel(ev.get('summary') or '(Sem título)')
        t.setStyleSheet(f"color: {TEXT_CSS}; font-family: {FONT}; font-weight: bold; font-size: 13px;")
        t.setWordWrap(True)

        start_raw = ev.get('start', '')
        end_raw = ev.get('end', '')
        try:
            st = datetime.fromisoformat(start_raw.replace('Z', '+00:00'))
            if show_full_date:
                time_str = st.strftime('%d/%m/%Y às %H:%M')
            else:
                time_str = st.strftime('Às %H:%M')
            if end_raw:
                et = datetime.fromisoformat(end_raw.replace('Z', '+00:00'))
                time_str += f" até {et.strftime('%H:%M')}"
        except Exception:
            time_str = start_raw

        sub = QLabel(f"{time_str}")
        sub.setStyleSheet(f"color: {TEXT_2_CSS}; font-size: {FS_SM}px; font-family: {FONT};")

        info.addWidget(t)
        info.addWidget(sub)

        if ev.get('description'):
            d = QLabel(ev['description'])
            d.setStyleSheet(f"color: {TEXT_2_CSS}; font-size: 11px; font-family: {FONT};")
            d.setWordWrap(True)
            info.addWidget(d)

        if detailed and ev.get('location'):
            loc = QLabel(f"{ev['location']}")
            loc.setStyleSheet(f"color: {TEXT_2_CSS}; font-size: 11px; font-family: {FONT};")
            info.addWidget(loc)

        ev_id = ev.get('id')
        del_btn = IconButton('close', 28, 'Excluir do Google Calendar')
        del_btn.clicked.connect(lambda i=ev_id: self._delete_event(i))

        lay.addWidget(icon)
        lay.addLayout(info, 1)
        lay.addWidget(del_btn)

        return card

    def _connect_google(self):
        cm = ComposioManager.get_instance()
        cm.authorize_toolkit(TOOLKIT_GOOGLECALENDAR, open_browser=True)
        QTimer.singleShot(4000, self.refresh)

    def _new_calendar_event(self, default_date: date | None = None):
        cm = ComposioManager.get_instance()
        if not cm.check_connection(TOOLKIT_GOOGLECALENDAR):
            self._connect_google()
            return

        dlg = NewGoogleCalendarEventDialog(self, default_date=default_date or self.selected_date)
        sc = QApplication.primaryScreen().availableGeometry()
        dlg.move(sc.width() // 2 - dlg.width() // 2, sc.height() // 2 - dlg.height() // 2)
        if dlg.exec() and dlg.result_data:
            data = dlg.result_data
            self.status_sync_lbl.setText('Salvando evento no Google Calendar...')
            
            def _create():
                try:
                    cm.calendar_create_event(
                        title=data['title'],
                        description=data.get('description', ''),
                        start_time=data['start_time'],
                        duration_minutes=data.get('duration_minutes', 30)
                    )
                except Exception as e:
                    print(f"[GoogleCalendarTab] Erro ao criar evento: {e}")
                finally:
                    QTimer.singleShot(500, self.refresh)

            threading.Thread(target=_create, daemon=True).start()

    def _delete_event(self, event_id: str):
        if not event_id:
            return
        cm = ComposioManager.get_instance()
        self.status_sync_lbl.setText('Excluindo evento no Google Calendar...')

        def _del():
            try:
                cm.calendar_delete_event(event_id)
            except Exception as e:
                print(f"[GoogleCalendarTab] Erro ao excluir: {e}")
            finally:
                QTimer.singleShot(500, self.refresh)

        threading.Thread(target=_del, daemon=True).start()


# =============================================================================
# Container Principal do BrainPanel
# =============================================================================

class BrainPanel(QWidget):
    """Painel de Inteligência com Schedules, Google Calendar Espelhado e Grafo."""

    def __init__(self, parent=None):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # Ver o comentario em ui/settings.py: minimo + resize, sem tamanho
        # fixo e sem "corrigir" o tamanho num resizeEvent (isso trava a UI).
        self.setMinimumSize(620, 660)
        self.resize(620, 660)
        self._drag_pos = None
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header Superior
        title_row = QHBoxLayout()
        title_row.setContentsMargins(20, 14, 16, 0)
        # Sem isto o espacamento herda o setSpacing(0) do layout pai e o logo
        # fica colado no "N" de "Nigel".
        title_row.setSpacing(10)

        import os
        _duck_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets', 'nigel.png')
        title_icon = QLabel()
        if os.path.exists(_duck_path):
            _pix = QPixmap(_duck_path).scaled(20, 20, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            title_icon.setPixmap(_pix)
        title_icon.setFixedSize(20, 20)

        title = QLabel('Nigel — Inteligência e Automação')
        title.setStyleSheet(f"color: {TEXT_CSS}; font-family: {FONT}; font-size: {FS_LG}px; font-weight: 600;")

        close_btn = IconButton('close', 26, 'Fechar')
        close_btn.clicked.connect(self.hide)

        title_row.addWidget(title_icon)
        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(close_btn)
        layout.addLayout(title_row)

        # Tabs de Navegação
        tabs_row = QHBoxLayout()
        tabs_row.setContentsMargins(16, 10, 16, 0)
        tabs_row.setSpacing(4)

        self.tab_btns = []
        tabs_def = [
            # Marca real, mesma razao do cabecalho da aba: e' a agenda do
            # Google especificamente, nao um calendario generico.
            ('brand_gcal', 'Google Agenda'),
            ('tasks', 'Schedules'),
            ('graph', 'Grafo')
        ]

        for i, (icon, lbl) in enumerate(tabs_def):
            btn = _tab_button(icon, lbl)
            btn.clicked.connect(lambda checked=False, idx=i: self._switch_tab(idx))
            self.tab_btns.append(btn)
            tabs_row.addWidget(btn)

        tabs_row.addStretch()
        layout.addLayout(tabs_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f'background: {BORDER_CSS}; margin: 0 16px;')
        layout.addSpacing(8)
        layout.addWidget(sep)

        # Instâncias das Abas
        self.calendar_tab = GoogleCalendarTab()
        self.schedules_tab = SchedulesTab()
        self.graph_tab = GraphTab()

        content = QWidget()
        content.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(16, 8, 16, 16)

        self.content_layout.addWidget(self.calendar_tab)
        self.content_layout.addWidget(self.schedules_tab)
        self.content_layout.addWidget(self.graph_tab)

        layout.addWidget(content, 1)
        self._switch_tab(0)

    def _switch_tab(self, idx: int):
        self.calendar_tab.setVisible(idx == 0)
        self.schedules_tab.setVisible(idx == 1)
        self.graph_tab.setVisible(idx == 2)

        for i, btn in enumerate(self.tab_btns):
            btn.setStyleSheet(_TAB_ON if i == idx else _TAB_OFF)

        if idx == 0:
            self.calendar_tab.refresh()
        elif idx == 1:
            self.schedules_tab.refresh()
        elif idx == 2:
            self.graph_tab.refresh()

    def paintEvent(self, event):
        p = QPainter(self)
        paint_panel(self, p, radius=20, bg=C_BG, border=C_BORDER)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None:
            if not (event.buttons() & Qt.MouseButton.LeftButton):
                # Auto-recuperacao do mesmo problema de bar.py/settings.py:
                # sem isso, um mouseReleaseEvent perdido deixa o arraste
                # grudado e o proximo clique some porque a janela pula pro
                # cursor antes do clique "chegar" no widget de baixo.
                self._drag_pos = None
            else:
                self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def show_near_bar(self, bar_widget: QWidget):
        bar_pos = bar_widget.pos()
        sc = QApplication.primaryScreen().availableGeometry()
        x = max(sc.left(), min(bar_pos.x(), sc.right() - self.width()))
        y = bar_pos.y() - self.height() - 12
        if y < sc.top():
            y = bar_pos.y() + bar_widget.height() + 12
        self.move(x, y)
        self.show()
        self.raise_()


# =============================================================================
# Aba de Memória (para visualização no Settings)
# =============================================================================

class MemoryTab(QWidget):
    """Aba de visualização de memórias salvas."""

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
                background: {RAISED_CSS}; border: 1px solid {BORDER_CSS};
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
        from core.database import NigelDB
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            if item.widget():
                _w = item.widget()
                _w.setParent(None)   # tira da tela JA; deleteLater() so' libera depois
                _w.deleteLater()
        items = NigelDB.get_instance().get_saved_items(include_persona=False)
        if not items:
            empty = QLabel('Nenhum item na memória ainda.\nItens importantes serão salvos automaticamente pela IA.')
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setWordWrap(True)
            empty.setStyleSheet(f"color: {TEXT_2_CSS}; font-size: 12px; font-family: {FONT};")
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
        title = item.get('subject') or item.get('ai_summary') or 'Nota'
        preview = item.get('body_preview', '')
        lbl = QLabel(f"<b>{title}</b><br/><span style='color:{TEXT_2_CSS}'>{preview}</span>")
        lbl.setStyleSheet(f"color: {TEXT_CSS}; font-size: 13px; font-family: {FONT};")
        lbl.setWordWrap(True)
        lay.addWidget(icon)
        lay.addWidget(lbl, 1)
        del_btn = IconButton('close', 28, 'Deletar memória')
        item_id = item['id']
        del_btn.clicked.connect(lambda i=item_id: self._delete_item(i))
        lay.addWidget(del_btn)
        return card

    def _delete_item(self, item_id: str):
        from core.database import NigelDB
        NigelDB.get_instance().delete_saved_item(item_id)
        self.refresh()

    def _save_note(self):
        text = self.note_input.text().strip()
        if not text:
            return
        from core.database import NigelDB
        import uuid
        NigelDB.get_instance().save_important({
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


# Aliases para compatibilidade retroativa
AgendaTab = SchedulesTab
NewScheduleDialog = NewAgentTaskDialog
