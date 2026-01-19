"""성과지표 계산.

요구사항:
- CAGR / Vol / Sharpe / MDD

입력:
- daily_returns: 포트폴리오 일간 수익률 Series

주의:
- Sharpe는 무위험수익률 0 가정
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class PerformanceMetrics:
    cagr: float
    vol: float
    sharpe: float
    mdd: float


def compute_equity_curve(daily_returns: pd.Series, initial: float = 1.0) -> pd.Series:
    """일간 수익률에서 누적수익률 곡선(자산가치)을 계산합니다."""
    r = daily_returns.fillna(0.0).astype(float)
    equity = (1.0 + r).cumprod() * float(initial)
    equity.name = "equity"
    return equity


def compute_mdd(equity_curve: pd.Series) -> float:
    """최대 낙폭(Max Drawdown)."""
    eq = equity_curve.astype(float)
    peak = eq.cummax()
    dd = (eq / peak) - 1.0
    return float(dd.min())


def compute_metrics(daily_returns: pd.Series, trading_days_per_year: int = 252) -> PerformanceMetrics:
    """성과지표(CAGR/Vol/Sharpe/MDD) 계산."""
    r = daily_returns.fillna(0.0).astype(float)
    if len(r) == 0:
        return PerformanceMetrics(cagr=0.0, vol=0.0, sharpe=0.0, mdd=0.0)

    equity = compute_equity_curve(r)
    n = len(r)
    years = n / float(trading_days_per_year)

    end_value = float(equity.iloc[-1])
    start_value = float(equity.iloc[0])
    if start_value <= 0 or end_value <= 0 or years <= 0:
        cagr = 0.0
    else:
        cagr = (end_value / start_value) ** (1.0 / years) - 1.0

    vol = float(r.std(ddof=0) * math.sqrt(trading_days_per_year))
    mean_ann = float(r.mean() * trading_days_per_year)

    if vol > 0:
        sharpe = mean_ann / vol
    else:
        sharpe = 0.0

    mdd = compute_mdd(equity)
    return PerformanceMetrics(cagr=float(cagr), vol=float(vol), sharpe=float(sharpe), mdd=float(mdd))


def metrics_to_dict(m: PerformanceMetrics) -> dict[str, float]:
    return {"CAGR": m.cagr, "Vol": m.vol, "Sharpe": m.sharpe, "MDD": m.mdd}
