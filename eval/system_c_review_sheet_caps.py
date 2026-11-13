"""Hand-check sheet covering BOTH output caps: one row per model x problem x repeat x cap.

Reuses the frozen classifier/scorer helpers from system_c_pilot.py (imported, not edited) and the scores.csv each run was scored into.
Row order: F.3B first, then the other beam-strength problems (F.1-1B, F.1-2B, F.1-3B), then everything else.
Columns the reviewer fills: dylan_verdict (left empty).

Usage (repo root):
  .venv/Scripts/python.exe eval/system_c_review_sheet_caps.py --out results/system_c_review_sheet.csv \
      --run "voyager gemma4-31b-it|1500|results/<dir>" --run "voyager gemma4-31b-it|4000|results/<dir>" ...
"""
import argparse, csv, hashlib, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "steelagent"))
import pandas as pd  # noqa: E402
import system_c_pilot as S  # noqa: E402

def _quote_line(problem_id, text):
    """The original output line holding the LAST limit-state statement the classifier matched (same pattern sets, same 'last wins' rule)."""
    if problem_id in ("F.1-1B", "F.3B"):
        pats = S._LB0_PATTERNS
    elif problem_id in ("F.1-2B", "F.1-3B"):
        pats = S._LTB_PATTERNS
    else:
        return None
    best = None
    for i, raw in enumerate((text or "").splitlines()):
        s = S._norm(raw)
        for ps in pats.values():
            for pat in ps:
                for m in re.finditer(pat, s, re.I):
                    if best is None or (i, m.start()) > best[0]:
                        best = ((i, m.start()), raw)
    return best[1].replace("**", "").replace("$", "").strip() if best else None


BEAMS_FIRST = ["F.3B", "F.1-1B", "F.1-2B", "F.1-3B"]
MAX_QUOTE = 220


def _short(text, n=MAX_QUOTE):
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _source_of_published_state(case, kind):
    """Where the 'published' limit state comes from: the Dataset C record names it for the F-series beams; otherwise System A (which matches the published value)."""
    if kind == "strength" and case["id"] in ("F.1-1B", "F.1-2B", "F.1-3B", "F.3B"):
        return "Dataset C record (problem description names it); equals System A"
    if kind == "strength" and case["check"] in ("tension_yield", "tension_rupture"):
        return "defined by the question asked (D2-1 or D2-2)"
    return "System A governing state (solver reproduces the published value within 0.5%)"


def build(runs):
    strength = {c["id"]: c for c in json.loads((S.C_DIR / "design_examples_strength.json").read_text(encoding="utf-8"))["cases"]}
    selection = {c["id"]: c for c in json.loads((S.C_DIR / "design_examples_selection.json").read_text(encoding="utf-8"))["cases"]}
    all_ids = [p["id"] for p in S.build_prompts()]
    rest = [i for i in all_ids if i not in BEAMS_FIRST]
    order = {pid: i for i, pid in enumerate(BEAMS_FIRST + rest)}
    rows = []
    for spec in runs:
        model, cap, d = spec.split("|", 2)
        d = Path(d)
        sc = pd.read_csv(d / "scores.csv").set_index(["id", "repeat"])
        for f in sorted((d / "raw").glob("*.json")):
            rec = json.loads(f.read_text(encoding="utf-8"))
            pid, rep = rec["id"], rec["repeat"]
            s = sc.loc[(pid, rep)]
            case = strength.get(pid) or selection[pid]
            exp_label = S.expected_limit_state(case) if rec["kind"] == "strength" else None
            lab, snip = S.stated_limit_state_detail(pid, rec["response"])
            statements = S.governing_statements(rec["response"], n=2)
            truncated = bool(s["truncated"])
            line = _quote_line(pid, rec["response"]) if exp_label is not None else None
            if exp_label is not None and (line or snip):
                quote = _short(line or snip)
            elif statements:
                quote = _short(statements)
            else:
                quote = "(no governing-state statement in the output" + ("; output hit the token cap)" if truncated else ")")
            rows.append({
                "problem_id": pid, "model": model, "cap": int(cap), "repeat": rep,
                "stated_governing_limit_state_quote": quote,
                "classifier_label": (lab or "(none stated)") if exp_label is not None else "n/a (not text-scored)",
                "published_aisc_limit_state": S.expected_governing_description(case, rec["kind"]),
                "dylan_verdict": "",
                "classifier_agrees_with_published": ("" if exp_label is None or lab is None else lab == exp_label),
                "limit_state_source": _source_of_published_state(case, rec["kind"]),
                "published_answer": s["published"],
                "parsed_answer": "" if str(s["parsed"]) == "nan" else s["parsed"],
                "error_pct": "" if rec["kind"] != "strength" or str(s.get("err_pct")) == "nan" else round(float(s["err_pct"]), 2),
                "output_truncated": truncated,
                "raw_output_file": str((d / "raw" / f.name).resolve().relative_to(ROOT)).replace("\\", "/"),
            })
    rows.sort(key=lambda r: (order[r["problem_id"]], r["model"], r["cap"], r["repeat"]))
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--run", action="append", required=True, help="'model label|cap|run_dir'")
    a = ap.parse_args()
    rows = build(a.run)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    per = pd.DataFrame(rows).groupby(["model", "cap"]).size().to_dict()
    print(f"wrote {len(rows)} rows to {out} | per (model, cap): {per} | scorer sha256 {hashlib.sha256(Path(S.__file__).read_bytes()).hexdigest()[:12]}")
    print("first rows:", [(r['problem_id'], r['model'], r['cap'], r['repeat']) for r in rows[:4]])
