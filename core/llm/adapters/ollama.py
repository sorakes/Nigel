"""
Adaptador Ollama local (/api/chat).

Particularidades:
- Aceita `tools` no formato de função da OpenAI.
- `arguments` já vem como OBJETO, e não há `id` de tool call.
- Builds mais antigos descartam `tools` silenciosamente quando `stream: true`;
  por isso o cliente força não-streaming sempre que houver ferramentas.
"""

from __future__ import annotations

from core.llm.types import ToolSpec, ToolCall, LLMResponse, parse_arguments
from core.llm.schema import sanitize

PROVIDER_TYPE = 'ollama'


class _StreamAccumulator:
    def __init__(self):
        self.text_parts: list[str] = []
        self.calls_raw: list[dict] = []
        self.done = False

    def feed(self, data: dict) -> str:
        msg = data.get('message') or {}
        out = msg.get('content') or ''
        if out:
            self.text_parts.append(out)
        for tc in (msg.get('tool_calls') or []):
            self.calls_raw.append(tc)
        if data.get('done'):
            self.done = True
        return out

    def result(self) -> LLMResponse:
        return _build(''.join(self.text_parts), self.calls_raw)


def _build(text: str, raw_calls: list[dict]) -> LLMResponse:
    calls = []
    for tc in raw_calls:
        fn = tc.get('function') or {}
        name = fn.get('name', '')
        if not name:
            continue
        calls.append(ToolCall(id=f'oll_{len(calls)}', name=name,
                              arguments=parse_arguments(fn.get('arguments'))))
    raw = {'role': 'assistant', 'content': text}
    if raw_calls:
        raw['tool_calls'] = raw_calls
    return LLMResponse(text=text, tool_calls=calls,
                       finish_reason='tool_calls' if calls else 'stop',
                       raw_assistant_message=raw)


class OllamaAdapter:
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
        out = []
        for m in messages:
            if m.get('role') == 'tool':
                out.append({'role': 'tool', 'content': m.get('content') or '',
                            'tool_name': m.get('name') or ''})
            else:
                out.append(m)
        return out

    def build_payload(self, model, messages, tools, *, stream, max_tokens, tool_choice='auto') -> dict:
        payload = {
            'model': model,
            'messages': self.encode_messages(messages),
            'stream': stream,
            'options': {'num_predict': max_tokens},
        }
        if tools:
            payload['tools'] = self.encode_tools(tools)
        return payload

    def parse_complete(self, body: dict) -> LLMResponse:
        msg = body.get('message') or {}
        return _build(msg.get('content') or '', msg.get('tool_calls') or [])

    def make_stream_accumulator(self):
        return _StreamAccumulator()

    def encode_tool_results(self, calls: list[ToolCall], results: list[str]) -> list[dict]:
        return [{'role': 'tool', 'name': c.name, 'content': r}
                for c, r in zip(calls, results)]
