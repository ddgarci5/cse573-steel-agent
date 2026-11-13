# Dataset D: natural-language problem to DesignCase pairs

Role (CLAUDE.md section 6): prompting, LoRA training and extraction tests. Three parts, kept apart so that nothing used for tuning is also used for testing:

| Part | What | Status |
|---|---|---|
| `human_test/` | **Human-written test split**: AISC "Given:" problems rewritten in the writer's own words, peer-written messy prompts, the student's own prompts, each with a gold DesignCase and an expected behavior (extract / ask the user / out of scope). **Test only.** | Intake kit and validator built 2026-11-13; **no items yet** (needs people) |
| templated train/dev | Template-generated problems with varied phrasing, units and omitted fields, labelled by construction | not started |
| LLM paraphrases | Paraphrases of templated problems, kept only if the parsed values match | not started |

## Rules
- The human split is never used for prompt tuning, few-shot examples, LoRA data or any training. Prompt development uses the templated dev part only.
- The 13 Dataset C problems (`datasets/C_benchmark/`) are a separate, templated-text evaluation and are also never training data. A human rewrite of a Dataset C problem is allowed and is reported as an overlap (`source_ref`).
- Only parameters and our own wording are stored. No AISC, textbook or teaching-module text (`references/` is gitignored and the builder rejects any item that copies a line from it).
- Writer ids are short codes; no names, emails or course details. Peer text is added only with the peer's consent (the repository is public).
- After the first model run on the split, items are frozen. `human_test.json` records `items_sha256`; any later edit is a documented new version and old results stay with the old hash.

## Workflow
`human_test/WRITER_GUIDE.md` (how to write and label items) -> `human_test/intake_<writer>.csv` -> `.venv/Scripts/python.exe eval/build_dataset_d_human.py` (validation, writes `human_test/human_test.json` and `build_report.txt`) -> second-person check of every gold row -> freeze.

## Known schema gaps the human split will expose (decide before extraction is scored on it)
- Problems give a length L and factors Kx, Ky rather than effective lengths. CLAUDE.md section 7 has `L_ft`, `Kx`, `Ky`; the current DesignCase (restricted to the 13 Dataset C problems) has only `Lcx_ft`, `Lcy_ft`. The intake already records L, Kx, Ky as `extra_gold`. Recommended: add the three fields to DesignCase so the model copies them and code computes K x L (the model must not multiply).
- Factored loads versus dead/live loads (load combinations are stretch scope): such items are `out_of_scope` with `expected_flag` = `other`.
- Tension and shear selection, ASD, other materials and non-W shapes are flagged unsupported.

## What is still needed to score the split
An evaluation runner for `human_test.json` (reuse `eval/first_slice_eval.py`): extraction field scores vs the gold row, correct abstention on `ask_user`, correct refusal on `out_of_scope`, and final answers from `route()` on the gold case as the reference (AISC published answers can be added as an optional column when a rewritten AISC problem has one). Not built yet.
