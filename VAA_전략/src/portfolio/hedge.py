"""미세 헷지(인버스 ETF) 정책.

요구사항:
- short_cover_state == ON일 때만 헷지 허용
- zVIX 구간별 hedge weight (0~20%)
- 적용 방식:
  base_weights 산출 후 non_hedge_weights *= (1 - hedge_w), hedge_weight=hedge_w

이 모듈은 "정책 계산"을 담당하며, 순수 함수로 작성합니다.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class HedgeBand:
    z_low: float
    z_high: float
    weight: float


def hedge_weight_from_z(z_vix: float | None, bands: list[HedgeBand]) -> float:
    """z-score에 따라 헷지 비중을 결정합니다."""
    if z_vix is None:
        return 0.0
    z = float(z_vix)
    for b in bands:
        if b.z_low <= z < b.z_high:
            return float(b.weight)
    return 0.0


def apply_hedge_to_weights(
    base_weights: pd.Series,
    hedge_ticker: str,
    hedge_weight: float,
    protect_tickers: list[str] | None = None,
) -> pd.Series:
    """비헷지 자산 weights에 헷지 비중을 포함해 최종 weights로 만듭니다.

    기본 동작은 기존과 동일하게 "전체 비헷지 자산을 (1-hw)로 비례 축소" 입니다.
    단, protect_tickers가 주어지면 해당 자산들은 가능한 한 비중을 유지하고,
    비보호 자산만 축소하여 hedge 비중을 확보합니다.
    """

    w = base_weights.astype(float).copy()
    w.index = [str(i).upper() for i in w.index]
    hedge_t = str(hedge_ticker).upper()

    # 안전장치: 과도한 헷지 비중을 제한 (기본 20%)
    hw = float(max(0.0, min(0.20, hedge_weight)))
    if hw <= 0.0:
        return w

    # base에 hedge_ticker가 이미 있으면 덮어쓰되, 먼저 제거
    if hedge_t in w.index:
        w = w.drop(index=hedge_t)

    if float(w.sum()) <= 0:
        return pd.Series({hedge_t: 1.0}, dtype=float)

    protected = set(str(t).upper() for t in (protect_tickers or []))
    protected.discard(hedge_t)

    protected_idx = [t for t in w.index.tolist() if t in protected]
    non_protected_idx = [t for t in w.index.tolist() if t not in protected]

    if len(protected_idx) == 0:
        # 기존 방식: 전부 비례 축소
        w = w * (1.0 - hw)
        w[hedge_t] = hw
        total = float(w.sum())
        return (w / total) if total > 0 else w

    protected_sum = float(w.loc[protected_idx].sum())
    non_protected_sum = float(w.loc[non_protected_idx].sum())
    remaining_budget_for_non_protected = (1.0 - hw) - protected_sum

    # 보호자산이 너무 큰 경우: 전체를 비례 축소로 fallback
    if remaining_budget_for_non_protected < -1e-12 or non_protected_sum <= 0:
        w = w * (1.0 - hw)
        w[hedge_t] = hw
        total = float(w.sum())
        return (w / total) if total > 0 else w

    scale = remaining_budget_for_non_protected / non_protected_sum
    w.loc[non_protected_idx] = w.loc[non_protected_idx] * scale
    # protected_idx는 그대로 유지

    w[hedge_t] = hw

    total = float(w.sum())
    if total > 0:
        w = w / total
    return w
