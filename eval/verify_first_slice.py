"""Independent re-computation of the first-slice headline numbers from the SAVED RAW OUTPUTS (no model calls, nothing re-run).

Deliberately does not use eval/first_slice_eval.py's scoring functions or any scores.csv / summary.json when it computes a number: it reads
<run>/<model>/raw/*.json (the model replies, the validated case, the route result), the gold cases and the Dataset C JSON, re-derives every
count with its own code, and only then compares with (a) the scorer's summary.json and (b) the numbers claimed in results/SESSION_SUMMARY.md
(written below as CLAIMS). Also re-derives the System C numbers at the 4,000-token cap from those runs' raw outputs.
It does re-run two deterministic things on the stored data: the router (stored route result must equal route(stored case)) and System A checks.
It uses the frozen answer parsers of eval/system_c_pilot.py for the System C raw text (the parsers are not what is being verified).

Usage (repo root):  .venv/Scripts/python.exe eval/verify_first_slice.py --run-dir results/first_slice_20261113T045951Z --aborted-dir <aborted dir>
Writes results/first_slice_verification_<ts>/verification.json and verification.txt
"""
import argparse
import datetime
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "steelagent"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import system_c_pilot as S  # noqa: E402  (frozen parsers for System C raw text only)
from agent import extract as X  # noqa: E402
from agent.design_case import DesignCase  # noqa: E402
from agent.route import route  # noqa: E402
from make_gold_design_cases import problem_texts  # noqa: E402
from steelagent import shapes  # noqa: E402
from steelagent.compression import compression_strength  # noqa: E402
from steelagent.flexure import flexure_strength  # noqa: E402

C_DIR = ROOT / "datasets" / "C_benchmark"
MODELS = ("gemma4-31b-it", "qwen38-27b")

# Numbers as written in results/SESSION_SUMMARY.md (first-slice sections). (gemma, qwen)
CLAIMS = {
    "runs": (39, 39), "valid_first_try": (39, 39), "valid_after_retry": (0, 0), "invalid": (0, 0), "retries_used": (0, 0),
    "in_code_fence": (39, 0), "truncated": (0, 0), "section_flagged_nonexistent": (0, 0),
    "exact_match": (36, 39), "leaves_correct": (855, 858), "leaves_total": (858, 858),
    "tp": (192, 192), "fp": (3, 0), "fn": (0, 0),
    "strength_runs": (27, 27), "strength_within_1pct": (27, 27), "strength_max_abs_err_pct_3dp": (0.466, 0.466),
    "selection_runs": (12, 12), "selection_exact": (9, 12), "would_ask_user": (3, 0), "unsafe_total": (0, 0),
    "err_extraction": (3, 0), "err_routing": (0, 0), "err_solver": (0, 0),
    "mean_completion_tokens_0dp": (285, 266), "mean_wall_seconds_1dp": (9.7, 7.1), "max_completion_tokens": (298, 281),
}
SYSTEM_C_CLAIMS = {  # System C at the 4,000-token cap: (gemma, qwen)
    "strength_runs": (27, 27), "within_1pct": (15, 7), "no_answer": (0, 10), "overestimate_gt_1pct": (5, 7),
    "selection_runs": (12, 12), "sel_exact": (8, 3), "sel_no_answer": (0, 2), "sel_unsafe": (1, 0), "sel_not_in_db": (1, 2),
    "truncated": (0, 12), "runs": (39, 39), "mean_tokens_0dp": (746, 2389),
}


# ------------------------------------------------------------ own comparer (recursive, not the scorer's LEAVES list)
def flatten(d, prefix=""):
    out = {}
    for k, v in d.items():
        if k == "problem_id":
            continue
        if isinstance(v, dict):
            out.update(flatten(v, prefix + k + "."))
        else:
            out[prefix + k] = tuple(sorted(v)) if isinstance(v, list) else v
    return out


def same(a, b):
    if isinstance(a, tuple) or isinstance(b, tuple):
        return tuple(a or ()) == tuple(b or ())
    if a is None or b is None:
        return a is None and b is None
    if isinstance(b, (int, float)) and not isinstance(b, bool):
        return (a == 0) if b == 0 else abs(a - b) / abs(b) <= 0.005
    return a == b


