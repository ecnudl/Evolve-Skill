"""Five-benchmark executable-skill and examiner co-evolution, route B (protocol ``fivebench-execskill-v1``).

A sibling package of ``skillopt.coevo5``: it imports the frozen v3 modules that carry no protocol identity (ledger,
call wrapper, outcomes, statistics, roles, leakage) read-only and copies, under its own version, every module that
would stamp a record (docs/handoff/execskill-registration-v1-20261021.md §1, "closed-set copy"). The registration fixes
every threshold; ``protocol`` transcribes them.
"""

VERSION = "fivebench-execskill-v1"
