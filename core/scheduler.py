"""
core/scheduler.py — Motor de Schedules e Tarefas Autônomas do Nigel (Manus-style Task Scheduler).

Gerencia tarefas agendadas que o próprio Nigel executa no tempo:
- Lembretes e chamadas interativas com diálogo de IA (reminder)
- Verificação autônoma de e-mails via Composio (check_emails)
- Briefing matinal / diário com agenda e pendências (daily_briefing)
- Execução de prompts e pesquisas em segundo plano pela IA (agent_prompt)
- Rotinas recorrentes (de hora em hora, diário, dias úteis, semanal)
"""

import json
import threading
from datetime import datetime, timedelta
from PyQt6.QtCore import QThread, pyqtSignal

from core import db as _db

# Tipos de tarefas do agente
TASK_REMINDER = 'reminder'
TASK_CHECK_EMAILS = 'check_emails'
TASK_DAILY_BRIEFING = 'daily_briefing'
TASK_AGENT_PROMPT = 'agent_prompt'
TASK_CUSTOM = 'custom'

# Status
STATUS_PENDING = 'pending'
STATUS_RUNNING = 'running'
STATUS_COMPLETED = 'completed'
STATUS_PAUSED = 'paused'
STATUS_FAILED = 'failed'

# Repetições
REPEAT_NONE = 'none'
REPEAT_HOURLY = 'hourly'
REPEAT_DAILY = 'daily'
REPEAT_WEEKDAYS = 'weekdays'
REPEAT_WEEKLY = 'weekly'


def parse_due_at(value: str | datetime | None) -> datetime:
    """Converte ISO string/datetime para datetime local naive (sem fuso)."""
    if value is None:
        return datetime.now()
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        except Exception:
            dt = datetime.now()
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt


def format_due_at(dt: datetime) -> str:
    """Serializa datetime para o banco sempre como ISO local naive."""
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt.isoformat()


def compute_next_due(current_due: datetime, repeat: str) -> datetime:
    """Calcula o próximo horário de disparo para tarefas recorrentes, preservando o horário base."""
    now = datetime.now()
    dt = current_due
    if repeat == REPEAT_HOURLY:
        dt += timedelta(hours=1)
        while dt <= now:
            dt += timedelta(hours=1)
    elif repeat == REPEAT_DAILY:
        dt += timedelta(days=1)
        while dt <= now:
            dt += timedelta(days=1)
    elif repeat == REPEAT_WEEKDAYS:
        dt += timedelta(days=1)
        while dt.weekday() >= 5 or dt <= now:
            dt += timedelta(days=1)
    elif repeat == REPEAT_WEEKLY:
        dt += timedelta(weeks=1)
        while dt <= now:
            dt += timedelta(weeks=1)
    return dt


