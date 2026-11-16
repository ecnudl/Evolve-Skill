# Cross-date replicate count: typed-v1 (read 2026-11-11/12) against typed-v2 (read 2026-11-13/14)

Zero-call count made on 2026-11-14 by `replicate_xdate.py <typed-v1 root> <typed-v2 root>` on the development machine.
For every test item of the rows C0 (format block only) and C (hand-written card) it takes the cells of the two runs
whose FIRST request is byte-identical and counts how often the judged outcome differs. A noise and drift reference
only: not a baseline, not a table row, and it selects nothing.

| chain | bench | event | typed-v2 unit | items | same 1st request | agree | right->wrong | wrong->right | unknown | flipped % |
|---|---|---|---|---|---|---|---|---|---|---|
| G | searchqa | C0 | C0 | 400 | 400 | 374 | 17 | 9 | 0 | 6.5 |
| G | searchqa | C | C | 400 | 400 | 378 | 17 | 5 | 0 | 5.5 |
| G | officeqa | C0 | C0 | 172 | 172 | 142 | 15 | 15 | 0 | 17.4 |
| G | officeqa | C | C | 172 | 172 | 141 | 17 | 14 | 0 | 18.0 |
| G | zebralogic | C0 | S2 | 200 | 200 | 129 | 36 | 35 | 0 | 35.5 |
| G | zebralogic | C | S2 | 200 | 200 | 132 | 36 | 32 | 0 | 34.0 |
| G | spreadsheetbench | C0 | C0 | 204 | 204 | 148 | 19 | 30 | 7 | 24.0 |
| G | spreadsheetbench | C | S5 | 204 | 204 | 150 | 23 | 23 | 8 | 22.5 |
| G | alfworld | C0 | C0 | 134 | 134 | 122 | 9 | 3 | 0 | 9.0 |
| G | alfworld | C | S5 | 134 | 134 | 129 | 3 | 2 | 0 | 3.7 |
| D | searchqa | C0 | C0 | 400 | 400 | 393 | 3 | 4 | 0 | 1.8 |
| D | searchqa | C | C | 400 | 400 | 393 | 4 | 3 | 0 | 1.8 |
| D | officeqa | C0 | C0 | 172 | 172 | 161 | 6 | 5 | 0 | 6.4 |
| D | officeqa | C | C | 172 | 172 | 151 | 13 | 8 | 0 | 12.2 |
| D | zebralogic | C0 | S5 | 200 | 200 | 168 | 17 | 15 | 0 | 16.0 |
| D | zebralogic | C | S5 | 200 | 200 | 173 | 13 | 14 | 0 | 13.5 |
| D | spreadsheetbench | C0 | C0 | 204 | 204 | 176 | 14 | 8 | 6 | 10.8 |
| D | spreadsheetbench | C | S5 | 204 | 204 | 165 | 14 | 18 | 7 | 15.7 |
| D | alfworld | C0 | C0 | 134 | 134 | 121 | 8 | 5 | 0 | 9.7 |
| D | alfworld | C | S4 | 134 | 134 | 130 | 0 | 4 | 0 | 3.0 |

"typed-v2 unit" is the fresh unit that stands for the row in the economy read plan (a row whose requests equal another
row's was not read again). "flipped %" = (right->wrong + wrong->right) / items; unknown cells are listed apart.
ALFWorld is a multi-turn task: only the first request is compared.

- Chain G (GLM-5.3): 2,220 replicate cells, 360 flips (16.2%): 192 right->wrong, 168 wrong->right.
- Chain D (deepseek-v4-flash): 2,220 replicate cells, 176 flips (7.9%): 92 right->wrong, 84 wrong->right.
