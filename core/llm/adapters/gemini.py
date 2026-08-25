"""
Adaptador Gemini.

Particularidades que o tornam o mais arriscado dos três:
- Não existe `tool_call_id`. O pareamento `functionCall` -> `functionResponse`
  é por NOME. Se o modelo chamar a mesma ferramenta duas vezes no mesmo turno
  a resposta fica ambígua, então colapsamos para a primeira ocorrência.
- `args` já vem como objeto.
- Papéis são 'user'/'model'; `system` vai em `systemInstruction`.
- O schema precisa passar pelo sanitizador (subconjunto do OpenAPI 3.0).
"""

from __future__ import annotations

from core.llm.types import ToolSpec, ToolCall, LLMResponse
from core.llm.schema import sanitize

PROVIDER_TYPE = 'gemini'


class _StreamAccumulator:
    """Gemini não fragmenta functionCall: cada chunk traz partes completas."""

    def __init__(self):
        self.text_parts: list[str] = []
        self.parts: list[dict] = []
        self.finish_reason = ''

    def feed(self, data: dict) -> str:
        cands = data.get('candidates') or []
        if not cands:
            return ''
        cand = cands[0]
        if cand.get('finishReason'):
            self.finish_reason = cand['finishReason']
        out = ''
        for part in ((cand.get('content') or {}).get('parts') or []):
            self.parts.append(part)
            if part.get('text'):
                self.text_parts.append(part['text'])
                out += part['text']
        return out

    def result(self) -> LLMResponse:
        return _build(self.text_parts, self.parts, self.finish_reason)


def _build(text_parts, parts, finish_reason) -> LLMResponse:
    text = ''.join(text_parts)
    calls, seen = [], set()
    for part in parts:
        fc = part.get('functionCall')
        if not fc:
            continue
        name = fc.get('name', '')
        if not name or name in seen:
            continue   # ver nota sobre ambiguidade no docstring do módulo
        seen.add(name)
        args = fc.get('args')
        calls.append(ToolCall(id=f'gem_{len(calls)}', name=name,
                              arguments=args if isinstance(args, dict) else {}))
    raw = {'role': 'model', 'parts': parts or ([{'text': text}] if text else [])}
    return LLMResponse(text=text, tool_calls=calls,
                       finish_reason=finish_reason or ('tool_calls' if calls else 'stop'),
                       raw_assistant_message=raw)


class GeminiAdapter:
    provider_type = PROVIDER_TYPE

    def encode_tools(self, tools: list[ToolSpec]) -> list[dict]:
        return [{'functionDeclarations': [{
            'name': t.name,
            'description': t.description,
            'parameters': sanitize(t.parameters, PROVIDER_TYPE),
        } for t in tools]}]

    def encode_messages(self, messages: list[dict]):
        """Devolve (contents, system_instruction)."""
        system, contents = [], []
        for m in messages:
            role = m.get('role', 'user')
            if role == 'system':
                system.append(m.get('content') or '')
                continue
            if role == 'tool':
                contents.append({'role': 'user', 'parts': [{'functionResponse': {
                    'name': m.get('name') or m.get('tool_call_id') or 'tool',
                    'response': {'result': m.get('content') or ''},
                }}]})
                continue
            if role in ('model', 'assistant') and isinstance(m.get('parts'), list):
                contents.append({'role': 'model', 'parts': m['parts']})
                continue
            contents.append({'role': 'model' if role == 'assistant' else 'user',
                             'parts': [{'text': m.get('content') or ''}]})
        return contents, '\n\n'.join(p for p in system if p)

    def build_payload(self, model, messages, tools, *, stream, max_tokens, tool_choice='auto') -> dict:
        contents, system = self.encode_messages(messages)
        payload = {'contents': contents, 'generationConfig': {'maxOutputTokens': max_tokens}}
        if system:
            payload['systemInstruction'] = {'parts': [{'text': system}]}
        if tools:
            payload['tools'] = self.encode_tools(tools)
            mode = 'NONE' if tool_choice == 'none' else 'AUTO'
            payload['toolConfig'] = {'functionCallingConfig': {'mode': mode}}
        return payload

    def parse_complete(self, body: dict) -> LLMResponse:
        cand = (body.get('candidates') or [{}])[0]
        parts = (cand.get('content') or {}).get('parts') or []
        texts = [p['text'] for p in parts if p.get('text')]
        return _build(texts, parts, cand.get('finishReason', ''))

    def make_stream_accumulator(self):
        return _StreamAccumulator()

    def encode_tool_results(self, calls: list[ToolCall], results: list[str]) -> list[dict]:
        # Um único turno 'user' com todas as functionResponse, casadas por nome.
        return [{'role': 'user', 'parts': [
            {'functionResponse': {'name': c.name, 'response': {'result': r}}}
            for c, r in zip(calls, results)
        ]}]
