"""
core/llm/client.py — Cliente LLM unificado com tool calling.

Substitui o caminho de chamada de `core/api_client.py`. A resolução de
provider/modelo/chave continua vindo de lá (`resolve_runtime`), que já funciona
bem e é o que a tela de Settings usa.

Regras de streaming, por adaptador:
  openai_compat + tools -> stream (o acumulador junta os fragmentos)
  gemini        + tools -> stream (functionCall chega inteiro)
  ollama        + tools -> FORÇADO não-stream (builds antigos descartam `tools`)
  qualquer      s/ tools -> stream
"""

from __future__ import annotations

import json
import threading

import requests

from core.llm import capabilities
from core.llm.adapters import get_adapter
from core.llm.sanitize_text import clean as clean_text
from core.llm.types import ToolSpec, ToolCall, LLMResponse

DEFAULT_MAX_TOKENS = 4096
DEFAULT_TIMEOUT = 90


class LLMError(RuntimeError):
    def __init__(self, message: str, status: int = 0, body: str = ''):
        super().__init__(message)
        self.status = status
        self.body = body


class ToolsUnsupported(LLMError):
    """O par (provider, modelo) não aceita `tools`. O chamador cai no fallback."""


class MalformedToolCall(LLMError):
    """O modelo emitiu uma tool call inválida. Vale repetir o turno."""


class LLMClient:
    def __init__(self, provider: str | None = None):
        from core.api_client import APIClient
        self._rt = APIClient().resolve_runtime(provider)
        self.provider = self._rt['provider']
        self.provider_type = self._rt['type']
        self.model = self._rt['model']
        self.adapter = get_adapter(self.provider_type)

    # ------------------------------------------------------------------ infra

    def _url(self, stream: bool) -> str:
        base = (self._rt['base_url'] or '').rstrip('/')
        if self.provider_type == 'gemini':
            verb = 'streamGenerateContent' if stream else 'generateContent'
            suffix = '&alt=sse' if stream else ''
            return (f'https://generativelanguage.googleapis.com/v1beta/models/'
                    f'{self.model}:{verb}?key={self._rt["api_key"]}{suffix}')
        if self.provider_type == 'ollama':
            return f'{base}/api/chat'
        return f'{base}/chat/completions'

    def _headers(self) -> dict:
        if self.provider_type == 'gemini':
            return {'Content-Type': 'application/json'}
        h = {'Content-Type': 'application/json'}
        if self.provider_type == 'openai_compat':
            h['Authorization'] = f'Bearer {self._rt["api_key"]}'
            if self.provider == 'openrouter':
                h['HTTP-Referer'] = 'https://github.com/sorakes/Nigel'
                h['X-Title'] = 'Nigel'
        return h

    def _should_stream(self, want_stream: bool, tools) -> bool:
        if not want_stream:
            return False
        if tools and self.provider_type == 'ollama':
            return False   # ver docstring do módulo
        return True

    # ------------------------------------------------------------------ chamada

    def complete(
        self,
        messages: list[dict],
        tools: list[ToolSpec] | None = None,
        *,
        stream: bool = False,
        on_text=None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        tool_choice: str = 'auto',
        timeout: int = DEFAULT_TIMEOUT,
        cancel: threading.Event | None = None,
        allow_tool_fallback: bool = True,
    ) -> LLMResponse:
        """Uma rodada com o modelo. `on_text(delta)` recebe o texto conforme chega."""
        tools = tools or []
        if tools and allow_tool_fallback and capabilities.supports_tools(self.provider, self.model) is False:
            raise ToolsUnsupported(f'{self.provider}/{self.model} nao suporta tools (em cache)')

        do_stream = self._should_stream(stream, tools)
        payload = self.adapter.build_payload(
            self.model, messages, tools,
            stream=do_stream, max_tokens=max_tokens, tool_choice=tool_choice,
        )

        try:
            resp = requests.post(self._url(do_stream), headers=self._headers(),
                                 json=payload, stream=do_stream, timeout=timeout)
        except requests.exceptions.Timeout as e:
            raise LLMError(f'Tempo esgotado falando com {self.provider}.') from e
        except requests.exceptions.ConnectionError as e:
            raise LLMError(f'Sem conexao com {self.provider}.') from e

        if not resp.ok:
            body = ''
            try:
                body = resp.text[:800]
            except Exception:
                pass
            if tools and capabilities.is_malformed_tool_call(resp.status_code, body):
                raise MalformedToolCall(
                    'o modelo emitiu uma chamada de ferramenta invalida.', resp.status_code, body)
            if tools and capabilities.looks_like_no_tool_support(resp.status_code, body):
                capabilities.record(self.provider, self.model, False)
                raise ToolsUnsupported(
                    f'{self.provider}/{self.model} rejeitou `tools`.', resp.status_code, body)
            raise LLMError(f'HTTP {resp.status_code}: {body}', resp.status_code, body)

        if tools:
            capabilities.record(self.provider, self.model, True)

        result = self._read_stream(resp, on_text, cancel) if do_stream else \
            self.adapter.parse_complete(resp.json())

        # Modelos menores as vezes escrevem a tool call como TEXTO em vez de
        # usar o canal proprio; isso nunca deve chegar ao balao de chat.
        result.text = clean_text(result.text)

        if not do_stream and on_text and result.text:
            on_text(result.text)
        return result

    def _read_stream(self, resp, on_text, cancel) -> LLMResponse:
        acc = self.adapter.make_stream_accumulator()
        for raw in resp.iter_lines():
            if cancel is not None and cancel.is_set():
                break
            if not raw:
                continue
            line = raw.decode('utf-8', errors='replace').strip()
            if self.provider_type == 'ollama':
                chunk = line
            else:
                if not line.startswith('data:'):
                    continue
                chunk = line[5:].strip()
                if chunk == '[DONE]':
                    break
            try:
                data = json.loads(chunk)
            except json.JSONDecodeError:
                continue
            delta = acc.feed(data)
            if delta and on_text:
                on_text(delta)
        return acc.result()

    # ------------------------------------------------------------------ atalhos

    def text(self, messages: list[dict], max_tokens: int = 1024, **kw) -> str:
        return self.complete(messages, max_tokens=max_tokens, **kw).text

    def encode_tool_results(self, calls: list[ToolCall], results: list[str]) -> list[dict]:
        return self.adapter.encode_tool_results(calls, results)
