# Report of piece P3r (read rows: no C0 anchor, interleaved + full), as returned by its builder 2026-11-15 ~03:4x

Worktree <repo-root> (branch research/typed-skills-v3-reads, on bd421da).
Whole typed selection 1038 passed (1019 + 19 new); no existing test edited.

Item 2 (interleaved + full): nothing was broken in this tree; both chains, five steps, complete and resume, smoke mode
and run mode (real reads.read_panel behind data.TestAccess under consent), base historical, unit_shared, repair and
archive index; the new tests pin that combination.

(a) readplan.py: READ_ANCHORS = (('C0','C'), ('C',)), READ_ANCHORS_DEFAULT; anchor_tuple refuses strings and
unregistered lists; read_events(anchors) = anchors + S1..S5; check_read_anchors: ('C',) needs read_plan 'full' and
base_card 'historical'. prepare.py: read_anchors_of(manifest) (absent = ('C0','C'); a manifest's `arms` must equal the
anchors' read events); prepare(..., read_anchors=('C0','C')) refuses a bad value before writing; under ('C',) the
manifest gets read_anchors ['C'] and arms C..S5; the default manifest unchanged; load_manifest checks it. reads.py:
consent(shared, arms=READ_ARMS): `arms` one of the two event lists and the record names exactly them, in order;
panel_tasks(..., arms=) refuses, before consent and before TestAccess, a label whose event is not planned (under C also
the label without an event, `test-read-plan`); open_panel refuses an unplanned event and passes the planned arms on.
readout.py: C-only functions _open_c, _five_by_five_c, _formulas_c, _bench_metrics_c, _macro_c, _cl_metrics_c chosen
when the state records the anchors; read_anchors key, read_events in status, markdown; _open_c refuses a C0 read unit.
chain.py: _read_anchors; _Run.anchor_events / read_events; read_anchors() loops over the sealed anchors; consent_first
names the planned arms; run() reads the option before writing; _open_state records read_anchors only when C alone and
refuses a resume started with other anchors. scripts/run_typed.py: READ_ANCHORS = ('C0,C', 'C'), prepare
--read-anchors, summary, read-count denominator 30 for C alone (35 default). NEW tests/test_typed3_reads.py (19).

(b) TMPDIR=/tmp/typed3-reads-neutral python3 -m pytest tests/test_typed3_reads.py -> 19 passed; tests/test_typed*.py ->
1038 passed (168 s). Python 3.10: new file + readout, reads, schedule tests 84 passed. Coverage: both chains with C
alone (events C, S1..S5, none for C0; every request of step k before every request of S<k> before step k+1's); every
read cell fresh (one send) and mounting only its own step's library; a hand-computed readout (contrasts, 5x5, metrics
with S0 := C); both chains on one root in run mode under the six-arm consent (60 consent checks, 30 panel openings per
chain); consent accepted for C..S5, refused when an arm is missing / reordered / extra or typed-v2's seven arms (the
chain pauses at read-C with nothing opened and completes after the consent is fixed); learn_first refused at its start
check with zero sends; a C0 read refused before any panel opens; six real SIGKILL cases (inside a read cell of C and of
S2, both chains; after an S2 mirror before the event's marks; right after step-2; right after step-0) each resuming to
an uninterrupted run's files and done units; default keeps typed-v2's shape. Scratch: 13 injected bugs all caught.

(d) Added guards (none weakened): C alone only with full + historical; `arms` must match the anchors; unplanned events
refused at the panel path; a C0 unit refused by the readout. typed-v1 readout functions left byte-equal (a test pins
their source): separate C-only functions. Default still calls consent(shared) with one argument (a test patches it).
The state records the anchors (a fake smoke's readout has no manifest). __init__.py, smoke.py and living docs not
touched. The C-only readout drops the C0 level, gain_over_C0 and the C-vs-C0 same-request noise; 5x5 has S<k> - C and
S<k> - S<k-1> (S0 := C); forward transfer and step-1 plasticity are measured against C.

(e) Risks: merge conflicts likely but small (_open_state, run() option lines, prepare() signature and fields,
run_typed's named tuple and parser); the P3b preset must pass read_anchors=('C',); the real consent must list exactly
["C","S1","S2","S3","S4","S5"] in order; real mount.solve, real panels, real sheet qualification and ALFWorld resets not
exercised; kills tested in smoke mode only.

(f) prepare flags: --schedule interleaved --read-plan full --read-anchors C --base-card historical (+ --memory-lock
unit_shared --program-learning repair --archive index; --smoke for the smoke root).
