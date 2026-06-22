"""
ui/agenda_skills.py — Sistema compartilhado de skills de agenda do Nigel.

Usado pelo chat principal (Bar) e pelos popups de lembrete (ScheduleAlertDialog).
A IA retorna JSON com actions/buttons; a UI nativa garante confirmação do usuário.
"""

import json
import re
import uuid
import unicodedata
from datetime import datetime, timedelta
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

_CLOSING_ACTIONS = frozenset({'reschedule', 'delete_current', 'postpone', 'mark_done', 'delete_schedule'})

_CHAT_SKILLS_DOC = '''
## AGENDA TOOLS (Nigel's local reminders)

You help the user manage reminders and follow-ups in the main chat. You reply to the user in the same language they wrote in (usually Portuguese), but you ALWAYS reason and emit tools using this English specification.

### THE GOLDEN RULE
Whenever the user wants to schedule, remember, book, postpone, reschedule, complete or cancel ANYTHING that has (or implies) a date/time, you MUST emit the agenda tool as a JSON block. Talking about it in plain text is NOT enough — if the JSON block is missing, the reminder DOES NOT EXIST. Never say "done", "created", "scheduled" or "noted" unless the JSON block with the agenda action is present in the same reply.

### DECIDE FIRST: ask for context, or create directly?
You are a curious agent that builds a personal understanding of the user — you do not act like a dumb form. Before scheduling, make ONE judgement call:

- Does the request involve a person, company, place, group, project or relationship that is genuinely important AND that you do NOT already know (it is not in the memory/graph above, and the user has not explained it in this conversation)?
  → THEN ask first. Return a "clarification" with a short, natural, open question (e.g. "who is X to you?", "what's the context of this client?") and put the scheduling action you would have run into "pending_buttons". Do NOT create the reminder yet. After the user answers, the reminder is created automatically.
- Otherwise (the context is clear, already known, or the entity does not need personal context — like "pay the bill", "gym at 7am") 
  → create directly: put the agenda action in "actions". It runs immediately, exactly like confirming.

Use this judgement, not fixed keywords. A bare request with a NEW important person almost always deserves a quick context question. A routine task does not.

### How tools work
- Direct creation: agenda action goes in "actions" (runs immediately).
- Ask-first: "clarification" + the action inside "pending_buttons" (MANDATORY together — without pending_buttons the reminder is lost).
- Real ambiguity (a very similar reminder already exists): offer "buttons" so the user picks "update existing" vs "create new". Do not wrap a simple request in buttons.
- MEMORY/KNOWLEDGE actions (save_memory) also go inside "actions" (saved automatically to the graph).
- Reminders must use create_schedule / update_schedule — never save_memory for the reminder itself.
- To edit / complete / postpone / reschedule an existing reminder, use its schedule_id from the CURRENT AGENDA block below.
- Dates are ISO 8601 (e.g. 2026-06-21T10:00:00). Timezone: Brazil (UTC-3). Resolve relative dates ("today", "tomorrow", "next friday", "in 2 hours", "at 1am", weekdays, day numbers) yourself using the current date/time provided below. Do not ask for the exact date if you can infer it.
- Button labels are short and clear (e.g. "Create reminder — 2pm").

### Before creating
Check the CURRENT AGENDA. If a reminder with the same or a very similar title already exists, do NOT silently create a duplicate — tell the user and offer TWO buttons: one to update the existing one (update_schedule with its schedule_id) and one to create a new one (create_schedule). If nothing related exists, just create it directly via "actions". If the user says a relative day like "today", use the current day below, not the day of an old reminder.

### Memory / knowledge graph
You also build a personal intelligence about the user. Save with save_memory (in "actions") only when the content has lasting future value (relationships, preferences, habits, recurring problems, work context, important messages/decisions, personal facts). Do not save casual chatter. For category persona, only save when the user clearly explained a relationship or fact — a bare name is not persona. When unsure whether something is persona, decide by reasoning about the context, never by fixed keyword lists. Never save full secrets (passwords, tokens, documents).

Memory categories: persona, event, issue, message, project, general.

### Asking for context (judgement, not rules)
If you genuinely need to understand a person/entity before acting, return a "clarification" object with a natural open question AND move the agenda action you would have taken into "pending_buttons" (this is MANDATORY when a scheduling request is involved — without pending_buttons the reminder is lost). Prefer open questions ("who is X to you?", "what's the context of X?") over closed ones that invite useless "no" answers. After the user answers, judge the quality: a vague/negative answer should not become memory.

### JSON format (only when using tools, at the very end of your reply)

Normal case — clear request, create directly in "actions":
```json
{
  "actions": [
    {"type": "create_schedule", "title": "Reminder title", "description": "...", "due_at": "2026-06-20T16:16:00"}
  ]
}
```

You learned a lasting fact too — combine save_memory with the agenda action:
```json
{
  "actions": [
    {"type": "create_schedule", "title": "Reminder title", "description": "...", "due_at": "2026-06-20T16:16:00"},
    {"type": "save_memory", "category": "persona", "subject": "Important person", "note": "Objective relevant fact"}
  ]
}
```

Ambiguity case only — a similar reminder exists, let the user choose with buttons:
```json
{
  "buttons": [
    {
      "label": "Update existing reminder",
      "confirm_action": {"type": "update_schedule", "schedule_id": 3, "title": "Reminder title", "description": "...", "due_at": "2026-06-20T16:16:00"}
    },
    {
      "label": "Create new reminder",
      "confirm_action": {"type": "create_schedule", "title": "Reminder title", "description": "...", "due_at": "2026-06-20T16:16:00"}
    }
  ]
}
```

Need context first — ask and keep the action in pending_buttons:
```json
{
  "clarification": {
    "type": "persona_context",
    "subject": "name/context that must be understood",
    "question": "Short natural question for the user"
  },
  "pending_buttons": [
    {
      "label": "Create reminder after the answer",
      "confirm_action": {"type": "create_schedule", "title": "Reminder title", "description": "...", "due_at": "2026-06-20T16:16:00"}
    }
  ]
}
```

Skills in actions or confirm_action (chat):
- create_schedule — title, description (optional), due_at
- update_schedule — schedule_id, title, description (optional), due_at
- mark_done — schedule_id
- delete_schedule — schedule_id
- postpone — schedule_id, minutes
- reschedule — schedule_id, due_at

Skill allowed in actions:
- save_memory — category, subject, note, optional relevance_score (1-100)
'''

