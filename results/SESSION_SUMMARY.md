# Session summary (newest first)

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
