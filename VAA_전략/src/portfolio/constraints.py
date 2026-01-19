"""포트폴리오 제약(Constraints).

요구사항:
- apply_floor_cap(weights: pd.Series, floor: dict|float|None, cap: dict|float|None) -> pd.Series

설계:
- 이 모듈은 순수 함수이며 입력 weights를 복사해서 반환합니다.
- floor/cap은 다음을 허용합니다.
  - None: 적용 안 함
  - float: 모든 자산에 동일 적용
  - dict[str, float]: 티커별 다른 값 적용

주의:
- floor/cap 적용 후 sum(w)=1로 재정규화합니다.
- 모든 weight가 0이 되어버리면(예: 지나친 cap) 0 series를 반환합니다.
"""

from __future__ import annotations

from typing import Mapping

import numpy as np
import pandas as pd


def _resolve_bound(bound: Mapping[str, float] | float | None, index: pd.Index) -> pd.Series | None:
    if bound is None:
        return None
    if isinstance(bound, (int, float)):
        return pd.Series(float(bound), index=index)
    # mapping
    s = pd.Series({str(k): float(v) for k, v in bound.items()})
    return s.reindex(index).fillna(0.0)


def apply_floor_cap(
    weights: pd.Series,
    floor: Mapping[str, float] | float | None,
    cap: Mapping[str, float] | float | None,
) -> pd.Series:
    """weights에 floor/cap 제약을 적용합니다.

    중요한 점:
    - 단순히 `max(floor)` 후 `sum=1`로 정규화하면 floor가 다시 깨질 수 있습니다.
    - 따라서 (lower/upper bound)를 만족하는 범위에서 sum=1이 되도록 재분배를 수행합니다.
    """

    if weights is None or len(weights) == 0:
        return pd.Series(dtype=float)

    w = weights.astype(float).copy()
    w.index = w.index.astype(str)

    # 결측/무한대 제거
    w = w.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    w = w.clip(lower=0.0)

    lower = _resolve_bound(floor, w.index)
    upper = _resolve_bound(cap, w.index)

    if lower is None:
        lower = pd.Series(0.0, index=w.index)
    else:
        lower = lower.clip(lower=0.0)

    if upper is None:
        upper = pd.Series(np.inf, index=w.index)
    else:
        upper = upper.clip(lower=0.0)

    # lower > upper 인 경우는 불가능하므로 upper를 우선
    lower = pd.concat([lower, upper], axis=1).min(axis=1)

    # 1) 우선 bounds로 clip
    w = w.clip(lower=lower, upper=upper)

    # 2) sum=1이 되도록 조정 (bounds 유지)
    target = 1.0
    tol = 1e-12

    # 빠른 종료
    s = float(w.sum())
    if s <= tol:
        return w * 0.0

    # 가능성 체크: sum(lower) <= 1 <= sum(upper)
    sum_lower = float(lower.sum())
    sum_upper = float(upper.replace(np.inf, 1.0).sum()) if np.isinf(float(upper.max())) else float(upper.sum())

    if sum_lower - tol > target:
        # floor 합이 1을 초과하면 해가 없음 -> floor 비례로 정규화(최선의 타협)
        w = lower / sum_lower
        return w

    # sum_upper는 inf가 있으면 충분히 큼. cap 합이 1보다 작은 경우도 처리.
    if not np.isinf(float(upper.max())):
        if sum_upper + tol < target:
            # cap 합이 1보다 작으면 해가 없음 -> cap 비례로 정규화
            if sum_upper <= tol:
                return w * 0.0
            w = upper / sum_upper
            return w

    # 반복 재분배(수렴용)
    for _ in range(200):
        s = float(w.sum())
        diff = target - s
        if abs(diff) <= tol:
            break

        if diff > 0:
            # 더 늘릴 수 있는 자산(upper 여유)에게 배분
            slack = (upper - w).replace(np.inf, np.nan)
            inc_mask = slack > tol
            if not bool(inc_mask.any()):
                # upper가 inf인 자산이 있는 경우 slack이 NaN이므로 따로 처리
                inf_mask = np.isinf(upper.values)
                if inf_mask.any():
                    # inf cap이면 현재 비중 비례로 배분
                    idx_inf = w.index[inf_mask]
                    base = w.loc[idx_inf]
                    if float(base.sum()) <= tol:
                        w.loc[idx_inf] = w.loc[idx_inf] + diff / len(idx_inf)
                    else:
                        w.loc[idx_inf] = w.loc[idx_inf] + diff * (base / float(base.sum()))
                    w = w.clip(lower=lower, upper=upper)
                    continue
                break

            slack = slack.where(inc_mask, other=0.0)
            total_slack = float(slack.sum())
            if total_slack <= tol:
                break
            w = w + diff * (slack / total_slack)
            w = w.clip(lower=lower, upper=upper)
        else:
            # 줄일 수 있는 자산( lower 초과분 )에서 차감
            excess = (w - lower)
            dec_mask = excess > tol
            if not bool(dec_mask.any()):
                break
            excess = excess.where(dec_mask, other=0.0)
            total_excess = float(excess.sum())
            if total_excess <= tol:
                break
            w = w + diff * (excess / total_excess)  # diff는 음수
            w = w.clip(lower=lower, upper=upper)

    # 마지막 수치 안정화
    w = w.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    w = w.clip(lower=0.0)
    s = float(w.sum())
    if s > tol:
        w = w / s
    return w
