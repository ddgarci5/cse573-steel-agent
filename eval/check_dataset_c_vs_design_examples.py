"""Check that the Dataset C problem parameters and published answers match the AISC Design Examples v16.0 PDF.

Reads references/design-examples/P901-23W.pdf (gitignored, copyrighted; never committed) with poppler's pdftotext, looks at the printed pages of each
example, and for every item of datasets/C_benchmark/design_examples_*.json checks that each stored number occurs in that example's pages in the expected
form (the published LRFD answer as "<value> kips" or "<value> kip-ft" next to "phi", the parameters as the quantities the example states).
The output holds only booleans and the numbers already stored in our JSON; no PDF text is saved.

What this does NOT do: it does not apply or check the May 2, 2025 errata (the errata document is not in the repo, and this PDF is dated August 2023).
Usage (repo root):  .venv/Scripts/python.exe eval/check_dataset_c_vs_design_examples.py
Writes results/dataset_c_vs_design_examples_<ts>/check.json and check.txt
"""
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "references" / "design-examples" / "P901-23W.pdf"
C_DIR = ROOT / "datasets" / "C_benchmark"


def find_pdftotext():
    import shutil
    for p in [shutil.which("pdftotext")] + [str(x) for x in Path.home().glob("scoop/apps/poppler/current/**/pdftotext.exe")]:
        if p and "poppler" in subprocess.run([p, "-v"], capture_output=True, text=True).stderr.lower():
            return p
    sys.exit("poppler pdftotext not found")


def load_pages():
    out = subprocess.run([find_pdftotext(), str(PDF), "-"], capture_output=True).stdout.decode("utf-8", "replace")
    return [re.sub(r"\s+", " ", p) for p in out.split("\f")]


def example_text(pages, start_pat, end_pat):
    """Concatenate pages from the page whose text starts the example (heading line) to the page before the next example heading."""
    start = next(i for i, p in enumerate(pages) if i > 30 and re.search(start_pat, p[:300]))
    end = next((i for i in range(start + 1, len(pages)) if re.search(end_pat, pages[i][:300])), start + 3)
    end = min(end, start + 4)          # an example never spans more than 4 pages here; stops a long range from matching unrelated text
    return " ".join(pages[start:end]), (start + 1, end)


def has(text, pattern):
    return re.search(pattern, text) is not None


def num(x):
    return re.escape(f"{x:g}") if isinstance(x, (int, float)) else re.escape(str(x))


# example id -> (heading pattern, next heading pattern)
EXAMPLES = {
    "D.1": (r"EXAMPLE D\.1 ", r"EXAMPLE D\.2"),
    "E.1A": (r"EXAMPLE E\.1A ", r"EXAMPLE E\.1B"),
    "E.1C": (r"EXAMPLE E\.1C ", r"EXAMPLE E\.1D"),
    "E.1D": (r"EXAMPLE E\.1D ", r"EXAMPLE E\.2"),
    "F.1-1A": (r"EXAMPLE F\.1-1A ", r"EXAMPLE F\.1-1B"),
    "F.1-1B": (r"EXAMPLE F\.1-1B ", r"EXAMPLE F\.1-2A"),
    "F.1-2B": (r"EXAMPLE F\.1-2B ", r"EXAMPLE F\.1-3A"),
    "F.1-3B": (r"EXAMPLE F\.1-3B ", r"EXAMPLE F\.2"),
    "F.3A": (r"EXAMPLE F\.3A ", r"EXAMPLE F\.3B"),
    "F.3B": (r"EXAMPLE F\.3B ", r"EXAMPLE F\.4"),
    "F.4": (r"EXAMPLE F\.4 ", r"EXAMPLE F\.5"),
    "G.1B": (r"EXAMPLE G\.1B ", r"EXAMPLE G\.2"),
}


