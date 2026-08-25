"""
core/tools/email_tools.py — Ferramentas de e-mail (Gmail e Outlook).

Antes o e-mail era só leitura: `fetch_unread_gmail` e `fetch_unread_outlook`,
mais nada. Aqui entram busca, leitura de thread, resposta, rascunho, envio,
rotulagem e arquivamento.

Enviar e responder são ações externas irreversíveis: vão marcadas com
`requires_confirmation=True` para a UI pedir confirmação antes de executar.
Um agente com envio livre está a uma alucinação de mandar e-mail para o chefe
do usuário.
"""

from __future__ import annotations

from core.agent.registry import Tool, ToolResult, ok, fail
from core.llm.types import ToolSpec
from core.tools import composio_exec as cx

GMAIL = 'gmail'
OUTLOOK = 'outlook'


def _accounts() -> dict:
    from core.composio_manager import ComposioManager
    try:
        return ComposioManager.get_instance().get_all_connection_statuses()
    except Exception:
        return {}


def _msgs(data) -> list:
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for k in ('messages', 'value', 'items', 'threads', 'data', 'response_data'):
        v = data.get(k)
        if isinstance(v, list):
            return v
        if isinstance(v, dict):
            for k2 in ('messages', 'value', 'items'):
                if isinstance(v.get(k2), list):
                    return v[k2]
    return []


def _txt(*candidates) -> str:
    """Primeiro candidato util, sempre como str.

    Campos do Gmail as vezes chegam como dict (ex. `payload.body`), e um
    fatiamento direto quebrava a busca inteira.
    """
    for c in candidates:
        if isinstance(c, str) and c.strip():
            return c
        if isinstance(c, dict):
            for k in ('text', 'data', 'content', 'value'):
                v = c.get(k)
                if isinstance(v, str) and v.strip():
                    return v
        if isinstance(c, list) and c:
            return _txt(*c)
    return ''


def _shape_gmail(m: dict) -> dict:
    payload = m.get('payload') or {}
    headers = {h.get('name', '').lower(): h.get('value', '')
               for h in (payload.get('headers') or []) if isinstance(h, dict)}
    return {
        'id': m.get('messageId') or m.get('id') or '',
        'thread_id': m.get('threadId') or m.get('thread_id') or '',
        'source': 'gmail',
        'from': _txt(m.get('sender'), m.get('from'), headers.get('from')),
        'to': _txt(m.get('to'), headers.get('to')),
        'subject': _txt(m.get('subject'), headers.get('subject')) or '(sem assunto)',
        'date': _txt(m.get('messageTimestamp'), headers.get('date')),
        'preview': _txt(m.get('snippet'), m.get('preview'), m.get('messageText'),
                        (m.get('payload') or {}).get('body'))[:400],
        'labels': m.get('labelIds') or [],
    }


def _shape_outlook(m: dict) -> dict:
    frm = m.get('from')
    if isinstance(frm, dict):
        frm = (frm.get('emailAddress') or {}).get('address', '')
    return {
        'id': m.get('id', ''),
        'thread_id': m.get('conversationId', ''),
        'source': 'outlook',
        'from': _txt(frm),
        'subject': _txt(m.get('subject')) or '(sem assunto)',
        'date': _txt(m.get('receivedDateTime')),
        'preview': _txt(m.get('bodyPreview'), m.get('body'))[:400],
        'read': m.get('isRead'),
    }


# --------------------------------------------------------------------------- leitura

