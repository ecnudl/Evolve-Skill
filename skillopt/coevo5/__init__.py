"""Five-benchmark Skill-and-examiner co-evolution (protocol ``fivebench-coevolution-v1``).

A sibling package: it imports the frozen evaluation backends, the probe's HTTP client and the sealing helpers
read-only and never edits them (their source hashes are bound into earlier sealed runs). The registration that fixes
every threshold below is docs/handoff/coevo5-registration-20261016.md.
"""

VERSION = "fivebench-coevolution-v1"
