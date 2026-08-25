"""
main.py — Ponto de entrada do Nigel.

Sobe a barra flutuante (janela raiz) e os workers de background:
polling de Gmail/Outlook via Composio e o monitor de schedules vencidos.
"""

import sys
import os

# Garante que a raiz do projeto esteja no sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configura encoding do console para evitar erros com emojis no Windows
for _stream in (sys.stdout, sys.stderr):
    if _stream and hasattr(_stream, 'reconfigure'):
        try:
            _stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, QTimer
from ui.bar import Bar
from core.polling_engine import GraphPollingWorker, GmailPollingWorker
from core.scheduler import ScheduleCheckerWorker, set_active_checker
from core.agenda_conflict import AgendaConflictWorker
from core.meeting_prep import MeetingPrepWorker


def _stop_workers(workers: list):
    """Encerra os QThreads de background de forma ordenada no fechamento do app."""
    for w in workers:
        try:
            if hasattr(w, 'stop'):
                w.stop()
            w.quit()
            w.wait(2000)
        except Exception as e:
            print(f"[Nigel] Falha ao encerrar worker {type(w).__name__}: {e}")


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Nigel")
    app.setApplicationDisplayName("Nigel")

    _icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'nigel.ico')
    if os.path.exists(_icon_path):
        app.setWindowIcon(QIcon(_icon_path))

    # A barra flutuante é a janela raiz e deve permanecer ativa
    app.setQuitOnLastWindowClosed(False)

    bar = Bar()
    bar.show()

    # Assistente de primeira abertura — so' aparece uma vez (ver
    # onboarding_completed em config.json), depois disso quem quiser
    # conectar algo usa Configuracoes -> Integracoes normalmente.
    from core.storage import load_config
    if not load_config().get('onboarding_completed'):
        def _show_onboarding():
            from ui.onboarding import OnboardingWindow
            wiz = OnboardingWindow()
            wiz.show_centered()
            app._onboarding = wiz
        QTimer.singleShot(400, _show_onboarding)

    workers = []

    # Polling de inbox em background via Composio
    for worker_cls, source in ((GraphPollingWorker, 'Outlook'), (GmailPollingWorker, 'Gmail')):
        worker = worker_cls()
        worker.new_important_item.connect(
            lambda item, s=source: bar.handle_important_item(item, s),
            Qt.ConnectionType.QueuedConnection)
        worker.status_update.connect(print)
        worker.start()
        workers.append(worker)

    # Monitor de schedules vencidos
    schedule_checker = ScheduleCheckerWorker()
    set_active_checker(schedule_checker)
    schedule_checker.overdue_found.connect(
        bar.handle_overdue, Qt.ConnectionType.QueuedConnection)
    schedule_checker.task_executed.connect(
        bar.handle_task_result, Qt.ConnectionType.QueuedConnection)
    bar.set_schedule_checker(schedule_checker)
    schedule_checker.start()
    workers.append(schedule_checker)

    # Monitor de conflito de agenda no Google Calendar real
    conflict_checker = AgendaConflictWorker()
    conflict_checker.conflict_found.connect(
        bar.handle_agenda_conflict, Qt.ConnectionType.QueuedConnection)
    conflict_checker.start()
    workers.append(conflict_checker)

    # Preparacao de reuniao antes dela comecar
    prep_worker = MeetingPrepWorker()
    prep_worker.prep_ready.connect(
        bar.handle_meeting_prep, Qt.ConnectionType.QueuedConnection)
    prep_worker.start()
    workers.append(prep_worker)

    # Manter referências para não serem coletadas pelo GC
    app._workers = workers
    app.aboutToQuit.connect(lambda: _stop_workers(workers))

    # Segunda checagem após a UI estar pronta
    QTimer.singleShot(1000, schedule_checker.force_check)

    print("[Nigel] Nigel iniciado com sucesso.")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
