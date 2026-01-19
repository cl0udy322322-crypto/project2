"""카나리아 스코어 및 레짐 입력(alive_count) 계산.

요구사항:
- 모멘텀스코어:
  score = (R_1M * 12) + (R_3M * 4) + (R_6M * 2) + (R_12M * 1)
- R_kM은 "월말 가격 기준" k개월 누적수익률(simple return)
- alive: score > 0
- alive_count = alive(BND) + alive(VWO)

입력/출력:
- 입력: 월말 가격 DataFrame (DatetimeIndex)
- 출력: 월말 기준 score/alive/alive_count Series/DataFrame

주의:
- 상장일이 늦은 티커 등 결측은 자연스럽게 NaN으로 남겨두고,
  계산 가능한 구간부터만 신호가 나오도록 합니다.
"""

from __future__ import annotations

import pandas as pd


def _simple_return(prices: pd.Series, months: int) -> pd.Series:
    """k개월 누적 단순수익률: P(t)/P(t-k)-1"""
    return prices / prices.shift(months) - 1.0


def canary_score(month_end_prices: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    """카나리아 티커들의 스코어/알라이브를 월말 기준으로 계산합니다."""
    if not isinstance(month_end_prices.index, pd.DatetimeIndex):
        raise TypeError("month_end_prices.index must be a DatetimeIndex")

    prices = month_end_prices.copy()
    prices.columns = [str(c).upper() for c in prices.columns]

    cols = [t.upper() for t in tickers]
    missing = [c for c in cols if c not in prices.columns]
    if missing:
        raise ValueError(f"Missing canary tickers in prices: {missing}")

    out = {}
    for t in cols:
        p = prices[t]
        r1 = _simple_return(p, 1)
        r3 = _simple_return(p, 3)
        r6 = _simple_return(p, 6)
        r12 = _simple_return(p, 12)
        score = (r1 * 12.0) + (r3 * 4.0) + (r6 * 2.0) + (r12 * 1.0)
        out[f"score_{t}"] = score
        out[f"alive_{t}"] = (score > 0).astype("float")  # NaN은 비교 결과 False가 되므로 주의
        out[f"alive_{t}"] = out[f"alive_{t}"].where(score.notna(), other=pd.NA)

    df = pd.DataFrame(out, index=prices.index)
    alive_cols = [f"alive_{t}" for t in cols]
    df["alive_count"] = df[alive_cols].sum(axis=1, min_count=1)
    return df
