"""
ui/agenda_skills.py — `trigger_ui_update`, usada por quem escreve no banco
pra pedir que as telas abertas (Schedules, Google Agenda, Grafo, Memória) se
atualizem sem precisar fechar e reabrir.

Até 2026-08-24 este arquivo tinha ~900 linhas: era o pipeline v1 inteiro
(parse de JSON solto em texto, `AgendaSkillExecutor`, dedupe de lembrete por
similaridade de título, etc.) usado pelo chat antigo e pelo popup de lembrete
antigo. Os dois foram migrados pro loop v2 com function calling nativo (ver
`core/agent/loop.py`, `ui/agent_worker.py`, `core/tools/schedule_tools.py`) —
o `ScheduleAlertDialog` foi o último a migrar. Depois da migração, nada no
app real importava mais nada daqui além desta função; o resto foi removido.
"""

from PyQt6.QtWidgets import QApplication


def trigger_ui_update():
    """Pede pras telas abertas que dependem do banco local se atualizarem."""
    for w in QApplication.topLevelWidgets():
        brain = getattr(w, '_brain', None)
        if brain:
            if hasattr(brain, 'schedules_tab'):
                brain.schedules_tab.refresh()
            if hasattr(brain, 'calendar_tab'):
                brain.calendar_tab.refresh()
            if hasattr(brain, 'graph_tab'):
                brain.graph_tab.refresh()
        settings = getattr(w, '_settings', None)
        if settings and hasattr(settings, 'memory_tab_widget'):
            settings.memory_tab_widget.refresh()
        if hasattr(w, 'memory_tab_widget'):
            w.memory_tab_widget.refresh()
        checker = getattr(w, '_schedule_checker', None)
        if checker:
            checker.force_check()
