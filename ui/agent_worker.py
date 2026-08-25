"""
ui/agent_worker.py — Ponte entre o loop do agente e o Qt.

Único ponto do agente que conhece Qt. O `AgentRunner` é Python puro; aqui ele
roda numa QThread e seus eventos viram sinais.

Isso também elimina o congelamento da barra: antes o `_parse_and_execute` fazia
HTTP bloqueante para o Composio na thread da GUI, e a barra travava durante uma
escrita no calendário.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from PyQt6.QtCore import QThread, pyqtSignal

from core.agent.loop import AgentEvent, AgentRunner, new_context

# Mantém referências vivas para o GC não coletar workers em execução.
_ACTIVE: set = set()


class BgCall(QThread):
    """Roda uma chamada qualquer (dispatch de ferramenta, LLM) fora da UI thread.

    Usado para executar a ação depois que o usuário confirma, e por outros
    pontos (popup de e-mail) que precisam de uma chamada única em background
    sem montar um AgentRunner inteiro.
    """

    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            self.done.emit(self._fn())
        except Exception as e:
            self.failed.emit(f'{type(e).__name__}: {e}')


class AgentWorker(QThread):
    text_delta = pyqtSignal(str)              # texto visível conforme chega
    tool_started = pyqtSignal(str, str, str)  # nome, rótulo, ícone
    tool_finished = pyqtSignal(str, str, bool, str)  # nome, mensagem, ok, ícone
    phase_changed = pyqtSignal(str)           # fase do orb
    asked = pyqtSignal(dict)              # ask_user_context disparou
    confirm_requested = pyqtSignal(str, str, str)  # nome, rótulo, ícone — ação irreversível
    answer_ready = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, system_prompt: str, messages: list[dict], registry,
                 event_refs=None, max_iterations: int = 8, parent=None):
        super().__init__(parent)
        self._system_prompt = system_prompt
        self._messages = list(messages)
        self._registry = registry
        self.registry = registry  # exposto para dispatch pos-confirmacao
        self._event_refs = event_refs
        self._max_iterations = max_iterations
        self._cancel = threading.Event()
        self._pool: ThreadPoolExecutor | None = None
        self.result = None

    def stop(self):
        self._cancel.set()

    def _on_event(self, ev: AgentEvent):
        if self._cancel.is_set():
            return
        if ev.kind == 'text':
            if ev.text:
                self.text_delta.emit(ev.text)
        elif ev.kind == 'tool_start':
            # Só o nível 0 (o que o Nigel chamou diretamente — os 4 especialistas,
            # lembretes, pergunta de contexto) vira linha na UI. As ferramentas
            # que um especialista roda por dentro (depth>=1) ficam de fora da
            # lista para não duplicar — o resultado delas já volta agregado
            # no ícone/mensagem do especialista.
            if ev.depth == 0:
                self.tool_started.emit(ev.name, ev.text or ev.name, ev.icon)
            self.phase_changed.emit(
                'subagent' if ev.name.endswith('_agent') else 'tool')
        elif ev.kind == 'tool_end':
            if ev.depth == 0:
                self.tool_finished.emit(ev.name, ev.text or '', ev.ok, ev.icon)
            self.phase_changed.emit('thinking')
        elif ev.kind == 'ask':
            self.asked.emit(ev.data or {'question': ev.text})
        elif ev.kind == 'confirm':
            self.confirm_requested.emit(ev.name, ev.text or ev.name, ev.icon)
        elif ev.kind == 'phase':
            self.phase_changed.emit('thinking')
        elif ev.kind == 'error':
            self.failed.emit(ev.text)

    def run(self):
        try:
            from core.llm.client import LLMClient
            llm = LLMClient()
        except Exception as e:
            self.failed.emit(f'Nenhum provider de IA configurado.\n{e}')
            return

        self._pool = ThreadPoolExecutor(max_workers=4)
        ctx = new_context(cancel=self._cancel, emit=self._on_event, pool=self._pool)
        if self._event_refs is not None:
            ctx.event_refs = self._event_refs
        self.ctx = ctx  # acessivel depois do run() para redespachar uma acao confirmada
        try:
            runner = AgentRunner(llm, self._registry, self._system_prompt,
                                 max_iterations=self._max_iterations)
            self.result = runner.run(self._messages, ctx)
            if self._cancel.is_set():
                return
            if self.result.error and not self.result.text:
                self.failed.emit(self.result.error)
            else:
                self.answer_ready.emit(self.result.text or '')
        except Exception as e:
            if not self._cancel.is_set():
                self.failed.emit(f'{type(e).__name__}: {e}')
        finally:
            if self._pool:
                self._pool.shutdown(wait=False)
                self._pool = None


def spawn(system_prompt: str, messages: list[dict], registry, **kw) -> AgentWorker:
    """Cria o worker e o mantém vivo até terminar."""
    w = AgentWorker(system_prompt, messages, registry, **kw)
    _ACTIVE.add(w)
    w.finished.connect(lambda: _ACTIVE.discard(w))
    return w
