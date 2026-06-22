"""
ui/agenda_skills.py — Sistema compartilhado de skills de agenda do SEQ.

Usado pelo chat principal (Bar) e pelos popups de lembrete (ScheduleAlertDialog).
A IA retorna JSON com actions/buttons; a UI nativa garante confirmação do usuário.
"""

import json
import re
import uuid
import unicodedata
from datetime import datetime, timedelta
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

_CLOSING_ACTIONS = frozenset({'reschedule', 'delete_current', 'postpone', 'mark_done', 'delete_schedule'})

_CHAT_SKILLS_DOC = '''
## FERRAMENTAS DE AGENDA (lembretes locais do SEQ)

Você pode ajudar o usuário a gerenciar lembretes e follow-ups no chat principal.

Regras rígidas:
1. Ações de AGENDA nunca devem ir em "actions"; agenda sempre vai em "buttons" para confirmação.
2. Ações de MEMÓRIA/CONHECIMENTO podem ir em "actions" e serão salvas automaticamente no grafo.
3. Ao criar lembrete, um clique no botão cria o lembrete instantaneamente — inclua title, description e due_at corretos.
4. Pedidos de lembrete/agenda NÃO devem usar save_memory — use create_schedule/update_schedule. Use save_memory apenas para conhecimento relevante que deva permanecer.
5. Para editar/concluir/adiar lembretes existentes, use o schedule_id da agenda abaixo.
6. Use datas ISO 8601 (ex: 2026-06-21T10:00:00). Fuso: Brasil (UTC-3).
7. Botões com labels curtos e claros (ex: "Criar lembrete — 2 min").
8. ANTES de criar lembrete, verifique AGENDA ATUAL. Se já existir lembrete com título igual ou muito parecido, AVISE o usuário no texto e ofereça DOIS botões: um para atualizar o existente (`update_schedule` com schedule_id) e outro para criar novo (`create_schedule`).
   Se NÃO existir lembrete relacionado na AGENDA ATUAL, NUNCA ofereça `update_schedule`; ofereça apenas criar novo.
9. Se o usuário disser "hoje", use O DIA ATUAL informado abaixo, não o dia do lembrete existente.
10. Se o usuário disser "o café/encontro/reunião com X vai ser hoje às 18h", isso normalmente significa ATUALIZAR o lembrete existente relacionado, não criar outro.
11. Se o usuário revelar pessoas importantes, apelidos, preferências ou relações pessoais na mesma mensagem, mencione que isso é importante para a Persona. O sistema também salvará esse detalhe automaticamente.
12. Se você, como IA, perceber que existe uma entidade subjetivamente importante mas insuficientemente conhecida (pessoa, empresa, lugar, grupo, projeto, relação social, etc.), NÃO use lista fixa, NÃO finja conhecer e NÃO salve só o nome.
13. Quando sua análise crítica concluir que falta contexto antes de agir, retorne `clarification` com uma pergunta humana e coloque a ação que seria feita em `pending_buttons`. Se havia pedido de agenda, `pending_buttons` é obrigatório. O app vai perguntar, salvar a resposta como Persona e só então continuar.
14. Evite perguntas fechadas que podem gerar respostas inúteis como "não". Prefira perguntas abertas: "quem é X para você?", "qual é o contexto de X?", "isso tem alguma prioridade especial para você?".
15. Depois de uma resposta de clarificação, avalie a qualidade da informação. Resposta vaga/negativa não deve virar memória; faça uma pergunta melhor. Se a resposta revelar outro contexto importante ainda desconhecido, investigue esse contexto antes de salvar.

## INTELIGÊNCIA DE MEMÓRIA / GRAFO
Você deve identificar informações relevantes para moldar uma inteligência pessoal do usuário.
Salve com `save_memory` em "actions" quando o conteúdo tiver valor futuro.

Categorias permitidas:
- `persona`: fatos sobre a pessoa, relações importantes, preferências, hábitos, dados pessoais, pessoas próximas.
- `event`: acontecimento relevante com tempo/contexto (ex: compromisso importante, reunião importante, prazo).
- `issue`: problema ou incidente que pode voltar a importar (ex: objeto que quebrou, pendência, bloqueio).
- `message`: mensagem recebida ou informação comunicada por alguém.
- `project`: trabalho, objetivo, tarefa grande, contexto profissional.
- `general`: informação útil que não cabe nas anteriores.

Critérios para salvar:
- Salve se a informação pode ajudar o usuário depois, explicar comportamento futuro, afetar agenda, decisões, prioridades ou contexto pessoal.
- Não salve conversa casual sem valor futuro.
- Para `persona`, só salve quando houver relação/fato claro explicado pelo usuário. Nome isolado não é Persona.
- Se estiver em dúvida se algo é Persona, pergunte. A dúvida deve ser decidida por raciocínio contextual, não por palavras pré-definidas.
- Não salve segredos sensíveis completos (senhas, tokens, documentos). Se necessário, salve só uma referência segura.
- Se a informação for uma agenda/lembrete, crie/atualize agenda nos buttons E salve em memória apenas se houver contexto extra relevante.

Formato JSON (no final da resposta, só quando usar ferramentas):

```json
{
  "actions": [
    {"type": "save_memory", "category": "persona", "subject": "Pessoa importante", "note": "Descrição objetiva do fato relevante"}
  ],
  "clarification": {
    "type": "persona_context",
    "subject": "nome/contexto que precisa ser entendido",
    "question": "Pergunta curta e natural para o usuário"
  },
  "pending_buttons": [
    {
      "label": "Criar lembrete depois da resposta",
      "confirm_action": {"type": "create_schedule", "title": "Título do lembrete", "description": "...", "due_at": "2026-06-20T16:16:00"}
    }
  ],
  "buttons": [
    {
      "label": "Atualizar lembrete existente",
      "confirm_action": {"type": "update_schedule", "schedule_id": 3, "title": "Título do lembrete", "description": "...", "due_at": "2026-06-20T16:16:00"}
    },
    {
      "label": "Criar lembrete novo",
      "confirm_action": {"type": "create_schedule", "title": "Título do lembrete", "description": "...", "due_at": "2026-06-20T16:16:00"}
    }
  ]
}
```

Skills em confirm_action (chat):
- `create_schedule` — title, description (opcional), due_at
- `update_schedule` — schedule_id, title, description (opcional), due_at
- `mark_done` — schedule_id
- `delete_schedule` — schedule_id
- `postpone` — schedule_id, minutes
- `reschedule` — schedule_id, due_at
- `save_memory` — subject, note

Skill permitida em actions:
- `save_memory` — category, subject, note, relevance_score opcional (1-100)
'''

