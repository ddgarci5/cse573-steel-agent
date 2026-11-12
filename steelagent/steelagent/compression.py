"""AISC 360-22 Chapter E: compression strength of doubly symmetric W-shapes (LRFD).

Implements E3 (flexural buckling) about both axes and E7 (members with slender
elements, effective-width method). Torsional buckling (E4) is not evaluated; per the
E4 user note it does not govern W-shapes when Lcz <= Lcy, which the MVP assumes.
"""
import math
from .materials import A992

PHI_C = 0.90

def fcr_e3(Fy, E, slenderness):
    """Critical stress, Section E3 (Eq. E3-2 / E3-3). slenderness = Lc/r."""
    if slenderness <= 0:
        return Fy, math.inf
    Fe = math.pi ** 2 * E / slenderness ** 2                       # E3-4
    if slenderness <= 4.71 * math.sqrt(E / Fy):                      # i.e. Fy/Fe <= 2.25
        return 0.658 ** (Fy / Fe) * Fy, Fe                         # E3-2
    return 0.877 * Fe, Fe                                          # E3-3

def _eff_width(b, lam, lam_r, Fy, Fcr, c1, c2):
    """Section E7.1 effective width of one slender element."""
    if lam <= lam_r * math.sqrt(Fy / Fcr):
        return b                                                   # E7-2
    Fel = (c2 * lam_r / lam) ** 2 * Fy                             # E7-5
    r = math.sqrt(Fel / Fcr)
    return b * (1 - c1 * r) * r                                    # E7-3

def compression_strength(shape, Lcx_ft, Lcy_ft, mat=A992):
    """Return dict with phi*Pn (kips), governing axis, Fcr, slenderness flags."""
    Fy, E = mat["Fy"], mat["E"]
    sx = Lcx_ft * 12 / shape["rx"]
    sy = Lcy_ft * 12 / shape["ry"]
    axis, s = ("x", sx) if sx >= sy else ("y", sy)
    Fcr, Fe = fcr_e3(Fy, E, s)

    # Table B4.1a width-to-thickness limits for axial compression
    lam_f, lam_w = shape["bf/2tf"], shape["h/tw"]
    lam_rf = 0.56 * math.sqrt(E / Fy)          # case 1: flanges of rolled I-shapes
    lam_rw = 1.49 * math.sqrt(E / Fy)          # case 5: webs of doubly symmetric I-shapes
    slender_f, slender_w = lam_f > lam_rf, lam_w > lam_rw

    Ag = shape["A"]
    Ae = Ag
    if slender_f or slender_w:
        tw, tf, bf = shape["tw"], shape["tf"], shape["bf"]
        h = lam_w * tw
        if slender_w:   # Table E7.1 case (a): stiffened elements, c1=0.18, c2=1.31
            he = _eff_width(h, lam_w, lam_rw, Fy, Fcr, 0.18, 1.31)
            Ae -= (h - he) * tw
        if slender_f:   # Table E7.1 case (c): all other elements, c1=0.22, c2=1.49
            b = bf / 2
            be = _eff_width(b, lam_f, lam_rf, Fy, Fcr, 0.22, 1.49)
            Ae -= 4 * (b - be) * tf
    Pn = Fcr * Ae
    return {
        "phiPn": PHI_C * Pn, "Pn": Pn, "Fcr": Fcr, "Fe": Fe, "governing_axis": axis,
        "KL_r": s, "KL_r_exceeds_200": s > 200, "slender_flange": slender_f,
        "slender_web": slender_w, "Ae": Ae, "provisions": ["E3", "E7"] if (slender_f or slender_w) else ["E3"],
    }
