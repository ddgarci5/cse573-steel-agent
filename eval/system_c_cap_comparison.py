"""Side-by-side table of the System C pilot at both output caps, per model, with exact counts.

Reads each run's summary.json (written by `system_c_pilot.py score` with the frozen scorer) and does no scoring of its own.
Usage (repo root):
  .venv/Scripts/python.exe eval/system_c_cap_comparison.py --run "voyager gemma4-31b-it|1500|results/<dir>" --run "voyager gemma4-31b-it|4000|results/<dir>" ...
Writes results/system_c_cap_comparison_<UTC>/{cap_comparison.csv,cap_comparison.md,inputs.json} and prints the table.
"""
import argparse, csv, datetime, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def row_values(summ):
    st, se = summ["strength"], summ["selection"]
    n_st, n_se = st["runs"], se["runs"]
    same, multi = summ["problems_with_identical_text_across_repeats"], summ["problems_with_2plus_repeats"]
    return [
        ("Strength runs answered (parsed numeric answer)", f"{n_st - st['no_final_answer']} of {n_st}"),
        ("Strength: within 1% of AISC", f"{st['within_1pct']} of {n_st}"),
        ("Strength: within 5% of AISC", f"{st['within_5pct']} of {n_st}"),
        ("Strength: overestimate > 1% (unsafe direction)", f"{st['overestimate_gt_1pct']} of {n_st}"),
        ("Selection: matches AISC section", f"{se['exact_match_published']} of {n_se}"),
        ("Selection: answered (parsed section)", f"{n_se - se['no_final_answer']} of {n_se}"),
        ("Selection: proposed section fails a System A check (unsafe)", f"{se['unsafe_recommendation']} of {n_se}"),
        ("Selection: section not in AISC database", f"{se['hallucinated_section']} of {n_se}"),
        ("Truncated outputs (hit the cap)", f"{summ['truncated_outputs']} of {summ['runs']}"),
        ("Repeats agreed (identical text, problems with >= 2 repeats)", f"{same} of {multi}" if same is not None else "n/a (1 repeat)"),
        ("Strength median abs. error, answered runs", f"{st['median_abs_err_pct']:.2f}%" if st["median_abs_err_pct"] is not None else "n/a"),
        ("Strength max abs. error, answered runs", f"{st['max_abs_err_pct']:.2f}%" if st["max_abs_err_pct"] is not None else "n/a"),
        ("Mean output tokens", f"{summ['mean_eval_tokens']:.0f}"),
    ]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="append", required=True, help="'model label|cap|run_dir'")
    a = ap.parse_args()
    cols, hashes = {}, set()
    for spec in a.run:
        model, cap, d = spec.split("|", 2)
        summ = json.loads((Path(d) / "summary.json").read_text(encoding="utf-8"))
        hashes.add(summ["scorer_sha256"][:12])
        cols[f"{model} @ {cap}"] = dict(row_values(summ))
    labels = list(next(iter(cols.values())).keys())
    out = ROOT / "results" / f"system_c_cap_comparison_{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    out.mkdir(parents=True)
    with open(out / "cap_comparison.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["metric"] + list(cols))
        for lab in labels:
            w.writerow([lab] + [cols[c][lab] for c in cols])
    md = ["| Metric | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols)]
    md += [f"| {lab} | " + " | ".join(cols[c][lab] for c in cols) + " |" for lab in labels]
    (out / "cap_comparison.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (out / "inputs.json").write_text(json.dumps({"runs": a.run, "scorer_sha256_prefixes_in_inputs": sorted(hashes)}, indent=2), encoding="utf-8")
    print("\n".join(md))
    print("\nscorer hashes across inputs:", sorted(hashes), "| saved to", out)
