"""
core/tools/schedule_tools.py — Lembretes e tarefas autônomas locais do Nigel.

Deliberadamente separado das ferramentas `calendar_*`: são coisas diferentes.
`schedule_*` é a agenda interna do Nigel (lembretes que abrem popup, checagem
de e-mail, briefing diário); `calendar_*` é o Google Calendar do usuário.

O prompt antigo misturava `create_schedule` e `create_calendar_event` sem
distinguir, e o modelo escolhia errado com frequência. Os nomes e as descrições
aqui deixam a diferença explícita.
"""

from __future__ import annotations

from datetime import datetime

from core.agent.registry import Tool, ToolResult, ok, fail
from core.llm.types import ToolSpec


def _mgr():
    from core.scheduler import ScheduleManager
    return ScheduleManager.get_instance()


def _parse(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).strip().replace('Z', ''))
    except ValueError:
        return None


def _row(r) -> dict:
    return {
        'schedule_id': r['id'],
        'titulo': r['title'],
        'quando': r['due_at'],
        'tipo': r['task_type'],
        'repete': r['repeat'],
        'concluido': bool(r['done']),
    }


def _list(args, ctx) -> ToolResult:
    rows = _mgr().get_all(include_done=bool(args.get('include_done')))
    items = [_row(r) for r in rows][:30]
    return ok({'lembretes': items, 'total': len(items)},
              user_message=f'{len(items)} lembrete(s)')


def _create(args, ctx) -> ToolResult:
    from core.scheduler import (TASK_REMINDER, TASK_CHECK_EMAILS,
                                TASK_DAILY_BRIEFING, TASK_AGENT_PROMPT)
    title = (args.get('title') or '').strip()
    if not title:
        return fail('BAD_ARGS', '`title` e obrigatorio')
    due = _parse(args.get('when'))
    if not due:
        return fail('BAD_ARGS', '`when` e obrigatorio (ISO 8601, ex. 2026-08-23T15:00:00)')

    tipo = (args.get('kind') or 'reminder').lower()
    tipo = {'reminder': TASK_REMINDER, 'check_emails': TASK_CHECK_EMAILS,
            'daily_briefing': TASK_DAILY_BRIEFING,
            'agent_prompt': TASK_AGENT_PROMPT}.get(tipo, TASK_REMINDER)

    payload = {}
    if args.get('prompt'):
        payload['prompt'] = args['prompt']

    sid = _mgr().add(title=title, description=args.get('description') or '',
                     due_at=due, task_type=tipo, payload=payload or None,
                     repeat=(args.get('repeat') or 'none'), source='chat')
    _refresh()
    return ok({'schedule_id': sid, 'titulo': title, 'quando': due.isoformat()},
              user_message=f'Lembrete criado: {title}')


def _update(args, ctx) -> ToolResult:
    sid = args.get('schedule_id')
    if not sid:
        return fail('BAD_ARGS', '`schedule_id` e obrigatorio (use schedule_list antes)')
    due = _parse(args.get('when'))
    _mgr().update(int(sid), title=args.get('title'),
                  description=args.get('description'), due_at=due,
                  repeat=args.get('repeat'))
    _forget(sid)
    _refresh()
    return ok({'atualizado': True, 'schedule_id': sid}, user_message='Lembrete atualizado')


def _done(args, ctx) -> ToolResult:
    sid = args.get('schedule_id')
    if not sid:
        return fail('BAD_ARGS', '`schedule_id` e obrigatorio')
    _mgr().mark_done(int(sid))
    _refresh()
    return ok({'concluido': True, 'schedule_id': sid}, user_message='Lembrete concluido')


def _postpone(args, ctx) -> ToolResult:
    sid = args.get('schedule_id')
    minutes = int(args.get('minutes') or 10)
    if not sid:
        return fail('BAD_ARGS', '`schedule_id` e obrigatorio')
    _mgr().postpone(int(sid), minutes)
    _forget(sid)
    _refresh()
    return ok({'adiado': True, 'schedule_id': sid, 'minutos': minutes},
              user_message=f'Adiado {minutes} min')


def _delete(args, ctx) -> ToolResult:
    sid = args.get('schedule_id')
    if not sid:
        return fail('BAD_ARGS', '`schedule_id` e obrigatorio')
    _mgr().delete(int(sid))
    _refresh()
    return ok({'removido': True, 'schedule_id': sid}, user_message='Lembrete removido')


def _forget(sid) -> None:
    try:
        from core.scheduler import forget_schedule_notification
        forget_schedule_notification(int(sid))
    except Exception:
        pass


def _refresh() -> None:
    try:
        from ui.agenda_skills import trigger_ui_update
        trigger_ui_update()
    except Exception:
        pass


def _obj(props, required=None):
    s = {'type': 'object', 'properties': props}
    if required:
        s['required'] = required
    return s

_SID = {'type': 'integer', 'description': 'id do lembrete, vindo de schedule_list'}


def build_tools() -> list[Tool]:
    return [
        Tool(ToolSpec('schedule_list',
             'Lista os lembretes e tarefas internas do Nigel. NAO e a agenda do Google '
             '(para isso use calendar_list_events).',
             _obj({'include_done': {'type': 'boolean'}}), parallel_safe=True),
             _list, label='Listando lembretes', icon='bell'),

        Tool(ToolSpec('schedule_create',
             'Cria um lembrete do Nigel, que abre um popup na hora marcada. Use para '
             '"me lembra de..."; para um compromisso real na agenda use calendar_create_event.',
             _obj({'title': {'type': 'string'},
                   'when': {'type': 'string', 'description': 'ISO 8601'},
                   'description': {'type': 'string'},
                   'repeat': {'type': 'string',
                              'enum': ['none', 'hourly', 'daily', 'weekdays', 'weekly']},
                   'kind': {'type': 'string',
                            'enum': ['reminder', 'check_emails', 'daily_briefing', 'agent_prompt'],
                            'description': 'reminder por padrao'},
                   'prompt': {'type': 'string',
                              'description': 'so para kind=agent_prompt: o que o Nigel deve fazer'}},
                  ['title', 'when'])),
             _create, label='Criando lembrete', icon='bell'),

        Tool(ToolSpec('schedule_update', 'Altera titulo, descricao, horario ou recorrencia de um lembrete.',
             _obj({'schedule_id': _SID, 'title': {'type': 'string'},
                   'description': {'type': 'string'},
                   'when': {'type': 'string', 'description': 'ISO 8601'},
                   'repeat': {'type': 'string'}}, ['schedule_id'])),
             _update, label='Atualizando lembrete', icon='bell'),

        Tool(ToolSpec('schedule_complete', 'Marca um lembrete como concluido.',
             _obj({'schedule_id': _SID}, ['schedule_id'])), _done, label='Concluindo', icon='bell'),

        Tool(ToolSpec('schedule_postpone', 'Adia um lembrete por N minutos.',
             _obj({'schedule_id': _SID, 'minutes': {'type': 'integer'}}, ['schedule_id'])),
             _postpone, label='Adiando', icon='bell'),

        Tool(ToolSpec('schedule_delete', 'Remove um lembrete.',
             _obj({'schedule_id': _SID}, ['schedule_id'])), _delete, label='Removendo lembrete', icon='bell'),
    ]
