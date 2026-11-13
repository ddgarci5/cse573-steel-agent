# Session summary (newest first)

## Session 2026-11-13: larger-cap rerun, publication prep, review sheet, slide facts, wrap-up

### What was done (commit hashes are the published, post-scrub ones; the map to the earlier hashes is `results/git_hash_map_after_history_scrub.json`)
| Task | Result | Commit |
|---|---|---|
| 1. System C rerun at 4,000 output tokens | qwen38-27b and gemma4-31b-it, 3 repeats each, scorer unchanged; side-by-side table for both caps (section "System C pilot, 2026-11-13" below) | `98eacd0` |
| 2. Publication prep | README, `.gitignore` (any PDF, raw validation printouts), statistics-only `validation_summary.json`, audits, clean-clone test | `126999a`, `a2743fd` |
| (your decision) history scrub | public repo; six raw printouts removed from all history; final tree identical | rewrote commits 1 to 6 |
| 3. Review sheet | `results/system_c_review_sheet.csv`, 173 rows, F.3B first | `d1718a5` |
| 4. Backup-slide facts | `results/BACKUP_SLIDE_FACTS.md` (every number read from code or saved results) | `80328c5` |
| 5. Wrap-up | `CLAUDE.md` sections 5 and 11, this summary | the commit that contains this text |
Tests: 34 passing (`cd steelagent && python -m pytest`). Tracked files after this commit: 271; commits: 9.

### Repository state for publication
- **Audits.** Run on all 267 files tracked at that time and on every blob in every commit (310 objects after the scrub): no `.env`, `references/`, PDF, xlsx, zip, pptx, docx, parquet, model file or per-case Manual-table CSV; no line from the 26 AISC sample-table PDFs or the sponsor's 29 slide decks; no Voyager API key.
- **History scrub.** The six raw `validate_*.txt` printouts listed 16 worst-case rows with individual AISC Manual table values (6 + 4 + 6, all from the good validation run; the failed-run printouts hold only a traceback). They are removed from all six earlier commits with `git filter-branch`. After the rewrite none of the 16 rows appears in any object. The final git tree is byte-identical before and after (`bf9d941...`), so only history changed. **All commit hashes changed.**
- **Backup of the old history** (with those 16 rows) is a git bundle one folder above the repo, outside git. It is not part of the repository and must never be pushed or committed; delete it when you no longer need it.
- **Hashes in older result files.** `meta.json` files written before the rewrite record pre-scrub hashes (`results/system_b_baseline_20261112T001158Z`: `92bcfa6`; the three 1,500-token System C runs: `9433658`; the two 4,000-token runs: `eb53b69`). Those commits no longer exist under those names; the map file lists old to new.
- **Not created: the GitHub remote.** `gh` is not installed. Steps: (1) github.com/new, name `cse573-steel-agent`, Public, leave README / .gitignore / license unticked; (2) in the repo folder run `git remote add origin https://github.com/<your-username>/cse573-steel-agent.git` and `git push -u origin main` (Git for Windows opens a browser sign-in); (3) on GitHub check there is no `.env` and no `references/` folder. Do not run `git push --all` or `--mirror`.

