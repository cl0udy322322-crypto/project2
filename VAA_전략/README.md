# VAA 전략 백테스트 엔진 (Quarterly Rebalance)

- 분기 리밸런싱 포트폴리오 백테스트 엔진
- 신호는 월 1회(월말), 리밸런싱은 분기 1회
- 카나리아(BND, VWO) 기반 레짐 + VIX z-score 기반 Short-covering state
- ATTACK 레짐에서는 카나리아와 동일한 가중 모멘텀(1/3/6/12M 가중)으로 상위 5개 선택 후 inverse-vol Risk Parity
- NEUTRAL: SPY/QQQ + (방어군 변동성 최저 2개) + UUP, 동일비중(총 5개)
- DEFENSE: (방어군 변동성 최저 2개) + UUP, 동일비중(총 3개)
- short-cover ON일 때 인버스 헷지(최대 20%, `config.yaml`의 `hedge.z_bands`로 조절)

## 설치

```bash
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 실행 예시

1) 기본 config 사용

```bash
python -m src.cli backtest --config configs/config.yaml --start 2006-01-01 --end 2025-12-31 --outdir outputs/run_001 --plot
```

2) 리밸런싱 모드 변경

```bash
python -m src.cli backtest --config configs/config.yaml --start 2012-01-01 --end 2025-12-31 --rebalance_mode quarter_end_next_day --outdir outputs/run_002
```

## config.yaml 주요 파라미터

- `windows.canary_lookback_months`: 카나리아 스코어 계산에 필요한 최대 룩백(12M 사용)
- `windows.rp_vol_window_months`: RP용 월 수익률 변동성 창(기본 12개월)
- `windows.vix_z_window_days`: VIX z-score 롤링 윈도우(기본 756일)
- `thresholds.vix_entry_z / vix_exit_z / vix_exit_streak_days`: short-covering 상태머신 진입/종료 조건
- `selection.attack_drop_bottom_n`: ATTACK 유니버스에서 하위 N개 제거(기본 2)
- `selection.attack_min_weight`: ATTACK 선택 자산별 최소 비중 floor(기본 0.05)
- `selection.neutral_attack_tickers`: NEUTRAL에서 고정으로 포함할 공격군(기본 `SPY`,`QQQ`)
- `selection.low_vol_defense_n`: NEUTRAL/DEFENSE에서 방어군 중 저변동성 선택 개수(기본 2)
- `hedge.*`: 헷지(인버스 ETF) 티커 및 z-score 구간별 비중, 반영 방식
- `hedge.protect_tickers`: 헷지 비중을 확보할 때 비중을 가능한 한 유지할 보호 자산(예: `UUP`)
- `behavior_on_missing.mode`: 데이터 부족 시 `carry_forward`(기본) 또는 `cash`
- `rebalance.mode`: `quarter_start` 또는 `quarter_end_next_day`

## 프로젝트 구조

- `src/data`: yfinance 다운로드 및 데이터 변환(월말 리샘플 등)
- `src/signals`: 카나리아/모멘텀/변동성/VIX z-score 계산
- `src/regime`: 레짐 룰 및 short-covering 상태 머신
- `src/portfolio`: Risk Parity, 제약(floor/cap), 헷지 정책
- `src/backtest`: 백테스트 엔진, 성과지표, 리포팅(파일 저장)
- `src/cli.py`: CLI 엔트리포인트 (`python -m src.cli ...`)
- `tests`: 최소 요구 3개 테스트

## 출력 파일

- `weights.csv`: 리밸런싱 날짜별 regime/short-cover/selected_assets/used_assets(실제 반영)/비중 로그
- `regime_timeline.csv`: 일간 레짐/short-cover 타임라인
- `daily_returns.csv`: 일간 포트폴리오 수익률/누적수익률
- `monthly_returns.csv`: 월말(마지막 거래일) 기준 월 수익률/누적수익률
- `metrics.json`: CAGR/Vol/Sharpe/MDD
- `equity_curve.png`: (옵션) 누적수익률 그래프
