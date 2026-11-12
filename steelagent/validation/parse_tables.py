"""Parse AISC Manual design-table excerpts (internal validation only; not redistributed)."""
import os, re, subprocess
from pathlib import Path

TABLES = Path(__file__).resolve().parents[2] / "references" / "aisc-sample-tables"
NUM = r"\d+(?:\.\d+)?"
_POPPLER = None

def _poppler():
    """Path of the first poppler pdftotext on PATH (or $POPPLER_PDFTOTEXT). The regexes below were written against
    poppler's -layout output; xpdf (bundled with Git for Windows) lays Table 3-2 out differently and the parsers
    then fail or return wrong numbers without raising, so non-poppler builds are skipped."""
    global _POPPLER
    if _POPPLER:
        return _POPPLER
    cands = [os.environ["POPPLER_PDFTOTEXT"]] if os.environ.get("POPPLER_PDFTOTEXT") else []
    for d in os.environ.get("PATH", "").split(os.pathsep):
        for name in ("pdftotext.exe", "pdftotext"):
            if (Path(d) / name).is_file():
                cands.append(str(Path(d) / name))
    found = []
    for c in cands:
        v = subprocess.run([c, "-v"], capture_output=True, text=True, encoding="utf-8", errors="replace")
        out = (v.stdout + v.stderr)
        if "poppler" in out.lower():
            _POPPLER = c
            return c
        found.append(out.strip().splitlines()[0] if out.strip() else c)
    raise RuntimeError("parse_tables.py needs poppler's pdftotext (e.g. `scoop install poppler`); found: " + "; ".join(found or ["none"]))

def _text(pdf, page=None):
    args = [_poppler(), "-layout"] + (["-f", str(page), "-l", str(page)] if page else []) + [str(pdf), "-"]
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8").stdout

def table_4_1a():
    """Return list of (shape, Lc_ft, phiPn_LRFD) from Table 4-1a pages."""
    rows = []
    pdf = TABLES / "Table 4-1_pp16-17.pdf"
    for page in (1, 2):
        lines = _text(pdf, page).splitlines()
        hdr = next(l for l in lines if "lb/ft" in l)
        weights = re.findall(r"(\d+)(?:\[c\])?", hdr.split("lb/ft")[1])
        shapes = [f"W14X{w}" for w in weights]
        for l in lines:
            m = re.match(rf"^\s+(\d+)\s+({NUM}(?:\s+{NUM})+)\s*$", l)
            if not m:
                continue
            Lc = int(m.group(1)); vals = [float(v) for v in m.group(2).split()]
            if len(vals) % 2 or len(vals) // 2 > len(shapes):
                continue
            for i in range(len(vals) // 2):        # pairs: ASD, LRFD (left-to-right)
                rows.append((shapes[i], Lc, vals[2 * i + 1]))
    return rows

def table_3_2():
    """Return list of dicts for each W-shape row of Table 3-2 (LRFD columns)."""
    out, pending = [], None
    for page in (1, 2):
        for l in _text(TABLES / "Table 3-2_pp24-25.pdf", page).splitlines():
            m0 = re.match(r"^\s*×(\d+)(\[[fv]\])?\s*$", l)
            if m0:
                pending = (m0.group(1), m0.group(2) or ""); continue
            m = re.match(rf"^\s*W(\d+)×(\d+)?(\[[fv]\])?\s+((?:{NUM}\s+){{11}}{NUM})\s*$", l)
            if not m:
                continue
            w = m.group(2) or (pending[0] if pending else None)
            note = m.group(3) or ("" if m.group(2) else (pending[1] if pending else ""))
            pending = None
            v = [float(x) for x in m.group(4).split()]
            out.append({"shape": f"W{m.group(1)}X{w}", "note": note, "Zx": v[0], "phiMp": v[2],
                        "phiMr": v[4], "BF": v[6], "Lp": v[7], "Lr": v[8], "Ix": v[9], "phiVn": v[11]})
    seen, uniq = set(), []
    for r in out:                               # footnote area repeats a few rows
        if r["shape"] not in seen:
            seen.add(r["shape"]); uniq.append(r)
    return uniq

def table_4_14():
    """Return list of (Fy, Lc_r, phiFcr_LRFD) for all six Fy columns."""
    FYS = [35, 36, 46, 50, 65, 70]
    out = []
    for l in _text(TABLES / "Table 4-14_pp228-232.pdf").splitlines():
        m = re.match(rf"^\s+(\d+)\s+((?:{NUM}\s+){{11}}{NUM})\s*$", l)
        if m:
            v = [float(x) for x in m.group(2).split()]
            out += [(fy, int(m.group(1)), v[2 * i + 1]) for i, fy in enumerate(FYS)]
    return out
