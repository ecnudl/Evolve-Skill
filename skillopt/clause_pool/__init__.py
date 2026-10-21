"""Clause pool (architecture X, 2026-10-16; design docs/handoff/two-architectures-design-20261016.md section 6).

A candidate Skill is decomposed into single edits relative to its parent (``edits``); each edit, applied alone to the
parent, is measured on the training items it is about (its trigger subset, ``skillopt.skill_features``) and admitted
by a pre-registered screen-and-confirm rule (``gate``); the final Skill is the parent plus the admitted edits. Zero
model calls here: measurements come from ``scripts/weak_solver_probe.py`` records.
"""