def main():
    pages = load_pages()
    strength = {c["id"]: c for c in json.loads((C_DIR / "design_examples_strength.json").read_text(encoding="utf-8"))["cases"]}
    selection = {c["id"]: c for c in json.loads((C_DIR / "design_examples_selection.json").read_text(encoding="utf-8"))["cases"]}
    results, lines = [], []

    def check(pid, ex, what, ok, expected):
        results.append({"id": pid, "example": ex, "check": what, "expected": expected, "found_in_pdf": bool(ok)})
        lines.append(f"{'OK  ' if ok else 'FAIL'} {pid:12} {what:42} expected {expected}")

    texts = {k: example_text(pages, *v) for k, v in EXAMPLES.items()}
    for k, (_, pr) in texts.items():
        lines.append(f"example {k}: PDF pages {pr[0]}-{pr[1]}")

    def phi_answer(text, value, unit):
        # LRFD column prints "phi Pn = <value> kips" (or "phi b Mn = ... kip-ft"); allow the symbol glyphs the text layer produces
        return has(text, rf"{num(value)}\s*{unit}\s*>\s*\d")

    for pid, c in strength.items():
        ex = {"D.1-yield": "D.1", "D.1-rupture": "D.1"}.get(pid, pid)
        t, _ = texts[ex]
        pub, i = c["published"], c["inputs"]
        check(pid, ex, "shape " + c["shape"], has(t, re.escape(c["shape"].replace("X", "×")) + "|" + re.escape(c["shape"].replace("X", "x"))), c["shape"])
        ok_pub = has(t, rf"1\.00 \( {num(pub['value'])} kips \)") if c["check"] == "shear" else phi_answer(t, pub["value"], "kip-ft" if pub["unit"] == "kip-ft" else "kips")
        check(pid, ex, f"published {pub['quantity']} (LRFD)", ok_pub, f"{pub['value']} {pub['unit']}")
        if pid == "D.1-rupture":
            check(pid, ex, "An (in^2)", has(t, rf"= {num(i['An_in2'])} in"), i["An_in2"])
            check(pid, ex, "U", has(t, rf"= {num(i['U'])} "), i["U"])
        if pid in ("E.1C", "E.1D"):
            check(pid, ex, "effective length x (ft)", has(t, rf"{num(i['Lcx_ft'])}(\.0)? ft"), i["Lcx_ft"])
            check(pid, ex, "effective length y (ft)", has(t, rf"{num(i['Lcy_ft'])}(\.0)? ft"), i["Lcy_ft"])
        if pid == "F.1-2B":
            check(pid, ex, "Cb", has(t, rf"= {num(i['Cb'])} "), i["Cb"])
            check(pid, ex, "Lb = 11.7 ft in the PDF (ours 35/3 = 11.667)", has(t, r"Lb = 11\.7 ft") and abs(i["Lb_ft"] - 35 / 3) < 1e-9, round(i["Lb_ft"], 4))
        if pid == "F.1-3B":
            check(pid, ex, "Cb", has(t, rf"= {num(i['Cb'])}0* "), i["Cb"])
            check(pid, ex, "Lb (ft)", has(t, rf"Lb = {num(i['Lb_ft'])} ft"), i["Lb_ft"])
        if pid == "F.1-1B":
            check(pid, ex, "continuously braced", has(t, r"continuously braced"), "Lb = 0")
        if pid == "F.3B":
            check(pid, ex, "continuously braced", has(t, r"continuously braced") or has(pages[texts["F.3A"][1][0] - 1], r"continuously braced"), "Lb = 0")
    for pid, c in selection.items():
        t, _ = texts[pid]
        d, g, k, sec = c["demands"], c["geometry"], c["constraints"], c["published"]["section"]
        check(pid, pid, "published section " + sec, has(t, re.escape(sec.replace("X", "×")) + "|" + re.escape(sec.replace("X", "x"))), sec)
        if "Pu_kip" in d:
            check(pid, pid, "Pu (kip)", has(t, rf"Pu = .{{0,80}}?= {num(d['Pu_kip'])} kips"), d["Pu_kip"])
            check(pid, pid, "effective length (ft)", has(t, rf"= {num(g['Lcx_ft'])}(\.0)? ft"), g["Lcx_ft"])
            check(pid, pid, "nominal depth 14 in.", has(t, r"nominal 14 in\."), k["nominal_depth_in"])
        else:
            check(pid, pid, "Mu (kip-ft)", has(t, rf"= {num(d['Mu_kipft'])} kip-ft"), d["Mu_kipft"])
            check(pid, pid, "continuously braced (Lb = 0)", has(t, r"continuously braced"), g["Lb_ft"])
        if "Ix_min_in4" in k:
            ix = f"{k['Ix_min_in4']:,}"
            check(pid, pid, "Ix required (in^4)", has(t, rf"{re.escape(ix)}|{num(k['Ix_min_in4'])}\s*in\.\s*4|{re.escape(ix.replace(',', ', '))}"), k["Ix_min_in4"])
        if "max_depth_in" in k:
            check(pid, pid, "maximum nominal depth (in.)", has(t, rf"maximum nominal depth of {num(k['max_depth_in'])} in"), k["max_depth_in"])
    n_ok = sum(r["found_in_pdf"] for r in results)
    lines.append(f"{n_ok} of {len(results)} checks found in the PDF")
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    od = ROOT / "results" / f"dataset_c_vs_design_examples_{stamp}"
    od.mkdir(parents=True)
    meta = {"pdf": PDF.name, "pdf_bytes": PDF.stat().st_size, "errata_applied_or_checked": False,
            "note": "booleans and our own stored numbers only; no PDF text; the May 2, 2025 errata are not checked here",
            "n_checks": len(results), "n_found": n_ok}
    (od / "check.json").write_text(json.dumps({**meta, "checks": results}, indent=2), encoding="utf-8")
    (od / "check.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print("saved to", od)


if __name__ == "__main__":
    main()
