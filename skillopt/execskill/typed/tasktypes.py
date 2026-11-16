"""Task typing for typed-v2 (design §1.2): level 1 = structural signature of the public view, level 2 = data
source clusters inside a structure (centroid of normalized sentence embeddings, p95 unknown threshold).

Routing never sees a benchmark name, a task id or a path: only the public view's keys and text. Embeddings come
from a subprocess in the separate CPU venv (embed_service.py); tests inject a fake embedder. A type map of another
typed version (its ``version`` or ``module``) is refused at load (DESIGN 3.5).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import sys
from pathlib import Path

from . import (EMBED_DIM, EMBED_HF_HOME, EMBED_MODEL, EMBED_PYTHON, EMBED_REVISION, PUBLIC_TEXT_CONTEXT_CHARS,
               UNKNOWN_PERCENTILE, VERSION)
from .units import checked_path  # the sealed-path guard applies to the frozen type maps as to every other writer

SIGNATURES = ('question/context', 'puzzle_template', 'workbook_preview', 'admissible_commands')
TYPEMAP_VERSION = 'typed-v2-typemap'


def _sha(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def structural_signature(view):
    """Level 1: which public fields the item carries (probe 2's rule; a view without a known shape raises)."""
    if not isinstance(view, dict):
        raise ValueError('Public view must be a dictionary')
    keys = set(view)
    features = []
    if 'question' in keys and ('context' in keys or 'snippets' in keys):
        features.append('question/context')
    if 'choices' in keys:
        features.append('choices')
    if 'workbook_preview' in keys:
        features.append('workbook_preview')
    if keys & {'admissible_commands', 'admissible_commands_at_reset'}:
        features.append('admissible_commands')
    if ('question' in keys and 'columns' in keys) or 'puzzle' in keys:
        features.append('puzzle_template')
    if not features:
        raise ValueError('Public view has no registered structural signature')
    return '+'.join(sorted(features))


def public_text(view, *, context_chars=PUBLIC_TEXT_CONTEXT_CHARS):
    """The fixed public-text extractor per signature (probe 2's extractor, keyed by structure, not by bench)."""
    signature = structural_signature(view)
    if signature == 'question/context':
        context = view.get('context', view.get('snippets', ''))
        if isinstance(context, list):
            context = '\n'.join(str(value) for value in context)
        if not isinstance(view.get('question'), str) or not isinstance(context, str):
            raise ValueError('QA public question/context must be strings')
        return view['question'] + '\n' + context[:context_chars]
    if signature == 'puzzle_template':
        text = view.get('question', view.get('puzzle'))
        if not isinstance(text, str):
            raise ValueError('Puzzle public text must be a string')
        return text
    if signature == 'workbook_preview':
        preview = view['workbook_preview']
        if isinstance(preview, list):
            header = [{'sheet': row.get('sheet'), 'header': (row.get('preview') or [])[:1]} for row in preview]
        elif isinstance(preview, dict):
            header = [{'sheet': key, 'header': value[:1] if isinstance(value, list) else value}
                      for key, value in sorted(preview.items())]
        else:
            raise ValueError('Unrecognized workbook preview')
        return str(view.get('instruction', '')) + '\n' + json.dumps(header, ensure_ascii=False, sort_keys=True)
    if signature == 'admissible_commands':
        goal = view.get('task_text') or alfworld_goal(view.get('initial_observation', ''))
        return goal + '\n' + str(view.get('initial_observation', ''))
    raise ValueError('Unsupported signature for public text: ' + signature)


def alfworld_goal(observation):
    """The task sentence after 'Your task is to:' in the frozen initial observation (empty when absent)."""
    if not isinstance(observation, str):
        return ''
    marker = 'Your task is to:'
    index = observation.rfind(marker)
    return observation[index + len(marker):].strip() if index >= 0 else ''


def embed_texts(texts, *, embedder=None, python=EMBED_PYTHON, hf_home=EMBED_HF_HOME, timeout=1800):
    """Normalized vectors for texts. ``embedder(texts) -> vectors`` replaces the subprocess (tests, dry runs)."""
    texts = list(texts)
    if any(not isinstance(text, str) for text in texts):
        raise ValueError('Texts must be strings')
    if not texts:
        return []
    if embedder is not None:
        vectors = [list(map(float, row)) for row in embedder(texts)]
    else:
        service = Path(__file__).with_name('embed_service.py')
        env = {**os.environ, 'HF_HUB_OFFLINE': '1', 'HF_HOME': hf_home, 'TOKENIZERS_PARALLELISM': 'false'}
        completed = subprocess.run([python, str(service)], input=json.dumps({'texts': texts}), capture_output=True,
                                   text=True, timeout=timeout, env=env, check=False)
        if completed.returncode != 0:
            # only the last stderr line (the exception's own), never the tail: a read embeds test text and a crash
            # that echoed its input must not travel in an exception message
            last = (completed.stderr or '').strip().splitlines()
            raise RuntimeError('embedding service failed: ' + (last[-1][:300] if last else 'no stderr'))
        reply = json.loads(completed.stdout)
        if reply.get('model') != EMBED_MODEL or reply.get('revision') != EMBED_REVISION:
            raise RuntimeError('embedding service model/revision differs from the registered one')
        vectors = reply['vectors']
    if len(vectors) != len(texts) or any(len(row) != len(vectors[0]) for row in vectors):
        raise RuntimeError('embedding service returned a misaligned matrix')
    return [_normalize(row) for row in vectors]


def _normalize(row):
    norm = math.sqrt(sum(x * x for x in row))
    if not norm or not math.isfinite(norm):
        raise ValueError('Zero or non-finite embedding')
    return [x / norm for x in row]


def _distance(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _centroid(vectors):
    dim = len(vectors[0])
    mean = [sum(row[i] for row in vectors) / len(vectors) for i in range(dim)]
    return _normalize(mean)


def nearest_rank_percentile(values, percentile):
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile / 100 * len(ordered)))
    return float(ordered[rank - 1])


