__doc__ = """
core/polling_engine.py — Motor de leitura em background do Nigel.

Lê e-mails (Outlook + Gmail) a cada 60 segundos, classifica com a IA
e só notifica a interface quando algo realmente importante aparecer.
"""

import time
import requests
from PyQt6.QtCore import QThread, pyqtSignal
from core.microsoft_auth import MicrosoftAuth
from core.google_auth import GoogleAuth
from core import ai_triage
from core.database import SeqDB

_POLL_INTERVAL = 60

class GraphAnalysisWorker(QThread):
    __doc__ = 'Pede para a IA pensar nas relações do grafo de conhecimento (em background).'

    analysis_done = pyqtSignal()

    def run(self):
        try:
            db = SeqDB.get_instance()
            graph = db.get_knowledge_graph(limit=80)
            result = ai_triage.analyze_graph(graph['nodes'])
            if result is not None:
                db.replace_ai_knowledge_edges(result.get('edges'), result.get('scores'))
                self.analysis_done.emit()
        except Exception as e:
            print(f"[Nigel] GraphAnalysisWorker erro: {e}")

class GraphPollingWorker(QThread):
    __doc__ = 'Lê e-mails do Outlook (Microsoft Graph) em background.'

    new_important_item = pyqtSignal(dict)
    status_update = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        db = SeqDB.get_instance()
        self.status_update.emit('[Outlook] Motor iniciado.')

        while self._running:
            try:
                auth = MicrosoftAuth.get_instance()
                token = auth.get_token_silent()

                if token:
                    self._fetch_and_process(token, db)
                else:
                    self.status_update.emit('[Outlook] Sem token. Aguardando login...')
            except Exception as e:
                self.status_update.emit(f'[Outlook] Erro: {e}')

            for _ in range(_POLL_INTERVAL):
                if not self._running:
                    break
                time.sleep(1)

    def _fetch_and_process(self, token: str, db: SeqDB):
        headers = {'Authorization': f'Bearer {token}'}
        url = 'https://graph.microsoft.com/v1.0/me/messages'
        params = {
            '$filter': 'isRead eq false',
            '$top': 10,
            '$select': 'id,subject,from,bodyPreview',
            '$orderby': 'receivedDateTime desc'
        }
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()

        for msg in resp.json().get('value', []):
            msg_id = msg['id']
            if db.is_seen(msg_id):
                continue

            db.mark_seen(msg_id, 'outlook')

            item = {
                'id': msg_id,
                'source': 'outlook',
                'subject': msg.get('subject', ''),
                'sender': msg.get('from', {}).get('emailAddress', {}).get('address', ''),
                'body_preview': msg.get('bodyPreview', '')
            }

            self.status_update.emit(f'[Outlook] Nova mensagem: {item["subject"][:50]}')

            triage = ai_triage.classify(item)
            if triage.get('important'):
                item['ai_summary'] = triage.get('summary', '')
                item['ai_reason'] = triage.get('reason', '')
                db.save_important(item, saved_by='ai')
                self.new_important_item.emit(item)
                self.status_update.emit(f'[Outlook] ⚡ IMPORTANTE: {triage.get("reason", "")}')

class GmailPollingWorker(QThread):
    __doc__ = 'Lê e-mails do Gmail (Google API) em background.'

    new_important_item = pyqtSignal(dict)
    status_update = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        db = SeqDB.get_instance()
        self.status_update.emit('[Gmail] Motor iniciado.')

        while self._running:
            try:
                auth = GoogleAuth.get_instance()
                token = auth.get_token_silent()

                if token:
                    self._fetch_and_process(token, db)
                else:
                    self.status_update.emit('[Gmail] Sem token. Aguardando login...')
            except Exception as e:
                self.status_update.emit(f'[Gmail] Erro: {e}')

            for _ in range(_POLL_INTERVAL):
                if not self._running:
                    break
                time.sleep(1)

    def _fetch_and_process(self, token: str, db: SeqDB):
        headers = {'Authorization': f'Bearer {token}'}
        list_resp = requests.get(
            'https://gmail.googleapis.com/gmail/v1/users/me/messages',
            headers=headers,
            params={'labelIds': 'INBOX,UNREAD', 'maxResults': 10},
            timeout=15
        )
        list_resp.raise_for_status()

        for msg_ref in list_resp.json().get('messages', []):
            msg_id = msg_ref['id']
            if db.is_seen(msg_id):
                continue

            db.mark_seen(msg_id, 'gmail')

            detail_resp = requests.get(
                f'https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}',
                headers=headers,
                params={'format': 'metadata', 'metadataHeaders': ['Subject', 'From']},
                timeout=15
            )
            detail_resp.raise_for_status()
            detail = detail_resp.json()

            headers_map = {h['name']: h['value'] for h in detail.get('payload', {}).get('headers', [])}

            item = {
                'id': msg_id,
                'source': 'gmail',
                'subject': headers_map.get('Subject', ''),
                'sender': headers_map.get('From', ''),
                'body_preview': detail.get('snippet', '')
            }

            self.status_update.emit(f'[Gmail] Nova mensagem: {item["subject"][:50]}')

            triage = ai_triage.classify(item)
            if triage.get('important'):
                item['ai_summary'] = triage.get('summary', '')
                item['ai_reason'] = triage.get('reason', '')
                db.save_important(item, saved_by='ai')
                self.new_important_item.emit(item)
                self.status_update.emit(f'[Gmail] ⚡ IMPORTANTE: {triage.get("reason", "")}')
            else:
                self.status_update.emit(f'[Gmail] Ignorado: {triage.get("reason", "")}')
