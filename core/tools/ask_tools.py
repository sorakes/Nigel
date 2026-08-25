"""
core/tools/ask_tools.py — A curiosidade do Nigel, agora como ferramenta.

Antes isso era um estágio inteiro de LLM (`chat_intent_gate`) mais um auditor
(`chat_compliance`) tentando adivinhar, por listas de marcadores em português,
se o Nigel deveria ter perguntado algo antes de agendar.

Agora é uma decisão do próprio modelo dentro de um loop só: se ele encontra uma
pessoa/lugar/coisa que não está na memória, ele chama `ask_user_context`. A UI
desenha a bolha roxa e o turno termina; a resposta do usuário chega como a
próxima mensagem.
"""

from __future__ import annotations

from core.agent.registry import Tool, ToolResult, ok, fail
from core.llm.types import ToolSpec


def _ask(args, ctx) -> ToolResult:
    question = (args.get('question') or '').strip()
    if not question:
        return fail('BAD_ARGS', '`question` e obrigatorio')
    subject = (args.get('subject') or '').strip()
    pending = args.get('pending_action') or ''

    ctx.pending_question = {'subject': subject, 'question': question, 'pending_action': pending}
    from core.agent.loop import AgentEvent
    ctx.emit(AgentEvent('ask', name=subject, text=question, data=ctx.pending_question))

    return ok({'pergunta_exibida': True,
               'proximo_passo': 'aguarde a resposta do usuario na proxima mensagem'},
              user_message=f'Perguntando sobre {subject}' if subject else 'Perguntando')


def build_tools() -> list[Tool]:
    return [Tool(ToolSpec(
        'ask_user_context',
        'Faz UMA pergunta aberta ao usuario sobre uma pessoa, lugar, projeto ou coisa que '
        'voce ainda nao conhece. Use antes de agendar algo envolvendo alguem que nao esta '
        'na memoria (confira com memory_known_entities). Encerra o turno: a resposta vem '
        'na proxima mensagem. Uma pergunta por vez.',
        {'type': 'object', 'properties': {
            'subject': {'type': 'string', 'description': 'quem ou o que voce quer entender'},
            'question': {'type': 'string', 'description': 'a pergunta, no idioma do usuario'},
            'pending_action': {'type': 'string',
                               'description': 'o que voce fara assim que souber'},
        }, 'required': ['question']}),
        _ask, label='Perguntando', icon='ai')]