_ACTION_TYPE_ALIASES = {
    'edit_schedule': 'update_schedule',
    'edit_agenda': 'update_schedule',
    'edit_reminder': 'update_schedule',
    'modify_schedule': 'update_schedule',
    'update_reminder': 'update_schedule',
    'change_schedule': 'update_schedule',
    'update': 'update_schedule',
}

_EXISTING_SCHEDULE_OPS = frozenset({
    'reschedule', 'update_schedule', 'postpone', 'mark_done', 'delete_schedule',
})


def normalize_action_type(action: dict) -> dict:
    """Normaliza tipo e campos comuns vindos da IA."""
    if not isinstance(action, dict):
        return action
    fixed = dict(action)
    atype = (fixed.get('type') or '').strip()
    if atype in _ACTION_TYPE_ALIASES:
        fixed['type'] = _ACTION_TYPE_ALIASES[atype]
    if 'content' in fixed and 'description' not in fixed:
        fixed['description'] = fixed.pop('content')
    if 'text' in fixed and 'description' not in fixed:
        fixed['description'] = fixed.pop('text')
    if 'body' in fixed and 'description' not in fixed:
        fixed['description'] = fixed.pop('body')
    if 'new_title' in fixed and 'title' not in fixed:
        fixed['title'] = fixed.pop('new_title')
    return fixed


def normalize_action(action: dict, user_text: str = '') -> dict:
    return normalize_action_dates(normalize_action_type(action), user_text)


