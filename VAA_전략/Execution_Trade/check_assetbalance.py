import os
import yaml
import requests
import json
import pandas as pd
from tabulate import tabulate
from datetime import datetime
import time

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
        "appkey": APP_KEY, "appsecret": APP_SECRET,
        "tr_id": tr_id, "custtype": "P"
    }

# ==========================================
# 3. 통합 잔고 조회 (에러 방지 로직 강화)
# ==========================================
def display_total_status(token):
    holdings = []
    
    print("\n" + "="*75)
    print(f" [ 계좌 통합 관리 시스템 ]  조회일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*75)

    # --- [1] 한국 잔고 조회 ---
    kr_res = requests.get(
        f"{URL_BASE}/uapi/domestic-stock/v1/trading/inquire-balance",
        headers=get_headers(token, "VTTC8434R"),
        params={
            "CANO": CANO, "ACNT_PRDT_CD": ACNT_PRDT_CD, "AFHR_FLPR_YN": "N", "OFL_YN": "N",
            "INQR_DVSN": "02", "UNPR_DVSN": "01", "FUND_STTL_ICLD_YN": "N", "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00", "CTX_AREA_FK100": "", "CTX_AREA_NK100": ""
        }
    ).json()
    
    if kr_res.get('rt_cd') == '0':
        kr_summary_list = kr_res.get('output2', [])
        if kr_summary_list and len(kr_summary_list) > 0:
            kr_s = kr_summary_list[0]
            print(f" ▶ 한국 총 자산: {format(int(float(kr_s.get('tot_evlu_amt', 0))), ',')} 원")
            print(f" ▶ 한국 예수금:   {format(int(float(kr_s.get('dnca_tot_amt', 0))), ',')} 원")
        else:
            print(f" ▶ 한국 자산 요약 정보가 없습니다.")
        
        for item in kr_res.get('output1', []):
            qty = int(float(item.get('hldg_qty', 0)))
            if qty > 0:
                holdings.append({
                    '국가': '한국', '종목명': item['prdt_name'], '보유수량': qty, 
                    '매입단가': format(int(float(item['pchs_avg_pric'])), ','),
                    '현재가': format(int(float(item['prpr'])), ','),
                    '수익률(%)': item['evlu_pfls_rt']
                })

    # --- [2] 미국 잔고 조회 (빈 리스트 에러 완벽 방어) ---
    us_res = requests.get(
        f"{URL_BASE}/uapi/overseas-stock/v1/trading/inquire-balance",
        headers=get_headers(token, "VTTS3012R"),
        params={"CANO": CANO, "ACNT_PRDT_CD": ACNT_PRDT_CD, "OVRS_EXCG_CD": "NASD", "TR_CRCY_CD": "USD", "CTX_AREA_FK200": "", "CTX_AREA_NK200": ""}
    ).json()
    
    usd_cash = '0'
    if us_res.get('rt_cd') == '0':
        # [핵심 수정] 리스트 존재 여부와 길이를 동시에 체크
        us_summary_list = us_res.get('output2', [])
        
        if isinstance(us_summary_list, list) and len(us_summary_list) > 0:
            usd_cash = us_summary_list[0].get('frcr_dncl_amt_2', '0')
        else:
            # output2가 없으면 output3 딕셔너리에서 시도
            usd_cash = us_res.get('output3', {}).get('frcr_dncl_amt_2', '0')
        
        print(f" ▶ 미국 예수금:   $ {usd_cash}")
        
        for item in us_res.get('output1', []):
            qty_val = item.get('ovrs_cblc_qty', 0)
            if qty_val and int(float(qty_val)) > 0:
                holdings.append({
                    '국가': '미국', '종목명': item['ovrs_item_name'], '보유수량': int(float(qty_val)), 
                    '매입단가': item['pchs_avg_pric'], '현재가': item['now_pric2'], 
                    '수익률(%)': item['evlu_pfls_rt']
                })
    else:
        print(f" ▶ 미국 잔고 조회 결과가 없습니다. (미국 예수금: $0)")
    
    print("-" * 75)

    # --- [3] 보유 종목 테이블 출력 ---
    if holdings:
        print("\n [ 실시간 보유 종목 현황 ]")
        df = pd.DataFrame(holdings)
        # 예시로 보여주신 컬럼 순서로 정렬
        cols = ['국가', '종목명', '보유수량', '매입단가', '현재가', '수익률(%)']
        df = df[cols]
        print(tabulate(df, headers='keys', tablefmt='psql', showindex=False))
    else:
        print("\n 현재 보유 중인 주식이 없습니다. (전액 현금 상태)")

# ==========================================
# 4. 당일 거래 내역
# ==========================================
def display_today_trade(token):
    today = datetime.now().strftime("%Y%m%d")
    logs = []
    
    # 한국 체결
    res_kr = requests.get(f"{URL_BASE}/uapi/domestic-stock/v1/trading/inquire-daily-ccld", headers=get_headers(token, "VTTC8001R"), params={"CANO": CANO, "ACNT_PRDT_CD": ACNT_PRDT_CD, "INQR_STRT_DT": today, "INQR_END_DT": today, "SLL_BUY_DVSN_CD": "00", "INQR_DVSN": "00", "PDNO": "", "CCLD_DVSN": "01", "ORD_GNO_BRNO": "", "ODNO": "", "INQR_DVSN_3": "00", "INQR_DVSN_1": "", "CTX_AREA_FK100": "", "CTX_AREA_NK100": ""}).json()
    if res_kr.get('rt_cd') == '0' and res_kr.get('output1'):
        for item in res_kr['output1']:
            logs.append({'시간': item['ord_tmd'], '종목명': item['prdt_name'], '구분': item['sll_buy_dvsn_cd_name'], '수량': item['tot_ccld_qty'], '단가': item['avg_prvs'], '통화': 'KRW'})

    if logs:
        print("\n [ 금일 주문 체결 내역 (증빙용) ]")
        print(tabulate(pd.DataFrame(logs), headers='keys', tablefmt='psql', showindex=False))
    else:
        print("\n 금일 거래 내역이 없습니다.")

# ==========================================
# 메인 실행부
# ==========================================
if __name__ == "__main__":
    try:
        auth_token = get_access_token()
        display_total_status(auth_token)
        display_today_trade(auth_token)
        print("\n" + "="*75)
    except Exception as e:
        print(f"\n 시스템 오류 발생: {e}")