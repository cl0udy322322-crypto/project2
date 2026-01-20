import os
import yaml
import requests
import json
import pandas as pd
from tabulate import tabulate

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

# ==========================================
# 2. 토큰 및 헤더 생성
# ==========================================
def get_access_token():
    headers = {"content-type": "application/json"}
    body = {
        "grant_type": "client_credentials",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET
    }
    res = requests.post(f"{URL_BASE}/oauth2/tokenP", headers=headers, data=json.dumps(body))
    return res.json()['access_token']

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
# 3. 국내 주식 잔고 조회
# ==========================================
def get_kr_balance(token):
    headers = get_headers(token, "VTTC8434R") # 모의투자 주식잔고조회
    params = {
        "CANO": CANO,
        "ACNT_PRDT_CD": ACNT_PRDT_CD,
        "AFHR_FLPR_YN": "N",
        "OFL_YN": "N",
        "INQR_DVSN": "02",
        "UNPR_DVSN": "01",
        "FUND_STTL_ICLD_YN": "N",
        "FNCG_AMT_AUTO_RDPT_YN": "N",
        "PRCS_DVSN": "00",
        "CTX_AREA_FK100": "",
        "CTX_AREA_NK100": ""
    }
    
    res = requests.get(f"{URL_BASE}/uapi/domestic-stock/v1/trading/inquire-balance", headers=headers, params=params)
    data = res.json()
    
    if data['rt_cd'] != '0':
        print(f"[국내] 조회 실패: {data['msg1']}")
        return []

    output = []
    for item in data['output1']:
        # 보유수량이 0인 경우 제외 (주문만 넣고 미체결 상태 등)
        if int(item['hldg_qty']) > 0:
            output.append({
                '국가': '한국',
                '종목명': item['prdt_name'],
                '보유수량': int(item['hldg_qty']),
                '매입단가': float(item['pchs_avg_pric']),
                '현재가': int(item['prpr']),
                '수익률(%)': float(item['evlu_pfls_rt'])
            })
    return output

# ==========================================
# 4. 해외 주식 잔고 조회 (미국)
# ==========================================
def get_us_balance(token):
    headers = get_headers(token, "VTTS3012R") # 모의투자 해외주식 잔고
    params = {
        "CANO": CANO,
        "ACNT_PRDT_CD": ACNT_PRDT_CD,
        "OVRS_EXCG_CD": "NASD", # 대표적으로 나스닥 조회 (NYSE 등 다른 거래소 필요시 변경/추가 호출 필요)
        "TR_CRCY_CD": "USD",
        "CTX_AREA_FK200": "",
        "CTX_AREA_NK200": ""
    }
    
    res = requests.get(f"{URL_BASE}/uapi/overseas-stock/v1/trading/inquire-balance", headers=headers, params=params)
    data = res.json()
    
    if data['rt_cd'] != '0':
        print(f"[해외] 조회 실패: {data['msg1']}")
        return []

    output = []
    for item in data['output1']:
        if int(item['ovrs_cblc_qty']) > 0:
            output.append({
                '국가': '미국',
                '종목명': item['ovrs_item_name'],
                '보유수량': int(item['ovrs_cblc_qty']),
                '매입단가($)': float(item['pchs_avg_pric']),
                '현재가($)': float(item['now_pric2']),
                '수익률(%)': float(item['evlu_pfls_rt'])
            })
    return output

# ==========================================
# 5. 실행 및 출력
# ==========================================
if __name__ == "__main__":
    print(">>> 모의투자 계좌 잔고 조회 중...")
    token = get_access_token()
    
    # 데이터 수집
    kr_stocks = get_kr_balance(token)
    us_stocks = get_us_balance(token)
    
    all_stocks = kr_stocks + us_stocks
    
    if all_stocks:
        df = pd.DataFrame(all_stocks)
        
        # 보기 좋게 출력
        print("\n[보유 종목 현황]")
        print(tabulate(df, headers='keys', tablefmt='psql', showindex=False))
        
        # 간단한 요약
        print(f"\n총 보유 종목 수: {len(df)}개")
    else:
        print("\n[알림] 현재 보유중인 주식이 없습니다. (주문 미체결 상태일 수 있음)")