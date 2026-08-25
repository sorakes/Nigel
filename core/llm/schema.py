"""
core/llm/schema.py — Saneamento de JSON Schema por provider.

Schemas vindos do Composio carregam chaves que o Gemini nao aceita
(`examples`, `title`, `human_parameter_name`, `const`, `pattern`,
`additionalProperties`, `$schema`...). O `functionDeclarations` do Gemini
aceita apenas um subconjunto do OpenAPI 3.0 e rejeita chaves desconhecidas.

Para os demais providers a limpeza e' mais leve: so remove ruido que nao
ajuda o modelo e custa token.
"""

from __future__ import annotations

# Aceitas pelo Gemini (subconjunto do OpenAPI 3.0)
_GEMINI_KEYS = {
    'type', 'description', 'enum', 'items', 'properties',
    'required', 'nullable', 'anyOf', 'format',
}
_GEMINI_FORMATS = {'date-time', 'date', 'time', 'duration', 'enum', 'int32', 'int64', 'float', 'double'}

# Ruido do Composio: sem valor para o modelo, caro em token.
_NOISE_KEYS = {
    'human_parameter_name', 'human_parameter_description',
    'examples', 'title', '$schema', 'file_uploadable',
}

_VALID_TYPES = {'string', 'number', 'integer', 'boolean', 'array', 'object', 'null'}


def _clean(node, keys: set[str] | None, drop: set[str]):
    if isinstance(node, list):
        return [_clean(n, keys, drop) for n in node]
    if not isinstance(node, dict):
        return node

    out = {}
    for k, v in node.items():
        if k in drop:
            continue
        if keys is not None and k not in keys:
            continue
        if k == 'properties' and isinstance(v, dict):
            # `properties` e' um MAPA nome->schema: os nomes dos campos nao
            # podem passar pelo whitelist, so os schemas aninhados.
            out[k] = {pname: _clean(pschema, keys, drop) for pname, pschema in v.items()}
        else:
            out[k] = _clean(v, keys, drop)

    # `type` como lista (ex.: ["string","null"]) nao e' aceito: vira nullable.
    t = out.get('type')
    if isinstance(t, list):
        non_null = [x for x in t if x != 'null']
        out['type'] = non_null[0] if non_null else 'string'
        if len(non_null) < len(t):
            out['nullable'] = True
    if isinstance(out.get('type'), str) and out['type'] not in _VALID_TYPES:
        out['type'] = 'string'

    if keys is _GEMINI_KEYS:
        fmt = out.get('format')
        if fmt is not None and fmt not in _GEMINI_FORMATS:
            out.pop('format', None)
        # objeto sem properties e array sem items confundem o Gemini
        if out.get('type') == 'object' and 'properties' not in out:
            out['properties'] = {}
        if out.get('type') == 'array' and 'items' not in out:
            out['items'] = {'type': 'string'}
    return out


def sanitize(parameters: dict, provider_type: str) -> dict:
    """Devolve o schema pronto para o `provider_type` informado."""
    if not isinstance(parameters, dict):
        return {'type': 'object', 'properties': {}}

    if provider_type == 'gemini':
        cleaned = _clean(parameters, _GEMINI_KEYS, _NOISE_KEYS)
    else:
        cleaned = _clean(parameters, None, _NOISE_KEYS)

    cleaned.setdefault('type', 'object')
    cleaned.setdefault('properties', {})
    # `required` citando um campo inexistente faz o Gemini recusar a declaracao
    props = cleaned.get('properties') or {}
    req = [r for r in (cleaned.get('required') or []) if r in props]
    if req:
        cleaned['required'] = req
    else:
        cleaned.pop('required', None)
    return cleaned
