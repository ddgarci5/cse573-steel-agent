"""Dataset B generator labels must equal the solver's (via the pandas-Series path) and search.lightest's."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ml"))
import dataset_b as D  # noqa: E402

from steelagent import shapes  # noqa: E402
from steelagent.compression import compression_strength  # noqa: E402
from steelagent.flexure import flexure_strength, shear_strength  # noqa: E402
from steelagent.search import lightest  # noqa: E402


@pytest.fixture(scope="module", params=["compression", "flexure"])
def data(request):
    cases, rows = D.generate(request.param, 24, 6, seed=7)
    return request.param, cases, rows.merge(cases, on="case_id")


def test_deterministic():
    a, _ = D.generate("flexure", 8, 2, seed=11)
    b, _ = D.generate("flexure", 8, 2, seed=11)
    assert a.equals(b)


def test_splits_and_ranges(data):
    m, cases, _ = data
    assert cases.split.value_counts().to_dict() == {"train": 16, "val": 4, "test": 4, "ood": 6}
    lengths = cases[["Lcx_ft", "Lcy_ft"]].max(axis=1) if m == "compression" else cases.Lb_ft
    assert (lengths[cases.split != "ood"] <= D.L_IN_MAX).all()
    assert (lengths[cases.split == "ood"] > D.L_IN_MAX).all()


def test_row_labels_match_solver(data):
    m, _, r = data
    df, _ = D.sections()
    for i in np.random.default_rng(0).choice(len(r), 150, replace=False):
        row = r.iloc[i]
        s = shapes.get(df.label[int(row.sec_idx)])
        if m == "compression":
            cap = compression_strength(s, row.Lcx_ft, row.Lcy_ft)["phiPn"]
            util = row.Pu_kip / cap
        else:
            cap = flexure_strength(s, row.Lb_ft, row.Cb)["phiMn"]
            util = max(row.Mu_kipft / cap, row.Vu_kip / shear_strength(s)["phiVn"])
        assert row.cap == pytest.approx(cap, rel=1e-6)
        assert row.util == pytest.approx(util, rel=1e-6)
        assert bool(row.passed) == (util <= 1.0)


def test_lightest_weight_matches_search(data):
    m, cases, _ = data
    for c in cases[cases.n_pass > 0].head(12).itertuples():
        if m == "compression":
            s = lightest("compression", {"Pu": c.Pu_kip}, {"Lcx_ft": c.Lcx_ft, "Lcy_ft": c.Lcy_ft})
        else:
            s = lightest("flexure", {"Mu": c.Mu_kipft, "Vu": c.Vu_kip}, {"Lb_ft": c.Lb_ft, "Cb": c.Cb})
        assert shapes.get(s["section"])["W"] == c.lightest_weight
