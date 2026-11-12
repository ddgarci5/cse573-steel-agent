"""Re-score the solver in THIS repo against the AISC values recorded in the shipped Nov 11 CSVs.

The `aisc*` columns were parsed from the Manual PDFs in the original sandbox (poppler pdftotext).
This script does NOT re-parse the PDFs: it recomputes our side with the current code and compares
it with those recorded values. It checks solver code, not the PDF parser."""
import os, sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd
from steelagent import shapes
from steelagent.compression import compression_strength, fcr_e3, PHI_C
from steelagent.flexure import flexure_strength, shear_strength

HERE = Path(__file__).parent
OUT = Path(os.environ.get("STEELAGENT_OUT", HERE))

def summarize(name, df, ours_col, ref_col):
    err = 100 * (df[ours_col] - df[ref_col]) / df[ref_col]
    a = err.abs()
    print(f"{name:34} cases {len(df):5d}  mean|err| {a.mean():.3f}%  max|err| {a.max():.3f}%  within 1%: {(a <= 1).mean() * 100:.1f}%")
    return {"table": name, "cases": int(len(df)), "mean_abs_err_pct": float(a.mean()), "max_abs_err_pct": float(a.max())}

c = pd.read_csv(HERE / "compression_table4-1a_results.csv")
c["rescored"] = [compression_strength(shapes.get(s), 0, L)["phiPn"] for s, L in zip(c["shape"], c.Lc_ft)]
f = pd.read_csv(HERE / "flexure_table3-2_results.csv")
def _flex(row):
    s = shapes.get(row["shape"]); fl = flexure_strength(s, 0)
    return {"phiMp": fl["phiMn_flb"], "phiMr": fl["phiMr"], "BF": fl["BF"], "Lp": fl["Lp_eff_ft"],
            "Lr": fl["Lr_ft"], "phiVn": shear_strength(s)["phiVn"]}[row["quantity"]]
f["rescored"] = f.apply(_flex, axis=1)
r = pd.read_csv(HERE / "fcr_table4-14_results.csv")
r["rescored"] = [PHI_C * fcr_e3(fy, 29000.0, s)[0] for fy, s in zip(r.Fy, r.Lc_r)]

out = [summarize("Table 4-1a phiPn (W14)", c, "rescored", "aisc_phiPn"),
       summarize("Table 3-2 (all 6 quantities)", f, "rescored", "aisc"),
       summarize("Table 4-14 phiFcr", r, "rescored", "aisc")]
print("\nTable 3-2 by quantity (max |err| %):")
fe = 100 * (f.rescored - f.aisc) / f.aisc
print(fe.abs().groupby(f.quantity).max().round(3).to_string())
print(f"Table 3-2 shapes: {f['shape'].nunique()}  note-flagged: {sorted(set(f.loc[f.note.notna(), 'shape']))}")
print(f"Table 4-1a shapes: {c['shape'].nunique()}  slender-shape cases: {int(c.slender.sum())}")
