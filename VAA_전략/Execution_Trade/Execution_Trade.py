import os
import yaml
import pandas as pd
from tabulate import tabulate
import requests
import json
import math
import time

# ==========================================
# 1. 설정 및 초기화
# ==========================================
# 현재 실행 중인 스크립트(.py)의 절대 경로를 가져옵니다.
current_path = os.path.dirname(os.path.abspath(__file__))

# 해당 경로 내의 YAML 파일명을 합칩니다. (이름이 Trade.yaml인지 config.yaml인지 꼭 확인!)
yaml_file = os.path.join(current_path, 'Trade.yaml') 

with open(yaml_file, encoding='UTF-8') as f:
    config = yaml.load(f, Loader=yaml.FullLoader)

APP_KEY = config['hantu']['api_key']
APP_SECRET = config['hantu']['secret_key']
CANO = str(config['hantu']['account_id'])
ACNT_PRDT_CD = "01"
URL_BASE = "https://openapivts.koreainvestment.com:29443"
TOTAL_CASH = 300000  # 투자 원금

# ==========================================
# 2. 공통 유틸리티 함수 (토큰, 헤더)
# ==========================================
def get_access_token():
    """인증 토큰 발급"""
    headers = {"content-type": "application/json"}
    body = {
        "grant_type": "client_credentials",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET
    }
    path = "oauth2/tokenP"
    res = requests.post(f"{URL_BASE}/{path}", headers=headers, data=json.dumps(body))
    return res.json()['access_token']

def get_common_headers(token, tr_id):
    """API 호출용 공통 헤더 생성"""
    return {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": tr_id,
        "custtype": "P"
    }

# ==========================================
# 3. 국적별 시세 조회 및 주문 함수
# ==========================================

