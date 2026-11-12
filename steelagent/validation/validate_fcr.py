import os, sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd
from steelagent.compression import fcr_e3, PHI_C
from validation.parse_tables import table_4_14
rows = [{"Fy": fy, "Lc_r": s, "aisc": ref, "ours": PHI_C * fcr_e3(fy, 29000.0, s)[0]} for fy, s, ref in table_4_14()]
df = pd.DataFrame(rows); df["err_pct"] = 100 * (df.ours - df.aisc) / df.aisc
df.to_csv(Path(os.environ.get("STEELAGENT_OUT", Path(__file__).parent)) / "fcr_table4-14_results.csv", index=False)
a = df.err_pct.abs()
print(f"cases {len(df)}  Lc/r range {df.Lc_r.min()}-{df.Lc_r.max()}  Fy values {sorted(df.Fy.unique())}")
print(f"mean |err| {a.mean():.3f}%  max |err| {a.max():.3f}%  within 1%: {(a<=1).mean()*100:.1f}%")
print(df.loc[a.nlargest(4).index].round(3).to_string())
