"""DesignCase: typed description of one steel-member design problem (CLAUDE.md section 7, restricted to what the 13 Dataset C problems need).

Two layers of checking, kept separate on purpose:
  1. Pydantic validation (hard errors, raise ValidationError; the extraction step may retry once with the message shown to the model):
     types, units-in-the-name, plausible ranges, unknown keys, and consistency of `missing_fields` with the required-inputs map.
  2. Domain flags (`DesignCase.flags()`, never raised, never corrected): section label not in the AISC Shapes Database, unsupported
     material / method / member-task combination, An > Ag. A flagged case is not computed (agent/route.py); nothing is silently fixed.

Required inputs are NEVER filled with defaults: a null stays null and is listed in `missing_fields`.
Units: U.S. customary; lengths in ft at the interface (kips, in., ksi, kip-ft).
The only formatting normalization is on the section label: whitespace removed, upper-cased, the multiplication sign mapped to X
("w14x132" -> "W14X132"); the characters of the label itself are never changed, so "W14X133" stays "W14X133" and is flagged.
"""
import re
import sys
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "steelagent") not in sys.path:
    sys.path.insert(0, str(ROOT / "steelagent"))

MemberType = Literal["tension", "compression", "flexure", "shear"]
Task = Literal["check_given_section", "select_lightest"]
LimitState = Literal["tension_yield", "tension_rupture"]

A992 = {"grade": "ASTM A992", "Fy_ksi": 50.0, "Fu_ksi": 65.0, "E_ksi": 29000.0}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Material(_Strict):
    grade: str = A992["grade"]
    Fy_ksi: float = Field(A992["Fy_ksi"], gt=0, le=200)
    Fu_ksi: float = Field(A992["Fu_ksi"], gt=0, le=250)
    E_ksi: float = Field(A992["E_ksi"], gt=1000, le=40000)


class Demands(_Strict):
    Pu_kip: Optional[float] = Field(None, gt=0, le=50000)
    Mu_kipft: Optional[float] = Field(None, gt=0, le=200000)
    Vu_kip: Optional[float] = Field(None, gt=0, le=10000)


class Geometry(_Strict):
    Lcx_ft: Optional[float] = Field(None, ge=0, le=200)       # effective length K*L about the x axis (compression)
    Lcy_ft: Optional[float] = Field(None, ge=0, le=200)       # effective length K*L about the y axis (compression)
    Lb_ft: Optional[float] = Field(None, ge=0, le=200)        # unbraced length for lateral-torsional buckling (flexure)
    Cb: Optional[float] = Field(None, ge=1.0, le=3.0)         # lateral-torsional buckling modification factor


class NetSection(_Strict):
    An_in2: Optional[float] = Field(None, gt=0, le=500)
    U: Optional[float] = Field(None, gt=0, le=1.0)


class Constraints(_Strict):
    nominal_depth_in: Optional[int] = Field(None, gt=0, le=44)   # "W14" -> 14: only sections with this nominal depth
    max_depth_in: Optional[int] = Field(None, gt=0, le=44)       # only sections with nominal depth <= this
    Ix_min_in4: Optional[float] = Field(None, gt=0, le=100000)   # minimum Ix for a deflection limit


# flat names used in missing_fields (all unique across groups)
_PATHS = {
    "section": ("section",),
    "Pu_kip": ("demands", "Pu_kip"), "Mu_kipft": ("demands", "Mu_kipft"), "Vu_kip": ("demands", "Vu_kip"),
    "Lcx_ft": ("geometry", "Lcx_ft"), "Lcy_ft": ("geometry", "Lcy_ft"), "Lb_ft": ("geometry", "Lb_ft"), "Cb": ("geometry", "Cb"),
    "An_in2": ("net_section", "An_in2"), "U": ("net_section", "U"),
}
MISSING_FIELD_NAMES = sorted(_PATHS)


def required_inputs(member_type, task, requested_limit_states=(), Lb_ft="unknown"):
    """Executable 'required checks' map: the inputs a (member_type, task) needs before it may be computed.
    Returns None for a combination the MVP does not support. Cb is needed unless Lb is known to be 0 (then LTB cannot reduce Mn)."""
    cb = [] if Lb_ft == 0 else ["Cb"]
    if task == "check_given_section":
        if member_type == "tension":
            rupture = (not requested_limit_states) or ("tension_rupture" in requested_limit_states)
            return ["section"] + (["An_in2", "U"] if rupture else [])
        if member_type == "compression":
            return ["section", "Lcx_ft", "Lcy_ft"]
        if member_type == "flexure":
            return ["section", "Lb_ft"] + cb
        if member_type == "shear":
            return ["section"]
    if task == "select_lightest":
        if member_type == "compression":
            return ["Pu_kip", "Lcx_ft", "Lcy_ft"]
        if member_type == "flexure":
            return ["Mu_kipft", "Lb_ft"] + cb
    return None


