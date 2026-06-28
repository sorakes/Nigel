"""
core/ai_triage.py — Classificador de importância de mensagens + LLM helpers compartilhados.
"""

import json
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


def call_llm_json(messages: list[dict], max_tokens: int = 512) -> dict | None:
    """Call active provider and parse JSON from response."""
    from core.api_client import APIClient
    try:
        response = APIClient().call_llm(messages, max_tokens=max_tokens)
        if not response:
            return None
        clean = response.strip().strip('```json').strip('```').strip()
        start, end = clean.find('{'), clean.rfind('}')
        if start != -1 and end != -1:
            clean = clean[start:end + 1]
        return json.loads(clean)
    except Exception as e:
        print(f"[Nigel] LLM JSON call failed: {e}")
        return None


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
        {"role": "user", "content": message_text},
    ]
    try:
        result = call_llm_json(messages, max_tokens=256)
        if not result:
            return {"important": False, "summary": "", "reason": "Erro de classificação"}
        return {
            "important": bool(result.get('important', False)),
            "summary": result.get('summary', ''),
            "reason": result.get('reason', ''),
        }
    except Exception as e:
        print(f"[Triage] Erro ao classificar: {e}")
        return {"important": False, "summary": "", "reason": str(e)}


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
        {"role": "user", "content": "Nodes:\n" + "\n".join(lines)},
    ]

    try:
        data = call_llm_json(messages, max_tokens=1024)
        if not data:
            return None
        edges = [p for p in data.get('edges', []) if isinstance(p, (list, tuple)) and len(p) == 2]
        scores = {str(k): int(v) for k, v in (data.get('scores') or {}).items() if str(v).lstrip('-').isdigit()}
        return {'edges': edges, 'scores': scores}
    except Exception as e:
        print(f"[Nigel] Graph analysis failed: {e}")
        return None
