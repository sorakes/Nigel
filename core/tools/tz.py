"""
core/tools/tz.py — Fuso horário do usuário, em nome IANA.

As ferramentas de calendário do Composio assumem **UTC** quando `timezone` não
é informado. Sem isso, "reunião às 14h" era gravada às 14h UTC e aparecia às
11h para um usuário em UTC-3 — três horas de diferença, silenciosa.
"""

from __future__ import annotations

import time
from datetime import datetime

DEFAULT_TZ = 'America/Sao_Paulo'

# Offset UTC (em horas) -> zona IANA representativa. Só é consultado quando a
# detecção pelo sistema falha e nada foi configurado.
_BY_OFFSET = {
    -3: 'America/Sao_Paulo', -4: 'America/Manaus', -5: 'America/New_York',
    -6: 'America/Mexico_City', -7: 'America/Denver', -8: 'America/Los_Angeles',
    0: 'UTC', 1: 'Europe/Lisbon', 2: 'Europe/Paris', 3: 'Europe/Moscow',
    5: 'Asia/Karachi', 8: 'Asia/Shanghai', 9: 'Asia/Tokyo', 10: 'Australia/Sydney',
}

_cached: str | None = None


def _detect() -> str:
    # 1. zoneinfo via variável de ambiente (Linux/macOS, e Windows configurado)
    try:
        key = getattr(datetime.now().astimezone().tzinfo, 'key', None)
        if key and '/' in key:
            return key
    except Exception:
        pass
    # 2. tzlocal, se instalado
    try:
        import tzlocal
        name = str(tzlocal.get_localzone())
        if name and '/' in name:
            return name
    except Exception:
        pass
    # 3. offset do sistema
    try:
        offset_h = -round((time.altzone if time.daylight and time.localtime().tm_isdst else time.timezone) / 3600)
        return _BY_OFFSET.get(offset_h, DEFAULT_TZ)
    except Exception:
        return DEFAULT_TZ


def user_timezone() -> str:
    """Zona IANA configurada pelo usuário, ou detectada, ou o padrão."""
    global _cached
    if _cached:
        return _cached
    try:
        from core.storage import load_config
        configured = (load_config().get('timezone') or '').strip()
        if configured:
            _cached = configured
            return _cached
    except Exception:
        pass
    _cached = _detect()
    return _cached


def set_user_timezone(name: str) -> None:
    global _cached
    from core.storage import save_config
    _cached = (name or '').strip() or DEFAULT_TZ
    save_config({'timezone': _cached})


def utc_offset_str() -> str:
    """Offset atual como '-03:00', para montar timestamps RFC3339."""
    try:
        off = datetime.now().astimezone().utcoffset()
        total = int(off.total_seconds())
        sign = '+' if total >= 0 else '-'
        total = abs(total)
        return f'{sign}{total // 3600:02d}:{(total % 3600) // 60:02d}'
    except Exception:
        return '-03:00'
