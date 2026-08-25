"""
core/llm/sanitize_text.py — Limpa artefatos de tool call do texto visivel.

Modelos menores as vezes EMITEM a chamada de ferramenta como texto em vez de
usar o canal de tool calling: blocos tipo `<minimax:tool_call>`, `<invoke ...>`,
`<function_calls>` ou um bloco ```json solto. Sem isso, essa marcacao vaza
direto para o balao de chat do usuario.
"""

from __future__ import annotations

import re

_PATTERNS = [
    re.compile(r'<\s*[a-z_]*:?tool_calls?\b.*?(?:</\s*[a-z_]*:?tool_calls?\s*>|$)',
               re.IGNORECASE | re.DOTALL),
    re.compile(r'<\s*function_calls\b.*?(?:</\s*function_calls\s*>|$)',
               re.IGNORECASE | re.DOTALL),
    re.compile(r'<\s*invoke\b.*?(?:</\s*invoke\s*>|$)', re.IGNORECASE | re.DOTALL),
    re.compile(r'<\s*parameter\b.*?(?:</\s*parameter\s*>|$)', re.IGNORECASE | re.DOTALL),
    re.compile(r'<\|?(?:tool_call|tool_code|function_call)\|?>.*?$',
               re.IGNORECASE | re.DOTALL),
]

_JSON_BLOCK = re.compile(
    r'```(?:json|tool_code)?\s*\{[\s\S]*?\}\s*```', re.IGNORECASE)

_THINK = re.compile(r'<\s*(think|thinking|reasoning)\s*>.*?</\s*\1\s*>',
                    re.IGNORECASE | re.DOTALL)


def clean(text: str) -> str:
    """Remove marcacao de ferramenta do texto destinado ao usuario."""
    if not text:
        return ''
    out = _THINK.sub('', text)
    for pat in _PATTERNS:
        out = pat.sub('', out)
    if '"tool_calls"' in out or '"arguments"' in out or '"name":' in out:
        out = _JSON_BLOCK.sub('', out)
    out = re.sub(r'\n{3,}', '\n\n', out)
    return out.strip()


def looks_empty(text: str) -> bool:
    """True quando so sobrou marcacao (nada util para mostrar)."""
    return not clean(text).strip()
