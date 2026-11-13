"""Build the Dataset D human-written TEST split from intake CSV files written by people (never by an LLM).

Input : datasets/D_instructions/human_test/intake_*.csv   (UTF-8, Excel "CSV UTF-8" is fine; one row = one problem; blank cell = null)
Output: datasets/D_instructions/human_test/human_test.json  (validated items + counts + sha256 of the items) and a text report.

What is checked (errors stop the build; warnings are printed and saved in the report):
  * ids unique; writer is a short code (no free-text names); source_type / expected_behavior from the allowed lists; problem text not tiny.
  * expected_behavior = extract     -> the gold row is a valid DesignCase, no missing inputs, no domain flags.
    expected_behavior = ask_user    -> valid DesignCase whose missing inputs (computed in code) are exactly the listed `missing_fields`, non-empty.
    expected_behavior = out_of_scope-> `expected_flag` is a DesignCase flag code that the gold row actually raises, or "other" (e.g. combined forces,
                                       a topic the schema cannot hold); the gold row is optional for "other".
  * numbers in the gold row should appear in the problem text (within 0.5 %) unless `conversion_note` explains the conversion (warning only).
  * the problem text must not copy >= 30-character lines from the copyrighted reference material in references/ (error; skipped with a warning
    if references/ or pdftotext is missing).
Nothing here calls a model. This split is TEST ONLY: never use it for prompt tuning, few-shot examples, LoRA data or any training.

Usage (repo root):  .venv/Scripts/python.exe eval/build_dataset_d_human.py [--no-reference-check]
"""
import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pydantic import ValidationError  # noqa: E402
from agent.design_case import DesignCase, format_validation_error  # noqa: E402

D_DIR = ROOT / "datasets" / "D_instructions" / "human_test"
SOURCE_TYPES = ("aisc_given_rewritten", "peer_written", "student_written")
BEHAVIORS = ("extract", "ask_user", "out_of_scope")
FLAG_CODES = ("unsupported_combination", "unsupported_design_method", "unsupported_material", "section_not_in_database", "An_exceeds_Ag", "other")
TAGS = ("units_mixed", "abbreviation", "missing_assumption", "ambiguous_phrasing", "K_and_L_given", "load_in_other_units", "extra_irrelevant_info",
        "typo", "implicit_value", "multiple_questions", "non_A992", "non_W_shape", "needs_load_combination", "other")
DATASET_C_IDS = {"D.1-yield", "D.1-rupture", "E.1C", "E.1D", "F.1-1B", "F.1-2B", "F.1-3B", "F.3B", "G.1B", "E.1A", "F.1-1A", "F.4", "F.3A"}

COLUMNS = ["item_id", "writer", "source_type", "source_ref", "problem_text", "expected_behavior", "expected_flag", "tags", "conversion_note", "notes",
           "member_type", "task", "section", "requested_limit_states", "design_method", "material_grade", "Fy_ksi", "Fu_ksi", "E_ksi",
           "Pu_kip", "Mu_kipft", "Vu_kip", "Lcx_ft", "Lcy_ft", "Lb_ft", "Cb", "An_in2", "U", "nominal_depth_in", "max_depth_in", "Ix_min_in4",
           "missing_fields", "L_ft", "Kx", "Ky"]
EXTRA_GOLD = ("L_ft", "Kx", "Ky")   # stated in the text but not yet in the schema (CLAUDE.md section 7 has them); kept as extra_gold, not scored yet
NUMERIC = {"Fy_ksi", "Fu_ksi", "E_ksi", "Pu_kip", "Mu_kipft", "Vu_kip", "Lcx_ft", "Lcy_ft", "Lb_ft", "Cb", "An_in2", "U", "nominal_depth_in", "max_depth_in", "Ix_min_in4", *EXTRA_GOLD}
GOLD_GROUPS = {"material": ("material_grade:grade", "Fy_ksi", "Fu_ksi", "E_ksi"), "demands": ("Pu_kip", "Mu_kipft", "Vu_kip"),
               "geometry": ("Lcx_ft", "Lcy_ft", "Lb_ft", "Cb"), "net_section": ("An_in2", "U"), "constraints": ("nominal_depth_in", "max_depth_in", "Ix_min_in4")}


def _split(cell):
    return [x.strip() for x in re.split(r"[;,|]", cell or "") if x.strip()]


