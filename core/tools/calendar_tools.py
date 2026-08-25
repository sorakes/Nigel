"""
core/tools/calendar_tools.py — Ferramentas de Google Calendar expostas ao agente.

Wrappers curados em cima dos slugs do Composio. Curados, e não descoberta
dinâmica, por orçamento de token: só `GOOGLECALENDAR_CREATE_EVENT` tem 13,9 KB
de schema e `PATCH_EVENT` 16,6 KB — e existem 49 ferramentas de calendário.
Os schemas abaixo têm ~600 caracteres cada.

Duas correções estruturais em relação ao código anterior:

1. Toda leitura devolve `event_id` E um handle curto (`ref`). Antes o
   `list_calendar` formatava só `summary` + `start` e descartava o id, então o
   modelo listava um evento e não tinha como referenciá-lo — por isso cancelar
   e mover nunca funcionaram.

2. Edições usam `GOOGLECALENDAR_PATCH_EVENT` (required: calendar_id, event_id)
   e não `UPDATE_EVENT` (required: start_datetime, event_id). Era esse required
   que forçava o antigo `start_datetime = now()`, e fazia editar só o título
   mover o evento para agora.
"""

from __future__ import annotations

import unicodedata
from datetime import datetime, timedelta

from core.agent.registry import Tool, ToolResult, ok, fail
from core.llm.types import ToolSpec
from core.tools import composio_exec as cx
from core.tools.tz import user_timezone

TOOLKIT = 'googlecalendar'
_HUMAN = 'Google Calendar'


# --------------------------------------------------------------------------- utils

def _dur(minutes: int) -> dict:
    """Divide minutos em hora+minuto. O código antigo travava em
    `min(59, minutes)`, então uma reunião de 2h virava 59 minutos calada."""
    m = max(1, int(minutes or 30))
    h, mm = divmod(m, 60)
    out = {}
    if h:
        out['event_duration_hour'] = h
    out['event_duration_minutes'] = mm
    if not h and not mm:
        out['event_duration_minutes'] = 30
    return out


def _iso(value, default=None):
    if value in (None, ''):
        return default
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%dT%H:%M:%S')
    s = str(value).strip().replace('Z', '')
    try:
        return datetime.fromisoformat(s).strftime('%Y-%m-%dT%H:%M:%S')
    except ValueError:
        return s


def _fold(text: str) -> str:
    """Minusculas sem acento, para casar 'Joao' com 'Joao'/'JOAO'."""
    if not text:
        return ''
    return unicodedata.normalize('NFKD', str(text)).encode('ascii', 'ignore').decode().lower()


def _rfc(value, default=None) -> str | None:
    """ISO 8601 COM offset de fuso.

    Sem offset explicito o Google interpreta a hora como UTC — era essa a causa
    de um evento pedido para as 14h aparecer as 11h para quem esta em UTC-3.
    Entrada sem fuso e' tratada como hora LOCAL do usuario; entrada com fuso
    (inclusive 'Z') e' convertida para o fuso local, preservando o instante.
    """
    raw = value if value not in (None, '') else default
    if raw in (None, ''):
        return None
    if isinstance(raw, datetime):
        dt = raw
    else:
        txt = str(raw).strip()
        if txt.endswith('Z'):
            txt = txt[:-1] + '+00:00'
        try:
            dt = datetime.fromisoformat(txt)
        except ValueError:
            return str(raw)
    if dt.tzinfo is None:
        dt = dt.astimezone()          # assume hora local do usuario
    else:
        dt = dt.astimezone()          # converte para local, mesmo instante
    return dt.strftime('%Y-%m-%dT%H:%M:%S%z')[:-2] + ':' + dt.strftime('%z')[-2:]


_LIST_KEYS = ('items', 'events', 'event_data', 'data', 'value')


def _items(data) -> list:
    """Extrai a lista de eventos.

    O FIND_EVENT aninha em `event_data.event_data` (um dict cuja unica chave
    repete o nome), e nao em `items` como as demais — por isso a busca voltava
    sempre vazia mesmo com a chamada dando sucesso.
    """
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in _LIST_KEYS:
        v = data.get(key)
        if isinstance(v, list):
            return v
        if isinstance(v, dict):
            for inner in _LIST_KEYS:
                iv = v.get(inner)
                if isinstance(iv, list):
                    return iv
    return [data] if data.get('id') else []


