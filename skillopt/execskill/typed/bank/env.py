"""The item bank's own environment (owner 2026-11-13: "一个造题模块和专门用来运行造题的一个环境").

A bank is built in its OWN root, never inside a chain root: its own token ledger with its own cap, its own
write-once records, and a fixed tool set. What the environment is, and is not:

- inputs: the pinned TRAINING-SIDE practice pools only (``prepare.load_pool`` with the pin of a typed manifest) and
  page references of the id manifests; no test-side panel, cell or reading is opened, and every path written goes
  through ``units.write_json`` (the path-word guard of the typed package);
- tools, all fixed code: the exact evaluator of derivations (``oqa``), the benchmark's own judge and solver request
  builder from the BOUND machinery snapshot (the same code the chains score with), and the recorded model clients;
- a fixed pipeline with a bounded number of repair requests, not a free agent: every model request and reply is
  stored before and after the call (``units.CallRecorder``), a finished call is never sent again, and a role is
  never shown a solver chain's outcome on its items (the firewall of BANK-PILOT.md);
- one process per ledger (``units.Ledger`` is thread-safe and has no file lock).

A stored reply is used again only for the IDENTICAL request (the sha256 of its system and user text): this is what
lets a new root carry the stored calls of an earlier one (``carry``) and send only what its code asks differently.

``BankEnv.call`` is one resumable role request; ``BankEnv.solver_call`` hands the frozen solver shell a recorded
``call(system, user) -> receipt``; ``BankEnv.once`` is a write-once JSON record; ``BankEnv.fan`` runs tasks on a
few threads, the first one alone until it has returned (first real response before any concurrency).
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import re
import time
from pathlib import Path

from .. import units

FENCE = re.compile(r'```(?:json|JSON)?[ \t]*\n(.*?)```', re.S)


def read_object(text):
    """The JSON object of a role reply: the reply itself, the body of a fenced block, or the text from its first
    '{' to its last '}'. None when none of them parses to an object (tolerant reading, strict use)."""
    if not isinstance(text, str):
        return None
    candidates = [text.strip()] + [body.strip() for body in FENCE.findall(text)]
    if '{' in text and '}' in text:
        candidates.append(text[text.index('{'):text.rindex('}') + 1])
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _terminal_receipt(sends, request):
    """The stored receipt of ``request`` (its sha256) when it is a verdict of the model: delivered (``ok``), or a
    model-side noncompletion. None for no send, an unfinished send or an infrastructure failure."""
    for send in sends:
        receipt = send.get('receipt')
        if send.get('request_sha256') != request or not isinstance(receipt, dict):
            continue
        if receipt.get('ok') is True or (receipt.get('error_type') or 'unknown') in units.MODEL_SIDE_ERRORS:
            return receipt
    return None


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def text_sha256(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


class BankEnv:
    """One bank root with its ledger and clients. ``clients``: {'role': client, 'solver': client}, each with
    ``call(system, user) -> receipt`` and ``max_tokens`` (the frozen client contract)."""

    def __init__(self, root, ledger, clients, *, width=4):
        self.root, self.ledger, self.clients, self.width = Path(root), ledger, dict(clients), width
        self.reused = {'role': 0, 'solver': 0}   # requests of this process answered from a stored reply (not sent)

    # ---- records ---------------------------------------------------------------------------------------------------
    def path(self, *parts):
        return self.root.joinpath(*parts)

    def exists(self, *parts):
        return self.path(*parts).exists()

    def read(self, *parts):
        return units.read_json(self.path(*parts))

    def once(self, parts, compute):
        """The record at ``parts`` (a tuple of path parts): read when it exists, else computed and written once."""
        path = self.path(*parts)
        if path.exists():
            return units.read_json(path)
        value = compute()
        units.write_json(path, value)
        return value

    # ---- model calls -----------------------------------------------------------------------------------------------
    def _recorder(self, unit, tag, client):
        out = self.path(unit, 'calls', tag + '.json')
        target = self.clients[client]
        recorder = units.CallRecorder(target.call, self.ledger, max_tokens=target.max_tokens, tag=tag, unit=unit,
                                      out_path=out)
        if out.exists():  # a new recorder would replace the file: keep the earlier sends (chain._keep_earlier_sends)
            recorder.sends.extend(units.read_json(out))
        return recorder

    def call(self, unit, tag, system, user, *, client='role'):
        """One resumable role request: {'reply', 'failure', 'request_sha256'}. A delivered reply and a model-side
        failure are final (written once, never sent again); an infrastructure failure is not, so a later run sends
        the request again. Raises ``units.Stop`` at the token cap, before anything is sent."""
        from .. import writers
        request = units.sha256_text(system + '\x00' + user)
        done = self.path(unit, 'calls', tag + '.result.json')
        if done.exists():
            stored = units.read_json(done)
            if stored.get('request_sha256') == request:
                self.reused['role'] += 1
                return stored
            # The tag's stored reply answers ANOTHER request (a root that carries the calls of an earlier root whose
            # code asked differently, or a web search that returned other hits on a second run): it is never used
            # for this one. This request gets its own tag and is sent.
            tag = '%s-x%s' % (tag, request[:12])
            done = self.path(unit, 'calls', tag + '.result.json')
            if done.exists():
                self.reused['role'] += 1
                return units.read_json(done)
        recorder = self._recorder(unit, tag, client)
        receipt = _terminal_receipt(recorder.sends, request)
        if receipt is not None:
            # the call was delivered and the process ended before its result was written: the stored reply is the
            # reply (review 2026-11-13: sending again would pay twice and could bring another text)
            self.reused['role'] += 1
        else:
            receipt = recorder(system, user)
        value = {'reply': writers.reply_of(receipt), 'failure': writers.reply_failure(receipt), 'request_sha256': request}
        if not (value['failure'] or '').startswith('infrastructure:'):
            units.write_json(done, value)
        return value

    def solver_call(self, unit, tag, *, client='solver'):
        """A recorded ``call(system, user) -> receipt`` for the frozen solver shell (one recorder per task). A
        request this task already sent and got a TERMINAL receipt for (a delivered reply, or a model-side
        noncompletion such as a reply cut at the token bound) is answered from that receipt: a stage that is run
        again pays for nothing twice and never redraws an outcome. Only an infrastructure failure is sent again.
        ``.recorder`` is the task's recorder (its ``infrastructure_unknown()`` tells the two kinds of failure
        apart)."""
        recorder = self._recorder(unit, tag, client)

        def recorded(system, user):
            receipt = _terminal_receipt(recorder.sends, units.sha256_text(system + '\x00' + user))
            if receipt is not None:
                self.reused['solver'] += 1
                return receipt
            return recorder(system, user)
        recorded.recorder = recorder
        return recorded

    # ---- fan-out ---------------------------------------------------------------------------------------------------
    def fan(self, tasks, work, *, label):
        """``work(task)`` for every task on ``self.width`` threads; the first task runs alone. Returns the results in
        task order. ``units.Stop`` (the cap, a ledger stop) ends the fan: tasks not yet started are not started, and
        the Stop is raised after the running ones returned."""
        tasks, results, stop = list(tasks), {}, []
        started = time.time()

        def guarded(index):
            if stop:
                return None
            try:
                return work(tasks[index])
            except units.Stop as halted:
                stop.append(halted)
                return None

        if tasks:
            results[0] = guarded(0)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, self.width)) as pool:
            futures = {pool.submit(guarded, index): index for index in range(1, len(tasks))}
            for done, future in enumerate(concurrent.futures.as_completed(futures), 2):
                results[futures[future]] = future.result()
                if done % 10 == 0 or done == len(tasks):
                    print('%s %s: %d/%d tasks, %d s, charged %d' % (
                        time.strftime('%H:%M:%S'), label, done, len(tasks), time.time() - started,
                        self.ledger.state['charged']), flush=True)
        if stop:
            raise stop[0]
        return [results[index] for index in range(len(tasks))]


# ---- carrying stored calls into a new root -------------------------------------------------------------------------
CARRIED_FOLDERS = ('calls', 'archive')   # stored requests and replies; the research stage's archived pages and lists


def carry(source, target):
    """Copy the stored calls (and the research archive and research records) of the bank root ``source`` into the
    freshly prepared root ``target`` and write ``<target>/carried.json``. Nothing else is copied: every trace, item,
    record and check verdict is computed again by the target's code, which reuses a carried reply only for the
    identical request (``BankEnv.call`` / ``solver_call``). The research records (findings, brief) ARE carried as
    data: the web is not searched a second time, so both roots write their questions from the same brief. The
    target's ledger starts at zero and counts only what the target sends."""
    import shutil
    source, target = Path(source), Path(target)
    assert (source / 'bank.json').is_file() and (target / 'bank.json').is_file(), 'Two prepared bank roots'
    assert not (target / 'carried.json').exists() and not (target / 'ledger.json').exists(), 'A fresh target root'
    copied = {}
    for folder in sorted(p for p in source.rglob('*') if p.is_dir() and p.name in CARRIED_FOLDERS):
        relative = folder.relative_to(source)
        files = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix == '.json')
        units.checked_path(target / relative).mkdir(parents=True, exist_ok=True)
        for path in files:
            shutil.copyfile(path, units.checked_path(target / relative / path.name))
        copied[str(relative)] = len(files)
    records = {}
    research = source / 'research'
    for folder in sorted(p for p in research.iterdir() if p.is_dir() and p.name not in CARRIED_FOLDERS) if research.is_dir() else []:
        for path in sorted(folder.glob('*.json')):
            units.checked_path(target / 'research' / folder.name).mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, units.checked_path(target / 'research' / folder.name / path.name))
            records['research/%s/%s' % (folder.name, path.name)] = file_sha256(path)
    note = {'from': str(source.absolute()), 'from_version': units.read_json(source / 'bank.json').get('version'),
            'from_code': units.read_json(source / 'bank.json').get('code'), 'call_files': copied,
            'research_records_carried_as_data': records}
    units.write_json(target / 'carried.json', note)
    return note
