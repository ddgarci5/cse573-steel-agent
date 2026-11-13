"""Gold DesignCases: valid, complete for all 13 Dataset C problems, equal to the mechanical mapping of the Dataset C JSON, and Dataset C untouched."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eval"))
from agent.design_case import DesignCase  # noqa: E402
import make_gold_design_cases as G  # noqa: E402

C_DIR = ROOT / "datasets" / "C_benchmark"
GOLD = json.loads((C_DIR / "gold_design_cases.json").read_text(encoding="utf-8"))


def test_gold_is_up_to_date_with_the_generator():
    assert GOLD["cases"] == G.build()


def test_13_valid_unflagged_complete_cases():
    assert len(GOLD["cases"]) == 13 and len({c["problem_id"] for c in GOLD["cases"]}) == 13
    for c in GOLD["cases"]:
        dc = DesignCase.model_validate(c["design_case"])
        assert dc.flags() == [] and dc.effective_missing_fields() == [] and dc.missing_fields == [], c["problem_id"]


def test_numeric_inputs_equal_dataset_c():
    src = {c["id"]: c for f in ("design_examples_strength.json", "design_examples_selection.json")
           for c in json.loads((C_DIR / f).read_text(encoding="utf-8"))["cases"]}
    for g in GOLD["cases"]:
        d, s = g["design_case"], src[g["problem_id"]]
        flat = {**d["geometry"], **d["net_section"], **d["demands"], **d["constraints"]}
        given = {**s.get("inputs", {}), **s.get("demands", {}), **s.get("geometry", {}), **s.get("constraints", {})}
        for k, v in given.items():
            assert flat[k] == v, (g["problem_id"], k)
        assert d["section"] == s.get("shape") or d["section"] is None
