| Metric | local qwen3.5:9b @ 1500 | voyager qwen38-27b @ 1500 | voyager qwen38-27b @ 4000 | voyager gemma4-31b-it @ 1500 | voyager gemma4-31b-it @ 4000 |
|---|---|---|---|---|---|
| Strength runs answered (parsed numeric answer) | 6 of 13 | 16 of 27 | 17 of 27 | 24 of 27 | 27 of 27 |
| Strength: within 1% of AISC | 3 of 13 | 8 of 27 | 7 of 27 | 14 of 27 | 15 of 27 |
| Strength: within 5% of AISC | 3 of 13 | 14 of 27 | 13 of 27 | 15 of 27 | 15 of 27 |
| Strength: overestimate > 1% (unsafe direction) | 0 of 13 | 5 of 27 | 7 of 27 | 5 of 27 | 5 of 27 |
| Selection: matches AISC section | 0 of 4 | 0 of 12 | 3 of 12 | 9 of 12 | 8 of 12 |
| Selection: answered (parsed section) | 0 of 4 | 1 of 12 | 10 of 12 | 12 of 12 | 12 of 12 |
| Selection: proposed section fails a System A check (unsafe) | 0 of 4 | 0 of 12 | 0 of 12 | 0 of 12 | 1 of 12 |
| Selection: section not in AISC database | 0 of 4 | 0 of 12 | 2 of 12 | 0 of 12 | 1 of 12 |
| Truncated outputs (hit the cap) | 11 of 17 | 22 of 39 | 12 of 39 | 3 of 39 | 0 of 39 |
| Repeats agreed (identical text, problems with >= 2 repeats) | 4 of 4 | 0 of 13 | 0 of 13 | 1 of 13 | 2 of 13 |
| Strength median abs. error, answered runs | 4.06% | 1.13% | 1.70% | 0.53% | 0.81% |
| Strength max abs. error, answered runs | 11.19% | 46.63% | 31.49% | 54.69% | 34.20% |
| Mean output tokens | 1247 | 1215 | 2389 | 774 | 746 |
