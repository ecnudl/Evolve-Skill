"""typed-v2 reply reader (DESIGN 3.3, decision D4): the one reader of program-writer replies, and the one format
retry per attempt of a programs unit.

The frozen route-B reader (``engineer_reader.read``) lost two of the four correct typed-v1 fix replies (F6): a
top-level ``change`` written for ``changes``, and a placeholder inline ``source`` beside a real fenced program. This
module reads with general tolerance (no patch for one field) and frozen PUBLIC helpers only (``MACHINERY_SYMBOLS``).
It is strict where it matters: it only parses (``ast.parse`` inside ``defined_hooks``, literal-only JSON inside
``tolerant_json``); it never executes, imports or compiles reply text and never replaces the static screen.
Tolerance decides WHICH text is screened, never WHETHER: every returned source goes unchanged to the screen and then
the sandbox smoke, and the text not chosen is recorded (length, sha256). Two different programs for one change are a
problem, never a guess. Reply content never makes a reader raise; ``ValueError`` only for caller mistakes.

    result  = {'records', 'problem', 'repairs', 'reply_sha256', 'reader'}
    record  = {'n', 'kind', 'entry', 'source', 'problem', 'repairs', 'read'}
    problem = {'code', 'detail', 'change'}          # change: the 1-based change number, None for the whole reply
    read    = {'source_from', 'is_program', 'hooks_defined', 'ignored', 'reply_sha256', 'reader'}
    outcome = {'result', 'request_sha256', 'format_retry'}      # read_with_retry

Repair rows keep the frozen row shape ``{'rule', 'path', ...}``; for a well-formed reply the records equal the
frozen reader's (entry, source and repair rows), which ``tests/test_typed_replies.py`` checks against the real frozen
reader. This module imports neither ``writers`` nor ``engineer_prompt``.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re

from skillopt.execskill import engineer, engineer_reader, profiles

from . import MACHINERY

# A change of any text below (or of the reading rules) comes with a new READER label and new PINS.
READER = 'typed-reply-reader-1'
FORMAT_RETRIES_PER_UNIT = 1
RETRY_PREVIOUS_REPLY_BYTES = 200_000
JSON_TAGS = ('json', 'jsonc', 'json5')
PYTHON_TAGS = ('python', 'py', 'python3')  # fence tags that may hold a (possibly broken) program: rule 7 (A2')
INLINE_KEYS = ('source', 'code')            # 'code' is the alias of an inline 'source'
DETAIL_KEYS, DETAIL_KEY_CHARS, DETAIL_FIELD_CHARS = 10, 40, 200

# Every frozen name this module reads, in the shape of machinery.REQUIRED ({module: (names,)}).
MACHINERY_SYMBOLS = {
    'skillopt.execskill.engineer_reader': ('FENCE', 'MAX_JSON_DEPTH', 'MAX_REPLY_BYTES', 'Unusable', 'defined_hooks',
                                           'normalize', 'schema', 'tolerant_json'),
    'skillopt.execskill.profiles': ('MAX_CHANGES',),
    'skillopt.execskill.engineer': ('EDIT_KINDS',),
}

# The field names of a new program's entry (the frozen schema): an object with one of them is a bare change.
ENTRY_FIELDS = tuple(engineer_reader.schema('new', train=False))

PROBLEM_CODES = ('oversize', 'several_manifests', 'no_manifest', 'manifest_json', 'ambiguous_envelope',
                 'no_changes_key', 'change_not_object', 'too_many_changes', 'fix_change_count', 'unknown_kind',
                 'blocks_not_assignable', 'ambiguous_source', 'no_source', 'entry_field', 'resources')

# Rule names this module writes itself (frozen names where the meaning is the frozen one); the frozen ``normalize``
# adds its own rows (schema_default, derived, inherited_change, unknown_key_ignored, relocated, ...).
REPAIR_RULES = ('tolerant_json', 'extra_json_blocks_ignored', 'manifest_outside_fence', 'manifest_absent_inherited',
                'alias_change', 'single_change_wrapped', 'bare_change', 'bare_list', 'unknown_key_ignored',
                'fence_not_program_ignored', 'fence_unassigned_ignored', 'unknown_revision_is_new', 'fix_kind_ignored',
                'inline_code_alias', 'inline_source_unfenced', 'inline_source', 'source_block_selected',
                'inline_not_program_ignored', 'echo_source_dropped')

# Why a candidate text of a change was not returned as its source (``read['ignored'][i]['why']``).
IGNORED_WHY = ('not_program', 'echo', 'same_program', 'ambiguous', 'unread')

REPLY_FORMAT = {
    'propose': ('Reply with one fenced json block holding {"changes": [...]} and then one fenced python block per '
                'change, in the same order. Each python block is one complete program. Put no program text inside '
                'the JSON.'),
    'fix': ('Reply with one fenced json block holding {"changes": [<the one corrected entry>]} and then one fenced '
            'python block with the complete corrected program. Put no program text inside the JSON.'),
}
FORMAT_RETRY_SYSTEM = ('Your previous reply could not be read. `problems` states exactly what was unreadable. Send '
                       'the same content again in the format given in `expected_format`. Do not change what the '
                       'program does; repair only the format. Give each program exactly once, inside one fenced '
                       'python block, and put no program text inside the JSON.')

# One fixed sentence per problem code, filled with counts and key names only (never reply text). The forms of
# no_changes_key, ambiguous_source and no_manifest are DESIGN 3.3's; the other twelve are worded here (addendum O8).
PROBLEM_SENTENCES = {
    'oversize': 'The reply has {size} bytes; at most {limit} bytes are read, so nothing in it was read.',
    'several_manifests': ('The reply has {count} JSON blocks or objects and {keyed} of them have a `changes` or '
                          '`change` key; exactly one is expected.'),
    'no_manifest': 'No JSON object was found (fenced code blocks: {blocks}; other text: {chars} characters).',
    'manifest_json': '{where} could not be parsed as JSON: {reason}.',
    'ambiguous_envelope': ('The JSON object has both `changes` and `change`, with different contents (changes: '
                           '{changes}; change: {alias}); send only `changes`.'),
    'no_changes_key': 'The JSON {value} has the top-level keys {keys}; none of them is `changes`.',
    'change_not_object': 'Change {change} is a JSON {value}, not an object.',
    'too_many_changes': 'The reply has {count} changes; at most {limit} are allowed, so none of them was read.',
    'fix_change_count': 'A fix reply must hold exactly one change; this reply holds {count} changes.',
    'unknown_kind': 'Change {change} has a `kind` that is none of {kinds}; a new program has "kind": "new".',
    'blocks_not_assignable': ('Change {change} cannot be matched to a fenced block: the reply has {changes} new '
                              'changes and {blocks} fenced code blocks ({programs} of them define a hook function); '
                              'give one python block per change, in the same order.'),
    'ambiguous_source': 'Change {change} gives {count} different programs: {programs}. Send exactly one.',
    'no_source': ('Change {change} has no program text that can be taken (its fenced code blocks: {blocks}, none '
                  'defining a hook function; inline `source`: {chars} characters).'),
    'entry_field': 'Change {change} has an entry field that cannot be used: {field}.',
    'resources': ('The reply could not be read within the reader limits ({error}); send it again shorter and with '
                  'less nesting.'),
}

# sha256 of the pinned texts (machinery check 6, DESIGN 3.5/4.3); ``verify()`` recomputes them.
PINS = {
    'format_retry_system': '8b0e72cfeaede6d8be7f96248b151875748e3103b2cdae22a4a548e82856d579',
    'problem_sentences': 'cb5cc536b271544048a80ff7e689840ce8ab653bd3958126e58327c6eb7b6b73',
    'reply_format.fix': '34bf0e0892d2b3318fb2e840a5f99d8010b76eeca1ea4b45dd5a8cfa9c0066b6',
    'reply_format.propose': '65248e276b3819a25b9d83e3eb8087212fc52563f804faea0fe04b393da6f517',
}

_INHERITED = object()   # the manifest marker of rule 3 (d): a fix reply without JSON reuses the entry under repair
_NUMBER_WORDS = {2: 'two', 3: 'three', 4: 'four', 5: 'five', 6: 'six', 7: 'seven', 8: 'eight', 9: 'nine', 10: 'ten'}


# ---- small helpers ---------------------------------------------------------------------------------------------
def _canonical(value):
    """Canonical JSON, the form of every typed request (``writers._json``)."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _sha(text):
    return hashlib.sha256(text.encode('utf-8', 'surrogatepass')).hexdigest()


