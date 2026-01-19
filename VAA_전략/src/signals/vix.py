"""VIX z-score 계산(일간).

요구사항:
- VIX: ^VIX
- z = (VIX - rolling_mean) / rolling_std
- window: config (기본 756 trading days)
"""

from __future__ import annotations

import pandas as pd


def vix_zscore(vix_prices: pd.Series, window_days: int) -> pd.Series:
    """VIX(가격 레벨) 시계열에서 z-score를 계산합니다."""
    if not isinstance(vix_prices.index, pd.DatetimeIndex):
        raise TypeError("vix_prices.index must be a DatetimeIndex")

    vix = vix_prices.sort_index().astype(float)
    mean = vix.rolling(window=window_days, min_periods=max(20, window_days // 10)).mean()
    std = vix.rolling(window=window_days, min_periods=max(20, window_days // 10)).std(ddof=0)
    z = (vix - mean) / std
    return z