def _shape(ev: dict, ctx) -> dict:
    """Normaliza um evento e registra seu handle curto."""
    start = ev.get('start') or {}
    end = ev.get('end') or {}
    if isinstance(start, dict):
        start = start.get('dateTime') or start.get('date') or ''
    if isinstance(end, dict):
        end = end.get('dateTime') or end.get('date') or ''
    eid = str(ev.get('id') or ev.get('event_id') or '')
    cal = str(ev.get('calendar_id') or 'primary')
    out = {
        'ref': ctx.event_refs.put(eid, cal) if (ctx and eid) else '',
        'event_id': eid,
        'summary': ev.get('summary') or '(sem titulo)',
        'start': start,
        'end': end,
    }
    if ev.get('location'):
        out['location'] = ev['location']
    if ev.get('description'):
        out['description'] = str(ev['description'])[:200]
    att = ev.get('attendees')
    if isinstance(att, list) and att:
        out['attendees'] = [a.get('email') for a in att if isinstance(a, dict) and a.get('email')][:10]
    if ev.get('recurringEventId'):
        out['recurring'] = True
    if ev.get('status') and ev['status'] != 'confirmed':
        out['status'] = ev['status']      # 'cancelled' apos remocao
    return out


def _resolve(args: dict, ctx) -> tuple[str, str] | None:
    token = args.get('ref') or args.get('event_id')
    return ctx.event_refs.resolve(token) if token else None


# --------------------------------------------------------------------------- leitura

def _find_events(args, ctx) -> ToolResult:
    """Busca por texto.

    Montado sobre EVENTS_LIST (que aceita `q`) e nao sobre FIND_EVENT: este
    ultimo ignorava a janela de tempo na pratica e devolvia apenas os proximos
    eventos a partir de agora, entao um compromisso a meses de distancia nunca
    era encontrado — que era exatamente o caso de "cancela a reuniao com o Joao".
    """
    cx.require_connected(TOOLKIT, _HUMAN)
    now = datetime.now()
    query = (args.get('query') or '').strip()

    t_min = _rfc(args.get('time_min')) or _rfc(now - timedelta(days=1))
    if args.get('time_max'):
        t_max = _rfc(args['time_max'])
    else:
        # Sem limite informado, procura amplo: o alvo pode estar meses a frente.
        t_max = _rfc(now + timedelta(days=540 if query else 30))

    payload = {
        'calendarId': args.get('calendar_id') or 'primary',
        'maxResults': min(int(args.get('max_results') or 15), 50),
        'timeMin': t_min,
        'timeMax': t_max,
        'singleEvents': True,
        'orderBy': 'startTime',
    }
    def _run(extra: dict | None = None, drop_q: bool = False):
        p = dict(payload)
        if extra:
            p.update(extra)
        if drop_q:
            p.pop('q', None)
        raw = cx.execute('GOOGLECALENDAR_EVENTS_LIST', p)
        got = [_shape(e, ctx) for e in _items(raw) if isinstance(e, dict)]
        return [e for e in got if e.get('status') != 'cancelled'], raw

    events, _ = _run({'q': query} if query else None)

    if not events and query:
        # O `q` do Google e' irregular com acentos e nomes proprios: tenta a
        # forma sem acento antes de partir para a varredura local.
        folded = _fold(query)
        if folded != query.lower():
            events, _ = _run({'q': folded})

    if not events and query:
        # Varredura local paginada. Sem paginar, so os ~50 primeiros eventos
        # cronologicos eram vistos, e um compromisso a mais de um ano de
        # distancia nunca aparecia numa agenda movimentada.
        termos = [t for t in _fold(query).split() if len(t) > 2]
        page, token = 0, None
        while termos and page < 6:
            extra = {'maxResults': 250}
            if token:
                extra['pageToken'] = token
            # sem `q`: o filtro do Google e' justamente o que esta falhando aqui
            _, raw = _run(extra, drop_q=True)
            for e in _items(raw):
                if not isinstance(e, dict) or e.get('status') == 'cancelled':
                    continue
                blob = _fold(' '.join(str(e.get(k) or '')
                                      for k in ('summary', 'description', 'location')))
                if any(t in blob for t in termos):
                    events.append(_shape(e, ctx))
            token = raw.get('nextPageToken') if isinstance(raw, dict) else None
            page += 1
            if not token or events:
                break

    if not events:
        return ok({'events': [], 'note': f'nenhum evento encontrado para "{query}" no periodo'},
                  user_message='Nenhum evento encontrado')
    return ok({'events': events[:20], 'count': len(events)},
              user_message=f'{len(events)} evento(s) encontrado(s)')


