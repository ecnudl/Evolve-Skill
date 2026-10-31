"""Bounded v2.15 engineer-only hook diagnostics, separate from delivered notes."""
from __future__ import annotations

import copy
import hashlib
import json
import re
import time

CONFIGURATION = 'zebra-pc-v14'
VERSION = 'engineer-diagnostics-v2-15'
MAX_STRINGS = 5
MAX_CHARS = 240
LOOKAHEAD = 256
PROCESSING_SECONDS = 0.1
INPUT_BYTES = 64_000
SCREENED_MARKER = '[diagnostic withheld by public-text screen]'


def enabled(configuration):
    return configuration in (CONFIGURATION, 'zebra-pc-v15')


def sha256(value):
    text = value if isinstance(value, str) else json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def identity():
    return {'version': VERSION, 'configuration': CONFIGURATION,
            'max_strings': MAX_STRINGS, 'max_characters': MAX_CHARS,
            'engineer_input_bytes': INPUT_BYTES, 'legacy_user_input_bytes': 220_000,
            'total_user_input_bytes': 220_000 + INPUT_BYTES,
            'screen': 'existing audit.marked lexical/instruction predicate and notes.CHANNEL_MARKERS_V29',
            'screened_marker': SCREENED_MARKER, 'shape_faults': 'informational',
            'solver_visibility': False, 'input_scope': 'public_hook_view_only',
            'aggregate': 'top8_distinct_strings_by_distinct_fired_run_items',
            'hash': 'sha256_utf8_text_and_canonical_json_record',
            'public_screen_sha256': sha256(worker_spec())}


def worker_spec(bench='zebralogic'):
    """Portable exact existing screen vocabulary; created only on the host."""
    from . import notes
    if bench != 'zebralogic':
        raise ValueError('The v2.15 diagnostic worker is Zebra-only')
    return {'lexicon': [[pattern.pattern, pattern.flags] for _, pattern in notes.PATTERNS[bench]],
            'form': [notes.FORM_PATTERN.pattern, notes.FORM_PATTERN.flags],
            'prefix': [notes.INSTRUCTION_PREFIX.pattern, notes.INSTRUCTION_PREFIX.flags],
            'reply_noun': [notes.REPLY_NOUN.pattern, notes.REPLY_NOUN.flags],
            'markers': list(notes.CHANNEL_MARKERS_V29)}


def _marked(text, spec):
    # Only displayed text and a fixed look-ahead require the potentially costly screen.
    text = text[:MAX_CHARS + LOOKAHEAD]
    if any(re.search(pattern, text, flags) for pattern, flags in spec['lexicon']):
        return True
    form, prefix, noun = (re.compile(*spec[key]) for key in ('form', 'prefix', 'reply_noun'))
    for match in form.finditer(text):
        if not prefix.search(text[:match.start()].lstrip(' -*\t')):
            continue
        if match.group(0).lower() in ('only the', 'just the') and not noun.match(text[match.end():]):
            continue
        return True
    return any(marker in text.lower() for marker in spec['markers'])


def _seal(value):
    value = {k: v for k, v in value.items() if k != 'sha256'}
    return {**value, 'sha256': sha256(value)}


def bounded(value, *, screen_spec=None):
    """Normalize raw diagnostic value without importing runtime/profile modules.

    The worker strips the raw field before accepting its clean output limit,
    then builds this sidecar under a separate budget. Only a bounded prefix
    and original digest survive; no other result changes.
    """
    out = {'version': VERSION, 'strings': [], 'shape_faults': [],
           'truncated_strings': 0, 'omitted_strings': 0, 'ignored_values': 0,
           'screened_count': 0}
    if type(value) is not list:
        out['shape_faults'].append({'kind': 'shape', 'informational': True, 'reason': 'not_list'})
        out['ignored_values'] = 1
        return _seal(out)
    if len(value) > MAX_STRINGS:
        out['omitted_strings'] = len(value) - MAX_STRINGS
        out['shape_faults'].append({'kind': 'shape', 'informational': True, 'reason': 'too_many',
                                    'count': len(value) - MAX_STRINGS})
    for index, text in enumerate(value[:MAX_STRINGS]):
        if type(text) is not str:
            out['ignored_values'] += 1
            out['shape_faults'].append({'kind': 'shape', 'informational': True,
                                        'reason': 'not_string', 'index': index})
            continue
        try:
            encoded = text.encode('utf-8')
        except UnicodeError:
            out['ignored_values'] += 1
            out['shape_faults'].append({'kind': 'shape', 'informational': True,
                                        'reason': 'invalid_unicode', 'index': index})
            continue
        screened = screen_spec is not None and _marked(text, screen_spec)
        cut = SCREENED_MARKER if screened else text[:MAX_CHARS]
        # Cutting a safe word can create a forbidden prefix (e.g. answerable).
        if not screened and screen_spec is not None and _marked(cut, screen_spec):
            screened, cut = True, SCREENED_MARKER
        out['strings'].append({'text': cut, 'sha256': sha256(cut), 'source_sha256': hashlib.sha256(encoded).hexdigest(),
                               'original_chars': len(text), 'truncated': len(text) > MAX_CHARS,
                               'screened': screened})
        out['truncated_strings'] += len(text) > MAX_CHARS
        out['screened_count'] += screened
    return _seal(out)



