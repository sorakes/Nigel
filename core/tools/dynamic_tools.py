"""
core/tools/dynamic_tools.py — Descoberta dinâmica de qualquer toolkit do Composio.

Cobrir "todos os outros apps" com wrappers curados é inviável, e despejar os
schemas crus no contexto também: só `GOOGLECALENDAR_CREATE_EVENT` tem 13,9 KB,
e existem 49 ferramentas de calendário e 63 de Gmail.

A saída são três meta-ferramentas. A busca devolve apenas slug e um resumo
curto (~2 KB para 10 resultados); o schema completo só é buscado quando o
modelo decide efetivamente executar algo.
"""

from __future__ import annotations

import threading

from core.agent.registry import Tool, ToolResult, ok, fail
from core.llm.types import ToolSpec
from core.tools import composio_exec as cx

# Schemas crus são caros de buscar: cache por processo.
_schema_cache: dict[str, dict] = {}
_cache_lock = threading.RLock()

# Já cobertos por ferramentas curadas — o apps_agent não deve reinventá-los.
_JA_COBERTOS = {'googlecalendar', 'gmail', 'outlook'}


def _client():
    from core.composio_manager import ComposioManager
    return ComposioManager.get_instance().get_client()


def _list_apps(args, ctx) -> ToolResult:
    from core.composio_manager import ComposioManager, DEFAULT_USER_ID
    cm = ComposioManager.get_instance()
    if not cm.is_configured():
        return fail(cx.NOT_CONNECTED, 'Composio nao configurado.')
    try:
        resp = _client().connected_accounts.list(
            user_ids=[DEFAULT_USER_ID], statuses=['ACTIVE'], timeout=10.0)
    except Exception as e:
        return fail(cx._classify(str(e)), str(e))

    from core.composio_manager import _extract_toolkit_slug
    items = getattr(resp, 'items', None) or getattr(resp, 'data', None) or resp
    slugs = sorted({_extract_toolkit_slug(a) for a in (items or []) if _extract_toolkit_slug(a)})
    outros = [s for s in slugs if s not in _JA_COBERTOS]
    return ok({'apps_conectados': slugs,
               'fora_de_agenda_e_email': outros,
               'nota': 'agenda e e-mail ja tem especialistas proprios'},
              user_message=f'{len(slugs)} app(s) conectado(s)')


def _search_tools(args, ctx) -> ToolResult:
    query = (args.get('query') or '').strip()
    toolkit = (args.get('app') or '').strip().lower()
    if not query and not toolkit:
        return fail(cx.BAD_ARGS, 'informe `query` e/ou `app`')
    limit = min(int(args.get('limit') or 10), 15)
    try:
        kwargs = {'limit': limit}
        if toolkit:
            kwargs['toolkits'] = [toolkit]
        if query:
            kwargs['search'] = query
        raw = _client().tools.get_raw_composio_tools(**kwargs)
    except Exception as e:
        return fail(cx._classify(str(e)), str(e))

    found = []
    for t in (raw or [])[:limit]:
        slug = getattr(t, 'slug', '') or ''
        if not slug:
            continue
        with _cache_lock:
            _schema_cache.setdefault(slug, {'_tool': t})
        found.append({'slug': slug,
                      'resumo': (getattr(t, 'description', '') or '')[:200]})
    if not found:
        return ok({'ferramentas': [], 'nota': 'nada encontrado; tente outro termo ou outro app'},
                  user_message='Nenhuma ferramenta encontrada')
    return ok({'ferramentas': found,
               'nota': 'chame run_app_tool com o slug escolhido'},
              user_message=f'{len(found)} ferramenta(s)')


def _tool_schema(slug: str) -> dict:
    with _cache_lock:
        entry = _schema_cache.get(slug)
        if entry and 'params' in entry:
            return entry['params']
    tool = (entry or {}).get('_tool') if entry else None
    if tool is None:
        tool = _client().tools.get_raw_composio_tool_by_slug(slug)
    params = getattr(tool, 'input_parameters', None) or {}
    with _cache_lock:
        _schema_cache[slug] = {'_tool': tool, 'params': params}
    return params


def _run_tool(args, ctx) -> ToolResult:
    slug = (args.get('slug') or '').strip().upper()
    if not slug:
        return fail(cx.BAD_ARGS, '`slug` e obrigatorio (use search_app_tools antes)')
    payload = args.get('arguments') or {}
    if isinstance(payload, str):
        from core.llm.types import parse_arguments
        payload = parse_arguments(payload)

    try:
        schema = _tool_schema(slug)
    except Exception as e:
        return fail(cx.NOT_FOUND, f'nao achei a ferramenta {slug}: {e}')

    required = [r for r in (schema.get('required') or []) if r not in payload]
    if required:
        props = schema.get('properties') or {}
        detalhe = {r: (props.get(r, {}).get('description') or '')[:120] for r in required}
        return fail(cx.BAD_ARGS,
                    f'faltam argumentos obrigatorios em {slug}: {detalhe}')

    data = cx.execute(slug, payload)
    texto = str(data)
    if len(texto) > 1800:
        data = {'resumo': texto[:1800] + '… [truncado]'}
    return ok(data, user_message=f'{slug} executado')


def _obj(props, required=None):
    s = {'type': 'object', 'properties': props}
    if required:
        s['required'] = required
    return s


def build_tools() -> list[Tool]:
    return [
        Tool(ToolSpec('list_connected_apps',
             'Lista os apps que o usuario conectou no Composio.',
             _obj({}), parallel_safe=True), _list_apps, label='Listando apps', icon='brand_app'),

        Tool(ToolSpec('search_app_tools',
             'Procura uma ferramenta disponivel num app conectado. Devolve slugs e resumos.',
             _obj({'query': {'type': 'string', 'description': 'o que voce quer fazer, ex. "enviar mensagem"'},
                   'app': {'type': 'string', 'description': 'slug do app, ex. slack, notion'},
                   'limit': {'type': 'integer'}}), parallel_safe=True),
             _search_tools, label='Procurando ferramenta', icon='brand_app'),

        Tool(ToolSpec('run_app_tool',
             'Executa uma ferramenta de app pelo slug. Se faltar argumento, a resposta diz qual.',
             _obj({'slug': {'type': 'string'},
                   'arguments': {'type': 'object', 'description': 'argumentos da ferramenta'}},
                  ['slug'])), _run_tool, label='Executando acao', icon='brand_app'),
    ]
