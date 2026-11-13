"""First agent slice (System D steps Parse + Calculate): LLM extraction -> Pydantic validation -> deterministic routing -> compare with AISC.

Same 13 Dataset C problem texts as the System C pilot (eval/system_c_pilot.py builds them; that file is imported, never modified).
The LLM only fills a DesignCase JSON; every number in a final answer comes from steelagent/ via agent/route.py.

SCORING DEFINITIONS (frozen before any model call; see SCORING_SPEC below and the sha256 recorded in meta.json):
  gold            datasets/C_benchmark/gold_design_cases.json
  field match     numbers: relative difference <= 0.5 % (gold 0 -> must be exactly 0); strings equal; lists (requested_limit_states,
                  missing_fields) compared as sets. 22 leaf fields per case (see LEAVES). problem_id is set by the harness and not scored.
  exact match     a valid DesignCase whose 22 leaf fields all match gold.
  field accuracy  matching leaves / 22, over valid extractions and over all runs (an invalid extraction counts as 0 of 22).
  field P/R/F1    micro-averaged over non-null gold/predicted leaves, constant leaves (design_method, material.*) excluded;
                  an invalid extraction contributes no predictions.
  strength        final answer = route() capacity; correct if within 1 % of the published AISC value; UNSAFE if it exceeds the published value by > 1 %.
  selection       correct if the section equals the published section; UNSAFE if the recommended section exists and fails any System A check
                  evaluated on the TRUE Dataset C case (never on the extracted one).
  no answer       invalid extraction after one retry, a domain flag, "would ask the user", or no passing section. Not unsafe; not correct.
  error trace     for each run that is not correct: SOLVER error if System A applied directly to the Dataset C parameters misses the published value;
                  ROUTING error if route(gold case) differs from that direct call; otherwise EXTRACTION error (the extracted case differs from gold);
                  "unexplained" if none of these (extraction exact match yet wrong).
Usage (repo root):
  .venv/Scripts/python.exe eval/first_slice_eval.py run   --model gemma4-31b-it --repeats 3 --run-dir results/first_slice_<ts>
  .venv/Scripts/python.exe eval/first_slice_eval.py score --run-dir results/first_slice_<ts>
"""
import argparse
import datetime
import glob
import hashlib
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "steelagent"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import system_c_pilot as S  # noqa: E402  (prompts, Voyager client, System A re-check; not modified)
from agent import extract as X  # noqa: E402
from agent.design_case import DesignCase  # noqa: E402
from agent.route import route  # noqa: E402
from make_gold_design_cases import problem_texts  # noqa: E402

C_DIR = ROOT / "datasets" / "C_benchmark"
SEED, MAX_TOKENS, TEMPERATURE = 573, 1000, 0
NUM_TOL = 0.005
SCORING_SPEC = __doc__

LEAVES = ["member_type", "task", "section", "design_method", "requested_limit_states",
          "material.grade", "material.Fy_ksi", "material.Fu_ksi", "material.E_ksi",
          "demands.Pu_kip", "demands.Mu_kipft", "demands.Vu_kip",
          "geometry.Lcx_ft", "geometry.Lcy_ft", "geometry.Lb_ft", "geometry.Cb",
          "net_section.An_in2", "net_section.U",
          "constraints.nominal_depth_in", "constraints.max_depth_in", "constraints.Ix_min_in4", "missing_fields"]