def _search(args, ctx) -> ToolResult:
    st = _accounts()
    if not st.get(GMAIL) and not st.get(OUTLOOK):
        return fail(cx.NOT_CONNECTED,
                    'Nenhuma conta de e-mail conectada. Abra Configuracoes -> Integracoes.')

    limit = min(int(args.get('max_results') or 10), 25)
    query = (args.get('query') or '').strip()
    only_unread = bool(args.get('unread_only'))
    out, errors = [], []

    if st.get(GMAIL):
        q = query
        if only_unread:
            q = (q + ' is:unread').strip()
        try:
            data = cx.execute('GMAIL_FETCH_EMAILS',
                              {'query': q or 'in:inbox', 'max_results': limit})
            out += [_shape_gmail(m) for m in _msgs(data) if isinstance(m, dict)]
        except cx.ComposioToolError as e:
            errors.append(f'gmail: {e.code}')

    if st.get(OUTLOOK):
        try:
            payload = {'top': limit}
            if only_unread:
                payload['is_read'] = False
            if query:
                payload['search'] = query
            data = cx.execute('OUTLOOK_LIST_MESSAGES', payload)
            out += [_shape_outlook(m) for m in _msgs(data) if isinstance(m, dict)]
        except cx.ComposioToolError as e:
            errors.append(f'outlook: {e.code}')

    if not out and errors:
        return fail(cx.UPSTREAM, '; '.join(errors))
    body = {'messages': out, 'count': len(out)}
    if errors:
        body['partial_errors'] = errors

    # De onde vieram os resultados: mostra o icone certo (Gmail/Outlook) em vez
    # de um envelope generico, ou o generico so quando a busca abrange as duas
    # contas de verdade.
    sources = {m.get('source') for m in out}
    if sources == {'gmail'}:
        icon = 'brand_gmail'
    elif sources == {'outlook'}:
        icon = 'brand_outlook'
    elif sources:
        icon = 'email'
    else:
        icon = 'brand_gmail' if st.get(GMAIL) else ('brand_outlook' if st.get(OUTLOOK) else 'email')

    return ok(body, user_message=f'{len(out)} e-mail(s)', icon=icon)


def _read_thread(args, ctx) -> ToolResult:
    tid = (args.get('thread_id') or '').strip()
    mid = (args.get('message_id') or '').strip()
    source = (args.get('source') or 'gmail').strip().lower()
    if not tid and not mid:
        return fail(cx.BAD_ARGS, 'informe `thread_id` ou `message_id`')

    if source == 'outlook':
        cx.require_connected(OUTLOOK, 'Outlook')
        data = cx.execute('OUTLOOK_GET_MESSAGE', {'message_id': mid or tid})
        msgs = [_shape_outlook(m) for m in _msgs(data) if isinstance(m, dict)]
        if not msgs and isinstance(data, dict) and data.get('id'):
            msgs = [_shape_outlook(data)]
        return ok({'messages': msgs, 'count': len(msgs)}, user_message='Conversa lida', icon='brand_outlook')

    cx.require_connected(GMAIL, 'Gmail')
    if tid:
        data = cx.execute('GMAIL_FETCH_MESSAGE_BY_THREAD_ID', {'thread_id': tid})
    else:
        data = cx.execute('GMAIL_FETCH_MESSAGE_BY_MESSAGE_ID', {'message_id': mid})
    msgs = [_shape_gmail(m) for m in _msgs(data) if isinstance(m, dict)]
    if not msgs and isinstance(data, dict):
        msgs = [_shape_gmail(data)]
    return ok({'messages': msgs, 'count': len(msgs)}, user_message='Conversa lida', icon='brand_gmail')


def _list_labels(args, ctx) -> ToolResult:
    cx.require_connected(GMAIL, 'Gmail')
    data = cx.execute('GMAIL_LIST_LABELS', {})
    labels = [{'id': l.get('id'), 'name': l.get('name')}
              for l in _msgs(data) or (data.get('labels') if isinstance(data, dict) else [])
              if isinstance(l, dict)]
    return ok({'labels': labels}, user_message=f'{len(labels)} rotulo(s)')


# --------------------------------------------------------------------------- escrita

