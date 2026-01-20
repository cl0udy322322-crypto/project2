import os
import yaml
import requests
import json
import pandas as pd
from tabulate import tabulate
from datetime import datetime
import time

# ==========================================
# 1. 설정 및 초기화 (경로 및 파일명 자동 체크)
# ==========================================
current_path = os.path.dirname(os.path.abspath(__file__))
# config.yaml 또는 Trade.yaml 중 있는 파일을 선택합니다.
yaml_file = os.path.join(current_path, 'config.yaml') 
if not os.path.exists(yaml_file):
    yaml_file = os.path.join(current_path, 'Trade.yaml')

with open(yaml_file, encoding='UTF-8') as f:
    config = yaml.load(f, Loader=yaml.FullLoader)

APP_KEY = config['hantu']['api_key']
APP_SECRET = config['hantu']['secret_key']
CANO = str(config['hantu']['account_id'])
ACNT_PRDT_CD = "01"
URL_BASE = "https://openapivts.koreainvestment.com:29443" # 모의투자

# ==========================================
# 2. 토큰 재사용 로직 (분당 1회 제한 회피)
# ==========================================
def get_access_token():
    token_file = os.path.join(current_path, "hantu_token.json")
    
    # 기존 토큰이 있고 유효한지 확인 (20시간 이내)
    if os.path.exists(token_file):
        with open(token_file, 'r', encoding='utf-8') as f:
            token_data = json.load(f)
        if time.time() - token_data['issued_at'] < 72000:
            return token_data['access_token']

    # 새로 발급
    print(">>> 토큰을 서버에서 새로 발급받습니다...")
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
        print(f"❌ 토큰 발급 실패: {res_data}")
        raise KeyError("토큰을 가져올 수 없습니다.")

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
# 3. 통합 자산/잔고 조회 (KeyError 방어 버전)
# ==========================================
def get_integrated_balance(token):
    results = []
    print("\n" + "="*50)
    
    # --- [국내 잔고] ---
    headers = get_headers(token, "VTTC8434R")
    params = {
        "CANO": CANO, "ACNT_PRDT_CD": ACNT_PRDT_CD, "AFHR_FLPR_YN": "N", "OFL_YN": "N",
        "INQR_DVSN": "02", "UNPR_DVSN": "01", "FUND_STTL_ICLD_YN": "N", "FNCG_AMT_AUTO_RDPT_YN": "N",
        "PRCS_DVSN": "00", "CTX_AREA_FK100": "", "CTX_AREA_NK100": ""
    }
    kr_res = requests.get(f"{URL_BASE}/uapi/domestic-stock/v1/trading/inquire-balance", headers=headers, params=params).json()
    
    if kr_res.get('rt_cd') == '0':
        summary_list = kr_res.get('output2', [])
        if summary_list:
            s = summary_list[0]
            print(f" [한국 자산] 총액: {format(int(float(s.get('tot_evlu_amt',0))), ',')}원 / 예수금: {format(int(float(s.get('dnca_tot_amt',0))), ',')}원")
        
        for item in kr_res.get('output1', []):
            if int(item.get('hldg_qty', 0)) > 0:
                results.append({'국가': '한국', '종목명': item['prdt_name'], '수량': item['hldg_qty'], '수익률': item['evlu_pfls_rt']})

    # --- [해외 잔고] ---
    headers = get_headers(token, "VTTS3012R")
    params = {"CANO": CANO, "ACNT_PRDT_CD": ACNT_PRDT_CD, "OVRS_EXCG_CD": "NASD", "TR_CRCY_CD": "USD", "CTX_AREA_FK200": "", "CTX_AREA_NK200": ""}
    us_res = requests.get(f"{URL_BASE}/uapi/overseas-stock/v1/trading/inquire-balance", headers=headers, params=params).json()
    
    if us_res.get('rt_cd') == '0':
        # output3 또는 output2에서 안전하게 달러 예수금 추출
        us_summ = us_res.get('output3', us_res.get('output2', [{}])[0] if us_res.get('output2') else {})
        usd_cash = us_summ.get('frcr_dncl_amt_2', '0')
        print(f" [미국 자산] 외화 예수금: ${usd_cash}")
        
        for item in us_res.get('output1', []):
            if int(float(item.get('ovrs_cblc_qty', 0))) > 0:
                results.append({'국가': '미국', '종목명': item['ovrs_item_name'], '수량': item['ovrs_cblc_qty'], '수익률': item['evlu_pfls_rt']})
    
    print("="*50)
    return results

