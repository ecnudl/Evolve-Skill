"""Zero-call structural features of benchmark items and of Skill text (2026-10-16).

``tagger`` maps an item (question, answer, context) or a piece of Skill guidance onto one shared tag vocabulary
(operation family, answer form, rounding requirement, context shape); ``profile`` aggregates item tags into a
distribution and compares two distributions. The same vocabulary serves two uses: the feature-aware generator
matches generated items to the training items' distribution, and the clause pool restricts the measurement of one
Skill edit to the training items that edit is about (its trigger subset). Heuristic and deterministic by design: no
model call, no reference answer of a held-out or test item is ever read here.
"""