# --- [한국 주식] ---
def get_kr_price(token, code):
    """한국 주식 현재가 조회"""
    headers = get_common_headers(token, "FHKST01010100") # 주식현재가 시세
    params = {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": code}
    
    res = requests.get(f"{URL_BASE}/uapi/domestic-stock/v1/quotations/inquire-price", 
                       headers=headers, params=params)
    if res.json()['rt_cd'] == '0':
        return int(res.json()['output']['stck_prpr'])
    return None

def order_kr_stock(token, code, qty):
    """한국 주식 매수 주문 (시장가)"""
    headers = get_common_headers(token, "VTTC0802U") # 모의투자 현금 매수
    body = {
        "CANO": CANO,
        "ACNT_PRDT_CD": ACNT_PRDT_CD,
        "PDNO": code,
        "ORD_DVSN": "01",   # 01: 시장가
        "ORD_QTY": str(qty),
        "ORD_UNPR": "0"
    }
    res = requests.post(f"{URL_BASE}/uapi/domestic-stock/v1/trading/order-cash", 
                        headers=headers, data=json.dumps(body))
    return res.json()

# --- [미국 주식] ---
# --- [미국 주식 현재가 조회 수정본] ---
def get_us_price(token, code):
    """미국 주식 현재가 조회 (빈 문자열 에러 방지)"""
    headers = get_common_headers(token, "HHDFS00000300") # 해외주식 현재체결가
    params = {
        "AUTH": "", 
        "EXCD": "NAS", # SQQQ는 나스닥 종목
        "SYMB": code
    } 
    res = requests.get(f"{URL_BASE}/uapi/overseas-price/v1/quotations/price", 
                       headers=headers, params=params)
    
    res_json = res.json()
    
    if res_json.get('rt_cd') == '0':
        last_price = res_json['output'].get('last', '') # 가격 필드 가져오기
        
        # [핵심] 가격이 비어있거나 공백인 경우 체크
        if last_price and last_price.strip() != '':
            return float(last_price)
        else:
            print(f"  -> [경고] {code}의 현재가 데이터가 비어있습니다. (장외 시간일 수 있음)")
            return None
    else:
        print(f"  -> [오류] {code} 시세 조회 API 실패: {res_json.get('msg1')}")
        return None

def order_us_stock(token, code, qty):
    """미국 주식 매수 주문 (지정가 - 모의투자는 시장가 제한이 있을 수 있음)"""
    # 주의: 미국 주식 주문은 실전/모의 TR ID가 다르고 복잡합니다.
    # 여기서는 모의투자 미국 매수(VTTT1002U) 사용
    
    # 현재가를 가져와서 그 가격으로 지정가 주문을 넣는 방식을 추천 (안정성)
    price = get_us_price(token, code) 
    if price is None: return {"rt_cd": "1", "msg1": "현재가 조회 실패"}

    headers = get_common_headers(token, "VTTT1002U") 
    body = {
        "CANO": CANO,
        "ACNT_PRDT_CD": ACNT_PRDT_CD,
        "OVRS_EXCG_CD": "NASD", # 거래소 코드 (NASD, NYSE, AMEX)
        "PDNO": code,
        "ORD_QTY": str(qty),
        "OVRS_ORD_UNPR": str(price), # 현재가로 지정가 주문
        "ORD_SVR_DVSN_CD": "0",
        "ORD_DVSN": "00" # 00: 지정가
    }
    res = requests.post(f"{URL_BASE}/uapi/overseas-stock/v1/trading/order", 
                        headers=headers, data=json.dumps(body))
    return res.json()

# ==========================================
# 4. 메인 실행 로직 (포트폴리오 분배)
# ==========================================
def main():
    print(">>> 시스템 시작...")
    
    # 1. 토큰 발급
    token = get_access_token()
    print(f"[인증] 토큰 발급 완료")

    # 2. 포트폴리오(CSV) 로드
    try:
        csv_path = os.path.join(current_path, 'target_portfolio.csv')
        portfolio = pd.read_csv(csv_path)
        print(f"[데이터] 타겟 포트폴리오 로드 완료 ({len(portfolio)}개 종목)")
    except Exception as e:
        print("[오류] CSV 파일을 찾을 수 없습니다.")
        return

    # 3. 종목별 주문 실행
    for index, row in portfolio.iterrows():
        code = str(row['code'])
        target_weight = float(row['weight'])
        
        # 할당 금액 계산
        target_amount = TOTAL_CASH * target_weight
        
        print(f"\n[{index+1}] 종목 분석: {code} (비중 {target_weight*100}%)")

        # 4. 국적 판별 로직 (한국: 숫자 6자리, 미국: 알파벳)
        is_korea_stock = code.isdigit() and len(code) == 6
        
        if is_korea_stock:
            # === 한국 주식 로직 ===
            print(f"  -> 시장: 한국(KRX)")
            current_price = get_kr_price(token, code)
            
            if current_price:
                # 수량 계산 (금액 / 현재가, 소수점 버림)
                qty = math.floor(target_amount / current_price)
                if qty > 0:
                    print(f"  -> 주문: 시장가 {qty}주 매수 시도")
                    result = order_kr_stock(token, code, qty)
                    if result['rt_cd'] == '0':
                        print(f"  -> [성공] 주문번호: {result['output']['KRX_FWDG_ORD_ORGNO']}")
                    else:
                        print(f"  -> [실패] {result['msg1']}")
                else:
                    print("  -> [Pass] 금액 부족으로 매수 수량 0")
            else:
                print("  -> [오류] 시세 조회 실패")

        else:
            # === 미국 주식 로직 ===
            print(f"  -> 시장: 미국(US)")
            # 환율 조회 로직이 필요하지만, 여기선 1달러=1400원 고정으로 단순 계산
            EXCHANGE_RATE = 1400 
            current_price_usd = get_us_price(token, code)
            
            if current_price_usd:
                current_price_krw = current_price_usd * EXCHANGE_RATE
                qty = math.floor(target_amount / current_price_krw)
                
                if qty > 0:
                    print(f"  -> 주문: 지정가(현재가) {qty}주 매수 시도 (${current_price_usd})")
                    result = order_us_stock(token, code, qty)
                    if result['rt_cd'] == '0':
                        print(f"  -> [성공] 주문번호: {result['output']['ODNO']}")
                    else:
                        print(f"  -> [실패] {result['msg1']}")
                else:
                    print("  -> [Pass] 금액 부족으로 매수 수량 0")
            else:
                print("  -> [오류] 시세 조회 실패")
        
        # API 호출 제한 방지 (1초 대기)
        time.sleep(0.5)

if __name__ == "__main__":
    main()