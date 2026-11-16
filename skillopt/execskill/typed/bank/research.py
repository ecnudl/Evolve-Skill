"""Research before item writing (BANK-PILOT B8; owner 2026-11-13: "在造题之前可以通过deep search去深度搜索应该造怎么样的题").

A researcher role answers a fixed list of research questions per bench (what kinds of questions the task family
holds, what makes them hard, which mistakes solvers make, the domain's conventions, what makes a written question
valid) and the findings are folded into one BRIEF that steers the question writer and names the mistakes the code
rubric should carry. The process is a fixed loop, not a free agent:

    plan      the researcher gives at most MAX_QUERIES search queries, each for one source;
    search    fixed code runs them, archives every result list, screens the hits;
    pick      the researcher picks at most MAX_PAGES hits to read;
    read      fixed code fetches and archives every page, screens it, and shows an excerpt;
    conclude  the researcher gives findings, each with a VERBATIM quote of a page it was shown;
    verify    fixed code keeps a finding only when its quote is in the archived text of the page it names.

One more round runs when fewer than MIN_FINDINGS findings were kept. After all questions one synthesis request
turns the kept findings into the brief; a brief entry counts only when it cites kept findings.

Sources (keyless, reached through the one explicit credential-free gateway; the environment's proxy settings are
never read): the English Wikipedia API (the frozen client of ``skillopt.execskill.research``), the arXiv API with
the paper's HTML full text when arXiv serves one, and the Stack Exchange API. Nothing else is fetched.

Integrity rules:
- the researcher never sees a benchmark item: its requests hold the fixed research question and a generic
  description of the task family, nothing from a pool;
- SCREEN: a search hit or a page that names one of the five benchmarks (or SearchQA's source show) is dropped by
  fixed code before any role sees it. The benchmarks' own papers and dataset pages may quote test items, so they are
  never read; this needs no test-side data. Dropped hits and pages are counted;
- every result list and page body is archived write-once (``<root>/research/archive/<sha256>.json``) before use, so
  a brief can be traced to the bytes it rests on.
"""
from __future__ import annotations

import html as html_module
import json
import re
import xml.etree.ElementTree as ElementTree

from .. import units
from .env import read_object, text_sha256

SOURCES = ('wikipedia', 'arxiv', 'stackexchange')
SCREEN = re.compile(r'office[\s_-]?qa|spreadsheet[\s_-]?bench|search[\s_-]?qa|zebra[\s_-]?logic|alf[\s_-]?world'
                    r'|\balfred\b|jeopardy', re.I)
KINDS = ('question_kind', 'difficulty', 'mistake', 'convention', 'item_writing')
MAX_QUERIES, MAX_HITS, MAX_PAGES, MAX_FINDINGS, MIN_FINDINGS, ROUNDS = 4, 6, 3, 8, 2, 2
EXCERPT_CHARS, SNIPPET_CHARS, QUOTE_CHARS, STATEMENT_CHARS = 14_000, 300, 500, 400
USER_AGENT = 'skill-bank-research/1'
ARXIV_API = 'http://export.arxiv.org/api/query'
ARXIV_HTML = 'https://arxiv.org/html/'
STACK_API = 'https://api.stackexchange.com/2.3/'
STACK_SITES = ('stackoverflow', 'superuser')
HOSTS = ('export.arxiv.org', 'arxiv.org', 'api.stackexchange.com')
ATOM = '{http://www.w3.org/2005/Atom}'
TAG = re.compile(r'<[^>]+>')
WORD = re.compile(r'[a-z0-9]+')
STOP = frozenset('a an and are as at be by do does for from how in is it of on or that the their this to what '
                 'when which who why with'.split())


class FetchError(RuntimeError):
    """A source that failed or answered outside its interface: recorded as a failed search or fetch, never a stop."""


def squeeze(text):
    return ' '.join(text.split())


def plain(markup):
    """Text of an HTML fragment: tags dropped, entities read, blank runs squeezed per line."""
    text = html_module.unescape(TAG.sub(' ', re.sub(r'<(br|/p|/div|/li|/h\d|/tr)\s*/?>', '\n', markup, flags=re.I)))
    return '\n'.join(line for line in (squeeze(line) for line in text.split('\n')) if line)


def words_of(text):
    return [word for word in WORD.findall(text.lower()) if word not in STOP and len(word) > 2]


