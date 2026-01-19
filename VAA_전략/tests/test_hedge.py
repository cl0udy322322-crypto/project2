import pandas as pd

from src.portfolio.hedge import apply_hedge_to_weights


def test_apply_hedge_caps_at_20pct_and_sums_to_one() -> None:
    base = pd.Series({"SPY": 0.6, "TLT": 0.4})

    # Ask for 50% hedge, but should be capped at 20%
    w = apply_hedge_to_weights(base, hedge_ticker="SH", hedge_weight=0.50)

    assert abs(float(w.sum()) - 1.0) < 1e-12
    assert 0.199999 <= float(w.get("SH", 0.0)) <= 0.200001

    # Non-hedge should be scaled to 80%
    assert abs(float(w.get("SPY", 0.0)) - 0.6 * 0.8) < 1e-12
    assert abs(float(w.get("TLT", 0.0)) - 0.4 * 0.8) < 1e-12


def test_apply_hedge_preserves_protected_ticker_when_possible() -> None:
    base = pd.Series({"SPY": 0.5, "UUP": 0.5})

    w = apply_hedge_to_weights(base, hedge_ticker="SH", hedge_weight=0.20, protect_tickers=["UUP"])

    assert abs(float(w.sum()) - 1.0) < 1e-12
    assert abs(float(w.get("SH", 0.0)) - 0.20) < 1e-12

    # UUP is protected and should stay at 0.5
    assert abs(float(w.get("UUP", 0.0)) - 0.5) < 1e-12
    # SPY absorbs the scaling needed to make room for the hedge
    assert abs(float(w.get("SPY", 0.0)) - 0.3) < 1e-12
