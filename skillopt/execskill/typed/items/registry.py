"""The maker registry of the item stage: ``MAKERS[bench]`` (read through ``items.MAKERS``).

Every maker has the attributes ``bench`` and ``built`` and three entry points:

- ``capability_sheet(*, pool, learn_ids, gate_ids) -> sheet``: what the analyst may ask for (``plan.check_sheet``);
- ``public_kind(item) -> dict``: what the analyst is told beside a learn item's public text (ZebraLogic: its size;
  ALFWorld: its task type; others: nothing);
- ``make(inp: items.MakeInput) -> result``: the step's items, ``{'bench', 'status': 'made' | 'no_items', 'reason',
  'records', 'slots', 'shortfalls', 'made_counts', 'record'}``.

OfficeQA and SpreadsheetBench have no maker yet (CHAIN-DECISIONS T5: OfficeQA's use depends on the audit, the
sheet maker is another piece): their entry returns no items with the reason ``maker_not_built``, recorded, no error.
"""
from __future__ import annotations

from . import no_items
from .select_items import ALFWorldSelector, SearchQASelector
from .zebra_items import ZebraMaker

NOT_BUILT = 'maker_not_built'


class NotBuilt:
    """The entry of a bench whose maker does not exist: no capability, no items, a recorded reason."""

    built = False

    def __init__(self, bench):
        self.bench = bench

    def capability_sheet(self, *, pool=None, learn_ids=None, gate_ids=None):
        return {'maker': None, 'what': 'No new items are made or picked for this kind of task in this step.',
                'fields': {}}

    def public_kind(self, item):
        return {}

    def make(self, inp):
        return no_items(inp, NOT_BUILT)


MAKERS = {'searchqa': SearchQASelector(), 'officeqa': NotBuilt('officeqa'), 'zebralogic': ZebraMaker(),
          'spreadsheetbench': NotBuilt('spreadsheetbench'), 'alfworld': ALFWorldSelector()}
