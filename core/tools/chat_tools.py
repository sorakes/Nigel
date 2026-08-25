"""
core/tools/chat_tools.py — Ferramentas de Slack para o agente.

Antes, mensageria caía inteira no `apps_agent` genérico (descoberta dinâmica
via `search_app_tools`/`run_app_tool`), que funciona mas custa uma rodada
extra de busca de schema a cada chamada e não sabe de antemão os nomes de
canal/pessoa mais comuns. Um wrapper curado, no mesmo molde de
`calendar_tools.py`/`email_tools.py`, dá ao `chat_agent` ferramentas com nome
e schema estáveis (~500 caracteres cada) em vez de reaprender o Slack
inteiro (167 tools, algumas com >7KB de schema) a cada tarefa.

Mandar mensagem é ação externa irreversível — visível para outra pessoa assim
que sai — logo `chat_send_message` carrega `requires_confirmation=True`,
igual a `email_send`/`email_reply`.

Microsoft Teams fica de fora por ora: nenhuma conta está conectada neste
ambiente para verificar os slugs ao vivo (mesma cautela usada antes para não
supor schema do Composio sem checar). Se conectar Teams, o padrão aqui
(`_obj`, `cx.execute`, `requires_confirmation` no envio) se estende igual.
"""

from __future__ import annotations

from core.agent.registry import Tool, ToolResult, ok, fail
from core.llm.types import ToolSpec
from core.tools import composio_exec as cx

TOOLKIT = 'slack'
_HUMAN = 'Slack'


# --------------------------------------------------------------------------- utils

def _items(data, keys=('channels', 'members', 'messages', 'matches', 'items')) -> list:
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in keys:
        v = data.get(key)
        if isinstance(v, list):
            return v
        if isinstance(v, dict):
            for inner in keys:
                iv = v.get(inner)
                if isinstance(iv, list):
                    return iv
    return []


def _shape_channel(c: dict) -> dict:
    return {
        'id': c.get('id') or '',
        'name': c.get('name') or c.get('name_normalized') or '',
        'is_private': bool(c.get('is_private')),
        'is_member': bool(c.get('is_member')) if 'is_member' in c else None,
        'topic': ((c.get('topic') or {}).get('value') or '')[:120] if isinstance(c.get('topic'), dict) else '',
    }


def _shape_message(m: dict) -> dict:
    return {
        'user': m.get('user') or m.get('username') or '',
        'text': (m.get('text') or '')[:400],
        'ts': m.get('ts') or '',
        'channel': m.get('channel') or (m.get('channel') or {}).get('id', '') if isinstance(m.get('channel'), dict) else m.get('channel', ''),
    }


def _shape_user(u: dict) -> dict:
    profile = u.get('profile') or {}
    return {
        'id': u.get('id') or '',
        'name': u.get('real_name') or u.get('name') or profile.get('real_name') or '',
        'email': profile.get('email') or '',
    }


# --------------------------------------------------------------------------- leitura

def _find_channels(args, ctx) -> ToolResult:
    cx.require_connected(TOOLKIT, _HUMAN)
    query = (args.get('query') or '').strip()
    if not query:
        return fail(cx.BAD_ARGS, '`query` e obrigatorio (nome, topico ou proposito do canal)')
    data = cx.execute('SLACK_FIND_CHANNELS', {
        'query': query,
        'limit': min(int(args.get('limit') or 20), 50),
        'exact_match': bool(args.get('exact_match')),
    })
    chans = [_shape_channel(c) for c in _items(data) if isinstance(c, dict)]
    return ok({'channels': chans, 'count': len(chans)}, user_message=f'{len(chans)} canal(is) encontrado(s)')


def _list_channels(args, ctx) -> ToolResult:
    cx.require_connected(TOOLKIT, _HUMAN)
    data = cx.execute('SLACK_LIST_CONVERSATIONS', {
        'limit': min(int(args.get('limit') or 30), 100),
        'types': args.get('types') or 'public_channel,private_channel',
        'exclude_archived': True,
    })
    chans = [_shape_channel(c) for c in _items(data) if isinstance(c, dict)]
    return ok({'channels': chans, 'count': len(chans)}, user_message=f'{len(chans)} canal(is)')


def _read_channel(args, ctx) -> ToolResult:
    cx.require_connected(TOOLKIT, _HUMAN)
    channel = (args.get('channel') or '').strip()
    if not channel:
        return fail(cx.BAD_ARGS, '`channel` e obrigatorio (id do canal, ex. C0123456789)')
    data = cx.execute('SLACK_FETCH_CONVERSATION_HISTORY', {
        'channel': channel,
        'limit': min(int(args.get('limit') or 20), 100),
    })
    msgs = [_shape_message(m) for m in _items(data) if isinstance(m, dict)]
    return ok({'messages': msgs, 'count': len(msgs)}, user_message=f'{len(msgs)} mensagem(ns)')


