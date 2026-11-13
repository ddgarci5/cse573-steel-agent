"""Dataset D human-test intake builder. Rows below are synthetic and live only inside these tests; they are never written to the split."""
import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eval"))
import build_dataset_d_human as B  # noqa: E402


def row(**kw):
    base = {c: "" for c in B.COLUMNS}
    base.update(item_id="H001", writer="peer1", source_type="peer_written", expected_behavior="extract",
             problem_text="need a column check, W14x90, 30 ft about x and 15 ft about y, whats the capacity", member_type="compression",
             task="check_given_section", section="W14X90", Lcx_ft="30", Lcy_ft="15")
    base.update(kw)
    return ("t.csv", 2, base)


def build(*rows, ref=None):
    return B.build_items(list(rows), ref)


def test_valid_extract_row():
    items, errors, warnings = build(row())
    assert errors == [] and warnings == [] and len(items) == 1
    it = items[0]
    assert it["gold_design_case"]["geometry"]["Lcx_ft"] == 30.0 and it["gold_design_case"]["problem_id"] == "H001" and it["split"] == "human_test"


def test_blank_is_null_and_zero_is_kept():
    items, errors, _ = build(row(item_id="H002", problem_text="beam W18x50 braced all along, Cb 1.0, flexural strength?", member_type="flexure",
                                 Lcx_ft="", Lcy_ft="", Lb_ft="0", Cb="1.0", section="W18X50"))
    g = items[0]["gold_design_case"]["geometry"]
    assert errors == [] and (g["Lb_ft"], g["Cb"], g["Lcx_ft"], g["Lcy_ft"]) == (0.0, 1.0, None, None)


@pytest.mark.parametrize("patch,msg", [
    ({"item_id": "X1"}, "item_id"),
    ({"writer": "Jane Doe"}, "writer"),
    ({"source_type": "llm_written"}, "source_type"),
    ({"expected_behavior": "maybe"}, "expected_behavior"),
    ({"problem_text": "short"}, "problem_text"),
    ({"tags": "not_a_tag"}, "unknown tags"),
    ({"source_type": "aisc_given_rewritten"}, "source_ref"),
    ({"Lcx_ft": "thirty"}, "not a number"),
    ({"Lcx_ft": "3000"}, "valid DesignCase"),                    # implausible range
    ({"Lcy_ft": ""}, "valid DesignCase"),                        # required input missing but not declared
])
def test_errors(patch, msg):
    items, errors, _ = build(row(**patch))
    assert items == [] and any(msg in e for e in errors), errors


def test_duplicate_id():
    items, errors, _ = build(row(), row())
    assert len(items) == 1 and any("duplicate" in e for e in errors)


def test_ask_user_row_must_list_exactly_the_missing_inputs():
    ok = row(item_id="H003", expected_behavior="ask_user", Lcy_ft="", missing_fields="Lcy_ft", tags="missing_assumption",
             problem_text="W14x90 column, 30 ft about the strong axis, what is the capacity?")
    items, errors, _ = build(ok)
    assert errors == [] and items[0]["gold_design_case"]["missing_fields"] == ["Lcy_ft"]
    bad = row(item_id="H004", expected_behavior="ask_user", Lcy_ft="", missing_fields="Lcy_ft;Lcx_ft")
    assert build(bad)[0] == [] and build(bad)[1]                      # Lcx is stated, so it cannot be listed as missing
    errs = build(row(item_id="H005", expected_behavior="ask_user"))[1]    # complete row labelled ask_user
    assert any("ask_user" in e for e in errs)
    errs = build(row(item_id="H009", expected_behavior="extract", Lcy_ft="", missing_fields="Lcy_ft"))[1]   # declared missing but labelled extract
    assert any("extract rows must be complete" in e for e in errs)


def test_out_of_scope_rows():
    ok = row(item_id="H006", expected_behavior="out_of_scope", expected_flag="section_not_in_database", section="HSS6X6X1/4", Lcx_ft="10", Lcy_ft="10",
             problem_text="HSS6x6x1/4 column, 10 ft both ways, how much can it carry?", tags="non_W_shape")
    assert build(ok)[1] == []
    assert any("expected_flag" in e for e in build(row(item_id="H007", expected_behavior="out_of_scope", expected_flag="unsupported_material"))[1])
    other = row(item_id="H008", expected_behavior="out_of_scope", expected_flag="other", member_type="", task="", section="", Lcx_ft="", Lcy_ft="",
                problem_text="beam-column under Pu = 200 kip and Mu = 150 kip-ft, check interaction", tags="other")
    items, errors, _ = build(other)
    assert errors == [] and items[0]["gold_design_case"] is None


def test_number_not_in_text_warns_unless_conversion_note():
    items, errors, warnings = build(row(Lcx_ft="14", problem_text="W14x90 column, 168 in about x and 15 ft about y, capacity?"))
    assert errors == [] and any("Lcx_ft" in w for w in warnings)
    _, _, warnings = build(row(Lcx_ft="14", conversion_note="168 in = 14 ft", problem_text="W14x90 column, 168 in about x and 15 ft about y, capacity?"))
    assert not any("Lcx_ft" in w for w in warnings)


def test_k_and_l_go_to_extra_gold_not_the_scored_case():
    r = row(Lcx_ft="14", Lcy_ft="10", L_ft="14", Kx="1.0", Ky="1.0", tags="K_and_L_given",
            problem_text="W14x90 column, L = 14 ft about x and 10 ft about y, K = 1.0 both ways, capacity?")
    items, errors, _ = build(r)
    assert errors == [] and items[0]["extra_gold"] == {"L_ft": 14.0, "Kx": 1.0, "Ky": 1.0}


def test_copyright_overlap_is_an_error():
    line = "an example sentence of at least thirty characters from a reference"
    items, errors, _ = build(row(problem_text="Q: " + line.upper() + " ... capacity of W14x90?"), ref={line})
    assert items == [] and any("copyrighted" in e for e in errors)


def test_main_writes_split_file_and_fails_on_errors(tmp_path):
    for name in ("intake_template.csv", "intake_peer1.csv"):
        with open(tmp_path / name, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=B.COLUMNS)
            w.writeheader()
            if name != "intake_template.csv":
                w.writerow(row()[2])
    B.main(["--dir", str(tmp_path), "--no-reference-check"])
    out = json.loads((tmp_path / "human_test.json").read_text(encoding="utf-8"))
    assert out["summary"]["n_items"] == 1 and "TEST ONLY" in out["role"] and len(out["items_sha256"]) == 64
    with open(tmp_path / "intake_peer1.csv", "a", newline="", encoding="utf-8-sig") as fh:
        csv.DictWriter(fh, fieldnames=B.COLUMNS).writerow({**row()[2], "item_id": "H002", "expected_behavior": "nope"})
    with pytest.raises(SystemExit):
        B.main(["--dir", str(tmp_path), "--no-reference-check"])