def _list_events(args, ctx) -> ToolResult:
    cx.require_connected(TOOLKIT, _HUMAN)
    now = datetime.now()
    t_min = _iso(args.get('time_min'), now.strftime('%Y-%m-%dT00:00:00'))
    days = int(args.get('days') or 7)
    t_max = _iso(args.get('time_max'), (now + timedelta(days=days)).strftime('%Y-%m-%dT23:59:59'))
    data = cx.execute('GOOGLECALENDAR_EVENTS_LIST', {
        'calendarId': args.get('calendar_id') or 'primary',
        'maxResults': min(int(args.get('max_results') or 25), 50),
        'timeMin': t_min + 'Z' if len(t_min) == 19 else t_min,
        'timeMax': t_max + 'Z' if len(t_max) == 19 else t_max,
        'singleEvents': True,
        'orderBy': 'startTime',
    })
    events = [_shape(e, ctx) for e in _items(data) if isinstance(e, dict)]
    return ok({'events': events, 'count': len(events), 'from': t_min, 'to': t_max},
              user_message=f'{len(events)} compromisso(s) no periodo')


def _get_event(args, ctx) -> ToolResult:
    cx.require_connected(TOOLKIT, _HUMAN)
    target = _resolve(args, ctx)
    if not target:
        return fail(cx.BAD_ARGS, 'informe `ref` (ex. e1) ou `event_id`')
    cal, eid = target
    data = cx.execute('GOOGLECALENDAR_EVENTS_GET', {'calendar_id': cal, 'event_id': eid})
    ev = data if isinstance(data, dict) and data.get('id') else (_items(data) or [{}])[0]
    return ok(_shape(ev, ctx), user_message='Detalhes do evento')


def _list_calendars(args, ctx) -> ToolResult:
    cx.require_connected(TOOLKIT, _HUMAN)
    data = cx.execute('GOOGLECALENDAR_LIST_CALENDARS', {})
    cals = [{'id': c.get('id'), 'name': c.get('summary'), 'primary': bool(c.get('primary'))}
            for c in _items(data) if isinstance(c, dict)]
    return ok({'calendars': cals}, user_message=f'{len(cals)} agenda(s)')


def _find_free(args, ctx) -> ToolResult:
    cx.require_connected(TOOLKIT, _HUMAN)
    now = datetime.now()
    payload = {
        'time_min': _iso(args.get('range_start'), now.strftime('%Y-%m-%dT%H:%M:%S')),
        'time_max': _iso(args.get('range_end'),
                         (now + timedelta(days=int(args.get('days') or 7))).strftime('%Y-%m-%dT%H:%M:%S')),
    }
    if args.get('duration_minutes'):
        payload['duration_minutes'] = int(args['duration_minutes'])
    payload['timezone'] = user_timezone()
    data = cx.execute('GOOGLECALENDAR_FIND_FREE_SLOTS', payload)
    return ok(data, user_message='Horarios livres consultados')


def _check_conflicts(args, ctx) -> ToolResult:
    cx.require_connected(TOOLKIT, _HUMAN)
    start = _iso(args.get('start'))
    if not start:
        return fail(cx.BAD_ARGS, '`start` e obrigatorio (ISO 8601)')
    end = _iso(args.get('end')) or (
        datetime.fromisoformat(start) + timedelta(minutes=int(args.get('duration_minutes') or 30))
    ).strftime('%Y-%m-%dT%H:%M:%S')
    cals = args.get('calendars') or ['primary']
    data = cx.execute('GOOGLECALENDAR_FREE_BUSY_QUERY', {
        'timeMin': _rfc(start), 'timeMax': _rfc(end),
        'items': cals if isinstance(cals, list) else [cals],
        'timeZone': user_timezone(),
    })
    return ok(data, user_message='Conflitos verificados')


# --------------------------------------------------------------------------- escrita