def sec_check(label, case):
    """Own System A re-check of a recommended section against the TRUE Dataset C case. Returns (exists, passes)."""
    if label not in shapes.w_shapes().index:
        return False, False
    s = shapes.get(label)
    d, g, c = case["demands"], case["geometry"], case["constraints"]
    ok = True
    if case["member_type"] == "compression":
        ok &= d["Pu_kip"] <= compression_strength(s, g["Lcx_ft"], g["Lcy_ft"])["phiPn"]
        if "nominal_depth_in" in c:
            ok &= label.startswith("W%dX" % c["nominal_depth_in"])
    else:
        ok &= d["Mu_kipft"] <= flexure_strength(s, g["Lb_ft"], g.get("Cb", 1.0))["phiMn"]
        if "Ix_min_in4" in c:
            ok &= s["Ix"] >= c["Ix_min_in4"]
        if "max_depth_in" in c:
            ok &= int(label[1:].split("X")[0]) <= c["max_depth_in"]
    return True, bool(ok)


def direct_value(case):
    from steelagent.flexure import shear_strength
    from steelagent.tension import tension_strength
    s, i = shapes.get(case["shape"]), case["inputs"]
    return {"tension_yield": lambda: tension_strength(s)["phiPn_yield"], "tension_rupture": lambda: tension_strength(s, An=i["An_in2"], U=i["U"])["phiPn_rupture"],
            "compression": lambda: compression_strength(s, i["Lcx_ft"], i["Lcy_ft"])["phiPn"], "flexure": lambda: flexure_strength(s, i["Lb_ft"], i["Cb"])["phiMn"],
            "shear": lambda: shear_strength(s)["phiVn"]}[case["check"]]()


def load_dc():
    strength = {c["id"]: c for c in json.loads((C_DIR / "design_examples_strength.json").read_text(encoding="utf-8"))["cases"]}
    selection = {c["id"]: c for c in json.loads((C_DIR / "design_examples_selection.json").read_text(encoding="utf-8"))["cases"]}
    gold = {c["problem_id"]: c["design_case"] for c in json.loads((C_DIR / "gold_design_cases.json").read_text(encoding="utf-8"))["cases"]}
    return strength, selection, gold


