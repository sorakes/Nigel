"""
core/ai_triage.py — Classificador de importância de mensagens.

Usa o LLM ativo do usuário (configurado no Settings) para decidir
se uma mensagem merece notificação com base no prompt de filtro do usuário.

Retorna: {"important": bool, "summary": str, "reason": str}
"""

import json
import requests
import os
from core.storage import load_config

_DEFAULT_TRIAGE_PROMPT = (
    "Você é um assistente pessoal que filtra notificações.\n"
    "Analise a mensagem abaixo e decida se ela precisa de atenção IMEDIATA.\n\n"
    "Critérios padrão para ser IMPORTANTE:\n"
    "- Pedidos urgentes de clientes ou colegas\n"
    "- Mensagens com prazos ou deadlines\n"
    "- Qualquer coisa que precise de uma resposta\n"
    "- Problemas ou erros críticos reportados\n\n"
    "Critérios para IGNORAR:\n"
    "- Newsletters e e-mails de marketing\n"
    "- Notificações automáticas de sistemas\n"
    "- Convites de calendário sem urgência\n"
    "- Confirmações automáticas\n\n"
    "Responda SEMPRE em JSON puro, sem markdown:\n"
    '{"important": true ou false, "summary": "resumo em 1 frase", "reason": "motivo da classificação"}'
)

def _get_active_provider_config():
    from core.api_client import PROVIDERS
    config = load_config()
    active = config.get('active_provider', '')

    if active and active in PROVIDERS:
        for key, info in PROVIDERS.items():
            env_key = info['env_key']
            val = os.getenv(env_key, '').strip() or config.get(f'api_key_{key}', '')
            if val:
                active = key
                break

    if not active:
        raise ValueError('Nenhum provider LLM configurado.')

    info = PROVIDERS[active]
    api_key = os.getenv(info['env_key'], '').strip() or config.get(f'api_key_{active}', '')
    model = config.get(f'model_{active}', info.get('default_model', ''))
    base_url = info.get('base_url', '')

    return info['type'], api_key, base_url, model, active

def classify(message):
    config = load_config()
    triage_prompt = config.get('triage_prompt', _DEFAULT_TRIAGE_PROMPT)

    message_text = (
        f"De: {message.get('sender', 'Desconhecido')}\n"
        f"Assunto: {message.get('subject', '(sem assunto)')}\n"
        f"Prévia: {message.get('body_preview', '')[:300]}"
    )

    messages = [
        {"role": "system", "content": triage_prompt},
        {"role": "user", "content": message_text}
    ]

    try:
        provider_type, api_key, base_url, model, provider_name = _get_active_provider_config()

        if provider_type in ('openai_compat',):
            response = _call_openai_compat(api_key, base_url, model, messages, provider_name)
        elif provider_type == 'gemini':
            response = _call_gemini(api_key, model, messages)
        elif provider_type == 'ollama':
            response = _call_ollama(model, messages)
        else:
            return {"important": False, "summary": "", "reason": "Provider não suportado"}

        clean = response.strip().strip('```json').strip('```').strip()
        result = json.loads(clean)

        return {
            "important": bool(result.get('important', False)),
            "summary": result.get('summary', ''),
            "reason": result.get('reason', '')
        }

    except (json.JSONDecodeError, ValueError) as e:
        print(f"[Triage] Erro ao parsear resposta da IA: {e}")
        return {"important": False, "summary": "", "reason": "Erro de classificação"}
    except Exception as e:
        print(f"[Triage] Erro ao classificar: {e}")
        return {"important": False, "summary": "", "reason": str(e)}

def _call_openai_compat(api_key, base_url, model, messages, provider):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    if provider == 'openrouter':
        headers['HTTP-Referer'] = 'https://github.com/seq-widget'
        headers['X-Title'] = 'SEQ Assistant'

    resp = requests.post(
        f"{base_url}/chat/completions",
        headers=headers,
        json={"model": model, "messages": messages, "max_tokens": 256, "stream": False},
        timeout=15
    )
    resp.raise_for_status()
    return resp.json()['choices'][0]['message']['content']

def _call_gemini(api_key, model, messages):
    contents = [{"role": m['role'] if m['role'] == 'user' else 'model', "parts": [{"text": m['content']}]} for m in messages]

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    resp = requests.post(
        url,
        json={"contents": contents, "generationConfig": {"maxOutputTokens": 256}},
        timeout=15
    )
    resp.raise_for_status()
    return resp.json()['candidates'][0]['content']['parts'][0]['text']

def _call_ollama(model, messages):
    base_url = os.getenv('SEQ_OLLAMA_URL', 'http://localhost:11434').rstrip('/')
    resp = requests.post(
        f"{base_url}/api/chat",
        json={"model": model, "messages": messages, "stream": False},
        timeout=30
    )
    resp.raise_for_status()
    return resp.json()['message']['content']
