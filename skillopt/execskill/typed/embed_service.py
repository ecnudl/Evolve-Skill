#!/usr/bin/env python3
"""Standalone embedding service for typed-v2 (runs in the separate CPU venv, never imports skillopt).

stdin: {"texts": [...]}  ->  stdout: {"vectors": [[...], ...], "model": ..., "revision": ..., "dim": n}
Run with /data/arch-probe-env/bin/python and HF_HUB_OFFLINE=1 HF_HOME=/data/arch-probe-env/hf (design §4).
"""
import json
import os
import sys

MODEL = 'sentence-transformers/all-MiniLM-L6-v2'
REVISION = '1110a243fdf4706b3f48f1d95db1a4f5529b4d41'


def main():
    os.environ.setdefault('HF_HUB_OFFLINE', '1')
    os.environ.setdefault('TOKENIZERS_PARALLELISM', 'false')
    request = json.load(sys.stdin)
    texts = request['texts']
    if not isinstance(texts, list) or any(not isinstance(t, str) for t in texts):
        raise SystemExit('texts must be a list of strings')
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(MODEL, revision=REVISION, device='cpu', local_files_only=True)
    vectors = model.encode(texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False,
                           convert_to_numpy=True, device='cpu') if texts else []
    out = {'vectors': [[float(x) for x in row] for row in vectors], 'model': MODEL, 'revision': REVISION,
           'dim': int(vectors.shape[1]) if len(texts) else 0}
    json.dump(out, sys.stdout)


if __name__ == '__main__':
    main()
