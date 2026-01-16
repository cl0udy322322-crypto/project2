"""
자동거래 시스템 진입점

실행:
    python live/run.py --mode paper    # Paper trading
    python live/run.py --mode live     # Live trading (위험!)
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import time

# 로컬 모듈 import
from kis_api import KISAuth, KISQuotation, KISTrading, KISAPIError
from trader import Trader
from strategy import generate_signal, validate_signal

# ============================================================================
# 로깅 설정
# ============================================================================

def setup_logging(log_file: str = "logs/trade.log"):
    """로깅 초기화"""
    
    Path("logs").mkdir(exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    logger = logging.getLogger(__name__)
    logger.info("="*80)
    logger.info(f"거래 시스템 시작: {datetime.now().isoformat()}")
    
    return logger


# ============================================================================
# 메인 거래 루프
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="자동거래 시스템")
    parser.add_argument('--mode', choices=['paper', 'live'], default='paper',
                       help="거래 모드 (기본: paper)")
    parser.add_argument('--interval', type=int, default=60,
                       help="신호 확인 간격 (초, 기본: 60)")
    parser.add_argument('--tickers', type=str, default='005930,051910',
                       help="거래 종목 (쉼표 구분)")
    
    args = parser.parse_args()
    
    logger = setup_logging()
    
    # ⚠️ Live mode 경고
    if args.mode == "live":
        logger.warning("="*80)
        logger.warning("⚠️  LIVE MODE - 실제 거래를 시작합니다!")
        logger.warning("⚠️  LIVE MODE - 실제 거래를 시작합니다!")
        logger.warning("="*80)
        response = input("\n정말로 LIVE 거래를 시작하시겠습니까? (yes/no): ")
        
        if response.lower() != 'yes':
            logger.info("Live trading 취소됨")
            sys.exit(0)
    
    # ============================================================================
    # 환경변수 및 API 초기화
    # ============================================================================
    
    load_dotenv()
    
    api_key = os.getenv('KIS_API_KEY')
    api_secret = os.getenv('KIS_API_SECRET')
    account_id = os.getenv('KIS_ACCOUNT_ID')
    base_url = "https://openapivts.koreainvestment.com:29443"  # 모의 거래
    
    if not all([api_key, api_secret, account_id]):
        logger.error("❌ 환경변수 누락: KIS_API_KEY, KIS_API_SECRET, KIS_ACCOUNT_ID")
        sys.exit(1)
    
    try:
        # API 인증
        logger.info("한투 API 인증 중...")
        auth = KISAuth(api_key, api_secret, base_url)
        auth.get_access_token()
        
        quotation = KISQuotation(auth)
        trading = KISTrading(auth, account_id, "01")
        
        # 거래 엔진 초기화
        trader = Trader(auth, quotation, trading, mode=args.mode)
        
        # 계좌 확인
        logger.info("계좌 정보 확인 중...")
        balance = trader.get_balance()
        logger.info(f"  현금: {balance['cash']:,.0f}원")
        logger.info(f"  총자산: {balance['total_value']:,.0f}원")
        
    except KISAPIError as e:
        logger.error(f"❌ API 초기화 실패: {str(e)}")
        sys.exit(1)
    
    # ============================================================================
    # 거래 루프
    # ============================================================================
    
    tickers = args.tickers.split(',')
    logger.info(f"거래 종목: {tickers}")
    logger.info(f"신호 확인 간격: {args.interval}초")
    logger.info(f"모드: {args.mode.upper()}")
    
    try:
        iteration = 0
        
        while True:
            iteration += 1
            logger.info(f"\n{'='*80}")
            logger.info(f"[반복 {iteration}] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            for ticker in tickers:
                logger.info(f"\n--- {ticker} ---")
                
                try:
                    # 1. 현재가 및 가격 히스토리 조회
                    current_price = trader.get_current_price(ticker)
                    prices = trader.get_price_history(ticker, days=30)
                    
                    # 2. 현재 포지션 확인
                    balance = trader.get_balance()
                    current_position = balance['positions'].get(ticker, {}).get('qty', 0)
                    
                    # 3. 신호 생성
                    signal_result = generate_signal(
                        ticker=ticker,
                        current_price=current_price,
                        prices=prices,
                        current_position=current_position
                    )
                    
                    signal = signal_result['signal']
                    reason = signal_result['reason']
                    
                    logger.info(f"신호: {signal} ({reason})")
                    logger.info(f"지표: {signal_result['indicators']}")
                    
                    # 4. 신호 검증
                    is_valid, validation_reason = validate_signal(
                        signal_result,
                        current_cash=balance['cash'],
                        current_price=current_price
                    )
                    
                    logger.info(f"검증: {'✓' if is_valid else '✗'} ({validation_reason})")
                    
                    if not is_valid:
                        continue
                    
                    # 5. 거래 실행
                    if signal != 0:
                        trade_result = trader.execute_trade(
                            ticker=ticker,
                            signal=signal,
                            current_price=current_price,
                            quantity=1
                        )
                        
                        logger.info(f"실행 결과: {trade_result['status']}")
                        trader.save_trade_log(trade_result)
                
                except Exception as e:
                    logger.error(f"{ticker} 처리 중 오류: {str(e)}")
                    continue
            
            # 대기
            logger.info(f"\n다음 확인까지 {args.interval}초 대기...")
            time.sleep(args.interval)
    
    except KeyboardInterrupt:
        logger.info("\n사용자 중단됨")
        sys.exit(0)
    
    except Exception as e:
        logger.error(f"❌ 예상치 못한 오류: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
