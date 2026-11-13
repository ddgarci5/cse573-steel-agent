"""LLM extraction: problem text -> DesignCase JSON (first two steps of System D: Parse, then validate; the solver is called by agent/route.py).

The model is asked for ONE JSON object and nothing else: no calculation, no capacity, no answer. The JSON is validated with Pydantic
(agent/design_case.py). If it is invalid, there is at most ONE retry in which the validation error is shown to the model; every attempt is logged.
Domain flags (e.g. a section that is not in the AISC database) are not "invalid JSON": they trigger no retry and are never corrected.

PROMPT_VERSION and PROMPT are FROZEN for the evaluation run (their sha256 is written to the run's meta.json). Do not edit them after a run has started;
if a real bug in the schema or the parser (not a model mistake) is found, fix it, document it, and rerun everything.
"""
import hashlib
import json
import re

from pydantic import ValidationError

from agent.design_case import DesignCase, format_validation_error

PROMPT_VERSION = "extract-v1"

PROMPT = """You convert a structural steel design problem into a JSON object called a DesignCase.
Output ONLY that one JSON object. No prose, no code fences, no working, no calculated values, no capacities, no answer to the problem.

This tool uses ANSI/AISC 360-22, LRFD, ASTM A992 steel and U.S. customary units. Convert every number to the unit in its field name
(lengths in ft, forces in kips, moments in kip-ft, areas in in^2, Ix in in^4, stresses in ksi). Copy numbers exactly as the problem states them.
Use null for anything the problem does not state. Never invent, assume or default a value, and never compute one.

JSON template (these are the only allowed keys):
{
  "member_type": "tension" | "compression" | "flexure" | "shear",
  "task": "check_given_section" | "select_lightest",
  "design_method": "LRFD",
  "section": null,
  "requested_limit_states": [],
  "material": {"grade": "ASTM A992", "Fy_ksi": 50, "Fu_ksi": 65, "E_ksi": 29000},
  "demands": {"Pu_kip": null, "Mu_kipft": null, "Vu_kip": null},
  "geometry": {"Lcx_ft": null, "Lcy_ft": null, "Lb_ft": null, "Cb": null},
  "net_section": {"An_in2": null, "U": null},
  "constraints": {"nominal_depth_in": null, "max_depth_in": null, "Ix_min_in4": null},
  "missing_fields": []
}

Field meanings:
- task: "check_given_section" if the problem asks for the strength of a stated section; "select_lightest" if it asks for the lightest W-shape.
- section: the W-shape label as an upper-case string such as "W14X90"; null when no section is given.
- requested_limit_states: tension members only. ["tension_yield"] if the question asks about yielding on the gross section, ["tension_rupture"] if it asks about rupture on the effective net area, both strings if it asks about both. Use [] for every other member type, and when no limit state is named.
- demands: factored (required) loads Pu, Mu, Vu.
- geometry: Lcx_ft and Lcy_ft are effective lengths about the x and y axes (compression); Lb_ft is the unbraced length for lateral-torsional buckling (0 if the beam is continuously braced); Cb is the moment-gradient factor.
- net_section: An_in2 is the net area and U the shear lag factor.
- constraints: nominal_depth_in is an exact nominal depth (14 for "W14"); max_depth_in is an upper limit on nominal depth ("no more than 18 in." gives 18); Ix_min_in4 is a minimum moment of inertia required for deflection.
- missing_fields: list the names of inputs that the requested check needs but the problem does not state. Needed inputs: tension check = section, plus An_in2 and U unless only yielding is asked; compression check = section, Lcx_ft, Lcy_ft; flexure check = section, Lb_ft, and Cb unless Lb_ft is 0; shear check = section; compression selection = Pu_kip, Lcx_ft, Lcy_ft; flexure selection = Mu_kipft, Lb_ft, and Cb unless Lb_ft is 0. Allowed names: section, Pu_kip, Mu_kipft, Vu_kip, Lcx_ft, Lcy_ft, Lb_ft, Cb, An_in2, U. Use [] when nothing needed is missing.

"""
PROMPT_SHA256 = hashlib.sha256(PROMPT.encode("utf-8")).hexdigest()


def build_messages(problem_text):
    """First-attempt chat messages: the frozen instructions followed by the problem statement."""
    return [{"role": "user", "content": PROMPT + problem_text.strip()}]


def retry_messages(messages, first_response, error_text):
    return messages + [{"role": "assistant", "content": first_response or ""},
                       {"role": "user", "content": "Your JSON object was not valid:\n" + error_text +
                        "\nReturn the corrected JSON object only (same template, same rules: no prose, no calculations, no invented values)."}]


def parse_json_object(text):
    """Return (obj, fenced, error). A surrounding markdown code fence is tolerated and recorded (`fenced`); any other text around the object
    makes the response unparseable (counted as invalid, retried once). The top-level value must be a JSON object."""
    t = (text or "").strip()
    fenced = False
    m = re.match(r"^```[a-zA-Z]*\s*\n(.*?)\n?```\s*$", t, flags=re.S)
    if m:
        t, fenced = m.group(1).strip(), True
    try:
        obj = json.loads(t)
    except json.JSONDecodeError as e:
        return None, fenced, f"not parseable JSON ({e.msg} at line {e.lineno} column {e.colno}); return one JSON object and nothing else"
    if not isinstance(obj, dict):
        return None, fenced, "the top-level JSON value must be an object"
    return obj, fenced, None


def validate_response(text, problem_id):
    """Parse + Pydantic-validate one model response. Returns dict(case=DesignCase|None, error=str|None, fenced=bool, raw_object=dict|None).
    problem_id is set by the harness (the model is never shown it)."""
    obj, fenced, err = parse_json_object(text)
    if err:
        return {"case": None, "error": err, "fenced": fenced, "raw_object": None}
    obj = {**obj, "problem_id": problem_id}
    try:
        return {"case": DesignCase.model_validate(obj), "error": None, "fenced": fenced, "raw_object": obj}
    except ValidationError as e:
        return {"case": None, "error": format_validation_error(e), "fenced": fenced, "raw_object": obj}


def extract(problem_text, problem_id, ask):
    """Run extraction with at most one retry.

    ask(messages) -> dict with at least {"response": str}; extra keys (usage, finish reason, ...) are logged as they are.
    Returns {"status": "valid_first_try" | "valid_after_retry" | "invalid", "case": DesignCase|None, "attempts": [log dicts]}.
    """
    messages = build_messages(problem_text)
    attempts = []
    resp = ask(messages)
    v = validate_response(resp["response"], problem_id)
    attempts.append({"attempt": 1, "messages": messages, "reply": resp, "valid": v["case"] is not None, "error": v["error"], "fenced": v["fenced"]})
    if v["case"] is not None:
        return {"status": "valid_first_try", "case": v["case"], "attempts": attempts}
    messages2 = retry_messages(messages, resp["response"], v["error"])
    resp2 = ask(messages2)
    v2 = validate_response(resp2["response"], problem_id)
    attempts.append({"attempt": 2, "messages": messages2, "reply": resp2, "valid": v2["case"] is not None, "error": v2["error"], "fenced": v2["fenced"]})
    return {"status": "valid_after_retry" if v2["case"] is not None else "invalid", "case": v2["case"], "attempts": attempts}
