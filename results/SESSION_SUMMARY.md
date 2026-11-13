# Session summary (newest first)

## Session 2026-11-13 (night): first agent slice, LLM extraction -> validation -> deterministic solver -> compare with AISC

This is the first two steps of System D (Parse, Calculate), not the LangGraph agent. The LLM only fills a DesignCase JSON; every number in a final answer comes from `steelagent/` through plain Python routing. **`steelagent/` was not modified** (34 solver tests still pass; 52 new tests in `agent/tests`, run with `cd agent && python -m pytest`).

### What was built (commit hashes as pushed; the docs commit that contains this text is the one after `13575cb`)
| Step | What | Commit |
|---|---|---|
| 1 | `agent/design_case.py`: Pydantic DesignCase (types, plausible ranges, unknown keys rejected, `missing_fields` consistency), domain flags, executable required-inputs map; `pydantic==2.14.3` pinned | `db2cc1c` |
| 2 | `datasets/C_benchmark/gold_design_cases.json` (13 gold cases, generated mechanically from the Dataset C JSON by `eval/make_gold_design_cases.py`, no Dataset C value changed); `results/gold_design_cases_review.md` | `01e3149` |
| 3 | `agent/extract.py` (frozen prompt `extract-v1`, JSON only, at most one retry with the validation error shown), `agent/route.py` (DesignCase to steelagent functions), `eval/first_slice_eval.py` (run + score) | `20282ec` |
| 3b | Scorer bug fix (see "What failed") | `bceb3d0` |
| 4 | Run and score: `results/first_slice_20261113T045951Z/` | `13575cb` |
**Gold DesignCases are pending Dylan's review.** `results/gold_design_cases_review.md` lists each gold case under its exact problem text with a checkbox. Nothing in it has been hand-checked yet; if you change a gold value, rerun `eval/first_slice_eval.py score` (no model calls needed) and `python -m pytest` in `agent/` (the gold-vs-generator test will tell you to regenerate).

### Design decisions fixed before any model call
- **Same problem texts as System C.** `problem_texts()` takes each System C prompt and removes the shared header and the answer-format tail, so the model sees exactly the "Problem: ..." statement. The harness sets `problem_id`; the model never sees it (problem ids such as F.3B would identify the AISC example).
- **One field added to the brief's list: `requested_limit_states`** (tension only). D.1-yield and D.1-rupture differ only in which limit state the question asks for, and the schema as listed cannot say that. With it empty, a tension check needs An and U (CLAUDE.md: the agent asks for them). Also added `shear` as a member type, as requested.
- **Required-inputs map** (executable, in `design_case.py`): tension check = section (+ An, U unless only yielding is asked); compression check = section, Lcx, Lcy; flexure check = section, Lb (+ Cb unless Lb = 0); shear check = section; compression selection = Pu, Lcx, Lcy; flexure selection = Mu, Lb (+ Cb unless Lb = 0). Cb is not required at Lb = 0 because LTB cannot reduce Mn there; the router then passes Cb = 1.0 to the solver without writing it into the case. Tension selection and shear selection are flagged unsupported.
- **`missing_fields`**: the model declares it; code computes the required-but-null inputs independently; the schema rejects a case if a required null input is not declared or a declared one has a value; the router asks the user when the **union** of the two lists is non-empty. A nonexistent section label is flagged (never corrected; only case and spacing of the label are normalized), triggers no retry, and the case is not computed.
- **Scoring frozen** in the docstring of `eval/first_slice_eval.py` (also in meta.json as `scorer_sha256`): numeric fields within 0.5%, 22 leaf fields per case, exact match = all 22, strength correct within 1% of AISC, selection correct = same section as AISC, unsafe = capacity overstated by more than 1% or a recommended section that fails System A **on the true Dataset C case**, error trace = solver / routing / extraction decided by a gold control (below).
- **Gold control (no model, run before every model run, aborts the run if it fails):** route(gold case) equals System A applied directly to the Dataset C parameters on all 13, and both agree with AISC (strength max error 0.466%, 4 of 4 selections exact). Saved as `gold_control.json`.
- Run settings: Voyager, temperature 0, seed 573, max output tokens 1,000, 3 repeats, Qwen with `enable_thinking=false` (as in System C), Gemma no flag, no tools, no retrieval. Prompt sha256 prefix `2f011000976b`, scorer `cc06b06bdda4`.

