import os
import yaml
import requests
import json
import time
from datetime import datetime

# ==========================================
# 1. 설정 및 초기화
# ==========================================
current_path = os.path.dirname(os.path.abspath(__file__))
yaml_file = os.path.join(current_path, 'config.yaml')
if not os.path.exists(yaml_file):
    yaml_file = os.path.join(current_path, 'Trade.yaml')

with open(yaml_file, encoding='UTF-8') as f:
    config = yaml.load(f, Loader=yaml.FullLoader)

APP_KEY = config['hantu']['api_key']
APP_SECRET = config['hantu']['secret_key']
CANO = str(config['hantu']['account_id'])
ACNT_PRDT_CD = "01"
URL_BASE = "https://openapivts.koreainvestment.com:29443"

# ==========================================
# 2. 토큰 및 헤더 함수
# ==========================================
def get_access_token():
    token_file = os.path.join(current_path, "hantu_token.json")
    if os.path.exists(token_file):
        with open(token_file, 'r', encoding='utf-8') as f:
            token_data = json.load(f)
        if time.time() - token_data['issued_at'] < 72000:
            return token_data['access_token']

    headers = {"content-type": "application/json"}
    body = {"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}
    res = requests.post(f"{URL_BASE}/oauth2/tokenP", headers=headers, data=json.dumps(body))
    res_data = res.json()
    if 'access_token' in res_data:
        save_data = {'access_token': res_data['access_token'], 'issued_at': time.time()}
        with open(token_file, 'w', encoding='utf-8') as f:
            json.dump(save_data, f)
        return res_data['access_token']
    else:
        raise KeyError(f"토큰 발급 실패: {res_data}")

def get_headers(token, tr_id):
    return {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": tr_id,
        "custtype": "P"
    }

# ==========================================
# 3. 전량 매도 로직
# ==========================================

def liquidate_kr_stocks(token):
    """한국 주식 전량 매수 종목 확인 후 매도"""
    print("\n>>> [한국 주식] 잔고 확인 및 매도 시작...")
    headers = get_headers(token, "VTTC8434R") # 모의투자 잔고조회
    params = {
        "CANO": CANO, "ACNT_PRDT_CD": ACNT_PRDT_CD, "AFHR_FLPR_YN": "N", "OFL_YN": "N",
        "INQR_DVSN": "02", "UNPR_DVSN": "01", "FUND_STTL_ICLD_YN": "N", "FNCG_AMT_AUTO_RDPT_YN": "N",
        "PRCS_DVSN": "00", "CTX_AREA_FK100": "", "CTX_AREA_NK100": ""
    }
    res = requests.get(f"{URL_BASE}/uapi/domestic-stock/v1/trading/inquire-balance", headers=headers, params=params).json()

    if res.get('rt_cd') == '0':
        stocks = res.get('output1', [])
        if not stocks: print("  - 보유 중인 한국 주식이 없습니다.")
        
        for item in stocks:
            qty = int(float(item.get('hldg_qty', 0)))
            if qty > 0:
                code = item['pdno']
                name = item['prdt_name']
                print(f"  -> [{name}({code})] {qty}주 매도 주문 중 (시장가)...")
                
                sell_headers = get_headers(token, "VTTC0011U") # 모의투자 현금 매도
                sell_body = {
                    "CANO": CANO, "ACNT_PRDT_CD": ACNT_PRDT_CD, "PDNO": code,
                    "ORD_DVSN": "01", "ORD_QTY": str(qty), "ORD_UNPR": "0"
                }
                sell_res = requests.post(f"{URL_BASE}/uapi/domestic-stock/v1/trading/order-cash", headers=sell_headers, data=json.dumps(sell_body)).json()
                
                if sell_res.get('rt_cd') == '0':
                    print(f"     [성공] 주문번호: {sell_res['output']['KRX_FWDG_ORD_ORGNO']}")
                else:
                    print(f"     [실패] {sell_res.get('msg1')}")
                time.sleep(0.2)
    else:
        print(f"  - 한국 잔고 조회 실패: {res.get('msg1')}")

def liquidate_us_stocks(token):
    """미국 주식 전량 매수 종목 확인 후 매도"""
    print("\n>>> [미국 주식] 잔고 확인 및 매도 시작...")
    headers = get_headers(token, "VTTS3012R") # 모의투자 해외잔고조회
    params = {"CANO": CANO, "ACNT_PRDT_CD": ACNT_PRDT_CD, "OVRS_EXCG_CD": "NASD", "TR_CRCY_CD": "USD", "CTX_AREA_FK200": "", "CTX_AREA_NK200": ""}
    res = requests.get(f"{URL_BASE}/uapi/overseas-stock/v1/trading/inquire-balance", headers=headers, params=params).json()

    if res.get('rt_cd') == '0':
        stocks = res.get('output1', [])
        if not stocks: print("  - 보유 중인 미국 주식이 없습니다.")
        
        for item in stocks:
            qty = int(float(item.get('ovrs_cblc_qty', 0)))
            if qty > 0:
                code = item['ovrs_pdno']
                name = item['ovrs_item_name']
                price = item['now_pric2'] # 현재가로 매도
                exch_code = item.get('ovrs_excg_cd', 'NASD')
                
                print(f"  -> [{name}({code})] {qty}주 매도 주문 중 (지정가 ${price})...")
                
                sell_headers = get_headers(token, "VTTT1001U") # 모의투자 미국 매도
                sell_body = {
                    "CANO": CANO, "ACNT_PRDT_CD": ACNT_PRDT_CD, "OVRS_EXCG_CD": exch_code,
                    "PDNO": code, "ORD_QTY": str(qty), "OVRS_ORD_UNPR": str(price),
                    "ORD_SVR_DVSN_CD": "0", "ORD_DVSN": "00"
                }
                sell_res = requests.post(f"{URL_BASE}/uapi/overseas-stock/v1/trading/order", headers=sell_headers, data=json.dumps(sell_body)).json()
                
                if sell_res.get('rt_cd') == '0':
                    print(f"     [성공] 주문번호: {sell_res['output']['ODNO']}")
                else:
                    print(f"     [실패] {sell_res.get('msg1')}")
                time.sleep(0.2)
    else:
        print(f"  - 미국 잔고 조회 실패: {res.get('msg1')}")

# ==========================================
# 4. 메인 실행
# ==========================================
if __name__ == "__main__":
    print(f"=== [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 전량 매도 시스템 가동 ===")
    try:
        auth_token = get_access_token()
        liquidate_kr_stocks(auth_token)
        liquidate_us_stocks(auth_token)
        print("\n>>> 모든 프로세스가 완료되었습니다.")
    except Exception as e:
        print(f"\n 오류 발생: {e}")