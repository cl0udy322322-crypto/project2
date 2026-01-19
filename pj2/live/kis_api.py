"""
한투 API 래퍼 - 한투 Open API와의 통신을 담당

역할: API 인증, 주가 조회, 잔고 조회, 주문/취소

설계:
- 각 함수는 단일 책임 (한 가지만 함)
- API 응답을 그대로 반환 (변환 안 함)
- 에러는 raise (호출자가 처리)
"""

import requests
import json
import os
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class KISAPIError(Exception):
    """한투 API 에러 기본 클래스"""
    pass


class KISAuth:
    """한투 API 인증 관리"""
    
    def __init__(self, api_key: str, api_secret: str, base_url: str):
        """
        Args:
            api_key: 한투 API Key
            api_secret: 한투 API Secret
            base_url: API Base URL (모의/실제)
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        self.access_token = None
        self.token_type = None
    
    def get_access_token(self) -> str:
        """
        접근토큰 발급
        
        Returns:
            발급받은 access_token
            
        Raises:
            KISAPIError: 토큰 발급 실패
        """
        url = self.base_url + "/oauth2/tokenP"
        body = {
            "grant_type": "client_credentials",
            "appkey": self.api_key,
            "appsecret": self.api_secret
        }
        
        try:
            res = requests.post(
                url,
                headers={"content-type": "application/json"},
                data=json.dumps(body),
                timeout=10
            ).json()
            
            if res.get('rt_cd') != '0':
                raise KISAPIError(f"토큰 발급 실패: {res.get('msg1')}")
            
            self.access_token = res['access_token']
            self.token_type = res['token_type']
            
            logger.info(f"✓ 접근토큰 발급 성공")
            return self.access_token
            
        except requests.RequestException as e:
            raise KISAPIError(f"API 연결 실패: {str(e)}")


class KISQuotation:
    """한투 시세 조회 API"""
    
    def __init__(self, auth: KISAuth):
        self.auth = auth
        self.base_url = auth.base_url
    
    def get_current_price(self, ticker: str) -> Dict[str, Any]:
        """
        현재가 조회 (국내주식 시세)
        
        Args:
            ticker: 종목코드 (예: '005930')
            
        Returns:
            {'stck_prpr': '70000', 'stck_hgpr': '70500', ...}
            
        Raises:
            KISAPIError: 조회 실패
        """
        url = self.base_url + "/uapi/domestic-stock/v1/quotations/inquire-price"
        
        headers = {
            "content-type": "application/json",
            "appkey": self.auth.api_key,
            "appsecret": self.auth.api_secret,
            "authorization": f"Bearer {self.auth.access_token}",
            "tr_id": "FHKST01010100"  # 주식현재가 시세
        }
        
        params = {
            "fid_cond_mrkt_div_code": "J",  # 국내
            "fid_input_iscd": ticker
        }
        
        try:
            res = requests.get(url, headers=headers, params=params, timeout=10).json()
            
            if res.get('rt_cd') != '0':
                raise KISAPIError(f"가격 조회 실패: {res.get('msg1')}")
            
            return res.get('output', {})
            
        except requests.RequestException as e:
            raise KISAPIError(f"API 요청 실패: {str(e)}")
    
    def get_daily_ohlcv(self, ticker: str, days: int = 20) -> Dict[str, Any]:
        """
        일봉 데이터 조회
        
        Args:
            ticker: 종목코드
            days: 조회 일수 (기본 20일)
            
        Returns:
            일별 OHLCV 데이터
            
        Raises:
            KISAPIError: 조회 실패
        """
        url = self.base_url + "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
        
        headers = {
            "content-type": "application/json",
            "appkey": self.auth.api_key,
            "appsecret": self.auth.api_secret,
            "authorization": f"Bearer {self.auth.access_token}",
            "tr_id": "FHKST03010100"  # 일봉 차트
        }
        
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": ticker,
            "fid_input_date_1": "00000101",  # 시작일 (가능한 한 과거)
            "fid_input_date_2": "99991231",  # 종료일 (오늘)
            "fid_period_div_code": "D",      # 일봉
            "fid_org_adj_prc": 0             # 수정가 적용
        }
        
        try:
            res = requests.get(url, headers=headers, params=params, timeout=10).json()
            
            if res.get('rt_cd') != '0':
                raise KISAPIError(f"차트 조회 실패: {res.get('msg1')}")
            
            return res.get('output2', [])
            
        except requests.RequestException as e:
            raise KISAPIError(f"API 요청 실패: {str(e)}")


class KISTrading:
    """한투 주문 관련 API"""
    
    def __init__(self, auth: KISAuth, account_id: str, account_suffix: str):
        self.auth = auth
        self.base_url = auth.base_url
        self.account_id = account_id
        self.account_suffix = account_suffix
    
    def get_balance(self) -> Dict[str, Any]:
        """
        계좌 잔고 조회
        
        Returns:
            {
                'output1': [보유 종목 리스트],
                'output2': [{'금액정보': ...}]
            }
            
        Raises:
            KISAPIError: 조회 실패
        """
        url = self.base_url + "/uapi/domestic-stock/v1/trading/inquire-balance"
        
        headers = {
            "content-type": "application/json",
            "appkey": self.auth.api_key,
            "appsecret": self.auth.api_secret,
            "authorization": f"Bearer {self.auth.access_token}",
            "tr_id": "VTTC8434R"
        }
        
        params = {
            "CANO": self.account_id,
            "ACNT_PRDT_CD": self.account_suffix,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "N",
            "INQR_DVSN": "01",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": ""
        }
        
        try:
            res = requests.get(url, headers=headers, params=params, timeout=10).json()
            
            if res.get('rt_cd') != '0':
                raise KISAPIError(f"잔고 조회 실패: {res.get('msg1')}")
            
            return res
            
        except requests.RequestException as e:
            raise KISAPIError(f"API 요청 실패: {str(e)}")
    
    def place_order(
        self,
        ticker: str,
        quantity: int,
        price: int = 0,
        order_type: str = "01"  # "00"=지정가, "01"=시장가
    ) -> Dict[str, Any]:
        """
        매수 주문
        
        Args:
            ticker: 종목코드 (예: '005930')
            quantity: 주문 수량
            price: 주문 가격 (시장가면 0)
            order_type: 주문 유형
            
        Returns:
            {'rt_cd': '0', 'msg1': '주문 완료', 'output': {'ODNO': '...'}}
            
        Raises:
            KISAPIError: 주문 실패
        """
        url = self.base_url + "/uapi/domestic-stock/v1/trading/order-cash"
        
        headers = {
            "content-type": "application/json",
            "appkey": self.auth.api_key,
            "appsecret": self.auth.api_secret,
            "authorization": f"Bearer {self.auth.access_token}",
            "tr_id": "VTTC0012U"  # 모의 매수
        }
        
        params = {
            "CANO": self.account_id,
            "ACNT_PRDT_CD": self.account_suffix,
            "PDNO": ticker,
            "ORD_DVSN": order_type,
            "ORD_QTY": str(quantity),
            "ORD_UNPR": str(price)
        }
        
        try:
            res = requests.post(
                url,
                headers=headers,
                data=json.dumps(params),
                timeout=10
            ).json()
            
            if res.get('rt_cd') != '0':
                raise KISAPIError(f"주문 실패: {res.get('msg1')}")
            
            logger.info(f"✓ 주문 완료: {ticker} {quantity}주 @ {price}원")
            return res
            
        except requests.RequestException as e:
            raise KISAPIError(f"API 요청 실패: {str(e)}")
    
    def cancel_order(self, original_order_no: str) -> Dict[str, Any]:
        """
        주문 취소
        
        Args:
            original_order_no: 원주문번호 (place_order 결과의 ODNO)
            
        Returns:
            취소 결과
            
        Raises:
            KISAPIError: 취소 실패
        """
        url = self.base_url + "/uapi/domestic-stock/v1/trading/order-rvsecncl"
        
        headers = {
            "content-type": "application/json",
            "appkey": self.auth.api_key,
            "appsecret": self.auth.api_secret,
            "authorization": f"Bearer {self.auth.access_token}",
            "tr_id": "VTTC0013U"
        }
        
        params = {
            "CANO": self.account_id,
            "ACNT_PRDT_CD": self.account_suffix,
            "KRX_FWDG_ORD_ORGNO": "",
            "RVSE_CNCL_DVSN_CD": "02",  # 취소
            "ORGN_ODNO": original_order_no,
            "ORD_DVSN": "00",
            "ORD_QTY": "0",
            "ORD_UNPR": "0",
            "QTY_ALL_ORD_YN": "Y"
        }
        
        try:
            res = requests.post(
                url,
                headers=headers,
                data=json.dumps(params),
                timeout=10
            ).json()
            
            if res.get('rt_cd') != '0':
                raise KISAPIError(f"취소 실패: {res.get('msg1')}")
            
            logger.info(f"✓ 주문 취소 완료: {original_order_no}")
            return res
            
        except requests.RequestException as e:
            raise KISAPIError(f"API 요청 실패: {str(e)}")


# ============================================================================
# 편의 함수 (전체 흐름을 한 번에)
# ============================================================================

def init_api(api_key: str, api_secret: str, base_url: str) -> tuple:
    """
    한투 API 초기화
    
    Returns:
        (auth, quotation, trading) 튜플
    """
    auth = KISAuth(api_key, api_secret, base_url)
    auth.get_access_token()
    
    quotation = KISQuotation(auth)
    trading = KISTrading(auth, account_id="XXXXXXXXXXXX", account_suffix="01")
    
    return auth, quotation, trading
