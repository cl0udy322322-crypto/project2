"""Risk Parity (실무형: inverse-vol).

요구사항:
- Risk Parity: inverse volatility 방식
  w_i ∝ 1 / sigma_i
- sigma_i는 최근 N개월 월 수익률 표준편차

주의:
- sigma가 0 또는 NaN인 자산은 계산에서 제외합니다.
- 결과는 sum(w)=1로 정규화된 pd.Series 입니다.

이 모듈은 "순수 함수"로 구성합니다.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def inverse_vol_weights(vol: pd.Series) -> pd.Series:
    """변동성 시리즈에서 inverse-vol weights를 계산합니다.

    Args:
        vol: 각 자산의 변동성(표준편차). index는 티커, 값은 양수 기대.

    Returns:
        sum=1, 음수 없는 weights
    """
    if vol is None or len(vol) == 0:
        return pd.Series(dtype=float)

    v = vol.astype(float).copy()
    v.index = v.index.astype(str)

    # 0 또는 음수/결측 제거
    valid = v.replace([np.inf, -np.inf], np.nan).dropna()
    valid = valid[valid > 0]
    if len(valid) == 0:
        return pd.Series(dtype=float)

    inv = 1.0 / valid
    w = inv / inv.sum()

    # 안전장치: -0 제거
    w = w.clip(lower=0.0)
    w = w / w.sum()
    return w
