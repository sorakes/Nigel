"""
core/chat_compliance.py — Compliance auditor: did Nigel actually follow the rules?

Runs after the intent gate. Ensures agenda tools exist when promised and get executed.
"""

import json

from core.ai_triage import call_llm_json
from core.chat_intent_gate import _skills_snapshot

_COMPLIANCE_PROMPT = (
    "You are Nigel's compliance auditor — the last critical check before the user sees the reply.\n"
    "The main AI must follow these rules:\n"
    "- If it tells the user a reminder was created/scheduled/updated, there MUST be a valid agenda "
    "tool in JSON \"actions\" (create_schedule, update_schedule, etc.). Words alone do not count.\n"
    "- If detective curiosity is still active (unknown important gaps remain), it must NOT claim "
    "the reminder exists and must NOT put create_schedule in actions yet.\n"
    "- If investigation is complete and the user expects the reminder, create_schedule must be in actions.\n\n"
    "You receive the user message, Nigel's reply, gate decision, tool snapshot and detective context.\n"
    "Return ONLY pure JSON:\n"
    '{"must_execute_agenda": false, "has_valid_agenda_json": false, "needs_fix": false, '
    '"fix_hint": "optional English hint", "override_gate_mode": null}\n'
    "override_gate_mode may be execute_agenda, ask_context, conversation, or null to keep gate decision."
)


def _visible_claims_agenda_done(text: str) -> bool:
    from ui.agenda_skills import visible_text
    v = (visible_text(text or '') or text or '').lower()
    if not v:
        return False
    markers = (
        'lembrete criado', 'lembrete marcado', 'agendei', 'vou criar o lembrete',
        'criei o lembrete', 'está agendado', 'esta agendado', 'está marcado', 'esta marcado',
        'reminder created', 'scheduled for', 'i created the reminder', 'i scheduled',
    )
    return any(m in v for m in markers)


def _local_audit(assistant_reply: str, gate_mode: str) -> dict:
    snap = _skills_snapshot(assistant_reply)
    has_json = bool(snap.get('agenda_in_actions'))
    claims_done = _visible_claims_agenda_done(assistant_reply)

    result = {
        'must_execute_agenda': False,
        'has_valid_agenda_json': has_json,
        'needs_fix': False,
        'fix_hint': '',
        'override_gate_mode': None,
    }

    if gate_mode == 'ask_context' and has_json:
        result['needs_fix'] = True
        result['fix_hint'] = 'Curiosity mode: move agenda from actions to pending_buttons; do not claim done.'
        return result

    if has_json and gate_mode != 'execute_agenda':
        result['must_execute_agenda'] = True
        result['override_gate_mode'] = 'execute_agenda'
        return result

    if claims_done and not has_json:
        result['must_execute_agenda'] = True
        result['needs_fix'] = True
        result['fix_hint'] = (
            'The reply claims a reminder was created but actions JSON is missing. '
            'Add create_schedule (or correct agenda action) in actions.'
        )
        return result

    if gate_mode == 'execute_agenda' and not has_json:
        result['must_execute_agenda'] = True
        result['needs_fix'] = True
        result['fix_hint'] = 'Gate expects agenda execution but actions JSON is missing.'
        return result

    if gate_mode == 'execute_agenda' and has_json:
        result['must_execute_agenda'] = True
        return result

    return result


def audit(
    user_text: str,
    assistant_reply: str,
    gate_mode: str = 'conversation',
    learned_facts: list | None = None,
    detective_original: str = '',
) -> dict:
    local = _local_audit(assistant_reply, gate_mode)
    if local.get('needs_fix') or local.get('override_gate_mode'):
        return local
    if local.get('must_execute_agenda'):
        return local

    snap = _skills_snapshot(assistant_reply)
    block = (
        f"User message:\n{user_text}\n\n"
        f"Gate mode: {gate_mode}\n\n"
        f"Nigel reply:\n{assistant_reply}\n\n"
        f"Tool snapshot:\n{json.dumps(snap, ensure_ascii=False)}\n\n"
        f"Detective original request:\n{detective_original or '(none)'}\n\n"
        f"Learned this thread:\n{json.dumps(learned_facts or [], ensure_ascii=False)}"
    )
    messages = [
        {'role': 'system', 'content': _COMPLIANCE_PROMPT},
        {'role': 'user', 'content': block},
    ]

    try:
        data = call_llm_json(messages, max_tokens=384)
        if not data:
            return local
        merged = dict(local)
        merged['must_execute_agenda'] = bool(data.get('must_execute_agenda', merged['must_execute_agenda']))
        merged['has_valid_agenda_json'] = bool(data.get('has_valid_agenda_json', merged['has_valid_agenda_json']))
        merged['needs_fix'] = bool(data.get('needs_fix', merged['needs_fix']))
        hint = str(data.get('fix_hint') or '').strip()
        if hint:
            merged['fix_hint'] = hint
        override = data.get('override_gate_mode')
        if override in ('execute_agenda', 'ask_context', 'conversation'):
            merged['override_gate_mode'] = override
        return merged
    except Exception as e:
        print(f"[Nigel] Compliance audit failed: {e}")
        return local


def build_compliance_fix_messages(user_text: str, draft: str, fix_hint: str = '') -> list[dict]:
    sys = (
        "You are Nigel fixing a reply that FAILED compliance audit. The user was told a reminder "
        "would exist but the agenda JSON tool is missing or wrong. Return ONLY the corrected full "
        "reply in the user's language with ```json containing the correct agenda action in "
        "\"actions\" for immediate execution. Do not claim done without that JSON block."
    )
    if fix_hint:
        sys += f"\n\nAuditor hint: {fix_hint}"
    return [
        {'role': 'system', 'content': sys},
        {'role': 'user', 'content': f"User request:\n{user_text}\n\nNon-compliant draft:\n{draft}"},
    ]
