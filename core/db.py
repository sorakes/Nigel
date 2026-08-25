"""
core/db.py — Autoridade única de conexão com o SQLite do Nigel.

Antes, `NigelDB` e `ScheduleManager` abriam duas conexões independentes com
`check_same_thread=False` e as compartilhavam entre a thread do Qt, os QThreads
de polling e várias `threading.Thread` fire-and-forget. Objetos `sqlite3.Connection`
não são seguros para uso concorrente mesmo com essa flag.

Aqui cada thread recebe a própria conexão (`threading.local`), em modo WAL para
que leitores e escritores não se bloqueiem, com `busy_timeout` para que um
escritor concorrente espere em vez de falhar.
"""

import os
import sqlite3
import threading

from core.storage import get_appdata_dir

_DB_FILE = 'nigel.db'

_local = threading.local()
_init_lock = threading.RLock()
_schema_done: set[str] = set()

# Serializa sequências de escrita com múltiplos statements (DELETE + INSERTs + commit),
# que sob concorrência poderiam se intercalar.
write_lock = threading.RLock()


def db_path() -> str:
    return os.path.join(get_appdata_dir(), _DB_FILE)


def get_conn() -> sqlite3.Connection:
    """Conexão SQLite desta thread, criada sob demanda."""
    conn = getattr(_local, 'conn', None)
    if conn is not None:
        return conn

    conn = sqlite3.connect(db_path(), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA busy_timeout=5000')
    conn.execute('PRAGMA synchronous=NORMAL')
    conn.execute('PRAGMA foreign_keys=ON')
    _local.conn = conn
    return conn


def close_conn() -> None:
    """Fecha a conexão desta thread. Chamar ao encerrar um worker de vida longa."""
    conn = getattr(_local, 'conn', None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
        _local.conn = None


def ensure_schema(name: str, create_fn) -> None:
    """Roda `create_fn(conn)` uma única vez por processo para o schema `name`."""
    if name in _schema_done:
        return
    with _init_lock:
        if name in _schema_done:
            return
        create_fn(get_conn())
        _schema_done.add(name)
