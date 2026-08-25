"""
core/composio_manager.py — Gerenciador central de integrações e ferramentas via Composio SDK.

Gerencia:
- API Key e autenticação do Composio
- Autorização e status de contas conectadas (Google Calendar, Gmail, Outlook)
- Operações de Agenda no Google Calendar (criação, edição, remoção, listagem de eventos)
- Leitura de e-mails em background via ferramentas do Composio (Gmail e Outlook)
"""

import os
import webbrowser
from datetime import datetime
from dotenv import load_dotenv

from core.storage import load_config, save_config, load_secret, save_secret

# Slugs de toolkits suportados
TOOLKIT_GOOGLECALENDAR = 'googlecalendar'
TOOLKIT_GMAIL = 'gmail'
TOOLKIT_OUTLOOK = 'outlook'
TOOLKIT_SLACK = 'slack'
TOOLKIT_NOTION = 'notion'
TOOLKIT_GOOGLEDRIVE = 'googledrive'
TOOLKIT_GITHUB = 'github'
TOOLKIT_DISCORD = 'discord'
TOOLKIT_TRELLO = 'trello'
TOOLKIT_TODOIST = 'todoist'
TOOLKIT_ASANA = 'asana'

# Toda integracao que aparece em Configuracoes -> Integracoes. `chat_agent`
# tem ferramentas curadas para o slack; as demais ficam disponiveis pro
# `apps_agent` (descoberta dinamica) assim que conectadas — nao precisam de
# um core/tools/*.py proprio pra virarem uteis.
ALL_TOOLKITS = (
    TOOLKIT_GOOGLECALENDAR, TOOLKIT_GMAIL, TOOLKIT_OUTLOOK, TOOLKIT_SLACK,
    TOOLKIT_NOTION, TOOLKIT_GOOGLEDRIVE, TOOLKIT_GITHUB, TOOLKIT_DISCORD,
    TOOLKIT_TRELLO, TOOLKIT_TODOIST, TOOLKIT_ASANA,
)

DEFAULT_USER_ID = 'default'


def _extract_toolkit_slug(acc) -> str:
    """Extrai com segurança o slug do toolkit a partir de qualquer estrutura retornada pelo SDK."""
    if not acc:
        return ''
    # 1. Objeto acc.toolkit (Toolkit model com atributo slug)
    tk_obj = getattr(acc, 'toolkit', None)
    if tk_obj:
        if isinstance(tk_obj, str):
            return tk_obj.lower()
        slug = getattr(tk_obj, 'slug', None) or getattr(tk_obj, 'name', None)
        if slug:
            return str(slug).lower()
        if isinstance(tk_obj, dict):
            slug = tk_obj.get('slug') or tk_obj.get('name')
            if slug:
                return str(slug).lower()

    # 2. Objeto acc.auth_config.toolkit
    auth_cfg = getattr(acc, 'auth_config', None)
    if auth_cfg:
        tk_from_cfg = getattr(auth_cfg, 'toolkit', None)
        if tk_from_cfg:
            slug = getattr(tk_from_cfg, 'slug', None) or getattr(tk_from_cfg, 'name', None)
            if slug:
                return str(slug).lower()

    # 3. Campos diretos
    for attr in ['toolkit_slug', 'app_unique_id', 'toolkit_name']:
        val = getattr(acc, attr, None)
        if val:
            return str(val).lower()

    # 4. Formato dicionário
    if isinstance(acc, dict):
        tk_val = acc.get('toolkit')
        if isinstance(tk_val, dict):
            slug = tk_val.get('slug') or tk_val.get('name')
            if slug:
                return str(slug).lower()
        elif isinstance(tk_val, str):
            return tk_val.lower()
        for k in ['toolkit_slug', 'app_unique_id', 'toolkit_name']:
            val = acc.get(k)
            if val:
                return str(val).lower()

    return ''


