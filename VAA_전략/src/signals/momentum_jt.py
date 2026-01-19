"""모멘텀(월말) 계산.

현재 전략 기본값(ATTACK 선택)은 카나리아와 동일한 가중 모멘텀을 사용합니다.
  score = (R_1M * 12) + (R_3M * 4) + (R_6M * 2) + (R_12M * 1)

참고로, 기존 Jegadeesh & Titman(J&T) 모멘텀도 함수로 남겨둡니다.

요구사항:
- MOM = R_12M(t-1) - R_1M(t)
  (최근 1개월 제외한 11개월 추세)

해석:
- R_12M(t-1): t-1 시점에서의 12개월 누적수익률 = P(t-1)/P(t-13)-1
- R_1M(t): t 시점의 1개월 누적수익률 = P(t)/P(t-1)-1

반환:
- 월말 index를 가진 Series(티커별 모멘텀 점수)
"""

from __future__ import annotations

import pandas as pd


def _simple_return(prices: pd.Series, months: int) -> pd.Series:
  """k개월 누적 단순수익률: P(t)/P(t-k)-1"""
  return prices / prices.shift(months) - 1.0


def weighted_momentum_scores(month_end_prices: pd.DataFrame) -> pd.DataFrame:
  """카나리아와 동일한 가중 모멘텀 점수를 월말 기준으로 계산합니다."""
  if not isinstance(month_end_prices.index, pd.DatetimeIndex):
    raise TypeError("month_end_prices.index must be a DatetimeIndex")

  prices = month_end_prices.sort_index().copy()
  prices.columns = [str(c).upper() for c in prices.columns]

  out: dict[str, pd.Series] = {}
  for t in prices.columns:
    p = prices[t]
    r1 = _simple_return(p, 1)
    r3 = _simple_return(p, 3)
    r6 = _simple_return(p, 6)
    r12 = _simple_return(p, 12)
    out[t] = (r1 * 12.0) + (r3 * 4.0) + (r6 * 2.0) + (r12 * 1.0)

  return pd.DataFrame(out, index=prices.index)


def jt_momentum_scores(month_end_prices: pd.DataFrame) -> pd.DataFrame:
    """각 티커별 J&T 모멘텀 점수를 월말 기준으로 계산합니다."""
    if not isinstance(month_end_prices.index, pd.DatetimeIndex):
        raise TypeError("month_end_prices.index must be a DatetimeIndex")

    prices = month_end_prices.sort_index().copy()
    prices.columns = [str(c).upper() for c in prices.columns]

    r12_t_minus_1 = prices.shift(1) / prices.shift(13) - 1.0
    r1_t = prices / prices.shift(1) - 1.0
    mom = r12_t_minus_1 - r1_t
    return mom
