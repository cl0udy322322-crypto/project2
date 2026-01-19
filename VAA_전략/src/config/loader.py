"""YAML 설정 로더.

- 외부 의존성: pyyaml
- 설정은 dict 형태로 로딩하며, 최소 기본값 보정(sanity)만 수행합니다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_config(path: str | Path) -> dict[str, Any]:
    """YAML 파일에서 설정을 로딩합니다."""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if not isinstance(config, dict):
        raise ValueError("Config must be a YAML mapping")

    # 필수 섹션 기본값(누락 시 최소 보정)
    config.setdefault("windows", {})
    config.setdefault("thresholds", {})
    config.setdefault("selection", {})
    config.setdefault("hedge", {})
    config.setdefault("costs", {})
    config.setdefault("behavior_on_missing", {})
    config.setdefault("rebalance", {})

    config["behavior_on_missing"].setdefault("mode", "carry_forward")
    config["rebalance"].setdefault("mode", "quarter_start")

    return config
