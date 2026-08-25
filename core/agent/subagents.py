"""
core/agent/subagents.py — Especialistas que o Nigel orquestra.

Um subagente é um system prompt + um subconjunto de ferramentas + o próprio
loop. Para o orquestrador ele aparece como UMA ferramenta que recebe uma tarefa
em linguagem natural e devolve um relatório curto em texto.

É isso que resolve o orçamento de token: o Nigel enxerga ~9 ferramentas
(4 subagentes + `ask_user_context` + `schedule_*`), enquanto o `agenda_agent`
manuseia 10 ferramentas de calendário que o Nigel nunca paga em contexto.

Profundidade: subagentes NÃO recebem ferramentas `*_agent`, então recursão é
impossível por construção; o teste de `ctx.depth` é só cinto e suspensório.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from core.agent import prompts
from core.agent.registry import Tool, ToolRegistry, ToolResult, ok, fail
from core.llm.types import ToolSpec

MAX_OUTPUT_CHARS = 1500
SUBAGENT_MAX_ITERATIONS = 5

_TASK_SCHEMA = {
    'type': 'object',
    'properties': {
        'task': {'type': 'string',
                 'description': 'a tarefa, em uma frase, com TODO o contexto necessario — '
                                'o especialista nao ve a conversa'},
        'context': {'type': 'string',
                    'description': 'detalhes extras uteis (nomes, datas, preferencias)'},
    },
    'required': ['task'],
}


@dataclass(frozen=True)
class SubAgentSpec:
    name: str
    description: str
    system_prompt: str
    tool_names: tuple[str, ...]
    label: str
    default_icon: str = ''      # usado quando o subagente nao chega a rodar nenhuma ferramenta
    max_iterations: int = SUBAGENT_MAX_ITERATIONS
    max_output_chars: int = MAX_OUTPUT_CHARS


SPECS = (
    SubAgentSpec(
        name='agenda_agent',
        description=(
            'Especialista na agenda do Google do usuario. Consulta, cria, remarca, cancela '
            'compromissos, verifica conflitos e acha horarios livres. Descreva a tarefa em '
            'linguagem natural, ex.: "cancelar a reuniao com o Joao de amanha".'),
        system_prompt=prompts.AGENDA_AGENT,
        tool_names=('calendar_find_events', 'calendar_list_events', 'calendar_get_event',
                    'calendar_list_calendars', 'calendar_find_free_slots',
                    'calendar_check_conflicts', 'calendar_create_event',
                    'calendar_update_event', 'calendar_reschedule_event',
                    'calendar_delete_event'),
        label='Consultando a agenda', default_icon='brand_gcal'),
    SubAgentSpec(
        name='email_agent',
        description=(
            'Especialista em e-mail (Gmail e Outlook). Busca, le, resume, rascunha, responde, '
            'arquiva e rotula. Ex.: "ver se o Joao mandou algo sobre a reuniao esta semana".'),
        system_prompt=prompts.EMAIL_AGENT,
        tool_names=('email_search', 'email_read_thread', 'email_list_labels',
                    'email_draft', 'email_send', 'email_reply',
                    'email_archive', 'email_label', 'email_trash'),
        label='Verificando e-mails', default_icon='email'),
    SubAgentSpec(
        name='memory_agent',
        description=(
            'Consulta o que o Nigel ja sabe sobre o usuario, suas pessoas, lugares e projetos. '
            'Use antes de perguntar algo ao usuario, para nao repetir pergunta.'),
        system_prompt=prompts.MEMORY_AGENT,
        tool_names=('memory_search', 'memory_known_entities', 'memory_get_persona', 'memory_save'),
        label='Consultando memoria', default_icon='memory'),
    SubAgentSpec(
        name='chat_agent',
        description=(
            'Especialista em Slack. Acha canais/pessoas, le e busca mensagens, manda mensagem '
            'ou DM. Ex.: "avisar o time no #geral que a reuniao mudou para 15h".'),
        system_prompt=prompts.CHAT_AGENT,
        tool_names=('chat_find_channels', 'chat_list_channels', 'chat_read_channel',
                    'chat_search_messages', 'chat_find_person', 'chat_send_message'),
        label='Verificando o Slack', default_icon='brand_slack'),
    SubAgentSpec(
        name='apps_agent',
        description=(
            'Alcanca qualquer OUTRO app conectado pelo usuario no Composio (Notion, '
            'Drive, Sheets...). Descubra o que existe e execute. Nao use para agenda, e-mail '
            'ou Slack — esses tem especialista proprio.'),
        system_prompt=prompts.APPS_AGENT,
        tool_names=('list_connected_apps', 'search_app_tools', 'run_app_tool'),
        label='Consultando apps', default_icon='brand_app'),
    SubAgentSpec(
        name='web_agent',
        description=(
            'Pesquisa na internet: noticias, precos, definicoes, documentacao, qualquer coisa '
            'publica que o Nigel nao sabe e nao esta na agenda, no e-mail ou na memoria do '
            'usuario. Ex.: "qual a cotacao do dolar hoje", "o que e RAG em IA".'),
        system_prompt=prompts.WEB_AGENT,
        tool_names=('web_search', 'web_fetch'),
        label='Pesquisando na web', default_icon='brand_web'),
)


def _pick_icon(seen: list[str], spec: SubAgentSpec) -> str:
    """Ícone mais específico visto durante a execução, ou o padrão da especialidade."""
    if not seen:
        return spec.default_icon
    distintos = set(seen)
    if len(distintos) == 1:
        return next(iter(distintos))
    return seen[-1]


def make_subagent_tool(spec: SubAgentSpec, base_registry: ToolRegistry, llm_factory) -> Tool:
    """Compila um SubAgentSpec numa ferramenta que o orquestrador pode chamar."""

    def _run(args: dict, ctx) -> ToolResult:
        task = (args.get('task') or '').strip()
        if not task:
            return fail('BAD_ARGS', '`task` e obrigatorio')
        if ctx.depth >= 1:
            return fail('DEPTH', 'um especialista nao pode chamar outro especialista')

        sub_registry = base_registry.subset(spec.tool_names)
        if not sub_registry.names():
            return fail('UNAVAILABLE', f'{spec.name} nao tem ferramentas disponiveis')

        if args.get('context'):
            task = f"{task}\n\nContexto: {args['context']}"

        # Intercepta os eventos internos só para saber quais ícones as
        # ferramentas de verdade usaram (ex.: email_search descobrindo Gmail
        # vs Outlook em runtime) — o resultado do especialista herda o ícone
        # mais específico, em vez de sempre mostrar o genérico da categoria.
        seen_icons: list[str] = []

        def _emit_and_track(ev):
            if ev.kind == 'tool_end' and getattr(ev, 'icon', ''):
                seen_icons.append(ev.icon)
            ctx.emit(ev)

        from core.agent.loop import AgentRunner
        sub_ctx = replace(ctx, depth=ctx.depth + 1, pending_question=None, emit=_emit_and_track)
        runner = AgentRunner(llm_factory(), sub_registry,
                             prompts.subagent_prompt(spec.system_prompt),
                             max_iterations=spec.max_iterations, name=spec.name,
                             max_tokens=2048)
        res = runner.run([{'role': 'user', 'content': task}], sub_ctx)

        if res.error and not res.text:
            return fail('SUBAGENT_ERROR', f'{spec.name}: {res.error}', icon=_pick_icon(seen_icons, spec))
        texto = (res.text or '').strip()[:spec.max_output_chars]
        if not texto:
            texto = 'o especialista nao produziu resposta'
        return ok({'especialista': spec.name, 'relatorio': texto,
                   'ferramentas_usadas': res.tool_calls},
                  user_message=spec.label, icon=_pick_icon(seen_icons, spec))

    return Tool(
        spec=ToolSpec(name=spec.name, description=spec.description,
                      parameters=_TASK_SCHEMA, parallel_safe=True),
        fn=_run, label=spec.label, icon=spec.default_icon)


def build_subagent_tools(base_registry: ToolRegistry, llm_factory) -> list[Tool]:
    return [make_subagent_tool(s, base_registry, llm_factory) for s in SPECS]
