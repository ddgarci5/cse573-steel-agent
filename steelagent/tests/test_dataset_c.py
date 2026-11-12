"""Solver vs. Dataset C (AISC Design Examples v16.0): strength checks and section selection.

Cases are read from datasets/C_benchmark/*.json. Dataset C is validation-only; never used for training."""
import json
from pathlib import Path

import pytest

from steelagent import shapes
from steelagent.compression import compression_strength
from steelagent.flexure import flexure_strength, shear_strength
from steelagent.search import lightest
from steelagent.tension import tension_strength

C_DIR = Path(__file__).resolve().parents[2] / "datasets" / "C_benchmark"
STRENGTH = json.loads((C_DIR / "design_examples_strength.json").read_text(encoding="utf-8"))
SELECTION = json.loads((C_DIR / "design_examples_selection.json").read_text(encoding="utf-8"))


def _ours(case):
    s, i = shapes.get(case["shape"]), case["inputs"]
    return {
        "tension_yield": lambda: tension_strength(s)["phiPn_yield"],
        "tension_rupture": lambda: tension_strength(s, An=i["An_in2"], U=i["U"])["phiPn_rupture"],
        "compression": lambda: compression_strength(s, i["Lcx_ft"], i["Lcy_ft"])["phiPn"],
        "flexure": lambda: flexure_strength(s, i["Lb_ft"], i["Cb"])["phiMn"],
        "shear": lambda: shear_strength(s)["phiVn"],
    }[case["check"]]()


@pytest.mark.parametrize("case", STRENGTH["cases"], ids=lambda c: c["id"])
def test_strength_matches_published(case):
    ours, ref = _ours(case), case["published"]["value"]
    err_pct = 100 * (ours - ref) / ref
    assert abs(err_pct) <= STRENGTH["tolerance_pct"], f"{case['id']}: ours {ours:.2f}, AISC {ref}, err {err_pct:.2f}%"


def _lightest_up_to_depth(demands, geometry, max_depth, Ix_min):
    """Lightest section over nominal depths <= max_depth (search.lightest takes one depth at a time)."""
    best = None
    for depth in (18, 16, 14, 12, 10, 8, 6, 5, 4):
        if depth > max_depth:
            continue
        r = lightest("flexure", demands, geometry, depth=depth, Ix_min=Ix_min)
        if r["section"] and (best is None or shapes.get(r["section"])["W"] < shapes.get(best["section"])["W"]):
            best = r
    return best


@pytest.mark.parametrize("case", SELECTION["cases"], ids=lambda c: c["id"])
def test_selection_matches_published(case):
    d, g, c = case["demands"], case["geometry"], case["constraints"]
    if case["member_type"] == "compression":
        r = lightest("compression", {"Pu": d["Pu_kip"]}, g, depth=c.get("nominal_depth_in"))
    elif "max_depth_in" in c:
        r = _lightest_up_to_depth({"Mu": d["Mu_kipft"]}, g, c["max_depth_in"], c.get("Ix_min_in4"))
    else:
        r = lightest("flexure", {"Mu": d["Mu_kipft"]}, g, Ix_min=c.get("Ix_min_in4"))
    assert r["section"] == case["published"]["section"]
    assert r["utilization"] <= 1.0


def test_dataset_c_file_sizes():
    assert len(STRENGTH["cases"]) == 9 and len(SELECTION["cases"]) == 4
