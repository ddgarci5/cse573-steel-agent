"""Load W-shape properties from the AISC Shapes Database v16.0 (U.S. customary units)."""
from functools import lru_cache
from pathlib import Path
import pandas as pd

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "aisc-shapes-database-v16_0.xlsx"
FIELDS = ["AISC_Manual_Label", "W", "A", "d", "bf", "tw", "tf", "kdes", "bf/2tf", "h/tw",
          "Ix", "Zx", "Sx", "rx", "Iy", "Zy", "Sy", "ry", "J", "Cw", "rts", "ho"]

@lru_cache(maxsize=1)
def w_shapes() -> pd.DataFrame:
    df = pd.read_excel(DB_PATH, sheet_name="Database v16.0")
    df = df[df["Type"] == "W"][FIELDS].copy()
    for c in FIELDS[1:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["label"] = df["AISC_Manual_Label"].str.upper().str.replace("X", "X", regex=False)
    return df.set_index("label")

def get(label: str) -> pd.Series:
    """get('W14X90') or get('W14x90')"""
    return w_shapes().loc[label.upper().replace("×", "X")]
