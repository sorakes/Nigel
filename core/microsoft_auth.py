import os
import msal
import atexit
from core.base_auth import BaseAuth
from core.storage import get_appdata_dir

SCOPES = ['User.Read', 'Mail.Read', 'Chat.Read']

def _cache_path() -> str:
    return os.path.join(get_appdata_dir(), 'ms_token.bin')

class MicrosoftAuth(BaseAuth):
    """Singleton-like manager for MSAL authentication."""
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.cache = msal.SerializableTokenCache()
        cache_file = _cache_path()
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    self.cache.deserialize(f.read())
            except Exception:
                pass
        atexit.register(self.save_cache)

    def save_cache(self):
        if self.cache.has_state_changed:
            try:
                with open(_cache_path(), 'w') as f:
                    f.write(self.cache.serialize())
            except:
                pass

    def get_client_id(self):
        return '2ac3513b-ec59-4c56-b14b-af7fa4af7951'

    def get_token_silent(self) -> str | None:
        client_id = self.get_client_id()
        if not client_id:
            return None

        app = msal.PublicClientApplication(
            client_id,
            authority='https://login.microsoftonline.com/common',
            token_cache=self.cache
        )
        accounts = app.get_accounts()
        if accounts:
            result = app.acquire_token_silent(SCOPES, account=accounts[0])
            if result and 'access_token' in result:
                self.save_cache()
                return result['access_token']
        return None

    def login_interactive(self) -> bool:
        client_id = self.get_client_id()
        app = msal.PublicClientApplication(
            client_id,
            authority='https://login.microsoftonline.com/common',
            token_cache=self.cache
        )
        result = app.acquire_token_interactive(scopes=SCOPES)
        if 'access_token' in result:
            self.save_cache()
            return True
        return False

    def is_connected(self) -> bool:
        return self.get_token_silent() is not None
