"""CLI 엔트리포인트.

요구사항:
- `python -m src.cli backtest --start YYYY-MM-DD --end YYYY-MM-DD --outdir outputs/run_001`
- --config, --rebalance_mode, --plot 지원

주의:
- 이 파일은 얇게(Thin) 유지하고, 핵심 로직은 `src/backtest/engine.py`로 위임합니다.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from src.backtest.engine import run_backtest
from src.config.loader import load_config
from src.utils.logging import get_logger, setup_logging


@dataclass(frozen=True)
class CliArgs:
    command: str
    config_path: str
    start: str
    end: str
    outdir: str
    rebalance_mode: str | None
    plot: bool


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vaa-backtest", description="VAA 전략 백테스트 CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    bt = subparsers.add_parser("backtest", help="백테스트 실행")
    bt.add_argument("--config", default="configs/config.yaml", help="설정 YAML 경로")
    bt.add_argument("--start", required=True, help="백테스트 시작일 (YYYY-MM-DD)")
    bt.add_argument("--end", required=True, help="백테스트 종료일 (YYYY-MM-DD)")
    bt.add_argument("--outdir", required=True, help="출력 폴더")
    bt.add_argument(
        "--rebalance_mode",
        default=None,
        choices=["quarter_start", "quarter_end_next_day"],
        help="config의 rebalance.mode를 덮어씁니다.",
    )
    bt.add_argument("--plot", action="store_true", help="있으면 누적수익률 그래프 저장")
    return parser


def _parse_args() -> CliArgs:
    parser = _build_parser()
    ns = parser.parse_args()
    return CliArgs(
        command=ns.command,
        config_path=ns.config,
        start=ns.start,
        end=ns.end,
        outdir=ns.outdir,
        rebalance_mode=ns.rebalance_mode,
        plot=bool(ns.plot),
    )


def main() -> None:
    setup_logging()
    logger = get_logger(__name__)

    args = _parse_args()
    config = load_config(args.config_path)

    if args.rebalance_mode is not None:
        config["rebalance"]["mode"] = args.rebalance_mode

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    if args.command == "backtest":
        logger.info("CLI backtest 시작: start=%s end=%s outdir=%s", args.start, args.end, outdir)
        run_backtest(config=config, start=args.start, end=args.end, outdir=outdir, plot=args.plot)
        logger.info("CLI backtest 완료")
    else:
        raise ValueError(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
