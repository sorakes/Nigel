"""
core/polling_engine.py — Motor de leitura em background do Nigel via Composio.

Lê e-mails (Outlook + Gmail) a cada 60 segundos via ferramentas do Composio,
classifica com a IA e só notifica a interface quando algo importante aparecer.
"""

import time
from PyQt6.QtCore import QThread, pyqtSignal
from core.composio_manager import ComposioManager, TOOLKIT_GMAIL, TOOLKIT_OUTLOOK
from core import ai_triage
from core.database import NigelDB

_POLL_INTERVAL = 60


class GraphAnalysisWorker(QThread):
    """Pede para a IA pensar nas relações do grafo de conhecimento (em background)."""

    analysis_done = pyqtSignal()

    def run(self):
        try:
            db = NigelDB.get_instance()
            graph = db.get_knowledge_graph(limit=80)
            result = ai_triage.analyze_graph(graph['nodes'])
            if result is not None:
                db.replace_ai_knowledge_edges(result.get('edges'), result.get('scores'))
                self.analysis_done.emit()
        except Exception as e:
            print(f"[Nigel] GraphAnalysisWorker erro: {e}")


class GraphPollingWorker(QThread):
    """Lê e-mails do Outlook via Composio em background."""

    new_important_item = pyqtSignal(dict)
    status_update = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        db = NigelDB.get_instance()
        cm = ComposioManager.get_instance()
        self.status_update.emit('[Outlook] Motor iniciado via Composio.')

        last_connected_state = None

        while self._running:
            try:
                if cm.is_configured() and cm.check_connection(TOOLKIT_OUTLOOK):
                    if last_connected_state is not True:
                        self.status_update.emit('[Outlook] Conexão ativa com Composio.')
                        last_connected_state = True
                    messages = cm.fetch_unread_outlook(limit=10)
                    for item in messages:
                        msg_id = item['id']
                        if db.is_seen(msg_id):
                            continue
                        db.mark_seen(msg_id, 'outlook')
                        self.status_update.emit(f'[Outlook] Nova mensagem: {item["subject"][:50]}')
                        triage = ai_triage.classify(item)
                        if triage.get('important'):
                            item['ai_summary'] = triage.get('summary', '')
                            item['ai_reason'] = triage.get('reason', '')
                            db.save_important(item, saved_by='ai')
                            self.new_important_item.emit(item)
                            self.status_update.emit(f'[Outlook] IMPORTANTE: {triage.get("reason", "")}')
                else:
                    if last_connected_state is not False and cm.is_configured():
                        self.status_update.emit('[Outlook] Conta não conectada no Composio.')
                        last_connected_state = False
            except Exception as e:
                self.status_update.emit(f'[Outlook] Erro: {e}')

            for _ in range(_POLL_INTERVAL):
                if not self._running:
                    break
                time.sleep(1)


class GmailPollingWorker(QThread):
    """Lê e-mails do Gmail via Composio em background."""

    new_important_item = pyqtSignal(dict)
    status_update = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        db = NigelDB.get_instance()
        cm = ComposioManager.get_instance()
        self.status_update.emit('[Gmail] Motor iniciado via Composio.')
        last_connected_state = None

        while self._running:
            try:
                if cm.is_configured() and cm.check_connection(TOOLKIT_GMAIL):
                    if last_connected_state is not True:
                        self.status_update.emit('[Gmail] Conexão ativa com Composio.')
                        last_connected_state = True
                    messages = cm.fetch_unread_gmail(limit=10)
                    for item in messages:
                        msg_id = item['id']
                        if db.is_seen(msg_id):
                            continue
                        db.mark_seen(msg_id, 'gmail')
                        self.status_update.emit(f'[Gmail] Nova mensagem: {item["subject"][:50]}')
                        triage = ai_triage.classify(item)
                        if triage.get('important'):
                            item['ai_summary'] = triage.get('summary', '')
                            item['ai_reason'] = triage.get('reason', '')
                            db.save_important(item, saved_by='ai')
                            self.new_important_item.emit(item)
                            self.status_update.emit(f'[Gmail] IMPORTANTE: {triage.get("reason", "")}')
                        else:
                            self.status_update.emit(f'[Gmail] Ignorado: {triage.get("reason", "")}')
                else:
                    if last_connected_state is not False and cm.is_configured():
                        self.status_update.emit('[Gmail] Conta não conectada no Composio.')
                        last_connected_state = False
            except Exception as e:
                self.status_update.emit(f'[Gmail] Erro: {e}')

            for _ in range(_POLL_INTERVAL):
                if not self._running:
                    break
                time.sleep(1)
