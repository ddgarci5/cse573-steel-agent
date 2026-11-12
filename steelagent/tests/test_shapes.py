from steelagent import shapes


def test_w_shape_database_loads():
    df = shapes.w_shapes()
    assert len(df) == 289                      # Dataset A: 289 W-shapes (CLAUDE.md section 6)
    assert df[["A", "Ix", "Zx", "ry", "rts", "J", "ho"]].notna().all().all()


def test_label_lookup_is_case_insensitive():
    assert shapes.get("W14x90")["W"] == shapes.get("W14X90")["W"] == 90