def informational(reason):
    """A fixed, text-free omission record; it never becomes a procedure fault."""
    if reason not in ('processing_failed', 'processing_timeout', 'invalid_record'):
        reason = 'processing_failed'
    return _seal({'version': VERSION, 'strings': [],
        'shape_faults': [{'kind': 'shape', 'informational': True, 'reason': reason}],
        'truncated_strings': 0, 'omitted_strings': 0, 'ignored_values': 1, 'screened_count': 0})


def safe_bounded(value, *, screen_spec=None):
    """Diagnostic errors/overruns omit only this informational channel."""
    started = time.monotonic()
    try:
        result = bounded(value, screen_spec=screen_spec)
    except BaseException:
        return informational('processing_failed')
    return informational('processing_timeout') if time.monotonic() - started > PROCESSING_SECONDS else result


def safe_verified_record(value, *, bench='zebralogic'):
    started = time.monotonic()
    try:
        result = verified_record(value, bench=bench)
    except BaseException:
        return informational('invalid_record')
    return informational('processing_timeout') if time.monotonic() - started > PROCESSING_SECONDS else result

def screen_record(value, *, bench='zebralogic'):
    """Apply the existing public lexical/imperative checks before disclosure.

    String screening is deliberately strict: a failing whole string becomes a
    fixed marker; it never contributes its offending text to another field.
    """
    from . import audit, notes
    out = copy.deepcopy(value)
    count = 0
    for row in out.get('strings', ()):
        text = row['text']
        failed = bool(row.get('screened')) or audit.marked(text, bench) or any(
            marker in text.lower() for marker in notes.CHANNEL_MARKERS_V29)
        if failed:
            row['text'] = SCREENED_MARKER
            row['sha256'] = sha256(SCREENED_MARKER)
            row['screened'] = True
            count += 1
    out['screened_count'] = count
    return _seal(out)


def extract(value, *, configuration, bench='zebralogic', hook='before_call',
            procedure=None, source_sha256=None):
    """Return (diagnostic-free original output, screened bounded record or None)."""
    if not enabled(configuration) or hook != 'before_call' or not isinstance(value, dict) or 'diagnostics' not in value:
        return value, None
    clean = {k: v for k, v in value.items() if k != 'diagnostics'}
    try:
        record = safe_verified_record(safe_bounded(value['diagnostics'], screen_spec=worker_spec(bench)), bench=bench)
    except BaseException:
        record = informational('processing_failed')
    record.update(hook=hook)
    if procedure is not None:
        record['procedure'] = procedure
    if source_sha256 is not None:
        record['source_sha256'] = source_sha256
    return clean, _seal(record)


def verified_record(value, *, bench='zebralogic'):
    """Validate a stored channel and re-screen at the engineer boundary."""
    if not isinstance(value, dict) or value.get('version') != VERSION:
        raise ValueError('Unknown diagnostic record')
    if value.get('sha256') != sha256({k: v for k, v in value.items() if k != 'sha256'}):
        raise ValueError('Diagnostic record hash mismatch')
    strings = value.get('strings')
    if not isinstance(strings, list) or len(strings) > MAX_STRINGS:
        raise ValueError('Diagnostic string bounds')
    for row in strings:
        if (not isinstance(row, dict) or type(row.get('text')) is not str
                or len(row['text']) > MAX_CHARS or row.get('sha256') != sha256(row['text'])):
            raise ValueError('Diagnostic text/hash bounds')
        if (set(row) != {'text', 'sha256', 'source_sha256', 'original_chars', 'truncated', 'screened'}
                or type(row['original_chars']) is not int or row['original_chars'] < 0
                or type(row['truncated']) is not bool or type(row['screened']) is not bool
                or type(row['source_sha256']) is not str or len(row['source_sha256']) != 64
                or any(c not in '0123456789abcdef' for c in row['source_sha256'])):
            raise ValueError('Diagnostic text metadata')
    faults = value.get('shape_faults')
    if not isinstance(faults, list) or len(faults) > MAX_STRINGS + 1:
        raise ValueError('Diagnostic shape-fault bounds')
    for fault in faults:
        if (not isinstance(fault, dict) or fault.get('kind') != 'shape'
                or fault.get('informational') is not True
                or fault.get('reason') not in ('not_list', 'too_many', 'not_string', 'invalid_unicode',
                                             'processing_failed', 'processing_timeout', 'invalid_record')
                or set(fault) - {'kind', 'informational', 'reason', 'index', 'count'}):
            raise ValueError('Diagnostic informational shape')
    for key in ('truncated_strings', 'omitted_strings', 'ignored_values', 'screened_count'):
        if type(value.get(key)) is not int or value[key] < 0:
            raise ValueError('Diagnostic counters')
    return screen_record(value, bench=bench)
