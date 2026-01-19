"""입출력 유틸.

- DataFrame/Series/JSON 저장을 표준화합니다.
- 이 모듈은 파일 시스템에 쓰는 부작용이 있으므로, 함수 이름에서 목적이 명확해야 합니다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_csv(df: pd.DataFrame, path: Path) -> None:
    ensure_dir(path.parent)
    df.to_csv(path, index=True, encoding="utf-8")


def write_json(data: dict[str, Any], path: Path) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
