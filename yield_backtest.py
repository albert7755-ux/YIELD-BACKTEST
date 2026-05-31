"""
國債殖利率突破 → 基金+債券績效回測系統
當 10Y/20Y/30Y 國債殖利率首次向上突破特定門檻時，
分析持有的基金和債券在那之後 1M/3M/6M/1Y/2Y/3Y 的績效。
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
import gspread
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request
import json
from datetime import datetime
from io import StringIO
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(page_title="國債殖利率突破回測", layout="wide", page_icon="📈")

# ==========================================
# 常數
# ==========================================
FUND_FOLDER_ID = "1i1-zUzLNnuwo2NVWijubvBICLbladZQO"
BOND_FOLDER_ID = "1k0RxJn5KKCTWdTEDZqq0Q5hnfwkuPgGK"

FUND_DB = {
    "F00001DRQQ_FO": "PIMCO收益增長",
    "F0GBR04AY1_FO": "富達全球動能多元基金",
    "F00000VH29_FO": "施羅德環球收益成長基金",
    "F0GBR04SG1_FO": "AV04駿利亨德森平衡基金",
    "F0GBR04AMK_FO": "貝萊德環球資產配置基金",
    "F00000MLER_FO": "聯博-新興市場多元收益基金",
    "F00000V557_FO": "聯博全球多元",
    "F00001EQPP_FO": "富邦台美雙星多重",
    "F00000ZXFV_FO": "施羅德環球收息債券",
    "F00000PR1I_FO": "富達全球優質債券基金",
    "F0000176Y4_FO": "富達永續發展全球存股優勢基金",
    "F000011JGT_FO": "群益潛力收益多重",
    "F0GBR04MRL_FO": "聯博美國收益EA穩定月配",
    "FOGBR05KHT_FO": "PIMCO多元收益",
    "F0000000P6_FO": "貝萊德全球智慧數據股票入息基金",
    "F00000T0K2_FO": "聯博-美國成長基金EP",
    "F00000T1CG_FO": "聯博-優化波動股票基金",
    "F000015CRE_FO": "富蘭克林穩定月收益A(acc)",
}

LOCAL_DB = {
    "US02079KBP12": {"issuer": "Alphabet公司債6", "coupon": 5.65, "maturity": "2056"},
    "US30303MAE21": {"issuer": "Meta公司債9", "coupon": 5.625, "maturity": "2055"},
    "US64110LBA35": {"issuer": "網飛公司債3", "coupon": 5.4, "maturity": "2054"},
    "US03769MAC01": {"issuer": "阿波羅公司債1", "coupon": 5.8, "maturity": "2054"},
    "US191216DS69": {"issuer": "可口可樂公司債5", "coupon": 5.3, "maturity": "2054"},
    "US92343VGW81": {"issuer": "威瑞森電信債12", "coupon": 5.5, "maturity": "2054"},
    "XS2747599509": {"issuer": "沙烏地阿拉伯債7", "coupon": 5.75, "maturity": "2054"},
    "US29736RAU41": {"issuer": "雅詩蘭黛公司債3", "coupon": 5.15, "maturity": "2053"},
    "US037833EW60": {"issuer": "蘋果公司債14", "coupon": 4.85, "maturity": "2053"},
    "US91324PEW86": {"issuer": "聯合健康集團債9", "coupon": 5.05, "maturity": "2053"},
    "US532457CG18": {"issuer": "禮來公司債1", "coupon": 4.875, "maturity": "2053"},
    "US91324PES74": {"issuer": "聯合健康集團債5", "coupon": 5.875, "maturity": "2053"},
    "US459200KZ37": {"issuer": "IBM公司債4", "coupon": 5.1, "maturity": "2053"},
    "US459200KV23": {"issuer": "IBM公司債1", "coupon": 4.9, "maturity": "2052"},
    "US45866FAX24": {"issuer": "洲際交易所債1", "coupon": 4.95, "maturity": "2052"},
    "US872898AJ06": {"issuer": "TSMC公司債4", "coupon": 4.5, "maturity": "2052"},
    "US084664DB47": {"issuer": "波克夏金融債2", "coupon": 3.85, "maturity": "2052"},
    "US92343VGP31": {"issuer": "威瑞森電信債11", "coupon": 3.875, "maturity": "2052"},
    "US828807DJ39": {"issuer": "賽門房地產債1", "coupon": 3.8, "maturity": "2050"},
    "US191216CQ13": {"issuer": "可口可樂公司債2", "coupon": 4.2, "maturity": "2050"},
    "US92556HAC16": {"issuer": "維康公司債3", "coupon": 4.95, "maturity": "2050"},
    "US31428XCA28": {"issuer": "聯邦快遞公司債1", "coupon": 5.25, "maturity": "2050"},
    "US09062XAG88": {"issuer": "生物基因公司債2", "coupon": 3.15, "maturity": "2050"},
    "US37045VAT70": {"issuer": "通用汽車公司債7", "coupon": 5.95, "maturity": "2049"},
    "US254687FM36": {"issuer": "迪士尼公司債2", "coupon": 2.75, "maturity": "2049"},
    "XS1982116136": {"issuer": "沙烏地阿拉伯石油債4", "coupon": 4.375, "maturity": "2049"},
    "US58933YAW57": {"issuer": "默克藥廠公司債1", "coupon": 4.0, "maturity": "2049"},
    "US854502AJ02": {"issuer": "史丹利百得公司債3", "coupon": 4.85, "maturity": "2048"},
    "US125523AK66": {"issuer": "信諾公司債1", "coupon": 4.9, "maturity": "2048"},
    "US88579YBD22": {"issuer": "3M公司債1", "coupon": 4.0, "maturity": "2048"},
    "US084664CQ25": {"issuer": "波克夏海瑟威債1", "coupon": 4.2, "maturity": "2048"},
    "XS1807174559": {"issuer": "卡達政府國際債1", "coupon": 5.103, "maturity": "2048"},
    "US00206RCU41": {"issuer": "AT&T公司債12", "coupon": 5.65, "maturity": "2047"},
    "US023135BJ40": {"issuer": "亞馬遜公司債1", "coupon": 4.05, "maturity": "2047"},
    "US375558BK80": {"issuer": "吉利德科學債1", "coupon": 4.15, "maturity": "2047"},
    "US037833CH12": {"issuer": "蘋果公司債6", "coupon": 4.25, "maturity": "2047"},
    "US94974BGU89": {"issuer": "富國銀行公司債10", "coupon": 4.75, "maturity": "2046"},
    "US172967KR13": {"issuer": "花旗集團公司債14", "coupon": 4.75, "maturity": "2046"},
    "US00206RCQ39": {"issuer": "AT&T公司債5", "coupon": 4.75, "maturity": "2046"},
    "US002824BH26": {"issuer": "亞培公司債2", "coupon": 4.9, "maturity": "2046"},
    "XS1508675508": {"issuer": "沙烏地阿拉伯政府債5", "coupon": 4.5, "maturity": "2046"},
    "US02209SAV51": {"issuer": "高特利集團債1", "coupon": 3.875, "maturity": "2046"},
    "US92343VCK89": {"issuer": "威瑞森電信債1", "coupon": 4.862, "maturity": "2046"},
    "US594918BT09": {"issuer": "微軟公司債2", "coupon": 3.7, "maturity": "2046"},
    "US125523CF53": {"issuer": "信諾公司債2", "coupon": 4.8, "maturity": "2046"},
    "US20030NBU46": {"issuer": "康卡斯特公司債1", "coupon": 3.4, "maturity": "2046"},
    "US375558BD48": {"issuer": "吉利德科學債2", "coupon": 4.75, "maturity": "2046"},
    "US02079KBN63": {"issuer": "Alphabet公司債5", "coupon": 5.5, "maturity": "2046"},
    "US58013MFA71": {"issuer": "麥當勞公司債2", "coupon": 4.875, "maturity": "2045"},
    "US42824CAY57": {"issuer": "慧與公司債1", "coupon": 6.35, "maturity": "2045"},
    "US09062XAD57": {"issuer": "生物基因公司債1", "coupon": 5.2, "maturity": "2045"},
    "US37045VAJ98": {"issuer": "通用汽車公司債4", "coupon": 5.2, "maturity": "2045"},
    "US61747YDY86": {"issuer": "摩根士丹利債20", "coupon": 4.3, "maturity": "2045"},
    "US30303M8X35": {"issuer": "Meta公司債10", "coupon": 5.5, "maturity": "2045"},
    "US747525AK99": {"issuer": "高通公司債3", "coupon": 4.8, "maturity": "2045"},
    "US94974BGE48": {"issuer": "富國銀行債9", "coupon": 4.65, "maturity": "2044"},
    "US172967HS33": {"issuer": "花旗集團債12", "coupon": 5.3, "maturity": "2044"},
    "XS1049699926": {"issuer": "渣打集團債6", "coupon": 5.7, "maturity": "2044"},
    "US404280AQ21": {"issuer": "匯豐控股債8", "coupon": 5.25, "maturity": "2044"},
    "US25468PDB94": {"issuer": "迪士尼公司債3", "coupon": 4.125, "maturity": "2044"},
    "US717081DK61": {"issuer": "輝瑞藥廠債2", "coupon": 4.4, "maturity": "2044"},
    "US449276AF17": {"issuer": "IBM金融債1", "coupon": 5.25, "maturity": "2044"},
    "US02209SAR40": {"issuer": "高特利集團債2", "coupon": 5.375, "maturity": "2044"},
    "US37045VAF76": {"issuer": "通用汽車公司債3", "coupon": 6.25, "maturity": "2043"},
    "US92553PAP71": {"issuer": "維康公司債2", "coupon": 4.375, "maturity": "2043"},
    "US12572QAF28": {"issuer": "芝加哥期交所債1", "coupon": 5.3, "maturity": "2043"},
    "US037833AL42": {"issuer": "蘋果公司債2", "coupon": 3.85, "maturity": "2043"},
    "US084670BK32": {"issuer": "波克夏公司債1", "coupon": 4.5, "maturity": "2043"},
    "US00206RBH49": {"issuer": "AT&T公司債1", "coupon": 4.3, "maturity": "2042"},
    "US71568QAB32": {"issuer": "印尼國家電力債2", "coupon": 5.25, "maturity": "2042"},
    "US854502AA92": {"issuer": "史丹利百得公司債2", "coupon": 5.2, "maturity": "2040"},
    "US50076QAN60": {"issuer": "卡夫亨氏公司債1", "coupon": 6.5, "maturity": "2040"},
    "XS2885079702": {"issuer": "國泰人壽公司債2", "coupon": 5.3, "maturity": "2039"},
    "US46625HHF01": {"issuer": "摩根大通銀行債3", "coupon": 6.4, "maturity": "2038"},
    "US37045VAP58": {"issuer": "通用汽車公司債2", "coupon": 5.15, "maturity": "2038"},
    "US126650CY46": {"issuer": "CVS公司債1", "coupon": 4.78, "maturity": "2038"},
    "US38141GFD16": {"issuer": "高盛公司債14", "coupon": 6.75, "maturity": "2037"},
    "US00206RDR03": {"issuer": "AT&T公司債3", "coupon": 5.25, "maturity": "2037"},
    "US594918BZ68": {"issuer": "微軟公司債7", "coupon": 4.1, "maturity": "2037"},
    "US404280AG49": {"issuer": "匯豐銀行公司債4", "coupon": 6.5, "maturity": "2036"},
    "US38143YAC75": {"issuer": "高盛證券公司債16", "coupon": 6.45, "maturity": "2036"},
    "US925524AX89": {"issuer": "維康公司債1", "coupon": 6.875, "maturity": "2036"},
    "US37045VAK61": {"issuer": "通用汽車公司債1", "coupon": 6.6, "maturity": "2036"},
    "XS3151416727": {"issuer": "富邦人壽(新加坡)1", "coupon": 5.45, "maturity": "2035"},
    "US06051GLU12": {"issuer": "美國銀行公司債6", "coupon": 5.872, "maturity": "2034"},
    "XS2852920342": {"issuer": "國泰人壽公司債1", "coupon": 5.95, "maturity": "2034"},
    "US717081EC37": {"issuer": "輝瑞藥廠債1", "coupon": 4.0, "maturity": "2036"},
    "US035242AM81": {"issuer": "百威英博債2", "coupon": 4.7, "maturity": "2036"},
    "US91159HJN17": {"issuer": "美國合眾銀債2", "coupon": 5.836, "maturity": "2034"},
    "US55608KBG94": {"issuer": "麥格理集團債10", "coupon": 5.491, "maturity": "2033"},
    "US686330AR22": {"issuer": "歐力士公司債2", "coupon": 5.2, "maturity": "2032"},
    "USG91139AL26": {"issuer": "TSMC全球債6", "coupon": 4.625, "maturity": "2032"},
    "US458140CA64": {"issuer": "英特爾公司債5", "coupon": 4.15, "maturity": "2032"},
}

FINRA_ISIN_TO_TICKER = {
    "US03769MAC01": "APO5813716", "US09062XAG88": "BIIB4981508",
    "US084670BK32": "BRK3963113", "US035242AM81": "BUD4327587",
    "US125523AK66": "CI4866401",  "US125523CF53": "CI5003121",
    "US20030NBU46": "CMCS4382861","US31428XCA28": "FBUO6172956",
    "US375558BD48": "GILD4287890","US37045VAT70": "GM4181484",
    "US404280AG49": "HBC US404280AG49","US449276AF17": "IBM5449458",
    "US45866FAX24": "ICE5414190", "US191216CQ13": "KO4969567",
    "US02209SAR40": "MO4065695",  "US02209SAV51": "MO4403915",
    "US61747YDY86": "MS4204532",  "US64110LBA35": "NFLX5862368",
    "US747525AK99": "QCOM4246685","XS1049699926": "SCBFF4110430",
    "US854502AJ02": "SDBO4820048","US854502AA92": "SWK.GM",
    "US00206RCQ39": "T4237450",   "US00206RCU41": "T4451561",
    "US91159HJN17": "USB5600582", "US92556HAC16": "VIA4987234",
    "US92343VGW81": "VZ4968008",  "US92343VFD10": "VZ5363445",
}

YIELD_TICKERS = {"10年期": "DGS10", "20年期": "DGS20", "30年期": "DGS30"}
YIELD_YAHOO   = {"10年期": "^TNX",  "20年期": "^FVX",   "30年期": "^TYX"}

HOLDING_PERIODS = {
    "1個月": 21, "3個月": 63, "6個月": 126,
    "1年": 252,  "2年": 504,  "3年": 756,
}

# ==========================================
# Google Drive 連線
# ==========================================
@st.cache_resource
def get_gspread_client():
    creds_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly",
              "https://www.googleapis.com/auth/drive.readonly"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)

def get_drive_headers():
    creds_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
    scopes = ["https://www.googleapis.com/auth/drive.readonly"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    creds.refresh(Request())
    return {"Authorization": f"Bearer {creds.token}"}

@st.cache_data(ttl=3600)
def list_sheets_in_folder(folder_id):
    headers = get_drive_headers()
    params = {"q": f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.spreadsheet' and trashed=false",
              "fields": "files(id, name)", "pageSize": 200}
    resp = requests.get("https://www.googleapis.com/drive/v3/files", headers=headers, params=params)
    return {f["name"]: f["id"] for f in resp.json().get("files", [])}

@st.cache_data(ttl=3600)
def read_sheet_as_series(sheet_id: str, label: str) -> pd.Series:
    client = get_gspread_client()
    sh = client.open_by_key(sheet_id)
    ws = sh.get_worksheet(0)
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    if df.empty:
        return pd.Series(dtype=float, name=label)
    date_col, val_col = df.columns[0], df.columns[1]
    df["date"] = pd.to_datetime(df[date_col], errors="coerce")
    if df["date"].isna().mean() > 0.5:
        df["date"] = pd.to_datetime(df[date_col], unit="s", errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date").set_index("date")
    return df[val_col].astype(float).rename(label)

# ==========================================
# 國債殖利率（FRED + Yahoo Finance 備援）
# ==========================================
@st.cache_data(ttl=3600)
def fetch_yield_data(tenor: str) -> pd.Series:
    fred_ticker = YIELD_TICKERS[tenor]

    # 優先：stooq（無 rate limit）
    try:
        stooq_map = {"DGS10": "10y.b.us", "DGS20": "20y.b.us", "DGS30": "30y.b.us"}
        stooq_t = stooq_map[fred_ticker]
        url = f"https://stooq.com/q/d/l/?s={stooq_t}&i=d"
        resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        df = pd.read_csv(StringIO(resp.text), parse_dates=["Date"], index_col="Date")
        s = pd.to_numeric(df["Close"], errors="coerce").dropna()
        if len(s) > 100:
            return s.sort_index().rename("yield")
    except Exception as e:
        st.warning(f"stooq 失敗：{e}")

    # 備援1：FRED
    try:
        url2 = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={fred_ticker}"
        resp2 = requests.get(url2, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if resp2.status_code == 200 and len(resp2.text) > 100:
            df2 = pd.read_csv(StringIO(resp2.text), parse_dates=[0], index_col=0)
            df2.columns = ["yield"]
            s2 = pd.to_numeric(df2["yield"], errors="coerce").dropna()
            if len(s2) > 100:
                return s2
    except:
        pass

    # 備援2：Yahoo Finance
    try:
        import yfinance as yf
        yahoo_map = {"DGS10": "^TNX", "DGS20": "^TNX", "DGS30": "^TYX"}
        yt = yahoo_map.get(fred_ticker, "^TNX")
        df3 = yf.download(yt, start="2000-01-01", progress=False, auto_adjust=True)
        if not df3.empty:
            s3 = df3["Close"].squeeze().dropna()
            s3.index = pd.to_datetime(s3.index)
            return s3.rename("yield")
    except:
        pass

    st.error("所有殖利率資料來源均失敗，請稍後再試。")
    return pd.Series(dtype=float)

# ==========================================
# 並行載入所有標的資料
# ==========================================
def load_all_series(fund_tickers, bond_sheets_map, fund_sheets_map):
    """並行載入基金+債券資料"""
    tasks = {}

    # 基金
    for ticker in fund_tickers:
        name = FUND_DB[ticker]
        sid = fund_sheets_map.get(ticker)
        if sid:
            tasks[name] = ("sheet", sid, name)

    # 債券
    for isin, info in LOCAL_DB.items():
        label = f"{info['issuer']}"
        sheet_id = None
        finra_t = FINRA_ISIN_TO_TICKER.get(isin)
        if finra_t:
            for sname, sid in bond_sheets_map.items():
                if finra_t in sname:
                    sheet_id = sid
                    break
        if not sheet_id:
            for sname, sid in bond_sheets_map.items():
                if isin in sname:
                    sheet_id = sid
                    break
        if sheet_id:
            tasks[label] = ("sheet", sheet_id, label)

    results = {}
    def _load(name, task):
        try:
            _, sid, lbl = task
            s = read_sheet_as_series(sid, lbl)
            if len(s) > 10:
                return name, s
        except:
            pass
        return name, None

    with ThreadPoolExecutor(max_workers=20) as ex:
        futures = {ex.submit(_load, k, v): k for k, v in tasks.items()}
        for f in as_completed(futures):
            name, s = f.result()
            if s is not None:
                results[name] = s

    return results

# ==========================================
# 回測核心
# ==========================================
def find_breakout_events(yield_s: pd.Series, threshold: float):
    above = yield_s > threshold
    crossings = (~above.shift(1, fill_value=False)) & above
    return list(crossings[crossings].index)

def calc_perf(series: pd.Series, event_date, days: int):
    future = series[series.index > event_date]
    if len(future) < days:
        return None
    base = series[series.index <= event_date]
    if base.empty:
        return None
    return (future.iloc[days - 1] - base.iloc[-1]) / base.iloc[-1]

# ==========================================
# UI
# ==========================================
st.title("📈 國債殖利率突破 → 基金＋債券績效回測")
st.caption("美國國債殖利率首次向上突破門檻後，各持有期間的平均績效")

st.sidebar.header("⚙️ 設定")
yield_tenor = st.sidebar.radio("國債期限", list(YIELD_TICKERS.keys()), horizontal=True)
thresholds = st.sidebar.multiselect(
    "突破門檻（%）",
    options=[3.0, 3.5, 4.0, 4.5, 5.0, 5.5],
    default=[4.0, 4.5, 5.0]
)
show_detail = st.sidebar.checkbox("顯示每次突破詳細明細", value=False)

if not thresholds:
    st.warning("請至少選擇一個突破門檻")
    st.stop()

# 載入殖利率
with st.spinner(f"載入 {yield_tenor} 國債殖利率..."):
    yield_data = fetch_yield_data(yield_tenor)

if yield_data.empty:
    st.error("無法取得殖利率資料，請稍後再試")
    st.stop()

st.success(f"✅ 殖利率資料：{len(yield_data)} 筆（{yield_data.index[0].strftime('%Y-%m-%d')} ~ {yield_data.index[-1].strftime('%Y-%m-%d')}）")

# 載入基金+債券（並行）
with st.spinner("並行載入基金＋債券資料中（約 20~30 秒）..."):
    fund_sheets = list_sheets_in_folder(FUND_FOLDER_ID)
    bond_sheets = list_sheets_in_folder(BOND_FOLDER_ID)
    all_series = load_all_series(
        list(FUND_DB.keys()), bond_sheets, fund_sheets
    )

n_fund  = sum(1 for k in all_series if k in FUND_DB.values())
n_bond  = len(all_series) - n_fund
st.success(f"✅ 已載入：基金 {len(FUND_DB)} 檔 + 債券 {len(LOCAL_DB)} 筆，成功讀取 {len(all_series)} 筆資料")

# ==========================================
# 殖利率走勢圖
# ==========================================
st.subheader(f"📊 美國 {yield_tenor} 國債殖利率走勢")
fig_yield = go.Figure()
fig_yield.add_trace(go.Scatter(
    x=yield_data.index, y=yield_data.values,
    mode="lines", name=f"{yield_tenor}殖利率",
    line=dict(color="#1565c0", width=1.5)
))
thr_colors = ["#e53935", "#f57c00", "#7b1fa2", "#2e7d32", "#00838f", "#ad1457"]
for i, thr in enumerate(sorted(thresholds)):
    events = find_breakout_events(yield_data, thr)
    fig_yield.add_hline(y=thr, line_dash="dash",
        line_color=thr_colors[i % len(thr_colors)],
        annotation_text=f"{thr}%（{len(events)}次突破）",
        annotation_position="right")
    if events:
        fig_yield.add_trace(go.Scatter(
            x=events, y=[yield_data.asof(e) for e in events],
            mode="markers",
            marker=dict(size=10, color=thr_colors[i % len(thr_colors)], symbol="triangle-up"),
            name=f"突破{thr}%", showlegend=True
        ))
fig_yield.update_layout(height=400, hovermode="x unified",
    yaxis_title="殖利率（%）", xaxis_title="日期",
    legend=dict(orientation="h", yanchor="bottom", y=1.02))
st.plotly_chart(fig_yield, use_container_width=True)

# ==========================================
# 回測結果
# ==========================================
periods = list(HOLDING_PERIODS.keys())

for thr in sorted(thresholds):
    events = find_breakout_events(yield_data, thr)
    if not events:
        st.info(f"殖利率從未突破 {thr}%")
        continue

    st.subheader(f"🎯 突破 {thr}% 門檻（共 {len(events)} 次）")
    ev_strs = "　".join([e.strftime("%Y-%m-%d") for e in events[:8]])
    if len(events) > 8:
        ev_strs += f"…等{len(events)}次"
    st.caption(f"突破日期：{ev_strs}")

    # 計算平均績效
    rows = []
    for name, series in sorted(all_series.items()):
        row = {"標的": name}
        for pname, days in HOLDING_PERIODS.items():
            perfs = [calc_perf(series, ev, days) for ev in events]
            perfs = [p for p in perfs if p is not None]
            row[pname] = np.mean(perfs) if perfs else np.nan
        rows.append(row)

    result_df = pd.DataFrame(rows).set_index("標的")

    # 顏色函式
    def color_cell(val):
        if pd.isna(val): return "color:#999"
        if val >=  0.05: return "background:#c8e6c9;color:#1b5e20;font-weight:bold"
        if val >=  0.02: return "background:#dcedc8;color:#33691e"
        if val >=  0.00: return "background:#f1f8e9;color:#558b2f"
        if val >= -0.02: return "background:#fff9c4;color:#f57f17"
        if val >= -0.05: return "background:#ffe0b2;color:#e65100"
        return "background:#ffcdd2;color:#b71c1c;font-weight:bold"

    st.dataframe(
        result_df.style
            .map(color_cell)
            .format(lambda x: f"{x:.2%}" if not pd.isna(x) else "-"),
        use_container_width=True, height=600
    )

    # 折線圖（只顯示基金，債券太多線會亂）
    st.markdown("**基金績效趨勢（各持有期間）**")
    fig_f = go.Figure()
    fund_names = [FUND_DB[t] for t in FUND_DB if FUND_DB[t] in result_df.index]
    palette = ["#1565c0","#c62828","#2e7d32","#6a1b9a","#e65100",
               "#00838f","#ad1457","#f57f17","#4527a0","#00695c",
               "#558b2f","#0277bd","#4e342e","#37474f","#1a237e",
               "#880e4f","#1b5e20","#bf360c"]
    for i, nm in enumerate(fund_names):
        if nm not in result_df.index: continue
        vals = [result_df.loc[nm, p] * 100 if not pd.isna(result_df.loc[nm, p]) else None for p in periods]
        fig_f.add_trace(go.Scatter(
            x=periods, y=vals, mode="lines+markers",
            name=nm[:16], connectgaps=False,
            line=dict(color=palette[i % len(palette)], width=2),
            marker=dict(size=7)
        ))
    fig_f.add_hline(y=0, line_dash="dash", line_color="#888")
    fig_f.update_layout(height=380, yaxis_title="平均累積報酬（%）",
        hovermode="x unified", plot_bgcolor="#f8f9ff",
        legend=dict(font=dict(size=10)))
    st.plotly_chart(fig_f, use_container_width=True)

    # 詳細明細
    if show_detail:
        with st.expander(f"🔍 每次突破 {thr}% 詳細績效"):
            for ev in events:
                st.markdown(f"**{ev.strftime('%Y-%m-%d')}（殖利率：{yield_data.asof(ev):.2f}%）**")
                ev_rows = []
                for name, series in sorted(all_series.items()):
                    r = {"標的": name}
                    for pname, days in HOLDING_PERIODS.items():
                        p = calc_perf(series, ev, days)
                        r[pname] = f"{p:.2%}" if p is not None else "-"
                    ev_rows.append(r)
                st.dataframe(pd.DataFrame(ev_rows).set_index("標的"), use_container_width=True)

st.markdown("---")
st.caption("※ 績效為各次突破後持有期間平均累積報酬（未年化）。顏色：深綠≥5%、淺綠2~5%、極淺綠0~2%、黃-2~0%、橙-5~-2%、紅<-5%。資料來源：FRED/Yahoo、Google Drive。僅供內部參考。")
