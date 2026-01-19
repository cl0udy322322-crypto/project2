"""날짜 관련 유틸.

핵심:
- 거래일(daily) 인덱스에서 "월말(해당 월의 마지막 거래일)"을 안전하게 추출
- 분기 리밸런싱 날짜 계산(분기 첫 거래일/분기말 다음 거래일)

주의:
- 금융 데이터는 휴장/결측이 있기 때문에, 캘린더 기반 month-end가 실제 거래일과 다를 수 있습니다.
  따라서 항상 "데이터에 존재하는 마지막 거래일"을 기준으로 처리합니다.
"""

from __future__ import annotations

from typing import Literal

import pandas as pd


def month_end_trading_days(daily_index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """일간 거래일 인덱스에서 각 월의 마지막 거래일만 뽑아 반환합니다."""
    if len(daily_index) == 0:
        return pd.DatetimeIndex([])

    idx = pd.DatetimeIndex(daily_index).sort_values().unique()
    # 각 월(period) 그룹의 마지막 날짜를 그대로 반환 (실제 마지막 거래일)
    last = pd.Series(1, index=idx).groupby(idx.to_period("M")).tail(1)
    return pd.DatetimeIndex(last.index)


RebalanceMode = Literal["quarter_start", "quarter_end_next_day"]


def rebalance_dates(
    daily_index: pd.DatetimeIndex,
    mode: RebalanceMode,
) -> pd.DatetimeIndex:
    """분기 리밸런싱 날짜를 계산합니다.

    - quarter_start: 분기 첫 거래일
    - quarter_end_next_day: 분기 말(마지막 거래일) "다음" 거래일

    반환:
    - daily_index 내의 날짜들로만 구성된 DatetimeIndex
    """
    if len(daily_index) == 0:
        return pd.DatetimeIndex([])

    idx = pd.DatetimeIndex(daily_index).sort_values().unique()
    df = pd.DataFrame(index=idx)
    df["month"] = df.index.to_period("M")
    df["quarter"] = df.index.to_period("Q")

    if mode == "quarter_start":
        # 각 분기별 첫 거래일
        first = df.groupby("quarter").head(1)
        return pd.DatetimeIndex(first.index)

    if mode == "quarter_end_next_day":
        # 각 분기별 마지막 거래일 -> 그 다음 거래일
        last = df.groupby("quarter").tail(1)
        last_dates = pd.DatetimeIndex(last.index)
        next_dates: list[pd.Timestamp] = []
        idx_set = set(idx)
        for d in last_dates:
            # 다음 거래일은 idx에서 d 이후 첫 날짜
            future = idx[idx > d]
            if len(future) == 0:
                continue
            next_day = future[0]
            if next_day in idx_set:
                next_dates.append(next_day)
        return pd.DatetimeIndex(next_dates)

    raise ValueError(f"Unknown rebalance mode: {mode}")