_ACTION_TYPE_ALIASES = {
    'edit_schedule': 'update_schedule',
    'edit_agenda': 'update_schedule',
    'edit_reminder': 'update_schedule',
    'modify_schedule': 'update_schedule',
    'update_reminder': 'update_schedule',
    'change_schedule': 'update_schedule',
    'update': 'update_schedule',
}

_EXISTING_SCHEDULE_OPS = frozenset({
    'reschedule', 'update_schedule', 'postpone', 'mark_done', 'delete_schedule',
})


def normalize_action_type(action: dict) -> dict:
    """Normaliza tipo e campos comuns vindos da IA."""
    if not isinstance(action, dict):
        return action
    fixed = dict(action)
    atype = (fixed.get('type') or '').strip()
    if atype in _ACTION_TYPE_ALIASES:
        fixed['type'] = _ACTION_TYPE_ALIASES[atype]
    if 'content' in fixed and 'description' not in fixed:
        fixed['description'] = fixed.pop('content')
    if 'text' in fixed and 'description' not in fixed:
        fixed['description'] = fixed.pop('text')
    if 'body' in fixed and 'description' not in fixed:
        fixed['description'] = fixed.pop('body')
    if 'new_title' in fixed and 'title' not in fixed:
        fixed['title'] = fixed.pop('new_title')
    return fixed


def normalize_action(action: dict, user_text: str = '') -> dict:
    return normalize_action_dates(normalize_action_type(action), user_text)


