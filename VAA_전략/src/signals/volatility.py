"""변동성 추정(월간) 관련 함수.

요구사항:
- Risk Parity에서 sigma_i는 최근 N개월 월 수익률 표준편차
"""

from __future__ import annotations

import pandas as pd


def rolling_monthly_vol(monthly_returns: pd.DataFrame, window_months: int) -> pd.DataFrame:
    """월간 수익률에서 롤링 표준편차를 계산합니다."""
    if not isinstance(monthly_returns.index, pd.DatetimeIndex):
        raise TypeError("monthly_returns.index must be a DatetimeIndex")

    rets = monthly_returns.sort_index().astype(float)
    vol = rets.rolling(window=window_months, min_periods=max(3, window_months // 2)).std(ddof=0)
    return vol
