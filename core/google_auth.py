import os
import os.path
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from core.base_auth import BaseAuth
from core.storage import get_appdata_dir

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

class GoogleAuth(BaseAuth):
    __module__ = __name__
    __qualname__ = 'GoogleAuth'
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.client_config = {
            'web': {
                'client_id': os.environ.get('GOOGLE_CLIENT_ID', ''),
                'project_id': 'seq-assistant',
                'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
                'token_uri': 'https://oauth2.googleapis.com/token',
                'auth_provider_x509_cert_url': 'https://www.googleapis.com/oauth2/v1/certs',
                'client_secret': os.environ.get('GOOGLE_CLIENT_SECRET', ''),
                'redirect_uris': ['http://localhost:5678/']
            }
        }
        self.creds = None
        self.token_file = os.path.join(get_appdata_dir(), 'google_token.pickle')
        self._load_creds()

    def _load_creds(self):
        if os.path.exists(self.token_file):
            with open(self.token_file, 'rb') as token:
                self.creds = pickle.load(token)

    def _save_creds(self):
        with open(self.token_file, 'wb') as token:
            pickle.dump(self.creds, token)

    def get_token_silent(self) -> str | None:
        if self.creds and self.creds.valid:
            return self.creds.token
        if self.creds and self.creds.expired and self.creds.refresh_token:
            try:
                self.creds.refresh(Request())
                self._save_creds()
                return self.creds.token
            except Exception:
                return None
        return None

    def login_interactive(self) -> bool:
        try:
            flow = InstalledAppFlow.from_client_config(self.client_config, SCOPES)
            self.creds = flow.run_local_server(port=5678)
            self._save_creds()
            return True
        except Exception as e:
            print(f'Erro no login interativo Google: {e}')
            return False

    def is_connected(self) -> bool:
        return self.get_token_silent() is not None
