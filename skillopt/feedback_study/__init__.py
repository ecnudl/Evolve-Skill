"""Sidecar attribution studies of the learning-v10 verifier feedback (10/8; Codex design rounds post-S3 1-2).

Validation/train-only mechanism experiments that never change a frozen stage, the main table or a learning protocol:
``fixed_rubric`` (L1) judges identical fresh train outputs with frozen rubric versions. The package lives outside
``skillopt/continual_learning`` on purpose: ``contracts.sources()`` hashes every module there, so a new file inside it
would change the frozen learning source identity. It reuses the v10 mechanisms (judge prompts, check parser,
v7 delivery handling, ledger, solver adapter) and binds its own code by hash.
"""
