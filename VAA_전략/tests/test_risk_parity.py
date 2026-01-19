from __future__ import annotations

import numpy as np
import pandas as pd

from src.portfolio.risk_parity import inverse_vol_weights


def test_inverse_vol_weights_sum_to_one_and_non_negative() -> None:
    vol = pd.Series({"A": 0.2, "B": 0.1, "C": 0.3})
    w = inverse_vol_weights(vol)

    assert np.isclose(float(w.sum()), 1.0)
    assert (w >= 0).all()
    # 변동성이 낮은 B가 더 큰 비중을 가져야 함
    assert w["B"] > w["A"]