def row_to_gold(row):
    """CSV row -> (DesignCase dict | None, extra_gold dict). Blank = null. Raises ValueError on an unparseable number."""
    def num(k):
        v = (row.get(k) or "").strip()
        if not v:
            return None
        try:
            return float(v.replace(",", ""))
        except ValueError:
            raise ValueError(f"{k}: {v!r} is not a number (write the number only, in the unit of the column name)")

    d = {k: (row.get(k) or "").strip() or None for k in ("member_type", "task", "section", "design_method")}
    if d["design_method"] is None:
        del d["design_method"]
    d["requested_limit_states"] = _split(row.get("requested_limit_states"))
    d["missing_fields"] = _split(row.get("missing_fields"))
    for grp, cols in GOLD_GROUPS.items():
        g = {}
        for c in cols:
            col, key = (c.split(":") + [c])[:2] if ":" in c else (c, c)
            if col in NUMERIC:
                v = num(col)
            else:
                v = (row.get(col) or "").strip() or None
            if v is not None:
                g[key] = v
        if g:
            d[grp] = g
    if d.get("member_type") is None and d.get("task") is None:
        return None, {k: num(k) for k in EXTRA_GOLD if num(k) is not None}
    return d, {k: num(k) for k in EXTRA_GOLD if num(k) is not None}


def numbers_in(text):
    text = re.sub(r"\bW\s*\d+\s*[xX×]\s*\d+(\.\d+)?", " ", text)     # drop section labels such as W14x90 so their digits do not count as stated values
    return [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*\.?\d*", text) if x.replace(",", "").replace(".", "", 1).isdigit()]


def gold_numbers(d, extra):
    out = {}
    for grp in ("demands", "geometry", "net_section", "constraints"):
        out.update({f"{grp}.{k}": v for k, v in d.get(grp, {}).items()})
    out.update({f"extra.{k}": v for k, v in extra.items()})
    return out


def norm(s):
    return re.sub(r"\s+", " ", s).strip().lower()


def reference_lines():
    ref = ROOT / "references"
    pdfs = list(ref.rglob("*.pdf")) if ref.exists() else []
    if not pdfs:
        return None
    lines = set()
    for pdf in pdfs:
        try:
            out = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, timeout=120).stdout.decode("utf-8", "replace")
        except (OSError, subprocess.TimeoutExpired):
            return None
        lines |= {norm(l) for l in out.splitlines() if len(norm(l)) >= 30}
    return lines


def build_items(rows, ref_lines=None):
    """rows: list of (source_file, line_no, dict). Returns (items, errors, warnings)."""
    items, errors, warnings, seen = [], [], [], set()
    for src, ln, row in rows:
        where = f"{src}:{ln} ({row.get('item_id') or '?'})"
        err = lambda m: errors.append(f"{where}: {m}")  # noqa: E731
        warn = lambda m: warnings.append(f"{where}: {m}")  # noqa: E731
        iid = (row.get("item_id") or "").strip()
        if not re.fullmatch(r"H\d{3,4}", iid):
            err("item_id must look like H001"); continue
        if iid in seen:
            err("duplicate item_id"); continue
        seen.add(iid)
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,20}", (row.get("writer") or "").strip()):
            err("writer must be a short code such as student, peer1 (letters, digits, - _ only; no names)"); continue
        st, beh = (row.get("source_type") or "").strip(), (row.get("expected_behavior") or "").strip()
        text = (row.get("problem_text") or "").strip()
        if st not in SOURCE_TYPES:
            err(f"source_type must be one of {SOURCE_TYPES}")
        if beh not in BEHAVIORS:
            err(f"expected_behavior must be one of {BEHAVIORS}")
        if len(text) < 20:
            err("problem_text is missing or too short")
        if st == "aisc_given_rewritten" and not (row.get("source_ref") or "").strip():
            err("aisc_given_rewritten needs source_ref (e.g. 'Design Example F.2-1, rewritten in own words'); never paste AISC text")
        tags = _split(row.get("tags"))
        bad_tags = [t for t in tags if t not in TAGS]
        if bad_tags:
            err(f"unknown tags {bad_tags}; allowed: {list(TAGS)}")
        if any(e.startswith(where) for e in errors):
            continue
        if ref_lines:
            hit = [l for l in ref_lines if l in norm(text)]
            if hit:
                err(f"problem_text contains {len(hit)} line(s) identical to the copyrighted reference material; rewrite it in your own words"); continue
        try:
            gold_dict, extra = row_to_gold(row)
        except ValueError as e:
            err(str(e)); continue
        case, flags, eff_missing = None, [], []
        if gold_dict is not None:
            try:
                case = DesignCase.model_validate({**gold_dict, "problem_id": iid})
                flags, eff_missing = case.flags(), case.effective_missing_fields()
            except ValidationError as e:
                err("gold row is not a valid DesignCase:\n" + format_validation_error(e)); continue
        flag_codes = [f["code"] for f in flags]
        if beh == "extract":
            if case is None:
                err("expected_behavior=extract needs a gold row (member_type, task, ...)"); continue
            if eff_missing or flag_codes:
                err(f"extract rows must be complete and in scope; got missing={eff_missing} flags={flag_codes}"); continue
        elif beh == "ask_user":
            declared = sorted(set(case.missing_fields)) if case else []
            if case is None or not eff_missing or sorted(eff_missing) != declared or flag_codes:
                err(f"ask_user rows need missing_fields equal to the inputs the check needs but the text lacks; computed missing={eff_missing}, "
                    f"listed={declared}, flags={flag_codes}"); continue
        else:
            ef = (row.get("expected_flag") or "").strip()
            if ef not in FLAG_CODES:
                err(f"out_of_scope needs expected_flag from {list(FLAG_CODES)}"); continue
            if ef != "other" and ef not in flag_codes:
                err(f"expected_flag={ef} but the gold row raises {flag_codes}"); continue
        if case is not None:
            for k, v in gold_numbers(gold_dict, extra).items():
                if v == 0 or any(abs(n - v) <= 0.005 * abs(v) for n in numbers_in(text)):
                    continue
                if not (row.get("conversion_note") or "").strip():
                    warn(f"gold {k} = {v:g} does not appear in the text and conversion_note is empty (typo, or an unstated unit conversion?)")
        if (row.get("source_ref") or "").strip() in DATASET_C_IDS:
            warn("source_ref names one of the 13 Dataset C problems; fine for a messy rewrite, but report it as an overlap")
        items.append({"item_id": iid, "writer": row["writer"].strip(), "source_type": st, "source_ref": (row.get("source_ref") or "").strip(),
                      "problem_text": text, "expected_behavior": beh, "expected_flag": (row.get("expected_flag") or "").strip() or None, "tags": tags,
                      "conversion_note": (row.get("conversion_note") or "").strip(), "notes": (row.get("notes") or "").strip(),
                      "gold_design_case": case.model_dump(mode="json") if case else None, "extra_gold": extra, "split": "human_test"})
    return items, errors, warnings


