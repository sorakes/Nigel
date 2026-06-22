__doc__ = """
core/persona_capture.py - Compatibilidade para captura de Persona.

Persona não deve ser inferida por listas ou padrões locais. O SEQ precisa usar
a IA para decidir quando perguntar, salvar ou ignorar um detalhe subjetivo.
"""

from __future__ import annotations
import hashlib
import re
from dataclasses import dataclass

def _clean(text: str) -> str:
    return re.sub(r'\s+', ' ', text or '').strip(' .,!?:;"\'')

def _stable_key(prefix: str, value: str) -> str:
    digest = hashlib.sha1(value.lower().encode('utf-8')).hexdigest()[:10]
    return f"{prefix}:{digest}"

@dataclass
class PersonaFact:
    key: str
    label: str
    value: str

def extract_persona_facts(text: str) -> list[PersonaFact]:
    return []

def capture_persona_from_text(text: str) -> list[PersonaFact]:
    facts = extract_persona_facts(text)
    if not facts:
        return []

    from core.database import SeqDB
    db = SeqDB.get_instance()

    for fact in facts:
        db.upsert_persona_fact(fact.key, fact.label, fact.value)

    return facts