class ComposioManager:
    _instance = None

    @classmethod
    def get_instance(cls) -> 'ComposioManager':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        load_dotenv(override=True)
        self._api_key = self._load_api_key()
        self._cached_client = None
        self._cached_client_key = None
        self._status_cache = {}
        self._last_status_check = None

    def _load_api_key(self) -> str:
        """Carrega a chave de API do Composio de .env, storage ou keyring."""
        key = os.getenv('COMPOSIO_API_KEY', '').strip()
        if not key:
            key = os.getenv('NIGEL_COMPOSIO_API_KEY', '').strip()
        if not key:
            key = (load_config().get('composio_api_key') or '').strip()
        if not key:
            key = load_secret('composio', 'api_key').strip()
        return key

    def get_api_key(self) -> str:
        if not self._api_key:
            self._api_key = self._load_api_key()
        return self._api_key

    def set_api_key(self, api_key: str) -> None:
        """Salva a chave de API no config.json e no keyring."""
        self._api_key = (api_key or '').strip()
        save_config({'composio_api_key': self._api_key})
        save_secret('composio', 'api_key', self._api_key)
        self._cached_client = None
        self._cached_client_key = None
        self._status_cache.clear()

        # Salva também no .env se possível
        try:
            from core.api_client import APIClient
            APIClient().save_settings({'COMPOSIO_API_KEY': self._api_key})
        except Exception:
            pass

    def is_configured(self) -> bool:
        """Retorna se há uma API key válida configurada (pelo menos 12 caracteres e não placeholder)."""
        key = self.get_api_key()
        if not key or len(key) < 12:
            return False
        key_lower = key.lower()
        if any(ph in key_lower for ph in ['your_composio_api_key', 'your_api_key', 'chave_aqui', 'insert_key', 'api_key_aqui', '<your_']):
            return False
        return True

    def get_client(self):
        """Retorna o cliente SDK Composio autenticado."""
        api_key = self.get_api_key()
        if not api_key:
            raise ValueError("Composio API Key não configurada. Configure em Settings → Sync.")
        if self._cached_client is not None and self._cached_client_key == api_key:
            return self._cached_client
        try:
            from composio import Composio
            try:
                self._cached_client = Composio(api_key=api_key, timeout=30.0)
            except TypeError:
                # SDK antigo sem `timeout` no construtor
                self._cached_client = Composio(api_key=api_key)
            self._cached_client_key = api_key
            return self._cached_client
        except Exception as e:
            print(f"[ComposioManager] Erro ao instanciar Composio: {e}")
            raise

    def execute_tool(self, slug: str, arguments: dict, user_id: str = DEFAULT_USER_ID):
        """Executa uma ferramenta do Composio com version check bypass para execução dinâmica segura."""
        client = self.get_client()
        try:
            return client.tools.execute(
                slug=slug,
                arguments=arguments,
                user_id=user_id,
                dangerously_skip_version_check=True
            )
        except TypeError:
            return client.tools.execute(
                slug=slug,
                arguments=arguments,
                user_id=user_id
            )

    # -------------------------------------------------------------------------
    # Conexões e Autorizações (OAuth)
    # -------------------------------------------------------------------------

    def authorize_toolkit(self, toolkit: str, open_browser: bool = True) -> str:
        """
        Inicia o fluxo de autorização OAuth para um toolkit (ex: 'googlecalendar', 'gmail', 'outlook').
        Retorna a URL de redirecionamento para autenticação.
        """
        client = self.get_client()
        try:
            print(f"[ComposioManager] Solicitando autorização para toolkit: {toolkit}...")
            connection_request = None
            try:
                # API publica primeiro; o caminho privado abaixo quebra a cada
                # atualizacao do SDK e so serve como rede de seguranca.
                connection_request = client.toolkits.authorize(
                    user_id=DEFAULT_USER_ID,
                    toolkit=toolkit
                )
            except Exception as e_init:
                err_str = str(e_init)
                if 'Multiple connected accounts' in err_str or 'already exists' in err_str:
                    self.check_connection(toolkit, force_refresh=True)
                    return ''
                auth_config_id = client.toolkits._get_auth_config_id(toolkit=toolkit)
                connection_request = client.connected_accounts.initiate(
                    user_id=DEFAULT_USER_ID,
                    auth_config_id=auth_config_id,
                    allow_multiple=True
                )

            redirect_url = getattr(connection_request, 'redirect_url', None) or getattr(connection_request, 'url', None)
            if not redirect_url and isinstance(connection_request, dict):
                redirect_url = connection_request.get('redirect_url') or connection_request.get('url')

            if redirect_url and open_browser:
                print(f"[ComposioManager] Abrindo URL de autenticação no navegador: {redirect_url}")
                webbrowser.open(redirect_url)

            return redirect_url or ''
        except Exception as e:
            if 'Multiple connected accounts' in str(e):
                self.check_connection(toolkit, force_refresh=True)
                return ''
            print(f"[ComposioManager] Erro ao autorizar toolkit {toolkit}: {e}")
            raise

    def check_connection(self, toolkit: str, force_refresh: bool = False) -> bool:
        """Verifica se um toolkit possui uma conta ativa conectada."""
        if not self.is_configured():
            return False

        now = datetime.now()
        if not force_refresh and self._last_status_check and (now - self._last_status_check).total_seconds() < 10:
            if toolkit in self._status_cache:
                return self._status_cache[toolkit]

        try:
            client = self.get_client()
            # Lista contas ativas com timeout curto para não travar
            response = client.connected_accounts.list(
                user_ids=[DEFAULT_USER_ID],
                statuses=['ACTIVE'],
                timeout=5.0
            )
            items = getattr(response, 'items', None) or getattr(response, 'data', None) or response
            if isinstance(items, list):
                active_toolkits = set()
                for acc in items:
                    tk = _extract_toolkit_slug(acc)
                    if tk:
                        active_toolkits.add(tk.lower())

                # Antes so' 3 chaves fixas eram guardadas aqui — qualquer outra
                # conta ativa (Slack, Notion...) sumia do cache mesmo com a API
                # confirmando a conexao. Agora guarda TODAS as contas ativas
                # que a API devolveu, mais aliases conhecidos pros 3 slugs
                # historicos cujo nome no Composio diverge do nosso.
                self._status_cache = {tk: True for tk in active_toolkits}
                self._status_cache[TOOLKIT_GOOGLECALENDAR] = bool(
                    active_toolkits & {TOOLKIT_GOOGLECALENDAR, 'google_calendar'})
                self._status_cache[TOOLKIT_OUTLOOK] = bool(
                    active_toolkits & {TOOLKIT_OUTLOOK, 'microsoft'})
                self._last_status_check = now
                return bool(self._status_cache.get(toolkit, False))

            return False
        except Exception as e:
            err_str = str(e)
            if 'Multiple connected accounts' in err_str:
                self._status_cache[toolkit] = True
                self._last_status_check = now
                return True
            if '401' in err_str or 'Unauthorized' in err_str:
                if not getattr(self, '_suppress_401_log', False):
                    print("[ComposioManager] Composio API Key não autorizada (401). Verifique a chave no Settings.")
                    self._suppress_401_log = True
            else:
                print(f"[ComposioManager] Erro ao checar conexão do toolkit {toolkit}: {e}")
            # Uma falha transitoria (timeout, 401 pontual) nao prova que TUDO
            # desconectou — so marca o toolkit consultado, preserva o resto.
            self._status_cache[toolkit] = False
            self._last_status_check = now
            return False

    def get_all_connection_statuses(self, force_refresh: bool = False,
                                    toolkits: tuple[str, ...] | None = None) -> dict[str, bool]:
        """Retorna o mapa de status das integrações pedidas (padrão: `ALL_TOOLKITS`)."""
        toolkits = toolkits or ALL_TOOLKITS
        if not self.is_configured():
            return {tk: False for tk in toolkits}

        # Uma checagem de qualquer toolkit ja atualiza o cache inteiro (a API
        # lista todas as contas ativas de uma vez — ver check_connection).
        self.check_connection(toolkits[0], force_refresh=force_refresh)
        return {tk: self._status_cache.get(tk, False) for tk in toolkits}

    def has_connected_agenda(self, force_refresh: bool = False) -> bool:
        """Verifica se a agenda oficial (Google Calendar) está conectada."""
        statuses = self.get_all_connection_statuses(force_refresh=force_refresh)
        return bool(statuses.get(TOOLKIT_GOOGLECALENDAR))

    def get_active_agenda_type(self) -> str:
        """Retorna 'googlecalendar' ou 'none'."""
        statuses = self.get_all_connection_statuses()
        if statuses.get(TOOLKIT_GOOGLECALENDAR, False):
            return TOOLKIT_GOOGLECALENDAR
        return 'none'

    # -------------------------------------------------------------------------
    # Operações de Agenda no Google Calendar (Agenda Oficial)
    # -------------------------------------------------------------------------

    def calendar_create_event(self, title: str, description: str = '', start_time: str | datetime = None, duration_minutes: int = 30) -> dict:
        """Cria um evento no Google Calendar via Composio com o schema oficial correto."""
        if not self.check_connection(TOOLKIT_GOOGLECALENDAR):
            raise RuntimeError("Google Calendar não está conectado no Composio.")

        start_dt = start_time if isinstance(start_time, datetime) else datetime.fromisoformat(str(start_time or datetime.now().isoformat()))
        start_iso = start_dt.strftime('%Y-%m-%dT%H:%M:%S')

        try:
            result = self.execute_tool(
                slug="GOOGLECALENDAR_CREATE_EVENT",
                arguments={
                    "summary": title,
                    "description": description or f"Criado pelo Nigel em {datetime.now().strftime('%d/%m/%Y %H:%M')}",
                    "start_datetime": start_iso,
                    "event_duration_minutes": max(1, min(59, duration_minutes)),
                    "calendar_id": "primary"
                },
                user_id=DEFAULT_USER_ID
            )
            resp_data = getattr(result, 'data', None) or getattr(result, 'response_data', None) or result
            event_id = ''
            if isinstance(resp_data, dict):
                event_id = resp_data.get('id') or resp_data.get('event_id') or resp_data.get('data', {}).get('id') or ''
            return {"success": True, "ref_id": str(event_id), "provider": "googlecalendar", "title": title, "due_at": start_iso}
        except Exception as e:
            print(f"[ComposioManager] Erro ao criar evento no Google Calendar: {e}")
            raise

    def calendar_update_event(self, event_id: str, title: str = '', description: str = '', start_time: str | datetime = None, duration_minutes: int = 30) -> dict:
        """Atualiza um evento existente no Google Calendar."""
        if not self.check_connection(TOOLKIT_GOOGLECALENDAR):
            raise RuntimeError("Google Calendar não está conectado no Composio.")
        if not event_id:
            return {"success": False, "error": "event_id obrigatório"}

        args = {"event_id": str(event_id), "calendar_id": "primary"}
        if start_time:
            start_dt = start_time if isinstance(start_time, datetime) else datetime.fromisoformat(str(start_time))
            args["start_datetime"] = start_dt.strftime('%Y-%m-%dT%H:%M:%S')
            args["event_duration_minutes"] = max(1, min(59, duration_minutes))
        else:
            args["start_datetime"] = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

        if title:
            args["summary"] = title
        if description is not None:
            args["description"] = description

        try:
            result = self.execute_tool(
                slug="GOOGLECALENDAR_UPDATE_EVENT",
                arguments=args,
                user_id=DEFAULT_USER_ID
            )
            return {"success": True, "event_id": str(event_id), "provider": "googlecalendar"}
        except Exception as e:
            print(f"[ComposioManager] Erro ao atualizar evento no Google Calendar: {e}")
            return {"success": False, "error": str(e)}

    def calendar_delete_event(self, event_id: str) -> dict:
        """Remove um evento no Google Calendar."""
        if not self.check_connection(TOOLKIT_GOOGLECALENDAR):
            return {"success": False, "error": "Google Calendar desconectado"}
        if not event_id:
            return {"success": False, "error": "event_id obrigatório"}

        try:
            result = self.execute_tool(
                slug="GOOGLECALENDAR_DELETE_EVENT",
                arguments={"event_id": str(event_id), "calendar_id": "primary"},
                user_id=DEFAULT_USER_ID
            )
            return {"success": True, "event_id": str(event_id)}
        except Exception as e:
            print(f"[ComposioManager] Erro ao remover evento no Google Calendar: {e}")
            return {"success": False, "error": str(e)}

    def calendar_list_events(self, limit: int = 100, query: str = '', time_min: datetime | str = None, time_max: datetime | str = None) -> list[dict]:
        """Lista eventos da agenda oficial no Google Calendar para o espelhamento."""
        if not self.check_connection(TOOLKIT_GOOGLECALENDAR):
            return []

        try:
            if time_min is None:
                # Começo do mês atual como padrão
                t_min_dt = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                t_min_str = t_min_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
            elif isinstance(time_min, datetime):
                t_min_str = time_min.strftime('%Y-%m-%dT%H:%M:%SZ')
            else:
                t_min_str = str(time_min)

            args = {
                "maxResults": limit,
                "calendarId": "primary",
                "timeMin": t_min_str,
                "singleEvents": True,
                "orderBy": "startTime"
            }
            if time_max is not None:
                if isinstance(time_max, datetime):
                    args["timeMax"] = time_max.strftime('%Y-%m-%dT%H:%M:%SZ')
                else:
                    args["timeMax"] = str(time_max)

            if query:
                args["q"] = query

            result = self.execute_tool(
                slug="GOOGLECALENDAR_EVENTS_LIST",
                arguments=args,
                user_id=DEFAULT_USER_ID
            )
            # execute_tool retorna dict com chaves: 'data', 'error', 'successful'
            # Usa .get() para dict ou getattr para objetos SDK
            if isinstance(result, dict):
                data = result.get('data') or {}
            else:
                data = getattr(result, 'data', None) or getattr(result, 'response_data', None) or result
            items = data.get('items', []) if isinstance(data, dict) else (data if isinstance(data, list) else [])

            events = []
            for ev in items:
                if isinstance(ev, dict):
                    events.append({
                        'id': ev.get('id', ''),
                        'summary': ev.get('summary') or '(sem título)',
                        'description': ev.get('description', ''),
                        'start': ev.get('start', {}).get('dateTime') or ev.get('start', {}).get('date', ''),
                        'end': ev.get('end', {}).get('dateTime') or ev.get('end', {}).get('date', ''),
                        'location': ev.get('location', ''),
                        'htmlLink': ev.get('htmlLink', '')
                    })
            return events
        except Exception as e:
            print(f"[ComposioManager] Erro ao listar eventos do Google Calendar: {e}")
            return []

    # -------------------------------------------------------------------------
    # Leitura de E-mails (Gmail & Outlook) via Composio
    # -------------------------------------------------------------------------

    def fetch_unread_gmail(self, limit: int = 10) -> list[dict]:
        """Busca e-mails não lidos no Gmail via Composio."""
        if not self.check_connection(TOOLKIT_GMAIL):
            return []

        try:
            result = self.execute_tool(
                slug="GMAIL_FETCH_EMAILS",
                arguments={"query": "is:unread", "max_results": limit},
                user_id=DEFAULT_USER_ID
            )
            data = getattr(result, 'data', None) or getattr(result, 'response_data', None) or result
            messages = []
            raw_list = data.get('messages', []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            for m in raw_list:
                if isinstance(m, dict):
                    msg_id = m.get('id', '')
                    subject = m.get('subject') or m.get('title') or '(sem assunto)'
                    sender = m.get('from') or m.get('sender') or ''
                    snippet = m.get('snippet') or m.get('body') or m.get('preview') or ''
                    messages.append({
                        'id': f"gmail:{msg_id}",
                        'source': 'gmail',
                        'subject': subject,
                        'sender': sender,
                        'body_preview': snippet
                    })
            return messages
        except Exception as e:
            print(f"[ComposioManager] Erro ao buscar e-mails do Gmail: {e}")
            return []

    def fetch_unread_outlook(self, limit: int = 10) -> list[dict]:
        """Busca e-mails não lidos no Outlook via Composio com a ferramenta OUTLOOK_LIST_MESSAGES."""
        if not self.check_connection(TOOLKIT_OUTLOOK):
            return []

        try:
            result = self.execute_tool(
                slug="OUTLOOK_LIST_MESSAGES",
                arguments={"top": limit, "is_read": False},
                user_id=DEFAULT_USER_ID
            )
            data = getattr(result, 'data', None) or getattr(result, 'response_data', None) or result
            messages = []
            raw_list = data.get('value', []) if isinstance(data, dict) else (data.get('messages', []) if isinstance(data, dict) else (data if isinstance(data, list) else []))
            for m in raw_list:
                if isinstance(m, dict):
                    msg_id = m.get('id', '')
                    subject = m.get('subject') or '(sem assunto)'
                    sender = m.get('from', {}).get('emailAddress', {}).get('address', '') if isinstance(m.get('from'), dict) else str(m.get('from', ''))
                    preview = m.get('bodyPreview') or m.get('body', '')
                    messages.append({
                        'id': f"outlook:{msg_id}",
                        'source': 'outlook',
                        'subject': subject,
                        'sender': sender,
                        'body_preview': preview
                    })
            return messages
        except Exception as e:
            print(f"[ComposioManager] Erro ao buscar e-mails do Outlook: {e}")
            return []
