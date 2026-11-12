import os, sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd
from steelagent import shapes
from steelagent.flexure import flexure_strength, shear_strength
from validation.parse_tables import table_3_2

rows = []
for t in table_3_2():
    s = shapes.get(t["shape"])
    f = flexure_strength(s, Lb_ft=0); v = shear_strength(s)
    ours = {"phiMp": f["phiMn_flb"], "phiMr": f["phiMr"], "BF": f["BF"],
            "Lp": f["Lp_eff_ft"], "Lr": f["Lr_ft"], "phiVn": v["phiVn"]}
    for k, val in ours.items():
        rows.append({"shape": t["shape"], "note": t["note"], "quantity": k, "aisc": t[k], "ours": val})
df = pd.DataFrame(rows)
df["err_pct"] = 100 * (df.ours - df.aisc) / df.aisc
df.to_csv(Path(os.environ.get("STEELAGENT_OUT", Path(__file__).parent)) / "flexure_table3-2_results.csv", index=False)
a = df.err_pct.abs()
print(f"shapes: {df['shape'].nunique()}  comparisons: {len(df)}  [f]/[v] shapes: {sorted(set(df.loc[df.note!='','shape']+df.loc[df.note!='','note']))}")
print(f"mean |err| {a.mean():.3f}%  max |err| {a.max():.3f}%  within 1%: {(a<=1).mean()*100:.1f}%  within 2%: {(a<=2).mean()*100:.1f}%")
print(df.groupby("quantity").err_pct.agg(mean_abs=lambda s: s.abs().mean(), max_abs=lambda s: s.abs().max()).round(3).to_string())
print(df.loc[a.nlargest(6).index].round(3).to_string())