def _bytes(text):
    return len(text.encode('utf-8', 'surrogatepass'))


def _number(value):
    return '{:,}'.format(value)


def _json_type(value):
    if isinstance(value, dict):
        return 'object'
    if isinstance(value, list):
        return 'array'
    if isinstance(value, str):
        return 'string'
    if isinstance(value, bool):
        return 'boolean'
    return 'number' if isinstance(value, (int, float)) else 'null'


def _problem(code, change=None, **fields):
    return {'code': code, 'detail': PROBLEM_SENTENCES[code].format(change=change, **fields), 'change': change}


def _result(records, problem, repairs, reply_sha):
    return {'records': records, 'problem': problem, 'repairs': repairs, 'reply_sha256': reply_sha, 'reader': READER}


def _keys_text(mapping):
    keys = [key if len(key) <= DETAIL_KEY_CHARS else key[:DETAIL_KEY_CHARS] + '...' for key in mapping]
    more = len(keys) - DETAIL_KEYS
    return repr(keys[:DETAIL_KEYS]) + (' and %s more' % _number(more) if more > 0 else '')


def _joined(parts):
    return parts[0] if len(parts) == 1 else ', '.join(parts[:-1]) + ' and ' + parts[-1]


class _Duplicate(Exception):
    pass


class _NonFinite(Exception):
    pass


