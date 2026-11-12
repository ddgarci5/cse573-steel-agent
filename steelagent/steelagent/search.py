"""Exhaustive candidate search: lightest W-shape passing every required check (System A)."""
from . import shapes
from .compression import compression_strength
from .flexure import flexure_strength, shear_strength

def lightest(member, demands, geometry, depth=None, Ix_min=None):
    df = shapes.w_shapes()
    if depth:
        df = df[df.index.str.startswith(f"W{depth}X")]
    rows = []
    for label, s in df.sort_values("W").iterrows():
        checks = {}
        if member == "compression":
            r = compression_strength(s, geometry["Lcx_ft"], geometry["Lcy_ft"])
            checks["compression"] = demands["Pu"] / r["phiPn"]
        if member == "flexure":
            f = flexure_strength(s, geometry["Lb_ft"], geometry.get("Cb", 1.0))
            checks["flexure"] = demands["Mu"] / f["phiMn"]
            if "Vu" in demands:
                checks["shear"] = demands["Vu"] / shear_strength(s)["phiVn"]
            if Ix_min:
                checks["deflection"] = Ix_min / s["Ix"]
        util = max(checks.values())
        rows.append((label, s["W"], util, max(checks, key=checks.get)))
        if util <= 1.0:
            return {"section": label, "utilization": util, "controls": max(checks, key=checks.get),
                    "rejected": rows[:-1]}
    return {"section": None, "rejected": rows}
