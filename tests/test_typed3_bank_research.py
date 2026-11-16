"""typed-v3 item bank research (bank/research.py): the fixed loop with a fake web and a fake researcher; the screen
that drops hits and pages naming a benchmark; verbatim findings; the brief keeps only cited entries. No network."""
import json
import shutil
import tempfile
from pathlib import Path

import pytest

from skillopt.execskill.typed import units
from skillopt.execskill.typed.bank import env as bank_env, prompts, research

PAGES = {
    'arxiv:2101.00001': {'id': 'arxiv:2101.00001', 'title': 'Numerical reasoning over financial tables', 'url': 'https://arxiv.org/html/2101.00001',
                         'text': 'We study errors.\nModels often select the wrong row or the wrong year column when tables are long.\n'
                                 'Scale words such as millions are frequently ignored.'},
    'arxiv:2101.00002': {'id': 'arxiv:2101.00002', 'title': 'A study on SearchQA retrieval', 'url': 'u', 'text': 'About SearchQA.'},
    'arxiv:2101.00003': {'id': 'arxiv:2101.00003', 'title': 'Generic paper', 'url': 'u3',
                         'text': 'This page compares with the OfficeQA benchmark in its related work.'},
}


class FakeWeb:
    def __init__(self):
        self.searches, self.reads = [], []

    def search(self, source, query):
        self.searches.append((source, query))
        if source == 'wikipedia':
            raise research.FetchError('http_503')
        return [{'id': ref, 'title': page['title'], 'snippet': ''} for ref, page in PAGES.items()]

    def page(self, ref):
        self.reads.append(ref)
        return dict(PAGES[ref])


