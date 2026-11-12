"""System B quick baseline: Decision Tree and HistGradientBoosting on Dataset B (compression + flexure).

Tasks
  1. Row-level pass/fail classification (case x section), scored on in-range test cases and on the out-of-range (ood) cases.
  2. Shortlist: the k lightest sections with predicted P(pass) >= theta (theta picked on the val split); System A re-checks the
     shortlist in weight order. Top-k recall = the true lightest passing WEIGHT is reachable inside the shortlist.
  3. Diagnostic: case-level HGB regression of log(lightest passing weight).
Features are case inputs, section properties, and simple ratios (e.g. Lb/ry). No solver output (capacities, Lp, Lr) is a feature.
The ML model only proposes; a section is "recommended" only after the solver re-check passes (CLAUDE.md rule 2).

Usage (repo root):  .venv/Scripts/python.exe ml/system_b_baseline.py
"""
import datetime, json, subprocess, sys, time
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, r2_score
from sklearn.tree import DecisionTreeClassifier

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dataset_b as D  # noqa: E402

SEED = 573
KS = [1, 2, 3, 5, 10, 15, 20]
THETAS = [0.02, 0.05, 0.1, 0.2, 0.3, 0.5]
SEC_COLS = {"compression": ["W", "A", "d", "bf", "tw", "tf", "rx", "ry", "bf/2tf", "h/tw"],
            "flexure": ["W", "A", "d", "bf", "tw", "tf", "Zx", "Sx", "ry", "rts", "J", "ho", "bf/2tf", "h/tw"]}
CASE_COLS = {"compression": ["Pu_kip", "Lcx_ft", "Lcy_ft"], "flexure": ["Mu_kipft", "Vu_kip", "Lb_ft", "Cb"]}


def features(member, cases, rows, secs):
    """Return (feature DataFrame aligned to rows, per-row arrays). Ratios in in./ksi units."""
    cid, sid = rows.case_id.to_numpy(), rows.sec_idx.to_numpy()
    f = {}
    for c in CASE_COLS[member]:
        f[c] = cases[c].to_numpy(np.float32)[cid]
    for c in SEC_COLS[member]:
        f[c] = secs[c].to_numpy(np.float32)[sid]
    if member == "compression":
        f["Lcx/rx"] = f["Lcx_ft"] * 12 / f["rx"]
        f["Lcy/ry"] = f["Lcy_ft"] * 12 / f["ry"]
        f["KLr_max"] = np.maximum(f["Lcx/rx"], f["Lcy/ry"])
        f["Pu/A"] = f["Pu_kip"] / f["A"]
    else:
        f["Lb/ry"] = f["Lb_ft"] * 12 / f["ry"]
        f["Lb/rts"] = f["Lb_ft"] * 12 / f["rts"]
        f["Mu/Zx"] = f["Mu_kipft"] * 12 / f["Zx"]
        f["Mu/Sx"] = f["Mu_kipft"] * 12 / f["Sx"]
        f["Vu/Aw"] = f["Vu_kip"] / (f["d"] * f["tw"])
    return pd.DataFrame(f)


def row_metrics(y, p, util):
    out = {"n": int(len(y)), "accuracy": accuracy_score(y, p), "precision": precision_score(y, p, zero_division=0),
           "recall": recall_score(y, p, zero_division=0), "f1": f1_score(y, p, zero_division=0),
           "false_pass_rate": float(((p == 1) & (y == 0)).sum() / max((y == 0).sum(), 1)),
           "false_passes": int(((p == 1) & (y == 0)).sum())}
    band = (util >= 0.9) & (util <= 1.1)
    out["n_band_0.9_1.1"] = int(band.sum())
    out["f1_band_0.9_1.1"] = f1_score(y[band], p[band], zero_division=0)
    out["accuracy_band_0.9_1.1"] = accuracy_score(y[band], p[band])
    return out


def shortlist_metrics(P, passed, W, lightest_idx, lightest_w, theta, ks):
    """P, passed: (cases, n_sec) weight-sorted; W: (n_sec,). Cases without any passing section are excluded by the caller."""
    cand = P >= theta
    order = np.cumsum(cand, axis=1)
    rows = []
    for k in ks:
        sel = cand & (order <= k)
        sel_pass = sel & passed
        valid = sel_pass.any(1)
        first_pass = np.where(valid, np.argmax(sel_pass, axis=1), -1)
        rec_w = np.where(valid, W[np.clip(first_pass, 0, None)], np.nan)
        hit = valid & (rec_w == lightest_w)
        n_sel = sel.sum(1)
        calls_in_list = np.where(valid, order[np.arange(len(P)), np.clip(first_pass, 0, None)], n_sel)  # re-check in weight order
        calls_ml = calls_in_list + np.where(valid, 0, lightest_idx + 1)                                   # fallback: full System A search
        gap = np.where(valid, (rec_w - lightest_w) / lightest_w * 100, np.nan)
        rows.append({"k": k, "theta": theta, "cases": int(len(P)), f"recall_exact_weight": float(hit.mean()),
                     "valid_recommendation_rate": float(valid.mean()), "fallback_rate": float((~valid).mean()),
                     "mean_weight_gap_pct_valid": float(np.nanmean(gap)),
                     "mean_calls_ml_with_fallback": float(calls_ml.mean()),
                     "mean_calls_systemA_early_stop": float((lightest_idx + 1).mean()), "calls_systemA_full_scan": int(P.shape[1])})
    return rows


