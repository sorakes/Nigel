__doc__ = """
core/storage.py — Armazenamento do Nigel.
Gerencia AppData, Keyring (Windows Credential Manager) e config.json.
"""

import os
import json
import keyring

_APP_NAME = 'Nigel'
_CONFIG_FILE = 'config.json'

def get_appdata_dir() -> str:
    base = os.environ.get('APPDATA', os.path.expanduser('~'))
    app_dir = os.path.join(base, _APP_NAME)
    os.makedirs(app_dir, exist_ok=True)
    return app_dir

def get_config_path() -> str:
    return os.path.join(get_appdata_dir(), _CONFIG_FILE)

def load_config() -> dict:
    path = get_config_path()
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}

def save_config(data: dict) -> None:
    existing = load_config()
    existing.update(data)
    with open(get_config_path(), 'w', encoding='utf-8') as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)

def _migrate_appdata():
    """Migra dados da pasta antiga 'SEQ' para 'Nigel' caso existam."""
    old_dir = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'SEQ')
    new_dir = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'Nigel')
    if os.path.isdir(old_dir) and not os.path.isdir(new_dir):
        import shutil
        try:
            shutil.copytree(old_dir, new_dir)
            print('[Nigel] Dados migrados de SEQ → Nigel com sucesso.')
        except Exception as e:
            print(f'[Nigel] Falha ao migrar dados: {e}')

_migrate_appdata()


def save_secret(service: str, key: str, value: str) -> None:
    try:
        keyring.set_password(f"{_APP_NAME}.{service}", key, value)
    except Exception as e:
        print(f"[Storage] Erro ao salvar segredo {service}/{key}: {e}")

def load_secret(service: str, key: str) -> str:
    try:
        val = keyring.get_password(f"{_APP_NAME}.{service}", key)
        return val or ''
    except Exception:
        return ''

def delete_secret(service: str, key: str) -> None:
    try:
        keyring.delete_password(f"{_APP_NAME}.{service}", key)
    except Exception:
        pass
