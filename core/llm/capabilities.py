"""
core/llm/capabilities.py — Quais pares (provider, modelo) suportam tool calling.

Vários modelos locais do Ollama e modelos gratuitos do OpenRouter ignoram ou
rejeitam `tools`. A detecção é por FALHA, não por sondagem: tenta com tools;
se vier um 400/422 mencionando tool/function, rebaixa o par, persiste, e o
cliente repete uma vez no caminho de texto. Custo: uma requisição perdida por
modelo, uma única vez.

Chaveado por (provider, modelo) e não só por provider — o OpenRouter faz proxy
de upstreams arbitrários com capacidades diferentes.
"""

from __future__ import annotations

import threading

from core.storage import load_config, save_config

_CONFIG_KEY = 'llm_tool_support'
_lock = threading.RLock()
_cache: dict[str, bool] | None = None

# Trechos que indicam "este modelo não faz tool calling", e não outro erro.
_UNSUPPORTED_HINTS = (
    'does not support tools',
    'does not support function',
    'tools is not supported',
    'tool use is not supported',
    'function calling is not supported',
    'unsupported parameter: tools',
    'unknown field: tools',
    'no endpoints found that support tool use',
)


def _key(provider: str, model: str) -> str:
    return f'{provider}::{model}'


def _load() -> dict:
    global _cache
    if _cache is None:
        raw = load_config().get(_CONFIG_KEY) or {}
        _cache = {k: bool(v) for k, v in raw.items()} if isinstance(raw, dict) else {}
    return _cache


def supports_tools(provider: str, model: str) -> bool | None:
    """True/False se já se sabe; None se ainda não foi testado."""
    with _lock:
        return _load().get(_key(provider, model))


def record(provider: str, model: str, value: bool) -> None:
    with _lock:
        cache = _load()
        k = _key(provider, model)
        if cache.get(k) == value:
            return
        cache[k] = value
        save_config({_CONFIG_KEY: dict(cache)})


def is_malformed_tool_call(status: int, body: str) -> bool:
    """400 causado por o MODELO ter emitido uma tool call invalida.

    Diferente de `looks_like_no_tool_support`: aqui o provider aceita tools, o
    modelo e que errou o formato. Vale tentar de novo em vez de desistir.
    """
    if status not in (400, 422):
        return False
    t = (body or '').lower()
    return ('invalid tool call' in t or 'invalid tool_call' in t
            or 'tool call arguments' in t or 'malformed' in t)


def looks_like_no_tool_support(status: int, body: str) -> bool:
    """Distingue 'modelo não faz tools' de qualquer outro erro HTTP."""
    if status not in (400, 404, 422, 500):
        return False
    text = (body or '').lower()
    # Somente marcas EXPLÍCITAS de falta de suporte. Um regex genérico do tipo
    # "tool" + "invalid" casava com "invalid tool call arguments" — que é o
    # modelo errando o formato, não falta de suporte — e rebaixava o par
    # (provider, modelo) permanentemente no cache, fazendo o cliente parar de
    # enviar `tools` em TODAS as requisições seguintes.
    return any(h in text for h in _UNSUPPORTED_HINTS)
