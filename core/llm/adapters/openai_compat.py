"""
Adaptador OpenAI-compat: groq, openai, openrouter, ollama_cloud.

Particularidades:
- `function.arguments` vem como STRING JSON (as vezes '' ou '{}').
- O turno do assistente precisa voltar ao historico VERBATIM: os `id` das
  tool_calls tem que bater com os `tool_call_id` das respostas.
- Em streaming, os argumentos chegam fragmentados e indexados por `index`;
  `id` e `name` so aparecem no primeiro fragmento de cada indice.
"""

from __future__ import annotations


from core.llm.types import ToolSpec, ToolCall, LLMResponse, parse_arguments
from core.llm.schema import sanitize

PROVIDER_TYPE = 'openai_compat'


class _StreamAccumulator:
    """Junta os deltas de um stream SSE em um LLMResponse."""

    def __init__(self):
        self.text_parts: list[str] = []
        self._calls: dict[int, dict] = {}
        self._last_index = 0
        self.finish_reason = ''

    def feed(self, data: dict) -> str:
        """Consome um chunk ja desserializado. Devolve o delta de texto visivel."""
        choices = data.get('choices') or []
        if not choices:
            return ''
        choice = choices[0]
        if choice.get('finish_reason'):
            self.finish_reason = choice['finish_reason']
        delta = choice.get('delta') or choice.get('message') or {}

        out = delta.get('content') or ''
        if out:
            self.text_parts.append(out)

        for tc in (delta.get('tool_calls') or []):
            idx = tc.get('index')
            if idx is None:
                # Alguns upstreams do OpenRouter omitem `index`: continua o
                # ultimo aberto em vez de perder o fragmento.
                idx = self._last_index
            self._last_index = idx
            slot = self._calls.setdefault(idx, {'id': '', 'name': '', 'args': ''})
            if tc.get('id'):
                slot['id'] = tc['id']
            fn = tc.get('function') or {}
            if fn.get('name'):
                slot['name'] = fn['name']
            if fn.get('arguments'):
                slot['args'] += fn['arguments']
        return out

    def result(self) -> LLMResponse:
        text = ''.join(self.text_parts)
        calls, raw_calls = [], []
        for idx in sorted(self._calls):
            slot = self._calls[idx]
            if not slot['name']:
                continue
            cid = slot['id'] or f'call_{idx}'
            calls.append(ToolCall(id=cid, name=slot['name'],
                                  arguments=parse_arguments(slot['args'])))
            raw_calls.append({'id': cid, 'type': 'function',
                              'function': {'name': slot['name'],
                                           'arguments': slot['args'] or '{}'}})
        raw = {'role': 'assistant', 'content': text or None}
        if raw_calls:
            raw['tool_calls'] = raw_calls
        return LLMResponse(text=text, tool_calls=calls,
                           finish_reason=self.finish_reason or ('tool_calls' if calls else 'stop'),
                           raw_assistant_message=raw)


class OpenAICompatAdapter:
    provider_type = PROVIDER_TYPE

    def encode_tools(self, tools: list[ToolSpec]) -> list[dict]:
        return [{
            'type': 'function',
            'function': {
                'name': t.name,
                'description': t.description,
                'parameters': sanitize(t.parameters, PROVIDER_TYPE),
            },
        } for t in tools]

    def encode_messages(self, messages: list[dict]) -> list[dict]:
        return messages   # ja e' o formato nativo

    def build_payload(self, model, messages, tools, *, stream, max_tokens, tool_choice='auto') -> dict:
        payload = {
            'model': model,
            'messages': self.encode_messages(messages),
            'max_tokens': max_tokens,
            'stream': stream,
        }
        if tools:
            payload['tools'] = self.encode_tools(tools)
            payload['tool_choice'] = tool_choice
        return payload

    def parse_complete(self, body: dict) -> LLMResponse:
        choice = (body.get('choices') or [{}])[0]
        msg = choice.get('message') or {}
        calls = []
        for tc in (msg.get('tool_calls') or []):
            fn = tc.get('function') or {}
            calls.append(ToolCall(
                id=tc.get('id') or f"call_{len(calls)}",
                name=fn.get('name', ''),
                arguments=parse_arguments(fn.get('arguments')),
            ))
        return LLMResponse(
            text=msg.get('content') or '',
            tool_calls=calls,
            finish_reason=choice.get('finish_reason', ''),
            raw_assistant_message=msg,
        )

    def make_stream_accumulator(self):
        return _StreamAccumulator()

    def encode_tool_results(self, calls: list[ToolCall], results: list[str]) -> list[dict]:
        return [{'role': 'tool', 'tool_call_id': c.id, 'name': c.name, 'content': r}
                for c, r in zip(calls, results)]
