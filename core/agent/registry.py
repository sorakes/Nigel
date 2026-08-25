"""
core/agent/registry.py — Registro de ferramentas e contrato de resultado.

`dispatch` nunca levanta: qualquer falha vira um `ToolResult` com `ok=False` e
um `code`, que é devolvido AO MODELO. Esse é o ponto central do novo loop —
antes o resultado de uma ferramenta virava uma string em português jogada num
balão da UI, e o modelo nunca ficava sabendo se deu certo.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from core.llm.types import ToolSpec, ToolCall

MAX_RESULT_CHARS = 2000


@dataclass
class ToolResult:
    ok: bool
    data: Any = None
    error: str | None = None
    code: str = ''
    user_message: str = ''      # texto curto em português para a linha de ação da UI
    icon: str = ''               # nome de icone (ui.icons) indicando de onde veio o resultado

    def to_model(self, limit: int = MAX_RESULT_CHARS) -> str:
        """Serializa para o turno `tool`. Trunca avisando, para o modelo saber paginar."""
        if self.ok:
            payload = self.data if self.data is not None else {'ok': True}
        else:
            payload = {'ok': False, 'code': self.code or 'ERROR',
                       'error': self.error or 'falha desconhecida'}
        try:
            text = json.dumps(payload, ensure_ascii=False, default=str)
        except Exception:
            text = str(payload)
        if len(text) > limit:
            text = text[:limit] + f'… [truncado em {limit} caracteres; refine a busca ou pagine]'
        return text


def ok(data: Any = None, user_message: str = '', icon: str = '') -> ToolResult:
    return ToolResult(True, data=data, user_message=user_message, icon=icon)


def fail(code: str, error: str, user_message: str = '', icon: str = '') -> ToolResult:
    return ToolResult(False, error=error, code=code,
                      user_message=user_message or error, icon=icon)


@dataclass(frozen=True)
class Tool:
    spec: ToolSpec
    fn: Callable[[dict, Any], ToolResult]
    requires_confirmation: bool = False   # ação externa irreversível (ex.: enviar e-mail)
    label: str = ''                       # rótulo para a UI ("Buscando na agenda…")
    icon: str = ''                        # icone padrão (ui.icons); sobrescrito se o
                                           # ToolResult trouxer um mais específico (ex.: e-mail
                                           # que descobre em runtime se veio do Gmail ou Outlook)

    @property
    def name(self) -> str:
        return self.spec.name


class ToolRegistry:
    def __init__(self, tools: Sequence[Tool] = ()):
        self._tools: dict[str, Tool] = {t.name: t for t in tools}
        self._write_lock = threading.RLock()

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def subset(self, names: Sequence[str]) -> 'ToolRegistry':
        return ToolRegistry([self._tools[n] for n in names if n in self._tools])

    def specs(self) -> list[ToolSpec]:
        return [t.spec for t in self._tools.values()]

    def is_parallel_safe(self, name: str) -> bool:
        t = self._tools.get(name)
        return bool(t and t.spec.parallel_safe)

    def dispatch(self, call: ToolCall, ctx) -> ToolResult:
        """Executa uma tool call. Nunca levanta."""
        tool = self._tools.get(call.name)
        if tool is None:
            disponiveis = ', '.join(sorted(self._tools)) or '(nenhuma)'
            return fail('UNKNOWN_TOOL',
                        f"ferramenta '{call.name}' nao existe. Disponiveis: {disponiveis}")
        try:
            if tool.spec.parallel_safe:
                result = tool.fn(call.arguments or {}, ctx)
            else:
                with self._write_lock:
                    result = tool.fn(call.arguments or {}, ctx)
        except Exception as e:
            from core.tools.composio_exec import ComposioToolError
            if isinstance(e, ComposioToolError):
                result = fail(e.code, e.message)
            else:
                result = fail('TOOL_CRASH', f'{type(e).__name__}: {e}')
        if not result.icon and tool.icon:
            result.icon = tool.icon
        return result
