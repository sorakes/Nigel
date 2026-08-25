"""
core/tools/composio_exec.py — Ponto único de execução de ferramentas do Composio.

Antes conviviam três contratos de falha na mesma classe: `create` levantava
exceção, `update`/`delete` devolviam `{"success": False}` e `list`/`fetch`
engoliam o erro e devolviam `[]`. A última era a pior: um 401 do Composio
renderizava como "Dia livre! Nenhum compromisso agendado" — indistinguível de
uma agenda genuinamente vazia.

Aqui existe um contrato só: sucesso devolve `data`, falha levanta
`ComposioToolError` com um `code` classificado, que sobe até o modelo para ele
poder explicar o que houve em vez de inventar sucesso.
"""

from __future__ import annotations

DEFAULT_USER_ID = 'default'

# Códigos de falha entregues ao modelo
NOT_CONNECTED = 'NOT_CONNECTED'
AUTH_EXPIRED = 'AUTH_EXPIRED'
RATE_LIMITED = 'RATE_LIMITED'
TIMEOUT = 'TIMEOUT'
BAD_ARGS = 'BAD_ARGS'
NOT_FOUND = 'NOT_FOUND'
UPSTREAM = 'UPSTREAM'


class ComposioToolError(Exception):
    def __init__(self, code: str, message: str, slug: str = ''):
        super().__init__(message)
        self.code = code
        self.message = message
        self.slug = slug

    def __str__(self) -> str:
        return f'[{self.code}] {self.message}'


def _classify(text: str) -> str:
    t = (text or '').lower()
    if '401' in t or 'unauthorized' in t or 'invalid api key' in t:
        return AUTH_EXPIRED
    if 'no connected account' in t or 'not connected' in t or 'connected account not found' in t:
        return NOT_CONNECTED
    if '429' in t or 'rate limit' in t or 'quota' in t:
        return RATE_LIMITED
    if 'timeout' in t or 'timed out' in t:
        return TIMEOUT
    if '404' in t or 'not found' in t:
        return NOT_FOUND
    if '400' in t or 'invalid' in t or 'required' in t or 'validation' in t:
        return BAD_ARGS
    return UPSTREAM


def _unwrap(result):
    """Extrai `data` de um ToolExecutionResponse, levantando se não teve sucesso."""
    if isinstance(result, dict):
        successful = result.get('successful', result.get('success', True))
        error = result.get('error')
        data = result.get('data')
    else:
        successful = getattr(result, 'successful', getattr(result, 'success', True))
        error = getattr(result, 'error', None)
        data = getattr(result, 'data', None)
        if data is None:
            data = getattr(result, 'response_data', None)

    if not successful or error:
        msg = str(error or 'ferramenta retornou sem sucesso')
        raise ComposioToolError(_classify(msg), msg)
    return data if data is not None else {}


def execute(slug: str, arguments: dict, *, user_id: str = DEFAULT_USER_ID):
    """Executa uma ferramenta do Composio. Devolve `data` ou levanta ComposioToolError."""
    from core.composio_manager import ComposioManager

    cm = ComposioManager.get_instance()
    if not cm.is_configured():
        raise ComposioToolError(
            NOT_CONNECTED,
            'Composio nao configurado. Abra Configuracoes -> Integracoes e informe a API Key.',
            slug)

    try:
        client = cm.get_client()
    except Exception as e:
        raise ComposioToolError(_classify(str(e)), str(e), slug) from e

    clean = {k: v for k, v in (arguments or {}).items() if v is not None and v != ''}

    try:
        raw = client.tools.execute(
            slug=slug, arguments=clean, user_id=user_id,
            dangerously_skip_version_check=True,
        )
    except TypeError:
        # SDKs antigos nao aceitam dangerously_skip_version_check
        try:
            raw = client.tools.execute(slug=slug, arguments=clean, user_id=user_id)
        except Exception as e:
            raise ComposioToolError(_classify(str(e)), str(e), slug) from e
    except Exception as e:
        raise ComposioToolError(_classify(str(e)), str(e), slug) from e

    try:
        return _unwrap(raw)
    except ComposioToolError as e:
        e.slug = slug
        raise


def is_connected(toolkit: str) -> bool:
    from core.composio_manager import ComposioManager
    try:
        return ComposioManager.get_instance().check_connection(toolkit)
    except Exception:
        return False


def require_connected(toolkit: str, human_name: str) -> None:
    if not is_connected(toolkit):
        raise ComposioToolError(
            NOT_CONNECTED,
            f'{human_name} nao esta conectado. Abra Configuracoes -> Integracoes para conectar.')