def _json_reason(text):
    """Why a manifest candidate is not JSON, from a strict parse: the json module's fixed message and position, a
    duplicate key name, or a bound of the frozen reader. Deterministic; never quotes the reply."""
    def pairs(items):
        found = {}
        for key, value in items:
            if key in found:
                raise _Duplicate(key)
            found[key] = value
        return found

    def constant(name):
        raise _NonFinite(name)

    try:
        json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except _Duplicate as error:
        key = error.args[0]
        return 'the key %r appears twice in one object' % (key if len(key) <= DETAIL_KEY_CHARS else
                                                            key[:DETAIL_KEY_CHARS] + '...')
    except _NonFinite:
        return 'it contains NaN or Infinity'
    except json.JSONDecodeError as error:
        return '%s at line %d, column %d' % (error.msg, error.lineno, error.colno)
    except RecursionError:
        return 'it is nested too deeply'
    except ValueError:
        return 'it contains a number with too many digits'
    return 'it exceeds the reader limits (nesting deeper than %d levels, or text that is not UTF-8)' % (
        engineer_reader.MAX_JSON_DEPTH)


def _parsed(text):
    """(value, frozen repair rows) when the frozen ``tolerant_json`` reads the text, else None."""
    try:
        value, repairs = engineer_reader.tolerant_json(text)
    except engineer_reader.Unusable:
        return None
    return value, list(repairs)


def _keyed(value, keys=('changes', 'change')):
    return isinstance(value, dict) and any(key in value for key in keys)


def _unfenced(text):
    """An inline value that is exactly one complete fence loses its fence lines (the frozen v2.9.2 rule of
    ``engineer_reader._inline_source``, re-implemented: private frozen names are not imported); else unchanged."""
    stripped = text.strip()
    opening = re.match(r"(`{3,}|~{3,})([^\n]*)\n", stripped)
    if opening is None:
        return text, False
    delimiter, info = opening.groups()
    if info.startswith(delimiter[0]) or (delimiter[0] == '`' and '`' in info):
        return text, False
    closing = re.search(r"^[ \t]*" + re.escape(delimiter[0]) + r"{%d,}[ \t]*\r?$" % len(delimiter),
                        stripped[opening.end():], re.M)
    if closing is None or opening.end() + closing.end() != len(stripped):
        return text, False
    return stripped[opening.end():opening.end() + closing.start()], True


def _spans(text):
    """The balanced top-level ``{...}`` segments of a text, double-quoted strings respected inside a segment."""
    spans, depth, start, quoted, escaped = [], 0, 0, False, False
    for index, char in enumerate(text):
        if depth == 0:
            if char == '{':
                depth, start = 1, index
        elif quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                spans.append(text[start:index + 1])
    return spans


# ---- the public reading functions ------------------------------------------------------------------------------
def is_program(text):
    """True iff the text parses as a Python module that defines at module level at least one registered hook
    (``engineer_reader.defined_hooks`` is non-empty). Used only to choose between candidate texts."""
    return isinstance(text, str) and bool(engineer_reader.defined_hooks(text))


def read_proposals(reply, *, parent_ids=()):
    """Read a proposal reply: one record per change, in the writer's order, or a whole-reply problem."""
    ids = tuple(parent_ids)
    if not isinstance(reply, str) or not all(isinstance(item, str) for item in ids):
        raise ValueError('A proposal reply is text and parent ids are strings')
    return _guarded(reply, fix=None, parent_ids=ids)


