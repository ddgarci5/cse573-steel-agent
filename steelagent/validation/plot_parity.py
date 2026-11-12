import pandas as pd, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
c = pd.read_csv("validation/compression_table4-1a_results.csv")
f = pd.read_csv("validation/flexure_table3-2_results.csv")
r = pd.read_csv("validation/fcr_table4-14_results.csv")
fig, ax = plt.subplots(1, 3, figsize=(13, 4.2), dpi=200)
panels = [
    (ax[0], c.aisc_phiPn, c.ours_phiPn, "Compression φcPn (kips)\nTable 4-1a · 13 W14 shapes · 324 cases"),
    (ax[1], f[f.quantity.isin(["phiMp","phiMr"])].aisc, f[f.quantity.isin(["phiMp","phiMr"])].ours,
     "Flexure φbMp, φbMr (kip-ft)\nTable 3-2 · 63 W-shapes · 126 cases"),
    (ax[2], r.aisc, r.ours, "Critical stress φcFcr (ksi)\nTable 4-14 · 6 grades · 1,200 cases"),
]
for a, x, y, t in panels:
    lo, hi = min(x.min(), y.min()), max(x.max(), y.max())
    a.plot([lo, hi], [lo, hi], color="#9CA3AF", lw=1, zorder=1)
    a.scatter(x, y, s=9, color="#8C1D40", alpha=.75, zorder=2, edgecolors="none")
    a.set_title(t, fontsize=10); a.set_xlabel("AISC Manual tabulated value"); a.set_ylabel("Our solver")
    a.spines[["top", "right"]].set_visible(False)
plt.tight_layout(); plt.savefig("validation/parity.png", bbox_inches="tight")