def resolve_schedule_id(action: dict, user_text: str = '', item: dict | None = None) -> int | None:
    """Resolve qual lembrete a ação afeta (popup, schedule_id ou match por contexto)."""
    if item:
        sid = item.get('id')
        if sid is not None:
            return int(sid)
    sid = action.get('schedule_id')
    if sid is not None:
        try:
            sid = int(sid)
        except (TypeError, ValueError):
            sid = None
        if sid is not None and _schedule_exists(sid):
            return sid
    from core.scheduler import ScheduleManager
    all_scheds = ScheduleManager.get_instance().get_all()
    if not all_scheds:
        return None
    atype = normalize_action_type(action).get('type')
    # Em update_schedule o title costuma ser o NOVO título — não use para achar o lembrete.
    if atype != 'update_schedule':
        title = (action.get('title') or '').strip()
        if title:
            matches = find_similar_schedules(title, threshold=0.5)
            if matches:
                return int(matches[0]['id'])
    if user_text:
        best_id = None
        best_score = 0.0
        for s in all_scheds:
            score = max(
                _title_similarity(user_text, s.get('title', '')),
                _title_similarity(user_text, s.get('description', '') or ''),
            )
            if score > best_score:
                best_score = score
                best_id = s['id']
        if best_score >= 0.3 and best_id is not None:
            return int(best_id)
    if len(all_scheds) == 1:
        return int(all_scheds[0]['id'])
    return None

_NOTIFICATION_SKILLS_DOC = '''
Você é o SEQ, assistente pessoal que gerencia a agenda do usuário neste popup de lembrete vencido.

## REGRAS DO POPUP
1. O usuário está falando DIRETAMENTE sobre o lembrete em foco — quando ele pedir remarcar, adiar, concluir ou cancelar, coloque a ação no array "actions" para execução imediata (ele já confirmou ao digitar).
2. Use "buttons" só quando houver ambiguidade ou múltiplas opções (máx. 3).
3. Seja CONTEXTUAL: ações devem corresponder EXATAMENTE ao pedido.
4. Na resposta em texto, confirme o que foi feito de forma curta (1 linha).
5. Você tem VISÃO TOTAL da agenda — evite conflitos de horário.
6. `save_memory` só para fatos pessoais duradouros, nunca para o lembrete em si.

Exemplo — usuário pede remarcação:
```json
{
  "actions": [
    {"type": "reschedule", "due_at": "2026-06-23T12:00:00"}
  ],
  "buttons": []
}
```

Exemplo — usuário pede editar título/descrição do lembrete em foco:
```json
{
  "actions": [
    {"type": "update_schedule", "title": "Novo título", "description": "Nova descrição"}
  ],
  "buttons": []
}
```

Skills em actions ou confirm_action:
- `{"type": "mark_done"}`
- `{"type": "delete_current"}`
- `{"type": "postpone", "minutes": 30}`
- `{"type": "reschedule", "due_at": "2026-06-21T10:00:00"}`
- `{"type": "update_schedule", "title": "...", "description": "..."}`
- `{"type": "create_schedule", "title": "...", "description": "...", "due_at": "2026-06-21T10:00:00"}`
- `{"type": "save_memory", "subject": "...", "note": "..."}`
- `{"type": "open_chat"}`
'''

def visible_text(buf: str) -> str:
    txt = buf
    match = re.search(r'```json[\s\S]*?```', txt)
    if match:
        txt = txt[:match.start()] + txt[match.end():]
    else:
        idx = txt.find('```json')
        if idx != -1:
            txt = txt[:idx]
    match_json = re.search(r'\{[\s\S]{0,100}?"(?:actions|buttons)"', txt)
    if match_json:
        txt = txt[:match_json.start()]
    return txt.strip()

def parse_skills_json(text: str) -> dict | None:
    data = None
    match = re.search(r'```json\s*(\{[\s\S]*?\})\s*```', text)
    if match:
        try:
            data = json.loads(match.group(1))
        except Exception:
            pass
    if data:
        return data
    start = text.find('{')
    if start != -1 and ('"actions"' in text or '"buttons"' in text):
        depth = 0
        end = start
        for idx in range(start, len(text)):
            if text[idx] == '{':
                depth += 1
            elif text[idx] == '}':
                depth -= 1
            if depth == 0:
                end = idx + 1
                break
        try:
            data = json.loads(text[start:end])
        except Exception:
            pass
    return data