def read_fix(reply, *, change):
    """Read a fix reply against the change under repair ``{'entry': dict, 'source': str}``: exactly one record (the
    kind is that of the change under repair, 'new') or a whole-reply problem."""
    if not isinstance(reply, str):
        raise ValueError('A fix reply is text')
    if not (isinstance(change, dict) and isinstance(change.get('entry'), dict)
            and isinstance(change.get('source'), str)):
        raise ValueError('A fix is read against the change under repair: {"entry": dict, "source": str}')
    if change['entry'].get('kind', 'new') != 'new':
        raise ValueError('Only a new program is fixed')
    entry = {key: copy.deepcopy(value) for key, value in change['entry'].items() if key not in INLINE_KEYS}
    return _guarded(reply, fix={'entry': entry, 'source': change['source']}, parent_ids=())


def readable(result):
    """No whole-reply problem, and no records (an explicit empty list: no proposal) or one record without a
    problem. A reply that is not readable triggers the format retry (``read_with_retry``)."""
    if not isinstance(result, dict) or result.get('problem') is not None:
        return False
    records = result.get('records') or []
    return not records or any(record.get('problem') is None for record in records)


def _problems(result):
    if result.get('problem') is not None:
        return [result['problem']]
    return [record['problem'] for record in result.get('records') or [] if record.get('problem') is not None]


def retry_request(purpose, bench, problems, previous_reply):
    """(system, user) of the format retry, or None when the previous reply is above RETRY_PREVIOUS_REPLY_BYTES. A new
    small request: the proposal payload is not re-sent."""
    rows = list(problems or ())
    if purpose not in REPLY_FORMAT or not isinstance(bench, str) or not bench or not isinstance(previous_reply, str):
        raise ValueError('A format retry needs a registered purpose, a bench and the previous reply')
    if not rows or not all(isinstance(row, dict) and row.get('code') in PROBLEM_CODES
                           and isinstance(row.get('detail'), str) for row in rows):
        raise ValueError('A format retry states at least one reading problem')
    if _bytes(previous_reply) > RETRY_PREVIOUS_REPLY_BYTES:
        return None
    user = {'request': 'format_retry', 'purpose': purpose, 'bench': bench,
            'problems': [{'code': row['code'], 'change': row.get('change'), 'detail': row['detail']} for row in rows],
            'expected_format': REPLY_FORMAT[purpose], 'previous_reply': previous_reply}
    return FORMAT_RETRY_SYSTEM, _canonical(user)


class RetryBudget:
    """The format retries of one attempt of a programs unit, shared by the proposal read and every fix read: ``take``
    is True exactly FORMAT_RETRIES_PER_UNIT times. It lives in memory: an interrupted unit starts again from its
    proposal call with a new budget, and every send of every attempt stays in the unit's calls file."""

    def __init__(self):
        self.left = FORMAT_RETRIES_PER_UNIT

    def take(self):
        if self.left <= 0:
            return False
        self.left -= 1
        return True


def read_with_retry(reply, sha, *, purpose, bench, send, budget, read):
    """Read a delivered reply; when nothing readable came back, send ONE format retry if the budget allows and read
    its reply with the same ``read``. ``send(system, user) -> (reply | None, request sha256)``; exceptions of
    ``send`` (the ledger's stop) pass through. ``request_sha256`` names the call whose reply is in ``result`` (the
    retry call when its reply was delivered). ``reply`` None (no reply) gives ``result`` None and no retry."""
    if purpose not in REPLY_FORMAT:
        raise ValueError('A registered reply purpose: propose or fix')
    if reply is None:
        return {'result': None, 'request_sha256': sha, 'format_retry': None}
    result = read(reply)
    if readable(result):
        return {'result': result, 'request_sha256': sha, 'format_retry': None}
    problems = _problems(result)
    request = retry_request(purpose, bench, problems, reply)
    if request is None:
        return {'result': result, 'request_sha256': sha,
                'format_retry': {'skipped': 'reply_too_large', 'problems': problems}}
    if not budget.take():
        return {'result': result, 'request_sha256': sha,
                'format_retry': {'skipped': 'budget_spent', 'problems': problems}}
    second, second_sha = send(*request)
    record = {'first_request_sha256': sha, 'request_sha256': second_sha, 'problems': problems,
              'no_reply': second is None, 'readable': False, 'problems_after': None}
    if second is None:
        return {'result': result, 'request_sha256': sha, 'format_retry': record}
    again = read(second)
    record.update(readable=readable(again), problems_after=_problems(again))
    return {'result': again, 'request_sha256': second_sha, 'format_retry': record}