def run_member(member, datasets_dir, log):
    t0 = time.time()
    cases = pd.read_parquet(datasets_dir / f"B_{member}_cases.parquet")
    rows = pd.read_parquet(datasets_dir / f"B_{member}_rows.parquet")
    secs, _ = D.sections()
    nsec = len(secs)
    W = secs["W"].to_numpy(float)
    assert (rows.case_id.to_numpy()[::nsec] == np.arange(len(cases))).all() and (rows.sec_idx.to_numpy()[:nsec] == np.arange(nsec)).all()
    X = features(member, cases, rows, secs)
    y = rows.passed.to_numpy(np.int8)
    util = rows.util.to_numpy()
    split_row = cases.split.to_numpy()[rows.case_id.to_numpy()]
    m = {s: split_row == s for s in ("train", "val", "test", "ood")}
    log(f"[{member}] rows {len(rows):,}  features {list(X.columns)}  pass rate train {y[m['train']].mean():.3f}")

    models = {
        "DecisionTree": DecisionTreeClassifier(max_depth=16, min_samples_leaf=10, random_state=SEED),
        "HistGB": HistGradientBoostingClassifier(max_iter=200, learning_rate=0.1, max_leaf_nodes=63, early_stopping=False, random_state=SEED),
    }
    res = {"features": list(X.columns), "row_metrics": {}, "shortlist": [], "val_theta_search": {}, "importance": {}, "train_seconds": {}}
    probs = {}
    for name, mdl in models.items():
        t = time.time()
        mdl.fit(X[m["train"]], y[m["train"]])
        res["train_seconds"][name] = round(time.time() - t, 1)
        probs[name] = mdl.predict_proba(X)[:, 1]
        for s in ("val", "test", "ood"):
            res["row_metrics"][f"{name}/{s}"] = row_metrics(y[m[s]], (probs[name][m[s]] >= 0.5).astype(int), util[m[s]])
        log(f"[{member}] {name}: trained in {res['train_seconds'][name]}s  test F1 {res['row_metrics'][f'{name}/test']['f1']:.4f}  "
            f"ood F1 {res['row_metrics'][f'{name}/ood']['f1']:.4f}  false passes test {res['row_metrics'][f'{name}/test']['false_passes']}")

    # shortlist
    def grid(name, split):
        idx = cases.index[(cases.split == split) & (cases.n_pass > 0)].to_numpy()
        rr = (idx[:, None] * nsec + np.arange(nsec)[None, :])
        return (probs[name][rr], rows.passed.to_numpy()[rr], cases.lightest_idx.to_numpy()[idx].astype(int),
                cases.lightest_weight.to_numpy()[idx], len(cases[cases.split == split]) - len(idx))
    for name in models:
        P, ps, li, lw, _ = grid(name, "val")
        best = None
        for th in THETAS:
            r10 = shortlist_metrics(P, ps, W, li, lw, th, [10])[0]
            res["val_theta_search"].setdefault(name, []).append({"theta": th, "recall@10": r10["recall_exact_weight"], "calls": r10["mean_calls_ml_with_fallback"]})
            key = (r10["recall_exact_weight"], -r10["mean_calls_ml_with_fallback"])
            if best is None or key > best[0]:
                best = (key, th)
        th = best[1]
        res["val_theta_search"][name + "_chosen"] = th
        for s in ("test", "ood"):
            P, ps, li, lw, n_none = grid(name, s)
            for r in shortlist_metrics(P, ps, W, li, lw, th, KS):
                res["shortlist"].append({"model": name, "split": s, "cases_without_feasible_section": int(n_none), **r})

    # feature importance: tree builtin + HGB permutation (F1) on a fixed test subsample
    res["importance"]["DecisionTree_builtin"] = dict(sorted(zip(X.columns, map(float, models["DecisionTree"].feature_importances_)), key=lambda t: -t[1]))
    sub = np.random.default_rng(SEED).choice(np.flatnonzero(m["test"]), 100_000, replace=False)
    pi = permutation_importance(models["HistGB"], X.iloc[sub], y[sub], scoring="f1", n_repeats=3, random_state=SEED)
    res["importance"]["HistGB_permutation_f1_drop"] = dict(sorted(zip(X.columns, map(float, pi.importances_mean)), key=lambda t: -t[1]))
    res["importance"]["HistGB_permutation_f1_drop_std"] = {c: float(s) for c, s in zip(X.columns, pi.importances_std)}

    # case-level regression of log lightest weight (diagnostic)
    feas = cases[cases.n_pass > 0]
    Xc = feas[CASE_COLS[member]].copy()
    if member == "compression":
        Xc["Lmax"] = feas[["Lcx_ft", "Lcy_ft"]].max(axis=1); Xc["Lmin"] = feas[["Lcx_ft", "Lcy_ft"]].min(axis=1)
    else:
        Xc["Mu/Vu"] = feas.Mu_kipft / feas.Vu_kip
    yc = np.log(feas.lightest_weight)
    reg = HistGradientBoostingRegressor(max_iter=300, random_state=SEED).fit(Xc[feas.split == "train"], yc[feas.split == "train"])
    res["weight_regression"] = {}
    for s in ("test", "ood"):
        msk = (feas.split == s).to_numpy(); pred = reg.predict(Xc[msk])
        res["weight_regression"][s] = {"n": int(msk.sum()), "r2_log_weight": float(r2_score(yc[msk], pred)),
                                       "median_abs_pct_err": float(np.median(np.abs(np.exp(pred) / np.exp(yc[msk]) - 1)) * 100)}
    res["cases"] = {s: int((cases.split == s).sum()) for s in ("train", "val", "test", "ood")}
    res["seconds"] = round(time.time() - t0, 1)
    return res