### Decisions needed before the first public push
1. **Personal information that would be published.** `CLAUDE.md` names the instructor, the sponsor and the student and contains the instructor's email address (line 148, deck instructions). All 8 earlier commits carry the author and committer identity `the student <the author's email address>`. Eleven tracked files mention a local Windows path or OneDrive (most contain your user name, for example `<home>\...` in pytest and meta outputs). Redacting any of these means another history rewrite, which is easiest now, before anything is pushed.
2. **License:** none chosen (the README says so). Without one, all rights are reserved by default.
3. **Parity plots** `presentation/solver_validation_parity.png` and `steelagent/validation/parity.png` plot our solver against the AISC value for 1,902 comparisons; they show agreement, not readable table values, and are kept. Remove them if you prefer.
4. **Errata:** the May 2, 2025 AISC errata are still not checked against the Dataset C values.

### Failures, mistakes and surprises (not rounded away)
- **A larger output cap did not make the models more accurate.** It exposed the runs that truncation had hidden: Qwen's within-1% count fell from 8 to 7 of 27 while its answered count rose from 16 to 17, and its overestimates rose from 5 to 7 of 27. Qwen still truncated 12 of 39 runs at 4,000 tokens (self-correction loops). Full table above.
- **Gemma's selection got worse at repeat 1 at the larger cap:** one non-existent section (`W24X45` on F.3A) and one that fails the deflection check (`W21X55` on F.4), neither present at 1,500 tokens although those answers were not truncated. Voyager is not deterministic at temperature 0 (identical text across repeats on 0 of 13 problems for Qwen, 1 to 2 of 13 for Gemma), so I report these as run-to-run variation, not a cap effect.
- **The local qwen3.5:9b was not rerun** at 4,000 tokens (it would not finish within the one-hour limit), so the local column exists only at 1,500 tokens and only as a 17-run snapshot.
- **My first secret scan silently matched nothing**: the `grep` pattern did not fit how `.env` is formatted, so "no key found" came out empty for the wrong reason. I redid it by parsing `.env` the way the runner does; the key appears in no tracked file and no historical blob.
- **I first told you 26 AISC rows were in history; the exact count is 16.** The failed-run printouts contain only a traceback. I corrected it before acting on it.
- **The clean-clone test found a real gap:** a fresh clone had no `steelagent/data/` folder, so the README's instruction to save the Shapes Database there failed. Fixed with a placeholder file (`a2743fd`).
- **Smaller tool bugs fixed along the way:** the review-sheet quote originally started mid-word (it now quotes the whole original line); a wording glitch in the slide-facts generator ("ranges are:."); the facts generator's first edit pattern did not match and I applied the edits directly.
- **Rewriting history changed every commit hash** (see "Hashes in older result files"). The content did not change.
- **Carried over and still true:** the scores in System B are on an easy synthetic task; System C rests on 13 problems and many answers depend on recalled section properties; E7 is validated on few shapes; the Shapes Database is not in the repo, so every command needs it.

### Open questions
1. Public repo: redact the personal information listed above, or publish as is? Which identity should the commits carry?
2. Which license, if any?
3. Create the GitHub repo now (steps above), or have me install `gh` with scoop first (you would still complete its browser login)?
4. Finish the local System C run (22 more runs, about 1.5 hours of CPU) or keep the 17-run snapshot?
5. Qwen with thinking ON, or a different prompt that asks for a shorter working? Qwen's long outputs are what truncate.


## System C pilot, 2026-11-13: does a larger output cap change the answers? (1,500 vs 4,000 output tokens)

**What changed and what did not.** The two Voyager models were rerun with `max_tokens = 4,000` instead of 1,500. Everything else is identical: the same 13 problems (9 strength, 4 selection), the same prompt text, temperature 0, seed 573, 3 repeats, the same thinking setting (qwen38-27b: `enable_thinking=false` sent; gemma4-31b-it: no flag; reasoning output appeared in 0 of 39 runs of each at both caps), and the same scorer. **The scoring/classifier code was not modified**: `eval/system_c_pilot.py` is byte-identical (sha256 prefix `c8e7959deb92`) and every run's `summary.json` records that hash, so the 1,500-token runs did not need re-scoring. No scorer bug was found. The cap was set without editing that file, through the wrapper `eval/system_c_run_cap.py`, which overrides the module constant and calls the same `run()`.
- New run folders (the 1,500-token folders were not touched): `results/system_c_pilot_voyager_qwen38-27b_cap4000_20261113T021439Z/` (39 runs, 43.9 min) and `results/system_c_pilot_voyager_gemma4-31b-it_cap4000_20261113T021439Z/` (39 runs, 20.3 min).
- Side-by-side table: `results/system_c_cap_comparison_20261113T025850Z/` (`cap_comparison.csv`, `.md`, `inputs.json`), produced by `eval/system_c_cap_comparison.py` from the runs' `summary.json` files.
- **Local qwen3.5:9b was NOT rerun.** At the 1,500 cap it averaged 262 s per problem (about 1,290 output tokens, 9 of 13 first-repeat outputs truncated). Outputs that were cut at 1,500 tokens could run up to 2.7x longer at a 4,000 cap on this CPU-only machine, so even one repeat of 13 problems would very likely exceed the one-hour limit. Its 1,500-token numbers (17-run snapshot) are kept as they were.

### Side-by-side, both caps (exact counts)
Strength = 9 problems x 3 repeats = 27 runs; selection = 4 x 3 = 12 runs; truncation and repeats-agreed are per model. The local column is the 17-run snapshot (13 strength + 4 selection).
| Metric | local qwen3.5:9b @ 1,500 | qwen38-27b @ 1,500 | qwen38-27b @ 4,000 | gemma4-31b-it @ 1,500 | gemma4-31b-it @ 4,000 |
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
| Repeats agreed (identical text, problems with 2+ repeats) | 4 of 4 | 0 of 13 | 0 of 13 | 1 of 13 | 2 of 13 |
| Strength median absolute error, answered runs | 4.06% | 1.13% | 1.70% | 0.53% | 0.81% |
| Strength max absolute error, answered runs | 11.19% | 46.63% | 31.49% | 54.69% | 34.20% |
| Mean output tokens | 1,247 | 1,215 | 2,389 | 774 | 746 |

### What the larger cap did and did not change
- **More answers, not better answers.** Gemma now answers all 27 strength runs (24 before) and its within-1% count moves 14 to 15 of 27. Qwen answers 17 of 27 (16 before) but its within-1% count moves 8 to 7 of 27 and its overestimates rise from 5 to 7 of 27: the runs that were hidden by truncation are mostly wrong ones. The previous error statistics were therefore computed on a flattering subset.
- **Qwen still truncates 12 of 39 runs at 4,000 tokens** (F.3B 3, G.1B 3, F.1-2B 2, and one each on F.1-1A, F.1-1B, F.1-3B, F.4). The two long outputs I read (G.1B and F.3B, repeat 1) are self-correction loops: the same wrong formula restated up to 8 times and 6 to 7 "Wait / re-check / Actually" markers, ending mid-calculation at the cap. A larger cap will not fix that; the model does not converge on those problems.
- **Qwen selection became visible and is poor:** 3 of 12 match (F.1-1A twice, F.4 once), 10 of 12 answered, and 2 of the answers are not AISC sections (E.1A repeat 1 `W14X130`, repeat 3 `W14X136`); E.1A repeat 2 is W14X233 (exists, passes System A, 101 lb/ft heavier). F.3A is W21X50 in all 3 repeats (passes, 2 lb/ft heavier than W21X48). No Qwen section failed a System A check, but 2 do not exist.
- **Gemma selection got worse at repeat 1 only:** F.3A repeat 1 proposed `W24X45` (not an AISC section; the working uses Zx = 107 in^3 for it) and F.4 repeat 1 proposed `W21X55`, which fails the deflection check (Ix utilization 1.105). The 1,500-token runs of the same model had neither failure and those answers were not truncated, so this is run-to-run variation at temperature 0 (Voyager outputs are not deterministic), not an effect of the cap. Gemma's other 10 selection runs passed System A.
- **Repeats still disagree:** identical text across repeats on 0 of 13 problems for Qwen at both caps; Gemma 1 of 13 at 1,500 and 2 of 13 at 4,000. The repeat-to-repeat spread is why single-run differences in the table (for example Gemma 9 vs 8 of 12 selection matches) should not be read as a cap effect.
- **Large errors that remain** are on the beam-flexure problems: Gemma F.1-3B at 4,000 tokens answers -10.6%, -34.2% and +23.2% (previously one answer, -54.7%); Gemma F.1-2B answers -15.1%, +14.8%, -13.6%. Gemma's F.3B (+7.41% x3) and G.1B (-19.02% x3) are identical at both caps. Qwen's largest overestimates are F.1-3B +17.1% and +31.5% (378.7 kip-ft equals phi*Mp, the LTB-ignoring value; it is the one run per cap that the value-based check labels a wrong limit state, F.1-3B repeat 3 at 4,000 and repeat 2 at 1,500).
- Refusals: 0 for both models at both caps (regex flagged none). Secondary (heuristic text classifier, 12 beam runs per model, every run states a limit state): wrong in Qwen 3 of 12 at 1,500 vs 5 of 12 at 4,000; Gemma 5 of 12 vs 4 of 12.

Median absolute error by strength problem, answered runs `(answered/3 repeats)`:
| Problem | qwen38 @ 1,500 | qwen38 @ 4,000 | gemma4 @ 1,500 | gemma4 @ 4,000 |
|---|---|---|---|---|
| D.1-yield | 1.70% (3/3) | 1.70% (3/3) | 0.23% (3/3) | 0.23% (3/3) |
| D.1-rupture | 0.14% (3/3) | 0.14% (3/3) | 0.14% (3/3) | 0.14% (3/3) |
| E.1C | 0.56% (3/3) | 0.56% (3/3) | 0.76% (3/3) | 0.81% (3/3) |
| E.1D | 0.49% (3/3) | 0.49% (3/3) | 0.17% (3/3) | 0.30% (3/3) |
| F.1-1B | 2.74% (1/3) | 14.01% (2/3) | 0.07% (3/3) | 0.07% (3/3) |
| F.1-2B | no answer (0/3) | 3.49% (1/3) | 15.75% (2/3) | 14.77% (3/3) |
| F.1-3B | 39.06% (2/3) | 24.29% (2/3) | 54.69% (1/3) | 23.23% (3/3) |
| F.3B | 4.52% (1/3) | no answer (0/3) | 7.41% (3/3) | 7.41% (3/3) |
| G.1B | no answer (0/3) | no answer (0/3) | 19.02% (3/3) | 19.02% (3/3) |


## System C pilot, 2026-11-12: local qwen3.5:9b vs ASU Voyager qwen38-27b and gemma4-31b-it

**What was run.** The same 13 Dataset C problems (9 strength checks, 4 section selections), the same prompt text, parser, token cap (1,500 output tokens), temperature 0 and seed 573, no tools and no retrieval. Raw outputs are saved separately per model:
- local: `results/system_c_pilot_20261112T004145Z/` (Ollama, qwen3.5:9b, digest 56671c2ab938). **Snapshot of 17 runs, not 39**: repeat 1 is complete (13) plus 4 problems of repeat 2. I stopped the run because the CPU needs about 260 s per problem; the 4 repeated problems were byte-identical to repeat 1, so repeats add little at temperature 0. Resume with `eval/system_c_pilot.py run --model qwen3.5:9b --repeats 3 --run-dir results/system_c_pilot_20261112T004145Z`.
- `results/system_c_pilot_voyager_qwen38-27b_20261112T012059Z/`: 39 runs (13 problems x 3 repeats).
- `results/system_c_pilot_voyager_gemma4-31b-it_20261112T012059Z/`: 39 runs.
Final comparison tables: `results/system_c_comparison_20261112T015638Z/` (all repeats) and `results/system_c_comparison_20261112T015639Z/` (repeat 1 only, 13 runs each, apples-to-apples). Hand-check sheet: `results/system_c_review_sheet.csv`.

**Thinking / reasoning mode (recorded per model).**
| Model | Mode used | How | Evidence in outputs |
|---|---|---|---|
| local qwen3.5:9b | off | `think=false` sent to Ollama | reasoning output in 0 of 17 runs |
| voyager qwen38-27b | off | `chat_template_kwargs.enable_thinking=false` sent. The model **thinks by default**: in a 1-prompt probe the reasoning used all 1,500 tokens and the answer was empty | reasoning output in 0 of 39 runs |
| voyager gemma4-31b-it | off (model default) | no flag sent; the probe showed no reasoning with or without the flag | reasoning output in 0 of 39 runs, no think tags |
Thinking-on results were not run for any model. The four probe calls used to learn this are not saved as results.

### Primary metric: numerical error vs AISC's published answers
Strength problems only (the AISC value is the reference). Error statistics cover **only runs that produced a parseable final answer**; the count is the first row. The 1,500-token cap truncated many outputs (see below), so these statistics are on a survivor subset and are not comparable across models without that row.

All repeats that exist (local = 17-run snapshot):
| | local qwen3.5:9b | voyager qwen38-27b | voyager gemma4-31b-it |
|---|---|---|---|
| Strength runs with a parsed numeric answer | 6 of 13 | 16 of 27 | 24 of 27 |
| Median absolute error | 4.06% | 1.13% | 0.53% |
| Mean absolute error | 5.08% | 5.95% | 7.10% |
| Max absolute error | 11.19% | 46.63% | 54.69% |
| Correct (within 1% of AISC), of all strength runs | 3 of 13 (23%) | 8 of 27 (30%) | 14 of 27 (52%) |
| Within 5% of AISC, of all strength runs | 3 of 13 (23%) | 14 of 27 (52%) | 15 of 27 (56%) |
| Overestimates by more than 1% (unsafe direction) | 0 of 13 | 5 of 27 | 5 of 27 |
| Selection: exact match to AISC section | 0 of 4 | 0 of 12 | 9 of 12 |
| Selection: answers parsed at all | 0 of 4 | 1 of 12 | 12 of 12 |
| Selection: proposed section fails System A re-check (unsafe) | 0 of 4 | 0 of 12 | 0 of 12 |
| Selection: section not in AISC database | 0 of 4 | 0 of 12 | 0 of 12 |

Repeat 1 only (13 runs per model):
| | local qwen3.5:9b | voyager qwen38-27b | voyager gemma4-31b-it |
|---|---|---|---|
| Strength runs with a parsed numeric answer | 4 of 9 | 6 of 9 | 8 of 9 |
| Median / mean / max absolute error | 4.06 / 4.83 / 11.19% | 1.09 / 1.67 / 4.52% | 0.50 / 4.99 / 19.02% |
| Within 1% / within 5% of AISC (of 9) | 2 / 2 | 3 / 6 | 5 / 5 |
| Overestimates by more than 1% | 0 of 9 | 2 of 9 | 2 of 9 |
| Selection exact match (of 4) | 0 | 0 | 3 |

Median absolute error by strength problem, all repeats, `(parsed answers / runs)`:
| Problem | local qwen3.5:9b | voyager qwen38-27b | voyager gemma4-31b-it |
|---|---|---|---|
| D.1-yield | 11.19% (2/2) | 1.70% (3/3) | 0.23% (3/3) |
| D.1-rupture | 0.00% (2/2) | 0.14% (3/3) | 0.14% (3/3) |
| E.1C | no answer (0/2) | 0.56% (3/3) | 0.76% (3/3) |
| E.1D | no answer (0/2) | 0.49% (3/3) | 0.17% (3/3) |
| F.1-1B | 0.92% (1/1) | 2.74% (1/3) | 0.07% (3/3) |
| F.1-2B | no answer (0/1) | no answer (0/3) | 15.75% (2/3) |
| F.1-3B | no answer (0/1) | 39.06% (2/3) | 54.69% (1/3) |
| F.3B | no answer (0/1) | 4.52% (1/3) | 7.41% (3/3) |
| G.1B | 7.19% (1/1) | no answer (0/3) | 19.02% (3/3) |

### Refusals and missing answers
- Regex flagged 2 local runs as refusals (E.1C repeats 1 and 2). I read both: the model writes "Since I cannot access external tables or software, I will derive..." and then continues the calculation until the token cap cuts it off. **Both are false positives; confirmed refusals are 0 for all three models.** The regex was not changed (frozen scorer), so the automated table row still shows 2 of 17 for local.
- Every run without a parseable answer ended at the 1,500-token cap (no answer and no truncation never coincide): local 11 of 17, qwen38-27b 22 of 39, gemma4-31b-it 3 of 39. Mean output length 1,247 / 1,215 / 774 tokens. Qwen and the local model write long working, so this confounds every comparison above. In particular **Qwen's and local's selection zeros mostly mean "no answer", not "wrong answer"**: Qwen truncated 11 of 12 selection runs (its one parsed answer, F.4 repeat 3, was W21X62: passes System A, 7 lb/ft heavier than W24X55); local truncated all 4. Raising the cap would be a different experiment from the local run, so I did not do it.

### Secondary metric: wrong limit state (heuristic; hand-check sheet provided)
| | local qwen3.5:9b | voyager qwen38-27b | voyager gemma4-31b-it |
|---|---|---|---|
| Inferred from the value: the wrong answer matches another limit state's value from System A (all 9 strength problems) | 0 of 13 | 1 of 27 (F.1-3B repeat 2: 378.7 kip-ft, which is about phi*Mp, so LTB ignored; +31%) | 0 of 27 |
| Stated in the working, beam problems F.1-1B, F.1-2B, F.1-3B, F.3B only (wrong / runs that state one) | 2 of 2 (4 beam runs) | 3 of 12 | 5 of 12 |
Repeat 1 only, stated-wrong: local 2 of 2, qwen38 1 of 4, gemma 2 of 4. The most common error: the classifier labels all 7 F.3B outputs (W21x48, published governing state flange local buckling; gemma 3, qwen38 3, local 1) as plastic yielding, and the three I read in full (one per model, repeat 1) all call the flange compact. In those three the reasoning follows from misremembered section properties (for example Zx about 114 in^3 and bf 6.5 in. for W21x48), not from a misunderstanding of the provisions. Likewise Gemma's G.1B answer (247.8 kips vs 306) comes from tw = 0.350 in. for W24x62. The dominant failure mode without tools or tables is therefore section-property recall.
Classifier agreement on the 28 beam rows in the sheet: agrees 16, disagrees 10, nothing stated 2. Known weakness: "last statement wins", so a hedge at the end of a truncated output can flip the label (Gemma F.1-3B repeat 1 says "elastic LTB" and later hedges "if Lb is between Lp and Lr", labeled inelastic). Column problems (E.1C, E.1D) are not text-scored because Gemma states the governing axis only implicitly (it computes max KL/r without saying which axis); a wrong axis would show up in the value-based check.

### Other observations
- Determinism at temperature 0: local repeats were byte-identical on 4 of 4 repeated problems; Voyager was not (qwen38-27b 0 of 13 problems identical across 3 repeats, gemma4-31b-it 1 of 13), even with a fixed seed. Repeat-to-repeat spread on Voyager is real and is why the 3-repeat numbers differ from repeat 1.
- Selection: Gemma proposed the published section on E.1A, F.1-1A and F.4 in all 3 repeats and W21X50 (2 lb/ft heavier than W21X48, passes) on F.3A in all 3. No selected section from any model failed a System A check.
- Section-property recall also explains the large single errors: Gemma F.1-3B repeat 2 = 130.5 kip-ft vs 288 (-54.7%), Qwen F.1-3B repeat 2 = 378.7 (+31.5%).

### Scoring changes made AFTER seeing outputs (full record) and the final scorer
All three runs were re-scored with the final scorer, `eval/system_c_pilot.py` sha256 `c8e7959deb92...` (recorded in each run's `summary.json` and in `inputs.json` of each comparison). Thresholds (1% correct, 5%, alternative-limit-state match within 1%), the `FINAL ANSWER` parser, unit rules, the System A re-check for selections and the prompt text were NOT changed after any output was seen. Before any pilot output was read I had only made design-time fixes: prompt numbers use 3 decimals (U = 0.908 had rounded to 0.91) and the prompts omit the governing limit state (the Dataset C descriptions name it, e.g. "elastic LTB"); refusal detection and the value-based wrong-limit-state check were written after the 4-call thinking probe but before any run was scored.
| # | Change after seeing outputs | Why | Kind |
|---|---|---|---|
| 1 | Added a text classifier for the limit state the model states (4 beam problems) | After reading Gemma's F.3B output (flange called compact, yielding governs) I saw the value-based check could not detect a wrong limit state when the number matches no alternative | new secondary metric |
| 2 | Tried a text classifier for the governing column axis, then removed it | Gemma never says which axis governs (only the max KL/r), so every column run came back "not stated"; the value-based check already covers a wrong axis | removed before final scoring |
| 3 | Added yielding phrasings ("Limit State: Yielding", "flange and web are compact", "local buckling does not govern/control/reduce", "based on/governed by yielding") | Gemma F.1-1B outputs came back unclassified | classifier tuning |
| 4 | Fixed regex: "non-slender flanges" was read as a slender flange | Qwen F.1-1B repeat 2 was mislabeled flange local buckling | classifier bug fix |
| 5 | Added the phrasing "local buckling limit state does not govern/control/reduce" | Qwen F.1-1B repeat 2 wording | classifier tuning |
| 6 | `compare --max-repeat` and moving the summary into `summarize()` | the local run had only repeat 1 complete, so a like-for-like view was needed | reporting |
| 7 | `summarize()` crashed when a model never produced a parseable selection answer; missing score columns are now created empty | local scoring crashed on its own outputs | bug fix |
| 8 | Comparison loader reads the older local `meta.json` format (`think=false`); per-problem table lists all 9 problems with "no answer"; row labels no longer embed per-model run counts (rows had split with blanks); the "identical text across repeats" metric counts only problems with 2 or more repeats (it had counted single-repeat problems as identical, showing 13 for local) | table bugs found while building the comparison | reporting |
| 9 | Review-sheet path bug (relative path error) | sheet writer crashed | bug fix |
| 10 | Table reordered: numerical error first, limit-state rows labeled SECONDARY | requested | reporting |
Effect: changes 1 to 5 affect only the secondary stated-limit-state numbers; changes 6 to 10 do not change any computed score. The primary numerical-error numbers are unchanged by anything done after outputs were seen.
Not validated: the stated-limit-state classifier has not been checked against a hand-labeled set; that is what `results/system_c_review_sheet.csv` is for (columns `reviewer_label`, `reviewer_notes` are blank for you). While developing it I read key passages (excerpts, not full texts) of roughly 15 raw outputs, mostly repeat 1 of the four beam problems for each model; that is a development check, not a held-out test.

### Review sheet
`results/system_c_review_sheet.csv` (utf-8 with BOM for Excel): 95 rows = 39 + 39 + 17, one per model x problem x repeat, sorted by problem. For every problem it gives System A's governing state in words, the model's published/parsed answer and error, the model's own last "governs/controls/critical/limit state" lines, and the final answer line. For the four beam problems it also gives the classifier label, the label System A expects, whether they agree, and the matched text. `raw_output_file` points to the saved response.

### Open questions
1. The 1,500-token cap was inherited from the local run and truncates most Qwen and local outputs. Do you want a Voyager rerun with a higher cap (for example 4,000), reported as a separate experiment next to this one?
2. Run Qwen with thinking ON? It will use far more tokens; the probe showed it does not finish inside 1,500.
3. Finish the local run (22 more runs, about 1.5 hours of CPU) or accept the 17-run snapshot?
4. Dataset C has only 13 problems, so the percentages above rest on 9 strength and 4 selection problems; treat them as pilot evidence.


## Ollama setup, 2026-11-12
Installed Ollama 0.40.16 with `scoop install ollama` (user-level). Verified `ollama serve` answers `/api/version`; no models pulled yet (0 installed), server stopped afterwards.
Machine: Intel i5-11400 (6 cores), 15.6 GB RAM, Intel UHD 730 only (no NVIDIA GPU), 153 GB free on C:. Models will run on CPU, so expect slow generation for 7-8B models.
Model check (Ollama library pages read 2026-11-12 through a summarizing fetch tool; relative dates only): newest general-purpose Qwen is qwen3.8, 27b only (18 GB, does not fit in RAM). Newest with 4-9b sizes: qwen3.5 (4b 3.3 GB, 9b 6.6 GB, "updated 4 weeks ago", text+image, tools, thinking). Older fallback: qwen3:8b 5.2 GB. Llama/Gemma second model not looked up yet.
Pulled `qwen3.5:9b` (id 56671c2ab938, 6.6 GB). Smoke test (1 prompt, think=false, temperature 0, seed 573, num_predict 80): coherent one-sentence answer; 100% CPU, default context 4096; model load 22.8 s; prompt 12.9 tok/s; generation 4.11 tok/s (44 tokens, 35.8 s total). One sample only. Thinking mode was not timed; it will be slower.

## Task 4, 2026-11-12: Dataset B generator + System B quick baseline
Code: `ml/dataset_b.py`, `ml/system_b_baseline.py`; tests `steelagent/tests/test_dataset_b.py` (23 tests total, all pass).
Outputs: `results/dataset_b_20261112T001016Z/manifest.json`, `results/system_b_baseline_20261112T001158Z/` (`metrics.json`, `shortlist_*.csv`, `row_metrics_*.csv`, `log.txt`, `meta.json`, `system_b_baseline.png`; figure copy in `presentation/`). Git hash in `meta.json` is the Nov 11 initial commit with a dirty tree (task 4 files not committed yet). Seed 573.

**Dataset B** (parquet files in `datasets/B_synthetic/`, gitignored): compression and flexure, each 12,000 cases x 289 W-shapes = 3,468,000 rows. Splits by case: train 7,000 / val 1,500 / test 1,500 (all lengths <= 30 ft) plus 2,000 out-of-range cases (a length of 30.5-45 ft; never trained on).
Labels come from the validated solver. Cross-check before use: 400 random rows per member vs. the solver's Series path (max relative difference 5.8e-8, float32 storage; 0 pass/fail mismatches) and lightest weight vs. `search.lightest` (49 + 50 cases, 0 mismatches).
Row pass rate: compression 0.512, flexure 0.496. Cases with no passing section: 99 (compression), 88 (flexure); excluded from shortlist scoring.
Only 4.3% (compression) and 4.1% (flexure) of rows have utilization in 0.9-1.1. The oversampling raises this but the share is small because every case is crossed with all 289 sections.
Governing limit states, rows: compression E3_y 1,943,722 / E7_y 1,162,226 / E3_x 312,278 / E7_x 49,774; flexure F2_yielding 1,378,918 / F2_LTB 1,077,646 / G2.1_shear 966,328 / F3_FLB 45,108.

**Models** (train rows only; DecisionTree depth 16, HistGB 200 iterations; fit time 12-25 s each). Features: case inputs, section properties, simple ratios (Pu/A, KL/r, Mu/Zx, Vu/Aw, Lb/ry, Lb/rts). No solver output is a feature.

Row-level pass/fail (threshold 0.5), F1 / false passes (actually-failing rows predicted to pass):
| Member | Model | Test F1 | Test false passes (of 433,500 rows) | Out-of-range F1 | Out-of-range false passes (of 578,000 rows) | Test F1 in util 0.9-1.1 band |
|---|---|---|---|---|---|---|
| Compression | DecisionTree | 0.9989 | 252 | 0.9980 | 821 | 0.9765 |
| Compression | HistGB | 0.9988 | 280 | 0.9973 | 1,323 | 0.9729 |
| Flexure | DecisionTree | 0.9986 | 333 | 0.9881 | 3,410 | 0.9726 |
| Flexure | HistGB | 0.9989 | 320 | 0.9958 | 1,839 | 0.9756 |

Shortlist (k lightest sections with P(pass) >= theta chosen on val; System A re-checks them; hit = lightest passing weight reachable). Recall at k = 10 (target >= 95%):
| Member | Model | In-range test | Out-of-range | Mean solver calls, ML (in-range / ood) | System A early-stop calls (in-range / ood) |
|---|---|---|---|---|---|
| Compression | DecisionTree | 0.9839 | 0.9909 | 1.08 / 1.20 | 132.3 / 120.8 |
| Compression | HistGB | 1.0000 | 1.0000 | 1.35 / 1.68 | 132.3 / 120.8 |
| Flexure | DecisionTree | 0.9899 | **0.9115** | 1.25 / 8.98 | 126.2 / 136.7 |
| Flexure | HistGB | 1.0000 | 0.9985 | 1.22 / 2.18 | 126.2 / 136.7 |
Case-level counts: in-range test 1,491 compression / 1,491 flexure feasible cases; out-of-range 1,987 / 1,988. Calls include a full System A fallback when no shortlisted section passes. Full scan = 289 calls. k = 1 recall is much lower (HistGB: compression 0.7197 in-range / 0.5586 ood; flexure 0.8209 / 0.3913); k = 5 already gives HistGB 1.0000 in-range for both and 0.9849 / 0.9764 out-of-range. See `shortlist_*.csv`.
Diagnostic regression of log lightest weight (HistGB, case features only): in-range test R^2 0.9986 (compression) / 0.9985 (flexure), median error 2.03% / 1.77%; out-of-range R^2 0.9456 / 0.9848, median error 12.97% / 8.66%. Not used for shortlisting.
Feature importance (HistGB permutation, drop in test F1): compression Pu/A 0.455, KLr_max 0.124, Lcy/ry 0.005; flexure Mu/Zx 0.365, Vu/Aw 0.201, **Lb/ry 0.017**, Mu/Sx 0.012, Cb 0.009. Decision tree builtin importances rank the same top features.

**What this does and does not show**
- The classifier alone is NOT safe: it still predicts pass for 0.12-0.16% of failing rows in-range and 0.29-1.15% out-of-range (range over both models and both member types). Rule 2 holds only because every shortlisted section is re-checked by the solver before it is recommended; the re-check is mandatory.
- The near-perfect scores are partly by construction: the engineered ratios (Pu/A, Mu/Zx, Vu/Aw) are close to the first-order capacity checks, and the demands are built from anchor-section capacity. Treat these scores as an upper bound on how easy the synthetic task is, not as expected real-world accuracy; Dataset C (13 cases) is the honest check and is not run through System B yet.
- Out-of-range here means longer lengths only (30.5-45 ft). The decision tree degrades there on flexure (F1 0.9881, recall@10 0.9115, below the 95% target); HistGB does not.
- About 35% of compression rows (1,212,000 of 3,468,000) are governed by E7 slender-element capacity. 101 of the 289 W-shapes have webs that are slender in compression (h/tw > 1.49*sqrt(E/Fy); none have slender flanges), spanning W8 to W44. The solver's E7 effective-width path is validated only on the slender W14 shapes in Table 4-1a (21 cases) and the Design Examples, so a large share of compression labels depends on E7 outside the validated set. Worth an additional independent E7 check (e.g. the Manual's slender-shape rows for other depths) before using these labels in the final report.
- Flexure covers major-axis F2/F3 + G2.1 only; shear governs 27.9% of rows. Deflection, ASD, combined forces and torsional buckling are not in Dataset B.
- Not done: Random Forest / XGBoost, hyperparameter tuning, Dataset B tension, model persistence, and a Dataset C evaluation of System B. Inference cost (289 predictions per case) is not counted in "calls saved".

## Session summary, 2026-11-11 (backlog tasks 1-3)

## Bottom line
Every section 5 number is reproduced by a full end-to-end rerun, including the PDF parsing of the three Manual tables.
First attempt (`results/validation_20261111T222322Z/`) failed because this machine only had xpdf `pdftotext`; after installing poppler 26.09.0 with
`scoop install poppler` the rerun (`results/validation_20261112T000516Z/`, all six jobs return code 0) matches. Git hash: none yet, no commits.

## Results (`results/validation_20261112T000516Z/`)
| Check | Cases | Max abs. error | Section 5 | Output file |
|---|---|---|---|---|
| Manual Table 4-1a, W14 phiPn (13 shapes, 21 slender-shape cases) | 324 | 0.446% | 0.45% | `validate_compression.txt` |
| Manual Table 3-2 (63 shapes, 6 quantities) | 378 | 0.929% | 0.93% | `validate_flexure.txt` |
| Manual Table 4-14, phiFcr (6 grades, Lc/r 1-200) | 1,200 | 0.433% | 0.43% | `validate_fcr.txt` |
| Design Examples strength checks | 9 | 0.47% | 0.47% | `dataset_c_pilot.txt` |
| Design Examples selection | 4 | 4/4 exact | 4/4 | `dataset_c_pilot.txt` |
| pytest (9 strength + 4 selection + 1 file-count + 2 shapes DB) | 16 | all passed | n/a | `pytest.txt` |

Mean |err|: 0.113% (4-1a), 0.129% (3-2), 0.093% (4-14); all cases within 1%.
Table 3-2 max error by quantity: BF 0.929, Lp 0.406, Lr 0.291, phiMp 0.139, phiMr 0.316, phiVn 0.372 (%).
Fresh poppler-parsed CSVs vs. the sandbox CSVs shipped in the zip: row counts equal, parsed AISC values identical on every row, error columns identical
(max difference 0). `rescore_shipped_csv.txt` (re-scoring shipped values with this repo's solver) gives the same maxima.

## What failed / caveats
- Run `20261111T222322Z` (xpdf) kept as a record: the three table scripts exited 1. Before the poppler guard existed they silently printed wrong numbers
  (Table 3-2 34% mean error, Table 4-14 114 cases, Table 4-1a 0 cases); those runs were discarded.
- Git for Windows' xpdf still comes first on PATH inside Git Bash. `parse_tables.py` now scans PATH (or `$POPPLER_PDFTOTEXT`) for the first poppler build, so this does not matter.
- The three Manual-table CSVs and the Design Examples values are only as good as the parse: agreement with the sandbox run shows the parser is reproducible, not independently audited.

## What was built
- Layout from section 3, `.gitignore` (`references/`, `*.zip`, `.venv/`, `.env`, `*.gguf`, `models/`, shapes xlsx, office files, `*_results.csv`), `requirements.txt` (pinned), `.venv` (CPython 3.14.7 via uv), `git init` (branch `main`, nothing committed, no remote).
- Solver unzipped to `steelagent/`; AISC shapes DB placed at `steelagent/data/aisc-shapes-database-v16_0.xlsx` (renamed to the name `shapes.py` expects).
- the sponsor's modules (Beams, Combined Forces, Compression, Tension) -> `references/teaching-modules/`; sample tables (26 PDFs) -> `references/aisc-sample-tables/` (flattened). `references/design-examples/` is empty: the Design Examples PDF was not among the files.
- Path fixes: `parse_tables.py` now resolves `references/aisc-sample-tables/` relative to the repo. All four other scripts also had `/home/claude/steelagent` hard-coded; fixed.
- New: `validation/run_all.py` (timestamped results + `meta.json`), `validation/rescore_shipped_csv.py`, poppler lookup/guard + UTF-8 decoding in `parse_tables.py`, `STEELAGENT_OUT` env var so reruns do not overwrite baselines.
- Task 3: `datasets/C_benchmark/design_examples_strength.json` (9) and `design_examples_selection.json` (4), params and published answers only; `steelagent/tests/` (16 tests, `pytest.ini`).

## Open questions
1. (Resolved) poppler 26.09.0 installed with scoop; the three table validations were fully rerun.
2. The per-case CSVs hold AISC Manual tabulated values. I gitignored them (rule 5). Say if you want them committed to the private repo anyway.
3. May 2, 2025 errata: not checked. Both Dataset C JSON files say `errata_applied: false`. Needs the Design Examples PDF in `references/design-examples/`.
4. Private GitHub repo: `gh` is not installed and I did not create a remote. Also no git `user.name`/`user.email` is configured, so no commit has been made.
5. The repo lives in OneDrive; `.venv/` (~19 packages) will sync. Consider excluding it from OneDrive sync or moving the venv outside.
6. `search.lightest` takes a single nominal depth; the F.1-1A "depth <= 18 in." case is handled by a loop in the test. Needs a `max_depth_in` option when the DesignCase constraints are implemented (backlog 6).
7. Deflection remains an `Ix_min` check only, and E4/F4/F5/block shear are still out of scope (unchanged from section 5).