def normalize_section(label):
    """Formatting only: strip whitespace, upper-case, map the multiplication sign to X. Never changes the digits."""
    if label is None:
        return None
    return re.sub(r"\s+", "", str(label)).upper().replace("×", "X") or None


class DesignCase(_Strict):
    problem_id: str = ""
    member_type: MemberType
    task: Task
    design_method: Literal["LRFD", "ASD"] = "LRFD"
    section: Optional[str] = None
    requested_limit_states: list[LimitState] = Field(default_factory=list)   # tension only; empty = every limit state of the member
    material: Material = Field(default_factory=Material)
    demands: Demands = Field(default_factory=Demands)
    geometry: Geometry = Field(default_factory=Geometry)
    net_section: NetSection = Field(default_factory=NetSection)
    constraints: Constraints = Field(default_factory=Constraints)
    missing_fields: list[str] = Field(default_factory=list)                  # as declared by the producer (LLM or gold)

    @field_validator("section", mode="before")
    @classmethod
    def _norm_section(cls, v):
        return normalize_section(v)

    @field_validator("missing_fields")
    @classmethod
    def _known_missing(cls, v):
        bad = [x for x in v if x not in _PATHS]
        if bad:
            raise ValueError(f"unknown missing_fields entries {bad}; allowed names: {MISSING_FIELD_NAMES}")
        return sorted(set(v))

    # ---- helpers
    def value_of(self, flat_name):
        cur = self
        for part in _PATHS[flat_name]:
            cur = getattr(cur, part)
        return cur

    def required_inputs(self):
        return required_inputs(self.member_type, self.task, self.requested_limit_states, self.geometry.Lb_ft if self.geometry.Lb_ft is not None else "unknown")

    def required_missing(self):
        """Required inputs that are null, computed in code from the required-inputs map (authoritative)."""
        req = self.required_inputs() or []
        return [n for n in req if self.value_of(n) is None]

    def effective_missing_fields(self):
        """Union of the producer's declaration and the code's computation: non-empty means the agent would ask the user."""
        return sorted(set(self.missing_fields) | set(self.required_missing()))

    @model_validator(mode="after")
    def _missing_consistent(self):
        wrongly_declared = [n for n in self.missing_fields if self.value_of(n) is not None]
        if wrongly_declared:
            raise ValueError(f"missing_fields lists {wrongly_declared}, but those inputs have a value")
        undeclared = [n for n in self.required_missing() if n not in self.missing_fields]
        if undeclared:
            raise ValueError(f"required input(s) {undeclared} are null for member_type={self.member_type}, task={self.task} but are not "
                             f"listed in missing_fields; list them (never invent values for missing inputs)")
        return self

    def flags(self):
        """Domain flags (list of {code, message}); computed in code, never fixed silently. A flagged case is not routed to the solver."""
        out = []
        if self.required_inputs() is None:
            out.append({"code": "unsupported_combination", "message": f"{self.member_type} with {self.task} is outside the MVP scope"})
        if self.design_method != "LRFD":
            out.append({"code": "unsupported_design_method", "message": f"{self.design_method} is outside the MVP scope (LRFD only)"})
        m = self.material
        if (m.grade, m.Fy_ksi, m.Fu_ksi, m.E_ksi) != (A992["grade"], A992["Fy_ksi"], A992["Fu_ksi"], A992["E_ksi"]):
            out.append({"code": "unsupported_material", "message": f"material {m.grade} (Fy={m.Fy_ksi}, Fu={m.Fu_ksi}, E={m.E_ksi}) is outside the MVP scope (ASTM A992 only)"})
        if self.section is not None:
            from steelagent import shapes
            if self.section not in shapes.w_shapes().index:
                out.append({"code": "section_not_in_database", "message": f"section label {self.section!r} is not in the AISC Shapes Database v16.0 (W-shapes)"})
            elif self.net_section.An_in2 is not None and self.net_section.An_in2 > float(shapes.get(self.section)["A"]) + 1e-9:
                out.append({"code": "An_exceeds_Ag", "message": f"An = {self.net_section.An_in2} in^2 exceeds Ag = {float(shapes.get(self.section)['A'])} in^2"})
        return out


def validate_case(data: dict) -> DesignCase:
    """Pydantic validation of a dict. Raises pydantic.ValidationError on a hard error."""
    return DesignCase.model_validate(data)


def format_validation_error(err) -> str:
    """Compact, model-readable error text (location: message), used in the one retry prompt."""
    lines = []
    for e in err.errors():
        loc = ".".join(str(x) for x in e["loc"]) or "(root)"
        lines.append(f"- {loc}: {e['msg']}")
    return "\n".join(lines)
