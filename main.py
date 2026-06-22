"""
main.py — Seq Widget entry point.
"""

import sys
import os

# Ensure project root is on the path so `ui` and `core` can be imported.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QTimer

from ui.bar import Bar
from core.polling_engine import GraphPollingWorker, GmailPollingWorker
from core.scheduler import ScheduleCheckerWorker, set_active_checker


def _handle_overdue(items: list, bar: Bar):
    bar.show_schedule_notification(len(items))
    from ui.notification import NotificationPopup
    for item in items:
        NotificationPopup.show_msg(item, anchor=bar)


def _handle_important_email(item: dict, bar: Bar, source: str):
    summary = item.get('ai_summary') or item.get('subject', '')
    print(f"[SEQ] ⚡ {source}: {summary}")
    bar.brain_btn.set_badge(bar.brain_btn._badge + 1)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Seq")
    app.setApplicationDisplayName("Seq")

    # Don't quit when the last (visible) window is closed —
    # the bar is the root window and must stay alive.
    app.setQuitOnLastWindowClosed(False)

    bar = Bar()
    bar.show()

    # Inicia os motores de polling em background (só notificam quando a IA classifica como importante)
    graph_worker = GraphPollingWorker()
    graph_worker.new_important_item.connect(
        lambda item, b=bar: _handle_important_email(item, b, 'Outlook'))
    graph_worker.status_update.connect(lambda msg: print(msg))
    graph_worker.start()

    gmail_worker = GmailPollingWorker()
    gmail_worker.new_important_item.connect(
        lambda item, b=bar: _handle_important_email(item, b, 'Gmail'))
    gmail_worker.status_update.connect(lambda msg: print(msg))
    gmail_worker.start()

    # Manter referências para não serem coletadas pelo GC
    app._workers = [graph_worker, gmail_worker]

    # Monitor de schedules vencidos
    schedule_checker = ScheduleCheckerWorker()
    set_active_checker(schedule_checker)
    schedule_checker.overdue_found.connect(
        lambda items, b=bar: _handle_overdue(items, b),
        Qt.ConnectionType.QueuedConnection)
    bar.set_schedule_checker(schedule_checker)
    print("[SEQ] Starting checker worker...")
    schedule_checker.start()
    app._workers.append(schedule_checker)
    # Segunda checagem após a UI estar pronta
    QTimer.singleShot(800, schedule_checker.force_check)

    print("[SEQ] Entering app.exec()...")
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

