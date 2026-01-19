"""레짐 결정 규칙.

요구사항:
- alive_count == 2 -> ATTACK
- alive_count == 1 -> NEUTRAL
- alive_count == 0 -> DEFENSE

주의:
- short_cover_state는 레짐을 바꾸지 않습니다.
"""

from __future__ import annotations

from typing import Literal

import pandas as pd

Regime = Literal["ATTACK", "NEUTRAL", "DEFENSE"]


def regime_from_alive_count(alive_count: float | int | None) -> Regime | None:
    """alive_count에서 레짐을 결정합니다. NaN/None이면 None을 반환합니다."""
    if alive_count is None:
        return None

    if isinstance(alive_count, float) and pd.isna(alive_count):
        return None

    v = int(alive_count)
    if v == 2:
        return "ATTACK"
    if v == 1:
        return "NEUTRAL"
    if v == 0:
        return "DEFENSE"
    raise ValueError(f"alive_count must be 0/1/2, got {alive_count}")