def _agenda_context_block() -> str:
    from core.scheduler import ScheduleManager
    all_scheds = ScheduleManager.get_instance().get_all()
    if not all_scheds:
        return '\n## AGENDA ATUAL: Nenhum lembrete pendente.\n'
    lines = '\n## AGENDA ATUAL (lembretes pendentes):\n'
    for s in all_scheds:
        desc = s.get('description') or ''
        extra = f' | {desc[:60]}' if desc else ''
        lines += f"- ID {s['id']}: {s['title']} — {s['due_at']}{extra}\n"
    return lines

def build_chat_agenda_prompt(now: str) -> str:
    return _CHAT_SKILLS_DOC + _agenda_context_block() + f'\n- Data/hora atual: {now}\n'

def build_notification_system_prompt(item: dict) -> str:
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    title = item.get('title', 'Lembrete')
    desc = item.get('description', '')
    due = item.get('due_at', '')
    sid = item.get('id', '')
    doc = _NOTIFICATION_SKILLS_DOC
    context = (
        f'\n## LEMBRETE ATUAL (EM FOCO)\n- ID: {sid}\n- Título: {title}\n- Descrição: {desc or "(nenhuma)"}\n- Horário: {due}\n'
    )
    return doc + _agenda_context_block() + context + f'\n- Data/hora atual: {now}\n- Fuso horário: Brasil (UTC-3)\n'

def _normalize_title(text: str) -> str:
    text = text.lower().strip()
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r'[^\w\s]', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()