def _send(args, ctx) -> ToolResult:
    to = args.get('to')
    subject = (args.get('subject') or '').strip()
    body = (args.get('body') or '').strip()
    source = (args.get('source') or 'gmail').strip().lower()
    if not to:
        return fail(cx.BAD_ARGS, '`to` e obrigatorio')
    if not body:
        return fail(cx.BAD_ARGS, '`body` e obrigatorio')
    recipients = to if isinstance(to, list) else [to]

    if source == 'outlook':
        cx.require_connected(OUTLOOK, 'Outlook')
        payload = {'to': ';'.join(recipients), 'subject': subject, 'body': body}
        if args.get('cc'):
            payload['cc_emails'] = args['cc'] if isinstance(args['cc'], list) else [args['cc']]
        cx.execute('OUTLOOK_SEND_EMAIL', payload)
        return ok({'sent': True, 'to': recipients, 'subject': subject},
                  user_message=f'E-mail enviado para {recipients[0]}', icon='brand_outlook')

    cx.require_connected(GMAIL, 'Gmail')
    payload = {'recipient_email': recipients[0], 'subject': subject, 'body': body}
    if len(recipients) > 1:
        payload['cc'] = recipients[1:]
    if args.get('cc'):
        payload['cc'] = args['cc'] if isinstance(args['cc'], list) else [args['cc']]
    cx.execute('GMAIL_SEND_EMAIL', payload)
    return ok({'sent': True, 'to': recipients, 'subject': subject},
              user_message=f'E-mail enviado para {recipients[0]}', icon='brand_gmail')


def _draft(args, ctx) -> ToolResult:
    to = args.get('to')
    source = (args.get('source') or 'gmail').strip().lower()
    if not to:
        return fail(cx.BAD_ARGS, '`to` e obrigatorio')
    recipients = to if isinstance(to, list) else [to]

    if source == 'outlook':
        cx.require_connected(OUTLOOK, 'Outlook')
        data = cx.execute('OUTLOOK_CREATE_DRAFT', {
            'to_recipients': recipients,
            'subject': args.get('subject') or '',
            'body': args.get('body') or '',
        })
        did = data.get('id') if isinstance(data, dict) else ''
        return ok({'draft_created': True, 'draft_id': did, 'to': recipients},
                  user_message='Rascunho criado', icon='brand_outlook')

    cx.require_connected(GMAIL, 'Gmail')
    data = cx.execute('GMAIL_CREATE_EMAIL_DRAFT', {
        'recipient_email': recipients[0],
        'subject': args.get('subject') or '',
        'body': args.get('body') or '',
    })
    did = data.get('id') if isinstance(data, dict) else ''
    return ok({'draft_created': True, 'draft_id': did, 'to': recipients},
              user_message='Rascunho criado', icon='brand_gmail')


def _reply(args, ctx) -> ToolResult:
    tid = (args.get('thread_id') or '').strip()
    mid = (args.get('message_id') or '').strip()
    body = (args.get('body') or '').strip()
    source = (args.get('source') or 'gmail').strip().lower()
    if not body:
        return fail(cx.BAD_ARGS, '`body` e obrigatorio')

    if source == 'outlook':
        # Outlook responde por message_id (nao existe "thread" como no Gmail).
        target = mid or tid
        if not target:
            return fail(cx.BAD_ARGS, '`message_id` e obrigatorio (use email_search antes)')
        cx.require_connected(OUTLOOK, 'Outlook')
        payload = {'message_id': target, 'comment': body}
        if args.get('cc'):
            payload['cc_emails'] = args['cc'] if isinstance(args['cc'], list) else [args['cc']]
        cx.execute('OUTLOOK_REPLY_EMAIL', payload)
        return ok({'replied': True, 'message_id': target}, user_message='Resposta enviada', icon='brand_outlook')

    if not tid:
        return fail(cx.BAD_ARGS, '`thread_id` e obrigatorio (use email_search antes)')
    cx.require_connected(GMAIL, 'Gmail')
    payload = {'thread_id': tid, 'message_body': body}
    if args.get('to'):
        payload['recipient_email'] = args['to'] if isinstance(args['to'], str) else args['to'][0]
    cx.execute('GMAIL_REPLY_TO_THREAD', payload)
    return ok({'replied': True, 'thread_id': tid}, user_message='Resposta enviada', icon='brand_gmail')