def figure(results, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e5e4e0", "#fcfcfb"
    COL = {"DecisionTree": "#2a78d6", "HistGB": "#eb6834"}          # categorical slots 1 and 2 (validated)
    plt.rcParams.update({"font.size": 9, "text.color": INK, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
                         "axes.edgecolor": GRID, "figure.facecolor": SURF, "axes.facecolor": SURF})
    fig, axs = plt.subplots(2, 2, figsize=(11, 7.6), dpi=200)
    for j, member in enumerate(("compression", "flexure")):
        ax = axs[0, j]
        sl = pd.DataFrame(results[member]["shortlist"])
        for name in ("DecisionTree", "HistGB"):
            for split, ls in (("test", "-"), ("ood", (0, (4, 2)))):
                d = sl[(sl.model == name) & (sl.split == split)]
                ax.plot(d.k, d.recall_exact_weight * 100, ls=ls, color=COL[name], lw=2, marker="o", ms=4, mfc=SURF, mew=1.5,
                        label=f"{name}, {'in-range test' if split == 'test' else 'out-of-range (L > 30 ft)'}")
        ax.axhline(95, color=INK2, lw=0.8, ls=":", label="95% recall target")
        ax.set_xticks(KS); ax.set_xlabel("shortlist size k (sections re-checked by System A)"); ax.set_ylabel("top-k recall of lightest passing weight (%)")
        ax.set_title(f"{member.capitalize()}: does the shortlist contain the optimum?", loc="left", color=INK, fontsize=10, fontweight="bold")
        ax.grid(axis="y", color=GRID, lw=0.7); ax.spines[["top", "right"]].set_visible(False)
        if j == 0:
            ax.legend(frameon=False, fontsize=7.5, loc="lower right")
        imp = results[member]["importance"]["HistGB_permutation_f1_drop"]
        ax = axs[1, j]
        top = list(imp.items())[:8][::-1]
        ax.barh([t[0] for t in top], [t[1] for t in top], color=COL["HistGB"], height=0.55)
        ax.set_xlabel("drop in test F1 when the feature is shuffled (HistGB)")
        ax.set_title(f"{member.capitalize()}: what the HistGB model relies on", loc="left", color=INK, fontsize=10, fontweight="bold")
        ax.grid(axis="x", color=GRID, lw=0.7); ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("System B baseline on Dataset B (synthetic, labeled by the validated solver)", x=0.01, ha="left", color=INK, fontsize=12, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(path, bbox_inches="tight"); plt.close(fig)


if __name__ == "__main__":
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "results" / f"system_b_baseline_{stamp}"
    out.mkdir(parents=True)
    logf = open(out / "log.txt", "w", encoding="utf-8")
    def log(msg):
        print(msg, flush=True); logf.write(msg + "\n"); logf.flush()
    results = {m: run_member(m, D.OUT_DIR, log) for m in ("compression", "flexure")}
    g = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True)
    meta = {"timestamp_utc": stamp, "git_hash": g.stdout.strip() if g.returncode == 0 else None,
            "git_dirty": bool(subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"], capture_output=True, text=True).stdout.strip()),
            "seed": SEED, "python": sys.version.split()[0],
            "packages": {p: version(p) for p in ("numpy", "pandas", "scikit-learn", "pyarrow", "matplotlib")},
            "dataset_b_manifest": sorted(str(p.name) for p in (ROOT / "results").glob("dataset_b_*"))[-1:]}
    (out / "metrics.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    for m, r in results.items():
        pd.DataFrame(r["shortlist"]).to_csv(out / f"shortlist_{m}.csv", index=False)
        pd.DataFrame([{"split_model": k, **v} for k, v in r["row_metrics"].items()]).to_csv(out / f"row_metrics_{m}.csv", index=False)
    figure(results, out / "system_b_baseline.png")
    (ROOT / "presentation").mkdir(exist_ok=True)
    import shutil
    shutil.copy(out / "system_b_baseline.png", ROOT / "presentation" / "system_b_baseline.png")
    log(f"saved to {out}")