def read_rows(paths):
    rows = []
    for p in paths:
        with open(p, newline="", encoding="utf-8-sig") as fh:
            rd = csv.DictReader(fh)
            missing = [c for c in COLUMNS if c not in (rd.fieldnames or [])]
            if missing:
                raise SystemExit(f"{p.name}: missing columns {missing}; start from intake_template.csv")
            for i, r in enumerate(rd, start=2):
                if any((v or "").strip() for v in r.values()):
                    rows.append((p.name, i, r))
    return rows


def summarize(items):
    return {"n_items": len(items), "by_expected_behavior": dict(Counter(i["expected_behavior"] for i in items)),
            "by_source_type": dict(Counter(i["source_type"] for i in items)),
            "by_writer": dict(Counter(i["writer"] for i in items)),
            "by_member_type": dict(Counter((i["gold_design_case"] or {}).get("member_type", "none") for i in items)),
            "by_task": dict(Counter((i["gold_design_case"] or {}).get("task", "none") for i in items)),
            "by_tag": dict(Counter(t for i in items for t in i["tags"])),
            "items_with_extra_gold_not_yet_in_schema": sum(bool(i["extra_gold"]) for i in items)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-reference-check", action="store_true")
    ap.add_argument("--dir", default=str(D_DIR))
    a = ap.parse_args(argv)
    d = Path(a.dir)
    paths = sorted(p for p in d.glob("intake_*.csv") if p.name != "intake_template.csv")
    rows = read_rows(paths)
    ref = None if a.no_reference_check else reference_lines()
    if ref is None and not a.no_reference_check:
        print("WARNING: reference overlap check skipped (references/ or pdftotext not available)")
    items, errors, warnings = build_items(rows, ref)
    report = [f"files: {[p.name for p in paths]}", f"rows read: {len(rows)}; valid items: {len(items)}; errors: {len(errors)}; warnings: {len(warnings)}"]
    report += ["ERROR " + e for e in errors] + ["warning " + w for w in warnings]
    print("\n".join(report))
    if errors:
        sys.exit(1)
    items.sort(key=lambda i: i["item_id"])
    blob = json.dumps(items, sort_keys=True, ensure_ascii=False)
    out = {"dataset": "D_instructions", "split": "human_test", "role": "TEST ONLY: never used for prompt tuning, few-shot examples, LoRA data or any training",
           "written_by": "people (student, peers, rewritten textbook 'Given:' statements in own words); never by an LLM", "summary": summarize(items),
           "items_sha256": hashlib.sha256(blob.encode("utf-8")).hexdigest(), "items": items}
    (d / "human_test.json").write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (d / "build_report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps(out["summary"], indent=2))


if __name__ == "__main__":
    main()
