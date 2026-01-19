# Quant KIS — 한투 API 기반 자동거래 시스템

## 개요
- **백테스팅**: Jupyter Notebooks (`.ipynb`)
- **거래 실행**: Python Scripts (`.py`)
- **거래 방식**: 현금만 사용 (레버리지 없음)
- **모드**: Paper Trading / Live Trading 토글 가능
- **대상**: 단일 사용자 로컬 개발 (VS Code)

---

## 워크플로우

### 1️⃣ 백테스팅 (Jupyter)
```
backtest/
├─ 01_data_check.ipynb      # 데이터 확인 및 전처리
├─ 02_strategy.ipynb        # 전략 신호 개발 및 검증
└─ 03_backtest.ipynb        # 백테스트 실행 및 성과 분석
```

**목적**: 거래 전략 검증 → 수익성 확인 → 파라미터 최적화

### 2️⃣ 전략 고정 (Decision)
핵심 신호 로직을 `live/strategy.py`에 포함시킬 최종 버전으로 결정

### 3️⃣ 거래 실행 (Python)
```
live/
├─ kis_api.py       # 한투 API 래퍼 (인증, 조회, 주문)
├─ strategy.py      # 거래 신호 로직 (사이드 이펙트 없음)
├─ trader.py        # 실행 로직 (paper/live 토글)
└─ run.py           # 진입점 (스케줄 + 실행)
```

**흐름**: `run.py` → `trader.py` → `strategy.py` + `kis_api.py`

---

## 프로젝트 구조

```
pj2/
├─ README.md                         # 이 파일
├─ requirements.txt                  # 의존성
├─ .env.example                      # 환경변수 템플릿
│
├─ config/
│  ├─ kis.yaml                       # 한투 API 설정
│  └─ universe.yaml                  # 거래 종목 리스트
│
├─ data/
│  ├─ raw/                           # 원본 데이터 (야후 파이낸스 등)
│  └─ processed/                     # 전처리된 데이터
│
├─ backtest/
│  ├─ 01_data_check.ipynb            # 데이터 EDA
│  ├─ 02_strategy.ipynb              # 신호 개발
│  └─ 03_backtest.ipynb              # 백테스트 실행
│
├─ live/
│  ├─ kis_api.py                     # 한투 API 통신
│  ├─ strategy.py                    # 거래 신호 (순수 함수)
│  ├─ trader.py                      # 실행 및 포지션 관리
│  └─ run.py                         # 메인 진입점
│
├─ logs/
│  └─ trade.log                      # 거래 로그
│
└─ outputs/
   ├─ reports/                       # 수익률, 드로다운 등
   └─ trades/                        # 체결 기록
```

---

## 설정 및 실행

### 1. 환경 설정
```bash
# 1) Python 의존성 설치
pip install -r requirements.txt

# 2) .env 파일 생성 (환경변수)
cp .env.example .env
# → .env 파일에 한투 API Key/Secret 입력

# 3) config/ 설정 확인
# → kis.yaml: API 엔드포인트, 계좌번호 등
# → universe.yaml: 거래할 종목 리스트
```

### 2. 백테스팅
```bash
# Jupyter 실행
jupyter notebook

# 순서:
# 1. 01_data_check.ipynb     → 데이터 로드 및 확인
# 2. 02_strategy.ipynb       → 신호 로직 개발
# 3. 03_backtest.ipynb       → 백테스트 실행
```

### 3. 라이브 거래
```bash
# Paper trading (모의 거래)
python live/run.py --mode paper

# Live trading (실제 거래)
python live/run.py --mode live
```

---

## 핵심 설계 원칙

### ✅ DO
- `kis_api.py`: API 통신만 담당 (깔끔한 인터페이스)
- `strategy.py`: 순수 함수 (입력 → 신호, 사이드 이펙트 없음)
- `trader.py`: 실행 로직과 포지션 관리
- 모든 거래는 로그에 기록
- 에러는 캐치하고 로그하고 계속 진행

### ❌ DON'T
- API 호출을 strategy 안에 넣지 말 것
- 글로벌 상태 변경
- 과도한 추상화 (클래스 오버사용)
- 하드코딩된 값 (config 파일 사용)

---

## 파일별 책임

| 파일 | 책임 |
|------|------|
| `kis_api.py` | 한투 API 래퍼 (가격조회, 주문, 잔고) |
| `strategy.py` | 거래 신호 결정 (순수 로직) |
| `trader.py` | 포지션 관리 + 주문 실행 |
| `run.py` | 스케줄 + 거래 루프 |

---

## 로그 및 아웃풋

- **logs/trade.log**: 모든 거래 이벤트 (시간, 종목, 가격, 수량, 상태)
- **outputs/reports/**: 수익률, 최대 손실, 승률 등
- **outputs/trades/**: 체결된 주문 상세 기록 (CSV)

---

## 문제 해결

### Q. `ModuleNotFoundError: No module named 'arch'`
```bash
pip install arch yfinance statsmodels
```

### Q. 한투 API 연결 실패
1. `.env` 파일에 API Key/Secret 확인
2. `config/kis.yaml`에서 엔드포인트 확인
3. `logs/trade.log` 에러 메시지 확인

### Q. Paper trading에서는 되는데 Live가 안 됨
1. `trader.py`의 `LIVE_MODE` 확인
2. 계좌번호 및 잔고 확인
3. 거래 가능 시간 확인

---

## 참고자료

- [한투 Open API 공식 문서](https://apiportal.koreainvestment.com)
- 백테스팅: `backtest/03_backtest.ipynb` 참조
- 거래 실행: `live/run.py` 참조

---

**마지막 업데이트**: 2026-01-16
