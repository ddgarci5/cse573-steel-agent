import os, sys, json; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd
from steelagent import shapes
from steelagent.compression import compression_strength
from validation.parse_tables import table_4_1a

rows = []
for shape, Lc, ref in table_4_1a():
    r = compression_strength(shapes.get(shape), Lcx_ft=0, Lcy_ft=Lc)  # table is w.r.t. ry
    rows.append({"shape": shape, "Lc_ft": Lc, "aisc_phiPn": ref, "ours_phiPn": r["phiPn"],
                 "slender": r["slender_web"] or r["slender_flange"], "KL_r": r["KL_r"]})
df = pd.DataFrame(rows)
df["err_pct"] = 100 * (df.ours_phiPn - df.aisc_phiPn) / df.aisc_phiPn
df.to_csv(Path(os.environ.get("STEELAGENT_OUT", Path(__file__).parent)) / "compression_table4-1a_results.csv", index=False)
a = df.err_pct.abs()
print(f"cases: {len(df)}  shapes: {df["shape"].nunique()}  slender-shape cases: {df.slender.sum()}")
print(f"mean |err| {a.mean():.3f}%   max |err| {a.max():.3f}%   within 1%: {(a<=1).mean()*100:.1f}%   within 2%: {(a<=2).mean()*100:.1f}%")
print(df.groupby("shape").err_pct.agg(lambda s: s.abs().max()).round(3).to_string())
print(df.loc[a.nlargest(6).index].round(2).to_string())
