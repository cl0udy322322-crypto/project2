"""yfinance 기반 데이터 다운로드.

요구사항:
- 데이터 소스: yfinance
- 가격: Adj Close 사용
- VIX: ^VIX

주의:
- yfinance는 네트워크/야후 측 제한으로 실패할 수 있으므로, 최소한의 예외 메시지를 제공합니다.
- 반환되는 인덱스는 DatetimeIndex(일간)이며, 정렬되어 있어야 합니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

import pandas as pd
import yfinance as yf

from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class YahooFetchResult:
    adj_close: pd.DataFrame


def fetch_adj_close(
    tickers: Iterable[str],
    start: str,
    end: str,
    ticker_aliases: Mapping[str, str] | None = None,
) -> YahooFetchResult:
    """여러 티커의 Adj Close를 다운로드합니다."""
    raw = [str(t).strip() for t in tickers if str(t).strip()]
    aliases = {str(k).upper(): str(v).upper() for k, v in (ticker_aliases or {}).items()}
    # 내부적으로는 alias로 실제 다운로드를 수행하되,
    # 최종 DataFrame 컬럼은 "원래 요청 티커"를 유지하도록 설계합니다.
    requested = [t.upper() for t in raw]
    download_list = [aliases.get(t, t) for t in requested]
    ticker_list = sorted(set(download_list))
    if len(ticker_list) == 0:
        raise ValueError("tickers is empty")

    logger.info("yfinance 다운로드 시작: tickers=%d start=%s end=%s", len(ticker_list), start, end)
    df = yf.download(
        tickers=ticker_list,
        start=start,
        end=end,
        auto_adjust=False,
        progress=False,
        group_by="column",
        threads=True,
    )

    if df is None or len(df) == 0:
        raise RuntimeError("yfinance download returned empty data")

    # 단일 티커 vs 멀티 티커에 따라 컬럼 구조가 달라질 수 있음
    if isinstance(df.columns, pd.MultiIndex):
        if ("Adj Close" not in df.columns.get_level_values(0)) and ("Adj Close" not in df.columns):
            raise RuntimeError("Downloaded data does not contain 'Adj Close'")
        adj = df["Adj Close"].copy()
    else:
        # 단일 티커인 경우
        if "Adj Close" not in df.columns:
            raise RuntimeError("Downloaded data does not contain 'Adj Close'")
        adj = df[["Adj Close"]].rename(columns={"Adj Close": ticker_list[0]}).copy()

    adj.index = pd.DatetimeIndex(adj.index)
    adj = adj.sort_index()
    # 컬럼명 정리
    adj.columns = [str(c).upper() for c in adj.columns]

    # alias를 사용한 경우: 원래 요청 티커로 되돌리는 역매핑
    # 예) 요청 SOX, alias SOXX -> 다운로드 컬럼 SOXX를 SOX로 rename
    inv = {v: k for k, v in aliases.items()}
    if inv:
        adj = adj.rename(columns={c: inv.get(c, c) for c in adj.columns})

    logger.info("yfinance 다운로드 완료: rows=%d cols=%d", adj.shape[0], adj.shape[1])
    return YahooFetchResult(adj_close=adj)
