"""백테스트 엔진(Quarterly rebalance).

요구사항 핵심:
- 데이터: yfinance Adj Close
- 신호: 월말 1회
- 리밸런싱: 분기 1회 (quarter_start / quarter_end_next_day)
- 레짐: 카나리아(BND,VWO) alive_count
- Short-covering: VIX z-score 상태 머신 (레짐은 안 바꾸고, 헷지 허용 여부만)
- ATTACK: J&T 모멘텀으로 상위 5개 선택 + inverse-vol RP + floor
- NEUTRAL: SPY/QQQ + (방어군 변동성 최저 2개) + UUP, 동일비중
- DEFENSE: (방어군 변동성 최저 2개) + UUP, 동일비중
- 헷지: short-cover ON일 때만 0~20% 인버스 ETF 포함 가능
- 성과/로그/CSV/JSON 저장

설계:
- 이 파일은 "오케스트레이션" 역할(부작용 있음)이며, 계산은 각 모듈로 분리합니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

from src.data.fetch_yahoo import fetch_adj_close
from src.data.transforms import to_daily_returns, to_month_end_prices, to_monthly_returns
from src.portfolio.hedge import HedgeBand, apply_hedge_to_weights, hedge_weight_from_z
from src.portfolio.policies import DEFAULT_UNIVERSE, Universe, compute_base_weights_for_date, policy_config_from_dict
from src.regime.rules import Regime, regime_from_alive_count
from src.regime.state_machine import ShortCoverConfig, simulate_short_cover_timeline
from src.signals.canary import canary_score
from src.signals.momentum_jt import weighted_momentum_scores
from src.signals.vix import vix_zscore
from src.backtest.metrics import compute_equity_curve, compute_metrics, metrics_to_dict
from src.backtest.reporting import (
    save_daily_returns,
    save_equity_plot,
    save_metrics,
    save_monthly_returns,
    save_regime_timeline,
    save_weights_log,
)
from src.utils.dates import RebalanceMode, month_end_trading_days, rebalance_dates
from src.utils.logging import get_logger

logger = get_logger(__name__)


RebalanceModeCli = Literal["quarter_start", "quarter_end_next_day"]


@dataclass(frozen=True)
class BacktestArtifacts:
    weights_log: pd.DataFrame
    regime_timeline: pd.DataFrame
    daily_returns: pd.DataFrame
    metrics: dict[str, Any]


def _all_strategy_tickers(universe: Universe, hedge_ticker: str) -> list[str]:
    tickers = set(universe.canary + universe.attack + universe.neutral + universe.defense)
    tickers.add(str(hedge_ticker).upper())
    # VIX는 별도 데이터로 포함
    tickers.add("^VIX")
    return sorted(tickers)


def _parse_hedge_bands(config: dict[str, Any]) -> list[HedgeBand]:
    bands_raw = config.get("hedge", {}).get("z_bands", [])
    bands: list[HedgeBand] = []
    for triplet in bands_raw:
        if not isinstance(triplet, list) or len(triplet) != 3:
            continue
        z_low, z_high, w = triplet
        bands.append(HedgeBand(float(z_low), float(z_high), float(w)))
    return bands


def _parse_hedge_protect_tickers(config: dict[str, Any]) -> list[str]:
    raw = config.get("hedge", {}).get("protect_tickers", [])
    if not isinstance(raw, list):
        return []
    return [str(t).upper() for t in raw]


def _compute_turnover_cost(prev_w: pd.Series, new_w: pd.Series, total_bps: float) -> float:
    """간단한 거래비용 모델: turnover * bps.

    turnover는 L1 변화량(sum(|Δw|))로 정의합니다.
    """
    if total_bps <= 0:
        return 0.0

    idx = prev_w.index.union(new_w.index)
    pw = prev_w.reindex(idx).fillna(0.0)
    nw = new_w.reindex(idx).fillna(0.0)
    turnover = float((nw - pw).abs().sum())
    return (total_bps / 10000.0) * turnover


def _build_weights_daily(
    daily_index: pd.DatetimeIndex,
    weights_by_rebalance_day: dict[pd.Timestamp, pd.Series],
    hedge_ticker: str,
    hedge_enabled: bool,
    hedge_rebalance_only: bool,
    hedge_bands: list[HedgeBand],
    hedge_protect_tickers: list[str],
    short_cover_state_daily: pd.Series,
    z_vix_daily: pd.Series,
) -> pd.DataFrame:
    """일간 weights를 생성합니다.

    - 기본은 분기 리밸런싱 날짜에만 weights 변경
    - hedge_rebalance_only=False면, 비헷지 weights는 고정하되 hedge 비중만 일간으로 조정 가능
    """
    all_tickers: list[str] = []
    for _, w in weights_by_rebalance_day.items():
        all_tickers.extend(list(w.index))
    if hedge_enabled:
        all_tickers.append(str(hedge_ticker).upper())

    cols = sorted(set([str(c).upper() for c in all_tickers]))
    weights_daily = pd.DataFrame(index=daily_index, columns=cols, dtype=float)

    # 리밸런싱 날에만 값 할당
    for d, w in weights_by_rebalance_day.items():
        if d in weights_daily.index:
            weights_daily.loc[d, w.index] = w.values

    # FutureWarning 대응: fillna(method=...) deprecated
    weights_daily = weights_daily.ffill().fillna(0.0)

    if not hedge_enabled:
        return weights_daily

    if hedge_rebalance_only:
        # 이미 리밸런싱 시점에 반영된 hedge를 그대로 유지
        if str(hedge_ticker).upper() not in weights_daily.columns:
            weights_daily[str(hedge_ticker).upper()] = 0.0
        return weights_daily

    # 일간 hedge 조정 모드: 매일 hedge_w를 다시 계산하고 non-hedge를 (1-hedge_w)로 스케일
    if str(hedge_ticker).upper() not in weights_daily.columns:
        weights_daily[str(hedge_ticker).upper()] = 0.0

    non_hedge_cols = [c for c in weights_daily.columns if c != str(hedge_ticker).upper()]

    for d in weights_daily.index:
        state = str(short_cover_state_daily.get(d, "OFF"))
        if state != "ON":
            hw = 0.0
        else:
            hw = hedge_weight_from_z(float(z_vix_daily.get(d, np.nan)), hedge_bands)

        base = weights_daily.loc[d, non_hedge_cols]
        base = base / float(base.sum()) if float(base.sum()) > 0 else base
        final_w = apply_hedge_to_weights(
            base,
            hedge_ticker=hedge_ticker,
            hedge_weight=hw,
            protect_tickers=hedge_protect_tickers,
        )

        # columns 정합
        weights_daily.loc[d, non_hedge_cols] = final_w.reindex(non_hedge_cols).fillna(0.0).values
        weights_daily.loc[d, str(hedge_ticker).upper()] = float(final_w.get(str(hedge_ticker).upper(), 0.0))

    return weights_daily


def run_backtest(
    config: dict[str, Any],
    start: str,
    end: str,
    outdir: Path,
    plot: bool,
    universe: Universe = DEFAULT_UNIVERSE,
) -> BacktestArtifacts:
    """백테스트 실행(결과 저장 포함)."""

    windows = config.get("windows", {})
    thresholds = config.get("thresholds", {})
    hedge_cfg = config.get("hedge", {})
    costs_cfg = config.get("costs", {})

    hedge_enabled = bool(hedge_cfg.get("enable", True))
    hedge_ticker = str(hedge_cfg.get("ticker", "SH")).upper()
    hedge_rebalance_only = bool(hedge_cfg.get("rebalance_only", True))
    hedge_bands = _parse_hedge_bands(config)
    hedge_protect_tickers = _parse_hedge_protect_tickers(config)

    vix_window_days = int(windows.get("vix_z_window_days", 756))

    sc_config = ShortCoverConfig(
        entry_z=float(thresholds.get("vix_entry_z", 2.0)),
        exit_z=float(thresholds.get("vix_exit_z", 1.5)),
        exit_streak_days=int(thresholds.get("vix_exit_streak_days", 10)),
    )

    rebalance_mode: RebalanceMode = str(config.get("rebalance", {}).get("mode", "quarter_start"))  # type: ignore[assignment]

    tickers = _all_strategy_tickers(universe=universe, hedge_ticker=hedge_ticker)

    # (옵션) yfinance 다운로드용 티커 별칭
    # 예: SOX는 야후에서 지수로 취급되어 실패할 수 있어 SOXX(ETF)로 우회
    ticker_aliases = config.get("ticker_aliases", {})

    # 1) 데이터 다운로드
    data = fetch_adj_close(tickers=tickers, start=start, end=end, ticker_aliases=ticker_aliases).adj_close

    # 2) 일간/월말 변환
    daily_prices = data.copy()
    daily_prices.columns = [str(c).upper() for c in daily_prices.columns]
    daily_prices = daily_prices.loc[(daily_prices.index >= pd.Timestamp(start)) & (daily_prices.index <= pd.Timestamp(end))]

    daily_index = pd.DatetimeIndex(daily_prices.index)
    logger.info("거래일 수: %d", len(daily_index))

    daily_returns_all = to_daily_returns(daily_prices)

    month_end_prices = to_month_end_prices(daily_prices)
    monthly_returns = to_monthly_returns(month_end_prices)

    # 3) 카나리아 alive_count (월말) -> (일간) ffill
    canary_df = canary_score(month_end_prices, tickers=universe.canary)
    alive_count_monthly = canary_df["alive_count"]
    alive_count_daily = alive_count_monthly.reindex(daily_index, method="ffill")

    # 4) 레짐(일간) + VIX z-score(일간)
    regime_daily = alive_count_daily.apply(lambda x: regime_from_alive_count(x) if pd.notna(x) else None)

    vix_col = "^VIX"
    if vix_col not in daily_prices.columns:
        raise ValueError("VIX (^VIX) column missing from downloaded prices")

    z_vix_daily = vix_zscore(daily_prices[vix_col], window_days=vix_window_days)

    # 5) short-cover 상태 머신 시뮬레이션
    sc_timeline = simulate_short_cover_timeline(
        dates=daily_index,
        alive_count_daily=alive_count_daily,
        z_vix_daily=z_vix_daily,
        config=sc_config,
    )
    short_cover_state_daily = sc_timeline["short_cover_state"]

    # 6) 월말 신호 준비(가중 모멘텀: 카나리아와 동일)
    attack_cols = [t.upper() for t in universe.attack]
    attack_mom_scores = weighted_momentum_scores(month_end_prices[attack_cols])

    policy_cfg = policy_config_from_dict(config)

    # 월말(신호) 날짜
    signal_dates = pd.DatetimeIndex(month_end_prices.index)

    # 7) 리밸런싱 날짜
    rb_dates = rebalance_dates(daily_index, mode=rebalance_mode)
    rb_dates = rb_dates[(rb_dates >= pd.Timestamp(start)) & (rb_dates <= pd.Timestamp(end))]
    logger.info("리밸런싱 날짜 수: %d (mode=%s)", len(rb_dates), rebalance_mode)

    # 8) 신호 날짜별 base weights 계산(월말 기준)
    base_weights_by_signal: dict[pd.Timestamp, pd.Series | None] = {}
    meta_by_signal: dict[pd.Timestamp, dict[str, Any]] = {}

    for sd in signal_dates:
        # 월말 레짐은 alive_count_monthly로 판단
        alive = alive_count_monthly.get(sd, np.nan)
        r = regime_from_alive_count(alive)
        if r is None:
            base_weights_by_signal[pd.Timestamp(sd)] = None
            meta_by_signal[pd.Timestamp(sd)] = {"signal_date": pd.Timestamp(sd), "regime": None, "reason": "no_regime"}
            continue

        w, meta = compute_base_weights_for_date(
            signal_date=pd.Timestamp(sd),
            regime=r,
            monthly_returns=monthly_returns,
            mom_scores=attack_mom_scores,
            universe=universe,
            config=policy_cfg,
        )
        base_weights_by_signal[pd.Timestamp(sd)] = w
        meta_by_signal[pd.Timestamp(sd)] = meta

    # 9) 리밸런싱 날짜별 최종 weights 확정(헷지 포함 가능)
    behavior_mode = str(config.get("behavior_on_missing", {}).get("mode", "carry_forward"))

    weights_by_rb_day: dict[pd.Timestamp, pd.Series] = {}
    weights_log_rows: list[dict[str, Any]] = []

    prev_weights = pd.Series(dtype=float)

    for d in rb_dates:
        # 리밸런싱 날짜에 사용할 최신 월말 신호 날짜
        prior_signals = signal_dates[signal_dates <= d]
        if len(prior_signals) == 0:
            # 신호가 아직 없다면: cash 또는 carry_forward
            if behavior_mode == "cash":
                w_final = pd.Series(dtype=float)
                reason = "no_signal_cash"
            else:
                w_final = prev_weights.copy()
                reason = "no_signal_carry"

            weights_by_rb_day[pd.Timestamp(d)] = w_final
            weights_log_rows.append({"rebalance_date": pd.Timestamp(d), "signal_date": pd.NaT, "reason": reason})
            prev_weights = w_final
            continue

        sd = pd.Timestamp(prior_signals.max())
        base_w = base_weights_by_signal.get(sd, None)
        meta = meta_by_signal.get(sd, {})

        if base_w is None or len(base_w) == 0 or float(base_w.sum()) <= 0:
            if behavior_mode == "cash":
                w_final = pd.Series(dtype=float)
                reason = f"missing_base_cash:{meta.get('reason', 'unknown')}"
            else:
                w_final = prev_weights.copy()
                reason = f"missing_base_carry:{meta.get('reason', 'unknown')}"
        else:
            w_final = base_w.copy()
            reason = "ok"

        # 헷지 비중(리밸런싱 시점) 반영 (rebalance_only=True인 기본 설정)
        if hedge_enabled:
            state = str(short_cover_state_daily.get(d, "OFF"))
            if state == "ON":
                z = float(z_vix_daily.get(d, np.nan))
                hw = hedge_weight_from_z(z, hedge_bands)
            else:
                hw = 0.0

            if hw > 0:
                w_final = apply_hedge_to_weights(
                    w_final,
                    hedge_ticker=hedge_ticker,
                    hedge_weight=hw,
                    protect_tickers=hedge_protect_tickers,
                )

        weights_by_rb_day[pd.Timestamp(d)] = w_final
        prev_weights = w_final

        weights_log_rows.append(
            {
                "rebalance_date": pd.Timestamp(d),
                "signal_date": sd,
                "regime": meta.get("regime", None),
                "short_cover_state": str(short_cover_state_daily.get(d, "OFF")),
                "z_vix": float(z_vix_daily.get(d, np.nan)),
                "selected_assets": ",".join(meta.get("selected_assets", [])) if isinstance(meta.get("selected_assets", []), list) else None,
                "used_assets": ",".join(meta.get("used_assets", [])) if isinstance(meta.get("used_assets", []), list) else None,
                "excluded_assets": ",".join(meta.get("excluded_assets", [])) if isinstance(meta.get("excluded_assets", []), list) else None,
                "reason": reason,
                **{f"w_{k}": float(v) for k, v in w_final.items()},
            }
        )

    weights_log = pd.DataFrame(weights_log_rows).set_index("rebalance_date").sort_index()

    # 10) 일간 weights 생성
    weights_daily = _build_weights_daily(
        daily_index=daily_index,
        weights_by_rebalance_day=weights_by_rb_day,
        hedge_ticker=hedge_ticker,
        hedge_enabled=hedge_enabled,
        hedge_rebalance_only=hedge_rebalance_only,
        hedge_bands=hedge_bands,
        hedge_protect_tickers=hedge_protect_tickers,
        short_cover_state_daily=short_cover_state_daily,
        z_vix_daily=z_vix_daily,
    )

    # 11) 포트폴리오 일간 수익률 계산
    # 투자대상 컬럼: VIX는 제외, 실제 ETF들만 사용
    invest_cols = [c for c in daily_returns_all.columns if c != "^VIX"]
    weights_daily = weights_daily.reindex(columns=invest_cols, fill_value=0.0)

    port_ret = (weights_daily * daily_returns_all[invest_cols].fillna(0.0)).sum(axis=1)

    # 거래비용(변화한 날만)
    total_bps = float(costs_cfg.get("fee_bps", 0.0)) + float(costs_cfg.get("slippage_bps", 0.0))
    costs = []
    prev_w_day = pd.Series(dtype=float)
    for d in weights_daily.index:
        w_day = weights_daily.loc[d].astype(float)
        c = _compute_turnover_cost(prev_w_day, w_day, total_bps=total_bps)
        costs.append(c)
        prev_w_day = w_day

    cost_series = pd.Series(costs, index=weights_daily.index, name="cost")
    port_ret_net = port_ret - cost_series
    port_ret_net.name = "portfolio_return"

    equity = compute_equity_curve(port_ret_net)

    daily_out = pd.DataFrame(
        {
            "portfolio_return": port_ret_net,
            "equity": equity,
            "cost": cost_series,
        },
        index=daily_index,
    )

    # 월별 수익률(월말=해당 월 마지막 거래일 기준)
    equity_me = equity.groupby(equity.index.to_period("M")).tail(1)
    month_ret = equity_me.pct_change().fillna(0.0)
    month_ret.name = "month_return"
    monthly_out = pd.DataFrame({"month_return": month_ret, "equity": equity_me}, index=equity_me.index)

    # 12) 레짐 타임라인 저장용 DF
    regime_timeline = pd.DataFrame(
        {
            "regime": regime_daily.astype(object),
            "alive_count": alive_count_daily,
            "z_vix": z_vix_daily,
            "short_cover_state": short_cover_state_daily,
            "exit_streak": sc_timeline["exit_streak"],
        },
        index=daily_index,
    )

    # 13) 지표 계산
    metrics = metrics_to_dict(compute_metrics(port_ret_net))

    # 14) 저장
    save_weights_log(weights_log, outdir)
    save_regime_timeline(regime_timeline, outdir)
    save_daily_returns(daily_out, outdir)
    save_monthly_returns(monthly_out, outdir)
    save_metrics(metrics, outdir)
    if plot:
        save_equity_plot(equity, outdir)

    logger.info("레짐 분포(일간): %s", regime_timeline["regime"].value_counts(dropna=False).to_dict())

    return BacktestArtifacts(
        weights_log=weights_log,
        regime_timeline=regime_timeline,
        daily_returns=daily_out,
        metrics=metrics,
    )
