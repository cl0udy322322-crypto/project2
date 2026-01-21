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
current_path = os.path.dirname(os.path.abspath(__file__))
yaml_file = os.path.join(current_path, 'Trade.yaml') 

with open(yaml_file, encoding='UTF-8') as f:
    config = yaml.load(f, Loader=yaml.FullLoader)

APP_KEY = config['hantu']['api_key']
APP_SECRET = config['hantu']['secret_key']
CANO = str(config['hantu']['account_id'])
ACNT_PRDT_CD = "01"
URL_BASE = "https://openapivts.koreainvestment.com:29443"
TOTAL_CASH = 10000000  # 투자 원금

# ==========================================
# 2. 공통 유틸리티 함수
# ==========================================
def get_access_token():
    headers = {"content-type": "application/json"}
    body = {"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}
    res = requests.post(f"{URL_BASE}/oauth2/tokenP", headers=headers, data=json.dumps(body))
    return res.json()['access_token']

def get_common_headers(token, tr_id):
    return {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY, "appsecret": APP_SECRET,
        "tr_id": tr_id, "custtype": "P"
    }

# ==========================================
# 3. 국적별 시세 조회 및 주문 함수
# ==========================================

# --- [한국 주식] ---
def get_kr_price(token, code):
    headers = get_common_headers(token, "FHKST01010100")
    params = {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": code}
    res = requests.get(f"{URL_BASE}/uapi/domestic-stock/v1/quotations/inquire-price", headers=headers, params=params)
    if res.json()['rt_cd'] == '0':
        return int(res.json()['output']['stck_prpr'])
    return None

def order_kr_stock(token, code, qty):
    headers = get_common_headers(token, "VTTC0802U")
    body = {"CANO": CANO, "ACNT_PRDT_CD": ACNT_PRDT_CD, "PDNO": code, "ORD_DVSN": "01", "ORD_QTY": str(qty), "ORD_UNPR": "0"}
    res = requests.post(f"{URL_BASE}/uapi/domestic-stock/v1/trading/order-cash", headers=headers, data=json.dumps(body))
    return res.json()

# --- [미국 주식: 거래소 자동 탐색 적용] ---
def get_us_price_and_exchange(token, code):
    """나스닥, 뉴욕, 아멕스 거래소를 순차적으로 조회하여 가격과 거래소 코드를 반환"""
    # (조회용 코드, 주문용 코드) 매핑
    exchanges = [
        ("NAS", "NASD"), # 나스닥
        ("NYS", "NYSE"), # 뉴욕
        ("AMS", "AMEX")  # 아멕스
    ]
    
    headers = get_common_headers(token, "HHDFS00000300")
    
    for view_code, order_code in exchanges:
        time.sleep(0.3) # API 간격 유지
        params = {"AUTH": "", "EXCD": view_code, "SYMB": code}
        res = requests.get(f"{URL_BASE}/uapi/overseas-price/v1/quotations/price", headers=headers, params=params).json()
        
        if res.get('rt_cd') == '0':
            last_price = res['output'].get('last', '')
            if last_price and last_price.strip() != '':
                return float(last_price), order_code
            
            # 실시간가 없으면 전일가(base) 사용
            base_price = res['output'].get('base', '')
            if base_price and base_price.strip() != '':
                return float(base_price), order_code
    return None, None

def order_us_stock(token, code, qty, price, exchange_code):
    """전달받은 거래소 코드를 사용하여 주문 실행"""
    headers = get_common_headers(token, "VTTT1002U") 
    body = {
        "CANO": CANO,
        "ACNT_PRDT_CD": ACNT_PRDT_CD,
        "OVRS_EXCG_CD": exchange_code, # 탐색된 거래소 코드 사용
        "PDNO": code,
        "ORD_QTY": str(qty),
        "OVRS_ORD_UNPR": str(price),
        "ORD_SVR_DVSN_CD": "0",
        "ORD_DVSN": "00"
    }
    res = requests.post(f"{URL_BASE}/uapi/overseas-stock/v1/trading/order", headers=headers, data=json.dumps(body))
    return res.json()

# ==========================================
# 4. 메인 실행 로직
# ==========================================
def main():
    print(">>> 시스템 시작...")
    token = get_access_token()
    print(f"[인증] 토큰 발급 완료")

    try:
        csv_path = os.path.join(current_path, 'target_portfolio.csv')
        portfolio = pd.read_csv(csv_path)
        print(f"[데이터] 타겟 포트폴리오 로드 완료 ({len(portfolio)}개 종목)")
    except Exception as e:
        print("[오류] CSV 파일을 찾을 수 없습니다.")
        return

    for index, row in portfolio.iterrows():
        code = str(row['code'])
        target_weight = float(row['weight'])
        target_amount = TOTAL_CASH * target_weight # 할당 금액 계산
        
        print(f"\n[{index+1}] 종목 분석: {code} (비중 {target_weight*100}%)")

        # 국적 판별 (한국: 숫자 6자리, 미국: 알파벳)
        is_korea_stock = code.isdigit() and len(code) == 6
        
        if is_korea_stock:
            print(f"  -> 시장: 한국(KRX)")
            current_price = get_kr_price(token, code)
            if current_price:
                qty = math.floor(target_amount / current_price)
                if qty > 0:
                    result = order_kr_stock(token, code, qty)
                    print(f"  -> [결과] {'성공 주문번호:' + result['output']['KRX_FWDG_ORD_ORGNO'] if result['rt_cd'] == '0' else '실패:' + result['msg1']}")
                else:
                    print("  -> [Pass] 금액 부족")
            else:
                print("  -> [오류] 시세 조회 실패")

        else:
            print(f"  -> 시장: 미국(US) 탐색 중...")
            EXCHANGE_RATE = 1400 
            
            # 거래소와 가격을 동시에 가져옴
            current_price_usd, found_exchange = get_us_price_and_exchange(token, code)
            
            if current_price_usd and found_exchange:
                print(f"  -> 확인된 거래소: {found_exchange}")
                current_price_krw = current_price_usd * EXCHANGE_RATE
                qty = math.floor(target_amount / current_price_krw)
                
                if qty > 0:
                    print(f"  -> 주문: {found_exchange} 지정가 {qty}주 매수 시도 (${current_price_usd})")
                    result = order_us_stock(token, code, qty, current_price_usd, found_exchange)
                    if result['rt_cd'] == '0':
                        print(f"  -> [성공] 주문번호: {result['output']['ODNO']}")
                    else:
                        print(f"  -> [실패] {result['msg1']}")
                else:
                    print("  -> [Pass] 금액 부족")
            else:
                print("  -> [오류] 나스닥/뉴욕/아멕스에 해당 종목이 없거나 장외 시간입니다.")
        
        time.sleep(3.0)

if __name__ == "__main__":
    main()