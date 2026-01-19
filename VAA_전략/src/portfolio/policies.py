"""포트폴리오 정책(레짐별 유니버스/선정/비중 산출).

요구사항 요약:
- 유니버스는 고정
- ATTACK: 카나리아와 동일한 가중 모멘텀(1/3/6/12M 가중)으로 7개 중 하위 2개 제거, 상위 5개 선택
- 가중치는 inverse-vol RP (월간 변동성 기준)
- ATTACK 추가 제약: 선택된 각 자산 최소 5% floor
- NEUTRAL: SPY, QQQ + (방어군 중 변동성 최저 2개) + UUP, 총 5개를 동일비중(1/N)으로 고정
- DEFENSE: (방어군 중 변동성 최저 2개) + UUP, 총 3개를 동일비중(1/N)으로 고정

참고:
- 변동성은 최근 N개월 월간 수익률 표준편차로 계산합니다.
- UUP는 별도로 항상 포함(가능한 경우)하며, 저변동성 2개 선정에서는 제외합니다.

설계:
- 이 모듈은 "정책"만 담당하고, 데이터 다운로드/리샘플링/상태머신은 다른 모듈이 담당합니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd

from src.portfolio.constraints import apply_floor_cap
from src.portfolio.risk_parity import inverse_vol_weights

Regime = Literal["ATTACK", "NEUTRAL", "DEFENSE"]


@dataclass(frozen=True)
class Universe:
    canary: list[str]
    attack: list[str]
    neutral: list[str]
    defense: list[str]


DEFAULT_UNIVERSE = Universe(
    canary=["BND", "VWO"],
    attack=["SPY", "QQQ", "IWM", "EWJ", "EEM", "VGK", "SOX"],
    neutral=["SPY", "QQQ", "TLT", "LQD", "GLD"],
    defense=["GLD", "DBC", "LQD", "TLT", "HYG", "UUP"],
)


@dataclass(frozen=True)
class SelectionConfig:
    attack_drop_bottom_n: int
    attack_min_weight: float
    neutral_attack_tickers: list[str]
    low_vol_defense_n: int


@dataclass(frozen=True)
class RiskParityConfig:
    vol_window_months: int


@dataclass(frozen=True)
class OptionalBoundsConfig:
    floor: dict[str, float] | float | None
    cap: dict[str, float] | float | None


@dataclass(frozen=True)
class PolicyConfig:
    selection: SelectionConfig
    rp: RiskParityConfig
    neutral_bounds: OptionalBoundsConfig
    defense_bounds: OptionalBoundsConfig


def _pick_attack_assets(
    mom_row: pd.Series,
    drop_bottom_n: int,
    target_n: int = 5,
) -> list[str]:
    """ATTACK 유니버스에서 모멘텀 기반 상위 target_n 선택."""
    s = mom_row.dropna().astype(float).sort_values(ascending=False)
    if len(s) == 0:
        return []

    if drop_bottom_n > 0 and len(s) > drop_bottom_n:
        s = s.iloc[:-drop_bottom_n]

    return [str(t).upper() for t in s.head(target_n).index.tolist()]


def _equal_weight(tickers: list[str]) -> pd.Series:
    cols = [str(t).upper() for t in tickers]
    cols = [c for c in cols if c]
    cols = list(dict.fromkeys(cols))
    if len(cols) == 0:
        return pd.Series(dtype=float)
    w = pd.Series(1.0 / len(cols), index=cols, dtype=float)
    return w


def _pick_low_vol_assets(
    monthly_returns: pd.DataFrame,
    end_date: pd.Timestamp,
    candidates: list[str],
    window: int,
    n: int,
) -> list[str]:
    """최근 window개월 월간 수익률 표준편차가 가장 낮은 n개를 선택합니다."""
    if n <= 0:
        return []

    rets = monthly_returns.copy()
    rets.columns = [str(c).upper() for c in rets.columns]
    cols = [str(c).upper() for c in candidates]
    cols = [c for c in cols if c in rets.columns]
    if len(cols) == 0:
        return []

    window_rets = _rolling_window_slice(rets[cols], end_date=end_date, window=window)
    vol = window_rets.std(axis=0, ddof=0).dropna().astype(float)
    vol = vol[vol > 0]
    if len(vol) == 0:
        return []

    picked = vol.sort_values(ascending=True).head(n).index.tolist()
    return [str(t).upper() for t in picked]


def _rolling_window_slice(df: pd.DataFrame, end_date: pd.Timestamp, window: int) -> pd.DataFrame:
    """end_date까지 포함해 마지막 window rows를 잘라 반환."""
    sliced = df.loc[:end_date].tail(window)
    return sliced


def compute_base_weights_for_date(
    signal_date: pd.Timestamp,
    regime: Regime,
    monthly_returns: pd.DataFrame,
    mom_scores: pd.DataFrame,
    universe: Universe,
    config: PolicyConfig,
) -> tuple[pd.Series | None, dict[str, Any]]:
    """신호 날짜(월말) 기준으로 "비헷지" base weights를 계산합니다.

    Returns:
        (weights_or_none, meta)

    meta에는 selected_assets 등 디버깅/리포팅에 필요한 정보를 담습니다.
    """
    meta: dict[str, Any] = {
        "signal_date": pd.Timestamp(signal_date),
        "regime": regime,
        "selected_assets": [],
        "used_assets": [],
        "excluded_assets": [],
        "reason": "ok",
    }

    # 1) 유니버스 결정
    if regime == "ATTACK":
        mom_row = mom_scores.loc[signal_date, [t.upper() for t in universe.attack]]
        selected = _pick_attack_assets(
            mom_row=mom_row,
            drop_bottom_n=config.selection.attack_drop_bottom_n,
            target_n=5,
        )
        meta["selected_assets"] = selected
        candidates = selected
    elif regime == "NEUTRAL":
        neutral_attack = [t.upper() for t in config.selection.neutral_attack_tickers]
        defense_pool = [t.upper() for t in universe.defense if str(t).upper() != "UUP"]
        lowvol = _pick_low_vol_assets(
            monthly_returns=monthly_returns,
            end_date=pd.Timestamp(signal_date),
            candidates=defense_pool,
            window=config.rp.vol_window_months,
            n=int(config.selection.low_vol_defense_n),
        )
        uup = ["UUP"] if "UUP" in {t.upper() for t in universe.defense} else []
        candidates = list(dict.fromkeys(neutral_attack + lowvol + uup))
        meta["selected_assets"] = candidates
    elif regime == "DEFENSE":
        defense_pool = [t.upper() for t in universe.defense if str(t).upper() != "UUP"]
        lowvol = _pick_low_vol_assets(
            monthly_returns=monthly_returns,
            end_date=pd.Timestamp(signal_date),
            candidates=defense_pool,
            window=config.rp.vol_window_months,
            n=int(config.selection.low_vol_defense_n),
        )
        uup = ["UUP"] if "UUP" in {t.upper() for t in universe.defense} else []
        candidates = list(dict.fromkeys(lowvol + uup))
        meta["selected_assets"] = candidates
    else:
        raise ValueError(f"Unknown regime: {regime}")

    if len(candidates) == 0:
        meta["reason"] = "no_candidates"
        return None, meta

    # 2) weights 산출
    if regime == "ATTACK":
        # 변동성 추정(월간 수익률 기반) -> inverse-vol RP
        rets = monthly_returns.copy()
        rets.columns = [str(c).upper() for c in rets.columns]
        try:
            window_rets = _rolling_window_slice(rets[candidates], end_date=pd.Timestamp(signal_date), window=config.rp.vol_window_months)
        except KeyError:
            meta["reason"] = "missing_returns_columns"
            return None, meta

        if len(window_rets) < max(3, config.rp.vol_window_months // 2):
            meta["reason"] = "insufficient_history"
            return None, meta

        vol = window_rets.std(axis=0, ddof=0)
        w = inverse_vol_weights(vol)
        if len(w) == 0:
            meta["reason"] = "invalid_vol"
            return None, meta

        # 실제로 포트폴리오에 반영된 자산(변동성 계산 불가/결측은 제외될 수 있음)
        used = [str(t).upper() for t in w.index.tolist()]
        meta["used_assets"] = used
        meta["excluded_assets"] = [t for t in candidates if t not in set(used)]

        # 선택 자산 모두 동일 floor 적용
        w = apply_floor_cap(w, floor=float(config.selection.attack_min_weight), cap=None)
    else:
        # NEUTRAL/DEFENSE는 동일비중 고정
        rets = monthly_returns.copy()
        rets.columns = [str(c).upper() for c in rets.columns]
        available = [t for t in candidates if t in set(rets.columns)]
        if len(available) == 0:
            meta["reason"] = "missing_returns_columns"
            return None, meta
        w = _equal_weight(available)
        meta["used_assets"] = list(w.index)
        meta["excluded_assets"] = [t for t in candidates if t not in set(w.index)]

    # 정규화 보장
    if float(w.sum()) > 0:
        w = w / float(w.sum())

    return w, meta


def policy_config_from_dict(config: dict[str, Any]) -> PolicyConfig:
    """YAML dict -> PolicyConfig 변환."""
    windows = config.get("windows", {})
    selection = config.get("selection", {})

    # NEUTRAL/DEFENSE floor/cap은 "옵션"이라 config에 없어도 됩니다.
    neutral_bounds = config.get("neutral_bounds", {})
    defense_bounds = config.get("defense_bounds", {})

    return PolicyConfig(
        selection=SelectionConfig(
            attack_drop_bottom_n=int(selection.get("attack_drop_bottom_n", 2)),
            attack_min_weight=float(selection.get("attack_min_weight", 0.05)),
            neutral_attack_tickers=[str(t).upper() for t in selection.get("neutral_attack_tickers", ["SPY", "QQQ"])],
            low_vol_defense_n=int(selection.get("low_vol_defense_n", 2)),
        ),
        rp=RiskParityConfig(vol_window_months=int(windows.get("rp_vol_window_months", 12))),
        neutral_bounds=OptionalBoundsConfig(
            floor=neutral_bounds.get("floor", None),
            cap=neutral_bounds.get("cap", None),
        ),
        defense_bounds=OptionalBoundsConfig(
            floor=defense_bounds.get("floor", None),
            cap=defense_bounds.get("cap", None),
        ),
    )
