"""DesignCase schema: validation rules (hard errors), domain flags, missing-field handling. Synthetic cases only (no LLM, no Dataset C)."""
import pytest
from pydantic import ValidationError

from agent.design_case import DesignCase, format_validation_error, normalize_section


def case(**kw):
    base = {"member_type": "compression", "task": "check_given_section", "section": "W14X90",
            "geometry": {"Lcx_ft": 30, "Lcy_ft": 15}}
    base.update(kw)
    return DesignCase.model_validate(base)


def test_defaults_are_a992_lrfd():
    c = case()
    assert (c.design_method, c.material.grade, c.material.Fy_ksi, c.material.Fu_ksi, c.material.E_ksi) == ("LRFD", "ASTM A992", 50.0, 65.0, 29000.0)
    assert c.flags() == [] and c.effective_missing_fields() == []


def test_section_label_formatting_only():
    assert normalize_section(" w14x90 ") == "W14X90"
    assert normalize_section("W14×90") == "W14X90"
    assert case(section="w14x90").section == "W14X90"


def test_nonexistent_section_is_flagged_not_corrected():
    c = case(section="W14X133")          # no such shape: must stay as written and be flagged
    assert c.section == "W14X133"
    assert [f["code"] for f in c.flags()] == ["section_not_in_database"]
    assert [f["code"] for f in case(section="HSS6X6X1/4").flags()] == ["section_not_in_database"]


@pytest.mark.parametrize("patch", [
    {"geometry": {"Lcx_ft": 3000, "Lcy_ft": 15}},          # plausible-range: 3,000 ft (inches typed as feet)
    {"geometry": {"Lcx_ft": -5, "Lcy_ft": 15}},
    {"geometry": {"Lcx_ft": "30 ft", "Lcy_ft": 15}},       # a unit string instead of a number
    {"demands": {"Pu_kip": 0}},
    {"demands": {"Pu_kip": 1e9}},
    {"net_section": {"U": 1.5}},
    {"geometry": {"Lcx_ft": 30, "Lcy_ft": 15, "Cb": 0.5}},
    {"constraints": {"nominal_depth_in": 14.5}},
    {"member_type": "column"},
    {"task": "design"},
    {"unknown_key": 1},
    {"geometry": {"Lcx_ft": 30, "Lcy_ft": 15, "K": 1.0}},   # unknown nested key
])
def test_hard_validation_errors(patch):
    with pytest.raises(ValidationError):
        case(**patch)


def test_required_null_input_must_be_listed_in_missing_fields_and_is_never_defaulted():
    with pytest.raises(ValidationError) as e:
        case(geometry={"Lcx_ft": 30})                      # Lcy missing, not declared
    assert "Lcy_ft" in format_validation_error(e.value)
    c = case(geometry={"Lcx_ft": 30}, missing_fields=["Lcy_ft"])
    assert c.geometry.Lcy_ft is None                       # not filled
    assert c.effective_missing_fields() == ["Lcy_ft"]


def test_declared_missing_field_with_a_value_is_an_error():
    with pytest.raises(ValidationError):
        case(missing_fields=["Lcx_ft"])
    with pytest.raises(ValidationError):
        case(missing_fields=["Fy"])                        # unknown name


def test_cb_required_only_when_lb_not_zero():
    base = {"member_type": "flexure", "task": "check_given_section", "section": "W18X50"}
    c0 = DesignCase.model_validate({**base, "geometry": {"Lb_ft": 0}})            # Lb = 0: Cb not needed
    assert c0.effective_missing_fields() == []
    with pytest.raises(ValidationError):
        DesignCase.model_validate({**base, "geometry": {"Lb_ft": 11.7}})          # Lb > 0 and Cb null
    c1 = DesignCase.model_validate({**base, "geometry": {"Lb_ft": 11.7}, "missing_fields": ["Cb"]})
    assert c1.effective_missing_fields() == ["Cb"]
    with pytest.raises(ValidationError):
        DesignCase.model_validate({**base})                                       # Lb unknown: must be declared
    assert DesignCase.model_validate({**base, "missing_fields": ["Cb", "Lb_ft"]}).effective_missing_fields() == ["Cb", "Lb_ft"]


def test_tension_rupture_needs_an_and_u_only_when_rupture_is_requested():
    base = {"member_type": "tension", "task": "check_given_section", "section": "W8X21"}
    assert DesignCase.model_validate({**base, "requested_limit_states": ["tension_yield"]}).effective_missing_fields() == []
    with pytest.raises(ValidationError):
        DesignCase.model_validate({**base, "requested_limit_states": ["tension_rupture"]})
    with pytest.raises(ValidationError):                                           # unspecified = every limit state, so rupture inputs are needed
        DesignCase.model_validate({**base})
    ok = DesignCase.model_validate({**base, "missing_fields": ["An_in2", "U"]})
    assert ok.effective_missing_fields() == ["An_in2", "U"]


def test_selection_requires_demand_and_geometry():
    with pytest.raises(ValidationError):
        DesignCase.model_validate({"member_type": "compression", "task": "select_lightest", "geometry": {"Lcx_ft": 30, "Lcy_ft": 30}})
    c = DesignCase.model_validate({"member_type": "compression", "task": "select_lightest", "demands": {"Pu_kip": 840},
                                   "geometry": {"Lcx_ft": 30, "Lcy_ft": 30}, "constraints": {"nominal_depth_in": 14}})
    assert c.effective_missing_fields() == [] and c.flags() == []


def test_unsupported_scope_is_flagged():
    c = DesignCase.model_validate({"member_type": "shear", "task": "select_lightest"})
    assert [f["code"] for f in c.flags()] == ["unsupported_combination"]
    c = case(design_method="ASD", material={"grade": "ASTM A36", "Fy_ksi": 36, "Fu_ksi": 58})
    assert {f["code"] for f in c.flags()} == {"unsupported_design_method", "unsupported_material"}


def test_net_area_cannot_exceed_gross_area():
    c = DesignCase.model_validate({"member_type": "tension", "task": "check_given_section", "section": "W8X21",
                                   "net_section": {"An_in2": 50.0, "U": 0.9}, "requested_limit_states": ["tension_rupture"]})
    assert [f["code"] for f in c.flags()] == ["An_exceeds_Ag"]