### Results (`results/first_slice_20261113T045951Z/`; 39 runs per model = 13 problems x 3 repeats; `SCORES.md`, `<model>/summary.json`, `scores.csv`, `field_errors.csv`, `error_trace.csv`, raw outputs in `<model>/raw/`)
| Metric | gemma4-31b-it | qwen38-27b |
|---|---|---|
| JSON valid on first try (after my parser strips a surrounding code fence) | 39 of 39 | 39 of 39 |
| ...of which wrapped in a markdown code fence despite "no code fences" | **39 of 39** (strictly bare JSON: 0 of 39) | 0 of 39 |
| Valid after retry / invalid after retry | 0 / 0 | 0 / 0 |
| Retries used (of 78 attempts) | 0 | 0 |
| Truncated responses (cap 1,000; longest answer 298 tokens) | 0 | 0 |
| Nonexistent section labels flagged | 0 | 0 |
| Exact-match DesignCase | 36 of 39 | 39 of 39 |
| Field accuracy (22 leaves per case) | 855 of 858 = 99.65% | 858 of 858 = 100% |
| Field micro P / R / F1 (constants excluded; 192 gold non-null fields) | 0.985 / 1.000 / 0.992 (192 TP, 3 FP, 0 FN) | 1.000 / 1.000 / 1.000 |
| Strength final answer within 1% of AISC | 27 of 27 (max error 0.466%) | 27 of 27 (max error 0.466%) |
| Selection exact match with AISC | 9 of 12 | 12 of 12 |
| Runs that would ask the user (no answer) | 3 of 39 | 0 of 39 |
| Unsafe output (overstated capacity > 1%, or recommended section fails System A) | 0 | 0 |
| Error trace of the runs that are not correct | extraction 3, routing 0, solver 0 | none |
| Mean output tokens / mean seconds per run | 285 / 9.7 | 266 / 7.1 |
**Every wrong or missing field (complete list):** Gemma E.1A repeats 1, 2 and 3: `missing_fields` = ["section"], gold []. The task is `select_lightest`, so no section is needed and the prompt's list says so; the model asked for one anyway, and because the router asks the user when `missing_fields` is non-empty, all three E.1A runs became "would ask the user" instead of W14X132. This is a model error (the schema, parser and router behaved as designed), and it is the conservative direction (asks, does not guess). Gemma got F.3A, F.1-1A and F.4, which have the same structure, right in all repeats. Qwen: no wrong or missing field in 39 runs. The extracted cases of both models were identical between this run and the aborted first run (39 of 39 each).

### System C at the 4,000-token cap vs this slice (same 27 strength and 12 selection runs per model; exact counts)
| Metric | gemma System C @ 4,000 | gemma slice | qwen System C @ 4,000 | qwen slice |
|---|---|---|---|---|
| Strength: within 1% of AISC | 15 of 27 | 27 of 27 | 7 of 27 | 27 of 27 |
| Strength: no answer | 0 of 27 | 0 of 27 | 10 of 27 | 0 of 27 |
| Strength: overestimate > 1% (unsafe direction) | 5 of 27 | 0 of 27 | 7 of 27 | 0 of 27 |
| Selection: exact match to AISC | 8 of 12 | 9 of 12 | 3 of 12 | 12 of 12 |
| Selection: no answer | 0 of 12 | 3 of 12 | 2 of 12 | 0 of 12 |
| Selection: recommended section fails a System A check | 1 of 12 | 0 of 12 | 0 of 12 | 0 of 12 |
| Selection: section not in AISC database | 1 of 12 | 0 of 12 (cannot occur: the search returns database sections only) | 2 of 12 | 0 of 12 (same) |
| Truncated at the cap (4,000 / 1,000 tokens) | 0 of 39 | 0 of 39 | 12 of 39 | 0 of 39 |
| Mean output tokens | 746 | 285 | 2,389 | 266 |
Source: the same `summary.json` files as the earlier cap comparison and `SCORES.md` of this run.

