"""AISC 360-22 Chapter D: tension members (LRFD). Rupture is evaluated only when the
net area An and shear-lag factor U are supplied (the agent must ask for them otherwise)."""
from .materials import A992

def tension_strength(shape, An=None, U=None, mat=A992):
    Ag = shape["A"]
    out = {"phiPn_yield": 0.90 * mat["Fy"] * Ag, "provisions": ["D2(a)"]}       # D2-1
    if An is not None and U is not None:
        Ae = An * U                                                              # D3-1
        out.update(Ae=Ae, phiPn_rupture=0.75 * mat["Fu"] * Ae)                    # D2-2
        out["provisions"].append("D2(b)")
    else:
        out["missing_for_rupture"] = [k for k, v in (("An", An), ("U", U)) if v is None]
    states = {k: v for k, v in out.items() if k.startswith("phiPn_")}
    out["phiPn"] = min(states.values()); out["governing"] = min(states, key=states.get)
    return out
