"""Pilot of Dataset C: problems from AISC Design Examples v16.0 (first-semester set).
Only problem parameters and published answers are recorded; no AISC text is reproduced."""
import sys, json; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from steelagent import shapes as S
from steelagent.compression import compression_strength as C
from steelagent.flexure import flexure_strength as F, shear_strength as V
from steelagent.tension import tension_strength as T
from steelagent.search import lightest

cases = [  # id, description, computed value, published LRFD value
 ("D.1",  "W8x21 tension yielding",                    T(S.get("W8X21"))["phiPn_yield"], 277),
 ("D.1",  "W8x21 tension rupture (An=4.76, U=0.908)",   T(S.get("W8X21"), An=4.76, U=0.908)["phiPn_rupture"], 211),
 ("E.1C", "W14x132 phiPn, Lc=30 ft both axes",          C(S.get("W14X132"), 30, 30)["phiPn"], 892),
 ("E.1D", "W14x90 phiPn, Lcx=30 ft, Lcy=15 ft",         C(S.get("W14X90"), 30, 15)["phiPn"], 927),
 ("F.1-1B","W18x50 phiMn, continuously braced",         F(S.get("W18X50"), 0)["phiMn"], 379),
 ("F.1-2B","W18x50 phiMn, Lb=11.7 ft, Cb=1.01",         F(S.get("W18X50"), 35/3, 1.01)["phiMn"], 304),
 ("F.1-3B","W18x50 phiMn, Lb=17.5 ft, Cb=1.30 (elastic LTB)", F(S.get("W18X50"), 17.5, 1.30)["phiMn"], 288),
 ("F.3B", "W21x48 phiMn, noncompact flange (FLB)",       F(S.get("W21X48"), 0)["phiMn"], 398),
 ("G.1B", "W24x62 phiVn",                               V(S.get("W24X62"))["phiVn"], 306),
]
print(f"{'Example':8} {'Check':48} {'ours':>8} {'AISC':>6} {'err%':>6}")
res = []
for ex, d, ours, ref in cases:
    e = 100 * (ours - ref) / ref; res.append(abs(e))
    print(f"{ex:8} {d:48} {ours:8.1f} {ref:6} {e:6.2f}")
print(f"\nstrength checks: {len(res)}  max |err| {max(res):.2f}%")

sel = [
 ("E.1A", "lightest W14 column, Pu=840 k, Lc=30 ft", lightest("compression", {"Pu": 840}, {"Lcx_ft": 30, "Lcy_ft": 30}, depth=14), "W14X132"),
 ("F.1-1A","lightest W<=18 beam, Mu=266, Ix>=746, braced", None, "W18X50"),
 ("F.4",  "lightest W beam, Mu=468, Ix>=1260, braced",  lightest("flexure", {"Mu": 468}, {"Lb_ft": 0}, Ix_min=1260), "W24X55"),
 ("F.3A", "lightest W beam, Mu=396, braced",            lightest("flexure", {"Mu": 396}, {"Lb_ft": 0}), "W21X48"),
]
# F.1-1A depth limit "max nominal depth 18 in." -> search W18 and shallower
best = None
for dep in (18, 16, 14, 12, 10, 8, 6):
    r = lightest("flexure", {"Mu": 266}, {"Lb_ft": 0}, depth=dep, Ix_min=746)
    if r["section"] and (best is None or S.get(r["section"])["W"] < S.get(best["section"])["W"]):
        best = r
sel[1] = (sel[1][0], sel[1][1], best, sel[1][3])
print(f"\n{'Example':8} {'Selection task':44} {'ours':>9} {'AISC':>9}  match")
for ex, d, r, ref in sel:
    print(f"{ex:8} {d:44} {r['section']:>9} {ref:>9}  {r['section']==ref}  (util {r['utilization']:.3f}, controls {r['controls']})")