def _create_event(args, ctx) -> ToolResult:
    cx.require_connected(TOOLKIT, _HUMAN)
    title = (args.get('title') or '').strip()
    start = _iso(args.get('start'))
    if not title:
        return fail(cx.BAD_ARGS, '`title` e obrigatorio')
    if not start:
        return fail(cx.BAD_ARGS, '`start` e obrigatorio (ISO 8601, ex. 2026-08-23T14:00:00)')

    payload = {
        'summary': title,
        'start_datetime': start,
        'calendar_id': args.get('calendar_id') or 'primary',
        # Sem isto o Composio assume UTC e o evento nasce deslocado do fuso do usuario.
        'timezone': args.get('timezone') or user_timezone(),
    }
    if args.get('end'):
        payload['end_datetime'] = _iso(args['end'])
    else:
        payload.update(_dur(args.get('duration_minutes') or 30))
    if args.get('description'):
        payload['description'] = args['description']
    if args.get('location'):
        payload['location'] = args['location']
    if args.get('attendees'):
        att = args['attendees']
        payload['attendees'] = att if isinstance(att, list) else [att]
        payload['send_updates'] = 'all'
    if args.get('recurrence'):
        rec = args['recurrence']
        payload['recurrence'] = rec if isinstance(rec, list) else [rec]

    data = cx.execute('GOOGLECALENDAR_CREATE_EVENT', payload)
    ev = data if isinstance(data, dict) else {}
    inner = ev.get('response_data') if isinstance(ev.get('response_data'), dict) else ev
    eid = str(inner.get('id') or inner.get('event_id') or '')
    ref = ctx.event_refs.put(eid, payload['calendar_id']) if (ctx and eid) else ''
    return ok({'created': True, 'ref': ref, 'event_id': eid,
               'summary': title, 'start': start,
               'link': inner.get('htmlLink', '')},
              user_message=f'Evento criado: {title}')


def _patch(args, ctx, fields: dict, msg: str) -> ToolResult:
    cx.require_connected(TOOLKIT, _HUMAN)
    target = _resolve(args, ctx)
    if not target:
        return fail(cx.BAD_ARGS, 'informe `ref` (ex. e1) ou `event_id`. Use calendar_find_events antes.')
    cal, eid = target
    # PATCH_EVENT exige apenas calendar_id + event_id: só vai o que foi informado.
    payload = {'calendar_id': cal, 'event_id': eid}
    payload.update({k: v for k, v in fields.items() if v not in (None, '')})
    if 'start_time' in payload or 'end_time' in payload:
        payload['timezone'] = user_timezone()
        base = len(payload) - 1
    else:
        base = len(payload)
    if base == 2:
        return fail(cx.BAD_ARGS, 'nada para alterar: informe ao menos um campo')
    cx.execute('GOOGLECALENDAR_PATCH_EVENT', payload)
    return ok({'updated': True, 'event_id': eid, 'changed': [k for k in payload if k not in ('calendar_id', 'event_id')]},
              user_message=msg)


def _update_event(args, ctx) -> ToolResult:
    return _patch(args, ctx, {
        'summary': args.get('title'),
        'description': args.get('description'),
        'location': args.get('location'),
    }, 'Evento atualizado')


def _reschedule_event(args, ctx) -> ToolResult:
    start = _iso(args.get('start'))
    if not start:
        return fail(cx.BAD_ARGS, '`start` e obrigatorio (novo horario ISO 8601)')
    end = _iso(args.get('end'))
    if not end:
        mins = int(args.get('duration_minutes') or 60)
        try:
            end = (datetime.fromisoformat(start) + timedelta(minutes=mins)).strftime('%Y-%m-%dT%H:%M:%S')
        except ValueError:
            end = None
    return _patch(args, ctx, {'start_time': start, 'end_time': end}, 'Evento remarcado')


def _delete_event(args, ctx) -> ToolResult:
    cx.require_connected(TOOLKIT, _HUMAN)
    target = _resolve(args, ctx)
    if not target:
        return fail(cx.BAD_ARGS, 'informe `ref` (ex. e1) ou `event_id`. Use calendar_find_events antes.')
    cal, eid = target
    cx.execute('GOOGLECALENDAR_DELETE_EVENT', {'calendar_id': cal, 'event_id': eid})
    return ok({'deleted': True, 'event_id': eid}, user_message='Evento cancelado')


# --------------------------------------------------------------------------- specs

def _obj(props: dict, required: list[str] | None = None) -> dict:
    schema = {'type': 'object', 'properties': props}
    if required:
        schema['required'] = required
    return schema

_REF = {'type': 'string', 'description': 'handle curto devolvido pela busca (ex. e1); prefira este ao event_id'}
_EVID = {'type': 'string', 'description': 'id cru do evento no Google (use `ref` quando tiver)'}
_CAL = {'type': 'string', 'description': "id da agenda; 'primary' por padrao"}