def recompute_model(run_dir, model, strength, selection, gold, texts):
    recs = [json.loads(f.read_text(encoding="utf-8")) for f in sorted((run_dir / model / "raw").glob("*.json"))]
    out = {"runs": len(recs), "valid_first_try": 0, "valid_after_retry": 0, "invalid": 0, "retries_used": 0, "in_code_fence": 0, "truncated": 0,
           "section_flagged_nonexistent": 0, "exact_match": 0, "leaves_correct": 0, "leaves_total": 0, "tp": 0, "fp": 0, "fn": 0,
           "strength_runs": 0, "strength_within_1pct": 0, "strength_overstated_gt_1pct": 0, "selection_runs": 0, "selection_exact": 0, "would_ask_user": 0,
           "flagged_not_computed": 0, "unsafe_total": 0, "err_extraction": 0, "err_routing": 0, "err_solver": 0, "err_unexplained": 0,
           "no_answer": 0}
    errs, wrong_fields, tokens, secs, prompt_ok, route_repro = [], [], [], [], True, True
    max_err = 0.0
    for r in recs:
        pid, att = r["id"], r["attempts"]
        prompt_ok &= (att[0]["messages"] == X.build_messages(texts[pid])) and (r["problem_text"] == texts[pid])
        out["valid_first_try"] += r["status"] == "valid_first_try"
        out["valid_after_retry"] += r["status"] == "valid_after_retry"
        out["invalid"] += r["status"] == "invalid"
        out["retries_used"] += len(att) == 2
        out["in_code_fence"] += any(a["fenced"] for a in att)
        out["truncated"] += any(a["reply"].get("finish_reason") == "length" for a in att)
        tokens.append(sum(a["reply"].get("completion_tokens") or 0 for a in att))
        secs.append(r["wall_seconds"])
        gflat = flatten(gold[pid])
        cflat = flatten(r["case"]) if r["case"] else None
        bad = [k for k in gflat if cflat is None or not same(cflat.get(k), gflat[k])]
        out["leaves_total"] += len(gflat)
        out["leaves_correct"] += len(gflat) - len(bad)
        exact = cflat is not None and not bad
        out["exact_match"] += exact
        wrong_fields += [(pid, r["repeat"], k, None if cflat is None else cflat.get(k), gflat[k]) for k in bad]
        const = {"design_method", "material.grade", "material.Fy_ksi", "material.Fu_ksi", "material.E_ksi"}
        for k in gflat:
            if k in const:
                continue
            w, v = gflat[k], (cflat or {}).get(k)
            pw, pv = w not in (None, ()), v not in (None, ())
            ok = pw and pv and same(v, w)
            out["tp"] += bool(ok)
            out["fp"] += bool(pv and not ok)
            out["fn"] += bool(pw and not ok)
        rt = r["route"]
        if r["case"]:
            re_rt = route(DesignCase.model_validate(r["case"]))
            route_repro &= json.dumps(re_rt, sort_keys=True, default=str) == json.dumps(rt, sort_keys=True, default=str)
        flags = [f["code"] for f in (rt or {}).get("flags", [])]
        out["section_flagged_nonexistent"] += "section_not_in_database" in flags
        status = (rt or {}).get("status")
        out["would_ask_user"] += status == "would_ask_user"
        out["flagged_not_computed"] += status == "flagged_not_computed"
        correct = unsafe = answered = False
        if pid in strength:
            out["strength_runs"] += 1
            pub = strength[pid]["published"]["value"]
            if status == "computed" and rt["answer"] is not None:
                answered = True
                e = 100 * (rt["answer"] - pub) / pub
                max_err = max(max_err, abs(e))
                correct, unsafe = abs(e) <= 1.0, e > 1.0
                out["strength_within_1pct"] += correct
                out["strength_overstated_gt_1pct"] += e > 1.0
        else:
            out["selection_runs"] += 1
            pub = selection[pid]["published"]["section"]
            if status == "computed" and rt["section"]:
                answered = True
                exists, passes = sec_check(rt["section"], selection[pid])
                correct, unsafe = rt["section"] == pub, exists and not passes
                out["selection_exact"] += correct
        out["unsafe_total"] += unsafe
        out["no_answer"] += not answered
        if not correct:
            # solver error: System A applied directly to the Dataset C parameters misses the published value; routing error: route(gold) differs
            # from that direct call; otherwise extraction error when the extracted case differs from gold
            if pid in strength:
                d_ok = abs(direct_value(strength[pid]) - pub) / pub <= 0.01
                rg = route(DesignCase.model_validate(gold[pid]))["answer"]
                r_ok = abs(rg - direct_value(strength[pid])) <= 1e-9 * max(1, rg)
            else:
                rg = route(DesignCase.model_validate(gold[pid]))["section"]
                d_ok, r_ok = rg == pub, True
            cls = "err_solver" if not d_ok else "err_routing" if not r_ok else "err_extraction" if not exact else "err_unexplained"
            out[cls] += 1
            errs.append((pid, r["repeat"], "answered" if answered else "no answer", cls))
    P = out["tp"] / max(out["tp"] + out["fp"], 1)
    R = out["tp"] / max(out["tp"] + out["fn"], 1)
    out.update(precision=round(P, 4), recall=round(R, 4), f1=round(2 * P * R / (P + R), 4) if P + R else 0.0,
               field_accuracy=round(out["leaves_correct"] / out["leaves_total"], 5), strength_max_abs_err_pct=max_err,
               strength_max_abs_err_pct_3dp=round(max_err, 3), mean_completion_tokens=sum(tokens) / len(tokens), mean_completion_tokens_0dp=round(sum(tokens) / len(tokens)),
               max_completion_tokens=max(tokens), mean_wall_seconds=sum(secs) / len(secs), mean_wall_seconds_1dp=round(sum(secs) / len(secs), 1),
               prompt_in_raw_equals_current_frozen_prompt=prompt_ok, stored_route_equals_rerouting_stored_case=route_repro)
    return out, errs, wrong_fields, recs


