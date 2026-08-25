"""Adaptadores de formato de fio por tipo de provider."""

from core.llm.adapters.openai_compat import OpenAICompatAdapter
from core.llm.adapters.gemini import GeminiAdapter
from core.llm.adapters.ollama import OllamaAdapter

_ADAPTERS = {
    'openai_compat': OpenAICompatAdapter,
    'gemini': GeminiAdapter,
    'ollama': OllamaAdapter,
}


def get_adapter(provider_type: str):
    try:
        return _ADAPTERS[provider_type]()
    except KeyError:
        raise ValueError(f"Tipo de provider sem adaptador: {provider_type!r}")
