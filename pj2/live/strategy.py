"""
거래 신호 생성 로직

설계:
- 순수 함수 (입력 → 신호, 사이드 이펙트 없음)
- API 호출 금지 (데이터는 미리 받아서 전달)
- 백테스트와 라이브에서 동일하게 사용

신호:
  1 = 매수 신호
 -1 = 매도 신호
  0 = 신호 없음 (보유 유지)
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple


def calculate_simple_ma(prices: list, period: int = 20) -> float:
    """
    단순 이동평균 계산
    
    Args:
        prices: 가격 리스트 (최신순)
        period: MA 기간
        
    Returns:
        이동평균값
    """
    if len(prices) < period:
        return None
    
    return np.mean(prices[-period:])


def calculate_momentum(prices: list, period: int = 10) -> float:
    """
    모멘텀 계산 (현재가 - period일 전 가격)
    
    Args:
        prices: 가격 리스트 (최신순)
        period: 기간
        
    Returns:
        모멘텀 (음수 = 하락, 양수 = 상승)
    """
    if len(prices) < period + 1:
        return None
    
    current = prices[-1]
    past = prices[-(period + 1)]
    
    return ((current - past) / past) * 100  # %


def calculate_rsi(prices: list, period: int = 14) -> float:
    """
    RSI (Relative Strength Index) 계산
    
    Args:
        prices: 가격 리스트 (최신순)
        period: 기간 (기본 14)
        
    Returns:
        RSI 값 (0-100)
    """
    if len(prices) < period + 1:
        return None
    
    deltas = np.diff(prices[-period-1:])
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    
    avg_gain = np.mean(gains)
    avg_loss = np.mean(losses)
    
    if avg_loss == 0:
        return 100 if avg_gain > 0 else 0
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi


# ============================================================================
# 핵심 전략 신호 함수
# ============================================================================

def generate_signal(
    ticker: str,
    current_price: float,
    prices: list,          # 최근 가격 리스트 (최신순)
    current_position: int  # 현재 보유 수량 (0 = 보유 없음)
) -> Dict[str, Any]:
    """
    거래 신호 생성 (예시: MA + 모멘텀 전략)
    
    전략:
    - MA(20) 상향 돌파 + 모멘텀 > 2% → 매수 신호
    - MA(20) 하향 돌파 또는 보유 손실 > 3% → 매도 신호
    
    Args:
        ticker: 종목코드
        current_price: 현재 가격
        prices: 최근 가격 리스트 (소수점 포함, 최신순)
        current_position: 보유 수량
    
    Returns:
        {
            'signal': 1 | 0 | -1,
            'reason': '신호 이유',
            'indicators': {계산된 지표들}
        }
    """
    
    # 1. 기술적 지표 계산
    ma20 = calculate_simple_ma(prices, 20)
    momentum = calculate_momentum(prices, 10)
    rsi = calculate_rsi(prices, 14)
    
    indicators = {
        'ma20': ma20,
        'momentum': momentum,
        'rsi': rsi
    }
    
    # 2. 신호 결정 로직
    signal = 0
    reason = "신호 없음"
    
    # 데이터 부족 시
    if ma20 is None or momentum is None:
        return {'signal': 0, 'reason': "데이터 부족", 'indicators': indicators}
    
    # 보유 중인 경우: 매도 조건 확인
    if current_position > 0:
        # 조건: MA 하향 돌파 또는 RSI > 70 (과매수)
        if current_price < ma20 * 0.98:  # MA 아래 2% 이상
            signal = -1
            reason = f"매도: MA 하향 돌파 (현가={current_price:.0f}, MA20={ma20:.0f})"
        
        elif rsi is not None and rsi > 70:
            signal = -1
            reason = f"매도: 과매수 신호 (RSI={rsi:.1f})"
    
    # 보유 없는 경우: 매수 조건 확인
    else:
        # 조건: MA 상향 돌파 + 긍정적 모멘텀 + RSI < 50
        if current_price > ma20 * 1.01:  # MA 위 1% 이상
            if momentum > 2:  # 상승 모멘텀
                if rsi is None or rsi < 70:  # 과매수 아님
                    signal = 1
                    reason = f"매수: MA 상향 돌파 + 모멘텀 (현가={current_price:.0f}, 모멘텀={momentum:.2f}%)"
    
    return {
        'signal': signal,
        'reason': reason,
        'indicators': indicators
    }


def validate_signal(
    signal: Dict[str, Any],
    current_cash: float,
    current_price: float,
    max_position_pct: float = 0.1  # 최대 투자 비중 10%
) -> Tuple[bool, str]:
    """
    신호의 타당성 검증 (리스크 관리)
    
    Args:
        signal: generate_signal 결과
        current_cash: 현재 현금
        current_price: 현재 가격
        max_position_pct: 최대 포지션 비중
        
    Returns:
        (승인 여부, 사유)
    """
    
    if signal['signal'] == 0:
        return True, "신호 없음"
    
    if signal['signal'] == -1:
        return True, "매도 신호 (항상 승인)"
    
    # 매수 신호의 경우만 검증
    if signal['signal'] == 1:
        # 1. 충분한 현금 확인
        max_invest = current_cash * max_position_pct
        
        if current_price > max_invest:
            return False, f"현금 부족 (필요={current_price}, 가능={max_invest:.0f})"
        
        # 2. 기술적 지표 다시 확인
        if signal['indicators']['rsi'] is not None:
            if signal['indicators']['rsi'] > 80:
                return False, "과도한 과매수 상태"
        
        return True, "매수 신호 검증 완료"
    
    return True, "기타"


# ============================================================================
# 테스트/디버깅용 헬퍼
# ============================================================================

def test_signal():
    """신호 생성 로직 테스트 (더미 데이터)"""
    
    # 더미 가격 데이터 (20일)
    base_price = 70000
    prices = [base_price + i * 100 for i in range(20)]  # 상향 추세
    
    # 시나리오 1: 보유 없음, 신호 생성해야 함
    result = generate_signal(
        ticker="005930",
        current_price=71900,
        prices=prices,
        current_position=0
    )
    
    print(f"[테스트] 신호: {result['signal']}")
    print(f"[테스트] 이유: {result['reason']}")
    print(f"[테스트] MA20: {result['indicators']['ma20']:.0f}")
    print(f"[테스트] 모멘텀: {result['indicators']['momentum']:.2f}%")
    
    # 검증
    is_valid, reason = validate_signal(
        result,
        current_cash=10000000,  # 1000만원
        current_price=71900
    )
    print(f"[검증] 승인: {is_valid} ({reason})")


if __name__ == "__main__":
    test_signal()