def computed_pins():
    texts = {'format_retry_system': FORMAT_RETRY_SYSTEM, 'problem_sentences': _canonical(PROBLEM_SENTENCES),
             'reply_format.fix': REPLY_FORMAT['fix'], 'reply_format.propose': REPLY_FORMAT['propose']}
    return {name: hashlib.sha256(text.encode('utf-8')).hexdigest() for name, text in texts.items()}


def verify():
    """The names of the pinned texts whose sha256 differs from PINS (an empty list when all hold)."""
    computed = computed_pins()
    return sorted(name for name in set(computed) | set(PINS) if computed.get(name) != PINS.get(name))


# ---- reading ---------------------------------------------------------------------------------------------------
def _guarded(reply, **options):
    reply_sha = _sha(reply)
    try:
        return _read(reply, reply_sha, **options)
    except (RecursionError, MemoryError, OverflowError) as error:
        return _result([], _problem('resources', error=type(error).__name__), [], reply_sha)


def _read(reply, reply_sha, *, fix, parent_ids):
    size = _bytes(reply)
    if size > engineer_reader.MAX_REPLY_BYTES:                                              # rule 1
        return _result([], _problem('oversize', size=_number(size), limit=_number(engineer_reader.MAX_REPLY_BYTES)),
                       [], reply_sha)
    candidates, code, outside = _blocks(reply)                                              # rule 2
    manifest, repairs, problem = _manifest(reply, candidates, code, outside, fix)           # rule 3
    changes = []
    if problem is None and manifest is _INHERITED:
        changes = [copy.deepcopy(fix['entry'])]
    elif problem is None:
        changes, problem = _envelope(manifest, repairs)                                     # rule 4
    if problem is None and fix is not None and len(changes) != 1:                           # rule 5
        problem = _problem('fix_change_count', count=_number(len(changes)))
    elif problem is None and fix is None and len(changes) > profiles.MAX_CHANGES:
        problem = _problem('too_many_changes', count=_number(len(changes)), limit=_number(profiles.MAX_CHANGES))
    if problem is not None:
        return _result([], problem, repairs, reply_sha)
    return _result(_records(changes, code, repairs, fix=fix, parent_ids=parent_ids, reply_sha=reply_sha), None,
                   repairs, reply_sha)


def _blocks(reply):
    """Fenced blocks with the frozen FENCE (one pass): JSON candidates (tagged json/jsonc/json5, or untagged and
    starting with ``{`` or ``[``), code blocks (every other block, numbered from 1 in reply order) and the text
    outside the fences, stripped."""
    candidates, code, outside, end = [], [], [], 0
    for match in engineer_reader.FENCE.finditer(reply):
        outside.append(reply[end:match.start()])
        end = match.end()
        tag, body = match.group(2).strip().lower(), match.group(3)
        if tag in JSON_TAGS or (tag == '' and body.lstrip().startswith(('{', '['))):
            candidates.append(body)
        else:
            code.append({'block': len(code) + 1, 'text': body, 'program': is_program(body), 'tag': tag})
    outside.append(reply[end:])
    return candidates, code, ''.join(outside).strip()


def _manifest(reply, candidates, code, outside, fix):
    """Rule 3: (manifest | _INHERITED | None, repair rows, problem | None)."""
    if len(candidates) == 1:                                                                # (a)
        found = _parsed(candidates[0])
        if found is None:
            return None, [], _problem('manifest_json', where='The fenced JSON block', reason=_json_reason(candidates[0]))
        return found[0], found[1], None
    if candidates:                                                                          # (b)
        parsed = [found for found in map(_parsed, candidates) if found is not None]
        extra = [{'rule': 'extra_json_blocks_ignored', 'path': '$', 'count': len(candidates) - 1}]
        if len(parsed) == 1:   # (a) read as "exactly one candidate parses": the others cannot be a manifest
            return parsed[0][0], parsed[0][1] + extra, None
        keyed = [found for found in parsed if _keyed(found[0], ('changes', 'change'))]
        if len(keyed) == 1:    # (b) one pass over both keys: a `changes` block never silently beats a `change` block
            return keyed[0][0], keyed[0][1] + extra, None
        return None, [], _problem('several_manifests', count=_number(len(candidates)), keyed=_number(len(keyed)))
    whole = _parsed(outside) if outside else None                                           # (c)
    if whole is not None and isinstance(whole[0], (dict, list)):
        return whole[0], whole[1] + ([{'rule': 'manifest_outside_fence', 'path': '$'}] if code else []), None
    spans = [found for found in map(_parsed, _spans(outside)) if found is not None and isinstance(found[0], dict)]
    if len(spans) == 1:
        return spans[0][0], spans[0][1] + [{'rule': 'manifest_outside_fence', 'path': '$'}], None
    if len(spans) > 1:
        return None, [], _problem('several_manifests', count=_number(len(spans)),
                                  keyed=_number(sum(_keyed(found[0]) for found in spans)))
    if fix is not None and code:                                                            # (d)
        return _INHERITED, [{'rule': 'manifest_absent_inherited', 'path': '$'}], None
    if outside.startswith(('{', '[')):                                                      # (e)
        if code:   # positions count in the text left after removing the fences
            return None, [], _problem('manifest_json', where='The text outside the fenced blocks',
                                      reason=_json_reason(outside))
        return None, [], _problem('manifest_json', where='The reply', reason=_json_reason(reply))
    return None, [], _problem('no_manifest', blocks=_number(len(code)), chars=_number(len(outside)))