def resolve_schedule_id(action: dict, user_text: str = '', item: dict | None = None) -> int | None:
    """Resolve qual lembrete a ação afeta (popup, schedule_id ou match por contexto)."""
    if item:
        sid = item.get('id')
        if sid is not None:
            return int(sid)
    sid = action.get('schedule_id')
    if sid is not None:
        try:
            sid = int(sid)
        except (TypeError, ValueError):
            sid = None
        if sid is not None and _schedule_exists(sid):
            return sid
    from core.scheduler import ScheduleManager
    all_scheds = ScheduleManager.get_instance().get_all()
    if not all_scheds:
        return None
    atype = normalize_action_type(action).get('type')
    # Em update_schedule o title costuma ser o NOVO título — não use para achar o lembrete.
    if atype != 'update_schedule':
        title = (action.get('title') or '').strip()
        if title:
            matches = find_similar_schedules(title, threshold=0.5)
            if matches:
                return int(matches[0]['id'])
    if user_text:
        best_id = None
        best_score = 0.0
        for s in all_scheds:
            score = max(
                _title_similarity(user_text, s.get('title', '')),
                _title_similarity(user_text, s.get('description', '') or ''),
            )
            if score > best_score:
                best_score = score
                best_id = s['id']
        if best_score >= 0.3 and best_id is not None:
            return int(best_id)
    if len(all_scheds) == 1:
        return int(all_scheds[0]['id'])
    return None

_NOTIFICATION_SKILLS_DOC = '''
You are Nigel, the personal assistant managing the user's agenda inside this overdue-reminder popup. Reply to the user in their language (usually Portuguese), but reason and emit tools using this English specification.

## POPUP RULES
1. The user is talking DIRECTLY about the reminder in focus. When they ask to reschedule, postpone, complete or cancel it, put the action in the "actions" array for immediate execution (typing it already counts as confirmation).
2. Use "buttons" only when there is ambiguity or multiple options (max 3).
3. Be CONTEXTUAL: the action must match the request EXACTLY.
4. THE GOLDEN RULE: any change to the reminder MUST be emitted as a JSON tool block. Never claim something was done without the JSON present.
5. In the text reply, confirm what was done in one short line.
6. You have FULL visibility of the agenda — avoid time conflicts.
7. save_memory is only for lasting personal facts, never for the reminder itself.

Example — user asks to reschedule:
```json
{
  "actions": [
    {"type": "reschedule", "due_at": "2026-06-23T12:00:00"}
  ],
  "buttons": []
}
```

Example — user asks to edit the title/description of the focused reminder:
```json
{
  "actions": [
    {"type": "update_schedule", "title": "New title", "description": "New description"}
  ],
  "buttons": []
}
```

Skills in actions or confirm_action:
- {"type": "mark_done"}
- {"type": "delete_current"}
- {"type": "postpone", "minutes": 30}
- {"type": "reschedule", "due_at": "2026-06-21T10:00:00"}
- {"type": "update_schedule", "title": "...", "description": "..."}
- {"type": "create_schedule", "title": "...", "description": "...", "due_at": "2026-06-21T10:00:00"}
- {"type": "save_memory", "subject": "...", "note": "..."}
- {"type": "open_chat"}
'''

def visible_text(buf: str) -> str:
    txt = buf
    match = re.search(r'```json[\s\S]*?```', txt)
    if match:
        txt = txt[:match.start()] + txt[match.end():]
    else:
        idx = txt.find('```json')
        if idx != -1:
            txt = txt[:idx]
    match_json = re.search(r'\{[\s\S]{0,100}?"(?:actions|buttons)"', txt)
    if match_json:
        txt = txt[:match_json.start()]
    return txt.strip()

def parse_skills_json(text: str) -> dict | None:
    data = None
    match = re.search(r'```json\s*(\{[\s\S]*?\})\s*```', text)
    if match:
        try:
            data = json.loads(match.group(1))
        except Exception:
            pass
    if data:
        return data
    start = text.find('{')
    if start != -1 and ('"actions"' in text or '"buttons"' in text):
        depth = 0
        end = start
        for idx in range(start, len(text)):
            if text[idx] == '{':
                depth += 1
            elif text[idx] == '}':
                depth -= 1
            if depth == 0:
                end = idx + 1
                break
        try:
            data = json.loads(text[start:end])
        except Exception:
            pass
    return data

