# typed-v2 versus v2.24 SkillOpt / GEPA (accuracy %, L side; "L/H" where unknown cells differ; "=" alias)

Cross-run, cross-date comparison: each method is also shown against the C row of its OWN run. v2.24 rows were read 2026-11-07/08; SkillOpt and GEPA started from an empty skill.

## Chain D

| row | SearchQA | OfficeQA | ZebraLogic | Sheet | ALFWorld | mean |
|---|---|---|---|---|---|---|
| typed-v2 C0 (format only) | 77.8 | 20.9 | 84.5= | 61.3/63.7 | 47.0 | 58.3 |
| typed-v2 C (hand card) | 81.5 | 29.1 | 84.5= | 57.8/59.8= | 67.2= | 64.0 |
| typed-v2 S1 | 83.8 | 33.7 | 84.5= | 57.8/59.8= | 67.2= | 65.4 |
| typed-v2 S2 | 84.0= | 34.3= | 84.5= | 57.8/59.8= | 67.2= | 65.6 |
| typed-v2 S3 | 84.0= | 34.3= | 84.5= | 57.8/59.8= | 67.2= | 65.6 |
| typed-v2 S4 | 84.0= | 34.3= | 84.5= | 57.8/59.8= | 67.2 | 65.6 |
| typed-v2 S5 | 84.0 | 34.3 | 84.5 | 57.8/59.8 | 76.1 | 67.4 |
| v2.24 skillopt C | 82.0 | 27.9 | 81.5 | 55.4/56.9 | 64.9 | 62.3 |
| v2.24 skillopt s5 | 20.2 | 5.8 | 95.0 | 50.0/52.0 | 60.4 | 46.3 |
| v2.24 gepa C | 82.0 | 27.9 | 81.5 | 55.4/56.9 | 64.9 | 62.3 |
| v2.24 gepa s5 | 82.8 | 27.3 | 86.5 | 60.3/62.7 | 61.9 | 63.8 |

Difference to the own run's C (points, L side):

| row | SearchQA | OfficeQA | ZebraLogic | Sheet | ALFWorld |
|---|---|---|---|---|---|
| typed-v2 S5 − C | +2.5 | +5.2 | +0.0 | +0.0 | +9.0 |
| typed-v2 C0 − C | -3.8 | -8.1 | +0.0 | +3.4 | -20.1 |
| v2.24 skillopt s5 − C | -61.8 | -22.1 | +13.5 | -5.4 | -4.5 |
| v2.24 gepa s5 − C | +0.8 | -0.6 | +5.0 | +4.9 | -3.0 |

## Chain G

| row | SearchQA | OfficeQA | ZebraLogic | Sheet | ALFWorld | mean |
|---|---|---|---|---|---|---|
| typed-v2 C0 (format only) | 82.5 | 45.3 | 73.5= | 66.7/69.1 | 87.3 | 71.1 |
| typed-v2 C (hand card) | 82.5 | 50.6 | 73.5= | 66.2/68.6= | 90.3= | 72.6 |
| typed-v2 S1 | 88.8 | 49.4 | 73.5= | 66.2/68.6= | 90.3= | 73.6 |
| typed-v2 S2 | 87.2= | 47.7= | 73.5 | 66.2/68.6= | 90.3= | 73.0 |
| typed-v2 S3 | 87.2= | 47.7= | 82.0= | 66.2/68.6= | 90.3= | 74.7 |
| typed-v2 S4 | 87.2= | 47.7= | 82.0= | 66.2/68.6= | 90.3= | 74.7 |
| typed-v2 S5 | 87.2 | 47.7 | 82.0 | 66.2/68.6 | 90.3 | 74.7 |
| v2.24 skillopt C | 84.8 | 50.0 | 73.0 | 65.7/66.7 | 90.3 | 72.7 |
| v2.24 skillopt s5 | 88.0 | 48.3 | 74.0 | 58.8/64.2 | 90.3 | 71.9 |
| v2.24 gepa C | 84.8 | 50.0 | 73.0 | 65.7/66.7 | 90.3 | 72.7 |
| v2.24 gepa s5 | 85.5 | 48.8 | 76.5 | 57.8/63.2 | 89.6 | 71.6 |

Difference to the own run's C (points, L side):

| row | SearchQA | OfficeQA | ZebraLogic | Sheet | ALFWorld |
|---|---|---|---|---|---|
| typed-v2 S5 − C | +4.8 | -2.9 | +8.5 | +0.0 | +0.0 |
| typed-v2 C0 − C | +0.0 | -5.2 | +0.0 | +0.5 | -3.0 |
| v2.24 skillopt s5 − C | +3.2 | -1.7 | +1.0 | -6.9 | +0.0 |
| v2.24 gepa s5 − C | +0.8 | -1.2 | +3.5 | -7.8 | -0.7 |

