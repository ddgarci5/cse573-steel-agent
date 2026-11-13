# Writer guide: human-written test problems (Dataset D, `human_test` split)

This split measures how well the extraction step copes with problems written by real people, not by our templates. It only works if **people write the problems and nobody tunes anything against them**. Read all of this before adding a row.

## Hard rules
1. **Written by a person. Do not use an LLM to write, rephrase, "clean up" or translate any problem text.** The mess is the point.
2. **Own words only.** Never paste text from the AISC Manual, the AISC Design Examples, a textbook, or the sponsor's teaching modules (the repo is public and those are copyrighted). For an AISC "Given:" problem, read it, close the book, and write the problem the way a classmate would ask it. Only the problem parameters (numbers, shape, loads) carry over. Put the example number in `source_ref`.
3. **Peer messages:** add someone's message only with their OK, because the repository is public. Remove names, emails, course details and anything identifying. In `writer` use a short code (`student`, `peer1`, `peer2`), never a name.
4. **Never look at model outputs while writing, and never edit an item after a model has been run on the split.** If you find a mistake later, add a note in `notes` and tell the team; the fix is made as a documented new version, with the old results kept.
5. **Test only.** These items are never used for prompt wording, few-shot examples, LoRA data or any training.

## How to add problems
1. Copy `intake_template.csv` to `intake_<writer code>.csv` (for example `intake_peer1.csv`) and open it in Excel or Sheets. Keep the header row. Save as **CSV UTF-8**.
2. One row per problem. **Blank cell = null** (not stated). Write numbers only, in the unit shown in the column name (`Lcx_ft` in feet, `Pu_kip` in kips, `Mu_kipft` in kip-ft, `Ix_min_in4` in in^4). `0` is a real value (for example `Lb_ft` = 0 for a continuously braced beam).
3. Run `.venv/Scripts/python.exe eval/build_dataset_d_human.py` from the repo root. It lists errors (the build stops) and warnings, then writes `human_test.json`.
4. Ask a **second person** to fill the gold columns from the problem text alone (without seeing yours) or to check yours against the text. Note who checked in `notes` (`checked: peer2`). Disagreements are decided by the team, not by a model.

## Columns
| Column | What to write |
|---|---|
| `item_id` | `H001`, `H002`, ... unique across all files (agree a range per writer, for example peer1 H100-H199) |
| `writer` | short code, no names |
| `source_type` | `aisc_given_rewritten`, `peer_written` or `student_written` |
| `source_ref` | required for `aisc_given_rewritten` (for example `Design Example F.2-1, rewritten in own words`); optional otherwise |
| `problem_text` | the problem exactly as a person would type it, typos included |
| `expected_behavior` | `extract`: complete and in scope, the agent should compute. `ask_user`: the check needs inputs the text does not give; the agent should ask and not compute. `out_of_scope`: the MVP cannot handle it (non-A992 steel, ASD, HSS or channel, combined forces, tension or shear selection...); the agent should say so |
| `expected_flag` | only for `out_of_scope`: `unsupported_material`, `unsupported_design_method`, `unsupported_combination`, `section_not_in_database`, `An_exceeds_Ag`, or `other` when the schema cannot even hold the problem (for example a beam-column interaction check) |
| `tags` | optional, `;`-separated: `units_mixed`, `abbreviation`, `missing_assumption`, `ambiguous_phrasing`, `K_and_L_given`, `load_in_other_units`, `extra_irrelevant_info`, `typo`, `implicit_value`, `multiple_questions`, `non_A992`, `non_W_shape`, `needs_load_combination`, `other` |
| `conversion_note` | if a gold number is not literally in the text (a unit conversion, for example `168 in = 14 ft`), say how you got it |
| `notes` | anything else, including who checked the row |
| gold columns | `member_type` (`tension`, `compression`, `flexure`, `shear`), `task` (`check_given_section` or `select_lightest`), `section` (for example `W14X90`), `requested_limit_states` (tension only: `tension_yield` and/or `tension_rupture`), `design_method` (blank = LRFD), `material_grade`/`Fy_ksi`/`Fu_ksi`/`E_ksi` (blank = A992 defaults), the demands, geometry, net-section and constraint columns, and `missing_fields` (`;`-separated names of inputs the check needs and the text lacks) |
| `L_ft`, `Kx`, `Ky` | when the text gives a length and K factors instead of effective lengths. They are stored as `extra_gold` and are **not scored yet**, because the current schema holds effective lengths only (see README). Also fill `Lcx_ft`, `Lcy_ft` with K x L so the row validates |

Gold rules: record what the text says, not what you would assume. If the text omits a needed input, leave it blank and list it in `missing_fields` (`ask_user`). Do not fill a value because "it is usually 1.0". Cb is needed only when Lb is not 0.

## What makes a good test item (aim for variety, not volume)
- Messy or conversational phrasing, abbreviations ("W14x90 col", "pin-pin", "KL"), typos, missing punctuation.
- Mixed or unusual units that convert cleanly (inches for lengths, loads stated in kips but moments in kip-in).
- Irrelevant details around the real inputs (building name, why the member is needed).
- Missing assumptions: no unbraced length, no Cb, no net area for a rupture check, no limit state named for a tension member.
- Several quantities in one message where only some matter.
- A few problems that are out of scope on purpose.

Proposed targets (a proposal, not yet agreed): at least 40 items; at least 6 per member type; at least 10 selections; at least 8 `ask_user`; at least 5 `out_of_scope`; at least 12 rewritten AISC "Given:" problems; at least 12 peer-written from at least 3 different people. Below about 30 items, report counts, not percentages.

Format illustrations (not part of the split, do not copy their wording): a one-line chat message asking for a column capacity with only one length given is an `ask_user` row; a message asking for an HSS column capacity is `out_of_scope` with `expected_flag` = `section_not_in_database`; a request with dead load and live load and no factored load is `out_of_scope` with `expected_flag` = `other` and tag `needs_load_combination`.
