"""
core/database.py — Banco de dados local SQLite para o SEQ.

Filosofia:
- 'seen_ids': tabela leve (só IDs) para deduplicação. Nenhum conteúdo salvo.
- 'saved_items': conteúdo completo, SOMENTE para itens importantes (classificados pela IA)
                 ou quando o usuário explicitamente pedir para salvar algo.
"""

import sqlite3
import os
import re
import hashlib
from datetime import datetime
from core.storage import get_appdata_dir

_DB_FILE = 'seq.db'

class SeqDB:
    __module__ = __name__
    __qualname__ = 'SeqDB'
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        db_path = os.path.join(get_appdata_dir(), _DB_FILE)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS seen_ids (
                id        TEXT PRIMARY KEY,
                source    TEXT NOT NULL,
                seen_at   TEXT NOT NULL
            )
        ''')
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS saved_items (
                id               TEXT PRIMARY KEY,
                source           TEXT NOT NULL,
                subject          TEXT,
                sender           TEXT,
                body_preview     TEXT,
                ai_summary       TEXT,
                ai_reason        TEXT,
                saved_by         TEXT DEFAULT 'ai',  -- 'ai' ou 'user'
                saved_at         TEXT NOT NULL,
                relevance_score  INTEGER DEFAULT 50   -- 1-100, definido/ajustado pela IA
            )
        ''')
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS knowledge_nodes (
                id              TEXT PRIMARY KEY,
                title           TEXT,
                body            TEXT,
                node_type       TEXT NOT NULL,
                source          TEXT,
                source_ref      TEXT,
                relevance_score INTEGER DEFAULT 50,
                updated_at      TEXT NOT NULL
            )
        ''')
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS knowledge_edges (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id  TEXT NOT NULL,
                target_id  TEXT NOT NULL,
                relation   TEXT NOT NULL,
                strength   REAL DEFAULT 0.6,
                created_by TEXT DEFAULT 'system',
                updated_at TEXT NOT NULL,
                UNIQUE(source_id, target_id, relation, created_by)
            )
        ''')
        self.conn.commit()
        self._migrate()

    def _migrate(self):
        cols = [row[1] for row in self.conn.execute('PRAGMA table_info(saved_items)').fetchall()]
        if 'relevance_score' not in cols:
            self.conn.execute('ALTER TABLE saved_items ADD COLUMN relevance_score INTEGER DEFAULT 50')
            self.conn.commit()

    def _node_type_for_item(self, item: dict) -> str:
        source = item.get('source', '').lower()
        item_id = str(item.get('id', ''))
        subject = item.get('subject', '').lower()

        if source == 'persona' or item_id.startswith('persona:') or subject.startswith('persona:'):
            return 'persona'
        if source in ('outlook', 'gmail'):
            return 'email'
        if source in ('agenda_chat',) or subject.startswith('agenda:'):
            return 'agenda'
        return 'note'

    def _tokenize(self, text: str) -> set[str]:
        text = text.lower() if text else ''
        text = re.sub(r'[^a-z0-9áàâãéèêíóôõúçñ\s]', ' ', text)
        words = {w for w in text.split() if len(w) >= 4}
        stop = frozenset({'este', 'essa', 'lembrete', 'histórico', 'uma', 'sobre', 'para', 'persona', 'com', 'historico', 'agenda', 'esse', 'esta'})
        return words - stop

    def _person_relation_key(self, name: str) -> str:
        digest = hashlib.sha1(name.strip().lower().encode('utf-8')).hexdigest()[:10]
        return f'person:{digest}'

    def cleanup_weak_persona_people(self):
        rows = self.conn.execute('''
            SELECT id, subject, body_preview, ai_summary
            FROM saved_items
            WHERE source = 'persona' AND id NOT LIKE 'persona:%'
        ''').fetchall()

        for row in rows:
            subject = (row['subject'] or '').strip()
            looks_like_person = bool(re.match(r'^(?:pessoa importante:\s*)?[A-Za-zÀ-ÿ]{2,}(?:\s+[A-Za-zÀ-ÿ]{2,})?$', subject, flags=re.IGNORECASE))
            if looks_like_person:
                self.conn.execute('''
                    UPDATE saved_items
                    SET source = 'manual',
                        ai_reason = 'Memória aguardando relação de Persona'
                    WHERE id = ?
                ''', (row['id'],))

        rows = self.conn.execute('''
            SELECT id, body_preview
            FROM saved_items
            WHERE source = 'persona' AND id LIKE 'persona:person:%'
        ''').fetchall()

        for row in rows:
            value = (row['body_preview'] or '').strip()
            if ':' in value:
                value = value.split(':', 1)[1].strip()
            words = [w for w in re.split(r'\s+', value) if w]
            if len(words) <= 1 and len(value) <= 8:
                self.conn.execute('DELETE FROM saved_items WHERE id = ?', (row['id'],))

        self.conn.commit()

    def _edge_key(self, a: str, b: str) -> tuple[str, str]:
        return (a, b) if str(a) <= str(b) else (b, a)

    def _upsert_edge(self, source_id: str, target_id: str, relation: str, strength: float = 0.6, created_by: str = 'system'):
        if not source_id or not target_id or source_id == target_id:
            return
        source_id, target_id = self._edge_key(str(source_id), str(target_id))
        self.conn.execute('''
            INSERT INTO knowledge_edges
                (source_id, target_id, relation, strength, created_by, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id, target_id, relation, created_by) DO UPDATE SET
                strength = excluded.strength,
                updated_at = excluded.updated_at
        ''', (source_id, target_id, relation, float(strength), created_by, datetime.utcnow().isoformat()))

    def sync_saved_items_to_knowledge(self):
        self.cleanup_weak_persona_people()
        rows = self.conn.execute('SELECT * FROM saved_items').fetchall()
        now = datetime.utcnow().isoformat()
        seen_ids = set()

        for row in rows:
            item = dict(row)
            node_id = item['id']
            seen_ids.add(node_id)
            title = item.get('subject') or item.get('ai_summary') or 'Memória'
            body = item.get('body_preview') or item.get('ai_summary') or ''
            node_type = self._node_type_for_item(item)
            self.conn.execute('''
                INSERT INTO knowledge_nodes
                    (id, title, body, node_type, source, source_ref, relevance_score, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    body = excluded.body,
                    node_type = excluded.node_type,
                    source = excluded.source,
                    source_ref = excluded.source_ref,
                    relevance_score = excluded.relevance_score,
                    updated_at = excluded.updated_at
            ''', (node_id, title, body, node_type, item.get('source', ''), node_id, item.get('relevance_score', 50), now))

        for row in self.conn.execute('SELECT id FROM knowledge_nodes').fetchall():
            node_id = row['id']
            if node_id not in seen_ids and not str(node_id).startswith('persona:core'):
                self.conn.execute('DELETE FROM knowledge_nodes WHERE id = ?', (node_id,))
                self.conn.execute('DELETE FROM knowledge_edges WHERE source_id = ? OR target_id = ?', (node_id, node_id))

        self.conn.commit()

    def rebuild_system_edges(self):
        self.sync_saved_items_to_knowledge()
        self.conn.execute("DELETE FROM knowledge_edges WHERE created_by = 'system'")
        nodes = [dict(r) for r in self.conn.execute('SELECT * FROM knowledge_nodes').fetchall()]
        by_id = {n['id']: n for n in nodes}
        persona = [n for n in nodes if n['node_type'] == 'persona']
        others = [n for n in nodes if n['node_type'] != 'persona']

        for p in persona:
            p_tokens = self._tokenize(f"{p.get('title', '')} {p.get('body', '')}")
            if not p_tokens:
                continue
            for n in others:
                n_tokens = self._tokenize(f"{n.get('title', '')} {n.get('body', '')}")
                overlap = p_tokens & n_tokens
                if overlap:
                    self._upsert_edge(p['id'], n['id'], 'mentions_persona', 0.9, 'system')

        items = [dict(r) for r in self.conn.execute('SELECT * FROM saved_items').fetchall()]
        sender_map = {}
        for item in items:
            sender = (item.get('sender') or '').strip().lower()
            if sender and item['id'] in by_id:
                sender_map.setdefault(sender, []).append(item['id'])

        for ids in sender_map.values():
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    self._upsert_edge(ids[i], ids[j], 'same_sender', 0.7, 'system')

        for i in range(len(others)):
            a = others[i]
            ta = self._tokenize(f"{a.get('title', '')} {a.get('body', '')}")
            if not ta:
                continue
            for j in range(i + 1, len(others)):
                b = others[j]
                tb = self._tokenize(f"{b.get('title', '')} {b.get('body', '')}")
                if not tb:
                    continue
                overlap = ta & tb
                if not overlap:
                    continue
                score = len(overlap) / max(len(ta), len(tb))
                if score >= 0.22:
                    self._upsert_edge(a['id'], b['id'], 'same_topic', min(0.95, 0.45 + score), 'system')

        self.conn.commit()

    def get_knowledge_graph(self, limit: int = 80) -> dict:
        self.rebuild_system_edges()
        nodes = [dict(r) for r in self.conn.execute('''
            SELECT * FROM knowledge_nodes
            ORDER BY CASE node_type WHEN 'persona' THEN 0 ELSE 1 END,
                     relevance_score DESC, updated_at DESC
            LIMIT ?
        ''', (limit,)).fetchall()]
        ids = {n['id'] for n in nodes}
        edges = [dict(r) for r in self.conn.execute('''
                SELECT * FROM knowledge_edges
                ORDER BY strength DESC, updated_at DESC
            ''').fetchall() if r['source_id'] in ids and r['target_id'] in ids]
        return {'nodes': nodes, 'edges': edges}

    def replace_ai_knowledge_edges(self, edges: list = None, scores: dict = None):
        if scores:
            clean_scores = {k: int(v) for k, v in scores.items() if not str(k).startswith('persona:')}
            self.bulk_update_relevance(clean_scores)

        self.sync_saved_items_to_knowledge()
        self.conn.execute("DELETE FROM knowledge_edges WHERE created_by = 'ai'")
        valid_ids = {r['id'] for r in self.conn.execute("SELECT id FROM knowledge_nodes WHERE node_type != 'persona'").fetchall()}

        for pair in edges or []:
            if len(pair) != 2:
                continue
            a, b = str(pair[0]), str(pair[1])
            if a in valid_ids and b in valid_ids and a != b:
                self._upsert_edge(a, b, 'ai_related', 0.85, 'ai')

        self.conn.commit()

    def mark_seen(self, item_id: str, source: str):
        self.conn.execute('INSERT OR IGNORE INTO seen_ids (id, source, seen_at) VALUES (?, ?, ?)', (item_id, source, datetime.utcnow().isoformat()))
        self.conn.commit()

    def is_seen(self, item_id: str) -> bool:
        row = self.conn.execute('SELECT 1 FROM seen_ids WHERE id = ?', (item_id,)).fetchone()
        return row is not None

    def save_important(self, item: dict, saved_by: str = 'ai'):
        self.conn.execute('''
            INSERT OR IGNORE INTO saved_items
                (id, source, subject, sender, body_preview, ai_summary, ai_reason, saved_by, saved_at, relevance_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            item['id'],
            item.get('source', 'unknown'),
            item.get('subject', ''),
            item.get('sender', ''),
            item.get('body_preview', ''),
            item.get('ai_summary', ''),
            item.get('ai_reason', ''),
            saved_by,
            datetime.utcnow().isoformat(),
            item.get('relevance_score', 50)
        ))
        self.conn.commit()

    def save_item(self, subject: str, body_preview: str, source: str, is_important: bool = False, relevance_score: int = 50):
        import uuid
        self.save_important({
            'id': str(uuid.uuid4()),
            'source': source,
            'subject': subject,
            'sender': '',
            'body_preview': body_preview,
            'ai_summary': subject,
            'ai_reason': 'Criado pela Agenda',
            'relevance_score': relevance_score
        }, saved_by='user')

    def upsert_persona_fact(self, key: str, label: str, value: str):
        item_id = f'persona:{key}'
        value = value.strip() if value else ''
        if not value:
            self.conn.execute('DELETE FROM saved_items WHERE id = ?', (item_id,))
            self.conn.commit()
            return

        self.conn.execute('''
            INSERT INTO saved_items
                (id, source, subject, sender, body_preview, ai_summary, ai_reason, saved_by, saved_at, relevance_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                source = excluded.source,
                subject = excluded.subject,
                body_preview = excluded.body_preview,
                ai_summary = excluded.ai_summary,
                ai_reason = excluded.ai_reason,
                saved_by = excluded.saved_by,
                relevance_score = excluded.relevance_score
        ''', (
            item_id,
            'persona',
            f'Persona: {label}',
            '',
            value,
            f'{label}: {value}',
            'Dado fixo de persona configurado pelo usuário',
            'user',
            datetime.utcnow().isoformat(),
            95
        ))
        self.conn.commit()

    def upsert_person_relation(self, name: str, relation_text: str):
        name = name.strip() if name else ''
        relation_text = relation_text.strip() if relation_text else ''
        if not name or not relation_text:
            return
        self.upsert_persona_fact(
            self._person_relation_key(name),
            f'Pessoa: {name}',
            f'Relação/contexto informado pelo usuário: {relation_text}'
        )

    def sync_persona_profile(self, persona: dict):
        self.upsert_persona_fact('name', 'Nome', persona.get('name', ''))
        self.upsert_persona_fact('age', 'Idade', persona.get('age', ''))
        self.upsert_persona_fact('email', 'Email', persona.get('email', ''))
        self.conn.execute("DELETE FROM saved_items WHERE id LIKE 'persona:custom:%'")
        self.conn.commit()

        for idx, fact in enumerate(persona.get('facts', []) or [], start=1):
            fact = fact.strip() if fact else ''
            if fact:
                self.upsert_persona_fact(f'custom:{idx}', f'Info {idx}', fact)

    def persona_mentions_name(self, name: str) -> bool:
        name = name.strip().lower() if name else ''
        if not name:
            return False
        rows = self.conn.execute('''
            SELECT subject, body_preview, ai_summary
            FROM saved_items
            WHERE source = 'persona'
        ''').fetchall()

        for row in rows:
            text = ' '.join(str(row[k]) or '' for k in row.keys()).lower()
            if name in text:
                return True
        return False

    def persona_has_person_relation(self, name: str) -> bool:
        name = name.strip() if name else ''
        if not name:
            return False
        item_id = f'persona:{self._person_relation_key(name)}'
        row = self.conn.execute("SELECT 1 FROM saved_items WHERE id = ? AND source = 'persona' LIMIT 1", (item_id,)).fetchone()
        return row is not None

    def get_saved_items(self, limit: int = 20, include_persona: bool = True) -> list[dict]:
        query = 'SELECT * FROM saved_items'
        params = []
        if not include_persona:
            query += " WHERE source != 'persona'"
        query += ' ORDER BY saved_at DESC LIMIT ?'
        params.append(limit)
        rows = self.conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def delete_saved_item(self, item_id: str):
        self.conn.execute('DELETE FROM saved_items WHERE id = ?', (item_id,))
        self.conn.commit()

    def update_relevance(self, item_id: str, score: int):
        score = max(1, min(100, int(score)))
        self.conn.execute('UPDATE saved_items SET relevance_score = ? WHERE id = ?', (score, item_id))
        self.conn.commit()

    def bulk_update_relevance(self, scores: dict):
        for item_id, score in scores.items():
            score = max(1, min(100, int(score)))
            self.conn.execute('UPDATE saved_items SET relevance_score = ? WHERE id = ?', (score, item_id))
        self.conn.commit()
