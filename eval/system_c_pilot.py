"""System C pilot: an open-weight LLM answers the 13 Dataset C (AISC Design Examples) problems end to end.

No tools, no retrieval, no section-property tables: the model must work from memory (CLAUDE.md section 8, backlog task 5).
Prompts are templated from datasets/C_benchmark/*.json (problem parameters restated in our own words). Every raw response is saved.
Scoring: strength checks vs the published AISC value; selections vs the published section AND re-checked by System A
(a section that does not exist, or that fails a required check, counts as a hallucination / unsafe recommendation).
Dataset C is never used for training.

Backends: local Ollama, or ASU Voyager (OpenAI-compatible; VOYAGER_BASE_URL / VOYAGER_API_KEY read from the gitignored .env, never printed).
Identical prompts, parsing and scoring for every backend; each model gets its own run directory with its raw outputs.

Usage (repo root):
  .venv/Scripts/python.exe eval/system_c_pilot.py run   --backend ollama  --model qwen3.5:9b --repeats 3     # Ollama server running
  .venv/Scripts/python.exe eval/system_c_pilot.py run   --backend voyager --model qwen38-27b --repeats 3
  .venv/Scripts/python.exe eval/system_c_pilot.py score --run-dir results/system_c_pilot_<...>
  .venv/Scripts/python.exe eval/system_c_pilot.py compare --run local=<dir> qwen38-27b=<dir> gemma4-31b-it=<dir>
"""
import argparse, datetime, json, re, statistics, subprocess, sys, time, urllib.error, urllib.request
from urllib.parse import urlparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "steelagent"))
C_DIR = ROOT / "datasets" / "C_benchmark"
OLLAMA = "http://localhost:11434"
SEED, NUM_CTX, NUM_PREDICT = 573, 4096, 1500

HEADER = ("You are a structural engineer. Use ANSI/AISC 360-22, LRFD, ASTM A992 steel (Fy = 50 ksi, Fu = 65 ksi, "
          "E = 29,000 ksi), U.S. customary units. You have no tables or software; work from your own knowledge.\n\n")
TAIL_NUM = ("\n\nShow brief working, then end with one final line exactly of the form:\nFINAL ANSWER: <number> <unit>")
TAIL_SEC = ("\n\nShow brief working, then end with one final line exactly of the form:\nFINAL ANSWER: W<depth>X<weight>")

QUANTITY = {  # check -> (what to ask for, unit)
    "tension_yield": ("the LRFD design tensile strength for yielding on the gross section, phi_t*Pn", "kips"),
    "tension_rupture": ("the LRFD design tensile strength for rupture on the effective net area, phi_t*Pn", "kips"),
    "compression": ("the LRFD design compressive strength, phi_c*Pn", "kips"),
    "flexure": ("the LRFD design flexural strength about the major axis, phi_b*Mn", "kip-ft"),
    "shear": ("the LRFD design shear strength of the web, phi_v*Vn", "kips"),
}


def _num(x):
    return f"{x:.3f}".rstrip("0").rstrip(".")


def build_prompts():
    """Return list of dicts {id, kind, prompt, expected}. Deterministic."""
    out = []
    s = json.loads((C_DIR / "design_examples_strength.json").read_text(encoding="utf-8"))
    for c in s["cases"]:
        what, unit = QUANTITY[c["check"]]
        i, shp = c["inputs"], c["shape"].replace("X", "x")
        # Built from structured fields on purpose: the Dataset C descriptions name the governing limit state, which would leak it.
        if c["check"] == "tension_yield":
            text = f"A {shp} rolled W-shape is used as a tension member."
        elif c["check"] == "tension_rupture":
            text = (f"A {shp} rolled W-shape is used as a tension member. Net area An = {_num(i['An_in2'])} in^2 and "
                    f"shear lag factor U = {_num(i['U'])}.")
        elif c["check"] == "compression":
            text = (f"A {shp} rolled W-shape is used as a column. Effective length about the x axis = {_num(i['Lcx_ft'])} ft; "
                    f"about the y axis = {_num(i['Lcy_ft'])} ft.")
        elif c["check"] == "flexure":
            lat = ("The beam is continuously braced laterally (Lb = 0)." if i["Lb_ft"] == 0
                   else f"Unbraced length Lb = {_num(i['Lb_ft'])} ft.")
            text = f"A {shp} rolled W-shape is used as a beam bent about its major axis. {lat} Cb = {_num(i['Cb'])}."
        else:
            text = f"A {shp} rolled W-shape is used as a beam."
        text = f"Problem: {text} What is {what}, in {unit}?"
        out.append({"id": c["id"], "kind": "strength", "prompt": HEADER + text + TAIL_NUM,
                    "expected": {"value": c["published"]["value"], "unit": c["published"]["unit"], "check": c["check"]}})
    sel = json.loads((C_DIR / "design_examples_selection.json").read_text(encoding="utf-8"))
    for c in sel["cases"]:
        text = f"Problem: {c['description']}. Select the lightest W-shape that satisfies every required strength check."
        out.append({"id": c["id"], "kind": "selection", "prompt": HEADER + text + TAIL_SEC,
                    "expected": {"section": c["published"]["section"], "case": c}})
    return out