def source_id(pool_pin):
    """Opaque source label from the practice pool's pin (never a benchmark name)."""
    return 'src-' + _sha(pool_pin)[:8]


class TypeMap:
    """Sources (practice pools seen so far) with centroids and thresholds, grouped into types; frozen per step."""

    def __init__(self, data=None):
        self.data = data or {'version': TYPEMAP_VERSION, 'module': VERSION, 'step': 0,
                             'embedding': {'model': EMBED_MODEL, 'revision': EMBED_REVISION, 'dim': EMBED_DIM},
                             'unknown_percentile': UNKNOWN_PERCENTILE, 'sources': {}, 'types': {},
                             'assignment_rule': ('signature match, nearest source centroid, distance <= that '
                                                 "source's p95 within-source distance, else unknown")}

    # ---- sources -------------------------------------------------------------------------------------------
    def add_source(self, pool_pin, signature, vectors, *, step, pin_note=None):
        """Fit one source from its members' vectors; returns the source id. Re-adding an identical pin is refused."""
        if signature not in SIGNATURES:
            raise ValueError('Unknown structural signature: ' + str(signature))
        vectors = [_normalize(row) for row in vectors]
        if not vectors:
            raise ValueError('A source needs at least one member')
        sid = source_id(pool_pin)
        if sid in self.data['sources']:
            raise ValueError('Source already registered: ' + sid)
        centroid = _centroid(vectors)
        distances = [_distance(row, centroid) for row in vectors]
        self.data['sources'][sid] = {
            'signature': signature, 'centroid': centroid, 'members': len(vectors),
            'threshold': nearest_rank_percentile(distances, self.data['unknown_percentile']),
            'mean_distance': sum(distances) / len(distances), 'pool_pin': dict(pool_pin), 'added_step': step,
            **({'note': pin_note} if pin_note else {})}
        return sid

    def sources_with_signature(self, signature):
        return [sid for sid, src in self.data['sources'].items() if src['signature'] == signature]

    # ---- types ---------------------------------------------------------------------------------------------
    def type_of_source(self, sid):
        for tid, typ in self.data['types'].items():
            if sid in typ['sources']:
                return tid
        return None

    def types_with_signature(self, signature):
        return [tid for tid, typ in self.data['types'].items() if typ['signature'] == signature]

    def new_type(self, sid, *, step):
        src = self.data['sources'][sid]
        if self.type_of_source(sid) is not None:
            raise ValueError('Source already belongs to a type: ' + sid)
        tid = 't%02d' % (len(self.data['types']) + 1)
        self.data['types'][tid] = {'signature': src['signature'], 'sources': [sid], 'card': None, 'programs': [],
                                   'created_step': step, 'history': [{'step': step, 'event': 'created', 'source': sid}]}
        return tid

    def merge_source(self, sid, tid, *, step, evidence):
        typ = self.data['types'][tid]
        if self.data['sources'][sid]['signature'] != typ['signature']:
            raise ValueError('A source joins a type of its own signature only')
        if self.type_of_source(sid) is not None:
            raise ValueError('Source already belongs to a type: ' + sid)
        typ['sources'].append(sid)
        typ['history'].append({'step': step, 'event': 'merged', 'source': sid, 'evidence': evidence})
        return tid

    def set_card(self, tid, skill_id, *, step):
        typ = self.data['types'][tid]
        typ['history'].append({'step': step, 'event': 'card', 'from': typ['card'], 'to': skill_id})
        typ['card'] = skill_id

    def add_program(self, tid, skill_id, *, step):
        typ = self.data['types'][tid]
        if skill_id in typ['programs']:
            raise ValueError('Program already mounted: ' + skill_id)
        typ['programs'].append(skill_id)
        typ['history'].append({'step': step, 'event': 'program', 'skill': skill_id})

    # ---- assignment ----------------------------------------------------------------------------------------
    def assign(self, signature, vector):
        """{'type', 'source', 'distance', 'threshold', 'unknown_reason'}; only typed sources are routing targets."""
        candidates = [(sid, self.data['sources'][sid]) for sid in self.sources_with_signature(signature)
                      if self.type_of_source(sid) is not None]
        if not candidates:
            return {'type': None, 'source': None, 'distance': None, 'threshold': None,
                    'unknown_reason': 'unseen_signature'}
        vector = _normalize(vector)
        sid, src, distance = min(((sid, src, _distance(vector, src['centroid'])) for sid, src in candidates),
                                 key=lambda row: (row[2], row[0]))
        if distance > src['threshold']:
            return {'type': None, 'source': sid, 'distance': distance, 'threshold': src['threshold'],
                    'unknown_reason': 'distance_above_p95'}
        return {'type': self.type_of_source(sid), 'source': sid, 'distance': distance,
                'threshold': src['threshold'], 'unknown_reason': None}

    def assign_view(self, view, *, embedder=None):
        """Convenience for one item: signature + one embedding call (batch callers embed once per unit)."""
        signature = structural_signature(view)
        if not self.sources_with_signature(signature):
            return {'signature': signature, 'type': None, 'source': None, 'distance': None, 'threshold': None,
                    'unknown_reason': 'unseen_signature'}
        vector = embed_texts([public_text(view)], embedder=embedder)[0]
        return {'signature': signature, **self.assign(signature, vector)}

    # ---- persistence ---------------------------------------------------------------------------------------
    def freeze(self, path, *, step):
        self.data['step'] = step
        payload = dict(self.data)
        payload['record_sha256'] = _sha({k: v for k, v in payload.items() if k != 'record_sha256'})
        path = checked_path(path)  # a frozen type map never lives in a sealed read unit
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + '.tmp')
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + '\n', encoding='utf-8')
        os.replace(tmp, path)
        return payload['record_sha256']

    @classmethod
    def load(cls, path):
        data = json.loads(checked_path(path).read_text(encoding='utf-8'))
        expected = data.pop('record_sha256')
        if _sha(data) != expected:
            raise ValueError('Type map record hash differs: ' + str(path))
        if data.get('version') != TYPEMAP_VERSION or data.get('module') != VERSION:
            raise ValueError('Type map version differs: %s needs %s of module %s' % (path, TYPEMAP_VERSION, VERSION))
        return cls(data)

    def summary(self):
        return {tid: {'signature': typ['signature'], 'sources': list(typ['sources']), 'card': typ['card'],
                      'programs': list(typ['programs'])} for tid, typ in self.data['types'].items()}


if __name__ == '__main__':  # tiny manual check of the service wiring: python -m skillopt.execskill.typed.tasktypes
    print(json.dumps({'dim': len(embed_texts(['a test sentence'])[0])}))
    sys.exit(0)