# ==========================================
# 4. 당일 체결 로그 (증빙 파일 생성)
# ==========================================
def get_execution_log(token):
    today = datetime.now().strftime("%Y%m%d")
    logs = []

    # [한국]
    headers = get_headers(token, "VTTC8001R")
    params = {"CANO": CANO, "ACNT_PRDT_CD": ACNT_PRDT_CD, "INQR_STRT_DT": today, "INQR_END_DT": today, "SLL_BUY_DVSN_CD": "00", "INQR_DVSN": "00", "PDNO": "", "CCLD_DVSN": "01", "ORD_GNO_BRNO": "", "ODNO": "", "INQR_DVSN_3": "00", "INQR_DVSN_1": "", "CTX_AREA_FK100": "", "CTX_AREA_NK100": ""}
    res = requests.get(f"{URL_BASE}/uapi/domestic-stock/v1/trading/inquire-daily-ccld", headers=headers, params=params).json()
    if res.get('rt_cd') == '0' and res.get('output1'):
        for item in res['output1']:
            logs.append({'시간': item['ord_tmd'], '종목명': item['prdt_name'], '구분': item['sll_buy_dvsn_cd_name'], '수량': item['tot_ccld_qty'], '단가': item['avg_prvs'], '통화': 'KRW'})

    # [미국]
    headers = get_headers(token, "VTTS3035R")
    params = {"CANO": CANO, "ACNT_PRDT_CD": ACNT_PRDT_CD, "STRT_DT": today, "END_DT": today, "OVRS_EXCG_CD": "NASD", "SLL_BUY_DVSN_CD": "00", "CTX_AREA_FK200": "", "CTX_AREA_NK200": ""}
    res = requests.get(f"{URL_BASE}/uapi/overseas-stock/v1/trading/inquire-ccnl", headers=headers, params=params).json()
    if res.get('rt_cd') == '0' and res.get('output'):
        for item in res['output']:
            if int(float(item.get('ft_ccld_qty', 0))) > 0:
                logs.append({'시간': item['ord_tmd'], '종목명': item['prdt_name'], '구분': item['sll_buy_dvsn_cd_name'], '수량': item['ft_ccld_qty'], '단가': item['ft_ccld_unpr3'], '통화': 'USD'})

    return logs

# ==========================================
# 5. 실행부
# ==========================================
if __name__ == "__main__":
    print(f">>> [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 시스템 가동")
    try:
        token = get_access_token()
        
        # 잔고 출력
        stocks = get_integrated_balance(token)
        if stocks:
            print("\n[현재 보유 종목 현황]")
            print(tabulate(pd.DataFrame(stocks), headers='keys', tablefmt='psql', showindex=False))
        
        # 체결 로그 저장
        trade_logs = get_execution_log(token)
        if trade_logs:
            df_logs = pd.DataFrame(trade_logs)
            print("\n>>> 오늘의 체결 내역 (증빙용)")
            print(tabulate(df_logs, headers='keys', tablefmt='psql', showindex=False))
            file_name = f"trading_proof_{datetime.now().strftime('%Y%m%d')}.csv"
            df_logs.to_csv(os.path.join(current_path, file_name), index=False, encoding='utf-8-sig')
            print(f"\n✅ 증빙 파일 저장 완료: {file_name}")
        else:
            print("\n[알림] 금일 체결 내역이 없습니다.")
            
    except Exception as e:
        print(f"\n❌ 실행 중 에러 발생: {e}")