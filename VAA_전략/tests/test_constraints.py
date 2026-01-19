from __future__ import annotations

import numpy as np
import pandas as pd

from src.portfolio.constraints import apply_floor_cap


def test_apply_floor_enforces_min_weight() -> None:
    w = pd.Series({"SPY": 0.01, "QQQ": 0.49, "IWM": 0.50})
    w2 = apply_floor_cap(w, floor=0.05, cap=None)

    assert np.isclose(float(w2.sum()), 1.0)
    assert (w2 >= 0.05 - 1e-12).all()
