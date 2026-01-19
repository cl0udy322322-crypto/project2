"""
거래 실행 엔진

역할:
- API를 통해 시장 데이터 수집
- strategy.py의 신호 함수 호출
- 포지션 관리 및 주문 실행
- Paper 또는 Live 모드 전환

설계:
- Paper Mode: 거래 시뮬레이션 (실제 주문 안 함)
- Live Mode: 실제 거래 (주의!)
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional
import json
from pathlib import Path

from kis_api import KISAuth, KISQuotation, KISTrading, KISAPIError
from strategy import generate_signal, validate_signal

logger = logging.getLogger(__name__)


class Trader:
    """거래 실행 엔진"""
    
    def __init__(
        self,
        auth: KISAuth,
        quotation: KISQuotation,
        trading: KISTrading,
        mode: str = "paper"  # "paper" or "live"
    ):
        """
        Args:
            auth: 한투 인증
            quotation: 시세 조회
            trading: 주문 API
            mode: "paper" 또는 "live"
        """
        self.auth = auth
        self.quotation = quotation
        self.trading = trading
        self.mode = mode
        
        # Paper trading 시뮬레이션 상태
        self.paper_cash = 10000000  # 초기 1000만원
        self.paper_positions = {}   # {ticker: {'qty': 100, 'entry_price': 50000}}
        
        logger.info(f"✓ Trader 초기화: mode={mode}")
    
    def get_current_price(self, ticker: str) -> float:
        """
        현재가 조회
        
        Args:
            ticker: 종목코드
            
        Returns:
            현재가
        """
        try:
            data = self.quotation.get_current_price(ticker)
            price = float(data['stck_prpr'])
            logger.debug(f"{ticker}: {price}원")
            return price
        
        except KISAPIError as e:
            logger.error(f"가격 조회 실패 ({ticker}): {str(e)}")
            raise
    
    def get_price_history(self, ticker: str, days: int = 20) -> list:
        """
        가격 히스토리 조회
        
        Args:
            ticker: 종목코드
            days: 조회 일수
            
        Returns:
            가격 리스트 (최신순)
        """
        try:
            data = self.quotation.get_daily_ohlcv(ticker, days)
            
            # API 응답 형식에 따라 파싱
            # data = [
            #     {'stck_clpr': '70000', ...},
            #     {'stck_clpr': '69900', ...},
            #     ...
            # ]
            
            prices = [float(d['stck_clpr']) for d in data]
            return prices[::-1]  # 오래된 순으로 정렬
        
        except KISAPIError as e:
            logger.error(f"가격 히스토리 조회 실패 ({ticker}): {str(e)}")
            raise
    
    def get_balance(self) -> Dict[str, Any]:
        """
        계좌 잔고 조회
        
        Returns:
            {'cash': 1000000, 'positions': {...}}
        """
        if self.mode == "paper":
            # Paper mode: 시뮬레이션 값 반환
            total_position_value = sum(
                qty['qty'] * qty['entry_price']
                for qty in self.paper_positions.values()
            )
            
            return {
                'cash': self.paper_cash,
                'positions': self.paper_positions,
                'total_value': self.paper_cash + total_position_value
            }
        
        else:  # live
            # Live mode: 실제 계좌 조회
            try:
                balance = self.trading.get_balance()
                
                # 응답 파싱
                holdings = balance.get('output1', [])
                summary = balance.get('output2', [{}])[0]
                
                cash = float(summary.get('prvs_rcdl_excc_amt', 0))
                
                positions = {
                    h['pdno']: {
                        'qty': int(h['hldg_qty']),
                        'entry_price': float(h['pchs_avg_prc']),
                        'current_price': float(h['stck_prpr'])
                    }
                    for h in holdings
                }
                
                return {
                    'cash': cash,
                    'positions': positions,
                    'total_value': cash + sum(
                        v['qty'] * v['current_price']
                        for v in positions.values()
                    )
                }
            
            except KISAPIError as e:
                logger.error(f"잔고 조회 실패: {str(e)}")
                raise
    
    def execute_trade(
        self,
        ticker: str,
        signal: int,  # 1=매수, -1=매도, 0=없음
        current_price: float,
        quantity: int = 1
    ) -> Dict[str, Any]:
        """
        거래 실행
        
        Args:
            ticker: 종목코드
            signal: 거래 신호 (1, -1, 0)
            current_price: 현재가
            quantity: 거래 수량
            
        Returns:
            실행 결과
        """
        
        if signal == 0:
            return {'status': 'no_signal', 'message': '신호 없음'}
        
        timestamp = datetime.now().isoformat()
        
        if self.mode == "paper":
            return self._execute_paper(ticker, signal, current_price, quantity, timestamp)
        else:
            return self._execute_live(ticker, signal, current_price, quantity, timestamp)
    
    def _execute_paper(
        self,
        ticker: str,
        signal: int,
        current_price: float,
        quantity: int,
        timestamp: str
    ) -> Dict[str, Any]:
        """Paper trading 시뮬레이션"""
        
        if signal == 1:  # 매수
            cost = current_price * quantity
            
            if self.paper_cash < cost:
                logger.warning(f"[PAPER] 현금 부족: {ticker} {quantity}주 @ {current_price}")
                return {
                    'status': 'failed',
                    'reason': 'insufficient_cash',
                    'message': f"필요: {cost}, 보유: {self.paper_cash}"
                }
            
            # 포지션 업데이트
            if ticker not in self.paper_positions:
                self.paper_positions[ticker] = {'qty': 0, 'entry_price': 0}
            
            pos = self.paper_positions[ticker]
            pos['qty'] += quantity
            pos['entry_price'] = current_price
            self.paper_cash -= cost
            
            logger.info(f"[PAPER] 매수: {ticker} {quantity}주 @ {current_price}원 (잔고: {self.paper_cash})")
            
            return {
                'status': 'success',
                'type': 'buy',
                'ticker': ticker,
                'quantity': quantity,
                'price': current_price,
                'timestamp': timestamp
            }
        
        elif signal == -1:  # 매도
            if ticker not in self.paper_positions or self.paper_positions[ticker]['qty'] == 0:
                logger.warning(f"[PAPER] 보유 없음: {ticker}")
                return {
                    'status': 'failed',
                    'reason': 'no_position',
                    'message': f"{ticker} 보유 종목 없음"
                }
            
            pos = self.paper_positions[ticker]
            qty_to_sell = min(quantity, pos['qty'])
            proceeds = current_price * qty_to_sell
            
            pos['qty'] -= qty_to_sell
            self.paper_cash += proceeds
            
            if pos['qty'] == 0:
                del self.paper_positions[ticker]
            
            logger.info(f"[PAPER] 매도: {ticker} {qty_to_sell}주 @ {current_price}원 (잔고: {self.paper_cash})")
            
            return {
                'status': 'success',
                'type': 'sell',
                'ticker': ticker,
                'quantity': qty_to_sell,
                'price': current_price,
                'timestamp': timestamp
            }
    
    def _execute_live(
        self,
        ticker: str,
        signal: int,
        current_price: float,
        quantity: int,
        timestamp: str
    ) -> Dict[str, Any]:
        """Live trading 실제 거래"""
        
        try:
            if signal == 1:  # 매수
                result = self.trading.place_order(
                    ticker=ticker,
                    quantity=quantity,
                    price=0,  # 시장가
                    order_type="01"
                )
                
                logger.info(f"[LIVE] 매수 주문: {ticker} {quantity}주")
                
                return {
                    'status': 'success',
                    'type': 'buy',
                    'ticker': ticker,
                    'quantity': quantity,
                    'api_response': result,
                    'timestamp': timestamp
                }
            
            elif signal == -1:  # 매도
                result = self.trading.place_order(
                    ticker=ticker,
                    quantity=quantity,
                    price=0,
                    order_type="01"
                )
                
                logger.info(f"[LIVE] 매도 주문: {ticker} {quantity}주")
                
                return {
                    'status': 'success',
                    'type': 'sell',
                    'ticker': ticker,
                    'quantity': quantity,
                    'api_response': result,
                    'timestamp': timestamp
                }
        
        except KISAPIError as e:
            logger.error(f"[LIVE] 주문 실패: {str(e)}")
            return {
                'status': 'failed',
                'reason': str(e),
                'timestamp': timestamp
            }
    
    def save_trade_log(self, trade_result: Dict[str, Any], log_file: str = "logs/trade.log"):
        """거래 기록 저장"""
        
        Path("logs").mkdir(exist_ok=True)
        
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(trade_result, ensure_ascii=False) + "\n")
        
        logger.debug(f"거래 기록 저장: {log_file}")
