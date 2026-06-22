"""
core/api_client.py
Multi-provider LLM client with streaming support via QThread.
"""
import os
import json
import requests
from PyQt6.QtCore import QThread, pyqtSignal
from dotenv import load_dotenv

load_dotenv()

PROVIDERS: dict[str, dict] = {
    'groq': {
        'name': 'Groq',
        'base_url': 'https://api.groq.com/openai/v1',
        'env_key': 'SEQ_GROQ_API_KEY',
        'default_model': 'llama-3.1-70b-versatile',
        'models': ['llama-3.1-70b-versatile', 'llama-3.1-8b-instant', 'mixtral-8x7b-32768'],
        'type': 'openai_compat'
    },
    'openai': {
        'name': 'OpenAI',
        'base_url': 'https://api.openai.com/v1',
        'env_key': 'SEQ_OPENAI_API_KEY',
        'default_model': 'gpt-4o-mini',
        'models': ['gpt-4o', 'gpt-4o-mini', 'gpt-3.5-turbo'],
        'type': 'openai_compat'
    },
    'gemini': {
        'name': 'Gemini',
        'base_url': 'https://generativelanguage.googleapis.com/v1beta',
        'env_key': 'SEQ_GEMINI_API_KEY',
        'default_model': 'gemini-1.5-flash',
        'models': ['gemini-2.0-flash-exp', 'gemini-1.5-pro', 'gemini-1.5-flash'],
        'type': 'gemini'
    },
    'openrouter': {
        'name': 'OpenRouter',
        'base_url': 'https://openrouter.ai/api/v1',
        'env_key': 'SEQ_OPENROUTER_API_KEY',
        'default_model': 'meta-llama/llama-3.1-8b-instruct:free',
        'models': ['meta-llama/llama-3.1-8b-instruct:free', 'anthropic/claude-3.5-sonnet'],
        'type': 'openai_compat'
    },
    'ollama': {
        'name': 'Ollama (Local)',
        'base_url': None,
        'env_key': 'SEQ_OLLAMA_URL',
        'default_model': 'llama3',
        'models': [],
        'type': 'ollama'
    }
}

class StreamWorker(QThread):
    """Runs the LLM API call in a background thread and emits chunks as they arrive."""

    chunk_received = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, provider: str, messages: list[dict], model: str | None = None, parent=None):
        super().__init__()
        self.provider = provider
        self.messages = messages
        self.model = model
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            provider_type = PROVIDERS[self.provider]['type']
            if provider_type == 'openai_compat':
                self._run_openai_compat()
            elif provider_type == 'gemini':
                self._run_gemini()
            elif provider_type == 'ollama':
                self._run_ollama()
        except requests.exceptions.ConnectionError:
            self.error_occurred.emit('Connection error. Check your internet connection or Ollama URL.')
        except requests.exceptions.Timeout:
            self.error_occurred.emit('Request timed out. Try again.')
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else '?'
            self.error_occurred.emit(f"HTTP {status}: {e.response.text[:200] if e.response else str(e)}")
        except Exception as e:
            self.error_occurred.emit(str(e))

    def _run_openai_compat(self):
        cfg = PROVIDERS[self.provider]
        api_key = os.getenv(cfg['env_key'], '').strip()
        base_url = cfg['base_url']
        env_model_key = f"SEQ_{self.provider.upper()}_MODEL"
        model = self.model or os.getenv(env_model_key, '').strip() or cfg['default_model']
        headers = {
            'Authorization': f"Bearer {api_key}",
            'Content-Type': 'application/json'
        }
        if self.provider == 'openrouter':
            headers['HTTP-Referer'] = 'https://github.com/seq-widget'
            headers['X-Title'] = 'Seq Widget'
        payload = {
            'model': model,
            'messages': self.messages,
            'stream': True,
            'max_tokens': 2048
        }
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
            stream=True,
            timeout=30
        )
        resp.raise_for_status()
        for raw in resp.iter_lines():
            if self._stop:
                return
            if not raw:
                continue
            line = raw.decode('utf-8')
            if line.startswith('data: '):
                data = line[6:]
                if data.strip() == '[DONE]':
                    return
                try:
                    chunk = json.loads(data)
                    delta = chunk['choices'][0]['delta']
                    content = delta.get('content', '')
                    if content:
                        self.chunk_received.emit(content)
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue

    def _run_gemini(self):
        api_key = os.getenv('SEQ_GEMINI_API_KEY', '').strip()
        model = self.model or os.getenv('SEQ_GEMINI_MODEL', '').strip() or PROVIDERS['gemini']['default_model']
        system_parts = []
        contents = []
        for msg in self.messages:
            role = msg.get('role', 'user')
            if role == 'system':
                system_parts.append(msg['content'])
                continue
            gemini_role = 'user' if role == 'user' else 'model'
            contents.append({
                'role': gemini_role,
                'parts': [{'text': msg['content']}]
            })
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?key={api_key}&alt=sse"
        payload = {
            'contents': contents,
            'generationConfig': {'maxOutputTokens': 2048}
        }
        if system_parts:
            payload['systemInstruction'] = {'parts': [{'text': '\n\n'.join(system_parts)}]}
        resp = requests.post(url, json=payload, stream=True, timeout=30)
        resp.raise_for_status()
        for raw in resp.iter_lines():
            if self._stop:
                return
            if not raw:
                continue
            line = raw.decode('utf-8')
            if line.startswith('data: '):
                data = line[6:]
                try:
                    chunk = json.loads(data)
                    text = chunk['candidates'][0]['content']['parts'][0]['text']
                    if text:
                        self.chunk_received.emit(text)
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue

    def _run_ollama(self):
        base_url = os.getenv('SEQ_OLLAMA_URL', 'http://localhost:11434').rstrip('/')
        model = self.model or os.getenv('SEQ_OLLAMA_MODEL', 'llama3')
        payload = {
            'model': model,
            'messages': self.messages,
            'stream': True
        }
        resp = requests.post(
            f"{base_url}/api/chat",
            json=payload,
            stream=True,
            timeout=60
        )
        resp.raise_for_status()
        for raw in resp.iter_lines():
            if self._stop:
                return
            if not raw:
                continue
            try:
                chunk = json.loads(raw.decode('utf-8'))
                text = chunk.get('message', {}).get('content', '')
                if text:
                    self.chunk_received.emit(text)
                if chunk.get('done', False):
                    return
            except (json.JSONDecodeError, KeyError):
                continue

