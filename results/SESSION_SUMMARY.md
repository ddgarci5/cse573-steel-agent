# Session summary, 2026-11-11 (backlog tasks 1-3)

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