def _envelope(manifest, repairs):
    """Rule 4: (the list of changes, None) or (None, problem); envelope repair rows are appended to ``repairs``."""
    if isinstance(manifest, list):
        repairs.append({'rule': 'bare_list', 'path': '$'})
        return list(manifest), None
    if not isinstance(manifest, dict):
        return None, _problem('no_changes_key', value=_json_type(manifest), keys='[]')
    present = [key for key in ('changes', 'change') if key in manifest]
    if present:
        if len(present) == 2:
            first, second = (value if isinstance(value, list) else [value]
                             for value in (manifest['changes'], manifest['change']))
            if first != second:
                return None, _problem('ambiguous_envelope', changes=_number(len(first)), alias=_number(len(second)))
            repairs.append({'rule': 'alias_change', 'path': '$.change', 'to': '$.changes', 'duplicate': True})
        elif present == ['change']:
            repairs.append({'rule': 'alias_change', 'path': '$.change', 'to': '$.changes'})
        repairs.extend({'rule': 'unknown_key_ignored', 'path': '$.' + key} for key in manifest
                       if key not in ('changes', 'change'))
        value = manifest[present[0]]
        if not isinstance(value, list):
            repairs.append({'rule': 'single_change_wrapped', 'path': '$.' + present[0]})
            value = [value]
        return list(value), None
    if any(key in manifest for key in INLINE_KEYS + ENTRY_FIELDS):
        repairs.append({'rule': 'bare_change', 'path': '$'})
        return [manifest], None
    return None, _problem('no_changes_key', value='object', keys=_keys_text(manifest))


def _state(n, change, *, fix, parent_ids):
    """Rule 6 (kind) for one change; the inline candidates (``source``, alias ``code``, unfenced when fenced)."""
    state = {'n': n, 'raw': change, 'kind': None, 'problem': None, 'inline': [], 'kind_rows': [],
             'drop_revises': False, 'owned': [], 'source': None, 'chosen': None, 'candidates': [], 'echoes': [],
             'entry': None, 'entry_rows': []}
    if not isinstance(change, dict):
        state['problem'] = _problem('change_not_object', change=n, value=_json_type(change))
        return state
    for key in INLINE_KEYS:
        value = change.get(key)
        if isinstance(value, str) and value.strip():
            text, unfenced = _unfenced(value)
            if text.strip():
                state['inline'].append({'origin': 'inline' if key == 'source' else 'inline_code', 'key': key,
                                        'block': None, 'text': text, 'unfenced': unfenced,
                                        'program': is_program(text)})
    if fix is not None:              # the kind is that of the change under repair; a stated other kind is ignored
        if 'kind' in change and change['kind'] != 'new':
            state['kind_rows'].append({'rule': 'fix_kind_ignored', 'path': '$.kind'})
        state['kind'] = 'new'
        return state
    target = change.get('revises', change.get('id'))
    known = isinstance(target, str) and target in parent_ids
    kind = change['kind'] if 'kind' in change else ('revision' if known else 'new')
    if kind == 'revision' and not known:
        kind, state['drop_revises'] = 'new', True
        state['kind_rows'].append({'rule': 'unknown_revision_is_new', 'path': '$.kind'})
    if not (isinstance(kind, str) and kind in engineer.EDIT_KINDS):
        state['problem'] = _problem('unknown_kind', change=n, kinds=', '.join(engineer.EDIT_KINDS))
    else:
        state['kind'] = kind
    return state


def _blocks_row(rule, blocks):
    return {'rule': rule, 'path': '$', 'count': len(blocks),
            'blocks': [{'block': block['block'], 'chars': len(block['text']), 'sha256': _sha(block['text'])}
                       for block in blocks]}


