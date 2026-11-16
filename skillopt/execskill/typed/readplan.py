"""The economy read plan of typed-v2, pure core (decisions D9, D10, D12, RP1 to RP12; ``spec/read-plan.md``).

Under ``read_plan = economy`` every distinct set of requests is read fresh exactly once: per bench, the seven read
events (C0, C, S1..S5) fall into CLASSES of equal per-item mount identity, the latest event of a class (the
REPRESENTATIVE) is read fresh, and every other member gets an ALIAS record that names the representative and stores
the proof. This module holds everything of that area that is a deterministic function of data passed in:

- per-item identity records from given components (R8 to R16): the ``mount.mount_identity`` output, the
  capture-mounted record's selection hash, ``public_sha256``, ``view_sha256``, the offered programs' record hashes
  and the first-request hash where RP3 requires it, each bound to the event's arm and to the frozen state the plan
  names for the event (K-A); the capture selector and capture call objects (R17, R19);
- identity lists per (event, bench), classes, representatives, the first-request condition and fallback classes
  with the closed reason vocabulary (R28 to R31, R81, R91);
- the sealed inputs and identities records (R78, 3.3), the open plan document (3.2) with canonical bytes, self-hash,
  ``write_once`` (R80), load and verify (R44 a), and the byte comparison of a replay (R47);
- alias records: build, verify against the plan, state entry (R39, R41 counts, RP3 counts; 3.4);
- the check of open records: hashes and counts only, never an item id, a text, an answer or a score (R81, T23).

Nothing here calls a model, opens a panel, reads chain state or starts a process. The integration (capture through
the real ``mount.mount``, panels, frozen states, the replay child, the readout, the CLI) calls these functions; the
identity is built on the one routing path of Step 5m (RP9), never on a third mount implementation, which is why this
module imports neither ``mount`` nor ``reads``. Everything the integration hands in is checked here, and every doubt
becomes a fallback (read fresh, D10 f), never a removed read.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from copy import deepcopy
from pathlib import Path

from . import CHAINS, ORDER, READ_ARMS
from .library import canonical_sha256, sha256_text
from .units import checked_path

# ---- versions, names, vocabulary -----------------------------------------------------------------------------
IDENTITY_VERSION = 'typed-v2-mount-identity-1'
PLAN_VERSION = 'typed-v2-read-plan-1'
ALIAS_VERSION = 'typed-v2-read-alias-1'
INPUTS_VERSION = 'typed-v2-read-plan-inputs-1'
IDENTITIES_VERSION = 'typed-v2-read-plan-identities-1'

EVENTS = tuple(READ_ARMS)                              # ('C0', 'C', 'S1', ..., 'S5'): the order of R29 and D10 c
S_EVENTS = tuple(e for e in EVENTS if e.startswith('S'))
ARM_OF_EVENT = {'C0': 'C0', 'C': 'C'}                  # every S<k> reads the library with arm F (reads.arm_of)
STEP_OF_EVENT = {'C0': 0, 'C': 0, **{event: int(event[1:]) for event in S_EVENTS}}   # C0 and C read s0 (R27)
PAIRS = len(EVENTS) * len(ORDER)                       # 35 (event, bench) pairs per chain
NO_CAPTURE_BENCH = 'alfworld'                          # RP3 option 1 a: no first-request capture on ALFWorld
FIRST_REQUEST_BENCHES = tuple(b for b in ORDER if b != NO_CAPTURE_BENCH)
BASE_CARDS = ('format', 'historical')                  # D17
SCHEDULE = 'learn_first'                               # D9: economy only with learn_first
READ_PLAN = 'economy'
STATUSES = ('ok', 'fallback')
SELECTION_CAPTURE_ERROR = 'read_plan_capture'          # R17, R19: the error type of every captured "reply"

# R81: one closed tuple for every reason, fallback, void reason, replay detail and recovery outcome.
PASS_FALLBACK_REASONS = ('identity_exception', 'identity_disagreement', 'capture_failed', 'embedder_unstable',
                         'first_request_mismatch', 'smoke_probe')                                    # R31
FALLBACK_REASONS = PASS_FALLBACK_REASONS + ('post_read_mismatch',)                                     # R42
PASS_FAILURE_CODES = ('inputs_mismatch', 'view_mismatch', 'sealed_file_mismatch', 'plan_file_mismatch',
                      'plan_self_check', 'pass_exception')                                           # R33 c, Q24
VOID_REASONS = ('pass_failed', 'sealed_file_invalid', 'replay_different', 'replay_error')            # R33 d, R44
REPLAY_CODES = ('replay_different', 'replay_error', 'qualification_missing', 'replay_exception', 'timeout')  # R47, R76
PAUSE_REASONS = ('read_plan_failed', 'read_plan_changed', 'read_alias_invalid', 'read_plan_incomplete',
                 'stopped_after_plan', 'solver_settings_changed', 'frozen_state_changed', 'read_mount_changed')
RECOVERY_OUTCOMES = ('pass_rerun', 'plan_restored', 'replay_equal', 'plan_void', 'alias_unsettled', 'paused_again')
READ_PLAN_REASONS = tuple(dict.fromkeys(FALLBACK_REASONS + PASS_FAILURE_CODES + VOID_REASONS + REPLAY_CODES
                                        + PAUSE_REASONS + RECOVERY_OUTCOMES))
REPLAY_VERDICTS = ('equal', 'different', 'error')
EXIT_CODE = re.compile(r'^exit_-?\d{1,4}$')            # R76: replay_error:exit_<n>

PLAN_UNIT = 'read-plan'                                # the pass's pseudo-unit and done_units marker
PLAN_FILE = 'read-plan.json'                           # open: <chain>/read-plan.json
SEALED_DIR = 'test-read-plan'                          # sealed by its name (3.8); written with allow_sealed only
SMOKE_SEALED_DIR = 'practice-read-plan'
ALIAS_DIR = 'read-alias'
ARCHIVE_DIR = 'archived'
PART_NAME = re.compile(r'^\.(?P<name>[^/]+)\.(?P<pid>\d+)\.(?P<nonce>[0-9a-f]{16})\.part$')   # R80
HEX64 = re.compile(r'^[0-9a-f]{64}$')

READ_MOUNT_ARMS = ('C0', 'C', 'F')                    # R11: the only arms of a read; a candidate arm never occurs
COMPONENT_KEYS = ('public_sha256', 'view_sha256', 'system_sha256', 'selection_sha256', 'programs', 'type', 'source',
                  'unknown_reason', 'card_skill', 'offered')
DESCRIPTIVE_KEYS = ('type', 'source', 'unknown_reason')   # R30: counted when they flip, never a fallback
RECORD_KEYS = ('identity', 'first_request', 'components')
# The frozen state an event's identities were computed from: the shape of ``state['read_mounts'][event]``
# (schedule-lock S6) and of R39 (2)'s check; bound to the plan's ``frozen[event]`` (K-A).
READ_MOUNT_KEYS = ('step', 'library_file_sha256', 'typemap_file_sha256')
ENTRY_KEYS = ('arm', 'status', 'reason', 'identity', 'first_request', 'components', 'descriptive_flips') \
    + READ_MOUNT_KEYS
INPUTS_KEYS = ('version', 'chain', 'bench', 'item_ids', 'view_sha256', 'alfworld_views', 'vectors', 'views_sha256',
               'vectors_sha256', 'record_sha256')
IDENTITIES_KEYS = ('version', 'chain', 'bench', 'item_ids', 'inputs_sha256', 'events', 'record_sha256')
FROZEN_KEYS = ('step', 'library_record_sha256', 'typemap_record_sha256', 'library_file_sha256', 'typemap_file_sha256',
               'receipt_sha256')
PLAN_KEYS = ('version', 'identity_version', 'chain', 'smoke', 'schedule', 'read_plan', 'base_card',
             'manifest_record_sha256', 'solver_settings_sha256', 'events', 'order', 'frozen', 'benches', 'read_order',
             'counts', 'plan_sha256')
BENCH_KEYS = ('items', 'item_set_sha256', 'registry_sha256', 'run_constants_sha256', 'inputs_sha256',
              'identities_sha256', 'embed', 'events', 'classes')
EVENT_KEYS = ('arm', 'status', 'reason', 'identity_list_sha256', 'first_request_list_sha256', 'captured', 'typed',
              'unknown', 'with_card', 'with_programs')
CLASS_KEYS = ('id', 'members', 'representative', 'identity_list_sha256', 'first_request_list_sha256')
ALIAS_KEYS = ('version', 'chain', 'event', 'bench', 'kind', 'representative', 'items', 'identity_list_sha256',
              'first_request_list_sha256', 'plan_sha256', 'check', 'representative_aggregate_sha256',
              'representative_counts', 'record_sha256')
CHECK_KEYS = ('items', 'equal', 'unequal')
COUNT_KEYS = ('unknown', 'infrastructure_unknown', 'configuration_errors')
OBSERVED_KEYS = ('system_sha256', 'selection_sha256', 'programs', 'public_sha256', 'first_request')

# Open records (plan, alias records, solver settings, state): no key that names test content, no float (no score),
# no text over a hash's length, no reason outside READ_PLAN_REASONS.
FORBIDDEN_OPEN_KEYS = frozenset({
    'item_id', 'item_ids', 'task_id', 'items_list', 'answer', 'answers', 'gold', 'solution', 'score', 'scores',
    'correct', 'incorrect', 'pass', 'fail', 'passed', 'failed', 'accuracy', 'reply', 'response', 'prediction', 'output',
    'output_excerpt', 'raw_excerpt', 'failure', 'text', 'texts', 'card_text', 'system_card', 'system', 'user', 'prompt',
    'question', 'public', 'private', 'view', 'views', 'alfworld_views', 'vectors', 'components', 'identity',
    'first_request', 'token', 'final_token', 'official'})
REASON_KEYS = frozenset({'reason', 'void_reason', 'fallback', 'detail', 'code', 'outcome', 'failures'})
OPEN_TEXT_MAX = 64
OPEN_RECORD_VIOLATIONS = ('key_not_text', 'forbidden_key', 'item_id', 'planted_text', 'long_string', 'float',
                          'reason_outside_vocabulary', 'verdict_outside_vocabulary', 'value_type')


# The three error classes keep their constructor arguments as ``args`` (the message is built in ``__str__``), so
# pickle and copy rebuild them unchanged, for example across a process pool of the per-bench identity loop.
class ReadPlanError(ValueError):
    """A detected read-plan inconsistency. ``code`` is a member of READ_PLAN_REASONS; the message holds the code and
    at most a closed file name, never test content (R81)."""

    def __init__(self, code, detail=''):
        if code not in READ_PLAN_REASONS:
            raise ValueError('Unregistered read-plan code')
        super().__init__(code, detail)
        self.code, self.detail = code, detail

    def __str__(self):
        return self.code + (': ' + str(self.detail) if self.detail else '')


class WriteOnceMismatch(ValueError):
    """``write_once`` found other bytes under the name (R80); the caller maps it to its own reason: read_plan_failed
    in the pass, read_plan_changed for a bound plan, read_alias_invalid for an alias, solver_settings_changed."""

    def __init__(self, name):
        super().__init__(name)
        self.name = name

    def __str__(self):
        return 'write_once: other bytes already stored under ' + str(self.name)


class OpenRecordViolation(ValueError):
    """An open record holds something other than hashes and counts; ``codes`` are OPEN_RECORD_VIOLATIONS only."""

    def __init__(self, codes):
        codes = tuple(codes)
        super().__init__(codes)
        self.codes = codes

    def __str__(self):
        return 'open record violations: ' + ', '.join(self.codes)


# What a check of untrusted data can raise: a broken rule or unreadable text (ValueError, which includes
# UnicodeError and JSONDecodeError), a value of another type or shape (TypeError, KeyError, AttributeError) and a
# value nested too deeply to walk or hash (RecursionError). Every reader maps these to its fixed code.
UNREADABLE = (ValueError, TypeError, KeyError, AttributeError, RecursionError)


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def is_hash(value):
    return isinstance(value, str) and HEX64.fullmatch(value) is not None


def is_reason(value):
    """A member of READ_PLAN_REASONS, or the composite replay detail ``replay_error:<code>`` (R76)."""
    if not isinstance(value, str):
        return False
    if value in READ_PLAN_REASONS:
        return True
    head, sep, code = value.partition(':')
    return sep == ':' and head == 'replay_error' and (code in READ_PLAN_REASONS or EXIT_CODE.fullmatch(code) is not None)


def replay_error_detail(code):
    """``replay_error:<code>`` for a fixed code (R47b), ``timeout`` or ``exit_<n>`` (R76)."""
    detail = 'replay_error:' + str(code)
    _require(is_reason(detail) and detail not in READ_PLAN_REASONS, 'A fixed replay error code: ' + repr(code))
    return detail


def _is_count(value, upper=None):
    return type(value) is int and value >= 0 and (upper is None or value <= upper)


# ---- events, units, paths ------------------------------------------------------------------------------------
def arm_of(event):
    """The mount arm of a read event (equal to ``reads.arm_of``): C0, C, else F."""
    _require(event in EVENTS, 'A registered read event: ' + repr(event))
    return ARM_OF_EVENT.get(event, 'F')


def step_of(event):
    """The frozen state an event mounts: s0 for C0 and C (R27), s<k> for S<k>."""
    _require(event in EVENTS, 'A registered read event: ' + repr(event))
    return STEP_OF_EVENT[event]


def read_unit_name(event, bench, *, smoke):
    """The read unit of a pair (equal to ``reads.unit_name``): test-read-<event>-<bench>, smoke practice-read-..."""
    _require(event in EVENTS and bench in ORDER, 'A registered read event and bench')
    _require(type(smoke) is bool, 'smoke is a flag')
    return ('practice-read-' if smoke else 'test-read-') + event + '-' + bench


def inputs_name(bench):
    _require(bench in ORDER, 'A registered bench: ' + repr(bench))
    return 'inputs-' + bench + '.json'


def identities_name(bench):
    _require(bench in ORDER, 'A registered bench: ' + repr(bench))
    return 'identities-' + bench + '.json'


def alias_name(event, bench):
    _require(event in EVENTS and bench in ORDER, 'A registered read event and bench')
    return event + '-' + bench + '.json'


def plan_path(root, chain):
    _require(chain in CHAINS, 'A registered chain: ' + repr(chain))
    return Path(root) / chain / PLAN_FILE


def sealed_dir(root, chain, *, smoke):
    _require(chain in CHAINS and type(smoke) is bool, 'A registered chain and a smoke flag')
    return Path(root) / chain / (SMOKE_SEALED_DIR if smoke else SEALED_DIR)


def inputs_path(root, chain, bench, *, smoke):
    return sealed_dir(root, chain, smoke=smoke) / inputs_name(bench)


def identities_path(root, chain, bench, *, smoke):
    return sealed_dir(root, chain, smoke=smoke) / identities_name(bench)


def alias_path(root, chain, event, bench):
    _require(chain in CHAINS, 'A registered chain: ' + repr(chain))
    return Path(root) / chain / ALIAS_DIR / alias_name(event, bench)


def archived_alias_path(root, chain, event, bench, number):
    _require(chain in CHAINS and type(number) is int and number >= 1, 'A registered chain and an archive number')
    return Path(root) / chain / ALIAS_DIR / ARCHIVE_DIR / ('%s-%s-%d.json' % (event, bench, number))


def record_kind(name):
    """'plan' | 'inputs' | 'identities' | 'alias' for the closed names of R80, else None (a ``.part`` file, ...)."""
    if name == PLAN_FILE:
        return 'plan'
    for bench in ORDER:
        if name == inputs_name(bench):
            return 'inputs'
        if name == identities_name(bench):
            return 'identities'
        for event in EVENTS:
            if name == alias_name(event, bench):
                return 'alias'
    return None


def record_names(directory, *, allow_sealed=False):
    """The closed record names present in a directory (regular files only); every other name is ignored (R80)."""
    folder = checked_path(directory, allow_sealed=allow_sealed)
    if not folder.is_dir():
        return []
    return sorted(entry.name for entry in folder.iterdir()
                  if record_kind(entry.name) is not None and entry.is_file() and not entry.is_symlink())


def remove_part_files(directory, *, allow_sealed=False):
    """Remove the temporary ``.part`` files a killed ``write_once`` left (R80); returns their number."""
    folder = checked_path(directory, allow_sealed=allow_sealed)
    if not folder.is_dir():
        return 0
    removed = 0
    for entry in sorted(folder.iterdir()):
        if PART_NAME.fullmatch(entry.name) and entry.is_file() and not entry.is_symlink():
            entry.unlink()
            removed += 1
    return removed


# ---- canonical bytes, self-hash, write_once ------------------------------------------------------------------
def canonical_text(value):
    """The one byte form of every record of this area: sorted keys, indent 1, UTF-8, no NaN, trailing newline."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=1, allow_nan=False) + '\n'