### What this does and does not show (read before quoting the numbers)
- **The extraction task is easy by construction.** All 13 texts are generated by our own template from the Dataset C fields (`eval/system_c_pilot.py`), so every number is stated plainly in one fixed sentence pattern. A model reading them is close to copying. Qwen's 39 of 39 says nothing about messy, human-written problems (Dataset D's real-world split, not built yet).
- **The prompt was written knowing these 13 problems.** Its field notes use the examples `"W14"` and `"no more than 18 in."`, which mirror E.1A and F.1-1A. I did not read any model output before freezing it, but the 100% should not be read as generalization.
- **The correctness of the final numbers is inherited from the solver**, which was validated against these same 13 AISC values (max error 0.47%, and the May 2, 2025 errata are still unchecked). On Dataset C the slice's final-answer score is therefore essentially the extraction score. This supports "the LLM does not need to compute" (RQ2), but it is weak evidence for RQ3.
- **Missing-field detection was not tested by any model**: all 13 gold cases are complete. The behavior (ask, do not compute, never default) is covered only by unit tests with synthetic cases. Gemma's three E.1A abstentions are over-asking, the opposite error.
- **The retry path never ran on real output** (0 of 78 first attempts invalid); it is covered only by tests with a fake LLM. Gemma's code fences are tolerated by the parser and counted as valid first try; I report the strict count above (0 of 39).
- **The abstentions are a consequence of a policy I fixed before running** (ask when the union of declared and computed missing fields is non-empty). Trusting only the code-computed list would have turned Gemma's three abstentions into correct answers (39 of 39), but I chose that policy before seeing outputs and did not change it afterwards. Which policy is right is an open question below.
- The System C and slice columns do different jobs (end-to-end calculation by the model vs. extraction only), so the table shows the benefit of moving the numbers into deterministic code, not that one model is better than the other at engineering.

