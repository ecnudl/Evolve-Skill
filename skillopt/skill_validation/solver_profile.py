"""Explicit, frozen solver settings; legacy callers retain their old protocol.

Reliability changes are uniform across conditions and never depend on audit
labels or a failed response. They do not enlarge the updater/research budget.
"""
from __future__ import annotations

from dataclasses import dataclass

from .models import require


@dataclass(frozen=True)
class SolverProfile:
    name: str = "legacy"
    max_tokens: int = 2048

    def __post_init__(self):
        require(type(self.name) is str and self.name in {"legacy", "reliable_v1"}, "Unknown solver profile")
        require(type(self.max_tokens) is int and 1 <= self.max_tokens <= 16000, "Invalid solver token cap")
        require(self.name != "legacy" or self.max_tokens == 2048, "Legacy solver cap must remain 2048")

    @classmethod
    def named(cls, name="legacy", max_tokens=None):
        return cls(name, (4096 if name == "reliable_v1" else 2048) if max_tokens is None else max_tokens)

    @property
    def enabled(self):
        return self.name != "legacy"

    def initial_options(self):
        return {"max_tokens": self.max_tokens, "format_policy": "compact_json_v1"} if self.enabled else {}

    def revision_options(self):
        return {**self.initial_options(), "allow_clean_timeout_revision": True,
                "public_selection_policy": "public_nonregression_v1"} if self.enabled else {}

    def output_token_limits(self):
        return {kind: self.max_tokens for kind in ("public-initial", "public-revision")} if self.enabled else {}

    def api_options(self):
        return {"initial_health_policy": "completed_response_v1"} if self.enabled else {}

    def to_dict(self):
        return {"name": self.name, "initial_max_tokens": self.max_tokens,
                "revision_max_tokens": self.max_tokens, "format_policy": "compact_json_v1" if self.enabled else None,
                "allow_clean_timeout_revision": self.enabled,
                "public_selection_policy": "public_nonregression_v1" if self.enabled else None,
                "max_revision_opportunities": 1,
                "initial_health_policy": "completed_response_v1" if self.enabled else "legacy_success_only"}
