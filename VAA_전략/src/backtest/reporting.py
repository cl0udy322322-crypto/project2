"""백테스트 결과 저장/플로팅.

요구사항 출력:
- weights.csv
- regime_timeline.csv
- daily_returns.csv
- metrics.json
- equity_curve.png (옵션)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd

from src.utils.io import write_csv, write_json


def save_weights_log(weights_log: pd.DataFrame, outdir: Path) -> None:
    write_csv(weights_log, outdir / "weights.csv")


def save_regime_timeline(regime_timeline: pd.DataFrame, outdir: Path) -> None:
    write_csv(regime_timeline, outdir / "regime_timeline.csv")


def save_daily_returns(daily_returns: pd.DataFrame, outdir: Path) -> None:
    write_csv(daily_returns, outdir / "daily_returns.csv")


def save_monthly_returns(monthly_returns: pd.DataFrame, outdir: Path) -> None:
    """월별 수익률을 CSV로 저장합니다."""
    write_csv(monthly_returns, outdir / "monthly_returns.csv")


def save_monthly_returns(monthly_returns: pd.DataFrame, outdir: Path) -> None:
    """월별 수익률(및 월말 equity 등)을 저장합니다."""
    write_csv(monthly_returns, outdir / "monthly_returns.csv")


def save_metrics(metrics: dict[str, Any], outdir: Path) -> None:
    write_json(metrics, outdir / "metrics.json")


def save_equity_plot(equity_curve: pd.Series, outdir: Path) -> None:
    """누적 수익률 곡선을 PNG로 저장합니다."""
    fig = plt.figure(figsize=(10, 4))
    ax = fig.add_subplot(111)
    equity_curve.plot(ax=ax)
    ax.set_title("Equity Curve")
    ax.set_xlabel("Date")
    ax.set_ylabel("Equity")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(outdir / "equity_curve.png", dpi=150)
    plt.close(fig)