# ---------------------------------------------------------------- parsing
_NUM = r"[-+]?\d[\d,]*\.?\d*"


def parse_final_number(text):
    """Last 'FINAL ANSWER: <number> <unit>' line. Returns (value, unit) or (None, None)."""
    m = re.findall(rf"FINAL ANSWER:\s*\**\s*({_NUM})\s*([A-Za-z][A-Za-z\-\. ]*)?", text or "", flags=re.I)
    if not m:
        return None, None
    v, u = m[-1]
    return float(v.replace(",", "")), (u or "").strip().lower().rstrip(".")


def parse_final_section(text):
    """Last 'FINAL ANSWER:' line containing a W-shape. Returns normalized label like W14X132 or None."""
    lines = [l for l in (text or "").splitlines() if re.search(r"FINAL ANSWER", l, re.I)]
    for l in reversed(lines):
        m = re.search(r"W\s*(\d+)\s*[xX×]\s*(\d+)", l)
        if m:
            return f"W{m.group(1)}X{m.group(2)}"
    return None


FORCE_UNITS = {"", "kip", "kips", "k"}
MOMENT_UNITS = {"", "kip-ft", "kip-feet", "kip-foot", "k-ft", "kips-ft", "kip ft", "kip-ft."}


def unit_ok(unit, expected_unit):
    return (unit in FORCE_UNITS) if expected_unit == "kip" else (unit in MOMENT_UNITS)