def recompute_system_c(model, strength, selection):
    d = sorted(glob.glob(str(ROOT / "results" / f"system_c_pilot_voyager_{model}_cap4000_*")))[-1]
    prompts = {p["id"]: p for p in S.build_prompts()}
    o = {"dir": Path(d).name, "runs": 0, "strength_runs": 0, "within_1pct": 0, "no_answer": 0, "overestimate_gt_1pct": 0, "selection_runs": 0, "sel_exact": 0,
         "sel_no_answer": 0, "sel_unsafe": 0, "sel_not_in_db": 0, "truncated": 0}
    toks = []
    for f in sorted((Path(d) / "raw").glob("*.json")):
        r = json.loads(f.read_text(encoding="utf-8"))
        o["runs"] += 1
        o["truncated"] += r["done_reason"] == "length"
        toks.append(r["eval_count"])
        if r["kind"] == "strength":
            o["strength_runs"] += 1
            v, _ = S.parse_final_number(r["response"])
            pub = prompts[r["id"]]["expected"]["value"]
            if v is None:
                o["no_answer"] += 1
            else:
                e = 100 * (v - pub) / pub
                o["within_1pct"] += abs(e) <= 1.0
                o["overestimate_gt_1pct"] += e > 1.0
        else:
            o["selection_runs"] += 1
            lab = S.parse_final_section(r["response"])
            if lab is None:
                o["sel_no_answer"] += 1
                continue
            o["sel_exact"] += lab == selection[r["id"]]["published"]["section"]
            exists, passes = sec_check(lab, selection[r["id"]])
            o["sel_not_in_db"] += not exists
            o["sel_unsafe"] += exists and not passes
    o["mean_tokens_0dp"] = round(sum(toks) / len(toks))
    return o


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--aborted-dir", default=None)
    a = ap.parse_args()
    run_dir = Path(a.run_dir)
    strength, selection, gold = load_dc()
    texts = problem_texts()
    res, lines, mismatches = {}, [], []
    for i, m in enumerate(MODELS):
        out, errs, wf, recs = recompute_model(run_dir, m, strength, selection, gold, texts)
        summ = json.loads((run_dir / m / "summary.json").read_text(encoding="utf-8"))
        scorer_pairs = {"valid_first_try": summ["validity"]["valid_first_try"], "valid_after_retry": summ["validity"]["valid_after_retry"], "invalid": summ["validity"]["invalid"],
                        "exact_match": summ["extraction"]["exact_match_runs"], "strength_within_1pct": summ["strength"]["within_1pct"], "selection_exact": summ["selection"]["exact_match"],
                        "unsafe_total": summ["unsafe_total"], "would_ask_user": summ["extraction"]["route_status_counts"].get("would_ask_user", 0),
                        "tp": summ["extraction"]["field_tp_fp_fn_all"][0], "fp": summ["extraction"]["field_tp_fp_fn_all"][1], "fn": summ["extraction"]["field_tp_fp_fn_all"][2]}
        lines.append(f"== {m}: independent recompute vs scorer summary.json vs SESSION_SUMMARY claims")
        for k, v in out.items():
            if k in CLAIMS:
                ok = v == CLAIMS[k][i]
                lines.append(f"  claim  {k:32} recomputed={v!s:>8} claimed={CLAIMS[k][i]!s:>8} {'MATCH' if ok else 'MISMATCH'}")
                if not ok:
                    mismatches.append((m, k, v, CLAIMS[k][i]))
        for k, v in scorer_pairs.items():
            ok = out[k] == v
            lines.append(f"  scorer {k:32} recomputed={out[k]!s:>8} summary.json={v!s:>8} {'MATCH' if ok else 'MISMATCH'}")
            if not ok:
                mismatches.append((m, "scorer:" + k, out[k], v))
        for k in ("precision", "recall", "f1", "field_accuracy", "strength_overstated_gt_1pct", "flagged_not_computed", "no_answer", "err_unexplained", "strength_max_abs_err_pct",
                  "prompt_in_raw_equals_current_frozen_prompt", "stored_route_equals_rerouting_stored_case"):
            lines.append(f"  info   {k:32} {out[k]}")
        lines.append(f"  every wrong or missing field ({len(wf)}): {wf}")
        lines.append(f"  runs that are not correct: {errs}")
        if a.aborted_dir:
            same_n = sum(json.loads(f.read_text(encoding='utf-8'))["case"] == json.loads((Path(a.aborted_dir) / m / "raw" / f.name).read_text(encoding="utf-8"))["case"]
                         for f in (run_dir / m / "raw").glob("*.json"))
            lines.append(f"  extracted case identical to the aborted run: {same_n} of {out['runs']}")
            out["identical_to_aborted_run"] = same_n
        res[m] = {**out, "wrong_fields": wf, "not_correct": errs}
    sc = {m: recompute_system_c(m, strength, selection) for m in MODELS}
    for i, m in enumerate(MODELS):
        csum = json.loads((Path(ROOT / "results" / sc[m]["dir"]) / "summary.json").read_text(encoding="utf-8"))
        pairs = {"within_1pct": csum["strength"]["within_1pct"], "no_answer": csum["strength"]["no_final_answer"], "overestimate_gt_1pct": csum["strength"]["overestimate_gt_1pct"],
                 "sel_exact": csum["selection"]["exact_match_published"], "sel_no_answer": csum["selection"]["no_final_answer"], "sel_unsafe": csum["selection"]["unsafe_recommendation"],
                 "sel_not_in_db": csum["selection"]["hallucinated_section"], "truncated": csum["truncated_outputs"]}
        lines.append(f"== System C @ 4,000 tokens, {m} ({sc[m]['dir']})")
        for k, v in sc[m].items():
            if k in SYSTEM_C_CLAIMS:
                ok = v == SYSTEM_C_CLAIMS[k][i]
                lines.append(f"  claim  {k:22} recomputed={v!s:>6} claimed={SYSTEM_C_CLAIMS[k][i]!s:>6} {'MATCH' if ok else 'MISMATCH'}")
                if not ok:
                    mismatches.append(("systemC-" + m, k, v, SYSTEM_C_CLAIMS[k][i]))
        for k, v in pairs.items():
            ok = sc[m][k] == v
            lines.append(f"  scorer {k:22} recomputed={sc[m][k]!s:>6} summary.json={v!s:>6} {'MATCH' if ok else 'MISMATCH'}")
            if not ok:
                mismatches.append(("systemC-scorer-" + m, k, sc[m][k], v))
    # gold control
    gc = json.loads((run_dir / "gold_control.json").read_text(encoding="utf-8"))
    mx = max(abs(v["direct_err_pct"]) for v in gc.values() if v["kind"] == "strength")
    lines.append(f"== gold control: max |direct System A error vs AISC| over the 9 strength problems = {mx:.4f}% (as 3 decimals: {mx:.3f}); selections route_ok = "
                 f"{sum(v['route_ok'] for v in gc.values() if v['kind'] == 'selection')} of 4; all 13 direct_ok/route_ok/route==direct: "
                 f"{all(v['direct_ok'] and v['route_ok'] and v['route_equals_direct'] for v in gc.values())}")
    lines.append(f"== MISMATCHES: {len(mismatches)} {mismatches}")
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    od = ROOT / "results" / f"first_slice_verification_{stamp}"
    od.mkdir(parents=True)
    (od / "verification.json").write_text(json.dumps({"run_dir": run_dir.name, "slice": res, "system_c_cap4000": sc, "gold_control_max_abs_err_pct": mx, "mismatches": mismatches}, indent=2, default=str), encoding="utf-8")
    (od / "verification.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print("saved to", od)


if __name__ == "__main__":
    main()
