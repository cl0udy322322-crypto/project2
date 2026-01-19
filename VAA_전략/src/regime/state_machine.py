"""Short-covering 상태 머신."""


































































































from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

ShortCoverState = Literal["OFF", "ON"]


@dataclass(frozen=True)
class ShortCoverConfig:
    """Short-covering 상태머신 파라미터."""

    entry_z: float
    exit_z: float
    exit_streak_days: int


@dataclass
class ShortCoverMachine:
    """일간 업데이트용 상태 머신.

    규칙:
    - 진입: alive_count in {0,1} AND zVIX >= entry_z -> ON (streak=0)
    - 종료: zVIX <= exit_z 가 exit_streak_days 연속이면 OFF
    """

    config: ShortCoverConfig
    state: ShortCoverState = "OFF"
    exit_streak: int = 0

    def update_short_cover_state(
        self,
        date: pd.Timestamp,
        alive_count: float | int | None,
        z_vix: float | None,
    ) -> tuple[ShortCoverState, int]:
        """하루치 관측치를 반영해 상태를 갱신합니다.

        주의:
        - 데이터 결측(None/NaN)이면 상태를 유지합니다.
        - `date`는 시그니처/로그 목적이며 상태전이 자체에는 쓰지 않습니다.
        """
        _ = date

        if alive_count is None or z_vix is None:
            return self.state, self.exit_streak
        if isinstance(alive_count, float) and pd.isna(alive_count):
            return self.state, self.exit_streak
        if isinstance(z_vix, float) and pd.isna(z_vix):
            return self.state, self.exit_streak

        alive_int = int(alive_count)
        z = float(z_vix)

        # 진입
        if alive_int in (0, 1) and z >= float(self.config.entry_z):
            self.state = "ON"
            self.exit_streak = 0
            return self.state, self.exit_streak

        # 종료(ON일 때만)
        if self.state == "ON":
            if z <= float(self.config.exit_z):
                self.exit_streak += 1
            else:
                self.exit_streak = 0

            if self.exit_streak >= int(self.config.exit_streak_days):
                self.state = "OFF"
                self.exit_streak = 0

        return self.state, self.exit_streak

    def update(
        self,
        date: pd.Timestamp,
        alive_count: float | int | None,
        z_vix: float | None,
    ) -> tuple[ShortCoverState, int]:
        """호환성을 위해 제공하는 별칭."""
        return self.update_short_cover_state(date=date, alive_count=alive_count, z_vix=z_vix)


def simulate_short_cover_timeline(
    dates: pd.DatetimeIndex,
    alive_count_daily: pd.Series,
    z_vix_daily: pd.Series,
    config: ShortCoverConfig,
) -> pd.DataFrame:
    """일간 타임라인 전체를 상태 머신으로 시뮬레이션합니다."""
    machine = ShortCoverMachine(config=config)
    records: list[dict[str, object]] = []

    for d in pd.DatetimeIndex(dates):
        state, streak = machine.update_short_cover_state(
            date=pd.Timestamp(d),
            alive_count=alive_count_daily.get(d, None),
            z_vix=z_vix_daily.get(d, None),
        )
        records.append({"date": pd.Timestamp(d), "short_cover_state": state, "exit_streak": streak})

    return pd.DataFrame.from_records(records).set_index("date")
