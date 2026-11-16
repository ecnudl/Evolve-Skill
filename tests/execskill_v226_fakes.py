"""Authored in-process worker with the real v2.22 hook result semantics."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

from skillopt.continual_eval.core import require
from skillopt.execskill import diagnostics, profiles as p, step, units, v222_cards
from skillopt.execskill.sandbox import worker_v222
from skillopt.validator_pilot.api import digest


class DiagnosticsWorker:
    def __init__(self, *, diagnostics_configuration=None, value_cap=1024, **options):
        self.diagnostics_configuration = diagnostics_configuration
        self.value_cap, self.options, self.calls = value_cap, options, []

    def start(self, package, **options):
        self.package = package
        return self

    def call(self, proc_id, fn, args, *, timeout_s, diagnostics_v215=False):
        self.calls.append((proc_id, fn, deepcopy(args), diagnostics_v215))
        proc = next(row for row in self.package.procedures if row.id == proc_id)
        result = worker_v222.execute(compile(proc.source, '<authored-v226>', 'exec'), fn, args,
            self.value_cap, diagnostics_spec=diagnostics.worker_spec() if diagnostics_v215 else None)
        return {**result, 'value_sha256': digest(result['value']) if result.get('ok') else None,
                'cpu_ms': 0, 'rss_kib': 1}

    def call_diagnostics(self, proc_id, fn, args, *, timeout_s, bench='zebralogic'):
        require(diagnostics.enabled(self.diagnostics_configuration)
                and fn == 'before_call' and bench == 'zebralogic',
                'Diagnostics belong to the v2.15 Zebra worker and note hook')
        return self.call(proc_id, fn, args, timeout_s=timeout_s, diagnostics_v215=True)

    def close(self):
        pass


class Workers:
    def __init__(self):
        self.opened = []

    @contextmanager
    def __call__(self, package, **options):
        worker = DiagnosticsWorker(**options).start(package)
        self.opened.append(worker)
        try:
            yield worker
        finally:
            worker.close()


class Registry:
    def __init__(self):
        self.calls = []

    def bound(self, root):
        return self

    def register(self, *args, **kw):
        self.calls.append(('register', args, kw))

    def dispatch(self, *args, **kw):
        self.calls.append(('dispatch', args, kw))

    def decide(self, *args, **kw):
        self.calls.append(('decide', args, kw))


def authored_step(root, parent, *, bench='spreadsheetbench', k=4, configuration='main-v10'):
    root = Path(root)
    workers = Workers()
    setting = units.Setting(run=digest(['authored-v226', bench, k]), root=root, shared=root/'shared',
        pools={}, cards={b: v222_cards.format_text(b) for b in p.MAIN_V5_ORDER},
        runtime={b: {} for b in p.MAIN_V5_ORDER}, clients=None, budget=None, slots={}, sandbox={},
        evidence='engineering_fixture', extra={'configuration': configuration, 'slot_root': root/'slots'})
    st = step._Step(setting, step.Services(registry=Registry(), sources=None, workers=workers),
                    'G', bench, k, parent, root/'G')
    # Pins are outside the authored fixture boundary; production unit creation,
    # worker binding, memory-lock wrapper and immutable unit receipts are real.
    st.verify = lambda: None
    return st, workers