def _archive(args, ctx) -> ToolResult:
    mid = (args.get('message_id') or '').strip()
    source = (args.get('source') or 'gmail').strip().lower()
    if not mid:
        return fail(cx.BAD_ARGS, '`message_id` e obrigatorio')

    if source == 'outlook':
        cx.require_connected(OUTLOOK, 'Outlook')
        cx.execute('OUTLOOK_MOVE_MESSAGE', {'message_id': mid, 'destination_id': 'archive'})
        return ok({'archived': True, 'message_id': mid}, user_message='E-mail arquivado', icon='brand_outlook')

    cx.require_connected(GMAIL, 'Gmail')
    cx.execute('GMAIL_REMOVE_LABEL', {'message_id': mid, 'label_name': 'INBOX'})
    return ok({'archived': True, 'message_id': mid}, user_message='E-mail arquivado', icon='brand_gmail')


def _label(args, ctx) -> ToolResult:
    mid = (args.get('message_id') or '').strip()
    name = (args.get('label') or '').strip()
    source = (args.get('source') or 'gmail').strip().lower()
    if not mid or not name:
        return fail(cx.BAD_ARGS, '`message_id` e `label` sao obrigatorios')

    if source == 'outlook':
        # Outlook nao tem rotulos como o Gmail; o unico caso pratico que cobrimos
        # e' marcar como lido/nao lido, reaproveitando esta mesma ferramenta.
        if name.strip().upper() != 'UNREAD':
            return fail(cx.BAD_ARGS,
                        'no Outlook so e possivel marcar como lido/nao lido '
                        '(label="UNREAD"); categorias nao sao suportadas ainda.')
        cx.require_connected(OUTLOOK, 'Outlook')
        is_read = bool(args.get('remove'))  # remove=True em cima de UNREAD == marcar como lido
        cx.execute('OUTLOOK_UPDATE_EMAIL', {'message_id': mid, 'is_read': is_read})
        return ok({'ok': True, 'message_id': mid, 'is_read': is_read},
                  user_message='Marcado como lido' if is_read else 'Marcado como nao lido',
                  icon='brand_outlook')

    cx.require_connected(GMAIL, 'Gmail')
    slug = 'GMAIL_REMOVE_LABEL' if args.get('remove') else 'GMAIL_ADD_LABEL_TO_EMAIL'
    cx.execute(slug, {'message_id': mid, 'label_name': name})
    verbo = 'removido de' if args.get('remove') else 'aplicado a'
    return ok({'ok': True, 'message_id': mid, 'label': name},
              user_message=f'Rotulo {name} {verbo} 1 e-mail', icon='brand_gmail')


def _trash(args, ctx) -> ToolResult:
    mid = (args.get('message_id') or '').strip()
    source = (args.get('source') or 'gmail').strip().lower()
    if not mid:
        return fail(cx.BAD_ARGS, '`message_id` e obrigatorio')

    if source == 'outlook':
        cx.require_connected(OUTLOOK, 'Outlook')
        cx.execute('OUTLOOK_DELETE_MESSAGE', {'message_id': mid})
        return ok({'trashed': True, 'message_id': mid},
                  user_message='E-mail movido para a lixeira', icon='brand_outlook')

    cx.require_connected(GMAIL, 'Gmail')
    cx.execute('GMAIL_MOVE_TO_TRASH', {'message_id': mid})
    return ok({'trashed': True, 'message_id': mid},
              user_message='E-mail movido para a lixeira', icon='brand_gmail')


# --------------------------------------------------------------------------- specs

def _obj(props: dict, required: list[str] | None = None) -> dict:
    schema = {'type': 'object', 'properties': props}
    if required:
        schema['required'] = required
    return schema

_MID = {'type': 'string', 'description': 'id da mensagem, vindo de email_search'}
_TID = {'type': 'string', 'description': 'id da conversa (thread), vindo de email_search'}