def _create_schema(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schedules (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            title           TEXT NOT NULL,
            description     TEXT,
            task_type       TEXT DEFAULT 'reminder',
            payload         TEXT DEFAULT '{}',
            repeat          TEXT DEFAULT 'none',
            source          TEXT DEFAULT 'manual',
            ref_item_id     TEXT,
            cloud_provider  TEXT,
            cloud_id        TEXT,
            due_at          TEXT NOT NULL,
            created_at      TEXT NOT NULL,
            last_run_at     TEXT,
            last_result     TEXT,
            status          TEXT DEFAULT 'pending',
            done            INTEGER DEFAULT 0
        )
    """)
    # Migration check para colunas do motor de tarefas do agente
    cols = [row[1] for row in conn.execute('PRAGMA table_info(schedules)').fetchall()]
    if 'task_type' not in cols:
        conn.execute("ALTER TABLE schedules ADD COLUMN task_type TEXT DEFAULT 'reminder'")
    if 'payload' not in cols:
        conn.execute("ALTER TABLE schedules ADD COLUMN payload TEXT DEFAULT '{}'")
    if 'repeat' not in cols:
        conn.execute("ALTER TABLE schedules ADD COLUMN repeat TEXT DEFAULT 'none'")
    if 'last_run_at' not in cols:
        conn.execute("ALTER TABLE schedules ADD COLUMN last_run_at TEXT")
    if 'last_result' not in cols:
        conn.execute("ALTER TABLE schedules ADD COLUMN last_result TEXT")
    if 'status' not in cols:
        conn.execute("ALTER TABLE schedules ADD COLUMN status TEXT DEFAULT 'pending'")
    if 'cloud_provider' not in cols:
        conn.execute('ALTER TABLE schedules ADD COLUMN cloud_provider TEXT')
    if 'cloud_id' not in cols:
        conn.execute('ALTER TABLE schedules ADD COLUMN cloud_id TEXT')
    conn.commit()


class ScheduleManager:
    _instance = None

    @classmethod
    def get_instance(cls) -> 'ScheduleManager':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        _db.ensure_schema('nigel_schedules', _create_schema)

    @property
    def conn(self):
        """Conexao SQLite desta thread (ver core/db.py)."""
        return _db.get_conn()

    def add(self, title: str, description: str = '', due_at: datetime = None,
            task_type: str = TASK_REMINDER, payload: dict | str = None,
            repeat: str = REPEAT_NONE, source: str = 'manual', ref_item_id: str = '') -> int:
        """Adiciona uma tarefa agendada no motor do Nigel."""
        if due_at is None:
            due_at = datetime.now() + timedelta(hours=1)
        else:
            due_at = parse_due_at(due_at)

        if isinstance(payload, dict):
            payload_str = json.dumps(payload, ensure_ascii=False)
        else:
            payload_str = str(payload or '{}')

        due_iso = format_due_at(due_at)
        cur = self.conn.execute('''
            INSERT INTO schedules (
                title, description, task_type, payload, repeat,
                source, ref_item_id, due_at, created_at, status, done
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        ''', (
            title, description, task_type, payload_str, repeat,
            source, ref_item_id, due_iso, datetime.now().isoformat(), STATUS_PENDING
        ))
        self.conn.commit()
        return cur.lastrowid

    def get_all(self, include_done: bool = False) -> list[dict]:
        query = 'SELECT * FROM schedules'
        if not include_done:
            query += " WHERE done = 0 AND status != 'completed' AND status != 'cancelled'"
        query += ' ORDER BY due_at ASC'
        return [dict(r) for r in self.conn.execute(query).fetchall()]

    def get_by_id(self, schedule_id: int) -> dict | None:
        row = self.conn.execute('SELECT * FROM schedules WHERE id = ?', (schedule_id,)).fetchone()
        return dict(row) if row else None

    def get_overdue(self) -> list[dict]:
        """Retorna tarefas pendentes prontas para execução (due_at <= now)."""
        now = datetime.now()
        overdue = []
        rows = self.conn.execute(
            "SELECT * FROM schedules WHERE done = 0 AND status = 'pending'"
        ).fetchall()
        for row in rows:
            try:
                if parse_due_at(row['due_at']) <= now:
                    overdue.append(dict(row))
            except (TypeError, ValueError):
                continue
        return overdue

    def mark_done(self, schedule_id: int) -> None:
        item = self.get_by_id(schedule_id)
        if not item:
            return
        repeat = item.get('repeat') or REPEAT_NONE
        if repeat != REPEAT_NONE:
            next_due = compute_next_due(parse_due_at(item['due_at']), repeat)
            self.conn.execute('''
                UPDATE schedules 
                SET due_at = ?, status = 'pending', last_run_at = ?
                WHERE id = ?
            ''', (format_due_at(next_due), datetime.now().isoformat(), schedule_id))
        else:
            self.conn.execute('''
                UPDATE schedules 
                SET done = 1, status = 'completed', last_run_at = ?
                WHERE id = ?
            ''', (datetime.now().isoformat(), schedule_id))
        self.conn.commit()
        forget_schedule_notification(schedule_id)

    def postpone(self, schedule_id: int, minutes: int) -> None:
        cur = self.conn.execute('SELECT * FROM schedules WHERE id = ?', (schedule_id,)).fetchone()
        if cur:
            current_due = parse_due_at(cur['due_at'])
            now = datetime.now()
            if current_due < now:
                new_due = now + timedelta(minutes=minutes)
            else:
                new_due = current_due + timedelta(minutes=minutes)
            self.conn.execute(
                "UPDATE schedules SET due_at = ?, status = 'pending' WHERE id = ?",
                (format_due_at(new_due), schedule_id)
            )
            self.conn.commit()
            forget_schedule_notification(schedule_id)

    def pause_task(self, schedule_id: int) -> None:
        self.conn.execute("UPDATE schedules SET status = 'paused' WHERE id = ?", (schedule_id,))
        self.conn.commit()
        forget_schedule_notification(schedule_id)

    def resume_task(self, schedule_id: int) -> None:
        self.conn.execute("UPDATE schedules SET status = 'pending' WHERE id = ?", (schedule_id,))
        self.conn.commit()

    def delete(self, schedule_id: int) -> None:
        self.conn.execute('DELETE FROM schedules WHERE id = ?', (schedule_id,))
        self.conn.commit()
        forget_schedule_notification(schedule_id)

    def update(self, schedule_id: int, title: str = None, description: str = None,
               due_at: datetime = None, task_type: str = None, repeat: str = None,
               payload: dict | str = None, status: str = None) -> None:
        cur = self.conn.execute('SELECT * FROM schedules WHERE id = ?', (schedule_id,)).fetchone()
        if not cur:
            return

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
        if task_type is not None:
            fields.append('task_type = ?')
            values.append(task_type)
        if repeat is not None:
            fields.append('repeat = ?')
            values.append(repeat)
        if payload is not None:
            fields.append('payload = ?')
            values.append(json.dumps(payload, ensure_ascii=False) if isinstance(payload, dict) else str(payload))
        if status is not None:
            fields.append('status = ?')
            values.append(status)

        if not fields:
            return
        values.append(schedule_id)
        self.conn.execute(f'UPDATE schedules SET {", ".join(fields)} WHERE id = ?', values)
        self.conn.commit()
        forget_schedule_notification(schedule_id)

    def execute_task(self, item: dict) -> dict:
        """
        Executa a tarefa agendada do Nigel de acordo com seu task_type.
        """
        sid = item.get('id')
        ttype = item.get('task_type') or TASK_REMINDER
        title = item.get('title', '')
        desc = item.get('description', '')
        payload = {}
        try:
            payload = json.loads(item.get('payload') or '{}')
        except Exception:
            pass

        print(f"[Nigel Scheduler] Executando tarefa #{sid}: [{ttype}] {title}")
        result = {"success": True, "task_id": sid, "type": ttype}

        try:
            if ttype == TASK_CHECK_EMAILS:
                from core.composio_manager import ComposioManager
                from core import ai_triage
                from core.database import NigelDB
                cm = ComposioManager.get_instance()
                db = NigelDB.get_instance()
                
                gmail_msgs = cm.fetch_unread_gmail(limit=5)
                outlook_msgs = cm.fetch_unread_outlook(limit=5)
                all_msgs = gmail_msgs + outlook_msgs
                
                important_found = []
                for msg in all_msgs:
                    msg_id = msg['id']
                    if not db.is_seen(msg_id):
                        db.mark_seen(msg_id, msg.get('source', 'email'))
                        triage = ai_triage.classify(msg)
                        if triage.get('important'):
                            msg['ai_summary'] = triage.get('summary', '')
                            msg['ai_reason'] = triage.get('reason', '')
                            db.save_important(msg, saved_by='ai')
                            important_found.append(msg)

                summary = f"Verificação concluída: {len(all_msgs)} e-mails analisados, {len(important_found)} importantes."
                result["summary"] = summary
                result["important_count"] = len(important_found)

            elif ttype == TASK_DAILY_BRIEFING:
                # Passa pelo orquestrador de verdade (agenda_agent + email_agent),
                # em vez de um dump cru de eventos + uma chamada solta de LLM sem
                # contexto de e-mail. Roda em background thread (ver
                # ScheduleCheckerWorker._emit_pending), então uma chamada síncrona
                # aqui não trava a UI.
                from core.tools import build_orchestrator_registry
                from core.agent.prompts import orchestrator_prompt
                from core.agent.loop import run_agent
                try:
                    registry = build_orchestrator_registry()
                    task = (
                        "Gere o briefing matinal do usuário: consulte a agenda de hoje com o "
                        "agenda_agent e veja se algo importante ou pendente chegou por e-mail com "
                        "o email_agent. Responda com um resumo executivo curto e direto (poucas "
                        "frases), sem preâmbulo — é a primeira coisa que a pessoa lê de manhã."
                    )
                    res = run_agent(orchestrator_prompt(), [{'role': 'user', 'content': task}],
                                    registry, max_iterations=6)
                    result["summary"] = (res.text or '').strip() or 'Nenhuma novidade para o briefing de hoje.'
                except Exception as e:
                    result["summary"] = f'Não consegui montar o briefing agora: {e}'

            elif ttype == TASK_AGENT_PROMPT:
                from core.api_client import APIClient
                prompt_text = payload.get('prompt') or desc or title
                res_text = APIClient().call_llm([
                    {"role": "system", "content": "Você é o Nigel, assistente executivo."},
                    {"role": "user", "content": prompt_text}
                ], max_tokens=300)
                result["summary"] = res_text.strip()

            else:
                # Reminder / Call User
                result["summary"] = f"Lembrete ativo: {title}"

            # Atualiza histórico no banco
            self.conn.execute(
                "UPDATE schedules SET last_run_at = ?, last_result = ? WHERE id = ?",
                (datetime.now().isoformat(), result.get("summary", ""), sid)
            )
            self.conn.commit()

            # Avança repetição ou conclui
            repeat = item.get('repeat') or REPEAT_NONE
            if repeat != REPEAT_NONE:
                next_due = compute_next_due(parse_due_at(item['due_at']), repeat)
                self.conn.execute(
                    "UPDATE schedules SET due_at = ?, status = 'pending' WHERE id = ?",
                    (format_due_at(next_due), sid)
                )
            else:
                self.conn.execute(
                    "UPDATE schedules SET done = 1, status = 'completed' WHERE id = ?",
                    (sid,)
                )
            self.conn.commit()

        except Exception as e:
            print(f"[Nigel Scheduler] Erro ao executar tarefa #{sid}: {e}")
            result["success"] = False
            result["error"] = str(e)
            self.conn.execute(
                "UPDATE schedules SET status = 'failed', last_result = ? WHERE id = ?",
                (str(e), sid)
            )
            self.conn.commit()

        return result


_active_checker: 'ScheduleCheckerWorker | None' = None


def set_active_checker(checker: 'ScheduleCheckerWorker | None') -> None:
    global _active_checker
    _active_checker = checker


def forget_schedule_notification(schedule_id: int) -> None:
    """Permite re-notificar após adiar/remarcar/atualizar uma tarefa."""
    if _active_checker is not None:
        _active_checker.forget(schedule_id)


class ScheduleCheckerWorker(QThread):
    """
    Monitor contínuo de tarefas agendadas do Nigel.
    Dispara execução automática quando o momento agendado chega.
    """
    overdue_found = pyqtSignal(list)
    task_executed = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self._running = True
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
        
        mgr = ScheduleManager.get_instance()
        reminders_for_popup = []

        for item in pending:
            ttype = item.get('task_type') or TASK_REMINDER
            if ttype == TASK_REMINDER:
                reminders_for_popup.append(item)
            else:
                # Executa tarefas do agente (check_emails, daily_briefing, agent_prompt)
                def _run_bg(it=item):
                    res = mgr.execute_task(it)
                    self.task_executed.emit(res)
                threading.Thread(target=_run_bg, daemon=True).start()

        if reminders_for_popup:
            print(f"[Nigel] {len(reminders_for_popup)} lembrete(s) do agente ativo(s)...")
            self.overdue_found.emit(reminders_for_popup)

    def force_check(self):
        mgr = ScheduleManager.get_instance()
        self._emit_pending(self._pending(mgr.get_overdue()))

    def run(self):
        import time
        mgr = ScheduleManager.get_instance()
        self._emit_pending(self._pending(mgr.get_overdue()))
        while self._running:
            self._emit_pending(self._pending(mgr.get_overdue()))
            for _ in range(5):
                if not self._running:
                    break
                time.sleep(1)
