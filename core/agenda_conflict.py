"""
core/agenda_conflict.py — Detecta conflito de horário na agenda real antes que
o usuário precise perguntar.

Consulta direta ao `calendar_list_events` (sem passar pelo LLM — é só uma
verificação periódica, não vale o custo de uma rodada de agente) e compara
os intervalos par a par. Roda a cada 5 minutos: frequência baixa o bastante
para não pesar na cota do Google Calendar, alta o bastante para avisar antes
de uma reunião dupla pegar o usuário de surpresa.
"""

from __future__ import annotations

import time
from datetime import datetime

from PyQt6.QtCore import QThread, pyqtSignal

_POLL_INTERVAL_SEC = 300


def _parse(dt_str: str):
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    except ValueError:
        return None


def _overlaps(a: dict, b: dict) -> bool:
    a_start, a_end = _parse(a.get('start')), _parse(a.get('end'))
    b_start, b_end = _parse(b.get('start')), _parse(b.get('end'))
    if not (a_start and a_end and b_start and b_end):
        return False
    return a_start < b_end and b_start < a_end


def find_conflicts(events: list[dict]) -> list[tuple[dict, dict]]:
    """Pares de eventos cujos horários se sobrepõem (evento cancelado já filtrado fora)."""
    pares = []
    for i in range(len(events)):
        for j in range(i + 1, len(events)):
            a, b = events[i], events[j]
            if a.get('event_id') and a.get('event_id') == b.get('event_id'):
                continue
            if _overlaps(a, b):
                pares.append((a, b))
    return pares


class AgendaConflictWorker(QThread):
    """Verifica periodicamente se dois compromissos reais se sobrepõem."""

    conflict_found = pyqtSignal(dict, dict)

    def __init__(self):
        super().__init__()
        self._running = True
        self._notified: set[frozenset] = set()

    def stop(self):
        self._running = False

    def forget_all(self):
        self._notified.clear()

    def _check_once(self):
        try:
            from core.agent.loop import new_context
            from core.agent.registry import ToolRegistry
            from core.llm.types import ToolCall
            from core.tools.calendar_tools import build_tools
            reg = ToolRegistry(build_tools())
            result = reg.dispatch(ToolCall('conflict-check', 'calendar_list_events', {'days': 2}),
                                  new_context())
            if not result.ok:
                return
            events = [e for e in (result.data or {}).get('events') or []
                     if e.get('status') != 'cancelled']
            for a, b in find_conflicts(events):
                key = frozenset({a.get('event_id'), b.get('event_id')})
                if key in self._notified:
                    continue
                self._notified.add(key)
                self.conflict_found.emit(a, b)
        except Exception as e:
            print(f'[Nigel] AgendaConflictWorker erro: {e}')

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
