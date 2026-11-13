"""Deterministic routing: a validated DesignCase -> the existing steelagent (System A) functions. Plain Python; no LLM, no model call.

route(case) returns a dict with
  status   "computed" | "would_ask_user" | "flagged_not_computed"
  answer / unit / quantity   (check_given_section) the capacity the question asks for
  section / utilization / controls / weight   (select_lightest) the lightest section that passes every check, or None
  missing, flags, notes
Nothing is computed when a domain flag is raised or a required input is missing: the case is reported as "would ask the user".
Rule 2 (CLAUDE.md): a selection is returned only if search.lightest found a section whose every check passes.
No solver code is modified here; the only logic added is choosing which solver function to call and, for "nominal depth no more than N", looping
over the nominal depths in the database (search.lightest takes one depth at a time; same approach as steelagent/tests/test_dataset_c.py).
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "steelagent") not in sys.path:
    sys.path.insert(0, str(ROOT / "steelagent"))

from steelagent import shapes  # noqa: E402
from steelagent.compression import compression_strength  # noqa: E402
from steelagent.flexure import flexure_strength, shear_strength  # noqa: E402
from steelagent.search import lightest  # noqa: E402
from steelagent.tension import tension_strength  # noqa: E402

from agent.design_case import DesignCase  # noqa: E402


def _nominal_depths_up_to(max_depth):
    depths = {int(re.match(r"W(\d+)X", lab).group(1)) for lab in shapes.w_shapes().index}
    return sorted((d for d in depths if d <= max_depth), reverse=True)


def _select(case: DesignCase):
    d, g, c = case.demands, case.geometry, case.constraints
    if c.nominal_depth_in is not None:
        depths = [c.nominal_depth_in]                      # an exact nominal depth wins if a maximum is also given
    elif c.max_depth_in is not None:
        depths = _nominal_depths_up_to(c.max_depth_in)     # deepest first, so a weight tie goes to the deeper section (as in test_dataset_c.py)
    else:
        depths = [None]
    if case.member_type == "compression":
        member, demands, geom, Ix_min = "compression", {"Pu": d.Pu_kip}, {"Lcx_ft": g.Lcx_ft, "Lcy_ft": g.Lcy_ft}, None
    else:  # flexure
        member = "flexure"
        demands = {"Mu": d.Mu_kipft, **({"Vu": d.Vu_kip} if d.Vu_kip is not None else {})}
        geom = {"Lb_ft": g.Lb_ft, **({"Cb": g.Cb} if g.Cb is not None else {})}   # Cb absent only when Lb = 0, where the search default (1.0) cannot matter
        Ix_min = c.Ix_min_in4
    best = None
    for depth in depths:
        r = lightest(member, demands, geom, depth=depth, Ix_min=Ix_min)
        if r["section"] and (best is None or float(shapes.get(r["section"])["W"]) < float(shapes.get(best["section"])["W"])):
            best = r
    r = best if best is not None else {"section": None}
    return {"section": r["section"], "utilization": r.get("utilization"), "controls": r.get("controls"), "depths_searched": depths,
            "weight_lb_ft": float(shapes.get(r["section"])["W"]) if r["section"] else None}


def route(case: DesignCase) -> dict:
    flags = case.flags()
    missing = case.effective_missing_fields()
    base = {"problem_id": case.problem_id, "member_type": case.member_type, "task": case.task, "flags": flags, "missing": missing,
            "answer": None, "unit": None, "quantity": None, "section": None, "utilization": None, "controls": None, "notes": []}
    if flags:
        return {**base, "status": "flagged_not_computed", "notes": ["not computed: " + "; ".join(f["message"] for f in flags)]}
    if missing:
        return {**base, "status": "would_ask_user", "notes": [f"would ask the user for: {', '.join(missing)}"]}

    if case.task == "select_lightest":
        sel = _select(case)
        note = [] if sel["section"] else ["no W-shape passes every required check under these inputs"]
        return {**base, "status": "computed", **sel, "notes": note}

    s = shapes.get(case.section)
    g, n, d = case.geometry, case.net_section, case.demands
    if case.member_type == "tension":
        want = case.requested_limit_states or ["tension_yield", "tension_rupture"]
        r = tension_strength(s, An=n.An_in2, U=n.U)
        vals = {"tension_yield": r["phiPn_yield"], **({"tension_rupture": r["phiPn_rupture"]} if "phiPn_rupture" in r else {})}
        chosen = {k: vals[k] for k in want}
        key = min(chosen, key=chosen.get)
        answer, unit, qty, cap = chosen[key], "kip", f"phiPn ({key})", chosen[key]
        dem = d.Pu_kip
    elif case.member_type == "compression":
        r = compression_strength(s, g.Lcx_ft, g.Lcy_ft)
        answer, unit, qty, cap, dem = r["phiPn"], "kip", "phiPn (compression, E3/E7)", r["phiPn"], d.Pu_kip
    elif case.member_type == "flexure":
        r = flexure_strength(s, g.Lb_ft, g.Cb if g.Cb is not None else 1.0)   # Cb is null here only when Lb = 0 (LTB cannot reduce Mn)
        answer, unit, qty, cap, dem = r["phiMn"], "kip-ft", "phiMn (major-axis flexure, F2/F3)", r["phiMn"], d.Mu_kipft
    else:  # shear
        r = shear_strength(s)
        answer, unit, qty, cap, dem = r["phiVn"], "kip", "phiVn (web shear, G2.1)", r["phiVn"], d.Vu_kip
    return {**base, "status": "computed", "answer": float(answer), "unit": unit, "quantity": qty, "section": case.section,
            "utilization": (dem / cap) if dem is not None else None}