class Fake:
    max_tokens = 2048

    def __init__(self, answer):
        self.answer, self.calls = answer, []

    def call(self, system, user):
        self.calls.append((system, user))
        return {'ok': True, 'response': self.answer(system, json.loads(user)), 'finish_reason': 'stop', 'error_type': None,
                'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}}


@pytest.fixture
def root():
    base = Path('/tmp/typed3-neutral')
    base.mkdir(exist_ok=True)
    made = Path(tempfile.mkdtemp(prefix='research-', dir=base))
    yield made
    shutil.rmtree(made, ignore_errors=True)


def researcher(system, payload):
    assert 'UID' not in json.dumps(payload)                                    # never an item of a benchmark
    if system == prompts.RESEARCH_PLAN:
        return json.dumps({'queries': [{'source': 'arxiv', 'query': 'table numerical reasoning errors'},
                                       {'source': 'wikipedia', 'query': 'Fiscal year'},
                                       {'source': 'arxiv', 'query': 'OfficeQA benchmark'},          # refused: names a benchmark
                                       {'source': 'google', 'query': 'anything'}]})                 # refused: no such source
    if system == prompts.RESEARCH_PICK:
        assert [hit['id'] for hit in payload['hits']] == ['arxiv:2101.00001', 'arxiv:2101.00003']   # the SearchQA title is screened
        return json.dumps({'read': ['arxiv:2101.00001', 'arxiv:2101.00003', 'arxiv:9999.99999']})
    if system == prompts.RESEARCH_CONCLUDE:
        assert [page['id'] for page in payload['pages']] == ['arxiv:2101.00001']                    # the page naming a benchmark is screened
        return json.dumps({'findings': [
            {'kind': 'mistake', 'statement': 'Solvers pick the wrong row or year column in long tables.',
             'quote': 'Models often select the wrong row or the   wrong year column', 'source': 'arxiv:2101.00001'},
            {'kind': 'mistake', 'statement': 'Scale words are ignored by solvers in many cases.',
             'quote': 'Scale words such as millions are frequently ignored.', 'source': 'arxiv:2101.00001'},
            {'kind': 'mistake', 'statement': 'An invented claim that no page supports at all.',
             'quote': 'this sentence is not on the page', 'source': 'arxiv:2101.00001'}]})
    assert system == prompts.RESEARCH_BRIEF and [f['n'] for f in payload['findings']] == [1, 2]
    return json.dumps({'question_kinds': [{'name': 'lookup', 'description': 'no source', 'from': []}],
                       'mistakes': [{'label': 'wrong_period', 'description': 'the neighbouring year column is read', 'from': [1]},
                                    {'label': 'made_up_label', 'description': 'x', 'from': [1]},
                                    {'label': 'wrong_series', 'description': 'cites a finding that does not exist', 'from': [7]}],
                       'conventions': [{'text': 'amounts are stated in millions', 'from': [2]}]})


def test_research_loop_screens_verifies_and_briefs(root):
    web, role = FakeWeb(), Fake(researcher)
    env = bank_env.BankEnv(root, units.Ledger(root / 'ledger.json', 5_000_000), {'role': role}, width=1)
    question = {'id': 'mistakes', 'sources': ('arxiv', 'wikipedia'), 'text': 'Which mistakes do models make on tables?'}
    record = research.investigate(env, web, prompts, 'officeqa', prompts.FAMILY['officeqa'], question)
    row = record['rounds'][0]
    assert [q['source'] for q in row['queries']] == ['arxiv', 'wikipedia'] and len(record['rounds']) == 1
    assert row['screened_hits'] == 1 and row['screened_pages'] == 1 and row['void_findings'] == 1
    assert row['failed'] == ['search:wikipedia:http_503'] and web.reads == ['arxiv:2101.00001', 'arxiv:2101.00003']
    assert [f['statement'][:7] for f in record['findings']] == ['Solvers', 'Scale w'] and record['findings'][0]['url'].startswith('https://arxiv.org')
    archived = [units.read_json(p) for p in (root / 'research' / 'archive').glob('*.json')]
    assert sorted(a['kind'] for a in archived) == ['page', 'search']            # the screened page is never archived as read
    calls = len(role.calls)
    assert research.investigate(env, web, prompts, 'officeqa', prompts.FAMILY['officeqa'], question) == record and len(role.calls) == calls

    made = research.brief(env, prompts, 'officeqa', prompts.FAMILY['officeqa'], [record], prompts.MISTAKE_LABELS)
    assert made['brief']['question_kinds'] == [] and [m['label'] for m in made['brief']['mistakes']] == ['wrong_period']
    assert made['shown'] == {'question_kinds': [], 'mistakes': [{'label': 'wrong_period', 'description': 'the neighbouring year column is read'}],
                             'conventions': [{'text': 'amounts are stated in millions'}]}


def test_no_findings_no_brief(root):
    role = Fake(lambda system, payload: '{"queries": []}')
    env = bank_env.BankEnv(root, units.Ledger(root / 'ledger.json', 5_000_000), {'role': role}, width=1)
    question = {'id': 'kinds', 'sources': ('arxiv',), 'text': 'What kinds of questions?'}
    record = research.investigate(env, FakeWeb(), prompts, 'officeqa', 'family', question)
    assert record['findings'] == [] and len(record['rounds']) == research.ROUNDS
    assert research.brief(env, prompts, 'officeqa', 'family', [record], prompts.MISTAKE_LABELS)['reason'] == 'no_findings'


def test_a_failed_role_call_writes_no_research_record(root):
    # review 2026-11-13: a planning call that failed for an infrastructure reason became an empty, final record
    class Down(Fake):
        def call(self, system, user):
            self.calls.append((system, user))
            if self.answer is None:
                return {'ok': False, 'response': None, 'finish_reason': None, 'usage': {}, 'error_type': 'transport'}
            return super().call(system, user)
    role = Down(None)
    env = bank_env.BankEnv(root, units.Ledger(root / 'ledger.json', 5_000_000), {'role': role}, width=1)
    question = {'id': 'mistakes', 'sources': ('arxiv', 'wikipedia'), 'text': 'Which mistakes do models make on tables?'}
    with pytest.raises(RuntimeError) as failed:
        research.investigate(env, FakeWeb(), prompts, 'officeqa', prompts.FAMILY['officeqa'], question)
    assert str(failed.value).startswith('infrastructure:') and not (root / 'research' / 'officeqa' / 'mistakes.json').exists()
    role.answer, role.calls = researcher, []                                 # the next run sends it and finishes
    record = research.investigate(env, FakeWeb(), prompts, 'officeqa', prompts.FAMILY['officeqa'], question)
    assert len(record['findings']) == 2 and (root / 'research' / 'officeqa' / 'mistakes.json').exists()
    role.answer = None
    with pytest.raises(RuntimeError):
        research.brief(env, prompts, 'officeqa', prompts.FAMILY['officeqa'], [record], prompts.MISTAKE_LABELS)
    assert not (root / 'research' / 'officeqa' / 'brief.json').exists()


def test_excerpt_and_plain_text():
    body = '\n'.join(['opening line'] + ['filler %d' % i for i in range(3000)] + ['the wrong column is a common mistake'] + ['tail'] * 50)
    shown = research.excerpt(body, ['mistake', 'column'], limit=2000)
    assert shown.startswith('opening line') and 'the wrong column is a common mistake' in shown and '[...]' in shown and len(shown) <= 2100
    assert research.plain('<div><p>A&nbsp;&amp; B</p><ul><li>one</li><li>two</li></ul></div>') == 'A & B\none\ntwo'


def test_web_parses_the_three_sources():
    class Response:
        def __init__(self, text, status=200):
            self.text, self.status_code = text, status

        def json(self):
            return json.loads(self.text)
    atom = ('<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/2105.07624v2</id><title>A  title</title>'
            '<summary>An abstract.</summary></entry></feed>')

    class Http:
        def __init__(self):
            self.urls = []

        def get(self, url, params=None):
            self.urls.append((url, params))
            if url == research.ARXIV_API:
                return Response(atom)
            if url.startswith(research.ARXIV_HTML):
                return Response('', 404) if url.endswith('2105.07624') else Response('<h1>Paper</h1><p>Body text.</p>')
            if url.endswith('search/advanced'):
                return Response(json.dumps({'items': [{'question_id': 11, 'title': 'openpyxl &amp; formulas'}]}))
            if url.endswith('/answers'):
                return Response(json.dumps({'items': [{'body': '<p>Use data_only.</p>'}]}))
            return Response(json.dumps({'items': [{'title': 'openpyxl &amp; formulas', 'body': '<p>How?</p>'}]}))

    class Wiki:
        def search(self, query):
            return ['Fiscal year']

        def page(self, title):
            return {'title': title, 'revid': 5, 'redirects': [], 'html': '<p>The fiscal year</p>', 'disambiguation': False}
    http = Http()
    web = research.Web(http, Wiki(), lambda html: (research.plain(html), []))
    assert web.search('arxiv', 'What is table question answering?') == [{'id': 'arxiv:2105.07624', 'title': 'A title', 'snippet': 'An abstract.'}]
    assert http.urls[0][1]['search_query'] == 'all:table AND all:question AND all:answering'
    assert web.page('arxiv:2105.07624')['text'] == 'A title\nAn abstract.'                       # no HTML edition: the abstract
    assert web.page('arxiv:2401.00001')['text'] == 'Paper\nBody text.'
    hits = web.search('stackexchange', 'openpyxl formula')
    assert hits[0] == {'id': 'stackexchange:stackoverflow:11', 'title': 'openpyxl & formulas', 'snippet': ''}
    assert 'Use data_only.' in web.page('stackexchange:stackoverflow:11')['text']
    assert web.search('wikipedia', 'fiscal year')[0]['id'] == 'wikipedia:Fiscal year'
    assert web.page('wikipedia:Fiscal year')['text'] == 'The fiscal year'
    with pytest.raises(research.FetchError):
        web.page('ftp:whatever')
