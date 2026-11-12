"""Dataset B generator: synthetic design cases x all 289 W-shapes, labeled by the validated deterministic solver (System A).

Every label (capacity, utilization, pass/fail, governing limit state, lightest passing weight) comes from steelagent/ functions;
nothing here computes a structural number itself. Dataset C (AISC examples) is never touched.

Sampling (see CLAUDE.md section 6):
  - Each case draws an "anchor" section and a target utilization u; the demand is u * (anchor capacity). u is 0.9-1.1 with
    probability 0.6 (oversampling the pass/fail boundary), else log-uniform in [0.3, 2.5].
  - In-range cases: effective / unbraced lengths <= 30 ft, split by case 70/15/15 into train/val/test.
  - Out-of-range ("ood") cases: at least one length in (30, 45] ft. Never used for training.
Scope: compression = E3 (+E7 slender); flexure = F2/F3 major-axis moment + G2.1 shear. LRFD, A992, rolled W-shapes.
Passing means every check above is <= 1.0. KL/r > 200 is recorded but not a failure (System A's search ignores it too).

Usage (from repo root):  .venv/Scripts/python.exe ml/dataset_b.py --members compression flexure --n 10000 --n-ood 2000
"""
import argparse, datetime, json, subprocess, sys, time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "steelagent"))
from steelagent import shapes                                   # noqa: E402
from steelagent.compression import compression_strength          # noqa: E402
from steelagent.flexure import flexure_strength, shear_strength  # noqa: E402

SEED = 573
L_IN_MAX, L_OOD_MAX = 30.0, 45.0
OUT_DIR = ROOT / "datasets" / "B_synthetic"


def sections():
    """W-shapes sorted by (weight, label): the position in this list is `sec_idx`. Returns (DataFrame, list of dicts)."""
    df = shapes.w_shapes().reset_index().sort_values(["W", "label"], kind="mergesort").reset_index(drop=True)
    return df, [dict(r) for r in df.to_dict("records")]


def _half_ft(x):
    return np.round(x * 2) / 2


def _target_util(rng, n):
    near = rng.random(n) < 0.6
    return np.where(near, rng.uniform(0.9, 1.1, n), np.exp(rng.uniform(np.log(0.3), np.log(2.5), n)))


# ---------------------------------------------------------------- compression
def _comp_eval(s, Lcx, Lcy):
    r = compression_strength(s, Lcx, Lcy)
    gov = f"{'E7' if (r['slender_flange'] or r['slender_web']) else 'E3'}_{r['governing_axis']}"
    return r["phiPn"], gov, r["KL_r_exceeds_200"]


def _comp_cases(rng, n, ood, secs):
    if ood:
        lx, ly = rng.uniform(3, L_OOD_MAX, n), rng.uniform(3, L_OOD_MAX, n)
        pick = rng.random(n) < 0.5
        big = rng.uniform(L_IN_MAX + 0.5, L_OOD_MAX, n)
        lx, ly = np.where(pick, big, lx), np.where(pick, ly, big)
    else:
        lx, ly = rng.uniform(3, L_IN_MAX, n), rng.uniform(3, L_IN_MAX, n)
    lx, ly = _half_ft(lx), _half_ft(ly)
    anchor, u = rng.integers(0, len(secs), n), _target_util(rng, n)
    Pu = np.array([u[i] * _comp_eval(secs[anchor[i]], lx[i], ly[i])[0] for i in range(n)])
    return pd.DataFrame({"Pu_kip": Pu, "Lcx_ft": lx, "Lcy_ft": ly, "anchor_idx": anchor, "target_util": u})


def _comp_rows(case, secs):
    n = len(secs)
    cap, util, gov, kl = np.empty(n), np.empty(n), [], np.empty(n, bool)
    for j, s in enumerate(secs):
        cap[j], g, kl[j] = _comp_eval(s, case.Lcx_ft, case.Lcy_ft)
        gov.append(g)
    util = case.Pu_kip / cap
    return {"cap": cap, "util": util, "gov": gov, "kl_r_gt_200": kl}


# ---------------------------------------------------------------- flexure
def _flex_eval(s, Lb, Cb):
    f = flexure_strength(s, Lb, Cb)
    return f["phiMn"], {"yielding": "F2_yielding", "LTB": "F2_LTB", "FLB": "F3_FLB"}[f["governing"]]


def _flex_cases(rng, n, ood, secs):
    if ood:
        Lb = rng.uniform(L_IN_MAX + 0.5, L_OOD_MAX, n)
    else:
        Lb = np.where(rng.random(n) < 0.15, 0.0, rng.uniform(1, L_IN_MAX, n))
    Lb = _half_ft(Lb)
    Cb = np.where(rng.random(n) < 0.4, 1.0, np.round(rng.uniform(1.0, 2.3, n), 2))
    anchor, u, v = rng.integers(0, len(secs), n), _target_util(rng, n), rng.uniform(0.05, 1.1, n)
    Mu = np.array([u[i] * _flex_eval(secs[anchor[i]], Lb[i], Cb[i])[0] for i in range(n)])
    Vu = np.array([v[i] * shear_strength(secs[anchor[i]])["phiVn"] for i in range(n)])
    return pd.DataFrame({"Mu_kipft": Mu, "Vu_kip": Vu, "Lb_ft": Lb, "Cb": Cb, "anchor_idx": anchor,
                         "target_util": u, "target_util_shear": v})


