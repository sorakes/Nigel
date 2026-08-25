"""
core/meeting_prep.py — Prepara uma reunião antes dela começar.

Verifica periodicamente os próximos compromissos e, quando um está prestes a
começar, pede para o orquestrador (agenda_agent + email_agent + memory_agent)
montar um resumo — participantes, e-mails recentes relacionados, contexto já
conhecido — e entrega antes da reunião pegar o usuário de surpresa.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta

from PyQt6.QtCore import QThread, pyqtSignal

_POLL_INTERVAL_SEC = 300
_PREP_LEAD_MINUTES = 15  # avisa quando faltam ate esses minutos para comecar


def _parse(dt_str: str):
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    except ValueError:
        return None


def due_for_prep(events: list[dict], now: datetime = None,
                 lead_minutes: int = _PREP_LEAD_MINUTES) -> list[dict]:
    """Eventos que comecam dentro da janela de preparo, ainda nao vencidos."""
    out = []
    for ev in events:
        if ev.get('status') == 'cancelled':
            continue
        start = _parse(ev.get('start'))
        if not start:
            continue
        # Cada evento pode trazer tz proprio (ou nenhum); compara sempre com
        # um "agora" no mesmo referencial pra nao misturar aware com naive.
        ref_now = now
        if ref_now is None:
            ref_now = datetime.now(start.tzinfo) if start.tzinfo else datetime.now()
        elif start.tzinfo and ref_now.tzinfo is None:
            ref_now = ref_now.astimezone()
        elif not start.tzinfo and ref_now.tzinfo is not None:
            ref_now = ref_now.replace(tzinfo=None)
        delta_min = (start - ref_now).total_seconds() / 60
        if 0 <= delta_min <= lead_minutes:
            out.append(ev)
    return out


class MeetingPrepWorker(QThread):
    """Verifica periodicamente se uma reuniao esta prestes a comecar e monta
    um resumo com o que o Nigel sabe sobre ela."""

    prep_ready = pyqtSignal(dict, str)   # evento, resumo em texto

    def __init__(self):
        super().__init__()
        self._running = True
        self._prepped: set[str] = set()

    def stop(self):
        self._running = False

    def forget_all(self):
        self._prepped.clear()

    def _prep_summary(self, ev: dict) -> str:
        from core.tools import build_orchestrator_registry
        from core.agent.prompts import orchestrator_prompt
        from core.agent.loop import run_agent
        title = ev.get('summary', '(sem titulo)')
        start = ev.get('start', '')
        attendees = ', '.join(ev.get('attendees') or []) or 'nenhum listado'
        task = (
            f"A reunião '{title}' começa em breve (às {start}). Participantes: {attendees}. "
            "Monte um briefing curto de preparação: veja com o email_agent se há e-mails recentes "
            "relacionados a essa reunião ou a esses participantes, e com o memory_agent o que já se "
            "sabe sobre eles. Responda em poucas frases, direto ao ponto — o usuário vai ler isso "
            "nos minutos antes de entrar na reunião."
        )
        registry = build_orchestrator_registry()
        res = run_agent(orchestrator_prompt(), [{'role': 'user', 'content': task}],
                        registry, max_iterations=6)
        return (res.text or '').strip() or f"Reunião '{title}' às {start}. Sem informações adicionais."

    def _check_once(self):
        try:
            from core.agent.loop import new_context
            from core.agent.registry import ToolRegistry
            from core.llm.types import ToolCall
            from core.tools.calendar_tools import build_tools
            reg = ToolRegistry(build_tools())
            result = reg.dispatch(ToolCall('prep-check', 'calendar_list_events', {'days': 1}),
                                  new_context())
            if not result.ok:
                return
            events = (result.data or {}).get('events') or []
            for ev in due_for_prep(events):
                eid = ev.get('event_id') or ''
                if not eid or eid in self._prepped:
                    continue
                self._prepped.add(eid)
                try:
                    summary = self._prep_summary(ev)
                except Exception as e:
                    summary = f"Não consegui preparar a reunião '{ev.get('summary','')}': {e}"
                self.prep_ready.emit(ev, summary)
        except Exception as e:
            print(f'[Nigel] MeetingPrepWorker erro: {e}')

    def force_check(self):
        self._check_once()

    def run(self):
        self._check_once()
        while self._running:
            for _ in range(_POLL_INTERVAL_SEC):
                if not self._running:
                    return
                time.sleep(1)
            self._check_once()