def build_tools() -> list[Tool]:
    return [
        Tool(ToolSpec('calendar_find_events',
             'Busca eventos na agenda por texto (nome de pessoa, assunto) e periodo. '
             'Use SEMPRE antes de remarcar ou cancelar: devolve o `ref` de cada evento.',
             _obj({'query': {'type': 'string', 'description': 'texto livre, ex. "Joao" ou "dentista"'},
                   'time_min': {'type': 'string', 'description': 'inicio do periodo, ISO 8601'},
                   'time_max': {'type': 'string', 'description': 'fim do periodo, ISO 8601'},
                   'max_results': {'type': 'integer'},
                   'calendar_id': _CAL}),
             parallel_safe=True), _find_events, label='Buscando na agenda', icon='brand_gcal'),

        Tool(ToolSpec('calendar_list_events',
             'Lista os compromissos de um periodo (padrao: proximos 7 dias). '
             'Para "o que tenho amanha" prefira esta; para achar um evento especifico use calendar_find_events.',
             _obj({'time_min': {'type': 'string', 'description': 'ISO 8601'},
                   'time_max': {'type': 'string', 'description': 'ISO 8601'},
                   'days': {'type': 'integer', 'description': 'janela em dias a partir de agora'},
                   'max_results': {'type': 'integer'},
                   'calendar_id': _CAL}),
             parallel_safe=True), _list_events, label='Consultando a agenda', icon='brand_gcal'),

        Tool(ToolSpec('calendar_get_event',
             'Detalhes completos de um evento, incluindo participantes.',
             _obj({'ref': _REF, 'event_id': _EVID}), parallel_safe=True),
             _get_event, label='Lendo evento', icon='brand_gcal'),

        Tool(ToolSpec('calendar_list_calendars',
             'Lista as agendas disponiveis do usuario.', _obj({}), parallel_safe=True),
             _list_calendars, label='Listando agendas', icon='brand_gcal'),

        Tool(ToolSpec('calendar_find_free_slots',
             'Encontra horarios livres para encaixar um compromisso.',
             _obj({'duration_minutes': {'type': 'integer'},
                   'range_start': {'type': 'string', 'description': 'ISO 8601'},
                   'range_end': {'type': 'string', 'description': 'ISO 8601'},
                   'days': {'type': 'integer'}}), parallel_safe=True),
             _find_free, label='Procurando horario livre', icon='brand_gcal'),

        Tool(ToolSpec('calendar_check_conflicts',
             'Verifica se um horario ja esta ocupado antes de agendar.',
             _obj({'start': {'type': 'string', 'description': 'ISO 8601'},
                   'end': {'type': 'string', 'description': 'ISO 8601'},
                   'duration_minutes': {'type': 'integer'}}, ['start']), parallel_safe=True),
             _check_conflicts, label='Verificando conflitos', icon='brand_gcal'),

        Tool(ToolSpec('calendar_create_event',
             'Cria um evento na agenda. Duracao pode passar de 1 hora sem problema.',
             _obj({'title': {'type': 'string'},
                   'start': {'type': 'string', 'description': 'ISO 8601, ex. 2026-08-23T14:00:00'},
                   'end': {'type': 'string', 'description': 'ISO 8601; alternativa a duration_minutes'},
                   'duration_minutes': {'type': 'integer', 'description': 'padrao 30; aceita 120, 480 etc.'},
                   'description': {'type': 'string'},
                   'location': {'type': 'string'},
                   'attendees': {'type': 'array', 'items': {'type': 'string'},
                                 'description': 'e-mails dos convidados'},
                   'recurrence': {'type': 'array', 'items': {'type': 'string'},
                                  'description': 'regras RRULE, ex. RRULE:FREQ=WEEKLY;BYDAY=MO'},
                   'calendar_id': _CAL}, ['title', 'start'])),
             _create_event, label='Criando evento', icon='brand_gcal'),

        Tool(ToolSpec('calendar_update_event',
             'Altera titulo, descricao ou local de um evento SEM mexer no horario.',
             _obj({'ref': _REF, 'event_id': _EVID,
                   'title': {'type': 'string'},
                   'description': {'type': 'string'},
                   'location': {'type': 'string'}})),
             _update_event, label='Atualizando evento', icon='brand_gcal'),

        Tool(ToolSpec('calendar_reschedule_event',
             'Move um evento para outro horario ou data (remarcar/adiar).',
             _obj({'ref': _REF, 'event_id': _EVID,
                   'start': {'type': 'string', 'description': 'novo inicio, ISO 8601'},
                   'end': {'type': 'string', 'description': 'novo fim, ISO 8601'},
                   'duration_minutes': {'type': 'integer'}}, ['start'])),
             _reschedule_event, label='Remarcando evento', icon='brand_gcal'),

        Tool(ToolSpec('calendar_delete_event',
             'Cancela/remove um evento da agenda. Busque antes para obter o `ref`.',
             _obj({'ref': _REF, 'event_id': _EVID})),
             _delete_event, label='Cancelando evento', icon='brand_gcal', requires_confirmation=False),
    ]