def _flex_rows(case, secs, phiVn):
    n = len(secs)
    cap, gov = np.empty(n), []
    for j, s in enumerate(secs):
        cap[j], g = _flex_eval(s, case.Lb_ft, case.Cb)
        gov.append(g)
    uf, us = case.Mu_kipft / cap, case.Vu_kip / phiVn
    gov = [g if a >= b else "G2.1_shear" for g, a, b in zip(gov, uf, us)]
    return {"cap": cap, "util": np.maximum(uf, us), "gov": gov, "util_flex": uf, "util_shear": us}


# ---------------------------------------------------------------- driver
def generate(member, n_in, n_ood, seed=SEED):
    """Return (cases_df, rows_df). rows_df has one row per (case, section)."""
    rng = np.random.default_rng([seed, {"compression": 1, "flexure": 2}[member]])
    _, secs = sections()
    gen = {"compression": _comp_cases, "flexure": _flex_cases}[member]
    cases = pd.concat([gen(rng, n_in, False, secs), gen(rng, n_ood, True, secs)], ignore_index=True)
    split = np.full(len(cases), "ood", dtype=object)
    perm = rng.permutation(n_in)
    split[perm[: int(0.70 * n_in)]] = "train"
    split[perm[int(0.70 * n_in): int(0.85 * n_in)]] = "val"
    split[perm[int(0.85 * n_in): n_in]] = "test"
    cases.insert(0, "case_id", np.arange(len(cases), dtype=np.int32))
    cases.insert(1, "member_type", member)
    cases.insert(2, "split", split)

    phiVn = np.array([shear_strength(s)["phiVn"] for s in secs])
    nsec = len(secs)
    blocks, n_pass, light_w, light_idx = [], np.zeros(len(cases), np.int16), np.full(len(cases), np.nan), np.full(len(cases), -1, np.int16)
    for c in cases.itertuples(index=False):
        r = _comp_rows(c, secs) if member == "compression" else _flex_rows(c, secs, phiVn)
        passed = r["util"] <= 1.0
        n_pass[c.case_id] = passed.sum()
        if passed.any():
            k = int(np.argmax(passed))                     # sections are weight-sorted
            light_idx[c.case_id], light_w[c.case_id] = k, secs[k]["W"]
        blocks.append({"case_id": np.full(nsec, c.case_id, np.int32), "sec_idx": np.arange(nsec, dtype=np.int16),
                       "passed": passed, **{k: (np.asarray(v, dtype=np.float32) if k in ("cap", "util", "util_flex", "util_shear") else v)
                                            for k, v in r.items()}})
    cases["n_pass"], cases["lightest_weight"], cases["lightest_idx"] = n_pass, light_w, light_idx
    rows = pd.concat([pd.DataFrame(b) for b in blocks], ignore_index=True)
    rows["gov"] = rows["gov"].astype("category")
    return cases, rows


def _git_hash():
    r = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--members", nargs="+", default=["compression", "flexure"], choices=["compression", "flexure"])
    ap.add_argument("--n", type=int, default=10_000, help="in-range cases per member type")
    ap.add_argument("--n-ood", type=int, default=2_000, help="out-of-range cases per member type")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    a = ap.parse_args()
    a.out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    manifest = {"timestamp_utc": stamp, "git_hash": _git_hash(), "seed": a.seed, "n_in_range": a.n, "n_ood": a.n_ood,
                "n_sections": len(sections()[1]), "members": {}}
    for m in a.members:
        t0 = time.time()
        cases, rows = generate(m, a.n, a.n_ood, a.seed)
        cases.to_parquet(a.out_dir / f"B_{m}_cases.parquet", index=False)
        rows.to_parquet(a.out_dir / f"B_{m}_rows.parquet", index=False)
        band = rows.util.between(0.9, 1.1)
        manifest["members"][m] = {
            "cases": int(len(cases)), "rows": int(len(rows)), "split_counts": cases.split.value_counts().to_dict(),
            "pass_rate_rows": float(rows.passed.mean()), "frac_rows_util_0.9_1.1": float(band.mean()),
            "cases_with_no_passing_section": int((cases.n_pass == 0).sum()),
            "governing_limit_state_rows": rows.gov.value_counts().to_dict(),
            "seconds": round(time.time() - t0, 1)}
        print(m, json.dumps(manifest["members"][m], indent=1))
    res = ROOT / "results" / f"dataset_b_{stamp}"
    res.mkdir(parents=True, exist_ok=True)
    (res / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("manifest:", res / "manifest.json")
