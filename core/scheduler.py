"""
core/scheduler.py — Gerenciador de Lembretes/Follow-ups do SEQ.

Suporta criação manual e automática (via IA).
Verifica schedules vencidos e emite signal para a UI.
"""

import sqlite3
import os
from datetime import datetime, timedelta
from PyQt6.QtCore import QThread, pyqtSignal
from core.storage import get_appdata_dir

_DB_FILE = 'seq.db'


def parse_due_at(value: str | datetime | None) -> datetime:
    """Converte ISO string/datetime para datetime local naive (sem fuso)."""
    if value is None:
        return datetime.now()
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt


def format_due_at(dt: datetime) -> str:
    """Serializa datetime para o banco sempre como ISO local naive."""
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt.isoformat()


def _get_conn() -> sqlite3.Connection:
    db_path = os.path.join(get_appdata_dir(), _DB_FILE)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schedules (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL,
            description TEXT,
            source      TEXT DEFAULT 'manual',
            ref_item_id TEXT,
            due_at      TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            done        INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    return conn

class ScheduleManager:
    __module__ = __name__
    __qualname__ = 'ScheduleManager'
    __doc__ = 'CRUD para lembretes/schedules.'
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.conn = _get_conn()

    def add(self, title: str, description: str, due_at: datetime = None, source: str = 'manual', ref_item_id: str = '') -> int:
        if due_at is None:
            due_at = datetime.now() + timedelta(hours=24)
        else:
            due_at = parse_due_at(due_at)
        cur = self.conn.execute('''
            INSERT INTO schedules (title, description, source, ref_item_id, due_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (title, description, source, ref_item_id, format_due_at(due_at), datetime.now().isoformat()))
        self.conn.commit()
        return cur.lastrowid

    def get_all(self, include_done: bool = False) -> list[dict]:
        query = 'SELECT * FROM schedules'
        if not include_done:
            query += ' WHERE done = 0'
        query += ' ORDER BY due_at ASC'
        return [dict(r) for r in self.conn.execute(query).fetchall()]

    def get_overdue(self) -> list[dict]:
        now = datetime.now()
        overdue = []
        rows = self.conn.execute('SELECT * FROM schedules WHERE done = 0').fetchall()
        for row in rows:
            try:
                if parse_due_at(row['due_at']) <= now:
                    overdue.append(dict(row))
            except (TypeError, ValueError):
                continue
        return overdue

    def mark_done(self, schedule_id: int) -> None:
        self.conn.execute('UPDATE schedules SET done = 1 WHERE id = ?', (schedule_id,))
        self.conn.commit()
        forget_schedule_notification(schedule_id)

    def postpone(self, schedule_id: int, minutes: int) -> None:
        cur = self.conn.execute('SELECT due_at FROM schedules WHERE id = ?', (schedule_id,)).fetchone()
        if cur:
            current_due = parse_due_at(cur['due_at'])
            now = datetime.now()
            if current_due < now:
                new_due = now + timedelta(minutes=minutes)
            else:
                new_due = current_due + timedelta(minutes=minutes)
            self.conn.execute('UPDATE schedules SET due_at = ? WHERE id = ?', (format_due_at(new_due), schedule_id))
            self.conn.commit()
            forget_schedule_notification(schedule_id)

    def delete(self, schedule_id: int) -> None:
        self.conn.execute('DELETE FROM schedules WHERE id = ?', (schedule_id,))
        self.conn.commit()
        forget_schedule_notification(schedule_id)

    def update(self, schedule_id: int, title: str = None, description: str = None, due_at: datetime = None) -> None:
        fields, values = [], []
        if title is not None:
            fields.append('title = ?')
            values.append(title)
        if description is not None:
            fields.append('description = ?')
            values.append(description)
        if due_at is not None:
            fields.append('due_at = ?')
            values.append(format_due_at(parse_due_at(due_at)))
        if not fields:
            return
        values.append(schedule_id)
        self.conn.execute(f'UPDATE schedules SET {", ".join(fields)} WHERE id = ?', values)
        self.conn.commit()
        forget_schedule_notification(schedule_id)

_active_checker: 'ScheduleCheckerWorker | None' = None


def set_active_checker(checker: 'ScheduleCheckerWorker | None') -> None:
    global _active_checker
    _active_checker = checker


def forget_schedule_notification(schedule_id: int) -> None:
    """Permite re-notificar após adiar/remarcar/atualizar um lembrete."""
    if _active_checker is not None:
        _active_checker.forget(schedule_id)


class ScheduleCheckerWorker(QThread):
    __module__ = __name__
    __qualname__ = 'ScheduleCheckerWorker'
    __doc__ = 'Verifica schedules vencidos a cada 10s e emite signal para a UI.'
    overdue_found = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self._running = True
        # id -> due_at na última notificação; re-notifica se due_at mudou
        self._notified_due: dict[int, str] = {}

    def stop(self):
        self._running = False

    def forget(self, schedule_id: int) -> None:
        self._notified_due.pop(int(schedule_id), None)

    def _pending(self, overdue: list[dict]) -> list[dict]:
        pending = []
        for item in overdue:
            sid = item['id']
            due_key = item.get('due_at', '')
            if self._notified_due.get(sid) != due_key:
                pending.append(item)
        return pending

    def _emit_pending(self, pending: list[dict]) -> None:
        if not pending:
            return
        for item in pending:
            self._notified_due[item['id']] = item.get('due_at', '')
        print(f"[SEQ] {len(pending)} lembrete(s) vencido(s) — abrindo popup(s)...")
        self.overdue_found.emit(pending)

    def force_check(self):
        mgr = ScheduleManager.get_instance()
        self._emit_pending(self._pending(mgr.get_overdue()))

    def run(self):
        import time
        mgr = ScheduleManager.get_instance()
        # Checagem imediata ao iniciar (não esperar 10s)
        self._emit_pending(self._pending(mgr.get_overdue()))
        while self._running:
            self._emit_pending(self._pending(mgr.get_overdue()))
            for _ in range(10):
                if not self._running:
                    break
                time.sleep(1)