def _agenda_context_block() -> str:
    from core.scheduler import ScheduleManager
    all_scheds = ScheduleManager.get_instance().get_all()
    if not all_scheds:
        return '\n## CURRENT AGENDA: No pending reminders.\n'
    lines = '\n## CURRENT AGENDA (pending reminders):\n'
    for s in all_scheds:
        desc = s.get('description') or ''
        extra = f' | {desc[:60]}' if desc else ''
        lines += f"- ID {s['id']}: {s['title']} — {s['due_at']}{extra}\n"
    return lines

def build_chat_agenda_prompt(now: str) -> str:
    return _CHAT_SKILLS_DOC + _agenda_context_block() + f'\n- Current date/time: {now}\n- Timezone: Brazil (UTC-3)\n'

def build_notification_system_prompt(item: dict) -> str:
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    title = item.get('title', 'Reminder')
    desc = item.get('description', '')
    due = item.get('due_at', '')
    sid = item.get('id', '')
    doc = _NOTIFICATION_SKILLS_DOC
    context = (
        f'\n## CURRENT REMINDER (IN FOCUS)\n- ID: {sid}\n- Title: {title}\n- Description: {desc or "(none)"}\n- Time: {due}\n'
    )
    return doc + _agenda_context_block() + context + f'\n- Current date/time: {now}\n- Timezone: Brazil (UTC-3)\n'

def _normalize_title(text: str) -> str:
    text = text.lower().strip()
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r'[^\w\s]', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()

