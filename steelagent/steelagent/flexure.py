"""AISC 360-22 Chapters F and G: major-axis flexure and shear of W-shapes (LRFD).

F2 (compact flanges/web: yielding + lateral-torsional buckling), F3 (noncompact or
slender flanges, compact web: adds flange local buckling), G2.1 (shear, unstiffened web).
Sections with noncompact webs (F4/F5) are flagged as out of MVP scope.
"""
import math
from .materials import A992

PHI_B = 0.90

def flexure_strength(shape, Lb_ft, Cb=1.0, mat=A992):
    Fy, E = mat["Fy"], mat["E"]
    Zx, Sx, ry, rts, J, ho = (shape[k] for k in ("Zx", "Sx", "ry", "rts", "J", "ho"))
    Mp = Fy * Zx                                   # F2-1 (kip-in)
    Mr = 0.7 * Fy * Sx
    lam_f, lam_w = shape["bf/2tf"], shape["h/tw"]
    lam_pf, lam_rf = 0.38 * math.sqrt(E / Fy), 1.0 * math.sqrt(E / Fy)   # Table B4.1b case 10
    lam_pw = 3.76 * math.sqrt(E / Fy)                                      # case 15
    web_compact = lam_w <= lam_pw

    Lp = 1.76 * ry * math.sqrt(E / Fy)             # F2-5 (in)
    c = 1.0
    jc = J * c / (Sx * ho)
    Lr = 1.95 * rts * E / (0.7 * Fy) * math.sqrt(jc + math.sqrt(jc ** 2 + 6.76 * (0.7 * Fy / E) ** 2))  # F2-6
    Lb = Lb_ft * 12

    # Lateral-torsional buckling, F2-2 / F2-3
    if Lb <= Lp:
        Mn_ltb = Mp
    elif Lb <= Lr:
        Mn_ltb = min(Cb * (Mp - (Mp - Mr) * (Lb - Lp) / (Lr - Lp)), Mp)
    else:
        Fcr = Cb * math.pi ** 2 * E / (Lb / rts) ** 2 * math.sqrt(1 + 0.078 * jc * (Lb / rts) ** 2)  # F2-4
        Mn_ltb = min(Fcr * Sx, Mp)

    # Flange local buckling, F3-1 / F3-2
    if lam_f <= lam_pf:
        Mn_flb, flange = Mp, "compact"
    elif lam_f <= lam_rf:
        Mn_flb, flange = Mp - (Mp - Mr) * (lam_f - lam_pf) / (lam_rf - lam_pf), "noncompact"
    else:
        kc = min(max(4 / math.sqrt(lam_w), 0.35), 0.76)
        Mn_flb, flange = 0.9 * E * kc * Sx / lam_f ** 2, "slender"

    states = {"yielding": Mp, "LTB": Mn_ltb, "FLB": Mn_flb}
    gov = min(states, key=states.get)
    Mn = states[gov]
    # Lp' : unbraced length where LTB strength equals the FLB-limited strength (Manual Table 3-2)
    Lp_eff = Lp + (Lr - Lp) * (Mp - Mn_flb) / (Mp - Mr) if Mn_flb < Mp else Lp
    return {
        "phiMn": PHI_B * Mn / 12, "Mn_kipft": Mn / 12, "governing": gov,
        "phiMp": PHI_B * Mp / 12, "phiMr": PHI_B * Mr / 12, "phiMn_flb": PHI_B * Mn_flb / 12,
        "Lp_ft": Lp / 12, "Lp_eff_ft": Lp_eff / 12, "Lr_ft": Lr / 12,
        "BF": PHI_B * (Mn_flb - Mr) / 12 / ((Lr - Lp_eff) / 12),
        "flange": flange, "web_compact": web_compact,
        "provisions": ["F2", "F3"] if flange != "compact" else ["F2"],
    }

def shear_strength(shape, mat=A992):
    """Section G2.1, rolled I-shape, unstiffened web (kv = 5.34)."""
    Fy, E = mat["Fy"], mat["E"]
    Aw = shape["d"] * shape["tw"]
    htw = shape["h/tw"]
    if htw <= 2.24 * math.sqrt(E / Fy):            # G2.1(a)
        phi, Cv1 = 1.00, 1.0
    else:                                          # G2.1(b)(1)
        phi, kv = 0.90, 5.34
        lim = 1.10 * math.sqrt(kv * E / Fy)
        Cv1 = 1.0 if htw <= lim else lim / htw
    Vn = 0.6 * Fy * Aw * Cv1                       # G2-1
    return {"phiVn": phi * Vn, "Vn": Vn, "phi_v": phi, "Cv1": Cv1, "provisions": ["G2.1"]}
