"""데이터 변환(순수 함수).

요구사항:
- 거래일 인덱스는 일간(daily)로 유지
- 신호 계산은 월말(month-end)로 리샘플링
- 월말 리샘플: resample('M') 후 last, 단 거래일 기준으로 안전 처리

이 파일은 가능한 한 "순수 함수"로 작성합니다.
"""

from __future__ import annotations

import pandas as pd


def to_daily_returns(adj_close: pd.DataFrame) -> pd.DataFrame:
    """Adj Close -> 일간 단순 수익률."""
    if not isinstance(adj_close.index, pd.DatetimeIndex):
        raise TypeError("adj_close.index must be a DatetimeIndex")

    prices = adj_close.sort_index()
    # FutureWarning 대응: 기본 fill_method='pad'가 deprecated
    daily_ret = prices.pct_change(fill_method=None)
    return daily_ret


def to_month_end_prices(adj_close: pd.DataFrame) -> pd.DataFrame:
    """Adj Close(일간) -> 월말(각 월의 마지막 거래일) 가격."""
    if not isinstance(adj_close.index, pd.DatetimeIndex):
        raise TypeError("adj_close.index must be a DatetimeIndex")

    prices = adj_close.sort_index()
    # 주의:
    # - `resample('M').last()`는 인덱스 라벨이 달력 월말(예: 2020-02-29)로 생성될 수 있습니다.
    # - 하지만 실제 거래일 데이터의 마지막 거래일은 2020-02-28일 수 있으며,
    #   이후 일간 데이터로 ffill할 때 신호가 "한 달 늦게" 전파되는 문제가 생깁니다.
    #
    # 따라서 "각 월의 마지막 거래일" 자체를 인덱스로 유지하도록 구현합니다.
    me = prices.groupby(prices.index.to_period("M")).tail(1)
    me.index = pd.DatetimeIndex(me.index)
    return me


def to_monthly_returns(month_end_prices: pd.DataFrame) -> pd.DataFrame:
    """월말 가격 -> 월간 단순 수익률."""
    if not isinstance(month_end_prices.index, pd.DatetimeIndex):
        raise TypeError("month_end_prices.index must be a DatetimeIndex")

    prices = month_end_prices.sort_index()
    monthly_ret = prices.pct_change(fill_method=None)
    return monthly_ret
