"""Parsing and prompt-building for the System C pilot (no Ollama needed)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
import system_c_pilot as S  # noqa: E402


def test_parse_number_variants():
    assert S.parse_final_number("work...\nFINAL ANSWER: 1,250.5 kips") == (1250.5, "kips")
    assert S.parse_final_number("FINAL ANSWER: **304 kip-ft**") == (304.0, "kip-ft")
    assert S.parse_final_number("FINAL ANSWER: 12 kip\nFINAL ANSWER: 13 kips.") == (13.0, "kips")
    assert S.parse_final_number("no answer here") == (None, None)


def test_parse_section_variants():
    assert S.parse_final_section("FINAL ANSWER: W14x132") == "W14X132"
    assert S.parse_final_section("blah W18X40\nFINAL ANSWER: **W 21 X 48**") == "W21X48"
    assert S.parse_final_section("W14X90 might work\nFINAL ANSWER: none") is None


def test_unit_ok():
    assert S.unit_ok("kips", "kip") and S.unit_ok("", "kip") and not S.unit_ok("kip-ft", "kip")
    assert S.unit_ok("kip-ft", "kip-ft") and not S.unit_ok("kn", "kip-ft")


def test_prompts_cover_all_13_cases_and_hide_answers():
    ps = S.build_prompts()
    assert len(ps) == 13 and sum(p["kind"] == "strength" for p in ps) == 9
    import re
    for p in ps:
        assert "FINAL ANSWER" in p["prompt"]
        problem = p["prompt"].split("Problem:")[1].upper()
        answer = str(p["expected"]["value"]) if p["kind"] == "strength" else p["expected"]["section"]
        assert not re.search(rf"(?<![\d.]){re.escape(answer.upper())}(?![\d.])", problem), f"{p['id']}: answer leaked into prompt"
    texts = {p["id"]: p["prompt"] for p in ps}
    assert "An = 4.76" in texts["D.1-rupture"] and "U = 0.908" in texts["D.1-rupture"]
    assert "Lb = 11.667 ft" in texts["F.1-2B"] and "Cb = 1.01" in texts["F.1-2B"]


def test_prompts_do_not_name_the_governing_limit_state():
    for p in S.build_prompts():
        low = p["prompt"].lower()
        assert not any(w in low for w in ("elastic", "inelastic", "local buckling", "noncompact", "slender"))


def test_refusal_detection():
    assert S.is_refusal("I cannot determine this without the AISC tables.", answered=False)
    assert S.is_refusal("Unable to provide a number.", answered=False)
    assert not S.is_refusal("I cannot access tables, but estimating... FINAL ANSWER: 900 kips", answered=True)
    assert not S.is_refusal("Let me compute step by step...", answered=False)


def test_wrong_limit_state_classification():
    import json
    cases = {c["id"]: c for c in json.loads((S.C_DIR / "design_examples_strength.json").read_text(encoding="utf-8"))["cases"]}
    alts = S.alt_limit_states(cases["E.1C"])                     # y axis governs (892 kips); x axis gives a larger value
    assert alts["flexural buckling about x axis"] > 892
    x = alts["flexural buckling about x axis"]
    assert S.classify_wrong_limit_state(x * 1.004, 892, alts) == "flexural buckling about x axis"
    assert S.classify_wrong_limit_state(700.0, 892, alts) is None
    alts = S.alt_limit_states(cases["F.1-2B"])                   # LTB governs (304 kip-ft); phi*Mp is larger
    assert S.classify_wrong_limit_state(alts["plastic moment (yielding; ignores LTB/FLB)"], 304, alts).startswith("plastic moment")
    assert S.classify_wrong_limit_state(304.0, 304, alts) is None   # the right answer never counts as a wrong limit state


def test_stated_limit_state_beams():
    assert S.stated_limit_state("F.3B", "Since the flange is compact, strength is governed by plastic yielding.") == "plastic yielding"
    assert S.stated_limit_state("F.3B", "The flange is noncompact, so flange local buckling governs.") == "flange local buckling"
    # 'non-slender' must not be read as a slender flange (regression)
    assert S.stated_limit_state("F.1-1B", "Check limits for non-slender flanges. The flange local buckling limit state does not reduce the strength.") == "plastic yielding"
    assert S.stated_limit_state("F.1-2B", "Since $L_p < L_b < L_r$, the beam is in the **inelastic LTB** range.") == "inelastic LTB"
    assert S.stated_limit_state("F.1-3B", "Wait, $L_b > L_r$, so elastic lateral-torsional buckling applies.") == "elastic LTB"
    assert S.stated_limit_state("F.1-3B", "inelastic LTB first... Correction: elastic LTB governs.") == "elastic LTB"   # last statement wins
    assert S.stated_limit_state("F.1-2B", "no conclusion yet") is None
    assert S.stated_limit_state("E.1C", "weak axis governs") is None              # columns are not text-scored


def test_expected_limit_states():
    import json
    cases = {c["id"]: c for c in json.loads((S.C_DIR / "design_examples_strength.json").read_text(encoding="utf-8"))["cases"]}
    assert {k: S.expected_limit_state(cases[k]) for k in ("F.1-1B", "F.1-2B", "F.1-3B", "F.3B")} == {
        "F.1-1B": "plastic yielding", "F.1-2B": "inelastic LTB", "F.1-3B": "elastic LTB", "F.3B": "flange local buckling"}
    assert S.expected_limit_state(cases["E.1C"]) is None


def test_detail_returns_matched_text_and_statements():
    lab, snip = S.stated_limit_state_detail("F.3B", "Zx = 114.\nSince the flange is compact, the strength is governed by plastic yielding.\nFINAL ANSWER: 427 kip-ft")
    assert lab == "plastic yielding" and "plastic yielding" in snip
    assert S.stated_limit_state_detail("E.1C", "weak axis governs") == (None, None)
    gs = S.governing_statements("a\nthe weak axis governs\nb\nLTB does not control here\nlimit state: yielding")
    assert gs == "the weak axis governs || LTB does not control here || limit state: yielding"


def test_expected_governing_description_covers_all_13():
    import json
    sc = {c["id"]: c for c in json.loads((S.C_DIR / "design_examples_strength.json").read_text(encoding="utf-8"))["cases"]}
    se = {c["id"]: c for c in json.loads((S.C_DIR / "design_examples_selection.json").read_text(encoding="utf-8"))["cases"]}
    d = {k: S.expected_governing_description(c, "strength") for k, c in sc.items()} | {k: S.expected_governing_description(c, "selection") for k, c in se.items()}
    assert len(d) == 13 and all(d.values())
    assert d["E.1C"].startswith("flexural buckling about y axis") and d["G.1B"].startswith("shear yielding of web, G2.1(a)")
    assert d["F.3B"].startswith("flange local buckling") and "deflection" in d["F.4"]
