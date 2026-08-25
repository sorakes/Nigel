"""
core/tools/memory_tools.py — Consulta e escrita no grafo de memória do Nigel.

Antes, `_build_full_history` despejava os itens salvos e o grafo inteiro no
system prompt de TODA mensagem. Com estas ferramentas o Nigel consulta sob
demanda: o prompt base carrega só a persona e um índice curto de nomes
conhecidos — o suficiente para ele saber *que* precisa perguntar.
"""

from __future__ import annotations

from core.agent.registry import Tool, ToolResult, ok, fail
from core.llm.types import ToolSpec


def _db():
    from core.database import NigelDB
    return NigelDB.get_instance()


def _search_memory(args, ctx) -> ToolResult:
    q = (args.get('query') or '').strip().lower()
    limit = min(int(args.get('limit') or 10), 30)
    db = _db()
    hits = []
    for item in db.get_saved_items(limit=120):
        blob = ' '.join(str(item.get(k) or '') for k in
                        ('subject', 'body_preview', 'ai_summary', 'sender')).lower()
        if not q or q in blob:
            hits.append({
                'id': item.get('id'),
                'titulo': item.get('subject') or item.get('ai_summary') or '',
                'texto': (item.get('ai_summary') or item.get('body_preview') or '')[:220],
                'origem': item.get('source'),
                'relevancia': item.get('relevance_score'),
            })
        if len(hits) >= limit:
            break
    if not hits:
        return ok({'resultados': [], 'nota': 'nada na memoria sobre isso'},
                  user_message='Nada na memoria')
    return ok({'resultados': hits, 'total': len(hits)},
              user_message=f'{len(hits)} lembranca(s)')


def _known_entities(args, ctx) -> ToolResult:
    db = _db()
    graph = db.get_knowledge_graph(limit=120)
    pessoas, coisas = [], []
    for n in graph.get('nodes', []):
        titulo = (n.get('title') or n.get('subject') or '').strip()
        if not titulo:
            continue
        (pessoas if n.get('node_type') == 'persona' else coisas).append(titulo)
    return ok({'pessoas': pessoas[:40], 'outros': coisas[:40]},
              user_message=f'{len(pessoas)} pessoa(s) conhecida(s)')


def _get_persona(args, ctx) -> ToolResult:
    from core.storage import load_config
    persona = load_config().get('persona') or {}
    return ok({'nome': persona.get('name', ''), 'idade': persona.get('age', ''),
               'email': persona.get('email', ''), 'fatos': (persona.get('facts') or [])[:20]},
              user_message='Perfil do usuario')


def _save_memory(args, ctx) -> ToolResult:
    titulo = (args.get('title') or '').strip()
    texto = (args.get('text') or '').strip()
    if not titulo and not texto:
        return fail('BAD_ARGS', 'informe `title` e/ou `text`')
    db = _db()
    tipo = (args.get('kind') or 'note').strip().lower()
    if tipo == 'person':
        db.upsert_person_relation(titulo, texto)
    else:
        db.save_item(subject=titulo or texto[:60], body_preview=texto,
                     source='chat', is_important=True,
                     relevance_score=int(args.get('relevance') or 60))
    try:
        from ui.agenda_skills import trigger_ui_update
        trigger_ui_update()
    except Exception:
        pass
    return ok({'salvo': True, 'titulo': titulo}, user_message=f'Memorizado: {titulo or texto[:40]}')


def _obj(props, required=None):
    s = {'type': 'object', 'properties': props}
    if required:
        s['required'] = required
    return s


def build_tools() -> list[Tool]:
    return [
        Tool(ToolSpec('memory_search',
             'Procura na memoria do Nigel por pessoas, lugares, projetos ou assuntos ja conhecidos.',
             _obj({'query': {'type': 'string'}, 'limit': {'type': 'integer'}}),
             parallel_safe=True), _search_memory, label='Consultando memoria', icon='memory'),

        Tool(ToolSpec('memory_known_entities',
             'Lista tudo que o Nigel ja conhece: pessoas e outros assuntos. '
             'Use para saber se precisa perguntar antes de agendar algo com alguem.',
             _obj({}), parallel_safe=True), _known_entities, label='Listando o que conheco', icon='memory'),

        Tool(ToolSpec('memory_get_persona',
             'Le o perfil do proprio usuario (nome, e-mail, fatos pessoais).',
             _obj({}), parallel_safe=True), _get_persona, label='Lendo perfil', icon='memory'),

        Tool(ToolSpec('memory_save',
             'Guarda um fato novo na memoria. Use depois que o usuario explicar quem e alguem '
             'ou o que e algum lugar/projeto.',
             _obj({'title': {'type': 'string', 'description': 'nome da pessoa/coisa'},
                   'text': {'type': 'string', 'description': 'o que foi aprendido'},
                   'kind': {'type': 'string', 'enum': ['person', 'note'],
                            'description': "'person' para gente, 'note' para o resto"},
                   'relevance': {'type': 'integer'}})),
             _save_memory, label='Memorizando', icon='memory'),
    ]