def _title_similarity(a: str, b: str) -> float:
    na, nb = _normalize_title(a), _normalize_title(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return 0.9
    wa, wb = set(na.split()), set(nb.split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / max(len(wa), len(wb))

def find_similar_schedules(title: str, threshold: float = 0.55) -> list[dict]:
    from core.scheduler import ScheduleManager
    matches = []
    for s in ScheduleManager.get_instance().get_all():
        score = _title_similarity(title, s.get('title', ''))
        if score >= threshold:
            matches.append({**s, '_similarity': score})
    matches.sort(key=lambda x: (-x['_similarity'], x.get('due_at', '')))
    return matches

def _schedule_exists(schedule_id: str) -> bool:
    if schedule_id is None:
        return False
    try:
        sid = int(schedule_id)
    except Exception:
        return False
    from core.scheduler import ScheduleManager
    return any(int(s.get('id')) == sid for s in ScheduleManager.get_instance().get_all())

def _action_references_existing_schedule(action: dict, user_text: str = '', item: dict | None = None) -> bool:
    action = normalize_action_type(action)
    atype = action.get('type')
    if atype in _EXISTING_SCHEDULE_OPS:
        return resolve_schedule_id(action, user_text, item) is not None
    return _schedule_exists(action.get('schedule_id'))

def _sanitize_button_action(action: list | dict, user_text: str = '', item: dict | None = None) -> list | dict | None:
    if isinstance(action, list):
        clean = []
        for item_action in action:
            if isinstance(item_action, dict):
                item_action = normalize_action(item_action, user_text)
                if _action_references_existing_schedule(item_action, user_text, item):
                    clean.append(item_action)
        return clean or None
    if isinstance(action, dict):
        action = normalize_action(action, user_text)
        if _action_references_existing_schedule(action, user_text, item):
            return action
    return None

def _format_due_short(due_str: str) -> str:
    try:
        return datetime.fromisoformat(due_str).strftime('%d/%m %H:%M')
    except Exception:
        return due_str or '?'

def _parse_time_from_text(user_text: str) -> tuple[int, int] | None:
    low = user_text.lower()
    match = re.search(r'(?:às|as|para as|para às)\s*(\d{1,2})(?::|h)?(\d{2})?', low)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return hour, minute
    return None

def _normalize_due_at_for_text(due_at: str, user_text: str) -> str:
    if not due_at:
        return due_at
    low = user_text.lower()
    now = datetime.now()
    try:
        dt = datetime.fromisoformat(due_at)
    except Exception:
        return due_at
    rel = re.search(r'daqui\s+(\d+)\s*(minuto|minutos|min|hora|horas|h)\b', low)
    if rel:
        amount = int(rel.group(1))
        unit = rel.group(2)
        if unit.startswith('hora') or unit == 'h':
            return (now + timedelta(hours=amount)).isoformat()
        return (now + timedelta(minutes=amount)).isoformat()
    explicit_time = _parse_time_from_text(user_text)
    if 'hoje' in low or 'dia de hoje' in low:
        hour, minute = explicit_time or (dt.hour, dt.minute)
        return dt.replace(year=now.year, month=now.month, day=now.day, hour=hour, minute=minute).isoformat()
    if 'amanhã' in low or 'amanha' in low:
        target = now + timedelta(days=1)
        hour, minute = explicit_time or (dt.hour, dt.minute)
        return dt.replace(year=target.year, month=target.month, day=target.day, hour=hour, minute=minute).isoformat()
    today_hint = re.search(r'hoje\s+(?:é|e)\s+dia\s+(\d{1,2})', low)
    if today_hint:
        day = int(today_hint.group(1))
        if day == now.day:
            hour, minute = explicit_time or (dt.hour, dt.minute)
            return dt.replace(year=now.year, month=now.month, day=now.day, hour=hour, minute=minute).isoformat()
    return due_at

def normalize_action_dates(action: dict, user_text: str) -> dict:
    if not isinstance(action, dict):
        return action
    atype = action.get('type')
    if atype not in {'update_schedule', 'create_schedule', 'reschedule'}:
        return action
    if 'due_at' not in action:
        return action
    fixed = dict(action)
    fixed['due_at'] = _normalize_due_at_for_text(str(action.get('due_at', '')), user_text)
    return fixed

def expand_chat_buttons(buttons: list[dict], user_text: str = '') -> list[dict]:
    expanded = []
    for btn in buttons:
        action = btn.get('confirm_action')
        if not action and 'action' in btn:
            action = {'type': btn['action']}
        if isinstance(action, list) or (action and action.get('type') != 'create_schedule'):
            clean_action = _sanitize_button_action(action, user_text)
            if clean_action:
                expanded.append({**btn, 'confirm_action': clean_action})
            continue
        action = normalize_action(action, user_text)
        title = action.get('title', '')
        similar = find_similar_schedules(title)
        if not similar:
            expanded.append({**btn, 'confirm_action': action})
            continue
        best = similar[0]
        new_due = _format_due_short(action.get('due_at', ''))
        old_due = _format_due_short(best.get('due_at', ''))
        expanded.append({
            'label': f'Atualizar existente ({old_due} → {new_due})',
            'confirm_action': {
                'type': 'update_schedule',
                'schedule_id': best['id'],
                'title': action.get('title', best['title']),
                'description': action.get('description') or best.get('description', ''),
                'due_at': action.get('due_at', '')
            }
        })
        expanded.append({
            'label': 'Criar lembrete novo',
            'confirm_action': action
        })
    return expanded[:3]

def augment_ai_text_for_duplicates(text: str) -> str:
    data = parse_skills_json(text)
    if not data:
        return text
    hints = []
    for btn in data.get('buttons', []):
        action = btn.get('confirm_action') or {}
        if action.get('type') != 'create_schedule':
            continue
        similar = find_similar_schedules(action.get('title', ''))
        if not similar:
            continue
        best = similar[0]
        old_due = _format_due_short(best.get('due_at', ''))
        hints.append(f'Já existe um lembrete parecido: "{best["title"]}" ({old_due}). Escolha abaixo se quer atualizar o existente ou criar um novo.')
    if not hints:
        return text
    visible = visible_text(text)
    hint = hints[0]
    if hint in visible or 'lembrete parecido' in visible.lower() or 'já existe' in visible.lower():
        return text
    return f'{visible}\n\n{hint}' + (text[len(visible):] if len(text) > len(visible) else '')

def commit_schedule(title: str, description: str, due_at: datetime, source: str) -> int:
    from core.scheduler import ScheduleManager
    from core.database import SeqDB
    if due_at is None:
        due_at = datetime.now() + timedelta(hours=1)
    sid = ScheduleManager.get_instance().add(title=title, description=description, due_at=due_at, source=source)
    preview = f'Agendado para {due_at.strftime("%d/%m/%Y %H:%M")}'
    if description:
        preview = f'{description} — {preview}'
    SeqDB.get_instance().save_item(
        subject=f'Agenda: {title}',
        body_preview=preview,
        source='manual',
        is_important=True
    )
    trigger_ui_update()
    QTimer.singleShot(1000, trigger_ui_update)
    return sid

def trigger_ui_update():
    for w in QApplication.topLevelWidgets():
        brain = getattr(w, '_brain', None)
        if brain and hasattr(brain, 'agenda_tab'):
            brain.agenda_tab.refresh()
        if brain and hasattr(brain, 'graph_tab'):
            brain.graph_tab.refresh()
        settings = getattr(w, '_settings', None)
        if settings and hasattr(settings, 'memory_tab_widget'):
            settings.memory_tab_widget.refresh()
        if hasattr(w, 'memory_tab_widget'):
            w.memory_tab_widget.refresh()
        checker = getattr(w, '_schedule_checker', None)
        if checker:
            checker.force_check()

def _schedule_dialog_close(dialog, delay_ms: int = 1500):
    if dialog and hasattr(dialog, '_close'):
        QTimer.singleShot(delay_ms, dialog._close)

def _maybe_close_after(dialog, action: dict, result: str, delay_ms: int = 1500):
    if action.get('type') in _CLOSING_ACTIONS and not result.startswith('❌'):
        _schedule_dialog_close(dialog, delay_ms)

class AgendaSkillExecutor:
    """Executa skills de agenda. Modo chat (sem item) ou notificação (com item)."""

    def __init__(self, item: dict | None = None, dialog=None):
        self._item = item
        self._dialog = dialog
        self._user_text = ''

    def execute(self, action: dict, user_text: str = '') -> str:
        if user_text:
            self._user_text = user_text
        action = normalize_action(action, self._user_text)
        atype = action.get('type', '')
        try:
            if atype == 'mark_done':
                return self._mark_done(action)
            if atype in ('delete_current', 'delete_schedule'):
                return self._delete(action)
            if atype == 'postpone':
                return self._postpone(action)
            if atype == 'reschedule':
                return self._reschedule(action)
            if atype == 'create_schedule':
                return self._create_schedule(action)
            if atype == 'update_schedule':
                return self._update_schedule(action)
            if atype == 'save_memory':
                return self._save_memory(action)
            if atype == 'open_chat':
                return self._open_chat()
            return f'Skill desconhecida: {atype}'
        except Exception as e:
            return f"❌ Erro ao executar '{atype}': {e}"

    def _schedule_id(self, action: dict) -> int | None:
        return resolve_schedule_id(action, self._user_text, self._item)

    def _mark_done(self, action: dict) -> str:
        from core.scheduler import ScheduleManager
        sid = self._schedule_id(action)
        if sid is None:
            return '❌ Informe o schedule_id do lembrete.'
        ScheduleManager.get_instance().mark_done(sid)
        trigger_ui_update()
        result = '✅ Lembrete marcado como concluído.'
        _maybe_close_after(self._dialog, action, result)
        return result

    def _delete(self, action: dict) -> str:
        from core.scheduler import ScheduleManager
        sid = self._schedule_id(action)
        if sid is None:
            return '❌ Informe o schedule_id do lembrete.'
        ScheduleManager.get_instance().delete(sid)
        trigger_ui_update()
        result = 'Lembrete cancelado.'
        _maybe_close_after(self._dialog, action, result)
        return result

    def _postpone(self, action: dict) -> str:
        from core.scheduler import ScheduleManager
        sid = self._schedule_id(action)
        if sid is None:
            return '❌ Informe o schedule_id do lembrete.'
        minutes = int(action.get('minutes', 30))
        ScheduleManager.get_instance().postpone(sid, minutes)
        if minutes < 60:
            label = f'{minutes} min'
        elif minutes < 1440:
            label = f'{minutes // 60}h'
        else:
            label = f'{minutes // 1440}d'
        trigger_ui_update()
        result = f'⏳ Adiado por {label}.'
        _maybe_close_after(self._dialog, action, result)
        return result

    def _reschedule(self, action: dict) -> str:
        from core.scheduler import ScheduleManager, parse_due_at, format_due_at
        sid = self._schedule_id(action)
        due_str = action.get('due_at', '')
        try:
            new_dt = parse_due_at(due_str)
        except Exception:
            return f'❌ Data inválida: {due_str}'
        if sid is None:
            return '❌ Informe o schedule_id do lembrete.'
        mgr = ScheduleManager.get_instance()
        mgr.update(sid, due_at=new_dt)
        trigger_ui_update()
        formatted = new_dt.strftime('%d/%m às %H:%M')
        result = f'Remarcado para {formatted}.'
        _maybe_close_after(self._dialog, action, result)
        return result

    def _create_schedule(self, action: dict) -> str:
        from core.scheduler import parse_due_at
        title = action.get('title', 'Novo lembrete')
        desc = action.get('description', '')
        due_str = action.get('due_at', '')
        try:
            if due_str:
                due_dt = parse_due_at(due_str)
            else:
                due_dt = datetime.now() + timedelta(hours=1)
        except Exception:
            due_dt = datetime.now() + timedelta(hours=1)
        commit_schedule(title=title, description=desc, due_at=due_dt, source='ai')
        formatted = due_dt.strftime('%d/%m às %H:%M')
        return f'✅ Lembrete criado: "{title}" — {formatted}'

    def _update_schedule(self, action: dict) -> str:
        from core.scheduler import ScheduleManager, parse_due_at
        sid = self._schedule_id(action)
        if sid is None:
            return '❌ Não achei qual lembrete atualizar. Informe o schedule_id ou seja mais específico.'
        mgr = ScheduleManager.get_instance()
        existing = next((s for s in mgr.get_all() if int(s['id']) == int(sid)), None)
        if not existing:
            return f'❌ Lembrete #{sid} não encontrado.'
        title = action.get('title') if 'title' in action else None
        desc = action.get('description') if 'description' in action else None
        due_str = action.get('due_at', '')
        due_dt = None
        if due_str:
            try:
                due_dt = parse_due_at(due_str)
            except Exception:
                return f'❌ Data inválida: {due_str}'
        if title is None and desc is None and due_dt is None:
            return '❌ Nada para atualizar — informe título, descrição ou horário.'
        mgr.update(sid, title=title, description=desc, due_at=due_dt)
        trigger_ui_update()
        display_title = title if title is not None else existing.get('title', 'lembrete')
        if due_dt:
            formatted = due_dt.strftime('%d/%m às %H:%M')
            return f'✅ Lembrete atualizado: "{display_title}" — {formatted}'
        parts = []
        if title is not None:
            parts.append('título')
        if desc is not None:
            parts.append('descrição')
        if due_dt is not None:
            parts.append('horário')
        return f'✅ Lembrete atualizado ({", ".join(parts)}): "{display_title}".'

    def _save_memory(self, action: dict) -> str:
        from core.database import SeqDB
        subject = action.get('subject') or (self._item.get('title') if self._item else 'Nota')
        note = action.get('note', '')
        category = action.get('category') or 'general'
        category = category.strip().lower()
        source = 'persona' if category == 'persona' else 'manual'
        try:
            relevance = int(action.get('relevance_score', 80 if category == 'persona' else 65))
        except Exception:
            relevance = 80 if category == 'persona' else 65
        SeqDB.get_instance().save_important({
            'id': str(uuid.uuid4()),
            'source': source,
            'subject': subject,
            'sender': '',
            'body_preview': note,
            'ai_summary': subject,
            'ai_reason': f'Memória relevante capturada pelo Nigel ({category})',
            'relevance_score': max(1, min(100, relevance)),
        }, saved_by='user')
        trigger_ui_update()
        if source == 'persona':
            return f'Persona atualizada: "{subject}".'
        return f'Memória salva: "{subject}".'

    def _open_chat(self) -> str:
        for w in QApplication.topLevelWidgets():
            if hasattr(w, '_expand'):
                w._expand()
                break
        return 'Chat aberto.'