def canonical_bytes(value):
    return canonical_text(value).encode('utf-8')


def bytes_sha256(data):
    return hashlib.sha256(bytes(data)).hexdigest()


def file_sha256(record):
    """The sha256 of the bytes ``write_once`` stores for a record (the plan binds sealed files by this, R32 c)."""
    return bytes_sha256(canonical_bytes(record))


def _plain(value):
    """JSON data as a reader gets it back (lists, never tuples): built and loaded records compare equal."""
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False))


def _with_hash(record, key):
    body = _plain({k: v for k, v in record.items() if k != key})
    body[key] = canonical_sha256(body)
    return body


def _hash_valid(record, key):
    return isinstance(record, dict) and is_hash(record.get(key)) and \
        canonical_sha256({k: v for k, v in record.items() if k != key}) == record[key]


def _strict_loads(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result

    def constant(_name):
        raise ValueError('Non-finite JSON number')
    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


def record_from_bytes(data, *, code):
    """A record from stored bytes, or ReadPlanError(code): the bytes must parse strictly (no duplicate key, no NaN)
    and be exactly the canonical bytes of what they hold, so that no byte can change without detection. Bytes that
    parse but cannot be written back (an out-of-range number, a lone surrogate) or nest too deeply are unreadable."""
    if not isinstance(data, (bytes, bytearray)):
        raise ReadPlanError(code, 'bytes expected')
    try:
        value = _strict_loads(bytes(data).decode('utf-8'))
        canonical = isinstance(value, dict) and canonical_bytes(value) == bytes(data)
    except UNREADABLE:
        raise ReadPlanError(code, 'unreadable') from None
    if not canonical:
        raise ReadPlanError(code, 'not canonical')
    return value


def _fsync_directory(directory):
    try:
        handle = os.open(str(directory), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(handle)
    except OSError:
        pass
    finally:
        os.close(handle)


def write_once(path, record, *, allow_sealed=False):
    """R80. Write the canonical bytes of ``record`` exactly once: a temporary ``.<name>.<pid>.<16 hex>.part`` in the
    same directory, fsync, ``os.link`` to the name, unlink the temporary file. Equal bytes already stored: accepted.
    Other bytes: ``WriteOnceMismatch``. Returns the sha256 of the stored bytes. A kill leaves at most a ``.part``
    file, which no reader of the closed names reads (``record_names``) and ``remove_part_files`` removes."""
    target = checked_path(path, allow_sealed=allow_sealed)
    _require(target.name.endswith('.json') and not target.name.startswith('.'),
             'A write-once record is a visible .json file')
    data = canonical_bytes(record)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.parent / ('.%s.%d.%s.part' % (target.name, os.getpid(), secrets.token_hex(8)))
    try:
        with open(temporary, 'xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            if target.read_bytes() != data:
                raise WriteOnceMismatch(target.name) from None
            return bytes_sha256(data)
        _fsync_directory(target.parent)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return bytes_sha256(data)


def read_bytes(path, *, allow_sealed=False):
    return checked_path(path, allow_sealed=allow_sealed).read_bytes()


# ---- hashes of R10 -------------------------------------------------------------------------------------------
def public_sha256(public):
    """R10 row 2: ``canonical_sha256(item['public'])`` (the cell row's ``public_hash``)."""
    return canonical_sha256(public)


def view_sha256(view):
    """R10 row 3: ``canonical_sha256(view)``."""
    return canonical_sha256(view)


def item_set_sha256(bench, item_ids):
    """The panel's item set, ids hashed: ``canonical_sha256({'v', 'bench', 'items': [sha256_text(id), ...]})``."""
    ids = _checked_item_ids(item_ids)
    return canonical_sha256({'v': IDENTITY_VERSION, 'bench': bench, 'items': [sha256_text(i) for i in ids]})


def run_constants_sha256(bench, *, runtime, worker_options, nominal_tokens, machinery):
    """R10 row 7: the run constants per (chain, bench) over named keys (bench runtime from the manifest, the
    services' worker options, ``nominal_tokens(bench)``, MACHINERY, IDENTITY_VERSION)."""
    _require(bench in ORDER, 'A registered bench: ' + repr(bench))
    _require(isinstance(runtime, dict) and isinstance(worker_options, dict), 'runtime and worker options are mappings')
    _require(nominal_tokens is None or _is_count(nominal_tokens), 'nominal tokens: None or a count')
    _require(isinstance(machinery, str) and machinery, 'A machinery name')
    return canonical_sha256({'bench': bench, 'runtime': runtime, 'worker_options': worker_options,
                             'nominal_tokens': nominal_tokens, 'machinery': machinery,
                             'identity_version': IDENTITY_VERSION})


def registry_sha256(entry):
    """R32 c: the panel registry entry without ``run`` (the manifest hash, different for every root)."""
    _require(isinstance(entry, dict), 'A registry entry is a mapping')
    return canonical_sha256({k: v for k, v in entry.items() if k != 'run'})


# ---- capture (R17, R19) --------------------------------------------------------------------------------------
def capture_selector(system, user):
    """The selector handed to the real ``mount.mount`` in the pass: no client, no recorder, no ledger. ``_select``
    calls it at most twice (request and format retry); ``attempts[0]`` is the first selection request hash."""
    return {'ok': False, 'error_type': SELECTION_CAPTURE_ERROR, 'usage': {}}


CAPTURE_RECEIPT = {'ok': False, 'response': None, 'finish_reason': None, 'usage': {},
                   'error_type': SELECTION_CAPTURE_ERROR}


class CaptureCall:
    """The call object handed to the solve function for the first-request capture (R19): it records
    ``sha256_text(system NUL user)`` of the first send only (as ``units.CallRecorder`` hashes it), answers every send
    with a fixed non-ok receipt, charges nothing and never reports an infrastructure unknown."""

    def __init__(self):
        self.sends = []

    def __call__(self, system, user):
        if type(system) is not str or type(user) is not str:
            raise TypeError('A captured request is text')
        digest = sha256_text(system + '\x00' + user) if not self.sends else None
        self.sends.append({'request_sha256': digest, 'receipt': None})
        return deepcopy(CAPTURE_RECEIPT)

    def tokens(self):
        return 0

    def infrastructure_unknown(self):
        return False

    def first_request(self):
        """The first request hash when exactly one send was recorded, else None (the event becomes capture_failed)."""
        return self.sends[0]['request_sha256'] if len(self.sends) == 1 else None


# ---- per-item identity (R9, R12, R16) ------------------------------------------------------------------------
def selection_sha256(mounted):
    """R16, ADV9: None when the record's ``selection`` is None (C0, C, unknown type) or its ``attempts`` is empty
    (``not_needed``); else ``attempts[0]``, the first selection request."""
    selection = mounted.get('selection') if isinstance(mounted, dict) else None
    if selection is None:
        return None
    if not isinstance(selection, dict) or not isinstance(selection.get('attempts'), list):
        raise ReadPlanError('identity_exception', 'selection record')
    attempts = selection['attempts']
    if not attempts:
        return None
    if not is_hash(attempts[0]):
        raise ReadPlanError('identity_exception', 'selection attempt')
    return attempts[0]


def _optional_text(value):
    return value is None or isinstance(value, str)


def item_components(identity, mounted, *, arm, public_sha256, view_sha256):
    """The components of one item under one event (R16) from (i) the ``mount_identity`` output
    ``{system_card_sha256, programs_offered: [[skill_id, sha256], ...], forced}`` and (ii) the capture-mounted record
    of the real ``mount.mount``. ``arm``: the event's read arm, ``arm_of(event)``. Self-check: (ii) was mounted with
    that arm (its ``arm`` field), (i) and (ii) agree on the system hash and the offered ids, and a selection request
    exists iff programs are offered, else ``ReadPlanError('identity_disagreement')`` (K-A: a record mounted through
    another arm must never give the event an identity). A malformed input, an ``arm`` that is not a read arm or a
    ``forced`` program (a candidate arm never occurs in a read, R11): ``ReadPlanError('identity_exception')``. Text
    fields of (ii) (``card_text``, ``system_card``, ``raw_excerpt``, ``failure``) are never taken."""
    if arm not in READ_MOUNT_ARMS:
        raise ReadPlanError('identity_exception', 'read arm')
    if not isinstance(identity, dict) or not isinstance(mounted, dict):
        raise ReadPlanError('identity_exception', 'identity or mount record missing')
    system, offered = identity.get('system_card_sha256'), identity.get('programs_offered')
    if 'forced' not in identity or identity['forced'] is not None:
        raise ReadPlanError('identity_exception', 'forced program in a read')
    if not is_hash(system) or not isinstance(offered, (list, tuple)) or not all(
            isinstance(pair, (list, tuple)) and len(pair) == 2 and isinstance(pair[0], str) and pair[0]
            and is_hash(pair[1]) for pair in offered):
        raise ReadPlanError('identity_exception', 'mount identity')
    if not is_hash(public_sha256) or not is_hash(view_sha256):
        raise ReadPlanError('identity_exception', 'public or view hash')
    mounted_offered = mounted.get('programs_offered')
    if not isinstance(mounted_offered, list) or not all(isinstance(sid, str) for sid in mounted_offered) \
            or not all(_optional_text(mounted.get(key)) for key in ('type', 'source', 'unknown_reason', 'card_skill')):
        raise ReadPlanError('identity_exception', 'mount record')
    offered_ids = [pair[0] for pair in offered]
    selection = selection_sha256(mounted)
    if mounted.get('arm') != arm:
        raise ReadPlanError('identity_disagreement', 'arm')
    if mounted.get('system_card_sha256') != system or mounted_offered != offered_ids \
            or bool(offered_ids) != (selection is not None):
        raise ReadPlanError('identity_disagreement')
    return {'public_sha256': public_sha256, 'view_sha256': view_sha256, 'system_sha256': system,
            'selection_sha256': selection, 'programs': [pair[1] for pair in offered], 'type': mounted.get('type'),
            'source': mounted.get('source'), 'unknown_reason': mounted.get('unknown_reason'),
            'card_skill': mounted.get('card_skill'), 'offered': offered_ids}


def _components_ok(components):
    return (isinstance(components, dict) and set(components) == set(COMPONENT_KEYS)
            and all(is_hash(components[key]) for key in ('public_sha256', 'view_sha256', 'system_sha256'))
            and (components['selection_sha256'] is None or is_hash(components['selection_sha256']))
            and isinstance(components['programs'], list) and all(is_hash(h) for h in components['programs'])
            and isinstance(components['offered'], list) and len(components['offered']) == len(components['programs'])
            and all(isinstance(sid, str) and sid for sid in components['offered'])
            and bool(components['programs']) == (components['selection_sha256'] is not None)
            and all(_optional_text(components[key]) for key in ('type', 'source', 'unknown_reason', 'card_skill')))


def item_identity(bench, components):
    """R9: ``canonical_sha256({'v', 'bench', 'public_sha256', 'view_sha256', 'system_sha256', 'programs',
    'selection_sha256'})``. Not hashed (RP8, R12, R14): type id, source, unknown reason, card skill id, offered ids."""
    _require(bench in ORDER, 'A registered bench: ' + repr(bench))
    _require(_components_ok(components), 'Item components of R16')
    return canonical_sha256({'v': IDENTITY_VERSION, 'bench': bench, 'public_sha256': components['public_sha256'],
                             'view_sha256': components['view_sha256'], 'system_sha256': components['system_sha256'],
                             'programs': list(components['programs']),
                             'selection_sha256': components['selection_sha256']})


def first_request_required(bench, components):
    """RP3, R19: a first-request hash is mandatory for every item without offered programs on SearchQA, OfficeQA,
    ZebraLogic and SpreadsheetBench, for every event; never on ALFWorld or for an item with offered programs."""
    _require(bench in ORDER, 'A registered bench: ' + repr(bench))
    return bench in FIRST_REQUEST_BENCHES and not components.get('programs')


def item_record(bench, components, *, first_request=None):
    """``{'identity', 'first_request', 'components'}`` of one item under one event. ``first_request``: the capture's
    hash (``CaptureCall.first_request()``) or None; whether it follows RP3 is decided per event (``event_entry``)."""
    _require(first_request is None or is_hash(first_request), 'A first-request hash or None')
    components = _plain(components)
    return {'identity': item_identity(bench, components), 'first_request': first_request, 'components': components}


def _record_ok(bench, record):
    return (isinstance(record, dict) and set(record) == set(RECORD_KEYS) and _components_ok(record['components'])
            and (record['first_request'] is None or is_hash(record['first_request']))
            and is_hash(record['identity']) and record['identity'] == item_identity(bench, record['components']))


def _valid_records(bench, records, count):
    """The records as plain data when every one is readable and consistent, else None (an unreadable identity)."""
    if not isinstance(records, (list, tuple)) or len(records) != count:
        return None
    try:
        records = [_plain(r) for r in records]
        return records if all(_record_ok(bench, r) for r in records) else None
    except UNREADABLE:
        return None


def _first_requests_follow_rule(bench, records):
    return all((r['first_request'] is not None) == first_request_required(bench, r['components']) for r in records)


# ---- lists, events, classes (R28 to R31) ---------------------------------------------------------------------
def _checked_item_ids(item_ids):
    _require(isinstance(item_ids, (list, tuple)) and item_ids, 'A panel has items (an empty panel is refused)')
    _require(all(isinstance(i, str) and i for i in item_ids), 'Item ids are nonempty text')
    _require(list(item_ids) == sorted(set(item_ids)), 'Item ids sorted and unique, as a read unit orders them')
    return list(item_ids)


def identity_list_sha256(bench, item_ids, identities):
    """R28: ``canonical_sha256({'v', 'bench', 'rows': [[sha256_text(item_id), identity], ...]})`` in sorted id
    order; None when any identity is missing (such an event cannot be in a class with another)."""
    ids = _checked_item_ids(item_ids)
    if not isinstance(identities, (list, tuple)) or len(identities) != len(ids) \
            or not all(is_hash(h) for h in identities):
        return None
    return canonical_sha256({'v': IDENTITY_VERSION, 'bench': bench,
                             'rows': [[sha256_text(i), h] for i, h in zip(ids, identities)]})


def first_request_list_sha256(bench, item_ids, first_requests):
    """R28: the same form over ``[[sha256_text(item_id), hash or None], ...]``; null for ALFWorld (and when the list
    itself is missing)."""
    ids = _checked_item_ids(item_ids)
    if bench == NO_CAPTURE_BENCH or not isinstance(first_requests, (list, tuple)) or len(first_requests) != len(ids) \
            or not all(h is None or is_hash(h) for h in first_requests):
        return None
    return canonical_sha256({'v': IDENTITY_VERSION, 'bench': bench,
                             'rows': [[sha256_text(i), h] for i, h in zip(ids, first_requests)]})


def _read_mount_ok(value):
    return (isinstance(value, dict) and set(value) == set(READ_MOUNT_KEYS) and _is_count(value['step'])
            and is_hash(value['library_file_sha256']) and is_hash(value['typemap_file_sha256']))


def _read_mount(value):
    """(step, library file hash, type map file hash) of an entry, a frozen receipt entry or a ``read_mounts`` entry."""
    return tuple(value[key] for key in READ_MOUNT_KEYS)


def entry_mounted_from(entry, frozen_entry):
    """K-A: the entry's identities were computed from the frozen state the plan binds for its event (``frozen_entry``
    is the plan's ``frozen[event]``): equal step and equal library and type map file hashes."""
    return _read_mount(entry) == _read_mount(frozen_entry)


def _fallback_entry(event, reason, frozen_entry):
    """A fallback without identities, named after the frozen state the plan binds for the event (its read mounts it);
    it holds no identity, so nothing was computed under that name."""
    return {'arm': arm_of(event), **{key: frozen_entry[key] for key in READ_MOUNT_KEYS}, 'status': 'fallback',
            'reason': reason, 'identity': None, 'first_request': None, 'components': None, 'descriptive_flips': 0}


def event_entry(bench, event, item_ids, records, *, read_mount, second=None, reason=None):
    """The sealed entry of one (event, bench) (3.3): ``{arm, step, library_file_sha256, typemap_file_sha256, status,
    reason, identity, first_request, components, descriptive_flips}``. ``records``: per item (sorted id order) the
    ``item_record`` of the event, or None where the identity is missing. ``read_mount``: ``{step,
    library_file_sha256, typemap_file_sha256}`` of the frozen state the records were computed from, i.e. of the
    library and type map files actually loaded for this event (``load_frozen``), never a copy of the plan header;
    ``identities_record`` binds it to the plan's ``frozen[event]``. ``second``: S events only, the item records of
    the second embedder run (R30). ``reason``: a fallback the caller determined (``identity_exception`` after a
    non-stop exception of an identity call, ``identity_disagreement``, ...). Status ``fallback`` with the first
    applicable reason of: the given one; ``identity_exception`` (a missing or unreadable record); ``capture_failed``
    (a first-request hash missing where RP3 requires it, or present where it may not be); ``embedder_unstable`` (no
    second run, or another identity list from it). Lists are kept for a fallback whenever they are complete
    (diagnostics, S3 c)."""
    _require(bench in ORDER and event in EVENTS, 'A registered bench and event')
    ids = _checked_item_ids(item_ids)
    _require(reason is None or reason in PASS_FALLBACK_REASONS, 'A fallback reason of R31: ' + repr(reason))
    _require(second is None or event in S_EVENTS, 'Only S events have a second embedder run (R30)')
    _require(_read_mount_ok(read_mount), 'read_mount: {step, library_file_sha256, typemap_file_sha256} of the '
                                         'frozen state the records were computed from')
    entry = {'arm': arm_of(event), **{key: read_mount[key] for key in READ_MOUNT_KEYS}, 'status': 'ok',
             'reason': None, 'identity': None, 'first_request': None, 'components': None, 'descriptive_flips': 0}
    found = reason
    first = _valid_records(bench, records, len(ids))
    if first is None:
        found = found or 'identity_exception'
    else:
        entry['identity'] = [r['identity'] for r in first]
        entry['components'] = [r['components'] for r in first]
        if bench != NO_CAPTURE_BENCH:
            entry['first_request'] = [r['first_request'] for r in first]
        if not _first_requests_follow_rule(bench, first):
            found = found or 'capture_failed'
        if event in S_EVENTS:
            again = _valid_records(bench, second, len(ids)) if second is not None else None
            if second is None:
                found = found or 'embedder_unstable'
            elif again is None:
                found = found or 'identity_exception'
            else:
                entry['descriptive_flips'] = sum(
                    1 for a, b in zip(first, again) if a['identity'] == b['identity']
                    and any(a['components'][k] != b['components'][k] for k in DESCRIPTIVE_KEYS))
                if [r['identity'] for r in again] != entry['identity']:
                    found = found or 'embedder_unstable'
    if found:
        entry['status'], entry['reason'] = 'fallback', found
    return _plain(entry)


def _check_entry(bench, event, count, entry, *, views=None):
    """Raises ValueError unless ``entry`` is a consistent sealed entry of (event, bench) for ``count`` items whose
    components carry the stored view hashes (``views``, from the inputs record) when given. Which frozen state the
    entry names is checked against the plan's ``frozen`` by the callers (``entry_mounted_from``)."""
    _require(isinstance(entry, dict) and set(entry) == set(ENTRY_KEYS), 'entry keys')
    _require(entry['arm'] == arm_of(event) and _read_mount_ok({key: entry[key] for key in READ_MOUNT_KEYS}),
             'entry arm and read mount')
    _require(entry['status'] in STATUSES, 'entry status')
    _require((entry['reason'] is None) == (entry['status'] == 'ok'), 'a reason iff fallback')
    _require(entry['reason'] is None or entry['reason'] in PASS_FALLBACK_REASONS, 'entry reason')
    _require(_is_count(entry['descriptive_flips'], count), 'descriptive flips')
    identity, components, firsts = entry['identity'], entry['components'], entry['first_request']
    _require((identity is None) == (components is None), 'identity and components go together')
    if identity is None:
        _require(firsts is None and entry['status'] == 'fallback', 'an entry without identities is a fallback')
        return
    _require(isinstance(identity, list) and len(identity) == count and isinstance(components, list)
             and len(components) == count, 'aligned lists')
    records = [{'identity': h, 'first_request': None, 'components': c} for h, c in zip(identity, components)]
    _require(all(_record_ok(bench, r) for r in records), 'identities recompute from their components')
    _require(views is None or [c['view_sha256'] for c in components] == list(views), 'components use the stored views')
    if bench == NO_CAPTURE_BENCH:
        _require(firsts is None, 'no first requests on ALFWorld')
    else:
        _require(isinstance(firsts, list) and len(firsts) == count and all(h is None or is_hash(h) for h in firsts),
                 'first-request list')
        for record, first in zip(records, firsts):
            record['first_request'] = first
    if entry['status'] == 'ok':
        _require(_first_requests_follow_rule(bench, records), 'an ok entry follows RP3')


def event_summary(bench, item_ids, entry):
    """The open per-event values of the plan (3.2): arm, status, reason, both list hashes and panel-level counts."""
    comps = entry['components'] or []
    firsts = entry['first_request'] or []
    return {'arm': entry['arm'], 'status': entry['status'], 'reason': entry['reason'],
            'identity_list_sha256': identity_list_sha256(bench, item_ids, entry['identity']),
            'first_request_list_sha256': first_request_list_sha256(bench, item_ids, entry['first_request']),
            'captured': sum(1 for h in firsts if h is not None),
            'typed': sum(1 for c in comps if c['type'] is not None),
            'unknown': sum(1 for c in comps if c['type'] is None and c['unknown_reason'] is not None),
            'with_card': sum(1 for c in comps if c['card_skill'] is not None),
            'with_programs': sum(1 for c in comps if c['programs'])}


def _summary_fields(bench, summary):
    """(status, reason, identity list hash, first-request list hash); anything unreadable is a fallback
    ``identity_exception`` without hashes (D10 f: a missing or unreadable identity is its own class)."""
    unreadable = ('fallback', 'identity_exception', None, None)
    if not isinstance(summary, dict):
        return unreadable
    status, reason = summary.get('status'), summary.get('reason')
    ils, frs = summary.get('identity_list_sha256'), summary.get('first_request_list_sha256')
    if (ils is not None and not is_hash(ils)) or (frs is not None and not is_hash(frs)):
        return unreadable
    if status == 'fallback' and reason in FALLBACK_REASONS:
        return status, reason, ils, frs
    if status == 'ok' and reason is None and ils is not None \
            and (frs is None) == (bench == NO_CAPTURE_BENCH):
        return status, reason, ils, frs
    return unreadable


def compute_classes(bench, summaries):
    """R29 to R31 for one bench. ``summaries``: {event: {status, reason, identity_list_sha256,
    first_request_list_sha256, ...}}; a missing or unreadable one is a fallback ``identity_exception``.
    Two events share a class iff both are ``ok``, their identity list hashes are equal and their first-request list
    hashes are equal wherever both are non-null; two ok events that fail only the last condition both become
    ``first_request_mismatch``. Every fallback is a class of its own. The representative is the latest member in
    the order C0, C, S1..S5. Returns ``(final, classes)``: final = {event: {'status', 'reason'}}, classes ordered by
    their first member, ids from 1. Idempotent: the final statuses give the same classes again."""
    _require(bench in ORDER, 'A registered bench: ' + repr(bench))
    final, hashes = {}, {}
    for event in EVENTS:
        status, reason, ils, frs = _summary_fields(bench, summaries.get(event) if isinstance(summaries, dict) else None)
        final[event], hashes[event] = {'status': status, 'reason': reason}, (ils, frs)
    groups = {}
    for event in EVENTS:
        if final[event]['status'] == 'ok':
            groups.setdefault(hashes[event][0], []).append(event)
    for members in groups.values():
        if len({hashes[e][1] for e in members if hashes[e][1] is not None}) > 1:
            for event in members:
                if hashes[event][1] is not None:
                    final[event] = {'status': 'fallback', 'reason': 'first_request_mismatch'}
    blocks, groups = [], {}
    for event in EVENTS:
        if final[event]['status'] == 'ok':
            groups.setdefault(hashes[event][0], []).append(event)
        else:
            blocks.append([event])
    blocks.extend(groups.values())
    blocks.sort(key=lambda members: EVENTS.index(members[0]))
    classes = []
    for number, members in enumerate(blocks, 1):
        representative = members[-1]
        classes.append({'id': number, 'members': list(members), 'representative': representative,
                        'identity_list_sha256': hashes[representative][0],
                        'first_request_list_sha256': hashes[representative][1]})
    return final, classes


def first_sweep(order, classes_by_bench):
    """R36 first sweep: for event S5..C0, the benches (chain order) where the event represents a class."""
    sweep = []
    for event in reversed(EVENTS):
        benches = [b for b in order if any(c['representative'] == event for c in classes_by_bench[b])]
        if benches:
            sweep.append([event, benches])
    return sweep


# ---- sealed inputs and identities (R78, 3.3) -----------------------------------------------------------------
def _vectors_ok(vectors, count):
    if vectors is None:
        return True
    if not isinstance(vectors, list) or len(vectors) != 2:
        return False
    dims = set()
    for run in vectors:
        if not isinstance(run, list) or len(run) != count:
            return False
        for vector in run:
            if not isinstance(vector, list) or not vector or not all(
                    isinstance(x, (int, float)) and not isinstance(x, bool) and x == x and abs(x) != float('inf')
                    for x in vector):
                return False
            dims.add(len(vector))
    return len(dims) == 1


def _views_sha256(view_hashes, alfworld_views):
    return canonical_sha256({'view_sha256': view_hashes, 'alfworld_views': alfworld_views})


def _check_inputs(record, *, chain=None, bench=None):
    _require(isinstance(record, dict) and set(record) == set(INPUTS_KEYS), 'inputs keys')
    _require(record['version'] == INPUTS_VERSION, 'inputs version')
    _require(record['chain'] in CHAINS and record['bench'] in ORDER, 'inputs chain and bench')
    _require(chain is None or record['chain'] == chain, 'inputs of another chain')
    _require(bench is None or record['bench'] == bench, 'inputs of another bench')
    ids = _checked_item_ids(record['item_ids'])
    views = record['view_sha256']
    _require(isinstance(views, list) and len(views) == len(ids) and all(is_hash(h) for h in views), 'view hashes')
    found = record['alfworld_views']
    if record['bench'] == NO_CAPTURE_BENCH:
        _require(isinstance(found, list) and len(found) == len(ids) and all(isinstance(v, dict) for v in found)
                 and [canonical_sha256(v) for v in found] == views, 'ALFWorld views stored and hashed')
    else:
        _require(found is None, 'stored views on ALFWorld only (other views are recomputed, R78)')
    _require(_vectors_ok(record['vectors'], len(ids)), 'two embedder runs of aligned finite vectors, or null')
    _require(record['views_sha256'] == _views_sha256(views, found), 'views hash')
    _require(record['vectors_sha256'] == canonical_sha256(record['vectors']), 'vectors hash')
    _require(_hash_valid(record, 'record_sha256'), 'inputs self-hash')


def inputs_record(chain, bench, item_ids, view_hashes, *, alfworld_views=None, vectors=None):
    """The sealed ``inputs-<bench>.json`` (R78, 3.3), written before any identity is computed: sorted item ids, one
    view hash per item, the ALFWorld views (ALFWorld only), both embedder runs (R30) or null, ``views_sha256``,
    ``vectors_sha256``, ``record_sha256``. A replay loads the ALFWorld views and both vector runs from it and
    recomputes every other view (``check_views``)."""
    _require(isinstance(item_ids, (list, tuple)) and isinstance(view_hashes, (list, tuple)), 'id and view lists')
    record = _with_hash({'version': INPUTS_VERSION, 'chain': chain, 'bench': bench, 'item_ids': list(item_ids),
                         'view_sha256': list(view_hashes), 'alfworld_views': alfworld_views, 'vectors': vectors,
                         'views_sha256': _views_sha256(list(view_hashes), _plain(alfworld_views)),
                         'vectors_sha256': canonical_sha256(_plain(vectors))}, 'record_sha256')
    _check_inputs(record, chain=chain, bench=bench)
    return record


def verify_inputs(record, *, chain=None, bench=None):
    """A stored inputs record, or ``ReadPlanError('inputs_mismatch')`` (R33 c)."""
    try:
        _check_inputs(record, chain=chain, bench=bench)
    except UNREADABLE:
        raise ReadPlanError('inputs_mismatch') from None
    return record


def check_views(inputs, recomputed):
    """R78: the non-ALFWorld views recomputed from the re-opened items must hash as stored, else
    ``ReadPlanError('view_mismatch')`` (read_plan_failed on a pass re-run, ``different`` in a replay)."""
    verify_inputs(inputs)
    if list(recomputed) != list(inputs['view_sha256']):
        raise ReadPlanError('view_mismatch')


def _probe_pair(probe):
    if probe is None:
        return None
    _require(isinstance(probe, (list, tuple)) and len(probe) == 2 and probe[0] in EVENTS and probe[1] in ORDER,
             'read_plan_probe is [event, bench]')
    return list(probe)


def _final_entries(bench, item_ids, entries):
    summaries = {event: event_summary(bench, item_ids, entry) for event, entry in entries.items()}
    final, _classes = compute_classes(bench, summaries)
    return final


def identities_record(chain, bench, inputs, entries, *, frozen, probe=None):
    """The sealed ``identities-<bench>.json`` (3.3) from the bench's inputs record and its seven event entries
    (``event_entry``). ``frozen``: the plan header's frozen receipt entries per event (3.2), checked as in the plan.
    A missing or inconsistent entry becomes a fallback ``identity_exception`` (D10 f); an entry computed from another
    frozen state than ``frozen[event]`` becomes a fallback ``identity_disagreement`` (K-A: an off-by-one state must
    not alias); the smoke probe (R7) turns its pair, if ok, into ``smoke_probe``; R29's first-request condition is
    applied, so every stored status is final. Every stored entry names ``frozen[event]``."""
    inputs = verify_inputs(inputs, chain=chain, bench=bench)
    ids = inputs['item_ids']
    probe = _probe_pair(probe)
    frozen = _plain(frozen)
    _check_frozen(frozen)
    _require(isinstance(entries, dict) and set(entries) <= set(EVENTS), 'entries per registered event')
    checked = {}
    for event in EVENTS:
        bound = frozen[event]
        try:
            entry = _plain(entries.get(event))
            _check_entry(bench, event, len(ids), entry, views=inputs['view_sha256'])
        except UNREADABLE:
            entry = _fallback_entry(event, 'identity_exception', bound)
        if not entry_mounted_from(entry, bound):
            entry = _fallback_entry(event, 'identity_disagreement', bound)
        if probe == [event, bench] and entry['status'] == 'ok':
            entry['status'], entry['reason'] = 'fallback', 'smoke_probe'
        checked[event] = entry
    for event, state in _final_entries(bench, ids, checked).items():
        checked[event]['status'], checked[event]['reason'] = state['status'], state['reason']
    return _with_hash({'version': IDENTITIES_VERSION, 'chain': chain, 'bench': bench, 'item_ids': ids,
                       'inputs_sha256': file_sha256(inputs), 'events': checked}, 'record_sha256')


def _check_identities(record, *, inputs=None, frozen=None, chain=None, bench=None):
    _require(isinstance(record, dict) and set(record) == set(IDENTITIES_KEYS), 'identities keys')
    _require(record['version'] == IDENTITIES_VERSION, 'identities version')
    _require(record['chain'] in CHAINS and record['bench'] in ORDER, 'identities chain and bench')
    _require(chain is None or record['chain'] == chain, 'identities of another chain')
    _require(bench is None or record['bench'] == bench, 'identities of another bench')
    ids = _checked_item_ids(record['item_ids'])
    _require(is_hash(record['inputs_sha256']), 'inputs hash')
    if inputs is not None:
        _require(record['inputs_sha256'] == file_sha256(inputs) and inputs['item_ids'] == ids
                 and inputs['chain'] == record['chain'] and inputs['bench'] == record['bench'], 'identities of these inputs')
    events = record['events']
    _require(isinstance(events, dict) and set(events) == set(EVENTS), 'identities events')
    if frozen is not None:
        _check_frozen(frozen)
    for event in EVENTS:
        _check_entry(record['bench'], event, len(ids), events[event],
                     views=inputs['view_sha256'] if inputs is not None else None)
        _require(events[event]['step'] == step_of(event), 'every entry names the state of its event')
        _require(frozen is None or entry_mounted_from(events[event], frozen[event]),
                 'identities computed from the frozen states of the plan')
    final = _final_entries(record['bench'], ids, events)
    _require(all(final[e] == {'status': events[e]['status'], 'reason': events[e]['reason']} for e in EVENTS),
             'stored statuses are final')
    _require(_hash_valid(record, 'record_sha256'), 'identities self-hash')


def verify_identities(record, *, inputs=None, frozen=None, chain=None, bench=None):
    """A stored identities record, or ``ReadPlanError('sealed_file_mismatch')``. ``inputs``: the bench's inputs
    record it must be bound to (file hash, ids, chain, bench, view hashes); ``frozen``: the plan header's frozen
    entries every stored entry must name (K-A)."""
    try:
        _check_identities(record, inputs=inputs, frozen=frozen, chain=chain, bench=bench)
    except UNREADABLE:
        raise ReadPlanError('sealed_file_mismatch') from None
    return record


def sealed_from_bytes(data, kind, *, file_sha256=None, inputs=None, frozen=None):
    """A sealed record ('inputs' or 'identities') from its stored bytes: canonical, self-hash valid, and equal to the
    bound file hash when given; an identities record also bound to ``inputs`` and ``frozen`` when given
    (``verify_identities``). Errors: ``inputs_mismatch`` / ``sealed_file_mismatch``."""
    _require(kind in ('inputs', 'identities'), 'A sealed record kind')
    code = 'inputs_mismatch' if kind == 'inputs' else 'sealed_file_mismatch'
    if file_sha256 is not None and (not isinstance(data, (bytes, bytearray)) or bytes_sha256(data) != file_sha256):
        raise ReadPlanError(code, 'file hash')
    record = record_from_bytes(data, code=code)
    return verify_inputs(record) if kind == 'inputs' else verify_identities(record, inputs=inputs, frozen=frozen)


def load_sealed(path, kind, *, file_sha256=None, inputs=None, frozen=None):
    return sealed_from_bytes(read_bytes(path, allow_sealed=True), kind, file_sha256=file_sha256, inputs=inputs,
                             frozen=frozen)


# ---- the plan (3.2, R32) -------------------------------------------------------------------------------------
def _check_frozen(frozen):
    _require(isinstance(frozen, dict) and set(frozen) == set(EVENTS), 'a frozen receipt entry per event')
    for event in EVENTS:
        entry = frozen[event]
        _require(isinstance(entry, dict) and set(entry) == set(FROZEN_KEYS), 'frozen entry keys')
        _require(type(entry['step']) is int and entry['step'] == step_of(event), 'frozen step of the event')
        _require(all(is_hash(entry[key]) for key in FROZEN_KEYS if key != 'step'), 'frozen hashes')
    _require(frozen['C0'] == frozen['C'], 'C0 and C read the same s0 state (R27)')


def _check_header(header):
    _require(header['chain'] in CHAINS, 'A registered chain')
    _require(type(header['smoke']) is bool, 'smoke is a flag')
    _require(header['schedule'] == SCHEDULE, 'economy requires learn_first (D9)')
    _require(header['read_plan'] == READ_PLAN, 'a plan exists under read_plan = economy only')
    _require(header['base_card'] in BASE_CARDS, 'base_card is format or historical (D17)')
    _require(is_hash(header['manifest_record_sha256']) and is_hash(header['solver_settings_sha256']),
             'manifest and solver settings hashes')
    order = header['order']
    _require(isinstance(order, list) and len(order) == len(ORDER) and set(order) == set(ORDER),
             'the chain order holds the five benches')
    _check_frozen(header['frozen'])


def _counts(benches):
    fresh = sum(len(entry['classes']) for entry in benches.values())
    fallback = sum(1 for entry in benches.values() for e in entry['events'].values() if e['status'] == 'fallback')
    return {'pairs': PAIRS, 'fresh': fresh, 'alias': PAIRS - fresh, 'fallback': fallback}


def build_plan(*, chain, smoke, schedule, read_plan, base_card, manifest_record_sha256, solver_settings_sha256,
               order, frozen, benches):
    """The open plan ``<chain>/read-plan.json`` (3.2): hashes and counts only, no time stamp, no path, self-hashed
    (``plan_sha256``). ``frozen``: per event the frozen receipt values {step, library_record_sha256,
    typemap_record_sha256, library_file_sha256, typemap_file_sha256, receipt_sha256}. ``benches``: per bench
    {'inputs': inputs record, 'identities': identities record, 'registry_sha256': entry hash without ``run`` (None in
    a smoke), 'run_constants_sha256'}; each identities record must be bound to its inputs and name these frozen
    entries (``verify_identities``, else ``sealed_file_mismatch``). The classes come from the identities' final
    statuses (R29); the read order is R36's first sweep."""
    header = _plain({'chain': chain, 'smoke': smoke, 'schedule': schedule, 'read_plan': read_plan,
                     'base_card': base_card, 'manifest_record_sha256': manifest_record_sha256,
                     'solver_settings_sha256': solver_settings_sha256, 'order': list(order), 'frozen': frozen})
    _check_header(header)
    _require(isinstance(benches, dict) and set(benches) == set(ORDER), 'one entry per bench')
    plan_benches, every_id, probes = {}, [], 0
    for bench in header['order']:
        spec = benches[bench]
        inputs = verify_inputs(_plain(spec['inputs']), chain=chain, bench=bench)
        identities = verify_identities(_plain(spec['identities']), inputs=inputs, frozen=header['frozen'],
                                       chain=chain, bench=bench)
        registry = spec.get('registry_sha256')
        _require((registry is None) if smoke else is_hash(registry), 'registry hash on a real root, null in a smoke')
        _require(is_hash(spec.get('run_constants_sha256')), 'run constants hash')
        ids = inputs['item_ids']
        every_id.extend(ids)
        events = {event: event_summary(bench, ids, identities['events'][event]) for event in EVENTS}
        final, classes = compute_classes(bench, events)
        _require(all(final[e] == {'status': events[e]['status'], 'reason': events[e]['reason']} for e in EVENTS),
                 'identities statuses are final')
        probes += sum(1 for e in EVENTS if events[e]['reason'] == 'smoke_probe')
        plan_benches[bench] = {
            'items': len(ids), 'item_set_sha256': item_set_sha256(bench, ids), 'registry_sha256': registry,
            'run_constants_sha256': spec['run_constants_sha256'], 'inputs_sha256': file_sha256(inputs),
            'identities_sha256': file_sha256(identities),
            'embed': {'runs': len(inputs['vectors']) if inputs['vectors'] is not None else 0,
                      'descriptive_flips': sum(identities['events'][e]['descriptive_flips'] for e in EVENTS)},
            'events': events, 'classes': classes}
    _require(probes == 0 or (smoke and probes == 1), 'a smoke probe only in a smoke, at most one pair (R7)')
    plan = {'version': PLAN_VERSION, 'identity_version': IDENTITY_VERSION, **header, 'events': list(EVENTS),
            'benches': plan_benches, 'read_order': first_sweep(header['order'], {b: e['classes'] for b, e in
                                                                              plan_benches.items()}),
            'counts': _counts(plan_benches)}
    plan = _with_hash(plan, 'plan_sha256')
    check_open_record(plan, item_ids=every_id)
    return plan


def plan_files(*, chain, smoke, schedule, read_plan, base_card, manifest_record_sha256, solver_settings_sha256,
               order, frozen, benches, probe=None):
    """Every record of a plan from its pure inputs: {closed name: record} for ``inputs-<b>``, ``identities-<b>``
    and ``read-plan.json``. ``benches``: per bench {'inputs', 'entries': {event: event_entry(...)},
    'registry_sha256', 'run_constants_sha256'}. The pass writes these (inputs first, plan last); a replay builds
    them from the stored inputs and compares bytes (``replay_compare``)."""
    _require(isinstance(benches, dict) and set(benches) == set(ORDER), 'one entry per bench')
    files, plan_benches = {}, {}
    for bench in ORDER:
        spec = benches[bench]
        inputs = verify_inputs(_plain(spec['inputs']), chain=chain, bench=bench)
        identities = identities_record(chain, bench, inputs, spec['entries'], frozen=frozen, probe=probe)
        files[inputs_name(bench)], files[identities_name(bench)] = inputs, identities
        plan_benches[bench] = {'inputs': inputs, 'identities': identities,
                               'registry_sha256': spec.get('registry_sha256'),
                               'run_constants_sha256': spec.get('run_constants_sha256')}
    files[PLAN_FILE] = build_plan(chain=chain, smoke=smoke, schedule=schedule, read_plan=read_plan,
                                  base_card=base_card, manifest_record_sha256=manifest_record_sha256,
                                  solver_settings_sha256=solver_settings_sha256, order=order, frozen=frozen,
                                  benches=plan_benches)
    return files


def _check_plan(plan):
    _require(isinstance(plan, dict) and set(plan) == set(PLAN_KEYS), 'plan keys')
    _require(_hash_valid(plan, 'plan_sha256'), 'plan self-hash')
    _require(plan['version'] == PLAN_VERSION and plan['identity_version'] == IDENTITY_VERSION, 'plan versions')
    _require(plan['events'] == list(EVENTS), 'plan events')
    _check_header(plan)
    benches = plan['benches']
    _require(isinstance(benches, dict) and set(benches) == set(ORDER), 'plan benches')
    probes = 0
    for bench, entry in benches.items():
        _require(isinstance(entry, dict) and set(entry) == set(BENCH_KEYS), 'bench keys')
        items = entry['items']
        _require(_is_count(items) and items >= 1, 'bench items')
        _require(all(is_hash(entry[k]) for k in ('item_set_sha256', 'run_constants_sha256', 'inputs_sha256',
                                                 'identities_sha256')), 'bench hashes')
        _require((entry['registry_sha256'] is None) if plan['smoke'] else is_hash(entry['registry_sha256']),
                 'registry hash')
        embed = entry['embed']
        _require(isinstance(embed, dict) and set(embed) == {'runs', 'descriptive_flips'}
                 and embed['runs'] in (0, 2) and _is_count(embed['descriptive_flips']), 'embed counts')
        events = entry['events']
        _require(isinstance(events, dict) and set(events) == set(EVENTS), 'bench events')
        for event in EVENTS:
            row = events[event]
            _require(isinstance(row, dict) and set(row) == set(EVENT_KEYS) and row['arm'] == arm_of(event),
                     'event keys and arm')
            _require(all(_is_count(row[k], items) for k in ('captured', 'typed', 'unknown', 'with_card',
                                                            'with_programs')), 'event counts')
            _require(row['reason'] is None or row['reason'] in PASS_FALLBACK_REASONS, 'event reason')
            probes += row['reason'] == 'smoke_probe'
        final, classes = compute_classes(bench, events)
        _require(all(final[e] == {'status': events[e]['status'], 'reason': events[e]['reason']} for e in EVENTS),
                 'event statuses readable and final')
        _require(entry['classes'] == classes, 'classes follow R29 from the event rows')
    _require(probes == 0 or (plan['smoke'] and probes == 1), 'smoke probe')
    _require(plan['read_order'] == first_sweep(plan['order'], {b: e['classes'] for b, e in benches.items()}),
             'read order is R36 first sweep')
    _require(plan['counts'] == _counts(benches), 'plan counts')
    _require(not open_record_violations(plan), 'hashes and counts only')


def verify_plan(plan, *, plan_sha256=None):
    """The plan's self-hash, structure and derived parts (classes, read order, counts) recomputed, or
    ``ReadPlanError('plan_self_check')``; a valid plan whose hash is not the bound one: ``plan_file_mismatch``."""
    try:
        _check_plan(plan)
    except UNREADABLE:
        raise ReadPlanError('plan_self_check') from None
    if plan_sha256 is not None and plan['plan_sha256'] != plan_sha256:
        raise ReadPlanError('plan_file_mismatch', 'other plan')
    return plan


def plan_from_bytes(data, *, file_sha256=None, plan_sha256=None):
    """R44 a: the plan from its bytes: the bound bytes hash (when given), canonical bytes, valid self-hash and
    structure, the bound ``plan_sha256`` (when given). Any changed byte is detected even without a bound hash."""
    if file_sha256 is not None and (not isinstance(data, (bytes, bytearray)) or bytes_sha256(data) != file_sha256):
        raise ReadPlanError('plan_file_mismatch', 'file hash')
    return verify_plan(record_from_bytes(data, code='plan_file_mismatch'), plan_sha256=plan_sha256)


def load_plan(path, *, file_sha256=None, plan_sha256=None):
    return plan_from_bytes(read_bytes(path), file_sha256=file_sha256, plan_sha256=plan_sha256)


def replay_compare(stored, recomputed):
    """R47 core: ``stored`` {closed name: bytes as found, or None when missing}; ``recomputed`` {closed name: record}
    built from the stored inputs. ``equal`` iff the plan file and every other named file are byte-equal; counts
    only. ``reason``: None or ``replay_different``."""
    _require(isinstance(stored, dict) and isinstance(recomputed, dict), 'name maps')
    names = sorted(set(stored) | set(recomputed))
    _require(all(record_kind(name) in ('plan', 'inputs', 'identities') for name in names),
             'plan and sealed names only (R80)')
    equal = different = missing = 0
    for name in names:
        found = stored.get(name)
        if name not in recomputed or found is None:
            missing += 1
        elif bytes(found) == canonical_bytes(recomputed[name]):
            equal += 1
        else:
            different += 1
    verdict = 'equal' if PLAN_FILE in names and not different and not missing else 'different'
    return {'verdict': verdict, 'files': len(names), 'equal': equal, 'different': different, 'missing': missing,
            'reason': None if verdict == 'equal' else 'replay_different'}


def frozen_entry_matches(plan, event, *, step, library_file_sha256, typemap_file_sha256):
    """R39 (2): the event's ``read_mounts`` entry (step and both file hashes) equals the plan's frozen entry."""
    entry = plan['frozen'][event]
    return (entry['step'], entry['library_file_sha256'], entry['typemap_file_sha256']) == \
        (step, library_file_sha256, typemap_file_sha256)


# ---- classes of a bound plan, post-read check, alias records (R39, R41, 3.4) ---------------------------------
def class_of(plan, event, bench):
    for cls in plan['benches'][bench]['classes']:
        if event in cls['members']:
            return cls
    raise ValueError('No class holds the pair')


def members_of(plan, bench, representative):
    """The other members of the class ``representative`` reads for: the pairs R39 settles after its unit."""
    for cls in plan['benches'][bench]['classes']:
        if cls['representative'] == representative:
            return [event for event in cls['members'] if event != representative]
    raise ValueError('Not a representative of this bench')


def alias_pairs(plan):
    """Every (event, bench) the plan settles by an alias record, in chain order, then event order."""
    return [(event, bench) for bench in plan['order'] for cls in plan['benches'][bench]['classes']
            for event in cls['members'] if event != cls['representative']]


def expected_for_check(identities, event):
    """R41: per planned item the hashed values a representative's cell must show (sealed identities file)."""
    entry = identities['events'][event]
    _require(entry['components'] is not None, 'The event has identities')
    firsts = entry['first_request'] or [None] * len(entry['components'])
    return [{'system_sha256': c['system_sha256'], 'selection_sha256': c['selection_sha256'],
             'programs': list(c['programs']), 'public_sha256': c['public_sha256'], 'first_request': first}
            for c, first in zip(entry['components'], firsts)]


def observed_from_row(row, program_sha256_of):
    """R41: the same values from one cell row (real and fake rows): ``mount.system_card_sha256``, ``mount.selection``
    reduced as in R16, ``mount.programs_offered`` mapped to skill sha256 by the event's frozen library,
    ``public_hash`` and ``request_sha256[0]``."""
    mounted = row.get('mount') if isinstance(row, dict) else None
    if not isinstance(mounted, dict):
        return None
    try:
        selection = selection_sha256(mounted)
    except ReadPlanError:
        selection = 'unreadable'
    requests = row.get('request_sha256')
    offered = mounted.get('programs_offered') if isinstance(mounted.get('programs_offered'), list) else []
    programs = []
    for skill_id in offered:
        try:
            programs.append(program_sha256_of(skill_id))
        except (KeyError, ValueError, TypeError):
            programs.append(None)  # a program the frozen library does not hold: never equal to a planned hash
    return {'system_sha256': mounted.get('system_card_sha256'), 'selection_sha256': selection, 'programs': programs,
            'public_sha256': row.get('public_hash'),
            'first_request': requests[0] if isinstance(requests, list) and requests else None}


def post_read_check(expected, observed):
    """R41 counts: ``{'items': n, 'equal': e, 'unequal': u}``; a missing cell (None) is neither. Passed iff u == 0
    and e == n (``check_passed``). The first request is compared where the plan holds one."""
    _require(isinstance(expected, list) and isinstance(observed, list) and len(expected) == len(observed),
             'aligned expected and observed lists')
    equal = unequal = 0
    for want, got in zip(expected, observed):
        if got is None:
            continue
        same = all(want[k] == got.get(k) for k in OBSERVED_KEYS if k != 'first_request') and (
            want['first_request'] is None or want['first_request'] == got.get('first_request'))
        equal, unequal = (equal + 1, unequal) if same else (equal, unequal + 1)
    return {'items': len(expected), 'equal': equal, 'unequal': unequal}


def check_passed(check, items):
    return (isinstance(check, dict) and set(check) == set(CHECK_KEYS) and all(_is_count(check[k]) for k in CHECK_KEYS)
            and check['items'] == items and check['equal'] == items and check['unequal'] == 0)


def build_alias(plan, event, bench, *, check, representative_aggregate_sha256, representative_counts):
    """The alias record ``<chain>/read-alias/<event>-<bench>.json`` (3.4) of an ok member of a class, written after
    the representative's unit passed R41: the representative (event and unit), both list hashes of member and
    representative (the proof, D10 d), the plan hash, the check counts, the representative's aggregate hash and
    its unknown / infrastructure / configuration counts (RP3 2 a), self-hashed. No time stamp, so a re-settling
    writes the same bytes."""
    verify_plan(plan)
    _require(bench in ORDER and event in EVENTS, 'A registered bench and event')
    rows = plan['benches'][bench]['events']
    _require(rows[event]['status'] == 'ok', 'A fallback pair is never an alias')
    representative = class_of(plan, event, bench)['representative']
    _require(representative != event, 'A representative is read fresh, never an alias')
    items = plan['benches'][bench]['items']
    _require(check_passed(check, items), 'The representative passed the post-read check (R41)')
    _require(is_hash(representative_aggregate_sha256), "The representative's aggregate hash")
    _require(isinstance(representative_counts, dict) and set(representative_counts) == set(COUNT_KEYS)
             and all(_is_count(representative_counts[k], items) for k in COUNT_KEYS), "The representative's counts")
    record = _with_hash({
        'version': ALIAS_VERSION, 'chain': plan['chain'], 'event': event, 'bench': bench, 'kind': 'alias',
        'representative': {'event': representative, 'unit': read_unit_name(representative, bench, smoke=plan['smoke'])},
        'items': items,
        'identity_list_sha256': {'member': rows[event]['identity_list_sha256'],
                                 'representative': rows[representative]['identity_list_sha256']},
        'first_request_list_sha256': {'member': rows[event]['first_request_list_sha256'],
                                      'representative': rows[representative]['first_request_list_sha256']},
        'plan_sha256': plan['plan_sha256'], 'check': {k: check[k] for k in CHECK_KEYS},
        'representative_aggregate_sha256': representative_aggregate_sha256,
        'representative_counts': {k: representative_counts[k] for k in COUNT_KEYS}}, 'record_sha256')
    _require(record['identity_list_sha256']['member'] == record['identity_list_sha256']['representative'],
             'equal identity lists')
    check_open_record(record)
    return record


def verify_alias(record, plan, *, representative_aggregate_sha256=None, representative_counts=None):
    """R44 a: an alias record's self-hash, its plan hash, equality with the record rebuilt from the plan, and (when
    given) the representative's current aggregate hash and unknown / infrastructure / configuration counts from its
    mirror (neither can be rebuilt from the plan); else ``ReadPlanError('read_alias_invalid')``."""
    try:
        _require(isinstance(record, dict) and set(record) == set(ALIAS_KEYS), 'alias keys')
        _require(_hash_valid(record, 'record_sha256'), 'alias self-hash')
        _require(record['plan_sha256'] == plan['plan_sha256'], 'alias of another plan')
        rebuilt = build_alias(plan, record['event'], record['bench'], check=record['check'],
                              representative_aggregate_sha256=record['representative_aggregate_sha256'],
                              representative_counts=record['representative_counts'])
        _require(rebuilt == record, 'alias equals the record rebuilt from the plan')
        _require(representative_aggregate_sha256 is None
                 or record['representative_aggregate_sha256'] == representative_aggregate_sha256,
                 "representative's aggregate changed")
        _require(representative_counts is None or record['representative_counts'] == representative_counts,
                 "representative's counts changed")
    except UNREADABLE:
        raise ReadPlanError('read_alias_invalid') from None
    return record


def alias_from_bytes(data, plan, *, representative_aggregate_sha256=None, representative_counts=None):
    """An alias record from its stored bytes (canonical, then ``verify_alias``), else ``read_alias_invalid``."""
    record = record_from_bytes(data, code='read_alias_invalid')
    return verify_alias(record, plan, representative_aggregate_sha256=representative_aggregate_sha256,
                        representative_counts=representative_counts)


def load_alias(path, plan, *, representative_aggregate_sha256=None, representative_counts=None):
    """An alias record from ``<chain>/read-alias/<event>-<bench>.json``; a record stored under another pair's name
    is invalid too."""
    record = alias_from_bytes(read_bytes(path), plan, representative_aggregate_sha256=representative_aggregate_sha256,
                              representative_counts=representative_counts)
    if Path(path).name != alias_name(record['event'], record['bench']):
        raise ReadPlanError('read_alias_invalid', 'name')
    return record


def alias_state_entry(record):
    """R39 (2): ``state['reads'][event][bench]`` of a settled alias."""
    return {'kind': 'alias', 'status': 'alias', 'alias_of': record['representative']['event'],
            'items': record['items'], 'alias_sha256': record['record_sha256']}


# ---- open records: hashes and counts only (R81, 3.8, T23) ----------------------------------------------------
HEX_TEXT = re.compile(r'^[0-9a-f]+$')


def _substring_ids(item_ids):
    """Ids checked as substrings: a short pure-hex id (for example a number) would match inside any hash by chance,
    so it is checked for equality only."""
    return [i for i in item_ids if len(i) >= 16 or HEX_TEXT.fullmatch(i) is None]


def open_record_violations(record, *, item_ids=(), texts=(), allow_floats=False):
    """The violation codes (OPEN_RECORD_VIOLATIONS, distinct, sorted) of an open record: a key that names test
    content, an item id (equal, or inside a string), a planted text, a string over 64 characters, a float (no score),
    a reason outside READ_PLAN_REASONS under a reason key, a verdict outside REPLAY_VERDICTS, a non-JSON value."""
    ids = [str(i) for i in item_ids if str(i)]
    id_set, inner_ids = set(ids), _substring_ids(ids)
    texts = [t for t in texts if isinstance(t, str) and t]
    found = set()

    def text(value):
        if value in id_set or any(i in value for i in inner_ids):
            found.add('item_id')
        if any(t in value for t in texts):
            found.add('planted_text')
        if len(value) > OPEN_TEXT_MAX:
            found.add('long_string')

    def visit(value, key):
        if isinstance(value, dict):
            for name, inner in value.items():
                if not isinstance(name, str):
                    found.add('key_not_text')
                    continue
                if name in FORBIDDEN_OPEN_KEYS:
                    found.add('forbidden_key')
                text(name)
                visit(inner, name)
        elif isinstance(value, (list, tuple)):
            for inner in value:
                visit(inner, key)
        elif isinstance(value, str):
            text(value)
            if key in REASON_KEYS and not is_reason(value):
                found.add('reason_outside_vocabulary')
            if key == 'verdict' and value not in REPLAY_VERDICTS:
                found.add('verdict_outside_vocabulary')
        elif isinstance(value, bool) or value is None or isinstance(value, int):
            return
        elif isinstance(value, float):
            if not allow_floats:
                found.add('float')
        else:
            found.add('value_type')
    visit(record, None)
    return sorted(found)


def check_open_record(record, *, item_ids=(), texts=(), allow_floats=False):
    """``OpenRecordViolation`` unless the record holds hashes, counts and closed words only."""
    codes = open_record_violations(record, item_ids=item_ids, texts=texts, allow_floats=allow_floats)
    if codes:
        raise OpenRecordViolation(codes)
    return record


# =================================================================================================================
# Integration (step rp-int): manifest values, the solver settings record, the pass, the replay, the post-read check.
# Everything below calls the tested core above; it opens panels only through ``reads.open_panel`` (R24), mounts only
# through the injected ``services.identity_fn`` / ``services.mount_fn`` (the real ``mount.mount_identity`` /
# ``mount.mount`` in the run, RP9) and captures first requests only through the injected ``services.solve_fn`` with
# a ``CaptureCall`` (R19). ``reads`` and the chain are imported lazily: the core's import surface stays as it was.
# =================================================================================================================
READ_PLANS = ('full', 'economy')                       # R1: 'full' (typed-v1's reads) is the code default
READ_PLAN_DEFAULT = 'full'
READ_PLAN_SCHEDULES = {'full': ('interleaved', 'learn_first'), 'economy': ('learn_first',)}   # R2: allowed pairs
# typed-v3 (CHAIN-DECISIONS T2): the anchor events read before step 1, a sealed manifest field (``read_anchors``, CLI
# ``prepare --read-anchors``): typed-v2's C0 and C (the code default, every record as before) or C alone (the owner:
# "the no-card row is not read"). Read with ``read_events``; ('C',) only with the 'full' read plan and the base card
# 'historical' (``check_read_anchors``).
READ_ANCHORS = (('C0', 'C'), ('C',))
READ_ANCHORS_DEFAULT = ('C0', 'C')
READ_PLAN_PAUSES = PAUSE_REASONS                       # R1 / 3.6: the pause reasons this area adds (and uses)
SOLVER_SETTINGS_VERSION = 'typed-v2-solver-settings-1'
SOLVER_SETTINGS_FILE = 'solver-settings.json'          # R75: open, write-once, credential-free
SOLVER_SETTINGS_KEYS = ('model', 'route', 'max_tokens', 'nominal_tokens', 'thinking', 'reasoning_effort',
                        'response_model_ids', 'read_timeout')
CHECKPOINTS = ('after-first-inputs', 'after-plan-file', 'replay-child')   # R92: the fake-smoke kill points
PLAN_PROBE_EVENT_BENCH = ('C0', 'zebralogic')          # R7 / S1: the smoke's probe (a would-be alias under every base)
REPLAY_TIMEOUT_SECONDS = 3 * 3600                      # R76: bounds the replay's own work (it never waits for a lock)
UNSAFE_TEXT = re.compile(r'://|^/|\\|@|\s')            # no URL, path, credential-like or spaced text in the settings


def check_read_plan(schedule, read_plan, probe=None, *, smoke):
    """R2, R3, R7, Q20: ``read_plan`` is one of READ_PLANS and allowed with ``schedule`` (economy only with
    learn_first, D9); ``probe`` (``read_plan_probe``) is None or ``[event, bench]``, and only in a smoke manifest
    under economy. Raises ValueError naming keys only."""
    _require(type(read_plan) is str and read_plan in READ_PLANS,
             'A registered read plan %s: %s' % (READ_PLANS, repr(read_plan)[:40]))
    _require(schedule in READ_PLAN_SCHEDULES[read_plan],
             'read_plan economy requires schedule learn_first (addendum D9); found schedule %s' % repr(schedule)[:40])
    if probe is not None:
        _require(smoke is True, 'read_plan_probe is a smoke-only field (Q20): refused on a real root')
        _require(read_plan == 'economy', 'read_plan_probe needs read_plan economy (Q20)')
        _probe_pair(probe)
    return read_plan


def anchor_tuple(value):
    """``value`` (a list or tuple, e.g. a manifest's JSON list) as a member of READ_ANCHORS; refused otherwise (a
    string is refused too: ``tuple('C0')`` would be ('C', '0'))."""
    found = tuple(value) if isinstance(value, (list, tuple)) else None
    _require(found in READ_ANCHORS, 'A registered read anchor list %s: %s' % (
        [list(anchors) for anchors in READ_ANCHORS], repr(value)[:40]))
    return found


def read_events(anchors=READ_ANCHORS_DEFAULT):
    """The read events of a run, in their order: the anchors, then S1..S5 (``EVENTS`` for the default anchors). The
    consent of a run names exactly these, a run reads exactly these, and its chain completes with exactly these."""
    return anchor_tuple(anchors) + S_EVENTS


def check_read_anchors(anchors, *, read_plan, base_card):
    """typed-v3 T2: the anchors are registered, and C alone comes only with the 'full' read plan -- the economy plan's
    classes, aliases, counts and completeness checks span the seven events, C0 included (and T2 wants no economy
    plan) -- and the base card 'historical': only then is C the start of learning (every learned arm composes on C,
    addendum D17), so S1 - C is step 1's own contrast and S0 := C; under 'format' the learned arms compose on C0's
    format lines, and a run without the C0 row could not tell a learned gain from the hand card's. Raises ValueError
    naming keys only; returns the anchors as a tuple."""
    found = anchor_tuple(anchors)
    if found != READ_ANCHORS_DEFAULT:
        _require(read_plan == 'full', 'read_anchors C (no C0 read) needs read_plan full; found read_plan %s'
                 % repr(read_plan)[:40])
        _require(base_card == 'historical', 'read_anchors C (no C0 read) needs base_card historical (C is then the '
                                            'start of learning); found base_card %s' % repr(base_card)[:40])
    return found


def parse_probe(text):
    """``<event>:<bench>`` of the CLI (R4) as ``[event, bench]``."""
    _require(isinstance(text, str) and text.count(':') == 1, 'read_plan_probe is <event>:<bench>')
    return _probe_pair(text.split(':'))


# ---- the solver settings record (R75, RP2, 3.5) --------------------------------------------------------------
def solver_settings_record(chain, benches):
    """``<chain>/solver-settings.json``: per bench the credential-free settings of the solver block the chain runs
    with (model asked, provider route NAME, max tokens B, nominal M, thinking / reasoning setting, accepted response
    model ids, read timeout), self-hashed. No URL, key, proxy or credential path: every text value is a short word
    (refused otherwise). Provenance only: it enters no request, identity or decision (RP2)."""
    _require(chain in CHAINS and isinstance(benches, dict) and set(benches) == set(ORDER), 'Settings per bench')
    rows = {}
    for bench in ORDER:
        row = benches[bench]
        _require(isinstance(row, dict) and set(row) == set(SOLVER_SETTINGS_KEYS), 'The settings keys of 3.5')
        rows[bench] = _plain(row)
    record = _with_hash({'version': SOLVER_SETTINGS_VERSION, 'chain': chain, 'benches': rows}, 'record_sha256')

    def safe(value):
        if isinstance(value, dict):
            return all(isinstance(k, str) and not UNSAFE_TEXT.search(k) and safe(v) for k, v in value.items())
        if isinstance(value, list):
            return all(safe(v) for v in value)
        if isinstance(value, str):
            return len(value) <= OPEN_TEXT_MAX and not UNSAFE_TEXT.search(value)
        return value is None or isinstance(value, (bool, int, float))
    _require(safe(record), 'The solver settings record holds no URL, path, key or long text (RP2)')
    check_open_record(record, allow_floats=True)
    return record


def solver_settings_of_block(block, bench, *, nominal):
    """One bench's row of 3.5 from a route-B solver block (``clients.solver['G']`` or chain D's route-B pin);
    ``nominal``: whether the chain sends a nominal M (chain D). Only named keys are taken."""
    route = block.get('route')
    backend = block.get('backend')
    return {'model': block.get('model'), 'route': ('%s/%s' % (backend, route)) if route else backend,
            'max_tokens': (block.get('B') or {}).get(bench), 'nominal_tokens': (block.get('M') or {}).get(bench)
            if nominal else None, 'thinking': block.get('thinking'), 'reasoning_effort': block.get('reasoning_effort'),
            'response_model_ids': sorted(block.get('response_model_ids') or []),
            'read_timeout': (block.get('read_timeout') or {}).get(bench)}


# ---- the pass (R16 to R34) -----------------------------------------------------------------------------------
def propagates(error):
    """R33 a: a typed ``Paused``, a ``units.Stop``, a route-B ``Pause`` (a plain Exception) or a route-B stop kind
    raised by code the pass calls propagates unchanged; nothing else does."""
    from skillopt.coevo5.cells import Pause as RoutePause
    from skillopt.execskill.errors import stop_kind
    from .chain import Paused
    from .units import Stop
    return isinstance(error, (Paused, Stop, RoutePause)) or stop_kind(error) is not None


def _checkpoint(services, point):
    """R92: the fakes-only seam (real services have no ``checkpoint``: skipped)."""
    _require(point in CHECKPOINTS, 'A registered checkpoint')
    found = getattr(services, 'checkpoint', None)
    if callable(found):
        found(point)


def manifest_sha256(manifest):
    """The manifest record hash the plan binds (a prepared manifest's ``record_sha256``; a fake smoke's synthetic
    manifest, which has none, by its canonical hash)."""
    found = manifest.get('record_sha256') if isinstance(manifest, dict) else None
    return found if is_hash(found) else canonical_sha256(manifest)


def frozen_entry(receipt):
    """The plan header's ``frozen[event]`` (3.2) from a verified ``s<k>/frozen.json`` receipt."""
    entry = {key: receipt[key] for key in FROZEN_KEYS if key != 'receipt_sha256'}
    entry['receipt_sha256'] = receipt['record_sha256']
    return entry


def read_mount_of(receipt):
    """``{step, library_file_sha256, typemap_file_sha256}`` of the frozen state a receipt names (READ_MOUNT_KEYS)."""
    return {key: receipt[key] for key in READ_MOUNT_KEYS}


def frozen_states(load):
    """{event: {'receipt', 'library', 'typemap'}} for the seven events, each step's state loaded ONCE by ``load(k)
    -> (receipt, library, typemap)`` (the chain's verified loader: a missing or changed file pauses
    ``frozen_state_changed`` before anything is computed). C0 and C share the s0 objects (R27). Every mount of the
    pass uses exactly these objects (RP13)."""
    loaded = {}
    for event in EVENTS:
        k = step_of(event)
        if k not in loaded:
            loaded[k] = load(k)
    return {event: dict(zip(('receipt', 'library', 'typemap'), loaded[step_of(event)])) for event in EVENTS}


def _panel_unit(smoke):
    return SMOKE_SEALED_DIR if smoke else SEALED_DIR


def _dummy_reset(public):
    """A reset that starts no environment: the views are replaced by the stored ones right after (R78, N15)."""
    return '', []


def _with_stored_views(items, inputs):
    """ALFWorld items carrying the views stored in the inputs file (R78) instead of a live reset's."""
    from skillopt.validator_pilot.api import digest
    stored = dict(zip(inputs['item_ids'], inputs['alfworld_views']))
    _require(sorted(item['task_id'] for item in items) == inputs['item_ids'], 'stored views of these items')
    return [{**item, 'public': {**item['public'], 'routing_view': stored[item['task_id']],
                                'routing_view_sha256': digest(stored[item['task_id']])}} for item in items]


def open_plan_panels(services, root, chain, *, smoke, stored, lock):
    """R21 to R26: the five panels of the pass or of a replay, in chain order, through the one panel path
    (``reads.open_panel``, label ``<chain>/test-read-plan``; smoke: the held-out practice items, no consent, no
    registry). ``lock``: the pass takes the heavy lock for the SpreadsheetBench panel opening as a read does; a
    replay passes False (ADV5). ALFWorld on a real root: the live preparation resets (``reads.preparation_reset``,
    locked under 'unit_shared', R23) on a first pass; a re-run or a replay with a stored inputs file starts no
    environment and takes the stored views (R78). Returns {bench: {'items', 'ids', 'views'}}; nothing is written but
    what ``panel_tasks`` writes (registry, qualification)."""
    from . import reads
    unit, out = _panel_unit(smoke), {}
    for bench in services.order:
        found, alfworld_views = stored.get(bench), None
        if bench == NO_CAPTURE_BENCH and not smoke:
            alfworld_views = _dummy_reset if found is not None else reads.preparation_reset(services, unit)
        setup = dict(items=reads._smoke_panel(services, bench) if smoke else None, manifest=services.manifest,
                     smoke=smoke, runtime=services.runtime, view_fn=services.view_fn,
                     heavy=getattr(services, 'heavy', None) if lock else None, native=services.native,
                     alfworld_views=alfworld_views, panel=None, embed=services.embed)
        opened = reads.open_panel(root, chain, bench, unit, setup=setup, vectors=False)
        items, views = opened['items'], opened['views']
        if bench == NO_CAPTURE_BENCH and not smoke and found is not None:
            items = _with_stored_views(items, found)
            views = {item['task_id']: services.view_fn(bench, item) for item in items}
        out[bench] = {'items': items, 'ids': list(opened['ids']), 'views': views}
    return out


def plan_inputs(services, chain, panels, stored):
    """R26, R30, R78: per bench the inputs record. A stored one (re-run or replay) must be valid, of the same items,
    and its view hashes must equal the views recomputed from the re-opened items (``view_mismatch``); its vectors are
    used, never recomputed. A new one runs the panel's embedder batch twice (two subprocesses with the real
    embedder) over exactly the list a read unit embeds, sorted by id."""
    from . import reads
    out = {}
    for bench, panel in panels.items():
        ids = panel['ids']
        hashes = [view_sha256(panel['views'][i]) for i in ids]
        found = stored.get(bench)
        if found is not None:
            verify_inputs(found, chain=chain, bench=bench)
            if found['item_ids'] != ids:
                raise ReadPlanError('inputs_mismatch', 'items')
            check_views(found, hashes)
            out[bench] = found
            continue
        items = sorted(panel['items'], key=lambda item: item['task_id'])
        runs = [reads.panel_vectors(bench, items, embed=services.embed, views=panel['views']) for _ in (1, 2)]
        out[bench] = inputs_record(
            chain, bench, ids, hashes,
            alfworld_views=[panel['views'][i] for i in ids] if bench == NO_CAPTURE_BENCH else None,
            vectors=[[list(map(float, run[i])) for i in ids] for run in runs])
    return out


def capture_first_request(services, bench, item, mounted, *, event, smoke, chain_dir):
    """R19: the first solver request of one item under one event, zero sends: the injected ``solve_fn`` (the real
    ``mount.solve``; the fake smoke's ``fake_solve``, X2) with the capture-mounted record, the real unit name and
    cell tag, the scorer path the real cell would get (never created) and a ``CaptureCall``. None unless exactly one
    send was recorded (the event becomes ``capture_failed``). Stops raised inside propagate."""
    from .units import cell_tag
    unit = read_unit_name(event, bench, smoke=smoke)
    call = CaptureCall()
    services.solve_fn(bench, item, mounted, call=call, runtime=services.runtime, worker_factory=None,
                      native=services.native, nominal_tokens=services.nominal_tokens(bench), unit=unit,
                      tag=cell_tag(bench, item['task_id'], arm_of(event)), scorer_root=Path(chain_dir) / unit / 'transient',
                      mode=services.mode)
    return call.first_request()


def item_record_for(services, bench, item, event, state, *, vector, view, base_card, smoke, chain_dir, capture=True):
    """R16: one item's record under one event, from (i) ``services.identity_fn`` and (ii) ``services.mount_fn`` with
    the capture selector, both handed exactly the frozen library and type map of the event (``state``, RP13), the
    event's arm, the vector of the embedder run and the view; the first request captured where RP3 requires it."""
    arm = arm_of(event)
    common = dict(arm=arm, typemap=state['typemap'], library=state['library'], vector=vector, view=view,
                  base_card=base_card)
    identity = services.identity_fn(bench, item, **common)
    mounted = services.mount_fn(bench, item, selector=capture_selector, **common)
    components = item_components(identity, mounted, arm=arm, public_sha256=public_sha256(item['public']),
                                 view_sha256=view_sha256(view))
    first = None
    if capture and first_request_required(bench, components):
        first = capture_first_request(services, bench, item, mounted, event=event, smoke=smoke, chain_dir=chain_dir)
    return item_record(bench, components, first_request=first)


def _records(services, bench, items, event, state, vectors, views, **kw):
    """The records of every item, or (None, reason): a ReadPlanError gives its code, any other non-stop exception
    ``identity_exception`` (R16, R31); stops and pauses propagate (R33 a)."""
    try:
        return [item_record_for(services, bench, item, event, state, view=views[item['task_id']],
                                vector=None if vectors is None else vectors.get(item['task_id']), **kw)
                for item in items], None
    except ReadPlanError as error:
        return None, error.code if error.code in PASS_FALLBACK_REASONS else 'identity_exception'
    except Exception as error:  # noqa: BLE001 -- R16: a non-stop exception of an identity call is a fallback
        if propagates(error):
            raise
        return None, 'identity_exception'


def bench_entries(services, bench, panel, inputs, states, *, base_card, smoke, chain_dir):
    """The seven sealed event entries of one bench (``event_entry``): C0 and C without vectors (a read of them embeds
    none), S<k> with the first embedder run and, for R30, the second one (identities only, no capture)."""
    ids = inputs['item_ids']
    by_id = {item['task_id']: item for item in panel['items']}
    items = [by_id[i] for i in ids]
    runs = None if inputs['vectors'] is None else [dict(zip(ids, run)) for run in inputs['vectors']]
    entries = {}
    for event in EVENTS:
        state = states[event]
        common = dict(base_card=base_card, smoke=smoke, chain_dir=chain_dir)
        first_vectors = runs[0] if (event in S_EVENTS and runs) else None
        records, reason = _records(services, bench, items, event, state, first_vectors, panel['views'], **common)
        second = None
        if event in S_EVENTS and reason is None and runs:
            second, again = _records(services, bench, items, event, state, runs[1], panel['views'], capture=False,
                                     **common)
            reason = again if again is not None else None
        entries[event] = event_entry(bench, event, ids, records, read_mount=read_mount_of(state['receipt']),
                                     second=second, reason=reason)
    return entries


def compute_files(services, root, chain, *, smoke, panels, inputs, states, header, registry):
    """Every record of the plan (``plan_files``) from the opened panels, the inputs records and the frozen states."""
    benches = {}
    for bench in ORDER:
        benches[bench] = {
            'inputs': inputs[bench], 'registry_sha256': registry.get(bench),
            'entries': bench_entries(services, bench, panels[bench], inputs[bench], states,
                                     base_card=header['base_card'], smoke=smoke, chain_dir=Path(root) / chain),
            'run_constants_sha256': run_constants_sha256(
                bench, runtime=(services.manifest.get('runtime') or {}).get(bench) or {},
                worker_options=dict(services.worker_options or {}), nominal_tokens=services.nominal_tokens(bench),
                machinery=header['machinery'])}
    return plan_files(chain=chain, smoke=smoke, schedule=header['schedule'], read_plan=READ_PLAN,
                      base_card=header['base_card'], manifest_record_sha256=header['manifest_record_sha256'],
                      solver_settings_sha256=header['solver_settings_sha256'], order=list(services.order),
                      frozen={event: frozen_entry(states[event]['receipt']) for event in EVENTS}, benches=benches,
                      probe=header['probe'])


def registry_hashes(root, *, smoke):
    """R32 c: per bench the panel registry entry's hash without ``run`` (None in a smoke: no registry)."""
    if smoke:
        return {bench: None for bench in ORDER}
    found = {}
    for bench in ORDER:
        record = json.loads(read_bytes(Path(root) / 'shared' / 'test' / (bench + '.json'), allow_sealed=True))
        found[bench] = registry_sha256(record['entry'])
    return found


def stored_inputs(root, chain, *, smoke, required=False):
    """The inputs records already stored (R78), {bench: record}; a stored file that fails its checks is
    ``inputs_mismatch``. ``required`` (a replay): a missing file is ``inputs_mismatch`` too."""
    out = {}
    for bench in ORDER:
        path = inputs_path(root, chain, bench, smoke=smoke)
        if checked_path(path, allow_sealed=True).exists():
            out[bench] = load_sealed(path, 'inputs')
        elif required:
            raise ReadPlanError('inputs_mismatch', 'missing')
    return out


def _guarded(error):
    """Q24 option A: a non-stop exception of the pass's own code (after the panel path) is ``pass_exception``."""
    if isinstance(error, ReadPlanError) or propagates(error):
        return error
    return ReadPlanError('pass_exception', type(error).__name__)


def run_pass(services, root, chain, *, smoke, header, load):
    """The planning pass (R20 to R34, R78, R80, R92) after the chain set the phase and the read mounts (R20) and
    checked consent (R21). Zero model calls: identities through the injected mount functions, first requests through
    ``CaptureCall``. In order: the ``.part`` leftovers of the sealed directory removed; the five panels opened with
    views and the inputs made (stored ones loaded and checked, R78) -- exceptions of this panel path propagate
    unchanged (R33 a) -- then, as the pass's own code: every inputs file written first (``write_once``), the
    identities of the seven events per bench from the frozen states ``load(k)`` returns (RP13), every identities
    file, then ``read-plan.json`` last. Returns ``(plan, file_sha256)``. The pass's own detections raise
    ``ReadPlanError`` (inputs_mismatch, view_mismatch, sealed_file_mismatch, plan_file_mismatch, plan_self_check,
    pass_exception: the chain makes them ``read_plan_failed``, R33 c, Q24); a stored file with other bytes is
    ``sealed_file_mismatch`` / ``inputs_mismatch`` / ``plan_file_mismatch`` (R80)."""
    directory = sealed_dir(root, chain, smoke=smoke)
    remove_part_files(directory, allow_sealed=True)
    states = frozen_states(load)
    stored = stored_inputs(root, chain, smoke=smoke)
    panels = open_plan_panels(services, root, chain, smoke=smoke, stored=stored, lock=True)
    inputs = plan_inputs(services, chain, panels, stored)
    try:
        for number, bench in enumerate(ORDER):
            try:
                write_once(inputs_path(root, chain, bench, smoke=smoke), inputs[bench], allow_sealed=True)
            except WriteOnceMismatch:
                raise ReadPlanError('inputs_mismatch', 'stored') from None
            if number == 0:
                _checkpoint(services, 'after-first-inputs')
        files = compute_files(services, root, chain, smoke=smoke, panels=panels, inputs=inputs, states=states,
                              header=header, registry=registry_hashes(root, smoke=smoke))
        for bench in ORDER:
            try:
                write_once(identities_path(root, chain, bench, smoke=smoke), files[identities_name(bench)],
                           allow_sealed=True)
            except WriteOnceMismatch:
                raise ReadPlanError('sealed_file_mismatch', 'stored') from None
        try:
            digest = write_once(plan_path(root, chain), files[PLAN_FILE])
        except WriteOnceMismatch:
            raise ReadPlanError('plan_file_mismatch', 'stored') from None
        _checkpoint(services, 'after-plan-file')
        plan = load_plan(plan_path(root, chain), file_sha256=digest)
        if plan != files[PLAN_FILE]:
            raise ReadPlanError('plan_self_check')
        return plan, digest
    except Exception as error:  # noqa: BLE001 -- classified by _guarded: own detections, Q24, or propagated
        raise _guarded(error) from None


def recompute_files(services, root, chain, *, smoke, header, load):
    """R47 core, R44 c: the plan files recomputed in memory from the stored inputs (every inputs file required and
    hash-checked; ALFWorld views and both vector runs loaded, other views recomputed and checked), with the panels
    re-opened WITHOUT the heavy lock (ADV5). Zero calls, nothing written."""
    stored = stored_inputs(root, chain, smoke=smoke, required=True)
    _checkpoint(services, 'replay-child')  # R92: the fake services act on it inside a replay child only
    states = frozen_states(load)
    panels = open_plan_panels(services, root, chain, smoke=smoke, stored=stored, lock=False)
    inputs = plan_inputs(services, chain, panels, stored)
    return compute_files(services, root, chain, smoke=smoke, panels=panels, inputs=inputs, states=states,
                         header=header, registry=registry_hashes(root, smoke=smoke)), panels, inputs


def stored_bytes(root, chain, *, smoke):
    """{closed name: bytes or None} of the plan file and every sealed file (R47 compares them)."""
    found = {PLAN_FILE: None}
    path = plan_path(root, chain)
    if path.exists():
        found[PLAN_FILE] = read_bytes(path)
    for bench in ORDER:
        for name, where in ((inputs_name(bench), inputs_path(root, chain, bench, smoke=smoke)),
                            (identities_name(bench), identities_path(root, chain, bench, smoke=smoke))):
            target = checked_path(where, allow_sealed=True)
            found[name] = target.read_bytes() if target.exists() else None
    return found


def qualification_present(root):
    """R47: on a real root the five registry entries and the SpreadsheetBench qualification pointer exist (the pass
    created or verified them), so the replay's ``panel_tasks`` only verifies and starts no scoring container."""
    base = Path(root) / 'shared' / 'test'
    names = [bench + '.json' for bench in ORDER] + ['spreadsheetbench-qualification.json']
    return all(checked_path(base / name, allow_sealed=True).is_file() for name in names)


def replay(services, root, chain, *, smoke, header, load):
    """R47: the zero-call replay. The pass recomputed in memory from the stored sealed inputs (no heavy lock, no
    environment) and compared byte for byte with ``read-plan.json`` and every sealed file. Returns {verdict:
    'equal' | 'different' | 'error', files, equal, different, missing, reason, code, reembedded}: counts and fixed
    codes only (R47b). A changed frozen state, inputs file, panel or view, or a mount built on another base, is
    ``different``; a missing registry entry or qualification pointer on a real root is ``different`` with code
    ``qualification_missing`` (no qualification is ever started by a replay); any other exception is ``error``
    with ``replay_exception``. ``reembedded``: how many items a fresh embedder batch would give another vector than
    the stored first run (information only, never a difference)."""
    from .chain import Paused
    base = {'files': 0, 'equal': 0, 'different': 0, 'missing': 0, 'reembedded': None}
    if not smoke and not qualification_present(root):
        return {**base, 'verdict': 'different', 'reason': 'replay_different', 'code': 'qualification_missing'}
    try:
        files, panels, inputs = recompute_files(services, root, chain, smoke=smoke, header=header, load=load)
    except ReadPlanError as error:
        return {**base, 'verdict': 'different', 'reason': 'replay_different', 'code': error.code}
    except Paused as pause:
        if pause.reason == 'frozen_state_changed':
            return {**base, 'verdict': 'different', 'reason': 'replay_different', 'code': 'frozen_state_changed'}
        raise
    result = replay_compare(stored_bytes(root, chain, smoke=smoke), files)
    result['code'] = None if result['verdict'] == 'equal' else 'replay_different'
    result['reembedded'] = _reembedded(services, panels, inputs)
    return result


def _reembedded(services, panels, inputs):
    """R47 information: items whose fresh embedder vector differs from the stored first run; None when the embedder
    cannot run here (information only)."""
    from . import reads
    try:
        count = 0
        for bench, panel in panels.items():
            ids = inputs[bench]['item_ids']
            items = sorted(panel['items'], key=lambda item: item['task_id'])
            fresh = reads.panel_vectors(bench, items, embed=services.embed, views=panel['views'])
            stored = dict(zip(ids, inputs[bench]['vectors'][0]))
            count += sum(1 for i in ids if [float(x) for x in fresh[i]] != stored[i])
        return count
    except Exception:  # noqa: BLE001 -- information only: an unavailable embedder is no replay difference
        return None


def hash_seed(environ):
    """R76, ADV10: the child's PYTHONHASHSEED, other than the parent's: the parent's numeric value plus 1 modulo
    2**32, else 1 (the parent then runs with a random seed)."""
    found = (environ or {}).get('PYTHONHASHSEED')
    if isinstance(found, str) and found.isdigit():
        return (int(found) + 1) % (2 ** 32)
    return 1


# ---- the post-read check (R41) -------------------------------------------------------------------------------
def check_representative(root, chain, plan, event, bench, *, smoke, library):
    """R41 on the representative unit of (event, bench), counts only: per planned item its cell (by
    ``units.cell_tag``) against the sealed identities file (bound by the plan's file hash); ``library``: the event's
    frozen library (offered program ids to their skill sha256). Returns {items, equal, unequal}."""
    from .units import cell_tag, read_json
    identities = load_sealed(identities_path(root, chain, bench, smoke=smoke), 'identities',
                             file_sha256=plan['benches'][bench]['identities_sha256'])
    expected = expected_for_check(identities, event)
    where = Path(root) / chain / read_unit_name(event, bench, smoke=smoke) / 'cells'

    def program_sha256_of(skill_id):
        return library.get(skill_id)['sha256']
    observed = []
    for item_id in identities['item_ids']:
        path = where / (cell_tag(bench, item_id, arm_of(event)) + '.json')
        try:
            row = read_json(path, allow_sealed=True) if checked_path(path, allow_sealed=True).exists() else None
        except (OSError, ValueError):
            row = None
        observed.append(observed_from_row(row, program_sha256_of) if isinstance(row, dict) else None)
    return post_read_check(expected, observed)
