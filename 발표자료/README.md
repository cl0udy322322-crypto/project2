# project2
# 📈 DAA Macro-Overlay & Automated Execution System
> **거시 경제 지표 분석을 통한 동적 자산 배분(DAA) 백테스트 및 실거래 자동 집행 시스템**

본 프로젝트는 카나리아 자산의 모멘텀과 구리/금 비율 기반의 거시 경제 지표를 결합한 **동적 자산 배분(DAA) 전략**을 구현합니다. 백테스트를 통해 도출된 최적 비중은 한국투자증권 API를 통해 국내 및 해외 시장에 자동으로 주문이 실행되도록 설계되었습니다.

---

## 1. 프로젝트 주요 기능
* **데이터 수집**: `yfinance`를 활용하여 ETF 및 선물(구리, 금) 시세 데이터를 실시간으로 수집합니다.
* **전략 연산**:
    * **Canary Regime**: VWO, BND의 모멘텀 점수를 통해 시장의 공격/방어 국면을 판단합니다.
    * **Macro Overlay**: 구리/금 비율($\log(\text{Copper}/\text{Gold})$)의 255일 EMA와 볼린저 밴드(1.5 $\sigma$)를 활용해 거시적 리스크를 보정합니다.
* **레버리지 실행**: 신호는 1배수 자산으로 계산하되, 실제 매수는 SPXL, SOXL 등 레버리지 ETF로 치환하여 수익률을 극대화합니다.
* **자동 매매**: `target_portfolio.csv`에 저장된 비중을 바탕으로 한국투자증권 API를 통해 한국/미국 주식을 자동 매수합니다.

---

## 2. 시스템 아키텍처
1.  **전략 엔진 (`정량적 접근법을 사용한 DAA 글로벌 반도체 투자.ipynby`)**:
    * 공격(SMH, CQQQ 등), 방어(UUP, GLD 등), 카나리아(VWO, BND) 자산 분석.
    * 매월 리밸런싱 날짜에 맞춘 최적 가중치 계산.
    * `target_portfolio.csv` 생성.
2.  **트레이딩 모듈 (`Execution_Trade.py`)**:
    * `Trade.yaml`의 API Key를 활용한 인증 토큰 발급.
    * 종목 코드(숫자 6자리 vs 알파벳)에 따른 국가별 시장 판별.
    * 투자 원금 대비 비중 계산 및 시장가(국내)/지정가(해외) 주문 수행.

---

## 3. 기술 스택
* **Language**: Python 3.x
* **Libraries**:
    * `pandas`, `numpy`: 데이터 분석 및 행렬 연산
    * `yfinance`: 금융 시세 데이터 로드
    * `matplotlib`: 성과 지표 시각화(수익률 곡선, MDD, 히트맵)
    * `requests`: 증권사 API 통신
    * `PyYAML`: 설정 파일 관리

---

## 4. 실행 가이드

### 사전 준비
1.  한국투자증권(KIS) API Key 및 Secret 발급.
2.  `Trade.yaml` 파일 내에 `api_key`, `secret_key`, `account_id` 설정.
3.  필수 라이브러리 설치:
    ```bash
    pip install yfinance pandas matplotlib requests pyyaml tabulate
    ```

### 실행 순서
1.  **백테스트 실행**: 최신 자산 비중이 담긴 CSV 파일을 생성합니다.
    ```bash
    python "정량적 접근법을 사용한 DAA 글로벌 반도체 투자.ipynby"
    ```
2.  **자동 매매 실행**: 생성된 CSV를 읽어 실거래 주문을 전송합니다.
    ```bash
    python Execution_Trade.py
    ```

---

## 5. 전략 성과 요약 (Sample)
* **수익률 곡선**: 전략과 벤치마크(1/N Buy & Hold) 간의 성과 비교 차트 제공.
* **리스크 지표**: CAGR, Sharpe Ratio, MDD, 리밸런싱 회전율(Turnover) 산출.
* **국면 시각화**: Canary Regime에 따른 공격/중립/방어 구간 쉐이딩 표시.

---

## 6. 면책 조항 (Disclaimer)
본 프로그램은 투자 참고용이며, 실제 투자에 따른 책임은 본인에게 있습니다. API 호출 제한 및 네트워크 지연에 따른 주문 실패 가능성이 있으므로 반드시 모의투자 환경에서 충분히 검증하시기 바랍니다.