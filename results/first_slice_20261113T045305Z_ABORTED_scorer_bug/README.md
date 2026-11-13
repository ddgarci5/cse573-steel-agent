# Aborted run (kept as a record, never scored)

This is the first execution of the first-slice evaluation (78 extraction runs, 2 models x 13 problems x 3 repeats, no retries logged).
`eval/first_slice_eval.py score` crashed before computing any number: a result column named `flags` collided with pandas' `DataFrame.flags`
attribute. The crash happened before any score was produced or read. The bug was in the scoring code, not in the model outputs, but the run's
`meta.json` records the scorer hash that was current at run time, so the whole evaluation was rerun with the fixed scorer in a new folder
(see `results/SESSION_SUMMARY.md`). These raw outputs are not used in any reported metric.