### What failed or went wrong (not rounded away)
- **A scorer bug, found at the first scoring attempt, before any number was produced.** A result column named `flags` collided with pandas' `DataFrame.flags` attribute and `score` crashed. My tests covered `score_run` but not the summary and report path, which is why it got through. Per your rule I fixed it (column renamed to `flag_codes`), added a test that runs the whole `score` command on a synthetic run (`test_score_command_end_to_end_on_a_synthetic_run`), and **reran everything** from the fixed, committed code. The aborted run's raw outputs are kept, unscored, in `results/first_slice_20261113T045305Z_ABORTED_scorer_bug/` (with a README). The rerun's extractions were identical to the aborted run's (39 of 39 for each model), so the bug did not change any model output.
- **My first version of the new test also had a wrong expectation** (truncated responses are counted per run, not per attempt); the test was wrong, not the scorer, and was corrected before the rerun.
- **I rewrote the three newest local commits once before the first push** (nothing had been pushed): the audit found my local Windows user path in the crash traceback of the aborted run (`score_stdout.txt`), the kind of string earlier sessions removed from history. It is now `<repo>` / `<home>` in all versions. Hashes changed: `1e26638` to `bceb3d0`, `fe11123` to `13575cb`, `8cf1238` to the docs commit that contains this text. `meta.json` of the scored run still records `git_hash` `1e26638...` (the code at that hash is unchanged; only the commit id changed). The three older commits of this session are untouched (`db2cc1c`, `01e3149`, `20282ec`; the aborted run's `meta.json` records `20282ec`).
- **`git_tree_dirty: true` in the new `meta.json` files** is only because the empty run folder itself was untracked when the run started; the tracked code was clean at the commit recorded as `git_hash` (`1e26638` in the file; that commit was later rewritten, see the next item, and is now `bceb3d0`).
- **Voyager host name again in four new `meta.json` files** (two in the scored run, two in the aborted run): `"endpoint_host": "openai.rc.asu.edu"`, consistent with your earlier decision to leave it published.
- **"Dylan" now appears by name** in this summary (as you asked) and, because I wrote the same status line there, in `results/gold_design_cases_review.md`, `datasets/C_benchmark/gold_design_cases.json` (`review_status`), and `eval/make_gold_design_cases.py` (`CLAUDE.md` says "the student"). The repo is public; earlier sessions redacted personal names except the `dylan_verdict` column. Say if you want those three replaced by "the student" (a text-only change, but the commits already made would still contain it unless history is rewritten again).
- **Not done tonight:** tension and shear selection, ASD, other materials, any retrieval, shortlist, verifier, Streamlit, LangGraph; System B has not been run through this slice.

### Open questions
1. Please hand-check `results/gold_design_cases_review.md` (13 cases).
2. `missing_fields` policy: keep "ask when declared or computed is non-empty" (safer, over-asks when a model invents a missing field) or trust only the code-computed list? Changing it after seeing Gemma's result would be a post-hoc choice; if you switch, report it as a new scoring version and rerun.
3. Next evidence worth having before claiming anything about extraction: Dataset D, especially the human-written messy prompts with missing assumptions, and a probe set where inputs are truly missing (missing-field detection), and the retry path with real output.

## Session 2026-11-13: larger-cap rerun, publication prep, review sheet, slide facts, wrap-up

### What was done (commit hashes are the final published ones, after all three history rewrites; the map to the original hashes is `results/git_hash_map_after_history_scrub.json`)
| Task | Result | Commit |
|---|---|---|
| 1. System C rerun at 4,000 output tokens | qwen38-27b and gemma4-31b-it, 3 repeats each, scorer unchanged; side-by-side table for both caps (section "System C pilot, 2026-11-13" below) | `c11b451` |
| 2. Publication prep | README, `.gitignore` (any PDF, raw validation printouts), statistics-only `validation_summary.json`, audits, clean-clone test | `032c5b0`, `4975158` |
| (your decision) history scrub | public repo; six raw printouts removed from all history; final tree identical | rewrote commits 1 to 6 |
| (your decision) redaction + generic identity | names, instructor email and Windows username path removed from files and history; author and committer set to a generic project identity | rewrote all 9 commits |
| 3. Review sheet | `results/system_c_review_sheet.csv`, 173 rows, F.3B first | `de24a69` |
| 4. Backup-slide facts | `results/BACKUP_SLIDE_FACTS.md` (every number read from code or saved results) | `02a73cf` |
| 5. Wrap-up | `CLAUDE.md` sections 5 and 11, this summary | `b696d51` (corrections after the redaction are in the commit after it) |
Tests: 34 passing (`cd steelagent && python -m pytest`). Tracked files: 271.

### Repository state for publication
- **Audits.** Run on all 267 files tracked at that time and on every blob in every commit (310 objects after the scrub): no `.env`, `references/`, PDF, xlsx, zip, pptx, docx, parquet, model file or per-case Manual-table CSV; no line from the 26 AISC sample-table PDFs or the sponsor's 29 slide decks; no Voyager API key.
- **History scrub.** The six raw `validate_*.txt` printouts listed 16 worst-case rows with individual AISC Manual table values (6 + 4 + 6, all from the good validation run; the failed-run printouts hold only a traceback). They are removed from all six earlier commits with `git filter-branch`. After the rewrite none of the 16 rows appears in any object. The final git tree is byte-identical before and after (`bf9d941...`), so only history changed. **All commit hashes changed.**
- **Redaction and identity (second and third rewrites).** Names (instructor, sponsor, student), the instructor's email address and the local Windows user path were removed from every text file and from all older versions. Rules, applied in order: specific `CLAUDE.md` sentences reworded to roles ("the course instructor", "the sponsor", "the student"); `C:\Users\<user>\OneDrive\Documents\CSE573-steel-agent` became `<repo>`; any other `C:\Users\<user>` became `<home>`; leftover names and emails became role phrases. Twelve files changed in the final tree (`CLAUDE.md`, this summary, `BACKUP_SLIDE_FACTS.md`, `system_b_baseline_*/log.txt`, and the command-log, `pytest`, `meta.json` and summary files of the two validation runs); only text changed, no number. The rule set was dry-run on a throwaway clone and reviewed first, and the real rewrite produced a tree identical to that dry run. After it, a scan of all 322 text files in history and every commit message finds none of the redacted strings. The column name `dylan_verdict` in the review sheet and its generator was kept on purpose because it was requested by name. Then author and committer on all commits were set to `Steel Agent Project <noreply@steel-agent.invalid>` (the `.invalid` domain can never resolve; a `users.noreply.github.com` address was avoided so the commits cannot be attributed to another GitHub account). The repo-local git identity uses the same value; no global identity is set.
- **Backups of earlier history** are two git bundles one folder above the repo, outside git: one from before the scrub (it contains the 16 AISC rows) and one from before the redaction (it contains the personal information). They are not part of the repository and must never be pushed or committed; delete them when you no longer need them.
- **Hashes in older result files.** `meta.json` files written before the rewrite record pre-scrub hashes (`results/system_b_baseline_20261112T001158Z`: `92bcfa6`; the three 1,500-token System C runs: `9433658`; the two 4,000-token runs: `eb53b69`). Those commits no longer exist under those names; the map file lists old to new.
- **Published (2026-11-13): a public GitHub repository named `cse573-steel-agent`, created with the GitHub CLI after you logged in; only `main` was pushed (first push at commit `b1c2715`).** A fresh clone from GitHub was audited: 10 commits, 330 text files, no names, emails, Windows paths, API key, AISC printout rows or forbidden paths; all commits show the generic identity with no linked account; 34 tests pass. Never use `git push --all` or `--mirror` (the backup bundles are outside the repo, but keep it that way).

### Decisions after the first public push
1. **Resolved: personal information.** Redacted and verified as described above; commits use a generic identity. Consequences you should know: because the author email is not linked to any GitHub account, the commits will show the name "Steel Agent Project" with no profile link and will not count toward your GitHub contribution graph. `README.md` and the suggested repository name (`cse573-steel-agent`) still say that this is an ASU CSE 573 course project (Group 13, Project 18); only personal names, emails and paths were redacted, as requested.
2. **Decided: no license for now.** The repository has no license file and the README says "No license has been chosen yet", which stays accurate. Default copyright applies (all rights reserved): the code can be viewed and forked on GitHub but not reused, modified or redistributed without permission. A license can be added later; the option discussed was MIT with the generic holder "Steel Agent Project contributors". Before opening the code up, check with the Group 13 teammates and, if the course or sponsor has IP rules, with the instructor or sponsor. No license on the code would cover the AISC-derived values in `datasets/C_benchmark`.
3. **Parity plots** `presentation/solver_validation_parity.png` and `steelagent/validation/parity.png` plot our solver against the AISC value for 1,902 comparisons; they show agreement, not readable table values, and are kept. Remove them if you prefer.
4. **Errata:** the May 2, 2025 AISC errata are still not checked against the Dataset C values.
5. **Decided: leave the Voyager host name published.** The four Voyager `meta.json` files under `results/` record `"endpoint_host": "openai.rc.asu.edu"` (the Voyager service address; not a secret, not the API key). It is already public and you chose to leave it; removing it would need another history rewrite and a force-push. It is the only appearance of that host name in the repository.
6. **Decided: skip the rest of the local System C run; the 17-run snapshot is the final local result.** The local qwen3.5:9b run (`results/system_c_pilot_20261112T004145Z/`, 1,500-token cap, thinking off) stays at 17 runs: repeat 1 is complete (13 runs) plus 4 repeat-2 runs (D.1-yield, D.1-rupture, E.1C, E.1D), which were byte-identical to repeat 1. The remaining 22 runs (about 1.5 hours of CPU at about 262 s per problem) will not be run, and there is no 4,000-token local run. Consequences for reading the tables: the local column is based on 17 runs against 39 for each Voyager model, so its counts (for example 3 of 13 strength runs within 1%, 0 of 4 selections answered) are small and not comparable one-to-one with the Voyager counts; use the repeat-1-only comparison (`results/system_c_comparison_20261112T015639Z/`, 13 runs per model) for a like-for-like view. The run can still be resumed with `eval/system_c_pilot.py run --model qwen3.5:9b --repeats 3 --run-dir results/system_c_pilot_20261112T004145Z` if the decision changes; nothing was deleted.
7. **Decided: keep "CSE 573, Group 13" in the README and keep the repository name `cse573-steel-agent`.** Only personal names, emails and paths were redacted.

### Failures, mistakes and surprises (not rounded away)
- **A larger output cap did not make the models more accurate.** It exposed the runs that truncation had hidden: Qwen's within-1% count fell from 8 to 7 of 27 while its answered count rose from 16 to 17, and its overestimates rose from 5 to 7 of 27. Qwen still truncated 12 of 39 runs at 4,000 tokens (self-correction loops). Full table above.
- **Gemma's selection got worse at repeat 1 at the larger cap:** one non-existent section (`W24X45` on F.3A) and one that fails the deflection check (`W21X55` on F.4), neither present at 1,500 tokens although those answers were not truncated. Voyager is not deterministic at temperature 0 (identical text across repeats on 0 of 13 problems for Qwen, 1 to 2 of 13 for Gemma), so I report these as run-to-run variation, not a cap effect.
- **The local qwen3.5:9b was not rerun** at 4,000 tokens (it would not finish within the one-hour limit), so the local column exists only at 1,500 tokens and only as a 17-run snapshot.
- **My first secret scan silently matched nothing**: the `grep` pattern did not fit how `.env` is formatted, so "no key found" came out empty for the wrong reason. I redid it by parsing `.env` the way the runner does; the key appears in no tracked file and no historical blob.
- **I first told you 26 AISC rows were in history; the exact count is 16.** The failed-run printouts contain only a traceback. I corrected it before acting on it.
- **The clean-clone test found a real gap:** a fresh clone had no `steelagent/data/` folder, so the README's instruction to save the Shapes Database there failed. Fixed with a placeholder file (`a2743fd`).
- **Smaller tool bugs fixed along the way:** the review-sheet quote originally started mid-word (it now quotes the whole original line); a wording glitch in the slide-facts generator ("ranges are:."); the facts generator's first edit pattern did not match and I applied the edits directly.
- **Rewriting history changed every commit hash, three times** (scrub, redaction, author identity; see "Hashes in older result files"). Content changed only in the redaction step, and only in text.
- **The automatic redaction garbled one sentence** in this summary (the paragraph that described the personal information, which contained the very strings being replaced). I caught it in review and rewrote it by hand in the next commit; no other redacted file needed a manual fix.
- **Redacting saved outputs edits files that other rules call "saved outputs".** Only path and name strings changed in the command logs, `meta.json` and `log.txt` files, never a number, and the scorer file and every `summary.json` hash are unchanged (sha256 prefix `c8e7959deb92`).
- **Carried over and still true:** the scores in System B are on an easy synthetic task; System C rests on 13 problems and many answers depend on recalled section properties; E7 is validated on few shapes; the Shapes Database is not in the repo, so every command needs it.

### Open questions
1. Keep or delete the two backup bundles one folder above the repo (pre-scrub and pre-redact history)? They are outside git and not published; deleting them removes the last unredacted copies, keeping them allows an undo.
2. Qwen with thinking ON, or a different prompt that asks for a shorter working? Qwen's long outputs are what truncate.


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
3. (Resolved 2026-11-13: the 17-run snapshot is kept; the local run is not extended. See "Decisions after the first public push", item 6.)
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
