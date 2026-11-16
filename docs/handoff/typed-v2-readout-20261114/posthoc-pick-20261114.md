# Post-hoc pick table (selected on the TEST set: an upper bound, not method evidence)

Every value is a difference in points to the hand card C read in the SAME run (own-run C). A difference not above the same-text noise of its chain and bench (v2.24 NF95, column noise; default 4.0) is not a pick. Re-reads (a step whose requests equal an earlier row's) are dropped; v2.24 and implant-v5 use their own paired estimate with identical requests tied; * = SpreadsheetBench, where that source counts unknown cells right for C only.

## Chain G

| bench | own-run C by source | noise | best difference to own C (configuration) | runner-up | pick |
|---|---|---|---|---|---|
| SearchQA | implant-v5 84.2, typed-v1 85.5, typed-v2 82.5, v2.24 gepa 84.8, v2.24 skillopt 84.8 | ±1.7 | +6.2 (typed-v2 S1 [learned card 94%]) | +4.8 (typed-v2 S2 [learned card 92%]) | typed-v2 S1 [learned card 94%] |
| OfficeQA | implant-v5 47.1, typed-v1 52.3, typed-v2 50.6, v2.24 gepa 50.0, v2.24 skillopt 50.0 | ±6.3 | +0.6 (gepa s1) | +0.0 (skillopt s1) | hand card C (nothing beats the noise) |
| ZebraLogic | implant-v5 69.5, typed-v1 75.5, typed-v2 73.5, v2.24 gepa 73.0, v2.24 skillopt 73.0 | ±8.2 | +8.5 (typed-v2 S3 [programs offered 96%]) | +5.5 (skillopt s1) | typed-v2 S3 [programs offered 96%] |
| Sheet | implant-v5 73.5, typed-v1 65.7, typed-v2 66.2, v2.24 gepa 66.7, v2.24 skillopt 66.7 | ±7.2 | +0.5 (typed-v2 C0 [format only]) | +0.0 (implant-v5 S3*) | hand card C (nothing beats the noise) |
| ALFWorld | implant-v5 88.1, typed-v1 91.0, typed-v2 90.3, v2.24 gepa 90.3, v2.24 skillopt 90.3 | ±4.4 | +7.5 (implant-v5 F (implanted programs)) | +1.5 (skillopt s4) | implant-v5 F (implanted programs) |

Post-hoc pick, mean gain over the hand card across the five benches (noise-floored): +4.4 points (an upper bound: picked on the test set)

## Chain D

| bench | own-run C by source | noise | best difference to own C (configuration) | runner-up | pick |
|---|---|---|---|---|---|
| SearchQA | implant-v5 82.2, typed-v1 81.8, typed-v2 81.5, v2.24 gepa 82.0, v2.24 skillopt 82.0 | ±1.8 | +2.5 (typed-v2 S2 [learned card 92%, programs offered 92%]) | +2.2 (typed-v2 S1 [learned card 94%, programs offered 94%]) | typed-v2 S2 [learned card 92%, programs offered 92%] |
| OfficeQA | implant-v5 31.4, typed-v1 32.0, typed-v2 29.1, v2.24 gepa 27.9, v2.24 skillopt 27.9 | ±3.9 | +5.2 (typed-v2 S2 [learned card 95%, programs offered 95%]) | +4.7 (typed-v2 S1 [learned card 68%, programs offered 68%]) | typed-v2 S2 [learned card 95%, programs offered 95%] |
| ZebraLogic | implant-v5 81.0, typed-v1 84.0, typed-v2 84.5, v2.24 gepa 81.5, v2.24 skillopt 81.5 | ±5.1 | +15.0 (skillopt s3) | +13.5 (implant-v5 S3) | skillopt s3 |
| Sheet | implant-v5 58.8, typed-v1 55.9, typed-v2 57.8, v2.24 gepa 56.9, v2.24 skillopt 56.9 | ±5.6 | +7.8 (typed-v1 C0 [format only]) | +3.4 (typed-v2 C0 [format only]) | typed-v1 C0 [format only] |
| ALFWorld | implant-v5 66.4, typed-v1 64.2, typed-v2 67.2, v2.24 gepa 64.9, v2.24 skillopt 64.9 | ±5.3 | +17.2 (implant-v5 F (implanted programs)) | +9.0 (typed-v2 S5 [learned card 94%]) | implant-v5 F (implanted programs) |

Post-hoc pick, mean gain over the hand card across the five benches (noise-floored): +9.5 points (an upper bound: picked on the test set)

