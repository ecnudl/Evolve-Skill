"""Route-B stop classes (docs/handoff/execskill-registration-v1-20261021.md §3.4, §4.4; implementation plan §1, errors
row) on top of the ONE frozen exception set, which is re-exported here unchanged: ``ConfigurationError``,
``BudgetStop``, ``CleanupUnconfirmed``, ``AssumptionBroken`` and ``LedgerFailure`` are the classes of
``skillopt.coevo5.outcomes`` (outcomes.py:95-120), never redefined, so a stop raised by frozen code and one raised by
route-B code are caught by the same handlers.

The three new stops, each a unit pause for the owner (§4.4):
- ``SandboxUnavailable`` -- P4: the sandbox image is missing, docker does not start, a container cannot be removed, or
  the short-hold per-call sandbox slot stays busy for 600 s twice in a row (``slots.OrderedSlots.hold_short``). Waiting
  for an episode, live-container or native slot is never P4.
- ``PackageInvalid`` -- a procedure package that fails validation (§2.1: caps, hooks, module shape, edits per step).
- ``ConsumptionConflict`` -- another unit of the same chain asks for an item the consumption registry holds (§3.4).

A fourth, from the registrar's row "deepseek route B" (owner instructions 2026-10-22 17:0x and 17:3x):
- ``BalanceExhausted`` -- chain D's solver route reported an exhausted balance (``client.balance_signal``). It is
  never retried or re-sent, and the unit pauses with kind ``balance_exhausted``: neither a model failure nor an
  infrastructure unknown. The operator's ``switch-route`` and ``recover`` move chain D to its other route.

``STOP_KINDS`` is the frozen ``cells.STOP_KINDS`` (cells.py:45-46) plus the four new kinds; ``stop_kind`` looks an
exception up by its class and then its base classes (as units.py:149 does), None for an exception that is no stop.
"""
from __future__ import annotations

from skillopt.coevo5.cells import STOP_KINDS as FROZEN_STOP_KINDS
from skillopt.coevo5.outcomes import AssumptionBroken, BudgetStop, CleanupUnconfirmed, ConfigurationError, LedgerFailure

__all__ = ["AssumptionBroken", "BalanceExhausted", "BudgetStop", "CleanupUnconfirmed", "ConfigurationError",
           "ConsumptionConflict", "LedgerFailure", "PackageInvalid", "STOP_KINDS", "SandboxUnavailable", "stop_kind"]


class SandboxUnavailable(RuntimeError):
    """P4 (§4.4): the sandbox cannot serve the unit; the unit pauses and the owner decides."""


class PackageInvalid(ValueError):
    """A package or procedure that fails validation (§2.1)."""


class ConsumptionConflict(RuntimeError):
    """§3.4: an item already held by another unit of the same chain's consumption namespace."""


class BalanceExhausted(RuntimeError):
    """Registrar row "deepseek route B" (2026-10-22 17:3x): the solver route's provider reported an exhausted balance;
    never retried, the unit pauses (kind ``balance_exhausted``) until the operator switches the route and recovers."""


STOP_KINDS = {**FROZEN_STOP_KINDS, SandboxUnavailable: "sandbox", PackageInvalid: "package",
              ConsumptionConflict: "consumption", BalanceExhausted: "balance_exhausted"}


def stop_kind(error):
    """The stop kind of ``error`` (its class's entry, else its nearest base class's), None when it is no stop."""
    for cls in type(error).__mro__:
        if cls in STOP_KINDS:
            return STOP_KINDS[cls]
    return None