class APIClient:
    """Facade for managing providers, settings, and creating stream workers."""

    def __init__(self):
        load_dotenv(override=True)

    def reload(self):
        """Reloads environment variables from the .env file."""
        load_dotenv(override=True)

    def get_active_provider(self) -> str | None:
        """
        Gets the currently active and configured provider.
        Priority: SEQ_ACTIVE_PROVIDER > first available provider.
        """
        explicit = os.getenv('SEQ_ACTIVE_PROVIDER', '').strip()
        if explicit and explicit in PROVIDERS:
            if self._provider_has_credentials(explicit):
                return explicit
        for key in PROVIDERS:
            if self._provider_has_credentials(key):
                return key
        return None

    def _provider_has_credentials(self, provider: str) -> bool:
        cfg = PROVIDERS[provider]
        val = os.getenv(cfg['env_key'], '').strip()
        return bool(val)

    def get_provider_info(self, provider: str) -> dict:
        """Returns the configuration dictionary for a given provider."""
        return PROVIDERS.get(provider, {})

    def create_worker(self, messages: list[dict], provider: str | None = None, model: str | None = None) -> StreamWorker:
        """
        Creates and returns a StreamWorker for the given provider and messages.
        If provider is not specified, it uses the active provider.
        """
        if provider is None:
            provider = self.get_active_provider()
        if provider is None:
            raise ValueError('Nenhum provider configurado.\nAbra Settings (4 pontinhos → ⚙ Settings) e adicione uma chave de API.')
        return StreamWorker(provider, messages, model)

    def get_settings(self) -> dict:
        """Returns a dictionary of all current settings from the environment."""
        load_dotenv(override=True)
        return {
            'SEQ_ACTIVE_PROVIDER': os.getenv('SEQ_ACTIVE_PROVIDER', ''),
            'SEQ_GROQ_API_KEY': os.getenv('SEQ_GROQ_API_KEY', ''),
            'SEQ_OPENAI_API_KEY': os.getenv('SEQ_OPENAI_API_KEY', ''),
            'SEQ_GEMINI_API_KEY': os.getenv('SEQ_GEMINI_API_KEY', ''),
            'SEQ_OPENROUTER_API_KEY': os.getenv('SEQ_OPENROUTER_API_KEY', ''),
            'SEQ_OLLAMA_URL': os.getenv('SEQ_OLLAMA_URL', ''),
            'SEQ_GROQ_MODEL': os.getenv('SEQ_GROQ_MODEL', PROVIDERS['groq']['default_model']),
            'SEQ_OPENAI_MODEL': os.getenv('SEQ_OPENAI_MODEL', PROVIDERS['openai']['default_model']),
            'SEQ_GEMINI_MODEL': os.getenv('SEQ_GEMINI_MODEL', PROVIDERS['gemini']['default_model']),
            'SEQ_OPENROUTER_MODEL': os.getenv('SEQ_OPENROUTER_MODEL', PROVIDERS['openrouter']['default_model']),
            'SEQ_OLLAMA_MODEL': os.getenv('SEQ_OLLAMA_MODEL', PROVIDERS['ollama']['default_model']),
            'SEQ_BAR_WIDTH': os.getenv('SEQ_BAR_WIDTH', '600'),
            'SEQ_BAR_HEIGHT': os.getenv('SEQ_BAR_HEIGHT', '60')
        }

    def save_settings(self, new_values: dict):
        """Saves a dictionary of settings to the .env file."""
        env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
        existing = {}
        if os.path.exists(env_path):
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        k, v = line.split('=', 1)
                        existing[k.strip()] = v.strip()
        existing.update(new_values)
        with open(env_path, 'w', encoding='utf-8') as f:
            f.write('# Seq Widget — configurações geradas automaticamente\n\n')
            for (k, v) in existing.items():
                f.write(f"{k}={v}\n")
        load_dotenv(dotenv_path=env_path, override=True)