def _owners(new, code, repairs):
    """Rule 7, block ownership. E = the new changes in order; B = the code blocks, reduced to the program blocks
    when any block is a program. (A1) len(B) == len(E): by position; (A2) len(B) == the number of changes without a
    program inline source: by position among those; (A2') the same over ALL code blocks, reached only when the
    reduction dropped blocks AND every code block is a python-tagged fence (a block that is a broken program, beside
    program blocks, still belongs to its change by position, as the frozen reader assigns it; a prose, untagged or
    other-language block never takes a position, so a program is never paired with another change's entry: Codex
    review round 1, finding 3, coordinator reading of the conflict between rule 7 and frozen-reader parity); (A3) one change: every block of B is its candidate; (A4) else
    each change without a program inline source gets the problem blocks_not_assignable. Blocks no change owns are
    recorded at the reply level."""
    programs = [block for block in code if block['program']]
    reduced = programs or code
    needing = [state for state in new if not any(item['program'] for item in state['inline'])]
    if len(reduced) == len(new):
        pairs, used = zip(new, reduced), reduced
    elif len(reduced) == len(needing):
        pairs, used = zip(needing, reduced), reduced
    elif len(code) == len(needing) and all(block.get('tag') in PYTHON_TAGS for block in code):
        pairs, used = zip(needing, code), code
    elif len(new) == 1:
        new[0]['owned'] = list(reduced)
        pairs, used = (), reduced
    else:
        pairs, used = (), []
        for state in needing:
            state['problem'] = _problem('blocks_not_assignable', change=state['n'], changes=_number(len(new)),
                                        blocks=_number(len(code)), programs=_number(len(programs)))
    for state, block in pairs:
        state['owned'] = [block]
    numbers = {block['block'] for block in used}
    dropped = [block for block in code if block['block'] not in numbers]
    if dropped:
        repairs.append(_blocks_row('fence_not_program_ignored' if used else 'fence_unassigned_ignored', dropped))


def _take_source(state, failed):
    """Rule 8: the source of a new change. Program candidates (equal texts once; in a fix, an echo of the failed
    source is dropped while another program remains): one -> the source, several -> ambiguous_source. No program
    candidate: the single owned block, else the inline text, unchanged (the screen names the fault); else
    no_source. Never inherited from the failed change or a parent; never altered apart from fence lines."""
    owned = [block for block in state['owned'] if block['text'].strip()]
    candidates = state['inline'] + [{'origin': 'fence %d' % block['block'], 'key': None, 'block': block['block'],
                                     'text': block['text'], 'unfenced': False, 'program': block['program']}
                                    for block in owned]
    state['candidates'] = candidates
    programs = [item for item in candidates if item['program']]
    if failed is not None:
        echo = failed.strip()
        if any(item['text'].strip() != echo for item in programs):
            state['echoes'] = [item for item in programs if item['text'].strip() == echo]
            programs = [item for item in programs if item['text'].strip() != echo]
    distinct, seen = [], set()
    for item in programs:
        if item['text'].strip() not in seen:
            seen.add(item['text'].strip())
            distinct.append(item)
    if len(distinct) > 1:
        described = ['%s (%s characters)' % ('inline `%s`' % item['key'] if item['block'] is None else
                                             'fenced block %d' % item['block'], _number(len(item['text'])))
                     for item in distinct]
        state['problem'] = _problem('ambiguous_source', change=state['n'], programs=_joined(described),
                                    count=_NUMBER_WORDS.get(len(distinct), _number(len(distinct))))
        return
    if distinct:
        state['chosen'] = distinct[0]
    elif len(owned) == 1:
        state['chosen'] = candidates[len(state['inline'])]
    elif not owned and state['inline']:
        state['chosen'] = state['inline'][0]
    else:
        inline = state['inline'][0]['text'] if state['inline'] else state['raw'].get('source')
        state['problem'] = _problem('no_source', change=state['n'], blocks=_number(len(state['owned'])),
                                    chars=_number(len(inline) if isinstance(inline, str) else 0))
        return
    state['source'] = state['chosen']['text']