def excerpt(body, words, limit=EXCERPT_CHARS):
    """What a researcher is shown of a long page: its opening lines, then the lines richest in the words of the
    research question and the query, in page order, '[...]' where lines were left out."""
    if len(body) <= limit:
        return body
    lines = body.split('\n')
    chosen, size = set(), 0
    for index, line in enumerate(lines):
        if size + len(line) + 1 > limit // 4:
            break
        chosen.add(index)
        size += len(line) + 1
    for score, index in sorted((-sum(word in line.lower() for word in words), index) for index, line in enumerate(lines)):
        if score == 0:
            break
        if index not in chosen and size + len(lines[index]) + 6 <= limit:
            chosen.add(index)
            size += len(lines[index]) + 6
    if not chosen:
        return body[:limit] + '\n[...]'
    shown, last = [], -1
    for index in sorted(chosen):
        if index != last + 1:
            shown.append('[...]')
        shown.append(lines[index])
        last = index
    return '\n'.join(shown + (['[...]'] if last != len(lines) - 1 else []))


class Web:
    """The three sources behind one interface: ``search(source, query) -> [{id, title, snippet}]`` and
    ``page(id) -> {id, title, url, text}``. ``http``: an httpx-like client with ``get(url, params=)`` (explicit
    proxy, ``trust_env=False``); ``wikipedia``: the frozen Wikipedia client and its HTML reader."""

    def __init__(self, http, wikipedia, page_text):
        self.http, self.wikipedia, self.page_text = http, wikipedia, page_text

    def _get(self, url, params=None):
        try:
            response = self.http.get(url, params=params)
        except Exception as error:  # httpx.HTTPError and friends: a failed fetch, never a stop
            raise FetchError('transport:' + type(error).__name__) from None
        if response.status_code != 200:
            raise FetchError('http_%d' % response.status_code)
        host = getattr(getattr(response, 'url', None), 'host', None)
        if host is not None and host not in HOSTS:  # a redirect that left the three sources: not read
            raise FetchError('foreign_host')
        return response

    def search(self, source, query):
        if source == 'wikipedia':
            try:
                return [{'id': 'wikipedia:' + title, 'title': title, 'snippet': ''}
                        for title in self.wikipedia.search(query)[:MAX_HITS]]
            except Exception as error:
                raise FetchError('wikipedia:' + str(error)[:60]) from None
        if source == 'arxiv':
            terms = words_of(query)[:6]
            if not terms:
                return []
            body = self._get(ARXIV_API, {'search_query': ' AND '.join('all:' + term for term in terms), 'start': 0,
                                         'max_results': MAX_HITS, 'sortBy': 'relevance'}).text
            try:
                entries = ElementTree.fromstring(body).findall(ATOM + 'entry')
            except ElementTree.ParseError:
                raise FetchError('invalid_atom') from None
            hits = []
            for entry in entries:
                found = re.search(r'arxiv\.org/abs/([0-9]{4}\.[0-9]{4,5})', entry.findtext(ATOM + 'id') or '')
                if found:
                    hits.append({'id': 'arxiv:' + found.group(1), 'title': squeeze(entry.findtext(ATOM + 'title') or ''),
                                 'snippet': squeeze(entry.findtext(ATOM + 'summary') or '')[:SNIPPET_CHARS]})
            return hits
        if source == 'stackexchange':
            hits = []
            for site in STACK_SITES:
                try:
                    value = self._get(STACK_API + 'search/advanced', {'order': 'desc', 'sort': 'relevance', 'q': query,
                                                                      'site': site, 'pagesize': MAX_HITS // 2}).json()
                except ValueError:
                    raise FetchError('invalid_json') from None
                hits += [{'id': 'stackexchange:%s:%d' % (site, row['question_id']),
                          'title': html_module.unescape(str(row.get('title', ''))), 'snippet': ''}
                         for row in value.get('items', []) if type(row.get('question_id')) is int]
            return hits[:MAX_HITS]
        raise FetchError('unknown_source')

    def page(self, ref):
        source, _, rest = ref.partition(':')
        if source == 'wikipedia':
            try:
                page = self.wikipedia.page(rest)
            except Exception as error:
                raise FetchError('wikipedia:' + str(error)[:60]) from None
            if page['disambiguation']:
                raise FetchError('disambiguation')
            return {'id': 'wikipedia:' + page['title'], 'title': page['title'], 'revid': page['revid'],
                    'url': 'https://en.wikipedia.org/wiki/' + page['title'].replace(' ', '_'),
                    'text': self.page_text(page['html'])[0]}
        if source == 'arxiv' and re.fullmatch(r'[0-9]{4}\.[0-9]{4,5}', rest):
            try:
                text, url = plain(self._get(ARXIV_HTML + rest).text), ARXIV_HTML + rest
            except FetchError:  # no HTML edition of this paper: its abstract
                body = self._get(ARXIV_API, {'id_list': rest}).text
                entry = ElementTree.fromstring(body).find(ATOM + 'entry')
                if entry is None:
                    raise FetchError('no_entry') from None
                text = squeeze(entry.findtext(ATOM + 'title') or '') + '\n' + squeeze(entry.findtext(ATOM + 'summary') or '')
                url = 'https://arxiv.org/abs/' + rest
            return {'id': ref, 'title': text.split('\n')[0][:200], 'url': url, 'text': text}
        if source == 'stackexchange' and re.fullmatch(r'[a-z]+:[0-9]+', rest):
            site, number = rest.split(':')
            if site not in STACK_SITES:
                raise FetchError('unknown_site')
            try:
                question = self._get(STACK_API + 'questions/' + number, {'site': site, 'filter': 'withbody'}).json()
                answers = self._get(STACK_API + 'questions/%s/answers' % number,
                                    {'site': site, 'filter': 'withbody', 'order': 'desc', 'sort': 'votes',
                                     'pagesize': 3}).json()
            except ValueError:
                raise FetchError('invalid_json') from None
            rows = question.get('items') or []
            if not rows:
                raise FetchError('no_question')
            title = html_module.unescape(str(rows[0].get('title', '')))
            parts = [title, plain(str(rows[0].get('body', '')))]
            parts += ['Answer:\n' + plain(str(row.get('body', ''))) for row in answers.get('items') or []]
            return {'id': ref, 'title': title, 'url': 'https://%s.com/q/%s' % (site, number), 'text': '\n\n'.join(parts)}
        raise FetchError('unknown_reference')


# ---- the fixed loop --------------------------------------------------------------------------------------------------
def keep(env, kind, value):
    """Write-once archive of a result list or a page; returns its sha256 name."""
    name = text_sha256(json.dumps(value, ensure_ascii=False, sort_keys=True))
    path = env.path('research', 'archive', name + '.json')
    if not path.exists():
        units.write_json(path, {'kind': kind, 'value': value})
    return name


def _queries(reply, allowed):
    found = read_object(reply) or {}
    rows = found.get('queries') if isinstance(found.get('queries'), list) else []
    out = []
    for row in rows:
        if (isinstance(row, dict) and row.get('source') in allowed and isinstance(row.get('query'), str)
                and 3 <= len(row['query'].strip()) <= 200 and not SCREEN.search(row['query'])):
            out.append({'source': row['source'], 'query': squeeze(row['query'])})
    return out[:MAX_QUERIES]


def _picks(reply, offered):
    found = read_object(reply) or {}
    rows = found.get('read') if isinstance(found.get('read'), list) else []
    return [ref for ref in dict.fromkeys(rows) if ref in offered][:MAX_PAGES]


def _findings(reply, pages):
    """Findings whose quote is verbatim (whitespace aside) in the archived text of the page they name."""
    found = read_object(reply) or {}
    rows = found.get('findings') if isinstance(found.get('findings'), list) else []
    kept, void = [], 0
    for row in rows[:MAX_FINDINGS]:
        ok = (isinstance(row, dict) and row.get('kind') in KINDS and isinstance(row.get('statement'), str)
              and 10 <= len(row['statement'].strip()) <= STATEMENT_CHARS and isinstance(row.get('quote'), str)
              and 15 <= len(row['quote']) <= QUOTE_CHARS and row.get('source') in pages
              and squeeze(row['quote']) in squeeze(pages[row['source']]['text']))
        if ok:
            kept.append({'kind': row['kind'], 'statement': squeeze(row['statement']), 'quote': squeeze(row['quote']),
                         'source': row['source'], 'url': pages[row['source']]['url']})
        else:
            void += 1
    return kept, void


def _reply(sent):
    """The reply of a research role call. An infrastructure failure raises: the enclosing record is NOT written, so
    the stage can be run again (review 2026-11-13: a failed planning call used to become an empty, final record)."""
    if sent['reply'] is None and (sent['failure'] or '').startswith('infrastructure:'):
        raise RuntimeError('infrastructure: ' + str(sent['failure']))
    return sent['reply']


def investigate(env, web, prompts, bench, family, question):
    """The write-once record of one research question: its kept findings and what was searched, read, screened."""
    def compute():
        record = {'bench': bench, 'question': question['id'], 'rounds': [], 'findings': []}
        allowed = [source for source in question['sources'] if source in SOURCES]
        earlier = []
        for number in range(1, ROUNDS + 1):
            tag = '%s-%s-r%d' % (bench, question['id'], number)
            row = {'round': number, 'queries': [], 'hits': 0, 'screened_hits': 0, 'read': [], 'screened_pages': 0,
                   'failed': [], 'void_findings': 0}
            record['rounds'].append(row)
            sent = env.call('research', tag + '-plan', *prompts.research_plan(family, question['text'], allowed, earlier))
            row['queries'] = _queries(_reply(sent), allowed)
            offered = {}
            for query in row['queries']:
                try:
                    hits = web.search(query['source'], query['query'])
                except FetchError as failed:
                    row['failed'].append('search:%s:%s' % (query['source'], failed))
                    continue
                keep(env, 'search', {'query': query, 'hits': hits})
                for hit in hits:
                    if SCREEN.search(hit['title'] + ' ' + hit['snippet']):
                        row['screened_hits'] += 1
                    else:
                        offered.setdefault(hit['id'], hit)
            row['hits'] = len(offered)
            earlier += [query['query'] for query in row['queries']]
            if not offered:
                continue
            sent = env.call('research', tag + '-pick', *prompts.research_pick(family, question['text'], list(offered.values())))
            pages = {}
            for ref in _picks(_reply(sent), offered):
                try:
                    page = web.page(ref)
                except FetchError as failed:
                    row['failed'].append('page:%s:%s' % (ref, failed))
                    continue
                if SCREEN.search(page['title'] + '\n' + page['text']):
                    row['screened_pages'] += 1
                    continue
                page['archive'] = keep(env, 'page', page)
                pages[ref] = page
                row['read'].append({'id': ref, 'url': page['url'], 'chars': len(page['text']), 'archive': page['archive']})
            if not pages:
                continue
            words = words_of(question['text'] + ' ' + ' '.join(earlier))
            shown = [{'id': ref, 'title': page['title'], 'text': excerpt(page['text'], words)} for ref, page in pages.items()]
            sent = env.call('research', tag + '-conclude', *prompts.research_conclude(family, question['text'], shown))
            kept, row['void_findings'] = _findings(_reply(sent), pages)
            record['findings'] += kept
            if len(record['findings']) >= MIN_FINDINGS:
                break
        return record

    return env.once(('research', bench, question['id'] + '.json'), compute)


def brief(env, prompts, bench, family, records, labels):
    """The write-once brief of a bench: the synthesis of the kept findings. An entry is kept only when it cites
    findings that exist; a mistake's label must be a registered one."""
    def compute():
        findings = [finding for record in records for finding in record['findings']]
        numbered = [{'n': index, **{key: finding[key] for key in ('kind', 'statement', 'quote')}}
                    for index, finding in enumerate(findings, 1)]
        if not numbered:
            return {'bench': bench, 'findings': [], 'brief': None, 'reason': 'no_findings'}
        sent = env.call('research', bench + '-brief', *prompts.research_brief(family, numbered, labels))
        found = read_object(_reply(sent)) or {}
        cited = lambda row: (isinstance(row, dict) and isinstance(row.get('from'), list) and row['from']
                             and all(type(n) is int and 1 <= n <= len(numbered) for n in row['from']))
        text = lambda row, key, limit: squeeze(str(row.get(key) or ''))[:limit]
        kinds = [{'name': text(row, 'name', 60), 'description': text(row, 'description', 300), 'from': row['from']}
                 for row in found.get('question_kinds') or [] if cited(row) and text(row, 'name', 60)][:8]
        mistakes = [{'label': row['label'], 'description': text(row, 'description', 300), 'from': row['from']}
                    for row in found.get('mistakes') or [] if cited(row) and row.get('label') in labels][:8]
        conventions = [{'text': text(row, 'text', 300), 'from': row['from']}
                       for row in found.get('conventions') or [] if cited(row) and text(row, 'text', 300)][:8]
        value = {'question_kinds': kinds, 'mistakes': mistakes, 'conventions': conventions}
        shown = {key: [{k: v for k, v in row.items() if k != 'from'} for row in rows] for key, rows in value.items()}
        return {'bench': bench, 'findings': findings, 'brief': value if any(value.values()) else None,
                'shown': shown if any(value.values()) else None,      # what the question writer receives
                'reason': None if any(value.values()) else 'no_cited_entry'}

    return env.once(('research', bench, 'brief.json'), compute)
