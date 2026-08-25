"""
core/tools/web_tools.py — Pesquisa na web e leitura de páginas.

Sem chave de API: usa o DuckDuckGo (via `ddgs`, sem scraping frágil de HTML)
para buscar, e um extrator de texto próprio (stdlib `html.parser`, sem
dependência nova) para ler o conteúdo de uma página encontrada.

É o subagente que fecha o "wide research" — pesquisar algo e trazer a resposta
resumida, sem o usuário precisar abrir o navegador.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

import requests

from core.agent.registry import Tool, ToolResult, ok, fail
from core.llm.types import ToolSpec

_TIMEOUT = 12
_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/124.0 Safari/537.36 NigelAgent/1.0')
_MAX_FETCH_CHARS = 4000


class _TextExtractor(HTMLParser):
    """Extrai texto visível de HTML, sem depender de beautifulsoup4."""

    _SKIP_TAGS = {'script', 'style', 'noscript', 'template', 'svg', 'nav', 'footer'}
    _BLOCK_TAGS = {'p', 'div', 'br', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                   'tr', 'section', 'article', 'header'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
        elif tag in self._BLOCK_TAGS:
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0 and data.strip():
            self.parts.append(data.strip())

    def text(self) -> str:
        raw = ' '.join(self.parts)
        raw = re.sub(r'[ \t]+', ' ', raw)
        raw = re.sub(r'\n\s*\n+', '\n', raw)
        return raw.strip()


def _search(args, ctx) -> ToolResult:
    query = (args.get('query') or '').strip()
    if not query:
        return fail('BAD_ARGS', '`query` e obrigatorio')
    limit = min(int(args.get('max_results') or 5), 10)
    region = (args.get('region') or 'br-pt').strip()

    try:
        from ddgs import DDGS
    except ImportError:
        return fail('UNAVAILABLE', 'biblioteca de busca (ddgs) nao instalada')

    try:
        raw = list(DDGS().text(query, region=region, max_results=limit))
    except Exception as e:
        return fail('UPSTREAM', f'busca falhou: {type(e).__name__}: {e}')

    if not raw:
        # Tenta sem regiao — alguns termos tecnicos batem menos resultado localizado.
        try:
            raw = list(DDGS().text(query, max_results=limit))
        except Exception:
            raw = []

    results = [{'titulo': r.get('title', ''), 'url': r.get('href', ''),
               'resumo': (r.get('body') or '')[:300]}
              for r in raw if r.get('href')]
    if not results:
        return ok({'resultados': [], 'nota': 'nenhum resultado — tente outros termos'},
                  user_message='Nenhum resultado', icon='brand_web')
    return ok({'resultados': results, 'total': len(results)},
              user_message=f'{len(results)} resultado(s)', icon='brand_web')


def _fetch(args, ctx) -> ToolResult:
    url = (args.get('url') or '').strip()
    if not url:
        return fail('BAD_ARGS', '`url` e obrigatorio')
    if not re.match(r'^https?://', url):
        url = 'https://' + url

    try:
        resp = requests.get(url, headers={'User-Agent': _UA}, timeout=_TIMEOUT,
                            allow_redirects=True)
    except requests.exceptions.Timeout:
        return fail('TIMEOUT', f'a pagina nao respondeu em {_TIMEOUT}s')
    except requests.exceptions.RequestException as e:
        return fail('UPSTREAM', f'nao consegui abrir a pagina: {type(e).__name__}')

    if resp.status_code >= 400:
        return fail('UPSTREAM', f'a pagina respondeu HTTP {resp.status_code}')

    ctype = resp.headers.get('Content-Type', '')
    if 'text/html' not in ctype and 'application/xhtml' not in ctype:
        return fail('BAD_ARGS', f'conteudo nao e HTML (Content-Type: {ctype or "desconhecido"})')

    extractor = _TextExtractor()
    try:
        extractor.feed(resp.text)
    except Exception:
        pass
    texto = extractor.text()
    if not texto:
        return fail('UPSTREAM', 'nao consegui extrair texto legivel dessa pagina')

    truncado = len(texto) > _MAX_FETCH_CHARS
    if truncado:
        texto = texto[:_MAX_FETCH_CHARS] + '… [truncado]'
    return ok({'url': resp.url, 'texto': texto, 'truncado': truncado},
              user_message='Página lida', icon='brand_web')


def _obj(props, required=None):
    s = {'type': 'object', 'properties': props}
    if required:
        s['required'] = required
    return s


def build_tools() -> list[Tool]:
    return [
        Tool(ToolSpec('web_search',
             'Pesquisa na web (DuckDuckGo). Use para qualquer coisa que voce nao sabe e nao esta '
             'nem na agenda, nem no e-mail, nem na memoria do usuario — noticias, precos, '
             'documentacao, definicoes, o que for. Devolve titulo, url e um resumo curto de cada '
             'resultado; use web_fetch na url mais relevante se precisar do conteudo completo.',
             _obj({'query': {'type': 'string', 'description': 'o que pesquisar'},
                   'max_results': {'type': 'integer'},
                   'region': {'type': 'string',
                              'description': "codigo de regiao, ex. 'br-pt' (padrao) ou 'us-en'"}},
                  ['query']), parallel_safe=True),
             _search, label='Pesquisando na web', icon='brand_web'),

        Tool(ToolSpec('web_fetch',
             'Abre uma URL e devolve o texto visivel da pagina (ate ~4000 caracteres). '
             'Use depois de web_search para ler o conteudo real de um resultado promissor.',
             _obj({'url': {'type': 'string'}}, ['url']), parallel_safe=True),
             _fetch, label='Lendo página', icon='brand_web'),
    ]
