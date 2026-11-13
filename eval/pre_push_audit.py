"""Pre-push audit of everything that is not on GitHub yet (default range: origin/main..HEAD, plus the current working tree).

Prints only counts and file names, never secret values. Exit code 1 if a hard problem is found.
Checks:
  1. forbidden paths or file types in the tree and in the range (.env, references/, .venv/, models, PDFs, xlsx, zip, pptx, docx, parquet, gguf, *_results.csv)
  2. API key values parsed from .env (the way eval/system_c_pilot.py parses it) appear in no file of the range or the working tree
  3. personal strings and local paths: Windows or macOS home paths, OneDrive, e-mail domain, and the current OS user name (read at run time,
     so this script contains no personal string itself). Hits are listed for review; a placeholder like <user> in prose is expected.
  4. no line of 30+ characters from the copyrighted material in references/ (PDFs via pdftotext, PowerPoint text) occurs in a text file of the range
     (skipped with a warning if references/ or pdftotext is missing)
Usage (repo root):  .venv/Scripts/python.exe eval/pre_push_audit.py [--base origin/main]
"""
import argparse
import getpass
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git(*a, binary=False):
    r = subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True)
    return r.stdout if binary else r.stdout.decode("utf-8", "replace")


def norm(s):
    return re.sub(r"\s+", " ", s).strip().lower()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="origin/main")
    a = ap.parse_args()
    problems = 0
    commits = git("rev-list", f"{a.base}..HEAD").split()
    objs = [l.split(" ", 1) for l in git("rev-list", "--objects", f"{a.base}..HEAD").splitlines() if " " in l]
    blobs = [(oid, p) for oid, p in objs if git("cat-file", "-t", oid).strip() == "blob"]
    print(f"range {a.base}..HEAD: {len(commits)} commit(s), {len(blobs)} blob(s); git status: {git('status', '--short').strip() or 'clean'}")

    forbid = re.compile(r"(^|/)(\.env|references/|\.venv/|models/)|\.(pdf|xlsx|zip|pptx|potx|docx|parquet|gguf)$|_results\.csv$", re.I)
    bad = sorted({p for p in git("ls-files").splitlines() if forbid.search(p)} | {p for _, p in blobs if forbid.search(p)})
    print("forbidden paths tracked or in range:", bad or "none")
    problems += bool(bad)

    texts = {(oid, p): git("cat-file", "-p", oid, binary=True).decode("utf-8", "replace") for oid, p in blobs}
    secrets = {}
    envf = ROOT / ".env"
    if envf.exists():
        for line in envf.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if "KEY" in k.upper() and len(v.strip().strip("\"'")) >= 8:
                    secrets[k.strip()] = v.strip().strip("\"'")
    print("secret values loaded from .env (names only):", sorted(secrets) or "none (.env missing or no key)")
    hits = sorted({p for (_, p), t in texts.items() for v in secrets.values() if v in t})
    wt = []
    for p in ROOT.rglob("*"):
        if p.is_file() and not {".venv", ".git", "references"} & set(p.parts) and p.suffix in (".json", ".txt", ".md", ".csv", ".py", ".yml", ".toml", ".ini"):
            txt = p.read_text(encoding="utf-8", errors="replace")
            if any(v in txt for v in secrets.values()):
                wt.append(str(p.relative_to(ROOT)))
    print("files in the range containing an API key value:", hits or "none", "| working-tree files:", wt or "none")
    problems += bool(hits or wt)

    user = re.escape(getpass.getuser())
    pats = {"windows/mac home path": re.compile(r"C:\\\\?Users|/Users/[A-Za-z]|/c/Users", re.I), "OneDrive": re.compile(r"OneDrive", re.I),
            "e-mail domain": re.compile(r"@[A-Za-z0-9.-]*\.edu\b", re.I), "current OS user name": re.compile(rf"\b{user}\b", re.I)}
    for name, rx in pats.items():
        f = sorted({p for (_, p), t in texts.items() if rx.search(t)})
        print(f"{name}: {f or 'none'}  (review each hit; prose placeholders such as <user> are expected)")

    ref = ROOT / "references"
    pdftotext = None
    for c in [shutil.which("pdftotext")] + [str(x) for x in Path.home().glob("scoop/apps/poppler/current/**/pdftotext.exe")]:
        if c and "poppler" in subprocess.run([c, "-v"], capture_output=True, text=True).stderr.lower():
            pdftotext = c
            break
    if not ref.exists() or pdftotext is None:
        print("WARNING: reference-overlap check skipped (references/ or poppler pdftotext not available)")
    else:
        lines = set()
        for pdf in ref.rglob("*.pdf"):
            out = subprocess.run([pdftotext, "-layout", str(pdf), "-"], capture_output=True).stdout.decode("utf-8", "replace")
            lines |= {norm(l) for l in out.splitlines() if len(norm(l)) >= 30}
        for pp in list(ref.rglob("*.pptx")):
            try:
                z = zipfile.ZipFile(pp)
            except zipfile.BadZipFile:
                continue
            with z:
                for n in z.namelist():
                    if n.startswith("ppt/slides/slide") and n.endswith(".xml"):
                        lines |= {norm(m) for m in re.findall(r"<a:t>([^<]*)</a:t>", z.read(n).decode("utf-8", "replace")) if len(norm(m)) >= 30}
        overlap = {}
        for (_, p), t in texts.items():
            if p.endswith(".png"):
                continue
            blob = norm(t)
            n = sum(1 for l in lines if l in blob)
            if n:
                overlap[p] = n
        print(f"reference lines indexed: {len(lines)}; files with a >=30-character line identical to reference material:", overlap or "none")
        problems += bool(overlap)
    print("AUDIT RESULT:", "PROBLEMS FOUND (see above)" if problems else "no hard problems")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
