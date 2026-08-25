"""
core/agent/loop.py — O loop observar→agir.

Python puro, sem Qt: reaproveitável pela barra, pelo popup de lembrete e pelas
tarefas agendadas, e testável sem subir a UI.

A mudança central em relação ao pipeline antigo: o resultado da ferramenta
volta para o histórico e o modelo o lê. Antes ele virava uma string em português
jogada num balão e o modelo nunca ficava sabendo se tinha dado certo — daí a
necessidade das quatro chamadas extras de LLM (review/gate/compliance/fix) só
para auditar se ele havia escrito o JSON certo.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

from core.agent.registry import ToolRegistry, ToolResult, fail
from core.llm.client import LLMClient, LLMError, MalformedToolCall, ToolsUnsupported
from core.llm.sanitize_text import clean as clean_text
from core.llm.text_tools import has_tool_marker, recover
from core.llm.types import ToolCall

MAX_ITERATIONS = 8
SUBAGENT_MAX_ITERATIONS = 5
DEFAULT_DEADLINE_SEC = 120.0
TOOL_TIMEOUT_SEC = 45.0


@dataclass
class AgentEvent:
    kind: str                 # text | tool_start | tool_end | ask | phase | error
    name: str = ''
    text: str = ''
    data: Any = None
    ok: bool = True
    icon: str = ''             # de onde veio (ui.icons): 'brand_gmail', 'brand_gcal'...
    depth: int = 0              # 0 = chamada direta do Nigel; 1 = dentro de um subagente


@dataclass
class RunContext:
    event_refs: Any = None
    cancel: threading.Event = field(default_factory=threading.Event)
    emit: Callable[[AgentEvent], None] = lambda e: None
    pool: ThreadPoolExecutor | None = None
    depth: int = 0
    deadline: float = 0.0
    user_text: str = ''
    pending_question: dict | None = None   # preenchido por ask_user_context

    def expired(self) -> bool:
        return bool(self.deadline) and time.monotonic() > self.deadline

    def stopped(self) -> bool:
        return self.cancel.is_set() or self.expired()


@dataclass
class AgentResult:
    text: str = ''
    iterations: int = 0
    tool_calls: int = 0
    stopped_early: bool = False
    error: str = ''
    asked: dict | None = None
    pending_confirmation: ToolCall | None = None   # ferramenta irreversível aguardando "sim"


def _plain_history(history: list[dict]) -> list[dict]:
    """Historico sem tool calls: so system, user e texto do assistente.

    Um turno de assistente com tool_calls invalidas faz o provider recusar
    tambem as requisicoes seguintes que o reprocessam. Os resultados de
    ferramenta ja obtidos viram texto simples, para nao perder o trabalho.
    """
    out = []
    for m in history:
        role = m.get('role')
        if role in ('system', 'user') and isinstance(m.get('content'), str):
            out.append({'role': role, 'content': m['content']})
        elif role == 'tool':
            out.append({'role': 'user',
                        'content': f"[resultado de {m.get('name') or 'ferramenta'}] "
                                   f"{m.get('content') or ''}"})
        elif role in ('assistant', 'model'):
            texto = m.get('content')
            if isinstance(texto, str) and texto.strip():
                out.append({'role': 'assistant', 'content': texto})
    return out


def new_context(**kw) -> RunContext:
    from core.tools.refs import EventRefCache
    kw.setdefault('event_refs', EventRefCache())
    kw.setdefault('deadline', time.monotonic() + DEFAULT_DEADLINE_SEC)
    return RunContext(**kw)


class AgentRunner:
    def __init__(self, llm: LLMClient, registry: ToolRegistry, system_prompt: str,
                 *, max_iterations: int = MAX_ITERATIONS, name: str = 'nigel',
                 max_tokens: int = 4096):
        self.llm = llm
        self.registry = registry
        self.system_prompt = system_prompt
        self.max_iterations = max_iterations
        self.name = name
        self.max_tokens = max_tokens

    # ------------------------------------------------------------------ tools

    def _run_calls(self, calls: list[ToolCall], ctx: RunContext) -> list[ToolResult]:
        """Executa as tool calls do turno. Leituras em paralelo, escritas em série."""
        results: list[ToolResult | None] = [None] * len(calls)

        parallel = [i for i, c in enumerate(calls) if self.registry.is_parallel_safe(c.name)]
        serial = [i for i in range(len(calls)) if i not in parallel]

        for i in parallel + serial:
            tool = self.registry.get(calls[i].name)
            ctx.emit(AgentEvent('tool_start', name=calls[i].name,
                                text=(tool.label if tool else calls[i].name),
                                data=calls[i].arguments,
                                icon=(tool.icon if tool else ''), depth=ctx.depth))

        if parallel and ctx.pool is not None and len(parallel) > 1:
            futs = {ctx.pool.submit(self.registry.dispatch, calls[i], ctx): i for i in parallel}
            for fut, i in futs.items():
                try:
                    results[i] = fut.result(timeout=TOOL_TIMEOUT_SEC)
                except Exception as e:
                    results[i] = fail('TIMEOUT', f'{type(e).__name__}: {e}')
        else:
            for i in parallel:
                results[i] = self.registry.dispatch(calls[i], ctx)

        for i in serial:
            if ctx.stopped():
                results[i] = fail('CANCELLED', 'execucao interrompida')
                continue
            results[i] = self.registry.dispatch(calls[i], ctx)

        out = []
        for c, r in zip(calls, results):
            r = r or fail('NO_RESULT', 'ferramenta nao retornou')
            out.append(r)
            ctx.emit(AgentEvent('tool_end', name=c.name,
                                text=r.user_message or ('ok' if r.ok else (r.error or 'falhou')),
                                data=r.data, ok=r.ok, icon=r.icon, depth=ctx.depth))
        return out

    # ------------------------------------------------------------------ loop

    def run(self, messages: list[dict], ctx: RunContext) -> AgentResult:
        history = [{'role': 'system', 'content': self.system_prompt}] + list(messages)
        specs = self.registry.specs()
        # Zera qualquer pergunta pendente de um turno anterior: sem isso, uma
        # pergunta antiga curto-circuitava o turno novo e a resposta se repetia.
        ctx.pending_question = None
        result = AgentResult()
        last_text = ''
        use_tools = bool(specs)
        malformed_retries = 0

        for it in range(1, self.max_iterations + 1):
            result.iterations = it
            if ctx.stopped():
                result.stopped_early = True
                break

            final_turn = it == self.max_iterations
            # Na última volta, proíbe ferramentas: o usuário sempre recebe prosa,
            # nunca uma tool call pendurada.
            tool_choice = 'none' if final_turn else 'auto'
            stream = True

            def on_text(delta, _it=it):
                ctx.emit(AgentEvent('text', text=delta, data=_it))

            try:
                resp = self.llm.complete(
                    history,
                    specs if use_tools else [],
                    stream=stream,
                    on_text=on_text,
                    max_tokens=self.max_tokens,
                    tool_choice=tool_choice,
                    cancel=ctx.cancel,
                )
            except MalformedToolCall:
                # O modelo errou o formato da tool call. Uma repeticao costuma
                # resolver; na segunda, termina em prosa em vez de travar o turno.
                malformed_retries += 1
                if malformed_retries == 1:
                    ctx.emit(AgentEvent('phase', name='retry', text='refazendo a chamada'))
                    continue
                # Na segunda falha, o proprio HISTORICO pode conter o turno
                # malformado, que o provider rejeita de novo ao reprocessar.
                # Refaz com um historico limpo: so texto, sem tool calls.
                try:
                    resp = self.llm.complete(_plain_history(history), [], stream=True,
                                             on_text=on_text, max_tokens=self.max_tokens,
                                             cancel=ctx.cancel)
                    result.text = clean_text(resp.text) or last_text
                    return result
                except LLMError as e2:
                    result.error = str(e2)
                    ctx.emit(AgentEvent('error', text=str(e2), ok=False))
                    break
            except ToolsUnsupported as e:
                # Modelo nao faz tool calling: segue sem ferramentas nesta rodada.
                if not use_tools:
                    result.error = str(e)
                    break
                use_tools = False
                ctx.emit(AgentEvent('phase', name='sem_tools', text=str(e)))
                continue
            except LLMError as e:
                result.error = str(e)
                ctx.emit(AgentEvent('error', text=str(e), ok=False))
                break

            calls = resp.tool_calls
            if not calls and use_tools and has_tool_marker(resp.text or ''):
                # O modelo escreveu a tool call como texto em vez de usar o
                # canal proprio. Resgata em vez de mostrar a marcacao crua.
                calls = recover(resp.text, {s.name for s in specs})
                if calls:
                    ctx.emit(AgentEvent('phase', name='resgate',
                                        text='chamada recuperada do texto'))
                    resp.raw_assistant_message = {
                        'role': 'assistant',
                        'content': f'[chamando {", ".join(c.name for c in calls)}]',
                    }
                    resp.text = ''

            visible = clean_text(resp.text or '')
            if visible:
                last_text = visible

            if not calls:
                result.text = visible or last_text
                return result

            # Ferramentas irreversíveis (enviar e-mail, apagar...) nunca rodam
            # sozinhas: o modelo decide O QUE fazer, mas quem aperta "sim" é o
            # usuário. Sem isso `requires_confirmation=True` nos Tools não tinha
            # nenhum efeito real — o agente podia mandar um e-mail sem perguntar.
            needs_confirm = [c for c in calls
                             if getattr(self.registry.get(c.name), 'requires_confirmation', False)]
            if needs_confirm:
                call = needs_confirm[0]
                tool = self.registry.get(call.name)
                ctx.emit(AgentEvent('confirm', name=call.name,
                                    text=(tool.label if tool else call.name),
                                    data={'call': call, 'registry': self.registry},
                                    icon=(tool.icon if tool else ''), depth=ctx.depth))
                result.pending_confirmation = call
                result.text = visible or f'Posso {(tool.label if tool else call.name).lower()}?'
                return result

            result.tool_calls += len(calls)
            history.append(resp.raw_assistant_message)
            results = self._run_calls(calls, ctx)

            # ask_user_context encerra o turno: a resposta vem na proxima mensagem.
            if ctx.pending_question is not None:
                result.asked = ctx.pending_question
                result.text = resp.text or ctx.pending_question.get('question', '')
                return result

            history.extend(self.llm.encode_tool_results(
                calls, [r.to_model() for r in results]))

        if not result.text:
            result.text = last_text
        result.stopped_early = result.stopped_early or not result.text
        return result


def run_agent(system_prompt: str, messages: list[dict], registry: ToolRegistry,
              ctx: RunContext | None = None, *, llm: LLMClient | None = None,
              max_iterations: int = MAX_ITERATIONS, name: str = 'nigel') -> AgentResult:
    """Atalho para uso headless (testes, tarefas agendadas)."""
    ctx = ctx or new_context()
    runner = AgentRunner(llm or LLMClient(), registry, system_prompt,
                         max_iterations=max_iterations, name=name)
    own_pool = ctx.pool is None
    if own_pool:
        ctx.pool = ThreadPoolExecutor(max_workers=4)
    try:
        return runner.run(messages, ctx)
    finally:
        if own_pool and ctx.pool:
            ctx.pool.shutdown(wait=False)
            ctx.pool = None
