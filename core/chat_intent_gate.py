"""
core/chat_intent_gate.py — Last subjective check before Nigel's chat reply is shown.

Decides whether this moment is about executing agenda tools, asking for personal
context, or normal conversation. No keyword lists — the model reasons from meaning.
"""

import json

from core.ai_triage import call_llm_json

_GATE_PROMPT = (
    "You are Nigel's intent gate — the final check before the UI renders a chat reply.\n"
    "You receive the user's message, Nigel's reviewed reply, and a factual snapshot of "
    "what tool JSON (if any) is already embedded.\n\n"
    "Think about what this moment is really about:\n"
    "- execute_agenda: the user wants something scheduled, updated, postponed, completed or "
    "canceled, and Nigel should run the agenda tool now. The reply must include a valid agenda "
    "JSON block. Curiosity is not the priority here.\n"
    "- ask_context: Nigel still lacks context about someone/something important in the request, OR "
    "this is a detective continuation where the original request still has meaningful unknowns "
    "(places, objects, relationships, ownership, timelines...) not yet in known_memory or learned_facts. "
    "One answer about Mariana does NOT mean the apartment is understood. Keep asking.\n"
    "- conversation: normal chat, memory, or explanation — no agenda execution required right now.\n\n"
    "Reason from meaning, not keyword lists. A clear scheduling request with enough context "
    "is execute_agenda. But if the user mentions someone by name for an appointment, visit, "
    "meeting or personal event, and that person/place/thing is NOT in known_memory below, and the draft "
    "already scheduled without asking — that should be ask_context with persona_ui true, not execute_agenda.\n\n"
    "Also verify tool shape:\n"
    "- execute_agenda requires agenda tool JSON in the reply (create/update/reschedule/etc.). "
    "If the text promises scheduling but JSON is missing or only has clarification, set needs_tool_fix true.\n"
    "- ask_context requires clarification plus pending_buttons with the deferred agenda action. "
    "If the text asks for context but JSON is wrong or missing, set needs_tool_fix true.\n\n"
    "persona_ui (purple bubble in the app):\n"
    "- true when Nigel is in curiosity mode — asking the user to explain a person, place, thing, "
    "project, company or context that is NOT already in known_memory below.\n"
    "- true for ask_context always.\n"
    "- also true for conversation when Nigel's reply invites the user to teach something missing "
    "(e.g. 'who is X to you?', 'tell me more about X', 'what is that place?') — even without agenda pending.\n"
    "- false when Nigel is only answering from existing memory or doing schedule/confirm work.\n\n"
    "Return ONLY pure JSON, no markdown:\n"
    '{"mode": "execute_agenda"|"ask_context"|"conversation", "persona_ui": false, '
    '"curiosity_subject": "optional name or topic", "needs_tool_fix": false, "fix_hint": "optional"}'
)

_FIX_AGENDA_PROMPT = (
    "You are Nigel fixing a reply that promised to schedule or change a reminder but forgot "
    "the agenda tool JSON block. Return ONLY the corrected full reply in the user's language, "
    "with a ```json block containing the correct agenda action in \"actions\" for immediate execution."
)

_FIX_CONTEXT_PROMPT = (
    "You are Nigel fixing a reply that needs personal context before scheduling or learning. Return ONLY "
    "the corrected full reply in the user's language, with ```json containing \"clarification\" "
    "(required for the purple curiosity bubble). If a schedule was deferred, put the agenda action inside "
    "\"pending_buttons\" — not in \"actions\"."
)


def _skills_snapshot(text: str) -> dict:
    from ui.agenda_skills import parse_skills_json

    data = parse_skills_json(text or '')
    agenda_types = frozenset({
        'create_schedule', 'update_schedule', 'reschedule', 'mark_done',
        'delete_schedule', 'postpone',
    })
    if not data:
        return {
            'has_tool_json': False,
            'has_clarification': False,
            'agenda_in_actions': False,
            'agenda_in_pending': False,
            'has_buttons': False,
        }

    def _has_agenda(block):
        if not isinstance(block, list):
            return False
        for item in block:
            if isinstance(item, dict) and item.get('type') in agenda_types:
                return True
            if isinstance(item, dict) and item.get('confirm_action', {}).get('type') in agenda_types:
                return True
        return False

    actions = data.get('actions') or []
    pending = data.get('pending_buttons') or []
    buttons = data.get('buttons') or []
    return {
        'has_tool_json': True,
        'has_clarification': isinstance(data.get('clarification'), dict),
        'agenda_in_actions': _has_agenda(actions),
        'agenda_in_pending': _has_agenda(pending),
        'has_buttons': bool(buttons or pending),
    }