def _title_similarity(a: str, b: str) -> float:
    na, nb = _normalize_title(a), _normalize_title(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return 0.9
    wa, wb = set(na.split()), set(nb.split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / max(len(wa), len(wb))

def find_similar_schedules(title: str, threshold: float = 0.55) -> list[dict]:
    from core.scheduler import ScheduleManager
    matches = []
    for s in ScheduleManager.get_instance().get_all():
        score = _title_similarity(title, s.get('title', ''))
        if score >= threshold:
            matches.append({**s, '_similarity': score})
    matches.sort(key=lambda x: (-x['_similarity'], x.get('due_at', '')))
    return matches

def _schedule_exists(schedule_id: str) -> bool:
    if schedule_id is None:
        return False
    try:
        sid = int(schedule_id)
    except Exception:
        return False
    from core.scheduler import ScheduleManager
    return any(int(s.get('id')) == sid for s in ScheduleManager.get_instance().get_all())

def _action_references_existing_schedule(action: dict, user_text: str = '', item: dict | None = None) -> bool:
    action = normalize_action_type(action)
    atype = action.get('type')
    if atype in _EXISTING_SCHEDULE_OPS:
        return resolve_schedule_id(action, user_text, item) is not None
    return _schedule_exists(action.get('schedule_id'))

def _sanitize_button_action(action: list | dict, user_text: str = '', item: dict | None = None) -> list | dict | None:
    if isinstance(action, list):
        clean = []
        for item_action in action:
            if isinstance(item_action, dict):
                item_action = normalize_action(item_action, user_text)
                if _action_references_existing_schedule(item_action, user_text, item):
                    clean.append(item_action)
        return clean or None
    if isinstance(action, dict):
        action = normalize_action(action, user_text)
        if _action_references_existing_schedule(action, user_text, item):
            return action
    return None

def _format_due_short(due_str: str) -> str:
    try:
        return datetime.fromisoformat(due_str).strftime('%d/%m %H:%M')
    except Exception:
        return due_str or '?'

def _parse_time_from_text(user_text: str) -> tuple[int, int] | None:
    low = user_text.lower()
    match = re.search(r'(?:às|as|para as|para às)\s*(\d{1,2})(?::|h)?(\d{2})?', low)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return hour, minute
    return None

def _normalize_due_at_for_text(due_at: str, user_text: str) -> str:
    if not due_at:
        return due_at
    low = user_text.lower()
    now = datetime.now()
    try:
        dt = datetime.fromisoformat(due_at)
    except Exception:
        return due_at
    rel = re.search(r'daqui\s+(\d+)\s*(minuto|minutos|min|hora|horas|h)\b', low)
    if rel:
        amount = int(rel.group(1))
        unit = rel.group(2)
        if unit.startswith('hora') or unit == 'h':
            return (now + timedelta(hours=amount)).isoformat()
        return (now + timedelta(minutes=amount)).isoformat()
    explicit_time = _parse_time_from_text(user_text)
    if 'hoje' in low or 'dia de hoje' in low:
        hour, minute = explicit_time or (dt.hour, dt.minute)
        return dt.replace(year=now.year, month=now.month, day=now.day, hour=hour, minute=minute).isoformat()
    if 'amanhã' in low or 'amanha' in low:
        target = now + timedelta(days=1)
        hour, minute = explicit_time or (dt.hour, dt.minute)
        return dt.replace(year=target.year, month=target.month, day=target.day, hour=hour, minute=minute).isoformat()
    today_hint = re.search(r'hoje\s+(?:é|e)\s+dia\s+(\d{1,2})', low)
    if today_hint:
        day = int(today_hint.group(1))
        if day == now.day:
            hour, minute = explicit_time or (dt.hour, dt.minute)
            return dt.replace(year=now.year, month=now.month, day=now.day, hour=hour, minute=minute).isoformat()
    return due_at

def normalize_action_dates(action: dict, user_text: str) -> dict:
    if not isinstance(action, dict):
        return action
    atype = action.get('type')
    if atype not in {'update_schedule', 'create_schedule', 'reschedule'}:
        return action
    if 'due_at' not in action:
        return action
    fixed = dict(action)
    fixed['due_at'] = _normalize_due_at_for_text(str(action.get('due_at', '')), user_text)
    return fixed

def expand_chat_buttons(buttons: list[dict], user_text: str = '') -> list[dict]:
    expanded = []
    for btn in buttons:
        action = btn.get('confirm_action')
        if not action and 'action' in btn:
            action = {'type': btn['action']}
        if isinstance(action, list) or (action and action.get('type') != 'create_schedule'):
            clean_action = _sanitize_button_action(action, user_text)
            if clean_action:
                expanded.append({**btn, 'confirm_action': clean_action})
            continue
        action = normalize_action(action, user_text)
        title = action.get('title', '')
        similar = find_similar_schedules(title)
        if not similar:
            expanded.append({**btn, 'confirm_action': action})
            continue
        best = similar[0]
        new_due = _format_due_short(action.get('due_at', ''))
        old_due = _format_due_short(best.get('due_at', ''))
        expanded.append({
            'label': f'Atualizar existente ({old_due} → {new_due})',
            'confirm_action': {
                'type': 'update_schedule',
                'schedule_id': best['id'],
                'title': action.get('title', best['title']),
                'description': action.get('description') or best.get('description', ''),
                'due_at': action.get('due_at', '')
            }
        })
        expanded.append({
            'label': 'Criar lembrete novo',
            'confirm_action': action
        })
    return expanded[:3]

def augment_ai_text_for_duplicates(text: str) -> str:
    data = parse_skills_json(text)
    if not data:
        return text
    hints = []
    for btn in data.get('buttons', []):
        action = btn.get('confirm_action') or {}
        if action.get('type') != 'create_schedule':
            continue
        similar = find_similar_schedules(action.get('title', ''))
        if not similar:
            continue
        best = similar[0]
        old_due = _format_due_short(best.get('due_at', ''))
        hints.append(f'Já existe um lembrete parecido: "{best["title"]}" ({old_due}). Escolha abaixo se quer atualizar o existente ou criar um novo.')
    if not hints:
        return text
    visible = visible_text(text)
    hint = hints[0]
    if hint in visible or 'lembrete parecido' in visible.lower() or 'já existe' in visible.lower():
        return text
    return f'{visible}\n\n{hint}' + (text[len(visible):] if len(text) > len(visible) else '')

def commit_schedule(title: str, description: str, due_at: datetime, source: str) -> int:
    from core.scheduler import ScheduleManager
    from core.database import SeqDB
    if due_at is None:
        due_at = datetime.now() + timedelta(hours=1)
    sid = ScheduleManager.get_instance().add(title=title, description=description, due_at=due_at, source=source)
    preview = f'Agendado para {due_at.strftime("%d/%m/%Y %H:%M")}'
    if description:
        preview = f'{description} — {preview}'
    SeqDB.get_instance().save_item(
        subject=f'Agenda: {title}',
        body_preview=preview,
        source='manual',
        is_important=True
    )
    trigger_ui_update()
    QTimer.singleShot(1000, trigger_ui_update)
    return sid

def trigger_ui_update():
    for w in QApplication.topLevelWidgets():
        brain = getattr(w, '_brain', None)
        if brain and hasattr(brain, 'agenda_tab'):
            brain.agenda_tab.refresh()
        if brain and hasattr(brain, 'graph_tab'):
            brain.graph_tab.refresh()
        settings = getattr(w, '_settings', None)
        if settings and hasattr(settings, 'memory_tab_widget'):
            settings.memory_tab_widget.refresh()
        if hasattr(w, 'memory_tab_widget'):
            w.memory_tab_widget.refresh()
        checker = getattr(w, '_schedule_checker', None)
        if checker:
            checker.force_check()

def _schedule_dialog_close(dialog, delay_ms: int = 1500):
    if dialog and hasattr(dialog, '_close'):
        QTimer.singleShot(delay_ms, dialog._close)

def _maybe_close_after(dialog, action: dict, result: str, delay_ms: int = 1500):
    if action.get('type') in _CLOSING_ACTIONS and not result.startswith('❌'):
        _schedule_dialog_close(dialog, delay_ms)

class AgendaSkillExecutor:
    """Executa skills de agenda. Modo chat (sem item) ou notificação (com item)."""

    def __init__(self, item: dict | None = None, dialog=None):
        self._item = item
        self._dialog = dialog
        self._user_text = ''

    def execute(self, action: dict, user_text: str = '') -> str:
        if user_text:
            self._user_text = user_text
        action = normalize_action(action, self._user_text)
        atype = action.get('type', '')
        try:
            if atype == 'mark_done':
                return self._mark_done(action)
            if atype in ('delete_current', 'delete_schedule'):
                return self._delete(action)
            if atype == 'postpone':
                return self._postpone(action)
            if atype == 'reschedule':
                return self._reschedule(action)
            if atype == 'create_schedule':
                return self._create_schedule(action)
            if atype == 'update_schedule':
                return self._update_schedule(action)
            if atype == 'save_memory':
                return self._save_memory(action)
            if atype == 'open_chat':
                return self._open_chat()
            return f'Skill desconhecida: {atype}'
        except Exception as e:
            return f"❌ Erro ao executar '{atype}': {e}"

    def _schedule_id(self, action: dict) -> int | None:
        return resolve_schedule_id(action, self._user_text, self._item)

    def _mark_done(self, action: dict) -> str:
        from core.scheduler import ScheduleManager
        sid = self._schedule_id(action)
        if sid is None:
            return '❌ Informe o schedule_id do lembrete.'
        ScheduleManager.get_instance().mark_done(sid)
        trigger_ui_update()
        result = '✅ Lembrete marcado como concluído.'
        _maybe_close_after(self._dialog, action, result)
        return result

    def _delete(self, action: dict) -> str:
        from core.scheduler import ScheduleManager
        sid = self._schedule_id(action)
        if sid is None:
            return '❌ Informe o schedule_id do lembrete.'
        ScheduleManager.get_instance().delete(sid)
        trigger_ui_update()
        result = 'Lembrete cancelado.'
        _maybe_close_after(self._dialog, action, result)
        return result

    def _postpone(self, action: dict) -> str:
        from core.scheduler import ScheduleManager
        sid = self._schedule_id(action)
        if sid is None:
            return '❌ Informe o schedule_id do lembrete.'
        minutes = int(action.get('minutes', 30))
        ScheduleManager.get_instance().postpone(sid, minutes)
        if minutes < 60:
            label = f'{minutes} min'
        elif minutes < 1440:
            label = f'{minutes // 60}h'
        else:
            label = f'{minutes // 1440}d'
        trigger_ui_update()
        result = f'⏳ Adiado por {label}.'
        _maybe_close_after(self._dialog, action, result)
        return result

    def _reschedule(self, action: dict) -> str:
        from core.scheduler import ScheduleManager, parse_due_at, format_due_at
        sid = self._schedule_id(action)
        due_str = action.get('due_at', '')
        try:
            new_dt = parse_due_at(due_str)
        except Exception:
            return f'❌ Data inválida: {due_str}'
        if sid is None:
            return '❌ Informe o schedule_id do lembrete.'
        mgr = ScheduleManager.get_instance()
        mgr.update(sid, due_at=new_dt)
        trigger_ui_update()
        formatted = new_dt.strftime('%d/%m às %H:%M')
        result = f'Remarcado para {formatted}.'
        _maybe_close_after(self._dialog, action, result)
        return result

    def _create_schedule(self, action: dict) -> str:
        from core.scheduler import parse_due_at
        title = action.get('title', 'Novo lembrete')
        desc = action.get('description', '')
        due_str = action.get('due_at', '')
        try:
            if due_str:
                due_dt = parse_due_at(due_str)
            else:
                due_dt = datetime.now() + timedelta(hours=1)
        except Exception:
            due_dt = datetime.now() + timedelta(hours=1)
        commit_schedule(title=title, description=desc, due_at=due_dt, source='ai')
        formatted = due_dt.strftime('%d/%m às %H:%M')
        return f'✅ Lembrete criado: "{title}" — {formatted}'

    def _update_schedule(self, action: dict) -> str:
        from core.scheduler import ScheduleManager, parse_due_at
        sid = self._schedule_id(action)
        if sid is None:
            return '❌ Não achei qual lembrete atualizar. Informe o schedule_id ou seja mais específico.'
        mgr = ScheduleManager.get_instance()
        existing = next((s for s in mgr.get_all() if int(s['id']) == int(sid)), None)
        if not existing:
            return f'❌ Lembrete #{sid} não encontrado.'
        title = action.get('title') if 'title' in action else None
        desc = action.get('description') if 'description' in action else None
        due_str = action.get('due_at', '')
        due_dt = None
        if due_str:
            try:
                due_dt = parse_due_at(due_str)
            except Exception:
                return f'❌ Data inválida: {due_str}'
        if title is None and desc is None and due_dt is None:
            return '❌ Nada para atualizar — informe título, descrição ou horário.'
        mgr.update(sid, title=title, description=desc, due_at=due_dt)
        trigger_ui_update()
        display_title = title if title is not None else existing.get('title', 'lembrete')
        if due_dt:
            formatted = due_dt.strftime('%d/%m às %H:%M')
            return f'✅ Lembrete atualizado: "{display_title}" — {formatted}'
        parts = []
        if title is not None:
            parts.append('título')
        if desc is not None:
            parts.append('descrição')
        if due_dt is not None:
            parts.append('horário')
        return f'✅ Lembrete atualizado ({", ".join(parts)}): "{display_title}".'

    def _save_memory(self, action: dict) -> str:
        from core.database import SeqDB
        subject = action.get('subject') or (self._item.get('title') if self._item else 'Nota')
        note = action.get('note', '')
        category = action.get('category') or 'general'
        category = category.strip().lower()
        source = 'persona' if category == 'persona' else 'manual'
        try:
            relevance = int(action.get('relevance_score', 80 if category == 'persona' else 65))
        except Exception:
            relevance = 80 if category == 'persona' else 65
        SeqDB.get_instance().save_important({
            'id': str(uuid.uuid4()),
            'source': source,
            'subject': subject,
            'sender': '',
            'body_preview': note,
            'ai_summary': subject,
            'ai_reason': f'Memória relevante capturada pelo SEQ ({category})',
            'relevance_score': max(1, min(100, relevance)),
        }, saved_by='user')
        trigger_ui_update()
        if source == 'persona':
            return f'Persona atualizada: "{subject}".'
        return f'Memória salva: "{subject}".'

    def _open_chat(self) -> str:
        for w in QApplication.topLevelWidgets():
            if hasattr(w, '_expand'):
                w._expand()
                break
        return 'Chat aberto.'
