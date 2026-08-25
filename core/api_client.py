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
    # Padroes revisados em 2026-08-24 depois de dois achados: o antigo padrao
    # do Groq (`llama-3.3-70b-versatile`) e do Gemini (`gemini-2.0-flash`)
    # foram DESCONTINUADOS pelos provedores — ver docs oficiais checadas ao
    # vivo. Escolha daqui pra frente prioriza, nessa ordem: (1) chamada de
    # ferramenta NATIVA confiavel — inclusive varias no mesmo turno, que e'
    # o padrao comum do Nigel (agenda_agent + email_agent juntos); (2) custo;
    # so' depois (3) velocidade. Onde deu pra testar de verdade (Ollama
    # Cloud, unica chave configurada nesta maquina), o padrao escolhido
    # passou em bateria de tool-calling real, nao mockada — ver
    # scratch/bench_tools.py. Nos outros, a escolha e' o mais barato entre
    # os que o catalogo publico do provedor confirma suportar `tools`.
    'groq': {
        'name': 'Groq',
        'base_url': 'https://api.groq.com/openai/v1',
        'env_key': 'NIGEL_GROQ_API_KEY',
        'default_model': 'openai/gpt-oss-120b',
        'models': ['openai/gpt-oss-120b', 'openai/gpt-oss-20b', 'groq/compound'],
        'type': 'openai_compat'
    },
    'openai': {
        'name': 'OpenAI',
        'base_url': 'https://api.openai.com/v1',
        'env_key': 'NIGEL_OPENAI_API_KEY',
        'default_model': 'gpt-5.6-luna',
        'models': ['gpt-5.6-luna', 'gpt-5-mini', 'gpt-5.6-terra'],
        'type': 'openai_compat'
    },
    'gemini': {
        'name': 'Gemini',
        'base_url': 'https://generativelanguage.googleapis.com/v1beta',
        'env_key': 'NIGEL_GEMINI_API_KEY',
        'default_model': 'gemini-2.5-flash-lite',
        'models': ['gemini-2.5-flash-lite', 'gemini-2.5-flash', 'gemini-3.5-flash-lite'],
        'type': 'gemini'
    },
    'openrouter': {
        'name': 'OpenRouter',
        'base_url': 'https://openrouter.ai/api/v1',
        'env_key': 'NIGEL_OPENROUTER_API_KEY',
        # Nao usa mais um modelo ":free" — esses tendem a ser fracos em tool
        # calling e sao rate-limited a parte (ver bench_tools.py: modelos
        # ~8B falham chamada de ferramenta com frequencia). gpt-oss-120b via
        # OpenRouter e' o mesmo modelo validado ao vivo via Ollama Cloud,
        # com preco por token confirmado no catalogo publico deles.
        'default_model': 'openai/gpt-oss-120b',
        'models': ['openai/gpt-oss-120b', 'openai/gpt-oss-20b', 'qwen/qwen3-30b-a3b-instruct-2507'],
        'type': 'openai_compat'
    },
    'ollama': {
        'name': 'Ollama (Local)',
        'base_url': None,
        'env_key': 'NIGEL_OLLAMA_URL',
        # 'llama3' (sem tag) nem baixa mais por esse nome no Ollama atual.
        # Testado ao vivo nesta maquina, 3x cada, uma ferramenta e depois
        # duas no mesmo turno: llama3.1:8b foi o UNICO 100% (6/6) — os
        # modelos menores (llama3.2:3b, qwen2.5:3b/7b) acertam o caso simples
        # mas falham quase sempre a chamada paralela. Roda em ~5GB de RAM/VRAM,
        # cabe em laptop comum; e' o piso recomendado pra uso local de verdade.
        'default_model': 'llama3.1:8b',
        'models': ['llama3.1:8b', 'qwen3:8b', 'llama3.2:3b'],
        'type': 'ollama'
    },
    'ollama_cloud': {
        'name': 'Ollama Cloud',
        'base_url': 'https://ollama.com/v1',
        'env_key': 'NIGEL_OLLAMA_CLOUD_API_KEY',
        # minimax-m3 foi o UNICO, em 3 rodadas seguidas, que acertou duas
        # ferramentas no mesmo turno (agenda + e-mail juntos) — o padrao real
        # de uso do Nigel. gpt-oss:120b acerta o caso simples e e' ~2x mais
        # rapido, mas so' faz uma ferramenta por vez; fica como alternativa
        # pra quando velocidade importa mais que cobrir o caso paralelo.
        'default_model': 'minimax-m3',
        'models': ['minimax-m3', 'gpt-oss:120b', 'gpt-oss:20b'],
        'type': 'openai_compat'
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
        env_model_key = f"NIGEL_{self.provider.upper()}_MODEL"
        model = self.model or os.getenv(env_model_key, '').strip() or cfg['default_model']
        headers = {
            'Authorization': f"Bearer {api_key}",
            'Content-Type': 'application/json'
        }
        if self.provider == 'openrouter':
            headers['HTTP-Referer'] = 'https://github.com/nigel-widget'
            headers['X-Title'] = 'Nigel'
        payload = {
            'model': model,
            'messages': self.messages,
            'stream': True,
            'max_tokens': 4096
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
        api_key = os.getenv('NIGEL_GEMINI_API_KEY', '').strip()
        model = self.model or os.getenv('NIGEL_GEMINI_MODEL', '').strip() or PROVIDERS['gemini']['default_model']
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
            'generationConfig': {'maxOutputTokens': 4096}
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
        base_url = (os.getenv('NIGEL_OLLAMA_URL') or 'http://localhost:11434').rstrip('/')
        model = self.model or os.getenv('NIGEL_OLLAMA_MODEL', 'llama3')
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
        Priority: NIGEL_ACTIVE_PROVIDER > first available provider.
        """
        explicit = os.getenv('NIGEL_ACTIVE_PROVIDER', '').strip()
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

    def resolve_runtime(self, provider: str | None = None) -> dict:
        """
        Same provider/model/key resolution as StreamWorker — used by gate, compliance, graph, triage.
        """
        load_dotenv(override=True)
        active = provider or self.get_active_provider()
        if not active:
            raise ValueError('Nenhum provider LLM configurado.')
        info = PROVIDERS[active]
        api_key = (os.getenv(info['env_key']) or '').strip()
        if not api_key:
            from core.storage import load_config
            api_key = (load_config().get(f'api_key_{active}') or '').strip()
        env_model_key = f'NIGEL_{active.upper()}_MODEL'
        model = (os.getenv(env_model_key) or '').strip() or (info.get('default_model') or '')
        base_url = info.get('base_url') or ''
        if active == 'ollama':
            base_url = (os.getenv('NIGEL_OLLAMA_URL') or 'http://localhost:11434').rstrip('/')
        return {
            'provider': active,
            'type': info['type'],
            'api_key': api_key,
            'base_url': base_url,
            'model': model,
        }

    def call_llm(self, messages: list[dict], max_tokens: int = 512, provider: str | None = None) -> str:
        """Non-streaming LLM call using the active provider (same config as chat)."""
        rt = self.resolve_runtime(provider)
        ptype = rt['type']
        if ptype == 'openai_compat':
            return _openai_compat_completion(
                rt['api_key'], rt['base_url'], rt['model'], messages, rt['provider'], max_tokens
            )
        if ptype == 'gemini':
            return _gemini_completion(rt['api_key'], rt['model'], messages, max_tokens)
        if ptype == 'ollama':
            return _ollama_completion(rt['base_url'], rt['model'], messages, max_tokens)
        raise ValueError(f"Provider não suportado: {rt['provider']}")

    def create_worker(self, messages: list[dict], provider: str | None = None, model: str | None = None) -> StreamWorker:
        if provider is None:
            provider = self.get_active_provider()
        if provider is None:
            raise ValueError('Nenhum provider configurado.\nAbra Settings (4 pontinhos → ⚙ Settings) e adicione uma chave de API.')
        return StreamWorker(provider, messages, model)

    def get_settings(self) -> dict:
        load_dotenv(override=True)
        return {
            'NIGEL_ACTIVE_PROVIDER': os.getenv('NIGEL_ACTIVE_PROVIDER', ''),
            'NIGEL_GROQ_API_KEY': os.getenv('NIGEL_GROQ_API_KEY', ''),
            'NIGEL_OPENAI_API_KEY': os.getenv('NIGEL_OPENAI_API_KEY', ''),
            'NIGEL_GEMINI_API_KEY': os.getenv('NIGEL_GEMINI_API_KEY', ''),
            'NIGEL_OPENROUTER_API_KEY': os.getenv('NIGEL_OPENROUTER_API_KEY', ''),
            'NIGEL_OLLAMA_URL': os.getenv('NIGEL_OLLAMA_URL', ''),
            'NIGEL_OLLAMA_CLOUD_API_KEY': os.getenv('NIGEL_OLLAMA_CLOUD_API_KEY', ''),
            'NIGEL_GROQ_MODEL': os.getenv('NIGEL_GROQ_MODEL', PROVIDERS['groq']['default_model']),
            'NIGEL_OPENAI_MODEL': os.getenv('NIGEL_OPENAI_MODEL', PROVIDERS['openai']['default_model']),
            'NIGEL_GEMINI_MODEL': os.getenv('NIGEL_GEMINI_MODEL', PROVIDERS['gemini']['default_model']),
            'NIGEL_OPENROUTER_MODEL': os.getenv('NIGEL_OPENROUTER_MODEL', PROVIDERS['openrouter']['default_model']),
            'NIGEL_OLLAMA_MODEL': os.getenv('NIGEL_OLLAMA_MODEL', PROVIDERS['ollama']['default_model']),
            'NIGEL_OLLAMA_CLOUD_MODEL': os.getenv('NIGEL_OLLAMA_CLOUD_MODEL', PROVIDERS['ollama_cloud']['default_model']),
            'NIGEL_BAR_WIDTH': os.getenv('NIGEL_BAR_WIDTH', '600'),
            'NIGEL_BAR_HEIGHT': os.getenv('NIGEL_BAR_HEIGHT', '60'),
        }

    def save_settings(self, new_values: dict):
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
            f.write('# Nigel — configurações geradas automaticamente\n\n')
            for k, v in existing.items():
                f.write(f'{k}={v}\n')
        load_dotenv(dotenv_path=env_path, override=True)


def _openai_compat_headers(provider: str, api_key: str) -> dict:
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    if provider == 'openrouter':
        headers['HTTP-Referer'] = 'https://github.com/nigel-widget'
        headers['X-Title'] = 'Nigel'
    return headers


def _openai_compat_completion(api_key, base_url, model, messages, provider, max_tokens=512) -> str:
    base_url = (base_url or '').rstrip('/')
    resp = requests.post(
        f'{base_url}/chat/completions',
        headers=_openai_compat_headers(provider, api_key),
        json={'model': model, 'messages': messages, 'max_tokens': max_tokens, 'stream': False},
        timeout=60,
    )
    if not resp.ok:
        detail = resp.text[:300] if resp.text else resp.reason
        raise requests.HTTPError(f'{resp.status_code} {detail}', response=resp)
    content = resp.json()['choices'][0]['message'].get('content') or ''
    return content


def _gemini_completion(api_key, model, messages, max_tokens=512) -> str:
    system_parts = []
    contents = []
    for msg in messages:
        role = msg.get('role', 'user')
        if role == 'system':
            system_parts.append(msg['content'])
            continue
        gemini_role = 'user' if role == 'user' else 'model'
        contents.append({'role': gemini_role, 'parts': [{'text': msg['content']}]})
    payload = {'contents': contents, 'generationConfig': {'maxOutputTokens': max_tokens}}
    if system_parts:
        payload['systemInstruction'] = {'parts': [{'text': '\n\n'.join(system_parts)}]}
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}'
    resp = requests.post(url, json=payload, timeout=60)
    resp.raise_for_status()
    parts = resp.json().get('candidates', [{}])[0].get('content', {}).get('parts', [{}])
    return (parts[0].get('text') if parts else '') or ''


def _ollama_completion(base_url, model, messages, max_tokens=512) -> str:
    resp = requests.post(
        f'{base_url.rstrip("/")}/api/chat',
        json={'model': model, 'messages': messages, 'stream': False, 'options': {'num_predict': max_tokens}},
        timeout=90,
    )
    resp.raise_for_status()
    return resp.json()['message']['content']
