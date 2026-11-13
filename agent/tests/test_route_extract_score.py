"""Route, extract and scoring logic, tested with fake LLMs (no network, no API key). An 'oracle' LLM that returns the gold JSON must give 13/13."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eval"))
import first_slice_eval as E  # noqa: E402
from agent import extract as X  # noqa: E402
from agent.design_case import DesignCase  # noqa: E402
from agent.route import route  # noqa: E402

GOLD = E.load_gold()
STRENGTH, SELECTION = E.dataset_c()
TEXTS = E.problem_texts()
CTRL = E.gold_control()


def gold_dict(pid):
    return json.loads(json.dumps({k: v for k, v in GOLD[pid]["design_case"].items() if k != "problem_id"}))


def oracle_for(pid, mutate=None):
    d = gold_dict(pid)
    if mutate:
        mutate(d)
    return lambda messages: {"response": json.dumps(d), "finish_reason": "stop", "completion_tokens": 100}


def run_record(pid, ask, repeat=1):
    res = X.extract(TEXTS[pid], pid, ask)
    case = res["case"]
    return {"id": pid, "repeat": repeat, "status": res["status"], "case": case.model_dump(mode="json") if case else None,
            "route": route(case) if case else None, "attempts": res["attempts"]}


def score(rec):
    return E.score_run(rec, GOLD, STRENGTH, SELECTION, CTRL)


def test_gold_control_all_13_pass_and_route_equals_direct_system_a():
    assert len(CTRL) == 13
    for pid, c in CTRL.items():
        assert c["direct_ok"] and c["route_ok"] and c["route_equals_direct"], pid


@pytest.mark.parametrize("pid", list(GOLD))
def test_oracle_llm_is_correct_on_every_problem(pid):
    row = score(run_record(pid, oracle_for(pid)))
    assert row["extraction_status"] == "valid_first_try" and row["exact_match"] and row["correct"] and not row["unsafe"], row
    assert row["n_wrong_fields"] == 0 and row["error_class"] is None


def test_problem_id_is_set_by_the_harness_and_never_shown_to_the_model():
    pid, seen = "F.3B", []

    def ask(messages):
        seen.append(messages[0]["content"])
        d = gold_dict(pid)
        d["problem_id"] = "SOMETHING-ELSE"
        return {"response": json.dumps(d)}

    res = X.extract(TEXTS[pid], pid, ask)
    assert res["case"].problem_id == pid and "F.3B" not in seen[0]


def test_prompt_instructions_contain_no_published_answer():
    for pid in GOLD:
        pub = (STRENGTH.get(pid) or SELECTION[pid])["published"]
        answer = str(pub.get("value", pub.get("section")))
        assert answer not in X.PROMPT, (pid, answer)


def test_one_retry_with_error_text_then_valid():
    pid, calls = "E.1C", []
    good, bad = gold_dict(pid), gold_dict(pid)
    bad["geometry"]["Lcx_ft"] = 3000

    def ask(messages):
        calls.append(messages)
        return {"response": json.dumps(bad if len(calls) == 1 else good)}

    res = X.extract(TEXTS[pid], pid, ask)
    assert res["status"] == "valid_after_retry" and len(calls) == 2 and len(res["attempts"]) == 2
    assert "geometry.Lcx_ft" in calls[1][-1]["content"] and calls[1][1]["role"] == "assistant"


def test_invalid_after_one_retry_is_never_retried_twice_and_is_scored_as_no_answer():
    pid, n = "E.1C", []

    def ask(messages):
        n.append(1)
        return {"response": "The answer is 892 kips.", "finish_reason": "stop"}

    rec = run_record(pid, ask)
    assert len(n) == 2 and rec["status"] == "invalid" and rec["case"] is None and rec["route"] is None
    row = score(rec)
    assert row["outcome"] == "no answer" and not row["unsafe"] and row["error_class"] == "extraction error" and row["n_wrong_fields"] == len(E.LEAVES)


def test_code_fence_is_tolerated_and_recorded():
    pid = "G.1B"
    d = gold_dict(pid)
    rec = run_record(pid, lambda m: {"response": "```json\n" + json.dumps(d) + "\n```"})
    assert rec["status"] == "valid_first_try" and rec["attempts"][0]["fenced"] is True


def test_nonexistent_section_is_flagged_not_corrected_not_retried_not_computed():
    pid, n = "G.1B", []

    def ask(messages):
        n.append(1)
        d = gold_dict(pid)
        d["section"] = "W24X63"
        return {"response": json.dumps(d)}

    rec = run_record(pid, ask)
    assert len(n) == 1 and rec["case"]["section"] == "W24X63"
    assert rec["route"]["status"] == "flagged_not_computed" and rec["route"]["answer"] is None
    row = score(rec)
    assert row["section_flagged_nonexistent"] and row["outcome"] == "no answer" and row["error_class"] == "extraction error"


def test_missing_input_means_would_ask_user_and_no_computation():
    pid = "E.1D"

    def mut(d):
        d["geometry"]["Lcy_ft"] = None
        d["missing_fields"] = ["Lcy_ft"]

    rec = run_record(pid, oracle_for(pid, mut))
    assert rec["route"]["status"] == "would_ask_user" and rec["route"]["answer"] is None and rec["route"]["missing"] == ["Lcy_ft"]
    row = score(rec)
    assert row["outcome"] == "no answer" and not row["unsafe"]
    assert "geometry.Lcy_ft" in row["wrong_fields"] and "missing_fields" in row["wrong_fields"]


def test_wrong_extracted_number_is_an_extraction_error_and_overstatement_is_unsafe():
    pid = "E.1D"
    row = score(run_record(pid, oracle_for(pid, lambda d: d["geometry"].update(Lcx_ft=10))))   # 30 ft read as 10 ft -> higher capacity
    assert row["outcome"] == "wrong answer" and row["error_class"] == "extraction error" and row["unsafe"] and row["err_pct"] > 1
    assert row["wrong_fields"].startswith("geometry.Lcx_ft")


def test_selection_with_wrong_demand_is_caught_against_the_true_case():
    pid = "E.1A"
    row = score(run_record(pid, oracle_for(pid, lambda d: d["demands"].update(Pu_kip=100))))   # 840 read as 100 kip
    assert row["outcome"] == "wrong answer" and row["unsafe"] and row["system_a_pass"] is False and row["error_class"] == "extraction error"


def test_numeric_tolerance_is_half_a_percent():
    pid = "F.1-2B"   # gold Lb = 35/3; the text says 11.667 (0.003 % off) and must still match
    row = score(run_record(pid, oracle_for(pid, lambda d: d["geometry"].update(Lb_ft=11.667))))
    assert row["exact_match"] and row["correct"]
    row = score(run_record(pid, oracle_for(pid, lambda d: d["geometry"].update(Lb_ft=11.9))))
    assert not row["exact_match"]


def test_max_depth_selection_searches_all_allowed_nominal_depths():
    case = DesignCase.model_validate(GOLD["F.1-1A"]["design_case"])
    r = route(case)
    assert r["section"] == "W18X50" and max(r["depths_searched"]) == 18 and r["controls"] == "deflection"
    case.constraints.max_depth_in = 14
    r2 = route(case)
    assert r2["section"] is None or int(r2["section"][1:].split("X")[0]) <= 14


def test_tension_with_unspecified_limit_state_needs_an_and_u():
    case = DesignCase.model_validate({"member_type": "tension", "task": "check_given_section", "section": "W8X21", "missing_fields": ["An_in2", "U"]})
    assert route(case)["status"] == "would_ask_user"


def test_score_command_end_to_end_on_a_synthetic_run(tmp_path, monkeypatch):
    """The full `score` path (scores.csv, summary.json, SCORES.md) on synthetic raw records: oracle on 13 problems plus a few failure types.
    This is the test that would have caught the 'flags' column name clashing with pandas' DataFrame.flags."""
    mdir = tmp_path / "fake-model"
    (mdir / "raw").mkdir(parents=True)
    (tmp_path / "gold_control.json").write_text(json.dumps(CTRL, default=str), encoding="utf-8")
    cases = {"E.1D": lambda d: d["geometry"].update(Lcx_ft=10), "G.1B": lambda d: d.update(section="W24X63"), "F.3A": lambda d: d["demands"].update(Mu_kipft=100)}
    for pid in GOLD:
        rec = run_record(pid, oracle_for(pid, cases.get(pid)))
        rec.update(model="fake-model", problem_text=TEXTS[pid], wall_seconds=1.0, finished_utc="x")
        (mdir / "raw" / f"{pid}_r1.json").write_text(json.dumps(rec, default=str), encoding="utf-8")
    bad = run_record("E.1C", lambda m: {"response": "no json", "finish_reason": "length", "completion_tokens": 1000})
    bad.update(model="fake-model", problem_text=TEXTS["E.1C"], wall_seconds=1.0, finished_utc="x", repeat=2)
    (mdir / "raw" / "E.1C_r2.json").write_text(json.dumps(bad, default=str), encoding="utf-8")

    import argparse
    E.score(argparse.Namespace(run_dir=str(tmp_path)))
    summ = json.loads((mdir / "summary.json").read_text(encoding="utf-8"))
    assert summ["runs"] == 14 and summ["validity"]["invalid"] == 1 and summ["validity"]["valid_first_try"] == 13
    assert summ["validity"]["section_flagged_not_in_database"] == 1 and summ["validity"]["truncated_responses"] == 1
    assert summ["strength"]["unsafe_overstated_gt_1pct"] == 1 and summ["selection"]["unsafe_fails_system_a"] == 1
    assert summ["final_correct_total"] == 10 and summ["error_trace_of_runs_not_correct"] == {"extraction error": 4}
    assert (tmp_path / "SCORES.md").exists() and (mdir / "scores.csv").exists() and (mdir / "field_errors.csv").exists()
