"""
core/llm/text_tools.py — Resgata tool calls que o modelo escreveu como TEXTO.

Modelos menores (minimax, vários locais do Ollama, alguns gratuitos do
OpenRouter) às vezes ignoram o canal de tool calling e escrevem a chamada na
resposta, em formatos proprietários:

    [TOOL_CALL]
    {tool => "agenda_agent", args => { --task "cancela a reuniao" }}

    <minimax:tool_call><invoke name="agenda_agent">
      <parameter name="task">cancela a reuniao</parameter></invoke>

    ```json
    {"tool_calls": [{"name": "agenda_agent", "arguments": {"task": "..."}}]}
    ```

Sem isso, o usuário vê essa marcação crua no chat e nada é executado. Com isso,
a chamada é resgatada e o loop segue normalmente — o que faz o Nigel funcionar
em modelos que não fazem tool calling nativo direito.
"""

from __future__ import annotations

import json
import re

from core.llm.types import ToolCall, parse_arguments

# <invoke name="x"><parameter name="y">z</parameter>...</invoke>
_INVOKE = re.compile(
    r'<\s*invoke\s+name\s*=\s*["\']([\w.-]+)["\']\s*>(.*?)(?:</\s*invoke\s*>|$)',
    re.IGNORECASE | re.DOTALL)
_PARAM = re.compile(
    r'<\s*parameter\s+name\s*=\s*["\']([\w.-]+)["\']\s*>(.*?)(?:</\s*parameter\s*>|$)',
    re.IGNORECASE | re.DOTALL)

# {"tool_calls": [...]} ou {"name": ..., "arguments": {...}}
_JSON_FENCE = re.compile(r'```(?:json|tool_code)?\s*([\s\S]*?)```', re.IGNORECASE)

# {tool => "x", args => { --chave "valor" ... }}   (estilo minimax)
_ARROW = re.compile(
    r'\{\s*tool\s*=>\s*["\']([\w.-]+)["\']\s*,\s*args\s*=>\s*\{(.*?)(?:\}\s*\}|$)',
    re.IGNORECASE | re.DOTALL)
_ARROW_KV = re.compile(r'--([\w.-]+)\s+("(?:[^"\\]|\\.)*"|\S+)')


def _mk(name: str, args: dict, n: int) -> ToolCall:
    return ToolCall(id=f'txt_{n}', name=name, arguments=args if isinstance(args, dict) else {})


def _from_invoke(text: str) -> list[ToolCall]:
    out = []
    for m in _INVOKE.finditer(text):
        name, body = m.group(1), m.group(2)
        args = {k: v.strip() for k, v in _PARAM.findall(body)}
        out.append(_mk(name, args, len(out)))
    return out


def _from_arrow(text: str) -> list[ToolCall]:
    out = []
    for m in _ARROW.finditer(text):
        name, body = m.group(1), m.group(2)
        args = {}
        for k, v in _ARROW_KV.findall(body):
            v = v.strip()
            if v.startswith('"') and v.endswith('"') and len(v) > 1:
                try:
                    v = json.loads(v)
                except json.JSONDecodeError:
                    v = v[1:-1]
            args[k] = v
        out.append(_mk(name, args, len(out)))
    return out


def _from_json(text: str) -> list[ToolCall]:
    blobs = [b.strip() for b in _JSON_FENCE.findall(text)]
    if not blobs:
        start, end = text.find('{'), text.rfind('}')
        if start != -1 and end > start:
            blobs = [text[start:end + 1]]

    out = []
    for blob in blobs:
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        calls = data.get('tool_calls') or data.get('tool_call') or data.get('actions')
        if isinstance(calls, dict):
            calls = [calls]
        if not isinstance(calls, list):
            if data.get('name'):
                calls = [data]
            else:
                continue
        for c in calls:
            if not isinstance(c, dict):
                continue
            name = c.get('name') or c.get('tool') or c.get('function') or c.get('type')
            if isinstance(name, dict):
                name = name.get('name')
            if not name:
                continue
            raw_args = (c.get('arguments') if 'arguments' in c else
                        c.get('args') if 'args' in c else
                        c.get('parameters') if 'parameters' in c else
                        {k: v for k, v in c.items()
                         if k not in ('name', 'tool', 'function', 'type')})
            out.append(_mk(str(name), parse_arguments(raw_args), len(out)))
    return out


# [nome_da_ferramenta] tarefa em texto livre, no inicio de uma linha.
# So aceito quando o nome bate EXATAMENTE com uma ferramenta conhecida, senao
# qualquer colchete em texto normal viraria uma chamada.
_BRACKET = re.compile(r'^[ \t]*(?:[\[*]{1,2}\s*)?([a-z][\w.-]*?)(?:\s*[\]*]{1,2})?\s*:\s*(.+)$'
                      r'|^[ \t]*[\[*]{1,2}\s*([a-z][\w.-]*)\s*[\]*]{1,2}\s*(.+)$',
                      re.MULTILINE)


def _from_bracket(text: str, valid_names: set[str] | None) -> list[ToolCall]:
    if not valid_names:
        return []
    out = []
    for m in _BRACKET.finditer(text):
        name = m.group(1) or m.group(3)
        task = (m.group(2) or m.group(4) or '').strip()
        if not name or name not in valid_names or not task:
            continue
        out.append(_mk(name, {'task': task}, len(out)))
    return out


def recover(text: str, valid_names: set[str] | None = None) -> list[ToolCall]:
    """Extrai tool calls escritas como texto. Devolve [] quando não há nenhuma."""
    if not text:
        return []
    calls = (_from_invoke(text) or _from_arrow(text) or _from_json(text)
             or _from_bracket(text, valid_names))
    if valid_names is not None:
        calls = [c for c in calls if c.name in valid_names]
    return calls


def has_tool_marker(text: str) -> bool:
    """Heurística barata: vale a pena tentar o resgate neste texto?"""
    if not text:
        return False
    t = text.lower()
    if any(m in t for m in (
            '[tool_call', '<invoke', 'tool_call>', '"tool_calls"', 'tool =>', '<function_calls')):
        return True
    # possivel formato [nome_da_ferramenta] ...
    return bool(re.search(r'^[ \t]*[\[*]{0,2}\s*[a-z][\w.-]*\s*[\]*]{0,2}\s*:', text, re.MULTILINE))