CONSTANT_LEAVES = {"design_method", "material.grade", "material.Fy_ksi", "material.Fu_ksi", "material.E_ksi"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def leaf(d, path):
    cur = d
    for p in path.split("."):
        cur = cur[p]
    return cur


def leaf_match(path, got, want):
    if isinstance(want, list) or isinstance(got, list):
        return set(got or []) == set(want or [])
    if want is None or got is None:
        return want is None and got is None
    if isinstance(want, (int, float)) and not isinstance(want, bool):
        if want == 0:
            return got == 0
        return abs(got - want) / abs(want) <= NUM_TOL
    return got == want


def is_present(v):
    return v is not None and v != []


def compare_cases(got, gold):
    """got: dict (model_dump of a valid DesignCase) or None; gold: dict. Returns (per-leaf results, errors list)."""
    res, errs = {}, []
    for p in LEAVES:
        w = leaf(gold, p)
        g = leaf(got, p) if got is not None else None
        ok = got is not None and leaf_match(p, g, w)
        res[p] = ok
        if not ok:
            errs.append({"field": p, "got": ("(no valid DesignCase)" if got is None else g), "expected": w,
                         "kind": ("invalid_extraction" if got is None else "missing" if (g is None or g == []) and is_present(w)
                                  else "spurious" if is_present(g) and not is_present(w) else "wrong_value")})
    return res, errs


# ---------------------------------------------------------------- gold + controls
def load_gold():
    return {c["problem_id"]: c for c in json.loads((C_DIR / "gold_design_cases.json").read_text(encoding="utf-8"))["cases"]}


def dataset_c():
    strength = {c["id"]: c for c in json.loads((C_DIR / "design_examples_strength.json").read_text(encoding="utf-8"))["cases"]}
    selection = {c["id"]: c for c in json.loads((C_DIR / "design_examples_selection.json").read_text(encoding="utf-8"))["cases"]}
    return strength, selection


def direct_system_a(case_id, strength, selection):
    """System A applied directly to the Dataset C parameters (no DesignCase, no route): the validated path of steelagent/tests/test_dataset_c.py."""
    from steelagent import shapes
    from steelagent.compression import compression_strength
    from steelagent.flexure import flexure_strength, shear_strength
    from steelagent.search import lightest
    from steelagent.tension import tension_strength
    if case_id in strength:
        c = strength[case_id]
        s, i = shapes.get(c["shape"]), c["inputs"]
        return {"tension_yield": lambda: tension_strength(s)["phiPn_yield"],
                "tension_rupture": lambda: tension_strength(s, An=i["An_in2"], U=i["U"])["phiPn_rupture"],
                "compression": lambda: compression_strength(s, i["Lcx_ft"], i["Lcy_ft"])["phiPn"],
                "flexure": lambda: flexure_strength(s, i["Lb_ft"], i["Cb"])["phiMn"],
                "shear": lambda: shear_strength(s)["phiVn"]}[c["check"]]()
    c = selection[case_id]
    d, g, k = c["demands"], c["geometry"], c["constraints"]
    if c["member_type"] == "compression":
        return lightest("compression", {"Pu": d["Pu_kip"]}, g, depth=k.get("nominal_depth_in"))["section"]
    depths = [None] if "max_depth_in" not in k else [x for x in (18, 16, 14, 12, 10, 8, 6, 5, 4) if x <= k["max_depth_in"]]
    best = None
    for depth in depths:
        r = lightest("flexure", {"Mu": d["Mu_kipft"]}, g, depth=depth, Ix_min=k.get("Ix_min_in4"))
        if r["section"] and (best is None or shapes.get(r["section"])["W"] < shapes.get(best)["W"]):
            best = r["section"]
    return best


def gold_control():
    """route(gold case) vs published AISC answer and vs the direct System A call, for all 13 problems. No model involved."""
    strength, selection = dataset_c()
    out = {}
    for pid, g in load_gold().items():
        r = route(DesignCase.model_validate(g["design_case"]))
        direct = direct_system_a(pid, strength, selection)
        if pid in strength:
            pub = strength[pid]["published"]["value"]
            out[pid] = {"kind": "strength", "published": pub, "direct_system_a": direct, "route_gold": r["answer"], "route_status": r["status"],
                        "direct_err_pct": 100 * (direct - pub) / pub, "route_err_pct": 100 * (r["answer"] - pub) / pub,
                        "direct_ok": abs(direct - pub) / pub <= 0.01, "route_ok": abs(r["answer"] - pub) / pub <= 0.01,
                        "route_equals_direct": abs(r["answer"] - direct) <= 1e-9 * max(1, abs(direct))}
        else:
            pub = selection[pid]["published"]["section"]
            out[pid] = {"kind": "selection", "published": pub, "direct_system_a": direct, "route_gold": r["section"], "route_status": r["status"],
                        "direct_ok": direct == pub, "route_ok": r["section"] == pub, "route_equals_direct": r["section"] == direct}
    return out


# ---------------------------------------------------------------- running
def make_ask(model):
    env = S._load_env()
    base, key = env["VOYAGER_BASE_URL"], env["VOYAGER_API_KEY"]
    ids = {m["id"] for m in json.load(urllib.request.urlopen(
        urllib.request.Request(base.rstrip("/") + "/models", headers={"Authorization": f"Bearer {key}"}), timeout=30))["data"]}
    if model not in ids:
        sys.exit(f"model {model} not served by Voyager")
    extra = S.VOYAGER_THINKING_OFF.get(model, {})
    opts = {"temperature": TEMPERATURE, "seed": SEED, "max_tokens": MAX_TOKENS}

    def ask(messages):
        t0 = time.time()
        d = S._voyager_post(base, key, {"model": model, "messages": messages, **opts, **extra})
        ch, m, u = d["choices"][0], d["choices"][0]["message"], d.get("usage") or {}
        return {"response": m.get("content") or "", "reasoning": m.get("reasoning_content") or m.get("reasoning"), "finish_reason": ch.get("finish_reason"),
                "completion_tokens": u.get("completion_tokens"), "prompt_tokens": u.get("prompt_tokens"), "seconds": round(time.time() - t0, 2)}
    meta = {"backend": "voyager", "endpoint_host": urlparse(base).netloc, "extra_request_fields": extra, "options": opts,
            "thinking_request": ("chat_template_kwargs.enable_thinking=false sent" if extra else "no flag sent (model default)")}
    return ask, meta


def run(args):
    run_dir = Path(args.run_dir)
    ctrl = gold_control()
    bad = {k: v for k, v in ctrl.items() if not (v["direct_ok"] and v["route_ok"] and v["route_equals_direct"])}
    if bad:
        sys.exit(f"gold control failed (bug in schema/routing/solver); not calling any model: {json.dumps(bad, indent=1, default=str)}")
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "gold_control.json").write_text(json.dumps(ctrl, indent=2, default=str), encoding="utf-8")
    texts = problem_texts()
    ask, meta_extra = make_ask(args.model)
    mdir = run_dir / args.model
    (mdir / "raw").mkdir(parents=True, exist_ok=True)
    git = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip() or None
    dirty = bool(subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"], capture_output=True, text=True).stdout.strip())
    meta = {"timestamp_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ"), "git_hash": git, "git_tree_dirty": dirty,
            "model": args.model, "repeats": args.repeats, "n_problems": len(texts), "prompt_version": X.PROMPT_VERSION, "prompt_sha256": X.PROMPT_SHA256,
            "scorer_sha256": sha(__file__), "design_case_sha256": sha(ROOT / "agent" / "design_case.py"), "extract_sha256": sha(ROOT / "agent" / "extract.py"),
            "route_sha256": sha(ROOT / "agent" / "route.py"), "gold_sha256": sha(C_DIR / "gold_design_cases.json"), "max_retries": 1,
            "tools": None, "retrieval": None, **meta_extra}
    (mdir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    t_all = time.time()
    for r in range(1, args.repeats + 1):
        for pid, text in texts.items():
            f = mdir / "raw" / f"{pid}_r{r}.json"
            if f.exists():
                continue
            t = time.time()
            res = X.extract(text, pid, ask)
            case = res["case"]
            rt = route(case) if case is not None else None
            rec = {"id": pid, "repeat": r, "model": args.model, "problem_text": text, "status": res["status"],
                   "case": case.model_dump(mode="json") if case else None, "route": rt, "attempts": res["attempts"],
                   "wall_seconds": round(time.time() - t, 1), "finished_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
            f.write_text(json.dumps(rec, indent=2, default=str), encoding="utf-8")
            print(f"[{args.model} r{r}] {pid:12} {res['status']:18} route={(rt or {}).get('status')} {rec['wall_seconds']:5.1f}s", flush=True)
    print(f"{args.model}: finished in {(time.time() - t_all) / 60:.1f} min -> {mdir}")


# ---------------------------------------------------------------- scoring
def score_run(rec, gold, strength, selection, ctrl):
    pid = rec["id"]
    g = gold[pid]["design_case"]
    got = rec["case"]
    res, errs = compare_cases(got, g)
    rt = rec["route"]
    row = {"id": pid, "repeat": rec["repeat"], "extraction_status": rec["status"], "retry_used": len(rec["attempts"]) == 2,
           "fenced": any(a["fenced"] for a in rec["attempts"]), "truncated": any((a["reply"].get("finish_reason") == "length") for a in rec["attempts"]),
           "completion_tokens": sum((a["reply"].get("completion_tokens") or 0) for a in rec["attempts"]),
           "n_leaves_correct": sum(res.values()), "n_leaves": len(LEAVES), "exact_match": got is not None and all(res.values()),
           "n_wrong_fields": len(errs), "wrong_fields": "; ".join(f"{e['field']}: got {e['got']!r} expected {e['expected']!r}" for e in errs),
           "first_attempt_error": next((a["error"] for a in rec["attempts"] if not a["valid"]), None),
           "flag_codes": ",".join(f["code"] for f in (rt or {}).get("flags", [])), "section_flagged_nonexistent": any(f["code"] == "section_not_in_database" for f in (rt or {}).get("flags", [])),
           "route_status": (rt or {}).get("status", "no_valid_case"), "missing": ",".join((rt or {}).get("missing", []))}
    tp = fp = fn = 0
    for p in LEAVES:
        if p in CONSTANT_LEAVES:
            continue
        w, v = leaf(g, p), (leaf(got, p) if got is not None else None)
        tp += is_present(w) and is_present(v) and res[p]
        fp += is_present(v) and not (is_present(w) and res[p])
        fn += is_present(w) and not (is_present(v) and res[p])
    row.update(tp=int(tp), fp=int(fp), fn=int(fn))
    answered, correct, unsafe = False, False, False
    if pid in strength:
        pub = strength[pid]["published"]["value"]
        row.update(kind="strength", published=pub)
        if rt and rt["status"] == "computed" and rt["answer"] is not None:
            answered = True
            err = 100 * (rt["answer"] - pub) / pub
            row.update(final=rt["answer"], err_pct=err)
            correct, unsafe = abs(err) <= 1.0, err > 1.0
    else:
        pub = selection[pid]["published"]["section"]
        row.update(kind="selection", published=pub)
        if rt and rt["status"] == "computed" and rt["section"]:
            answered = True
            chk = S._system_a_check(rt["section"], selection[pid])
            row.update(final=rt["section"], system_a_pass=chk["passes"], system_a_reasons="; ".join(chk["reasons"]))
            correct, unsafe = rt["section"] == pub, chk["exists"] and not chk["passes"]
    row.update(answered=answered, correct=correct, unsafe=unsafe)
    cause = None
    if not correct:
        c = ctrl[pid]
        if not c["direct_ok"]:
            cause = "solver error"
        elif not c["route_equals_direct"] or not c["route_ok"]:
            cause = "routing error"
        elif not row["exact_match"]:
            cause = "extraction error"
        else:
            cause = "unexplained"
    row["error_class"] = cause
    row["outcome"] = "correct" if correct else ("wrong answer" if answered else "no answer")
    return row


def summarize_model(df, model_dir, ctrl):
    import pandas as pd  # noqa: F401
    st, se = df[df.kind == "strength"], df[df.kind == "selection"]
    valid = df[df.extraction_status != "invalid"]
    tp, fp, fn = int(df.tp.sum()), int(df.fp.sum()), int(df.fn.sum())
    P, R = tp / max(tp + fp, 1), tp / max(tp + fn, 1)
    pv_tp, pv_fp, pv_fn = int(valid.tp.sum()), int(valid.fp.sum()), int(valid.fn.sum())
    return {
        "runs": int(len(df)), "problems": int(df.id.nunique()), "repeats": int(df.repeat.nunique()),
        "validity": {"valid_first_try": int((df.extraction_status == "valid_first_try").sum()), "valid_after_retry": int((df.extraction_status == "valid_after_retry").sum()),
                     "invalid": int((df.extraction_status == "invalid").sum()), "responses_in_code_fence": int(df.fenced.sum()),
                     "truncated_responses": int(df.truncated.sum()), "section_flagged_not_in_database": int(df.section_flagged_nonexistent.sum()),
                     "runs_with_any_domain_flag": int((df["flag_codes"].fillna("") != "").sum())},
        "extraction": {"exact_match_runs": int(df.exact_match.sum()), "exact_match_of_valid": f"{int(valid.exact_match.sum())} of {len(valid)}",
                       "field_accuracy_all_runs": float(df.n_leaves_correct.sum() / df.n_leaves.sum()),
                       "field_accuracy_valid_runs": float(valid.n_leaves_correct.sum() / valid.n_leaves.sum()) if len(valid) else None,
                       "field_micro_precision_all": P, "field_micro_recall_all": R, "field_micro_f1_all": (2 * P * R / (P + R)) if P + R else 0.0,
                       "field_tp_fp_fn_all": [tp, fp, fn], "field_tp_fp_fn_valid_only": [pv_tp, pv_fp, pv_fn],
                       "runs_with_wrong_or_missing_field": int((df.n_wrong_fields > 0).sum()),
                       "route_status_counts": {k: int(v) for k, v in df.route_status.value_counts().items()}},
        "strength": {"runs": int(len(st)), "answered": int(st.answered.sum()), "no_answer": int((~st.answered).sum()), "within_1pct": int(st.correct.sum()),
                     "unsafe_overstated_gt_1pct": int(st.unsafe.sum()),
                     "max_abs_err_pct_answered": float(st[st.answered].err_pct.abs().max()) if st.answered.any() else None},
        "selection": {"runs": int(len(se)), "answered": int(se.answered.sum()), "no_answer": int((~se.answered).sum()), "exact_match": int(se.correct.sum()),
                      "unsafe_fails_system_a": int(se.unsafe.sum())},
        "final_correct_total": int(df.correct.sum()), "unsafe_total": int(df.unsafe.sum()),
        "error_trace_of_runs_not_correct": {k: int(v) for k, v in df[~df.correct].error_class.value_counts().items()},
        "error_trace_of_wrong_answers_only": {k: int(v) for k, v in df[df.outcome == "wrong answer"].error_class.value_counts().items()},
        "mean_completion_tokens": float(df.completion_tokens.mean()), "mean_wall_seconds": None,
    }


def system_c_vs_slice(model, summ):
    """Side-by-side rows: System C at the 4,000-token cap (same 27 strength + 12 selection runs) vs this slice."""
    dirs = sorted(glob.glob(str(ROOT / "results" / f"system_c_pilot_voyager_{model}_cap4000_*")))
    if not dirs:
        return None
    c = json.loads((Path(dirs[-1]) / "summary.json").read_text(encoding="utf-8"))
    cs, cl = c["strength"], c["selection"]
    s, l = summ["strength"], summ["selection"]
    return [
        ("Strength runs", f"{cs['runs']}", f"{s['runs']}"),
        ("Strength: within 1% of AISC", f"{cs['within_1pct']} of {cs['runs']}", f"{s['within_1pct']} of {s['runs']}"),
        ("Strength: no answer (no final number / abstained / invalid)", f"{cs['no_final_answer']} of {cs['runs']}", f"{s['no_answer']} of {s['runs']}"),
        ("Strength: overestimate > 1% (unsafe direction)", f"{cs['overestimate_gt_1pct']} of {cs['runs']}", f"{s['unsafe_overstated_gt_1pct']} of {s['runs']}"),
        ("Selection runs", f"{cl['runs']}", f"{l['runs']}"),
        ("Selection: exact match to AISC section", f"{cl['exact_match_published']} of {cl['runs']}", f"{l['exact_match']} of {l['runs']}"),
        ("Selection: no answer", f"{cl['no_final_answer']} of {cl['runs']}", f"{l['no_answer']} of {l['runs']}"),
        ("Selection: recommended section fails a System A check (unsafe)", f"{cl['unsafe_recommendation']} of {cl['runs']}", f"{l['unsafe_fails_system_a']} of {l['runs']}"),
        ("Selection: section not in AISC database (System C: proposed; slice: cannot occur, the search only returns database sections)", f"{cl['hallucinated_section']} of {cl['runs']}", "0 of %d (by construction)" % l["runs"]),
        ("Truncated outputs at the cap (System C 4,000 tokens; slice 1,000)", f"{c['truncated_outputs']} of {c['runs']}", f"{summ['validity']['truncated_responses']} of {summ['runs']}"),
        ("Mean output tokens per run", f"{c['mean_eval_tokens']:,.0f}", f"{summ['mean_completion_tokens']:,.0f}"),
    ], dirs[-1]


def score(args):
    import pandas as pd
    run_dir = Path(args.run_dir)
    gold = load_gold()
    strength, selection = dataset_c()
    ctrl = json.loads((run_dir / "gold_control.json").read_text(encoding="utf-8"))
    md = [f"# First agent slice: scores ({run_dir.name})", "", f"Scorer sha256 `{sha(__file__)[:12]}`, prompt `{X.PROMPT_VERSION}` sha256 `{X.PROMPT_SHA256[:12]}`.", ""]
    all_summ, all_rows = {}, {}
    for mdir in sorted(p for p in run_dir.iterdir() if p.is_dir() and (p / "raw").exists()):
        model = mdir.name
        rows = [score_run(json.loads(f.read_text(encoding="utf-8")), gold, strength, selection, ctrl) for f in sorted((mdir / "raw").glob("*.json"))]
        df = pd.DataFrame(rows)
        df.to_csv(mdir / "scores.csv", index=False)
        summ = summarize_model(df, mdir, ctrl)
        summ["mean_wall_seconds"] = float(sum(json.loads(f.read_text(encoding="utf-8"))["wall_seconds"] for f in (mdir / "raw").glob("*.json")) / len(rows))
        summ["scorer_sha256"] = sha(__file__)
        (mdir / "summary.json").write_text(json.dumps(summ, indent=2), encoding="utf-8")
        ferr = df[df.n_wrong_fields > 0][["id", "repeat", "extraction_status", "n_wrong_fields", "wrong_fields", "first_attempt_error"]]
        ferr.to_csv(mdir / "field_errors.csv", index=False)
        df[~df.correct].reindex(columns=["id", "repeat", "kind", "outcome", "published", "final", "err_pct", "error_class", "route_status", "missing", "flag_codes", "wrong_fields"]).to_csv(mdir / "error_trace.csv", index=False)
        all_summ[model], all_rows[model] = summ, df
        md += [f"## {model}", "", "```json", json.dumps(summ, indent=2), "```", ""]
        md += ["### Every run with a wrong or missing field", ""]
        md += [f"- **{r.id} r{r.repeat}** ({r.extraction_status}): {r.wrong_fields or r.first_attempt_error}" for r in ferr.itertuples()] or ["- none"]
        md += ["", "### Runs that are not correct (error trace)", ""]
        md += [f"- **{r.id} r{r.repeat}**: {r.outcome}, {r.error_class}; final={getattr(r, 'final', None)!r} published={r.published!r}" for r in df[~df.correct].itertuples()] or ["- none"]
        md += [""]
        sc = system_c_vs_slice(model, summ)
        if sc:
            rows_, d = sc
            md += [f"### System C (cap 4,000, `{Path(d).name}`) vs this slice, {model}", "", "| Metric | System C @ 4,000 | Slice (extract + route) |", "|---|---|---|"]
            md += [f"| {a} | {b} | {c_} |" for a, b, c_ in rows_] + [""]
    (run_dir / "SCORES.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--model", required=True)
    r.add_argument("--repeats", type=int, default=3)
    r.add_argument("--run-dir", required=True)
    s = sub.add_parser("score")
    s.add_argument("--run-dir", required=True)
    a = ap.parse_args()
    {"run": run, "score": score}[a.cmd](a)
