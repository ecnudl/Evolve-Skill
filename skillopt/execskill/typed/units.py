"""Units of typed-v2 (design §5.5): the token ledger (charge before send, settle on receipt), the recorded call
function handed to the solver shell, atomic unit directories with resume, and the concurrent cell runner with its
stop rules (cap, eight consecutive infrastructure unknowns, a configuration failure on a bench's first cell, and
any route-B stop kind raised by a cell: sandbox, balance, package, cleanup, configuration, budget, ...).

Nothing here knows about benches' content; it only moves records. Infrastructure unknown = transport / HTTP /
receipt-guard failure. Model-side noncompletions (length, empty, filtered) are known failures, never infrastructure.
WHY route-B stops are unit stops here and not per-cell losses: ``mount.solve`` re-raises every ``errors.STOP_KINDS``
member after the shell closed its worker (a docker outage, an exhausted balance, an invalid package); route B pauses
the unit for the owner on each of them, and a typed unit that silently dropped such a cell would shrink a gate's
denominator or leave a test panel incomplete without anyone noticing.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

from skillopt.coevo5 import ledger as attempt_ledger
from skillopt.coevo5.protocol import CLIENT_ATTEMPTS, RESERVATION_OVERHEAD
from skillopt.execskill.errors import STOP_KINDS, stop_kind

from . import FORBIDDEN_PATH_WORDS, SEED

TOKEN_FIELDS = ('prompt_tokens', 'completion_tokens', 'total_tokens')
INFRA_STOP_STREAK = 8
MODEL_SIDE_ERRORS = frozenset({'finish_length', 'finish_max_tokens', 'finish_sensitive', 'finish_content_filter',
                               'empty_content', 'content_missing', 'invalid_receipt'})
RECEIPT_KEYS = ('ok', 'response', 'finish_reason', 'usage', 'error_type', 'returned_model', 'reasoning_tokens',
                'visible_completion_tokens', 'reasoning_chars', 'attempts')


class Stop(RuntimeError):
    """Raised inside a call when the chain must not send anything more."""


class ReplayRefused(ValueError):
    """The resume replay 'on' refuses a calls file it cannot match call by call (typed-v3 B6 d; Codex's second look
    at the replay, point 3): a send record without its ``occurrence`` (a file written before sends were numbered, or
    one that mixes numbered and unnumbered records) is never guessed at. Nothing is sent for the cell: ``run_unit``
    stops its unit with the kind 'replay_refused' (the chain pauses for the owner), a role call pauses its unit."""


REPLAY_REFUSED = 'replay_refused'


def sha256_text(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def checked_path(path, *, allow_sealed=False):
    """Refuse names that belong to sealed test material unless the caller is a sealed read unit."""
    path = Path(path).expanduser().absolute()
    if not allow_sealed:
        for candidate in (path, path.resolve()):
            if any(word in str(candidate).lower() for word in FORBIDDEN_PATH_WORDS):
                raise ValueError('Refusing a sealed/test path outside a read unit: ' + str(path))
    return path


def write_json(path, value, *, allow_sealed=False):
    path = checked_path(path, allow_sealed=allow_sealed)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    with tmp.open('w', encoding='utf-8') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=1, sort_keys=True) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


def read_json(path, *, allow_sealed=False):
    return json.loads(checked_path(path, allow_sealed=allow_sealed).read_text(encoding='utf-8'))


# ---- ledger ------------------------------------------------------------------------------------------------------
def settle_receipt(receipt, size, max_tokens):
    """(tokens charged, reported usage or None, reservation breached) of one call, by route B's per-attempt rule
    (``coevo5.ledger.settle``): the frozen clients retry up to CLIENT_ATTEMPTS times inside one ``call``, so every
    attempt is charged -- the reported usage on the last attempt, 0 for an attempt refused before generation
    (connection refused, HTTP 4xx), else its whole bound; no receipt (an exception) charges the whole reservation.
    A receipt without an ``attempts`` list (the fakes) counts as one connected attempt."""
    if isinstance(receipt, dict) and receipt.get('attempts') is None:
        receipt = {**receipt, 'attempts': [{}]}
    attempts = receipt.get('attempts') if isinstance(receipt, dict) else None
    if isinstance(receipt, dict) and not (isinstance(attempts, list) and 1 <= len(attempts) <= CLIENT_ATTEMPTS
                                          and all(isinstance(a, dict) for a in attempts)):
        # a client outside the frozen contract (more attempts than reserved): the whole reservation, and a breach
        return CLIENT_ATTEMPTS * (size + RESERVATION_OVERHEAD + max_tokens), None, True
    charged, broken = attempt_ledger.settle(receipt if isinstance(receipt, dict) else None, size, max_tokens)
    usage = attempt_ledger._usage((receipt or {}).get('usage')) if isinstance(receipt, dict) else None
    reported = None
    if usage is not None:
        reported = usage[0] + usage[1]
    return charged, reported, bool(broken)


class Ledger:
    """Per-chain token ledger. State: cap, charged (reservations of pending calls + settled charges), reported
    (settled usage only), pending {key: {bound (the reservation), attempt_bound, size, max_tokens, cell, unit}},
    stopped, stop_reason, sends, missing_usage, recovered, infra_streak, by_unit.

    ``rerun_cells`` (in memory, never persisted): the ``(unit, tag)`` entries of cells to run again -- an interrupted
    call recovered on resume, a cell ``mark_infrastructure_reruns`` archived. An entry belongs to ONE unit and is
    consumed when ``run_unit`` of that unit has run the cell again (DESIGN 3.4 "Cells"): gate labels such as ``F#1``
    recur in several units of a step and a cell tag does not name its unit, so a bare tag left in the set would
    re-draw a finished cell of a later unit (more than R requests for that item and arm).

    WHY a reservation of CLIENT_ATTEMPTS attempt bounds: the frozen solver and role clients retry inside one call
    (1 + 3 attempts), and an attempt that timed out after reaching the provider may have been billed; route B
    reserves and settles exactly this way (``coevo5.ledger``), so the cap holds even when every attempt is billed."""

    def __init__(self, path, cap, *, resume=False, allow_sealed=False, durable=None):
        """``durable`` (the resume replay 'on'; None: typed-v2): ``durable(pending) -> {key: receipt}``, the receipts
        of pending calls that reached their calls file before the process died (``durable_receipts``). Each is settled
        exactly once before the ordinary recovery, as the uninterrupted call settled it (Codex review of 9c6d1f7,
        finding 2): its reservation becomes its charge by its recorded attempts and usage, and it is neither recovered
        nor marked for a re-run -- the resumed cell replays that receipt, nothing is sent again."""
        if type(cap) is not int or cap <= 0:
            raise ValueError('Positive token cap required')
        self.path, self.cap, self.lock = path, cap, threading.RLock()
        self.allow_sealed = allow_sealed
        self.stop_event = threading.Event()
        self.rerun_cells = set()
        self.state = {'cap': cap, 'charged': 0, 'reported': 0, 'pending': {}, 'stopped': False, 'stop_reason': None,
                      'sends': 0, 'missing_usage': 0, 'recovered': [], 'infra_streak': 0, 'by_unit': {}}
        if path is not None and checked_path(path, allow_sealed=allow_sealed).exists():
            if not resume:
                raise Stop('Existing ledger requires resume')
            self.state = read_json(path, allow_sealed=allow_sealed)
            if self.state['cap'] != cap:
                raise ValueError('Ledger cap changed')
            if durable is not None and self.state['pending']:
                found = durable({key: dict(entry) for key, entry in self.state['pending'].items()})
                for key in sorted(found, key=lambda key: int(key) if key.isdigit() else -1):
                    if key in self.state['pending']:
                        try:
                            self.settle(key, found[key])
                        except Stop:  # a reservation breach: the ledger stopped, as the uninterrupted call stopped it
                            pass
            for key, entry in self.state['pending'].items():  # an interrupted call may have been billed: keep its bound
                self.rerun_cells.add((entry['unit'], entry['cell']))
                self.state['recovered'].append({'key': key, **entry, 'at': time.strftime('%Y-%m-%dT%H:%M:%S')})
                self.state['missing_usage'] += 1
                per_unit = self.state['by_unit'].setdefault(entry['unit'], {'calls': 0, 'reported': 0, 'charged': 0})
                per_unit['calls'] += 1  # the reservation stays in the chain's charge: the unit's cost names it too
                per_unit['charged'] += entry['bound']
                per_unit['recovered'] = per_unit.get('recovered', 0) + entry['bound']
            self.state['pending'] = {}
            if self.state['stopped']:
                self.stop_event.set()
            self.persist()

    def persist(self):
        if self.path is not None:
            write_json(self.path, self.state, allow_sealed=self.allow_sealed)

    # ``rerun_cells`` is read and changed only through these three, under the lock: the read units of one event run
    # in parallel threads, and an unlocked change while another unit iterates the set raised 'Set changed size
    # during iteration' (fix-b, review rb-resume 3).
    def mark_rerun(self, unit, tag):
        """Mark the cell ``tag`` of ``unit`` for a re-run."""
        with self.lock:
            self.rerun_cells.add((unit, tag))

    def reruns_of_unit(self, unit):
        """The cell tags of ``unit`` marked for a re-run (a copy)."""
        with self.lock:
            return {tag for owner, tag in self.rerun_cells if owner == unit}

    def consume_reruns(self, unit, tags):
        """Remove the entries of the cells ``tags`` of ``unit`` (absent entries are ignored)."""
        with self.lock:
            self.rerun_cells.difference_update([(unit, tag) for tag in tags])

    def stop(self, reason):
        with self.lock:
            self.state['stopped'] = True
            self.state['stop_reason'] = self.state['stop_reason'] or reason
            self.stop_event.set()
            self.persist()

    def stopped(self):
        return self.stop_event.is_set() or self.state['stopped']

    def before_send(self, system, user, max_tokens, *, cell, unit):
        """Reserve CLIENT_ATTEMPTS attempt bounds (bytes + 512 + max_tokens each) before the call; returns (key, the
        ONE-attempt bound)."""
        if type(max_tokens) is not int or max_tokens < 1:
            raise ValueError('Positive completion bound required')
        size = attempt_ledger.request_bytes(system, user)
        bound = size + RESERVATION_OVERHEAD + max_tokens
        reservation = CLIENT_ATTEMPTS * bound
        with self.lock:
            if self.stopped():
                raise Stop('ledger stopped: ' + str(self.state['stop_reason']))
            if self.state['charged'] + reservation > self.cap:
                self.state['stopped'], self.state['stop_reason'] = True, 'token_cap'
                self.stop_event.set()
                self.persist()
                raise Stop('token cap reached')
            key = str(self.state['sends'])
            self.state['sends'] += 1
            self.state['charged'] += reservation
            self.state['pending'][key] = {'bound': reservation, 'attempt_bound': bound, 'size': size,
                                          'max_tokens': max_tokens, 'cell': cell, 'unit': unit}
            self.persist()  # a persistence failure prevents the send
            return key, bound

    def settle(self, key, receipt, *, max_tokens=None, prompt_bound=None):
        """Replace the call's reservation by its per-attempt charge (``settle_receipt``); a reported usage above
        the attempt bound (prompt > bytes + 512 or completion > max_tokens) stops the ledger."""
        with self.lock:
            entry = self.state['pending'].pop(key)
            reservation, unit = entry['bound'], entry['unit']
            charged, reported, breach = settle_receipt(receipt, entry['size'], entry['max_tokens'])
            self.state['charged'] += charged - reservation
            self.state['reported'] += reported or 0
            self.state['missing_usage'] += int(reported is None)
            per_unit = self.state['by_unit'].setdefault(unit, {'calls': 0, 'reported': 0, 'charged': 0})
            per_unit['calls'] += 1
            per_unit['reported'] += reported or 0
            per_unit['charged'] += charged
            if breach:
                self.state['stopped'], self.state['stop_reason'] = True, 'reservation_breach'
                self.stop_event.set()
            self.persist()
            if breach:
                raise Stop('provider exceeded the reservation bound')
            return charged

    def observe_infrastructure(self, unknown):
        """Count consecutive infrastructure unknowns; eight in a row stop the chain."""
        with self.lock:
            self.state['infra_streak'] = self.state['infra_streak'] + 1 if unknown else 0
            if self.state['infra_streak'] >= INFRA_STOP_STREAK and not self.state['stopped']:
                self.state['stopped'], self.state['stop_reason'] = True, 'eight_consecutive_infrastructure_unknowns'
                self.stop_event.set()
            self.persist()


# ---- recorded call ---------------------------------------------------------------------------------------------
class CallRecorder:
    """The ``call(system, user) -> receipt`` handed to the shell: charge, call the factory client, settle, record.
    ``keep_rest`` (False; ``replaying`` sets it under the resume replay 'on'): each send record also keeps, as
    ``receipt_rest``, the receipt's keys outside ``RECEIPT_KEYS``, so a replayed receipt is the one the shell saw.
    ``count_occurrences()`` (the resume replay 'on' and the role-call replay call it): each send record also keeps its
    ``occurrence``, the n-th call of its request hash in this recorder's flow -- a call a replay answered counts too
    (``next_occurrence``), and a call sent again after a resume carries the number of the occurrence it replaces."""

    def __init__(self, client_call, ledger, *, max_tokens, tag, unit, out_path, transform=None, allow_sealed=False):
        self.client_call, self.ledger, self.max_tokens = client_call, ledger, max_tokens
        self.tag, self.unit, self.out_path, self.transform = tag, unit, out_path, transform
        self.allow_sealed = allow_sealed
        self.sends, self.receipts = [], []
        self.keep_rest = False
        self.flow = None  # {request hash: calls so far in this recorder's flow} once occurrences are counted

    def count_occurrences(self):
        """From now on every send record names its occurrence (the counting starts with this recorder's flow)."""
        if self.flow is None:
            self.flow = {}

    def next_occurrence(self, sha):
        """The occurrence number of the next call of request hash ``sha`` in this recorder's flow (1, 2, ...)."""
        self.count_occurrences()
        self.flow[sha] = self.flow.get(sha, 0) + 1
        return self.flow[sha]

    def __call__(self, system, user, *, occurrence=None):
        """One recorded call. An exception settles the call at its bound. An interruption of the process inside the
        call (KeyboardInterrupt from SIGINT, SystemExit: a BaseException that is no Exception) leaves it UNSETTLED, as
        a kill would: its reservation stays pending, so the resumed ledger records it as recovered and marks its
        (unit, cell) for a re-run, and the decision records count that re-run (fix-b, review rb-resume 1).
        ``occurrence``: the number a replaying wrapper gave this call (else counted here once counting is on)."""
        if self.transform is not None:
            system, user = self.transform(system, user)
        sha = sha256_text(system + '\x00' + user)
        if occurrence is None and self.flow is not None:
            occurrence = self.next_occurrence(sha)
        key, bound = self.ledger.before_send(system, user, self.max_tokens, cell=self.tag, unit=self.unit)
        record = {'request_sha256': sha, 'system': system, 'user': user,
                  'logical_call': key, 'receipt': None, 'charge_bound': bound, 'reserved': CLIENT_ATTEMPTS * bound}
        if occurrence is not None:
            record['occurrence'] = occurrence
        self.sends.append(record)
        self._flush()
        receipt, interrupted = None, False
        try:
            receipt = self.client_call(system, user)
            if not isinstance(receipt, dict):
                receipt = {'ok': False, 'usage': {}, 'error_type': 'invalid_receipt'}
            record['receipt'] = {k: receipt.get(k) for k in RECEIPT_KEYS}
            if self.keep_rest:
                record['receipt_rest'] = {k: v for k, v in receipt.items() if k not in RECEIPT_KEYS}
            self.receipts.append(receipt)
            return receipt
        except Exception as error:
            record['exception'] = type(error).__name__
            raise
        except BaseException as error:
            record['exception'], interrupted = type(error).__name__, True
            raise
        finally:
            try:
                self._flush()
            finally:
                if not interrupted:
                    self.ledger.settle(key, receipt, max_tokens=self.max_tokens, prompt_bound=bound - self.max_tokens)

    def _flush(self):
        if self.out_path is not None:
            write_json(self.out_path, self.sends, allow_sealed=self.allow_sealed)

    def tokens(self):
        return tokens_of(self.sends)

    def infrastructure_unknown(self):
        """True when any send failed for a transport/HTTP/receipt reason (not a model-side noncompletion)."""
        return infrastructure_unknown_of(self.sends)


def tokens_of(sends):
    """The total tokens of the usage of the receipts of ``sends``."""
    return sum(((s.get('receipt') or {}).get('usage') or {}).get('total_tokens') or 0 for s in sends)


# typed-v3 B7 (2026-11-15, chain G's first real run): a provider's content filter refusing THIS request is a model-side
# outcome, as ``finish_sensitive`` / ``finish_content_filter`` are (addendum O1: final, scored 0, never re-run). GLM-5.3
# answers a request whose content its filter refuses with HTTP 400 and error code 1301, 0 tokens, and answers the same
# request the same way again (s1/items-check: a SearchQA practice item, re-run once on 2026-11-15 15:18, refused
# again). The code is read from a send record's ``receipt_rest`` (kept under the resume replay 'on', the typed-v3
# preset); a record without it (typed-v2's, 'off') keeps an HTTP 400 an infrastructure unknown, as before. Role calls
# (``writers.reply_failure``) are unchanged.
PROVIDER_FILTER_REFUSALS = frozenset({('http_400', '1301')})


def provider_filter_refusal(send):
    """True when ``send`` failed because the provider's content filter refused its request: its receipt is not ok and
    (error_type, ``receipt_rest.error_code``) is one of ``PROVIDER_FILTER_REFUSALS``."""
    receipt = send.get('receipt') or {}
    rest = send.get('receipt_rest') or {}
    if not receipt or receipt.get('ok') or not isinstance(rest, dict) or rest.get('error_code') is None:
        return False
    return (str(receipt.get('error_type')), str(rest.get('error_code'))) in PROVIDER_FILTER_REFUSALS


def infrastructure_unknown_of(sends):
    """True when any of ``sends`` failed for a transport/HTTP/receipt reason (not a model-side noncompletion; a
    provider's content-filter refusal, ``provider_filter_refusal``, is model-side)."""
    for send in sends:
        receipt = send.get('receipt') or {}
        if send.get('exception') and send.get('exception') != 'Stop':
            return True
        if (receipt and not receipt.get('ok') and (receipt.get('error_type') or 'unknown') not in MODEL_SIDE_ERRORS
                and not provider_filter_refusal(send)):
            return True
    return False


def cell_refused(row):
    """typed-v3 B7b: True when the provider's content filter refused a request of the solver cell ``row``: one of its
    ``sends`` or ``selection_sends`` (the selection request carries the task's public text too) is a
    ``provider_filter_refusal``. The chain keeps such an item's text out of the role samples that show public text
    without reading an outcome (``chain._Run.refused_ids``) and out of the analyst's learn rows
    (``items.plan.learn_rows``)."""
    if not isinstance(row, dict):
        return False
    return any(isinstance(send, dict) and provider_filter_refusal(send)
               for key in ('sends', 'selection_sends') for send in (row.get(key) or ()))


# ---- the resume replay (typed-v3, CHAIN-DECISIONS B6 d) ------------------------------------------------------------
def replay_queues(sends):
    """The replay rule of a calls file written before sends named their occurrence (``ReplayRule``'s fallback; P1 F5's
    rule): from the sends an earlier attempt saved in a calls file, per request hash (``request_sha256``, of system
    NUL user after the recorder's transform) its DELIVERED sends (receipt ``ok``) and its FAILED sends that precede the
    file's last delivered one (a failure the earlier flow read and went past), each in file order. A send without a
    receipt (interrupted inside the client) or with an exception is in neither, and a failure after the last delivered
    receipt (where the earlier process stood) is in neither: those requests are sent again. Returns (delivered,
    failed) as {hash: [send, ...]}; both are empty when the file holds no delivered receipt (a resume after failures
    sends again, as typed-v2)."""
    rows = [send for send in sends or [] if isinstance(send, dict) and not send.get('exception')
            and isinstance(send.get('receipt'), dict)]
    last = max((n for n, send in enumerate(rows) if send['receipt'].get('ok') is True), default=None)
    delivered, failed = {}, {}
    if last is None:
        return delivered, failed
    for n, send in enumerate(rows):
        ok = send['receipt'].get('ok') is True
        if ok or n < last:
            (delivered if ok else failed).setdefault(send.get('request_sha256'), []).append(send)
    return delivered, failed


class ReplayRule:
    """The replay rule of a resumed call over the sends an earlier attempt saved in a calls file. ``answer(sha, k)``:
    the saved send that answers the call -- occurrence ``k`` of request hash ``sha`` -- or None (send it).

    ``numbered`` (the resume replay 'on', typed-v3 B6 d; Codex review of 9c6d1f7, finding 1): every saved send names
    its occurrence (the k-th call of its request in the recorder's flow) and occurrence k is answered by ITS OWN
    outcome, the last record of (sha, k) in the file -- a delivered receipt is replayed (an occurrence is never paid
    twice); a failure the flow went past (a later record follows it in the file: the earlier flow read it and went on,
    e.g. to the next identical fix request) is replayed as the failure; a failure at the end of the file (where the
    earlier process stood), a call interrupted inside the client and a call that raised are sent again as occurrence
    k. So two identical requests whose first failed and whose second was delivered are answered failed, then
    delivered, as the uninterrupted flow saw them. A file with a record that names no occurrence (written before sends
    were numbered, or mixing numbered and unnumbered records) is refused (``ReplayRefused``; Codex's second look,
    point 3): it is never guessed at. ``failures`` False (a cell re-run after its recorded outcome was archived,
    ``replaying``): no failure is replayed.

    ``final_refusals`` (numbered only; ``ReplayingRecorder``, the solver cells' replay, sets it; typed-v3 B7b, Codex's
    review of f1950b9): a saved send that is a provider's content-filter refusal (``provider_filter_refusal``) answers
    its occurrence as a delivered receipt does -- wherever it stands in the file (the last record, where the earlier
    process stood, too) and also with ``failures`` False -- because B7 made it a final model-side outcome (addendum O1:
    scored 0, never re-run): a refusal saved right before a kill, or one kept in the calls file of a cell re-run after
    another failure, is never sent again (a new reply could replace the final zero; a transport failure on the resend
    would turn it into an infrastructure unknown). A delivered receipt of the same occurrence still answers first. The
    role-call replay (``chain._Replaying``) and the unnumbered rule never set it: a role call's refused receipt at the
    end of its file is sent again, as before.

    Not ``numbered`` (the role-call replay of P1 F5 under 'repair' with the resume replay 'off'; the rule of cb80dcc,
    kept exactly): ``replay_queues`` -- per request hash its delivered receipts in file order, then the failures that
    precede the file's last delivered receipt; ``k`` is not read."""

    def __init__(self, sends, *, failures=True, numbered=False, final_refusals=False):
        self.numbered = bool(numbered)
        self._answers, self._delivered, self._failed = {}, {}, {}
        if final_refusals and not self.numbered:
            raise ValueError('final_refusals is a rule of the numbered replay (the resume replay on) only')
        if not self.numbered:
            self._delivered, failed = replay_queues(sends)
            self._failed = failed if failures else {}
            return
        if not isinstance(sends, list):
            raise ReplayRefused('A calls file holds the list of its sends')
        rows = list(sends)
        unnamed = sum(1 for send in rows if not (isinstance(send, dict) and type(send.get('occurrence')) is int
                                                 and send['occurrence'] >= 1))
        if unnamed:
            raise ReplayRefused('%d of the %d saved sends of this calls file name no occurrence: the resume replay '
                                "'on' matches every call by its occurrence and does not guess (a file written before "
                                'sends were numbered, or one that mixes numbered and unnumbered records)'
                                % (unnamed, len(rows)))
        last, delivered, refused = {}, {}, {}
        for n, send in enumerate(rows):
            key = (send.get('request_sha256'), send['occurrence'])
            last[key] = (n, send)
            receipt = send.get('receipt')
            if not send.get('exception') and isinstance(receipt, dict) and receipt.get('ok') is True:
                delivered[key] = send
            elif final_refusals and not send.get('exception') and provider_filter_refusal(send):
                refused[key] = send
        for key, (n, send) in last.items():
            receipt = send.get('receipt')
            if key in delivered:
                self._answers[key] = delivered[key]
            elif key in refused:  # B7b: final, wherever it stands and whatever ``failures`` says
                self._answers[key] = refused[key]
            elif (failures and not send.get('exception') and isinstance(receipt, dict) and n != len(rows) - 1):
                self._answers[key] = send

    @property
    def replays(self):
        """Some call of a resumed flow would be answered from the file."""
        return bool(self._answers or self._delivered or self._failed)

    def answer(self, sha, k=None):
        if self.numbered:
            return self._answers.get((sha, k))
        queue = self._delivered.get(sha) or self._failed.get(sha)
        return queue.pop(0) if queue else None


class ReplayingRecorder:
    """The recorder of a solver cell under the resume replay 'on' (typed-v3 B6 d): a ``CallRecorder`` (the cell's solve
    call or its selection call) whose calls file holds the sends of an earlier attempt of the cell -- the process died
    after a reply was saved and before the cell record was written. The k-th call of a request whose occurrence k has
    a saved answer (``ReplayRule`` with ``final_refusals``: its delivered receipt, its provider content-filter refusal
    wherever it stands (typed-v3 B7b: a final model-side outcome, never sent again), or -- with ``failures`` -- a
    failure the earlier flow went past) is answered with its receipt -- the saved ``receipt`` with its
    ``receipt_rest`` (the keys outside ``RECEIPT_KEYS`` the shell and the judge may read, e.g. ``over_nominal``,
    ``subtype``): nothing is sent, charged or written. Any other call goes to the recorder as that occurrence, which
    charges, sends and records it after the earlier sends (they stay in the calls file). What the cell records --
    ``sends``, ``tokens()``, ``infrastructure_unknown()`` -- is THIS attempt's path: each replayed send's saved record
    and each new send, in call order; an earlier send nothing replayed (a failure where the earlier process stood, a
    call interrupted inside the client) is in the calls file only, as typed-v2's resend left it in the ledger only.
    ``replayed``: the request hashes answered so; ``receipts``: every receipt this attempt returned; every other
    attribute is the recorder's.
    ``failures`` False (``replaying``: a cell run again after its recorded outcome was archived for a re-run): no
    failure is replayed, every failed request is sent again -- but a provider refusal, which is no failure to heal,
    is replayed still (B7b). A calls file whose sends do not all name their occurrence is refused (``ReplayRule``:
    ``ReplayRefused``, before anything is sent)."""

    def __init__(self, call, earlier, *, failures=True):
        self._call, self.path, self.replayed, self.receipts = call, [], [], []
        self._rule = ReplayRule(earlier, failures=failures, numbered=True, final_refusals=True)
        call.count_occurrences()

    def __call__(self, system, user):
        transform = getattr(self._call, 'transform', None)
        shown = transform(system, user) if transform is not None else (system, user)
        sha = sha256_text(shown[0] + '\x00' + shown[1])
        k = self._call.next_occurrence(sha)
        send = self._rule.answer(sha, k)
        if send is not None:
            self.replayed.append(sha)
            self.path.append(send)
            receipt = {**send['receipt'], **(send.get('receipt_rest') or {})}
            self.receipts.append(receipt)
            return receipt
        n = len(self._call.sends)
        try:
            receipt = self._call(system, user, occurrence=k)
            self.receipts.append(receipt)
            return receipt
        finally:
            self.path.extend(self._call.sends[n:])

    @property
    def sends(self):
        return list(self.path)

    def tokens(self):
        return tokens_of(self.path)

    def infrastructure_unknown(self):
        return infrastructure_unknown_of(self.path)

    def __getattr__(self, name):
        return getattr(self._call, name)


def replaying(call):
    """``call`` (a ``CallRecorder``) of a solver cell under the resume replay 'on', set to keep each receipt's rest
    (``keep_rest``: what a later replay of the send returns besides ``RECEIPT_KEYS``) and to name each send's
    occurrence (``count_occurrences``: what a later replay matches a call by): when its calls file already holds the
    sends of an earlier attempt, they go into the recorder first (its flushes rewrite the file with them, so every
    earlier send stays in it) and a ``ReplayingRecorder`` answers from them; else the recorder itself.

    A cell whose earlier outcome was recorded and then archived for a re-run (``rerun/<tag>-<n>.json`` beside the
    unit's ``calls/``: ``mark_infrastructure_reruns``, an infrastructure unknown or a configuration failure) replays
    its delivered receipts and its provider refusals only (typed-v3 B7b: a refusal is a final model-side outcome, no
    failure to heal): the re-run exists to heal those failures, so each failed request is sent again --
    replaying a failure its flow went past (a failed selection call before its delivered format retry) would record
    the same infrastructure unknown after every recovery. A cell never recorded (a kill after a reply was saved)
    replays the failures its flow went past too, so it completes as the uninterrupted attempt did; a refusal saved
    right before the kill is replayed wherever it stands. A calls file that is no list of numbered sends is refused
    before anything is sent or rewritten (``ReplayRefused``)."""
    call.keep_rest = True
    call.count_occurrences()
    path = getattr(call, 'out_path', None)
    sealed = bool(getattr(call, 'allow_sealed', False))
    if path is None or not checked_path(path, allow_sealed=sealed).exists():
        return call
    earlier = read_json(path, allow_sealed=sealed)
    if not isinstance(getattr(call, 'sends', None), list) or call.sends:
        raise ValueError('A new recorder has sent nothing')
    found = ReplayingRecorder(call, earlier, failures=not archived_for_rerun(path, getattr(call, 'tag', None),
                                                                            allow_sealed=sealed))
    call.sends.extend(earlier)
    return found


def archived_for_rerun(calls_path, tag, *, allow_sealed=False):
    """The cell ``tag`` of the unit whose calls file is ``calls_path`` (``<unit>/calls/<file>``) has an earlier record
    archived for a re-run (``<unit>/rerun/<tag>-<n>.json``, ``mark_infrastructure_reruns``)."""
    if type(tag) is not str or not tag:
        return False
    rerun = checked_path(Path(calls_path).parent.parent / 'rerun', allow_sealed=allow_sealed)
    return rerun.is_dir() and any(rerun.glob(tag + '-*.json'))


def durable_receipts(chain_dir, pending, *, opens=lambda unit: False):
    """The receipts that reached a calls file of the ``pending`` ledger calls ({key: entry}, the entry naming its
    ``unit`` and ``cell``, the recorder's tag): {key: receipt} for each send record in a calls file of that cell
    (``<chain_dir>/<unit>/calls/<cell>[-<purpose>].json``) whose ``logical_call`` is the pending key and which holds a
    receipt -- delivered or failed; a call interrupted inside the client or one that raised holds none -- with its
    ``receipt_rest`` when kept (the receipt the call returned). The ``durable`` of ``Ledger`` under the resume replay
    'on'. ``opens(unit)`` decides, before anything of the unit is opened: False -- an open unit; True -- a sealed unit
    (a read unit) whose files may be opened now (its read's own checks passed: ``chain._durable_receipts``); None --
    the unit stays closed and its pending calls go to the ordinary recovery (Codex's second look, point 1)."""
    wanted = {}
    for key, entry in pending.items():
        unit, cell = (entry.get('unit'), entry.get('cell')) if isinstance(entry, dict) else (None, None)
        if type(unit) is str and unit and type(cell) is str and cell:
            wanted.setdefault(unit, {})[key] = cell
    found = {}
    for unit, cells in sorted(wanted.items()):
        access = opens(unit)
        if access is None:
            continue
        allow = bool(access)
        calls = checked_path(Path(chain_dir) / unit / 'calls', allow_sealed=allow)
        if not calls.is_dir():
            continue
        for path in sorted(calls.glob('*.json')):
            if not any(path.name.startswith(cell) for cell in cells.values()):
                continue
            sends = read_json(path, allow_sealed=allow)
            for send in sends if isinstance(sends, list) else ():
                key = send.get('logical_call') if isinstance(send, dict) else None
                if (key in cells and key not in found and not send.get('exception')
                        and isinstance(send.get('receipt'), dict)):
                    found[key] = {**send['receipt'], **(send.get('receipt_rest') or {})}
    return found


# ---- units -------------------------------------------------------------------------------------------------------
def cell_tag(bench, item_id, arm):
    return sha256_text(bench + '\x00' + item_id + '\x00' + arm)


def arm_order(item_id, arms):
    """Deterministic per-item order of the arms of one item (both arms of an item run back to back)."""
    import random
    ordered = list(arms)
    random.Random(SEED + int(sha256_text(item_id)[:8], 16)).shuffle(ordered)
    return ordered


def unit_done(unit_dir, *, allow_sealed=False):
    return checked_path(Path(unit_dir) / 'done.json', allow_sealed=allow_sealed).exists()


def reopen_stopped(unit_dir, *, allow_sealed=False):
    """Archive the ``done.json`` of a unit that stopped early (a stop reason or missing cells) as
    ``done-stopped-<n>.json`` so that ``run_unit`` runs its missing cells again instead of returning it as done.
    WHY here: ``run_unit`` writes ``done.json`` even when it stopped (the chain reads the stop reason from it), so
    the one place that owns the marker also owns its archiving; the chain's learning units and the sealed read
    units both resume through it. Returns True when a marker was archived."""
    unit_dir = checked_path(unit_dir, allow_sealed=allow_sealed)
    path = unit_dir / 'done.json'
    if not path.exists():
        return False
    done = read_json(path, allow_sealed=allow_sealed)
    if not done.get('stop_reason') and not done.get('missing_cells'):
        return False
    n = 1 + len(list(unit_dir.glob('done-stopped-*.json')))
    os.replace(path, unit_dir / ('done-stopped-%d.json' % n))
    return True


def archive_done(unit_dir, *, allow_sealed=False):
    """Archive a unit's ``done.json`` unconditionally (``done-stopped-<n>.json``), so that the next ``run_unit``
    runs the unit again instead of returning it from disk. WHY: a unit can be complete by count and still unusable
    (a noise calibration with too few known pairs); the chain archives the marker before it pauses, and the owner's
    recovery then re-enters the unit. Returns True when a marker was archived."""
    unit_dir = checked_path(unit_dir, allow_sealed=allow_sealed)
    path = unit_dir / 'done.json'
    if not path.exists():
        return False
    n = 1 + len(list(unit_dir.glob('done-stopped-*.json')))
    os.replace(path, unit_dir / ('done-stopped-%d.json' % n))
    return True


def mark_infrastructure_reruns(unit_dir, ledger, *, unit, allow_sealed=False):
    """Mark the finished cells of an UNFINISHED unit whose outcome is an infrastructure unknown, or a configuration
    failure (an exception after the call: the judge or the scorer raised), for a rerun: each record is MOVED to
    ``rerun/<tag>-<n>.json`` (one archived record per earlier attempt, so the files count the re-runs of a cell)
    and ``(unit, tag)`` is added to ``ledger.rerun_cells``; ``run_unit`` of that unit runs the cell again and
    consumes the entry. ``unit``: the unit's name as the ledger records it (``s<k>/noise``, a read unit's name).
    WHY: the one automatic retry and an owner recovery exist to heal transport/HTTP outages and the configuration
    fault the owner looked at; re-running only the ledger's interrupted calls would leave every cell that failed
    during the outage, or before the fix, unknown for good (and a gate arm undecidable), and a cached failed first
    cell must never confirm a bench's configuration. A model-side unknown (``correct`` None with neither flag) is a
    final verdict and is never marked (addendum O1). A done unit is never touched. Returns the marked tags."""
    unit_dir = checked_path(unit_dir, allow_sealed=allow_sealed)
    require_unit(unit)
    if unit_done(unit_dir, allow_sealed=allow_sealed) or not (unit_dir / 'cells').is_dir():
        return []
    marked = []
    for path in sorted((unit_dir / 'cells').glob('*.json')):
        row = read_json(path, allow_sealed=allow_sealed)
        if row.get('correct') is None and (row.get('infrastructure_unknown') or row.get('configuration_error')):
            n = 1 + len(list((unit_dir / 'rerun').glob(path.stem + '-*.json'))) if (unit_dir / 'rerun').is_dir() else 1
            target = checked_path(unit_dir / 'rerun' / ('%s-%d.json' % (path.stem, n)), allow_sealed=allow_sealed)
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(path, target)
            ledger.mark_rerun(unit, path.stem)
            marked.append(path.stem)
    return marked


def require_unit(unit):
    if type(unit) is not str or not unit:
        raise ValueError('A unit is named as the ledger records it (a non-empty string)')
    return unit


def reruns_of(unit_dir, tags, *, allow_sealed=False):
    """The number of archived earlier attempts (``rerun/<tag>-<n>.json``) of the given cell tags of one unit."""
    unit_dir = checked_path(unit_dir, allow_sealed=allow_sealed)
    if not (unit_dir / 'rerun').is_dir():
        return 0
    wanted = set(tags)
    return sum(1 for path in (unit_dir / 'rerun').glob('*.json') if path.stem.rsplit('-', 1)[0] in wanted)


def run_unit(unit_dir, jobs, *, unit, widths, build_cell, ledger, resume=False, allow_sealed=False, meta=None):
    """Run cells of one unit concurrently and atomically.

    ``unit``: the unit's name as its calls record it in the ledger (``s<k>/noise``, a read unit's name); only the
    ``(unit, tag)`` entries of ``ledger.rerun_cells`` re-run a stored cell of this unit, and an entry is consumed
    (removed) once its cell has run again, so no entry ever re-draws a cell of another unit or a cell twice.
    ``jobs``: list of (bench, item, arms) with ``arms`` the arm tags of that item (run back to back per item);
    ``build_cell(bench, item, arm, tag) -> row`` must return a dict with at least ``correct`` (True/False/None),
    ``failure`` (exception class or None), ``configuration_error`` (bool), ``infrastructure_unknown`` (bool) and
    ``sends`` (list); it raises ``Stop`` only through the ledger, and a route-B stop kind (``errors.STOP_KINDS``)
    stops the unit with that kind (``stop.json`` names the cell). Returns (cells, stop_reason).
    """
    unit_dir = checked_path(unit_dir, allow_sealed=allow_sealed)
    require_unit(unit)
    if unit_done(unit_dir, allow_sealed=allow_sealed):
        done = read_json(unit_dir / 'done.json', allow_sealed=allow_sealed)
        cells = [read_json(p, allow_sealed=allow_sealed) for p in sorted((unit_dir / 'cells').glob('*.json'))]
        return cells, done.get('stop_reason')
    if unit_dir.exists() and any(unit_dir.iterdir()) and not resume:
        raise Stop('Unit directory is not empty and resume is off: ' + str(unit_dir))
    (unit_dir / 'cells').mkdir(parents=True, exist_ok=True)
    cached = {}
    rerun = ledger.reruns_of_unit(unit)
    for path in (unit_dir / 'cells').glob('*.json'):
        row = read_json(path, allow_sealed=allow_sealed)
        if path.stem not in rerun:
            cached[path.stem] = row
    cells, lock, stop_reason = list(cached.values()), threading.RLock(), [None]
    started = time.strftime('%Y-%m-%dT%H:%M:%S')

    def one(bench, item, arm, *, first):
        tag = cell_tag(bench, item['task_id'], arm)
        if tag in cached:
            return cached[tag]
        if ledger.stopped() or stop_reason[0]:
            return None
        try:
            row = build_cell(bench, item, arm, tag)
        except Stop:
            return None
        except ReplayRefused as error:  # the resume replay 'on' refused the cell's calls file: nothing was sent
            with lock:
                write_json(unit_dir / 'stop.json', {'reason': REPLAY_REFUSED, 'failure': type(error).__name__,
                           'cell': tag, 'bench': bench, 'at': time.strftime('%Y-%m-%dT%H:%M:%S'),
                           'detail': str(error)[:300]}, allow_sealed=allow_sealed)
            ledger.stop(REPLAY_REFUSED)
            return None
        except tuple(STOP_KINDS) as error:  # a route-B stop: the unit stops with its kind, the chain pauses
            reason = stop_kind(error)
            with lock:
                write_json(unit_dir / 'stop.json', {'reason': reason, 'failure': type(error).__name__, 'cell': tag,
                           'bench': bench, 'at': time.strftime('%Y-%m-%dT%H:%M:%S')}, allow_sealed=allow_sealed)
            ledger.stop(reason)
            return None
        except Exception as error:
            row = {'bench': bench, 'item_id': item['task_id'], 'arm': arm, 'correct': None, 'failure': type(error).__name__,
                   'configuration_error': True, 'infrastructure_unknown': False, 'sends': [], 'tokens': 0}
        row.setdefault('tag', tag)
        with lock:
            if row.get('sends'):
                write_json(unit_dir / 'cells' / (tag + '.json'), row, allow_sealed=allow_sealed)
                cells.append(row)
            else:
                write_json(unit_dir / 'unsubmitted' / (tag + '.json'), row, allow_sealed=allow_sealed)
            ledger.consume_reruns(unit, (tag,))  # the cell ran again: its rerun entry is consumed
            ledger.observe_infrastructure(bool(row.get('infrastructure_unknown')))
            if first and row.get('configuration_error'):
                stop_reason[0] = 'first_cell_configuration:' + bench
                write_json(unit_dir / 'failure.json', {'reason': stop_reason[0], 'failure': row.get('failure'),
                           'cell': tag, 'bench': bench}, allow_sealed=allow_sealed)
                ledger.stop(stop_reason[0])
        return row

    def item_arms(bench, item, skip=()):
        for arm in arm_order(item['task_id'], item_arm_list(item)):
            if arm not in skip:
                one(bench, item, arm, first=False)

    def item_arm_list(item):
        return item['_arms']

    by_bench = {}
    for bench, item, arms in jobs:
        by_bench.setdefault(bench, []).append({**item, '_arms': list(arms)})
    try:
        with ThreadPoolExecutor(max_workers=max(widths.values()) if widths else 1, thread_name_prefix='typed-unit') as pool:
            for bench, items in by_bench.items():
                if ledger.stopped() or stop_reason[0]:
                    break
                width = widths.get(bench, 1)
                first_item = items[0]
                first_arm = arm_order(first_item['task_id'], first_item['_arms'])[0]
                first_row = one(bench, first_item, first_arm, first=True)
                if ledger.stopped() or stop_reason[0]:
                    break
                confirmed = _responded(first_row)
                queue = [(first_item, (first_arm,))] + [(item, ()) for item in items[1:]]
                running = set()
                for item, skip in queue:
                    if ledger.stopped() or stop_reason[0]:
                        break
                    if not confirmed:  # serial until an actual model response arrived for this bench
                        item_arms(bench, item, skip)
                        confirmed = any(_responded(row) for row in cells if row.get('bench') == bench)
                        continue
                    while len(running) >= width:
                        done, running = wait(running, return_when=FIRST_COMPLETED)
                        for future in done:
                            future.result()
                    running.add(pool.submit(item_arms, bench, item, skip))
                for future in running:
                    future.result()
    except BaseException:
        ledger.stop('interrupted')
        raise
    reason = stop_reason[0] or (ledger.state['stop_reason'] if ledger.stopped() else None)
    expected = sum(len(arms) for _, _, arms in jobs)
    write_json(unit_dir / 'done.json', {'unit': unit_dir.name, 'started': started,
               'finished': time.strftime('%Y-%m-%dT%H:%M:%S'), 'cells': len(cells), 'expected_cells': expected,
               'missing_cells': expected - len(cells), 'stop_reason': reason, 'ledger': dict(ledger.state),
               **(meta or {})}, allow_sealed=allow_sealed)
    return cells, reason


def _responded(row):
    """A cell confirms its bench's configuration only with an actual model response AND no configuration failure
    after it (a judge or scorer exception on a delivered reply confirms nothing)."""
    return (bool(row) and not row.get('configuration_error')
            and any((s.get('receipt') or {}).get('ok') and (s.get('receipt') or {}).get('response') is not None
                    for s in row.get('sends', [])))