def _memory_entities_snapshot() -> list[str]:
    try:
        from core.database import SeqDB
        db = SeqDB.get_instance()
        graph = db.get_knowledge_graph(limit=80)
        entities = []
        for n in graph.get('nodes', []):
            title = (n.get('title') or n.get('subject') or '').strip()
            if title:
                entities.append(title)
        for item in db.get_saved_items(limit=30):
            subj = (item.get('subject') or item.get('ai_summary') or '').strip()
            if subj and subj not in entities:
                entities.append(subj)
        return entities[:40]
    except Exception:
        return []


def _persona_names_snapshot() -> list[str]:
    try:
        from core.database import SeqDB
        graph = SeqDB.get_instance().get_knowledge_graph(limit=80)
        names = []
        for n in graph.get('nodes', []):
            if n.get('node_type') != 'persona':
                continue
            title = (n.get('title') or n.get('subject') or '').strip()
            if title:
                names.append(title)
        return names[:24]
    except Exception:
        return []


def evaluate(user_text: str, assistant_reply: str, learned_facts: list | None = None) -> dict | None:
    """Return gate decision or None on failure."""
    user_text = (user_text or '').strip()
    assistant_reply = (assistant_reply or '').strip()
    if not assistant_reply:
        return {'mode': 'conversation', 'needs_tool_fix': False, 'fix_hint': ''}

    snap = _skills_snapshot(assistant_reply)
    known_memory = _memory_entities_snapshot()
    learned = learned_facts or []
    user_block = (
        f"User message:\n{user_text}\n\n"
        f"Nigel reviewed reply:\n{assistant_reply}\n\n"
        f"Tool snapshot (facts only, not rules):\n{json.dumps(snap, ensure_ascii=False)}\n\n"
        f"known_memory (already stored):\n{json.dumps(known_memory, ensure_ascii=False)}\n\n"
        f"learned_facts (user taught Nigel THIS thread, not yet fully in memory):\n"
        f"{json.dumps(learned, ensure_ascii=False)}"
    )
    messages = [
        {'role': 'system', 'content': _GATE_PROMPT},
        {'role': 'user', 'content': user_block},
    ]

    try:
        data = call_llm_json(messages, max_tokens=512)
        if not data:
            return None
        mode = str(data.get('mode', 'conversation')).strip().lower()
        if mode not in ('execute_agenda', 'ask_context', 'conversation'):
            mode = 'conversation'
        persona_ui = bool(data.get('persona_ui', False))
        if mode == 'ask_context':
            persona_ui = True
        return {
            'mode': mode,
            'persona_ui': persona_ui,
            'curiosity_subject': str(data.get('curiosity_subject') or '').strip(),
            'needs_tool_fix': bool(data.get('needs_tool_fix', False)),
            'fix_hint': str(data.get('fix_hint') or '').strip(),
        }
    except Exception as e:
        print(f"[Nigel] Intent gate failed: {e}")
        return None


def build_tool_fix_messages(user_text: str, draft: str, mode: str, fix_hint: str = '') -> list[dict]:
    """Messages for a short fix pass when the gate detects missing/wrong tools."""
    sys = _FIX_AGENDA_PROMPT if mode == 'execute_agenda' else _FIX_CONTEXT_PROMPT
    if fix_hint:
        sys += f"\n\nHint: {fix_hint}"
    return [
        {'role': 'system', 'content': sys},
        {'role': 'user', 'content': f"User request:\n{user_text}\n\nDraft reply to fix:\n{draft}"},
    ]
