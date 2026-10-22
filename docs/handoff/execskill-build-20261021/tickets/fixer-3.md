# Ticket fixer-3 → owner / registrar: SearchQA replies without an answer tag get two guesses under scorer v2

From the fixer (2026-10-22). Statistics review finding 6; registration §4.4 (Codex F7); `judge.py:28-29`, `:84-91`;
note A7 lines 107-109.

The fixer did **not** change the code, because the registration contradicts itself here and only the owner or the
registrar can choose. Under scorer v2 a SearchQA reply holding JSON X and a final line Y passes when either X or Y is
correct:
- `{"answer": "Lyon"}\nParis` passes on the official last line;
- `{"answer": "Paris"}\nLyon` passes through the JSON rescue.

§4.4 promises both "v2 >= official" and "a second format never buys a second guess". On SearchQA these two promises
cannot both hold.

Choose one (for a v1.1 note):
- (a) The tagless last line is SearchQA's official carrier. JSON is consulted only when the last line is itself the
  JSON object. No second guess; v2 >= official still holds on every reply whose last line is the JSON.
- (b) Keep the rescue, and report a per-arm "two-channel" pass count (replies whose JSON and last line differ and
  only one is correct) next to every SearchQA number.

After the ruling, the main agent adds a T-JUDGE fixture for the chosen rule. Under (b), `readout.arm_table` also
gains the count.