def _search_messages(args, ctx) -> ToolResult:
    cx.require_connected(TOOLKIT, _HUMAN)
    query = (args.get('query') or '').strip()
    if not query:
        return fail(cx.BAD_ARGS, '`query` e obrigatorio')
    data = cx.execute('SLACK_SEARCH_MESSAGES', {
        'query': query,
        'count': min(int(args.get('limit') or 20), 50),
        'sort': 'timestamp',
        'sort_dir': 'desc',
    })
    msgs = [_shape_message(m) for m in _items(data) if isinstance(m, dict)]
    return ok({'messages': msgs, 'count': len(msgs)}, user_message=f'{len(msgs)} resultado(s)')


def _find_person(args, ctx) -> ToolResult:
    cx.require_connected(TOOLKIT, _HUMAN)
    email = (args.get('email') or '').strip()
    name = (args.get('name') or '').strip()
    if email:
        data = cx.execute('SLACK_FIND_USER_BY_EMAIL_ADDRESS', {'email': email})
        users = [data] if isinstance(data, dict) and (data.get('id') or data.get('user')) else _items(data)
    elif name:
        data = cx.execute('SLACK_FIND_USERS', {'search_query': name, 'limit': 10})
        users = _items(data)
    else:
        return fail(cx.BAD_ARGS, 'informe `email` ou `name`')
    users = [_shape_user(u) for u in users if isinstance(u, dict)]
    return ok({'users': users, 'count': len(users)}, user_message=f'{len(users)} pessoa(s) encontrada(s)')


# --------------------------------------------------------------------------- escrita

def _send_message(args, ctx) -> ToolResult:
    cx.require_connected(TOOLKIT, _HUMAN)
    channel = (args.get('channel') or '').strip()
    text = (args.get('text') or '').strip()
    if not channel:
        return fail(cx.BAD_ARGS, '`channel` e obrigatorio (id do canal ou @usuario para DM)')
    if not text:
        return fail(cx.BAD_ARGS, '`text` e obrigatorio')
    payload = {'channel': channel, 'markdown_text': text}
    if args.get('thread_ts'):
        payload['thread_ts'] = args['thread_ts']
    cx.execute('SLACK_SEND_MESSAGE', payload)
    return ok({'sent': True, 'channel': channel}, user_message=f'Mensagem enviada em {channel}')


def _obj(props: dict, required: list[str] | None = None) -> dict:
    s = {'type': 'object', 'properties': props}
    if required:
        s['required'] = required
    return s


def build_tools() -> list[Tool]:
    return [
        Tool(ToolSpec('chat_find_channels',
             'Acha canais do Slack por nome, topico ou proposito. Use antes de ler ou '
             'mandar mensagem quando so tiver o nome do canal, nao o id.',
             _obj({'query': {'type': 'string'}, 'limit': {'type': 'integer'},
                   'exact_match': {'type': 'boolean'}}, ['query']),
             parallel_safe=True), _find_channels, label='Buscando canais', icon='brand_slack'),

        Tool(ToolSpec('chat_list_channels',
             'Lista os canais do Slack que o Nigel enxerga (publicos e privados que participa).',
             _obj({'limit': {'type': 'integer'},
                   'types': {'type': 'string', 'description': "ex. 'public_channel,private_channel,im'"}}),
             parallel_safe=True), _list_channels, label='Listando canais', icon='brand_slack'),

        Tool(ToolSpec('chat_read_channel',
             'Le as mensagens mais recentes de um canal ou DM do Slack (precisa do id do canal '
             '- use chat_find_channels antes se so tiver o nome).',
             _obj({'channel': {'type': 'string'}, 'limit': {'type': 'integer'}}, ['channel']),
             parallel_safe=True), _read_channel, label='Lendo canal', icon='brand_slack'),

        Tool(ToolSpec('chat_search_messages',
             'Busca mensagens no Slack por texto, em qualquer canal que o Nigel enxerga.',
             _obj({'query': {'type': 'string'}, 'limit': {'type': 'integer'}}, ['query']),
             parallel_safe=True), _search_messages, label='Buscando mensagens', icon='brand_slack'),

        Tool(ToolSpec('chat_find_person',
             'Acha uma pessoa no workspace do Slack por e-mail ou nome, para saber o id '
             'antes de mandar uma DM.',
             _obj({'email': {'type': 'string'}, 'name': {'type': 'string'}}),
             parallel_safe=True), _find_person, label='Buscando pessoa', icon='brand_slack'),

        Tool(ToolSpec('chat_send_message',
             'ENVIA uma mensagem no Slack (canal ou DM). Acao externa irreversivel: '
             'sera confirmada pelo usuario.',
             _obj({'channel': {'type': 'string', 'description': 'id do canal ou id do usuario para DM'},
                   'text': {'type': 'string'},
                   'thread_ts': {'type': 'string', 'description': 'ts de uma mensagem existente, para responder em thread'}},
                  ['channel', 'text'])),
             _send_message, label='Enviando mensagem', icon='brand_slack', requires_confirmation=True),
    ]
