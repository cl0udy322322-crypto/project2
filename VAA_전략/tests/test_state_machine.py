from __future__ import annotations

import pandas as pd

from src.regime.state_machine import ShortCoverConfig, ShortCoverMachine


def test_state_machine_turns_on_when_entry_condition_met() -> None:
    cfg = ShortCoverConfig(entry_z=2.0, exit_z=1.5, exit_streak_days=10)
    m = ShortCoverMachine(config=cfg)

    # alive_count=0이고 z>=2이면 ON
    state, streak = m.update(pd.Timestamp("2020-01-01"), alive_count=0, z_vix=2.0)
    assert state == "ON"
    assert streak == 0

    # alive_count=1이고 z>=2이면 ON
    m = ShortCoverMachine(config=cfg)
    state, _ = m.update(pd.Timestamp("2020-01-01"), alive_count=1, z_vix=2.1)
    assert state == "ON"


def test_state_machine_turns_off_after_exit_streak() -> None:
    cfg = ShortCoverConfig(entry_z=2.0, exit_z=1.5, exit_streak_days=10)
    m = ShortCoverMachine(config=cfg)

    # 먼저 ON으로 만든다
    m.update(pd.Timestamp("2020-01-01"), alive_count=0, z_vix=2.2)
    assert m.state == "ON"

    # z <= 1.5 조건을 10일 연속 유지하면 OFF
    for i in range(10):
        d = pd.Timestamp("2020-01-02") + pd.Timedelta(days=i)
        state, streak = m.update(d, alive_count=0, z_vix=1.5)

    assert state == "OFF"
    assert streak == 0
