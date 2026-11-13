"""Distill the validation printouts into summary statistics only (counts, mean / max error, within-1%), with NO AISC table values.

The raw printouts (results/validation_<ts>/validate_*.txt) list worst-case rows that include individual AISC Manual table values, so they
stay local (gitignored). This script reads them and writes results/validation_<ts>/validation_summary.json, which is safe to publish.

Usage (repo root): .venv/Scripts/python.exe eval/summarize_validation.py results/validation_20261112T000516Z
"""
import json, re, sys
from pathlib import Path


def _stdout(path):
    txt = Path(path).read_text(encoding="utf-8")
    return txt.split("--- stdout", 1)[1].split("--- stderr", 1)[0]


def _err_line(s):
    m = re.search(r"mean \|err\| ([\d.]+)%\s+max \|err\| ([\d.]+)%\s+within 1%: ([\d.]+)%(?:\s+within 2%: ([\d.]+)%)?", s)
    return {"mean_abs_err_pct": float(m.group(1)), "max_abs_err_pct": float(m.group(2)), "within_1pct_of_cases": float(m.group(3)),
            **({"within_2pct_of_cases": float(m.group(4))} if m.group(4) else {})}


def main(run_dir):
    d = Path(run_dir)
    out = {"source_run_dir": d.name, "note": "summary statistics only; per-case AISC Manual values are not reproduced",
           "meta": json.loads((d / "meta.json").read_text(encoding="utf-8"))}
    s = _stdout(d / "validate_compression.txt")
    m = re.search(r"cases: (\d+)\s+shapes: (\d+)\s+slender-shape cases: (\d+)", s)
    per_shape = dict(re.findall(r"^(W14X\d+)\s+([\d.]+)\s*$", s, flags=re.M))
    out["manual_table_4-1a_W14_phiPn"] = {"cases": int(m.group(1)), "shapes": int(m.group(2)), "slender_shape_cases": int(m.group(3)),
                                          **_err_line(s), "max_abs_err_pct_by_shape": {k: float(v) for k, v in per_shape.items()}}
    s = _stdout(d / "validate_flexure.txt")
    m = re.search(r"shapes: (\d+)\s+comparisons: (\d+)", s)
    by_q = {q: {"mean_abs_err_pct": float(a), "max_abs_err_pct": float(b)}
            for q, a, b in re.findall(r"^(BF|Lp|Lr|phiMp|phiMr|phiVn)\s+([\d.]+)\s+([\d.]+)\s*$", s, flags=re.M)}
    out["manual_table_3-2_flexure_shear"] = {"shapes": int(m.group(1)), "comparisons": int(m.group(2)), **_err_line(s), "by_quantity": by_q}
    s = _stdout(d / "validate_fcr.txt")
    m = re.search(r"cases (\d+)\s+Lc/r range (\d+)-(\d+)", s)
    out["manual_table_4-14_phiFcr"] = {"cases": int(m.group(1)), "Lc_r_range": [int(m.group(2)), int(m.group(3))], "steel_grades": 6, **_err_line(s)}
    (d / "validation_summary.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k.startswith("manual")}, indent=1)[:1500])
    print("wrote", d / "validation_summary.json")


if __name__ == "__main__":
    main(sys.argv[1])
