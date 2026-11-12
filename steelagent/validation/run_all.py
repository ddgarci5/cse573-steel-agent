"""Run every validation script and pytest, saving outputs to results/validation_<UTC timestamp>/ (CLAUDE.md rule 7).

Usage (from steelagent/):  ../.venv/Scripts/python.exe validation/run_all.py
Each script's stdout/stderr and return code is saved even when it fails; failures are never hidden."""
import datetime, json, os, platform, subprocess, sys
from importlib.metadata import version
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent          # steelagent/
REPO = PKG.parent
stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
out = REPO / "results" / f"validation_{stamp}"
out.mkdir(parents=True)

def git(*args):
    r = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None

env = {**os.environ, "STEELAGENT_OUT": str(out), "PYTHONIOENCODING": "utf-8"}
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from parse_tables import _poppler
    _p = _poppler()
    _v = subprocess.run([_p, "-v"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    pdftotext = f"{_p} :: " + (_v.stderr or _v.stdout).strip().splitlines()[0]
except Exception as e:  # recorded, not hidden: the table validations will then fail too
    pdftotext = f"no poppler: {e}"
meta = {
    "timestamp_utc": stamp, "git_hash": git("rev-parse", "HEAD"), "git_dirty": bool(git("status", "--porcelain")),
    "python": platform.python_version(), "platform": platform.platform(),
    "packages": {p: version(p) for p in ("numpy", "pandas", "openpyxl", "matplotlib", "pytest")},
    "pdftotext": pdftotext,
    "runs": {},
}
jobs = {
    "dataset_c_pilot": [sys.executable, "-I", "validation/dataset_c_pilot.py"],
    "rescore_shipped_csv": [sys.executable, "-I", "validation/rescore_shipped_csv.py"],
    "pytest": [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
    "validate_compression": [sys.executable, "-I", "validation/validate_compression.py"],
    "validate_flexure": [sys.executable, "-I", "validation/validate_flexure.py"],
    "validate_fcr": [sys.executable, "-I", "validation/validate_fcr.py"],
}
for name, cmd in jobs.items():
    r = subprocess.run(cmd, cwd=PKG, env=env, capture_output=True, text=True, encoding="utf-8")
    (out / f"{name}.txt").write_text(f"$ {' '.join(cmd)}\nreturncode: {r.returncode}\n\n--- stdout\n{r.stdout}\n--- stderr\n{r.stderr}", encoding="utf-8")
    meta["runs"][name] = r.returncode
    print(f"{name:24} returncode {r.returncode}")
(out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
print("saved to", out)
