"""
core/llm/types.py — Tipos neutros de provider para tool calling.

O resto do app fala nestes tipos; cada adaptador em core/llm/adapters traduz
para o formato de fio do seu provider.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolSpec:
    """Descricao de uma ferramenta oferecida ao modelo."""
    name: str
    description: str
    parameters: dict          # JSON Schema, sempre type=object
    parallel_safe: bool = False   # somente leitura -> pode rodar em paralelo


@dataclass
class ToolCall:
    """Pedido de execucao emitido pelo modelo. `arguments` ja vem como dict."""
    id: str
    name: str
    arguments: dict = field(default_factory=dict)


@dataclass
class LLMResponse:
    text: str = ''
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = ''
    # Turno do assistente no formato NATIVO do provider. Precisa voltar ao
    # historico exatamente como veio: a OpenAI exige que os ids de tool_calls
    # batam com os tool_call_id das respostas.
    raw_assistant_message: Any = None

    @property
    def wants_tools(self) -> bool:
        return bool(self.tool_calls)


def parse_arguments(raw: Any) -> dict:
    """Normaliza os argumentos de uma tool call para dict.

    OpenAI-compat manda string JSON (as vezes vazia); Ollama e Gemini mandam
    objeto. Modelos pequenos as vezes mandam JSON com aspas simples ou um dict
    aninhado em {"arguments": ...}.
    """
    if raw is None or raw == '':
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            val = json.loads(raw)
        except json.JSONDecodeError:
            try:
                import ast
                val = ast.literal_eval(raw)
            except Exception:
                return {'_raw': raw}
        return val if isinstance(val, dict) else {'value': val}
    return {'value': raw}
