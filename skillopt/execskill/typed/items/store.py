"""Where the item stage's tools write (``ItemStore``) and what a chain made or selected before (``RunRegistry``).

``ItemStore`` is the output writer a maker receives (P2b hands it the unit directory): write-once JSON records and the
item files, every path through ``units.write_json`` / ``units.read_json`` (the path-word guard of the typed package).
An item file is named by its SLOT, ``<side>-<class>-<w<n>|x>-<nnn>`` (the n-th item of a class, side and weakness),
never by its item id: a practice id may hold a '/', a ':' or a word the path guard refuses ('lgp-test-...'), and a
slot is known before the item exists, so a resumed unit finds the slot it was making. Files of one unit:

- ``items/<slot>.json``: the item in its benchmark form (written once, before its slot record);
- ``records/<slot>.json``: the write-once slot record ``{'version', 'slot', 'record' (the item record, or None for a
  shortfall), 'shortfall' (None or the reason), 'attempts', 'detail'}``;
- maker records through ``once`` (e.g. ``zebralogic/language.json``, ``selector/batch-01.json``, ``selection.json``).

A unit interrupted between an item file and its slot record makes the same item again (makers are deterministic):
the existing file must hold exactly it (byte for byte), else the store refuses; an item file is never replaced.
"""
from __future__ import annotations

import json
import re

from skillopt.continual_eval.core import require

from .. import units
from . import CLASSES, RECORD_VERSION, SIDES, check_record

SLOT = re.compile(r'^(shown|judging)-(attack|guard|calibration)-(w[1-9][0-9]*|x)-[0-9]{3}$')


def slot_name(side, cls, weakness, number):
    """The slot of the ``number``-th (1-based) item of a side, class and weakness (None: 'x')."""
    require(side in SIDES and cls in CLASSES and type(number) is int and 1 <= number <= 999, 'A registered slot')
    name = '%s-%s-%s-%03d' % (side, cls, weakness or 'x', number)
    require(SLOT.match(name) is not None, 'A slot name of a registered side, class and weakness: ' + name)
    return name


class ItemStore:
    """The write-once files of one unit directory (see the module text)."""

    def __init__(self, root):
        self.root = units.checked_path(root)

    def path(self, *parts):
        return units.checked_path(self.root.joinpath(*parts))

    def exists(self, *parts):
        return self.path(*parts).exists()

    def read(self, *parts):
        return units.read_json(self.path(*parts))

    def once(self, parts, compute):
        """The record at ``parts`` (a tuple of path parts): read when it exists, else computed and written once (the
        contract of ``bank.env.BankEnv.once``, so ``zebra_build.stage_language`` takes this store as its env)."""
        path = self.path(*parts)
        if path.exists():
            return units.read_json(path)
        value = compute()
        units.write_json(path, value)
        return value

    # ---- items and slot records ----------------------------------------------------------------------------------
    def slot(self, name):
        """The stored slot record, or None."""
        require(SLOT.match(name) is not None, 'A slot name: ' + str(name))
        path = self.path('records', name + '.json')
        return units.read_json(path) if path.exists() else None

    def write_item(self, name, item):
        """Write the item of a slot once. An existing file must hold exactly this item -- the bytes
        ``units.write_json`` would write -- and is left as it is; a file with other content is refused (an item a slot
        record may already bind by its hash is never replaced)."""
        require(SLOT.match(name) is not None, 'A slot name: ' + str(name))
        path = self.path('items', name + '.json')
        if path.exists():
            text = json.dumps(item, ensure_ascii=False, indent=1, sort_keys=True) + '\n'   # units.write_json's form
            require(path.read_bytes() == text.encode('utf-8'), 'The item file of slot %s holds another item' % name)
            return
        units.write_json(path, item)

    def item(self, name):
        require(SLOT.match(name) is not None, 'A slot name: ' + str(name))
        return units.read_json(self.path('items', name + '.json'))

    def write_slot(self, name, *, record, shortfall, attempts, detail=None):
        """Write a slot record once: an item record (its item file written before) or a shortfall reason. A stored
        slot record is never replaced; a second write must carry the same content."""
        require(SLOT.match(name) is not None, 'A slot name: ' + str(name))
        require((record is None) != (shortfall is None), 'A slot holds an item record or a shortfall')
        if record is not None:
            check_record(record)
            require(self.exists('items', name + '.json'), 'The item file of a slot is written before its record')
        value = {'version': RECORD_VERSION, 'slot': name, 'record': record, 'shortfall': shortfall,
                 'attempts': list(attempts), 'detail': detail}
        stored = self.slot(name)
        if stored is not None:
            require(stored == value, 'The slot %s holds another record' % name)
            return stored
        units.write_json(self.path('records', name + '.json'), value)
        return value


class RunRegistry:
    """What one chain made or selected before (any step, any round, replaced items included): item ids, the sides of
    every family, and the text hashes of made puzzles (a ZebraLogic certificate's ``text_sha256``). Built by P2b from
    the earlier item records of the chain (``RunRegistry(records)``); a maker adds every item it makes or selects, so
    two items of one step never coincide either."""

    def __init__(self, records=()):
        self.ids, self.texts, self.families = set(), set(), {}
        for record in records:
            self.add(record)

    def add(self, record):
        """Register one item record; refused (nothing changed) when its id or its made text is registered already."""
        check_record(record)
        require(record['item'] not in self.ids, 'An item is made or selected once in a run: ' + record['item'])
        text = (record.get('certificate') or {}).get('text_sha256')
        require(text is None or (isinstance(text, str) and text not in self.texts), 'A made text once in a run')
        self.ids.add(record['item'])
        self.families.setdefault(record['family'], set()).add(record['side'])
        if text is not None:
            self.texts.add(text)

    def family_sides(self, family):
        return frozenset(self.families.get(family, ()))

    def summary(self):
        return {'ids': len(self.ids), 'texts': len(self.texts), 'families': len(self.families)}