def build_tools() -> list[Tool]:
    _SRC = {'type': 'string', 'enum': ['gmail', 'outlook'],
            'description': "de qual conta agir — 'gmail' ou 'outlook', conforme o campo "
                           "`source` que email_search devolveu para essa mensagem. Padrao: gmail."}
    return [
        Tool(ToolSpec('email_search',
             'Busca e-mails no Gmail e no Outlook. Cada resultado traz `source` (gmail/outlook), '
             '`id` e `thread_id` — guarde o `source` junto do id para usar nas outras ferramentas.',
             _obj({'query': {'type': 'string', 'description': 'texto, remetente ou sintaxe do Gmail (ex. from:joao)'},
                   'unread_only': {'type': 'boolean'},
                   'max_results': {'type': 'integer'}}),
             parallel_safe=True), _search, label='Buscando e-mails'),
             # icon deixado em branco de proposito: _search descobre em runtime se
             # o resultado veio do Gmail, do Outlook ou dos dois, e define sozinho.

        Tool(ToolSpec('email_read_thread',
             'Le a conversa completa de um e-mail, no Gmail ou no Outlook.',
             _obj({'thread_id': _TID, 'message_id': _MID, 'source': _SRC}), parallel_safe=True),
             _read_thread, label='Lendo conversa', icon='brand_gmail'),

        Tool(ToolSpec('email_list_labels', 'Lista os rotulos do Gmail disponiveis.',
             _obj({}), parallel_safe=True), _list_labels, label='Listando rotulos', icon='brand_gmail'),

        Tool(ToolSpec('email_draft',
             'Cria um RASCUNHO de e-mail no Gmail ou no Outlook, sem enviar. '
             'Prefira esta quando estiver em duvida.',
             _obj({'to': {'type': 'array', 'items': {'type': 'string'}},
                   'subject': {'type': 'string'},
                   'body': {'type': 'string'},
                   'source': _SRC}, ['to', 'body'])),
             _draft, label='Criando rascunho', icon='brand_gmail'),

        Tool(ToolSpec('email_send',
             'ENVIA um e-mail pelo Gmail ou pelo Outlook. Acao externa irreversivel: '
             'sera confirmada pelo usuario.',
             _obj({'to': {'type': 'array', 'items': {'type': 'string'}},
                   'cc': {'type': 'array', 'items': {'type': 'string'}},
                   'subject': {'type': 'string'},
                   'body': {'type': 'string'},
                   'source': _SRC}, ['to', 'body'])),
             _send, label='Enviando e-mail', icon='brand_gmail', requires_confirmation=True),

        Tool(ToolSpec('email_reply',
             'RESPONDE a uma conversa existente no Gmail (use `thread_id`) ou no Outlook '
             '(use `message_id`). Acao externa irreversivel: sera confirmada.',
             _obj({'thread_id': _TID, 'message_id': _MID, 'body': {'type': 'string'},
                   'to': {'type': 'string'}, 'source': _SRC}, ['body'])),
             _reply, label='Respondendo e-mail', icon='brand_gmail', requires_confirmation=True),

        Tool(ToolSpec('email_archive', 'Arquiva um e-mail do Gmail ou do Outlook (tira da caixa de entrada).',
             _obj({'message_id': _MID, 'source': _SRC}, ['message_id'])),
             _archive, label='Arquivando', icon='brand_gmail'),

        Tool(ToolSpec('email_label',
             'Aplica ou remove um rotulo do Gmail. No Outlook so cobre marcar como lido/nao lido '
             '(label="UNREAD").',
             _obj({'message_id': _MID, 'label': {'type': 'string'},
                   'remove': {'type': 'boolean', 'description': 'true para remover em vez de aplicar'},
                   'source': _SRC},
                  ['message_id', 'label'])), _label, label='Rotulando', icon='brand_gmail'),

        Tool(ToolSpec('email_trash', 'Move um e-mail do Gmail ou do Outlook para a lixeira.',
             _obj({'message_id': _MID, 'source': _SRC}, ['message_id'])),
             _trash, label='Movendo para lixeira', icon='brand_gmail', requires_confirmation=True),
    ]
