# First agent slice: scores (first_slice_20261113T045951Z)

Scorer sha256 `cc06b06bdda4`, prompt `extract-v1` sha256 `2f011000976b`.

## gemma4-31b-it

```json
{
  "runs": 39,
  "problems": 13,
  "repeats": 3,
  "validity": {
    "valid_first_try": 39,
    "valid_after_retry": 0,
    "invalid": 0,
    "responses_in_code_fence": 39,
    "truncated_responses": 0,
    "section_flagged_not_in_database": 0,
    "runs_with_any_domain_flag": 0
  },
  "extraction": {
    "exact_match_runs": 36,
    "exact_match_of_valid": "36 of 39",
    "field_accuracy_all_runs": 0.9965034965034965,
    "field_accuracy_valid_runs": 0.9965034965034965,
    "field_micro_precision_all": 0.9846153846153847,
    "field_micro_recall_all": 1.0,
    "field_micro_f1_all": 0.9922480620155039,
    "field_tp_fp_fn_all": [
      192,
      3,
      0
    ],
    "field_tp_fp_fn_valid_only": [
      192,
      3,
      0
    ],
    "runs_with_wrong_or_missing_field": 3,
    "route_status_counts": {
      "computed": 36,
      "would_ask_user": 3
    }
  },
  "strength": {
    "runs": 27,
    "answered": 27,
    "no_answer": 0,
    "within_1pct": 27,
    "unsafe_overstated_gt_1pct": 0,
    "max_abs_err_pct_answered": 0.46603204219891087
  },
  "selection": {
    "runs": 12,
    "answered": 9,
    "no_answer": 3,
    "exact_match": 9,
    "unsafe_fails_system_a": 0
  },
  "final_correct_total": 36,
  "unsafe_total": 0,
  "error_trace_of_runs_not_correct": {
    "extraction error": 3
  },
  "error_trace_of_wrong_answers_only": {},
  "mean_completion_tokens": 284.7692307692308,
  "mean_wall_seconds": 9.700000000000001,
  "scorer_sha256": "cc06b06bdda4407618585f156734b9d30d5dee05fb03644cd91d9c5543e6b8ae"
}
```

### Every run with a wrong or missing field

- **E.1A r1** (valid_first_try): missing_fields: got ['section'] expected []
- **E.1A r2** (valid_first_try): missing_fields: got ['section'] expected []
- **E.1A r3** (valid_first_try): missing_fields: got ['section'] expected []

### Runs that are not correct (error trace)

- **E.1A r1**: no answer, extraction error; final=nan published='W14X132'
- **E.1A r2**: no answer, extraction error; final=nan published='W14X132'
- **E.1A r3**: no answer, extraction error; final=nan published='W14X132'

### System C (cap 4,000, `system_c_pilot_voyager_gemma4-31b-it_cap4000_20261113T021439Z`) vs this slice, gemma4-31b-it

| Metric | System C @ 4,000 | Slice (extract + route) |
|---|---|---|
| Strength runs | 27 | 27 |
| Strength: within 1% of AISC | 15 of 27 | 27 of 27 |
| Strength: no answer (no final number / abstained / invalid) | 0 of 27 | 0 of 27 |
| Strength: overestimate > 1% (unsafe direction) | 5 of 27 | 0 of 27 |
| Selection runs | 12 | 12 |
| Selection: exact match to AISC section | 8 of 12 | 9 of 12 |
| Selection: no answer | 0 of 12 | 3 of 12 |
| Selection: recommended section fails a System A check (unsafe) | 1 of 12 | 0 of 12 |
| Selection: section not in AISC database (System C: proposed; slice: cannot occur, the search only returns database sections) | 1 of 12 | 0 of 12 (by construction) |
| Truncated outputs at the cap (System C 4,000 tokens; slice 1,000) | 0 of 39 | 0 of 39 |
| Mean output tokens per run | 746 | 285 |

## qwen38-27b

```json
{
  "runs": 39,
  "problems": 13,
  "repeats": 3,
  "validity": {
    "valid_first_try": 39,
    "valid_after_retry": 0,
    "invalid": 0,
    "responses_in_code_fence": 0,
    "truncated_responses": 0,
    "section_flagged_not_in_database": 0,
    "runs_with_any_domain_flag": 0
  },
  "extraction": {
    "exact_match_runs": 39,
    "exact_match_of_valid": "39 of 39",
    "field_accuracy_all_runs": 1.0,
    "field_accuracy_valid_runs": 1.0,
    "field_micro_precision_all": 1.0,
    "field_micro_recall_all": 1.0,
    "field_micro_f1_all": 1.0,
    "field_tp_fp_fn_all": [
      192,
      0,
      0
    ],
    "field_tp_fp_fn_valid_only": [
      192,
      0,
      0
    ],
    "runs_with_wrong_or_missing_field": 0,
    "route_status_counts": {
      "computed": 39
    }
  },
  "strength": {
    "runs": 27,
    "answered": 27,
    "no_answer": 0,
    "within_1pct": 27,
    "unsafe_overstated_gt_1pct": 0,
    "max_abs_err_pct_answered": 0.46603204219891087
  },
  "selection": {
    "runs": 12,
    "answered": 12,
    "no_answer": 0,
    "exact_match": 12,
    "unsafe_fails_system_a": 0
  },
  "final_correct_total": 39,
  "unsafe_total": 0,
  "error_trace_of_runs_not_correct": {},
  "error_trace_of_wrong_answers_only": {},
  "mean_completion_tokens": 265.7692307692308,
  "mean_wall_seconds": 7.087179487179487,
  "scorer_sha256": "cc06b06bdda4407618585f156734b9d30d5dee05fb03644cd91d9c5543e6b8ae"
}
```

### Every run with a wrong or missing field

- none

### Runs that are not correct (error trace)

- none

### System C (cap 4,000, `system_c_pilot_voyager_qwen38-27b_cap4000_20261113T021439Z`) vs this slice, qwen38-27b

| Metric | System C @ 4,000 | Slice (extract + route) |
|---|---|---|
| Strength runs | 27 | 27 |
| Strength: within 1% of AISC | 7 of 27 | 27 of 27 |
| Strength: no answer (no final number / abstained / invalid) | 10 of 27 | 0 of 27 |
| Strength: overestimate > 1% (unsafe direction) | 7 of 27 | 0 of 27 |
| Selection runs | 12 | 12 |
| Selection: exact match to AISC section | 3 of 12 | 12 of 12 |
| Selection: no answer | 2 of 12 | 0 of 12 |
| Selection: recommended section fails a System A check (unsafe) | 0 of 12 | 0 of 12 |
| Selection: section not in AISC database (System C: proposed; slice: cannot occur, the search only returns database sections) | 2 of 12 | 0 of 12 (by construction) |
| Truncated outputs at the cap (System C 4,000 tokens; slice 1,000) | 12 of 39 | 0 of 39 |
| Mean output tokens per run | 2,389 | 266 |

