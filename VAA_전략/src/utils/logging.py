"""로깅 설정.

요구사항:
- 주요 단계마다 info 로그를 남길 수 있도록 전역 로거 구성을 제공합니다.

설계 원칙:
- 로깅 설정은 부작용(side-effect)이므로 `setup_logging()`에서만 수행합니다.
- 각 모듈은 `get_logger(__name__)`를 통해 로거를 획득합니다.
"""

from __future__ import annotations

import logging
from typing import Final

_DEFAULT_FORMAT: Final[str] = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def setup_logging(level: int = logging.INFO) -> None:
    """프로세스 전역 로깅을 초기화합니다."""
    logging.basicConfig(level=level, format=_DEFAULT_FORMAT)


def get_logger(name: str) -> logging.Logger:
    """모듈별 로거를 반환합니다."""
    return logging.getLogger(name)
