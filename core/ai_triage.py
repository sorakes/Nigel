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
    "You are a personal assistant that filters notifications.\n"
    "Analyze the message below and decide whether it needs IMMEDIATE attention.\n\n"
    "Treat as IMPORTANT:\n"
    "- Urgent requests from clients or colleagues\n"
    "- Messages with deadlines\n"
    "- Anything that needs a reply\n"
    "- Critical problems or errors reported\n\n"
    "IGNORE:\n"
    "- Newsletters and marketing emails\n"
    "- Automatic system notifications\n"
    "- Non-urgent calendar invites\n"
    "- Automatic confirmations\n\n"
    "Always answer in pure JSON, no markdown. Write summary and reason in Portuguese:\n"
    '{"important": true or false, "summary": "one-sentence summary", "reason": "classification reason"}'
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
        f"From: {message.get('sender', 'Unknown')}\n"
        f"Subject: {message.get('subject', '(no subject)')}\n"
        f"Preview: {message.get('body_preview', '')[:300]}"
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

def _call_openai_compat(api_key, base_url, model, messages, provider, max_tokens=256):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    if provider == 'openrouter':
        headers['HTTP-Referer'] = 'https://github.com/seq-widget'
        headers['X-Title'] = 'Nigel'

    resp = requests.post(
        f"{base_url}/chat/completions",
        headers=headers,
        json={"model": model, "messages": messages, "max_tokens": max_tokens, "stream": False},
        timeout=30
    )
    resp.raise_for_status()
    return resp.json()['choices'][0]['message']['content']

def _call_gemini(api_key, model, messages, max_tokens=256):
    contents = [{"role": m['role'] if m['role'] == 'user' else 'model', "parts": [{"text": m['content']}]} for m in messages]

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    resp = requests.post(
        url,
        json={"contents": contents, "generationConfig": {"maxOutputTokens": max_tokens}},
        timeout=30
    )
    resp.raise_for_status()
    return resp.json()['candidates'][0]['content']['parts'][0]['text']

def _call_ollama(model, messages, max_tokens=256):
    base_url = os.getenv('NIGEL_OLLAMA_URL', 'http://localhost:11434').rstrip('/')
    resp = requests.post(
        f"{base_url}/api/chat",
        json={"model": model, "messages": messages, "stream": False, "options": {"num_predict": max_tokens}},
        timeout=60
    )
    resp.raise_for_status()
    return resp.json()['message']['content']

_GRAPH_PROMPT = (
    "You are the relationship engine of a personal knowledge graph.\n"
    "You receive a list of nodes. Each node has an id, a type and some text.\n"
    "- type=persona means a fact about the user themselves (their identity, "
    "their people, their preferences). A node like 'persona:friend Leonardo' is a person the user knows.\n"
    "- other types (email, agenda, note...) are memories and events.\n\n"
    "Think the way a thoughtful person would about how these things actually relate:\n"
    "- Link a memory to a persona node when that memory genuinely involves that specific "
    "person or fact (an event with a friend links to that friend; a generic task does not link to "
    "unrelated people).\n"
    "- Link two memories when they truly share a person, project, subject or thread — "
    "not just a coincidental word.\n"
    "- Also estimate how relevant each node is to the user, from 1 to 100.\n\n"
    "Reason about meaning. Do not rely on fixed keyword lists. Prefer a few strong, honest "
    "connections over many weak ones; if two nodes are unrelated, leave them apart.\n\n"
    "Reply with ONLY pure JSON, no markdown:\n"
    '{"edges": [["idA", "idB"], ...], "scores": {"id": 70, ...}}'
)

def analyze_graph(nodes):
    """Let the AI decide the relationships between knowledge nodes."""
    if not nodes or len(nodes) < 2:
        return None

    lines = []
    for n in nodes:
        body = (n.get('body') or n.get('body_preview') or n.get('ai_summary') or '')
        body = ' '.join(str(body).split())[:180]
        title = ' '.join(str(n.get('title') or n.get('subject') or '').split())[:120]
        lines.append(f"- id={n.get('id')} | type={n.get('node_type', '')} | title={title} | text={body}")

    messages = [
        {"role": "system", "content": _GRAPH_PROMPT},
        {"role": "user", "content": "Nodes:\n" + "\n".join(lines)}
    ]

    try:
        provider_type, api_key, base_url, model, provider_name = _get_active_provider_config()

        if provider_type == 'openai_compat':
            response = _call_openai_compat(api_key, base_url, model, messages, provider_name, max_tokens=1024)
        elif provider_type == 'gemini':
            response = _call_gemini(api_key, model, messages, max_tokens=1024)
        elif provider_type == 'ollama':
            response = _call_ollama(model, messages, max_tokens=1024)
        else:
            return None

        clean = response.strip().strip('```json').strip('```').strip()
        start, end = clean.find('{'), clean.rfind('}')
        if start != -1 and end != -1:
            clean = clean[start:end + 1]
        data = json.loads(clean)

        edges = [p for p in data.get('edges', []) if isinstance(p, (list, tuple)) and len(p) == 2]
        scores = {str(k): int(v) for k, v in (data.get('scores') or {}).items() if str(v).lstrip('-').isdigit()}
        return {'edges': edges, 'scores': scores}

    except Exception as e:
        print(f"[Nigel] Graph analysis failed: {e}")
        return None