# ---------------------------------------------------------------- running
def _post(path, body, timeout=1800):
    req = urllib.request.Request(OLLAMA + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def _load_env(path=ROOT / ".env"):
    env = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


# Thinking is switched off where the API allows it, to match the local run (Ollama think=false). Verified by probe on 2026-11-12:
# qwen38-27b thinks by default (empty answer at 1500 tokens); gemma4-31b-it returns no reasoning with or without the flag, so no flag is sent.
VOYAGER_THINKING_OFF = {"qwen38-27b": {"chat_template_kwargs": {"enable_thinking": False}}}


def _voyager_post(base, key, body, retries=6):
    """POST /chat/completions with retry on 429/5xx. Error text never includes the key."""
    req = urllib.request.Request(base.rstrip("/") + "/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    for attempt in range(retries):
        try:
            return json.load(urllib.request.urlopen(req, timeout=900))
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(2 ** attempt * 2)
                continue
            raise RuntimeError(f"HTTP {e.code}: {e.read()[:300].decode('utf-8', 'replace')}") from None
        except urllib.error.URLError as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt * 2)
                continue
            raise RuntimeError(f"network error: {e.reason}") from None


def run(args):
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    prompts = build_prompts()
    git = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip() or None
    if args.backend == "ollama":
        ver = json.load(urllib.request.urlopen(OLLAMA + "/api/version", timeout=5))["version"]
        tags = {m["name"]: m for m in json.load(urllib.request.urlopen(OLLAMA + "/api/tags", timeout=5))["models"]}
        if args.model not in tags:
            sys.exit(f"model {args.model} not installed; have {list(tags)}")
        opts = {"temperature": 0, "seed": SEED, "num_ctx": NUM_CTX, "num_predict": NUM_PREDICT}
        meta_extra = {"backend": "ollama", "ollama_version": ver, "model_digest": tags[args.model]["digest"], "think": False,
                      "thinking_request": "think=false sent to Ollama"}
        default_dir = f"system_c_pilot_{stamp}"

        def ask(prompt):
            resp = _post("/api/chat", {"model": args.model, "stream": False, "think": False,
                                       "messages": [{"role": "user", "content": prompt}], "options": opts})
            return {"response": resp["message"]["content"], "thinking": resp["message"].get("thinking"), "done_reason": resp.get("done_reason"),
                    "eval_count": resp.get("eval_count"), "eval_seconds": resp.get("eval_duration", 0) / 1e9,
                    "prompt_eval_count": resp.get("prompt_eval_count"), "usage": None}
    else:
        env = _load_env()
        base, key = env["VOYAGER_BASE_URL"], env["VOYAGER_API_KEY"]
        listing = json.load(urllib.request.urlopen(urllib.request.Request(base.rstrip("/") + "/models", headers={"Authorization": f"Bearer {key}"}), timeout=30))
        ids = {m["id"] for m in listing["data"]}
        if args.model not in ids:
            sys.exit(f"model {args.model} not served by Voyager")
        extra = VOYAGER_THINKING_OFF.get(args.model, {})
        opts = {"temperature": 0, "seed": SEED, "max_tokens": NUM_PREDICT}
        meta_extra = {"backend": "voyager", "endpoint_host": urlparse(base).netloc, "extra_request_fields": extra,
                      "thinking_request": ("chat_template_kwargs.enable_thinking=false sent" if extra else "no flag sent (model default)")}
        default_dir = f"system_c_pilot_voyager_{args.model}_{stamp}"

        def ask(prompt):
            t0 = time.time()
            d = _voyager_post(base, key, {"model": args.model, "messages": [{"role": "user", "content": prompt}], **opts, **extra})
            ch, m, u = d["choices"][0], d["choices"][0]["message"], d.get("usage") or {}
            return {"response": m.get("content") or "", "thinking": m.get("reasoning_content") or m.get("reasoning"),
                    "done_reason": ch.get("finish_reason"), "eval_count": u.get("completion_tokens"), "eval_seconds": round(time.time() - t0, 2),
                    "prompt_eval_count": u.get("prompt_tokens"), "usage": u}
    run_dir = Path(args.run_dir) if args.run_dir else ROOT / "results" / default_dir
    (run_dir / "raw").mkdir(parents=True, exist_ok=True)
    meta = {"timestamp_utc": stamp, "git_hash": git, "model": args.model, "options": opts, "repeats": args.repeats,
            "n_problems": len(prompts), "tools": None, "retrieval": None, **meta_extra}
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    t_all = time.time()
    for r in range(1, args.repeats + 1):
        for p in prompts:
            f = run_dir / "raw" / f"{p['id']}_r{r}.json"
            if f.exists():
                continue
            t = time.time()
            out = ask(p["prompt"])
            rec = {"id": p["id"], "kind": p["kind"], "repeat": r, "prompt": p["prompt"], **out, "wall_seconds": round(time.time() - t, 1),
                   "finished_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
            f.write_text(json.dumps(rec, indent=2), encoding="utf-8")
            print(f"[r{r}] {p['id']:12} {rec['eval_count']!s:>5} tok  {rec['wall_seconds']:6.1f}s  done={rec['done_reason']}", flush=True)
    print(f"run finished in {(time.time() - t_all) / 60:.1f} min -> {run_dir}")


# ---------------------------------------------------------------- scoring
def _system_a_check(label, case):
    """Re-check a proposed section with System A. Returns dict(exists, passes, util, reasons)."""
    from steelagent import shapes
    from steelagent.compression import compression_strength
    from steelagent.flexure import flexure_strength
    try:
        s = shapes.get(label)
    except KeyError:
        return {"exists": False, "passes": False, "weight": None, "reasons": ["section not in AISC database"]}
    d, g, c = case["demands"], case["geometry"], case["constraints"]
    reasons, util = [], {}
    if case["member_type"] == "compression":
        util["compression"] = d["Pu_kip"] / compression_strength(s, g["Lcx_ft"], g["Lcy_ft"])["phiPn"]
        if "nominal_depth_in" in c and not label.startswith(f"W{c['nominal_depth_in']}X"):
            reasons.append(f"nominal depth is not {c['nominal_depth_in']} in.")
    else:
        util["flexure"] = d["Mu_kipft"] / flexure_strength(s, g["Lb_ft"], g.get("Cb", 1.0))["phiMn"]
        if "Ix_min_in4" in c:
            util["deflection(Ix)"] = c["Ix_min_in4"] / s["Ix"]
        if "max_depth_in" in c and int(re.match(r"W(\d+)X", label).group(1)) > c["max_depth_in"]:
            reasons.append(f"nominal depth exceeds {c['max_depth_in']} in.")
    reasons += [f"{k} utilization {v:.3f} > 1" for k, v in util.items() if v > 1.0]
    return {"exists": True, "passes": not reasons, "weight": float(s["W"]), "util": util, "reasons": reasons}


REFUSAL_RE = re.compile(
    r"(\bI (cannot|can't|can not|won't|am unable|'m unable|am not able|'m not able)\b|\bunable to (provide|determine|calculate|compute|answer)\b|"
    r"\bcannot (provide|determine|calculate|compute|answer)\b|\b(do|does)(n't| not) have (access|enough information)\b|"
    r"\binsufficient information\b|\bnot possible to (determine|calculate)\b)", re.I)


def is_refusal(text, answered):
    """A refusal = no parseable final answer AND the text declines / says it cannot. Regex heuristic: flagged outputs are read by hand."""
    return (not answered) and bool(REFUSAL_RE.search(text or ""))


def alt_limit_states(case):
    """Values the solver gives for plausible WRONG limit states / provisions of the same member (strength problems).
    A wrong answer within 1% of one of these is classified as 'wrong limit state' (inferred from the number, not from the model's words)."""
    from steelagent import shapes
    from steelagent.compression import compression_strength as C
    from steelagent.flexure import flexure_strength as F, shear_strength as V
    from steelagent.tension import tension_strength as T
    s, i, chk = shapes.get(case["shape"]), case["inputs"], case["check"]
    alts = {}
    if chk == "compression":
        alts["flexural buckling about x axis"] = C(s, i["Lcx_ft"], 0)["phiPn"]
        alts["flexural buckling about y axis"] = C(s, 0, i["Lcy_ft"])["phiPn"]
        alts["yielding of gross section (no buckling)"] = 0.9 * 50.0 * float(s["A"])
    elif chk == "flexure":
        f = F(s, i["Lb_ft"], i["Cb"])
        alts["plastic moment (yielding; ignores LTB/FLB)"] = f["phiMp"]
        alts["LTB with Cb = 1.0"] = F(s, i["Lb_ft"], 1.0)["phiMn"]
    elif chk == "tension_rupture":
        alts["yielding on gross section"] = T(s)["phiPn_yield"]
    elif chk == "shear":
        alts["phi_v = 0.90 instead of 1.00"] = 0.9 * V(s)["Vn"]
    return alts


def classify_wrong_limit_state(value, published, alts, tol=0.01):
    """Name of the first alternative limit state the wrong answer matches within tol, else None. Alternatives equal to the published value are ignored."""
    for name, alt in alts.items():
        if abs(alt - published) / published <= tol:
            continue
        if abs(value - alt) / alt <= tol:
            return name
    return None


def summarize(df, run_dir):
    """Summary metrics for a scored dataframe (any subset of repeats)."""
    df = df.copy()
    for c in ("err_pct", "unit_ok", "within_1pct", "within_5pct", "overestimate_gt_1pct", "wrong_limit_state", "expected_limit_state",
              "stated_limit_state", "wrong_limit_state_stated", "exact_match", "exists", "hallucinated", "system_a_pass", "unsafe",
              "weight_gap_lb_ft", "refusal"):
        if c not in df:                       # e.g. a model that never produced a parseable selection answer
            df[c] = None
    summ = {"runs": int(len(df)), "problems": int(df.id.nunique()), "repeats": int(df.repeat.nunique()), "truncated_outputs": int(df.truncated.sum()),
            "mean_eval_tokens": float(df.eval_tokens.mean()), "mean_wall_seconds": float(df.wall_seconds.mean()),
            "refusals": int(df.refusal.fillna(False).sum()), "no_final_answer": int(df.no_answer.sum()),
            "runs_with_reasoning_output": int(df.reasoning_present.sum())}
    st = df[df.kind == "strength"]
    if len(st):
        ok = st[~st.no_answer.astype(bool)]
        summ["strength"] = {
            "runs": int(len(st)), "no_final_answer": int(st.no_answer.sum()),
            "within_1pct": int(st.within_1pct.fillna(False).sum()), "within_5pct": int(st.within_5pct.fillna(False).sum()),
            "overestimate_gt_1pct": int(st.overestimate_gt_1pct.fillna(False).sum()),
            "unit_mismatch": int((~ok.unit_ok.astype(bool)).sum()) if len(ok) else 0,
            "median_abs_err_pct": float(ok.err_pct.abs().median()) if len(ok) else None,
            "mean_abs_err_pct": float(ok.err_pct.abs().mean()) if len(ok) else None,
            "max_abs_err_pct": float(ok.err_pct.abs().max()) if len(ok) else None,
            "wrong_limit_state": int(st.wrong_limit_state.notna().sum()) if "wrong_limit_state" in st else 0,
            "limit_state_applicable_runs": int(st.expected_limit_state.notna().sum()) if "expected_limit_state" in st else 0,
            "limit_state_stated_runs": int(st.stated_limit_state.notna().sum()) if "stated_limit_state" in st else 0,
            "wrong_limit_state_stated": int((st.wrong_limit_state_stated == True).sum()) if "wrong_limit_state_stated" in st else 0,  # noqa: E712
            "wrong_limit_state_by_problem": ({k: int(v) for k, v in st.dropna(subset=["wrong_limit_state"]).groupby("id").size().items()} if "wrong_limit_state" in st else {})}
    se = df[df.kind == "selection"]
    if len(se):
        summ["selection"] = {
            "runs": int(len(se)), "no_final_answer": int(se.no_answer.sum()),
            "exact_match_published": int(se.exact_match.fillna(False).sum()),
            "hallucinated_section": int(se.hallucinated.fillna(False).sum()),
            "system_a_pass": int(se.system_a_pass.fillna(False).sum()),
            "unsafe_recommendation": int(se.unsafe.fillna(False).sum()),
            "mean_weight_gap_lb_ft_when_exists": float(se.weight_gap_lb_ft.dropna().mean()) if se.weight_gap_lb_ft.notna().any() else None}
    # run-to-run consistency (temperature 0): identical raw text across repeats
    reps = {int(r) for r in df.repeat.unique()}
    if len(reps) > 1:
        same, multi = 0, 0
        for pid in df.id.unique():
            txt = [json.loads(f.read_text(encoding="utf-8"))["response"] for f in (run_dir / "raw").glob(f"{pid}_r*.json")
                   if int(f.stem.rsplit("_r", 1)[1]) in reps]
            if len(txt) >= 2:
                multi += 1
                same += len(set(txt)) == 1
        summ["problems_with_identical_text_across_repeats"] = same
        summ["problems_with_2plus_repeats"] = multi
    else:
        summ["problems_with_identical_text_across_repeats"] = None   # needs >= 2 repeats
    return summ


# ---- limit state the model STATES as governing (text heuristic; complements the value-based check)
_LB0_PATTERNS = {   # beams with Lb = 0: yielding vs flange local buckling
    "flange local buckling": [r"(?<![a-z])non-?compact\s+(flange|section|shape)", r"flanges?\s+(is|are)\s+(\*\*)?(non-?compact|slender)",
                              r"(?<![a-z])(?<!non-)(non-?compact|slender)\s+flanges?", r"(flange )?local buckling\s*(\(?FLB\)?)?\s*(governs|controls)",
                              r"governed by (flange )?local buckling"],
    "plastic yielding": [r"flanges?\s+(is|are)\s+(\*\*)?compact", r"(section|shape|flange|beam)\s+is\s+(\*\*)?compact",
                         r"governed by\s+(\*\*)?(plastic )?yielding", r"(yielding|plastic moment|M_p)\s*(\(\w+\))?\s*(governs|controls)",
                         r"nominal (moment )?strength is (the )?plastic moment", r"limit state:\s*(\*\*)?\s*(plastic )?yielding",
                         r"(flange|web)[^.\n]{0,40}\b(is|are)\s+(\*\*)?compact", r"local buckling( limit state)? does not (govern|control|reduce)",
                         r"(based on|governed by|limit state of)\s+(\*\*)?(plastic )?yield"]}
_LTB_PATTERNS = {   # beams with Lb > 0: LTB regime
    "inelastic LTB": [r"inelastic\s+(lateral[- ]torsional|LTB)", r"zone\s*2", r"L_?p\s*<\s*L_?b\s*(<|le|\u2264)\s*L_?r", r"between\s+L_?p"],
    "elastic LTB": [r"(?<![a-z])elastic\s+(lateral[- ]torsional|LTB)", r"zone\s*3", r"L_?b\s*>\s*L_?r"],
    "plastic yielding": [r"zone\s*1", r"L_?b\s*(le|\u2264|<=)\s*L_?p"]}


def _norm(text):
    return re.sub(r"[${}\\]", "", text or "")


def stated_limit_state_detail(problem_id, text):
    """(label, matched_text) of the LAST limit-state statement the heuristic finds, or (None, None). Beam-strength problems only."""
    s = _norm(text)
    if problem_id in ("F.1-1B", "F.3B"):
        pats = _LB0_PATTERNS
    elif problem_id in ("F.1-2B", "F.1-3B"):
        pats = _LTB_PATTERNS
    else:
        return None, None
    events = [(m.start(), lab, s[max(0, m.start() - 80): m.end() + 80].replace("\n", " ")) for lab, ps in pats.items()
              for pat in ps for m in re.finditer(pat, s, re.I)]
    if not events:
        return None, None
    _, lab, snip = max(events)
    return lab, snip


def stated_limit_state(problem_id, text):
    """Last governing limit state the working states, or None if none is stated. Only for the 4 beam-strength problems (F.1-1B, F.1-2B,
    F.1-3B, F.3B): 'plastic yielding' / 'inelastic LTB' / 'elastic LTB' / 'flange local buckling'. Column problems are not text-scored:
    a wrong buckling axis shows up in the number, which the value-based check classifies."""
    return stated_limit_state_detail(problem_id, text)[0]


def governing_statements(text, n=3):
    """The model's own last n lines mentioning governs/controls/critical/limit state (for hand review of any problem)."""
    hits = [re.sub(r"\s+", " ", l).strip() for l in (text or "").splitlines()
            if re.search(r"govern|control|critical|limit state", l, re.I) and len(l.strip()) < 400]
    return " || ".join(hits[-n:])


def expected_governing_description(case, kind):
    """What System A says governs, in words, for ALL 13 problems (review sheet reference column)."""
    from steelagent import shapes
    from steelagent.compression import compression_strength as C
    from steelagent.flexure import shear_strength as V
    if kind == "selection":
        chk = _system_a_check(case["published"]["section"], case)
        util = chk["util"]
        return f"published section {case['published']['section']}: controlling check = {max(util, key=util.get)} (utilization {max(util.values()):.3f})"
    s, i = shapes.get(case["shape"]), case["inputs"]
    if case["check"] == "tension_yield":
        return "yielding of gross section (D2-1)"
    if case["check"] == "tension_rupture":
        return "rupture of effective net area (D2-2)"
    if case["check"] == "compression":
        r = C(s, i["Lcx_ft"], i["Lcy_ft"])
        return f"flexural buckling about {r['governing_axis']} axis (E3), KL/r = {r['KL_r']:.1f}" + (" with slender elements (E7)" if r["slender_web"] or r["slender_flange"] else "")
    if case["check"] == "flexure":
        return expected_limit_state(case) + " (F2/F3)"
    v = V(s)
    return f"shear yielding of web, G2.1({'a' if v['phi_v'] == 1.0 else 'b'}), phi_v = {v['phi_v']}, Cv1 = {v['Cv1']:.2f}"


def expected_limit_state(case):
    """Governing limit state per System A for the beam-strength problems, in the vocabulary of stated_limit_state(); None otherwise."""
    from steelagent import shapes
    from steelagent.flexure import flexure_strength as F
    s, i = shapes.get(case["shape"]), case["inputs"]
    if case["check"] == "flexure":
        f = F(s, i["Lb_ft"], i["Cb"])
        if f["governing"] == "FLB":
            return "flange local buckling"
        if f["governing"] == "yielding":
            return "plastic yielding"
        return "inelastic LTB" if i["Lb_ft"] <= f["Lr_ft"] else "elastic LTB"
    return None


def score(args):
    from steelagent import shapes
    run_dir = Path(args.run_dir)
    prompts = {p["id"]: p for p in build_prompts()}
    STRENGTH_CASES = json.loads((C_DIR / "design_examples_strength.json").read_text(encoding="utf-8"))["cases"]
    rows = []
    for f in sorted((run_dir / "raw").glob("*.json")):
        rec = json.loads(f.read_text(encoding="utf-8"))
        p = prompts[rec["id"]]
        row = {"id": rec["id"], "kind": rec["kind"], "repeat": rec["repeat"], "truncated": rec["done_reason"] == "length",
               "eval_tokens": rec["eval_count"], "wall_seconds": rec["wall_seconds"],
               "reasoning_present": bool(rec.get("thinking")) or "<think" in (rec["response"] or "").lower()}
        if rec["kind"] == "strength":
            v, u = parse_final_number(rec["response"])
            ref = p["expected"]["value"]
            row.update(published=ref, parsed=v, unit=u, no_answer=v is None)
            if v is not None:
                err = 100 * (v - ref) / ref
                row.update(unit_ok=unit_ok(u, p["expected"]["unit"]), err_pct=err, within_1pct=abs(err) <= 1.0,
                           within_5pct=abs(err) <= 5.0, overestimate_gt_1pct=err > 1.0)
                if abs(err) > 1.0:
                    row["wrong_limit_state"] = classify_wrong_limit_state(v, ref, alt_limit_states(next(c for c in STRENGTH_CASES if c["id"] == rec["id"])))
            row["refusal"] = is_refusal(rec["response"], v is not None)
            case_ = next(c for c in STRENGTH_CASES if c["id"] == rec["id"])
            exp_ls = expected_limit_state(case_)
            if exp_ls is not None:
                got_ls = stated_limit_state(rec["id"], rec["response"])
                row.update(expected_limit_state=exp_ls, stated_limit_state=got_ls,
                           wrong_limit_state_stated=(got_ls != exp_ls) if got_ls is not None else None)
        else:
            lab = parse_final_section(rec["response"])
            case, pub = p["expected"]["case"], p["expected"]["section"]
            row.update(published=pub, parsed=lab, no_answer=lab is None, refusal=is_refusal(rec["response"], lab is not None))
            if lab is not None:
                chk = _system_a_check(lab, case)
                row.update(exact_match=lab == pub, exists=chk["exists"], system_a_pass=chk["passes"],
                           unsafe=chk["exists"] and not chk["passes"], hallucinated=not chk["exists"],
                           weight=chk["weight"], weight_gap_lb_ft=(chk["weight"] - float(shapes.get(pub)["W"])) if chk["weight"] else None,
                           system_a_reasons="; ".join(chk["reasons"]))
        rows.append(row)
    import pandas as pd
    df = pd.DataFrame(rows)
    df.to_csv(run_dir / "scores.csv", index=False)
    summ = summarize(df, run_dir)
    import hashlib
    summ["scorer_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (run_dir / "summary.json").write_text(json.dumps(summ, indent=2), encoding="utf-8")
    print(json.dumps(summ, indent=2))
    cols = [c for c in ("id", "repeat", "published", "parsed", "err_pct", "unit_ok", "wrong_limit_state", "expected_limit_state", "stated_limit_state", "refusal", "exact_match", "exists", "system_a_pass", "system_a_reasons") if c in df]
    print(df[cols].round(2).to_string(index=False))


def compare(args):
    """Side-by-side table of several scored run directories (label=dir). Writes results/system_c_comparison_<ts>/."""
    import pandas as pd
    cols, rows_out = {}, {}
    for spec in args.run:
        label, d = spec.split("=", 1)
        d = Path(d)
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        df = pd.read_csv(d / "scores.csv")
        if args.max_repeat:
            df = df[df.repeat <= args.max_repeat]
        summ = summarize(df, d)
        st, se = summ["strength"], summ["selection"]
        n_st, n_se = st["runs"], se["runs"]
        # the first local run was written before 'backend'/'thinking_request' existed in meta.json; it recorded think=false
        req = meta.get("thinking_request") or ("think=false sent to Ollama" if meta.get("think") is False else "not recorded")
        thinking = f"{req}; reasoning output in {summ['runs_with_reasoning_output']}/{summ['runs']} runs"
        cols[label] = {
            "Backend / model": f"{meta.get('backend', 'ollama')} / {meta['model']}",
            "Thinking / reasoning mode": thinking,
            "Runs scored (13 problems x repeats)": f"{summ['runs']}",
            "PRIMARY | Strength runs with a parsed numeric answer (error stats below cover only these)": f"{n_st - st['no_final_answer']} of {n_st}",
            "PRIMARY | Strength: median |error| % vs AISC": round(st["median_abs_err_pct"], 2) if st["median_abs_err_pct"] is not None else None,
            "PRIMARY | Strength: mean |error| %": round(st["mean_abs_err_pct"], 2) if st["mean_abs_err_pct"] is not None else None,
            "PRIMARY | Strength: max |error| %": round(st["max_abs_err_pct"], 2) if st["max_abs_err_pct"] is not None else None,
            "PRIMARY | Strength: correct (within 1% of AISC)": f"{st['within_1pct']} of {n_st} ({100 * st['within_1pct'] / max(n_st, 1):.0f}%)",
            "PRIMARY | Strength: within 5% of AISC": f"{st['within_5pct']} of {n_st} ({100 * st['within_5pct'] / max(n_st, 1):.0f}%)",
            "PRIMARY | Strength: overestimate > 1% (unsafe direction)": f"{st['overestimate_gt_1pct']} of {n_st}",
            "PRIMARY | Selection: exact match to AISC section": f"{se['exact_match_published']} of {n_se}",
            "PRIMARY | Selection: section fails System A re-check (unsafe)": f"{se['unsafe_recommendation']} of {n_se}",
            "PRIMARY | Selection: hallucinated section (not in AISC database)": f"{se['hallucinated_section']} of {n_se}",
            "Refusals (regex; flagged outputs read by hand)": f"{summ['refusals']} of {summ['runs']}",
            "No parseable final answer (incl. refusals)": f"{summ['no_final_answer']} of {summ['runs']}",
            "Truncated outputs (hit 1,500-token cap)": f"{summ['truncated_outputs']} of {summ['runs']}",
            "SECONDARY | Wrong limit state, inferred from the value (answer matches another limit state's value)": f"{st['wrong_limit_state']} of {n_st}",
            "SECONDARY |   ...which problems": ", ".join(f"{k} x{v}" for k, v in st["wrong_limit_state_by_problem"].items()) or "none",
            "SECONDARY | Wrong limit state stated in working, beams only (heuristic text match)":
                f"{st['wrong_limit_state_stated']} of {st['limit_state_stated_runs']} runs that state one ({st['limit_state_applicable_runs']} beam runs)",
            "Mean output tokens": round(summ["mean_eval_tokens"], 0),
            "Determinism at temperature 0: problems with identical text across repeats": (f"{summ['problems_with_identical_text_across_repeats']} of {summ['problems_with_2plus_repeats']} problems with >= 2 repeats" if summ["problems_with_identical_text_across_repeats"] is not None else "n/a (1 repeat)"),
        }
        all_ids = [c["id"] for c in json.loads((C_DIR / "design_examples_strength.json").read_text(encoding="utf-8"))["cases"]]
        sdf = df[df.kind == "strength"]
        med = sdf.groupby("id").err_pct.apply(lambda s: s.abs().median() if s.notna().any() else float("nan"))
        n_ok = sdf.groupby("id").err_pct.apply(lambda s: int(s.notna().sum()))
        n_all = sdf.groupby("id").size()
        rows_out[label] = pd.Series({i: (f"{med[i]:.2f} ({n_ok[i]}/{n_all[i]})" if n_ok.get(i, 0) else f"no answer (0/{n_all.get(i, 0)})") for i in all_ids})
    table = pd.DataFrame(cols)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "results" / f"system_c_comparison_{stamp}"
    out.mkdir(parents=True)
    table.to_csv(out / "comparison.csv")
    per_problem = pd.DataFrame(rows_out)
    per_problem.to_csv(out / "median_abs_error_by_problem.csv")
    import hashlib
    (out / "inputs.json").write_text(json.dumps({"max_repeat": args.max_repeat or None,
                                                 "scorer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), **{s.split("=", 1)[0]: s.split("=", 1)[1] for s in args.run}}, indent=2), encoding="utf-8")
    print(table.to_string()); print(); print("median |error| % by strength problem (parsed answers / runs):"); print(per_problem.to_string()); print("saved to", out)


def review_sheet(args):
    """CSV for hand-checking: per model x problem x repeat, the model's own governing statements, the classifier's label and System A's governing state."""
    import csv, hashlib
    strength = {c["id"]: c for c in json.loads((C_DIR / "design_examples_strength.json").read_text(encoding="utf-8"))["cases"]}
    selection = {c["id"]: c for c in json.loads((C_DIR / "design_examples_selection.json").read_text(encoding="utf-8"))["cases"]}
    order = {pid: i for i, pid in enumerate([p["id"] for p in build_prompts()])}
    rows = []
    for spec in args.run:
        label, d = spec.split("=", 1)
        d = Path(d)
        import pandas as pd
        sc = pd.read_csv(d / "scores.csv").set_index(["id", "repeat"])
        for f in sorted((d / "raw").glob("*.json")):
            rec = json.loads(f.read_text(encoding="utf-8"))
            pid, rep_ = rec["id"], rec["repeat"]
            s = sc.loc[(pid, rep_)]
            case = strength.get(pid) or selection[pid]
            exp_desc = expected_governing_description(case, rec["kind"])
            lab, snip = stated_limit_state_detail(pid, rec["response"])
            exp_label = expected_limit_state(case) if rec["kind"] == "strength" else None
            final_line = next((l.strip() for l in reversed(rec["response"].splitlines()) if "FINAL ANSWER" in l.upper()), "")
            rows.append({
                "model": label, "problem_id": pid, "repeat": rep_, "kind": rec["kind"],
                "published_answer": s["published"], "parsed_answer": s["parsed"] if str(s["parsed"]) != "nan" else "",
                "error_pct": ("" if str(s.get("err_pct")) == "nan" else round(float(s["err_pct"]), 2)) if rec["kind"] == "strength" else "",
                "output_truncated": bool(s["truncated"]), "final_answer_line": final_line,
                "system_a_governing": exp_desc,
                "classifier_applies": exp_label is not None,
                "classifier_label": (lab or "(none stated)") if exp_label is not None else "n/a (not text-scored)",
                "classifier_expected_label": exp_label or "",
                "classifier_agrees_with_system_a": ("" if exp_label is None or lab is None else lab == exp_label),
                "classifier_matched_text": snip or "",
                "model_governing_statements": governing_statements(rec["response"]),
                "raw_output_file": str((d / "raw" / f.name).resolve().relative_to(ROOT)).replace("\\", "/"),
                "reviewer_label": "", "reviewer_notes": ""})
    rows.sort(key=lambda r: (order[r["problem_id"]], r["model"], r["repeat"]))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {out}  (scorer sha256 {hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:12]})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("--backend", choices=["ollama", "voyager"], default="ollama")
    r.add_argument("--model", default="qwen3.5:9b"); r.add_argument("--repeats", type=int, default=3)
    r.add_argument("--run-dir", default=None, help="resume an existing run directory")
    s = sub.add_parser("score"); s.add_argument("--run-dir", required=True)
    c = sub.add_parser("compare"); c.add_argument("--run", nargs="+", required=True, help="label=run_dir ...")
    c.add_argument("--max-repeat", type=int, default=0, help="use only repeats 1..N of every run (apples-to-apples when runs have different repeat counts)")
    v = sub.add_parser("review-sheet"); v.add_argument("--run", nargs="+", required=True, help="label=run_dir ..."); v.add_argument("--out", required=True)
    a = ap.parse_args()
    {"run": run, "score": score, "compare": compare, "review-sheet": review_sheet}[a.cmd](a)
