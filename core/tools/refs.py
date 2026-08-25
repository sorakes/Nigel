"""
core/tools/refs.py — Handles curtos para eventos de agenda.

IDs de evento do Google têm de 26 a 60 caracteres opacos (ex.:
`4pk9m1r8u3v0h2q7s5t6n4b1c8`). Modelos menores transcrevem errado com
frequência, e é aí que "cancela a reunião com o João" falha silenciosamente.

Toda ferramenta de leitura devolve, junto do `event_id` real, um handle curto
(`e1`, `e2`, ...). Ferramentas que alteram aceitam `event_id` OU `ref`.
"""

from __future__ import annotations

import threading


class EventRefCache:
    """Mapeia handles curtos -> (calendar_id, event_id). Um por conversa."""

    def __init__(self, limit: int = 120):
        self._lock = threading.RLock()
        self._by_ref: dict[str, tuple[str, str]] = {}
        self._by_event: dict[str, str] = {}
        self._n = 0
        self._limit = limit

    def put(self, event_id: str, calendar_id: str = 'primary') -> str:
        """Registra um evento e devolve seu handle (estável para o mesmo id)."""
        if not event_id:
            return ''
        with self._lock:
            existing = self._by_event.get(event_id)
            if existing:
                return existing
            self._n += 1
            ref = f'e{self._n}'
            self._by_ref[ref] = (calendar_id or 'primary', event_id)
            self._by_event[event_id] = ref
            if len(self._by_ref) > self._limit:
                oldest = next(iter(self._by_ref))
                _, ev = self._by_ref.pop(oldest)
                self._by_event.pop(ev, None)
            return ref

    def resolve(self, token: str) -> tuple[str, str] | None:
        """Aceita um handle (`e1`) ou um event_id cru. Devolve (calendar_id, event_id)."""
        if not token:
            return None
        t = str(token).strip()
        with self._lock:
            if t in self._by_ref:
                return self._by_ref[t]
            cal = None
            for c, ev in self._by_ref.values():
                if ev == t:
                    cal = c
                    break
        # Não é um handle conhecido: trata como event_id cru no calendário visto.
        return (cal or 'primary', t)

    def clear(self) -> None:
        with self._lock:
            self._by_ref.clear()
            self._by_event.clear()
            self._n = 0