def _take_entry(state, inherited):
    """Rule 9: the entry without source/code through the frozen public ``normalize`` (mode single: the call of the
    frozen reader); a frozen ``Unusable`` (or any refusal of a value) is the problem entry_field."""
    entry = {key: copy.deepcopy(value) for key, value in state['raw'].items() if key not in INLINE_KEYS}
    if 'kind' in entry:
        entry['kind'] = 'new'
    if state['drop_revises']:
        entry.pop('revises', None)
    rows = []
    try:
        entry = engineer_reader.normalize(
            entry, engineer_reader.schema('new', train=False, source=state['source'], entry=entry),
            inherited=inherited, repairs=rows, configuration=MACHINERY)
    except (ValueError, TypeError) as error:     # engineer_reader.Unusable is a ValueError
        state['problem'] = _problem('entry_field', change=state['n'],
                                    field=str(error)[:DETAIL_FIELD_CHARS].rstrip('.') or type(error).__name__)
        return
    state['entry'], state['entry_rows'] = entry, rows


def _records(changes, code, repairs, *, fix, parent_ids, reply_sha):
    states = [_state(n, change, fix=fix, parent_ids=parent_ids) for n, change in enumerate(changes, 1)]
    _owners([state for state in states if state['problem'] is None and state['kind'] == 'new'], code, repairs)
    failed = fix['source'] if fix is not None else None
    inherited = (fix['entry'] if fix is not None else {}, {})
    records = []
    for state in states:
        if state['problem'] is None and state['kind'] == 'new':
            _take_source(state, failed)
            if state['problem'] is None:
                _take_entry(state, inherited)
        records.append(_record(state, repairs, reply_sha))
    return records


def _why(item, state, chosen):
    """Why a candidate text was not returned (IGNORED_WHY)."""
    if any(item is echo for echo in state['echoes']):
        return 'echo'
    if chosen is not None:   # every other program candidate has the chosen text (else the source is ambiguous)
        return 'same_program' if item['text'].strip() == chosen['text'].strip() else 'not_program'
    code = (state['problem'] or {}).get('code')
    if code == 'ambiguous_source':
        return 'ambiguous' if item['program'] else 'not_program'
    return 'not_program' if code == 'no_source' else 'unread'


def _record(state, base, reply_sha):
    """One record: entry, source, problem, the repair rows in the frozen order (reply rows, inline rows, kind rows,
    source rule, normalize rows) and ``read`` with every candidate text that was not returned."""
    readable_new = state['problem'] is None and state['kind'] == 'new'
    chosen = state['chosen'] if readable_new else None
    candidates = state['candidates'] or state['inline']
    inline_rows, source_rows, typed_rows, ignored = [], [], [], []
    if chosen is not None and chosen['block'] is None:
        if chosen['key'] == 'code':
            inline_rows.append({'rule': 'inline_code_alias', 'path': '$.code', 'to': '$.source'})
        if chosen['unfenced']:
            inline_rows.append({'rule': 'inline_source_unfenced', 'path': '$.source'})
        source_rows.append({'rule': 'inline_source', 'path': '$.source'})
    elif chosen is not None:
        source_rows.append({'rule': 'source_block_selected', 'path': '$.source'})
    for item in candidates:
        if item is chosen:
            continue
        why = _why(item, state, chosen)
        ignored.append({'from': item['origin'], 'chars': len(item['text']), 'sha256': _sha(item['text']), 'why': why})
        if why == 'not_program' and item['block'] is None and chosen is not None:
            typed_rows.append({'rule': 'inline_not_program_ignored', 'path': '$.' + item['key']})
    if chosen is not None and state['echoes']:
        typed_rows.append({'rule': 'echo_source_dropped', 'path': '$.source'})
    if readable_new:
        entry = state['entry']
        same = any(item['block'] is not None and item['text'].strip() == chosen['text'].strip() for item in candidates)
        source_from = 'fence' if chosen['block'] is not None else 'inline_and_fence_equal' if same else 'inline'
    elif state['problem'] is None:   # another kind: returned without source and without normalisation
        entry = {key: copy.deepcopy(value) for key, value in state['raw'].items() if key not in INLINE_KEYS}
        entry['kind'] = state['kind']
        source_from = None
    else:
        entry = copy.deepcopy(state['raw']) if isinstance(state['raw'], dict) else None
        source_from = None
    source = state['source'] if readable_new else None
    hooks = list(engineer_reader.defined_hooks(source)) if source is not None else []
    repairs = (copy.deepcopy(base) + inline_rows + state['kind_rows'] + source_rows + typed_rows
               + (state['entry_rows'] if readable_new else []))
    return {'n': state['n'], 'kind': state['kind'], 'entry': entry, 'source': source, 'problem': state['problem'],
            'repairs': repairs,
            'read': {'source_from': source_from, 'is_program': bool(hooks), 'hooks_defined': hooks,
                     'ignored': ignored, 'reply_sha256': reply_sha, 'reader': READER}}
