"""
國債殖利率突破 → 基金績效回測系統
當 10Y/20Y/30Y 國債殖利率首次向上突破特定門檻時，
分析持有的債券型基金在那之後 1M/3M/6M/1Y/2Y/3Y 的績效。
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
from datetime import datetime, timedelta

st.set_page_config(
    page_title="國債殖利率突破回測",
    layout="wide",
    page_icon="📈"
)

# ==========================================
# 常數
# ==========================================
FUND_FOLDER_ID = "1i1-zUzLNnuwo2NVWijubvBICLbladZQO"

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

# 國債殖利率 FRED tickers
YIELD_TICKERS = {
    "10年期": "DGS10",
    "20年期": "DGS20",
    "30年期": "DGS30",
}

HOLDING_PERIODS = {
    "1個月": 21,
    "3個月": 63,
    "6個月": 126,
    "1年": 252,
    "2年": 504,
    "3年": 756,
}

# ==========================================
# Google Drive 連線
# ==========================================
@st.cache_resource
def get_gspread_client():
    creds_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly"
    ]
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
    params = {
        "q": f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.spreadsheet' and trashed=false",
        "fields": "files(id, name)",
        "pageSize": 200,
    }
    resp = requests.get("https://www.googleapis.com/drive/v3/files", headers=headers, params=params)
    return {f["name"]: f["id"] for f in resp.json().get("files", [])}

@st.cache_data(ttl=3600)
def read_sheet_as_series(sheet_id, label):
    client = get_gspread_client()
    sh = client.open_by_key(sheet_id)
    ws = sh.get_worksheet(0)
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    if df.empty:
        return pd.Series(dtype=float, name=label)
    date_col = df.columns[0]
    val_col = df.columns[1]
    try:
        df["date"] = pd.to_datetime(df[date_col], errors="coerce")
        if df["date"].isna().mean() > 0.5:
            df["date"] = pd.to_datetime(df[date_col], unit="s", errors="coerce")
    except:
        df["date"] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=["date"])
    df = df.sort_values("date").set_index("date")
    return df[val_col].astype(float).rename(label)

# ==========================================
# 國債殖利率資料（FRED）
# ==========================================
@st.cache_data(ttl=3600)
def fetch_yield_data(fred_ticker: str) -> pd.Series:
    """從 FRED 抓取國債殖利率"""
    try:
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={fred_ticker}"
        resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        from io import StringIO
        df = pd.read_csv(StringIO(resp.text), parse_dates=[0], index_col=0)
        df.columns = ["yield"]
        df = df.replace(".", np.nan).dropna()
        df["yield"] = pd.to_numeric(df["yield"], errors="coerce").dropna()
        return df["yield"]
    except Exception as e:
        st.error(f"無法從 FRED 取得 {fred_ticker} 資料：{e}")
        return pd.Series(dtype=float)

# ==========================================
# 核心計算：找首次向上突破事件
# ==========================================
def find_breakout_events(yield_series: pd.Series, threshold: float) -> list:
    """找殖利率首次向上突破門檻的日期清單"""
    events = []
    above = yield_series > threshold
    # 找從下方穿越上方的點（False → True）
    crossings = (~above.shift(1, fill_value=False)) & above
    for date in crossings[crossings].index:
        events.append(date)
    return events

def calc_fund_perf_after_event(
    fund_series: pd.Series,
    event_date: pd.Timestamp,
    holding_days: int
) -> float | None:
    """計算基金在事件後 N 天的累積報酬"""
    future = fund_series[fund_series.index > event_date]
    if len(future) < holding_days:
        return None
    start_price = fund_series[fund_series.index <= event_date].iloc[-1]
    end_price = future.iloc[holding_days - 1]
    return (end_price - start_price) / start_price

# ==========================================
# 主程式
# ==========================================
st.title("📈 國債殖利率突破 → 基金績效回測")
st.caption("當美國國債殖利率首次向上突破特定門檻時，分析各基金的後續表現")

# 側邊欄設定
st.sidebar.header("1. 殖利率設定")
yield_tenor = st.sidebar.radio("國債期限", list(YIELD_TICKERS.keys()), horizontal=True)
thresholds = st.sidebar.multiselect(
    "突破門檻（%）",
    options=[3.5, 4.0, 4.5, 5.0, 5.5],
    default=[4.0, 4.5, 5.0]
)

st.sidebar.header("2. 選擇基金")
selected_funds = st.sidebar.multiselect(
    "選擇要分析的基金",
    options=list(FUND_DB.keys()),
    default=list(FUND_DB.keys())[:6],
    format_func=lambda x: FUND_DB[x]
)

if not thresholds:
    st.warning("請至少選擇一個突破門檻")
    st.stop()
if not selected_funds:
    st.warning("請至少選擇一支基金")
    st.stop()

# 載入殖利率資料
fred_ticker = YIELD_TICKERS[yield_tenor]
with st.spinner(f"載入 {yield_tenor} 國債殖利率資料..."):
    yield_data = fetch_yield_data(fred_ticker)

if yield_data.empty:
    st.error("無法取得殖利率資料，請稍後再試")
    st.stop()

# 載入基金淨值
with st.spinner("載入基金淨值資料..."):
    fund_sheets = list_sheets_in_folder(FUND_FOLDER_ID)
    fund_series_dict = {}
    failed = []
    for ticker in selected_funds:
        name = FUND_DB[ticker]
        sheet_id = fund_sheets.get(ticker)
        if not sheet_id:
            failed.append(name)
            continue
        try:
            s = read_sheet_as_series(sheet_id, name)
            if len(s) > 10:
                fund_series_dict[name] = s
        except:
            failed.append(name)

if failed:
    st.warning(f"以下基金資料載入失敗：{', '.join(failed)}")
if not fund_series_dict:
    st.error("沒有可用的基金資料")
    st.stop()

# ==========================================
# 顯示殖利率走勢圖
# ==========================================
st.subheader(f"📊 美國 {yield_tenor} 國債殖利率走勢")

fig_yield = go.Figure()
fig_yield.add_trace(go.Scatter(
    x=yield_data.index, y=yield_data.values,
    mode="lines", name=f"{yield_tenor}殖利率",
    line=dict(color="#1565c0", width=1.5)
))

colors_thresh = ["#e53935", "#f57c00", "#7b1fa2", "#2e7d32", "#00838f"]
for i, thr in enumerate(sorted(thresholds)):
    fig_yield.add_hline(
        y=thr, line_dash="dash",
        line_color=colors_thresh[i % len(colors_thresh)],
        annotation_text=f"{thr}%",
        annotation_position="right"
    )
    # 標示突破點
    events = find_breakout_events(yield_data, thr)
    if events:
        fig_yield.add_trace(go.Scatter(
            x=events,
            y=[yield_data.asof(e) for e in events],
            mode="markers",
            marker=dict(size=10, color=colors_thresh[i % len(colors_thresh)], symbol="triangle-up"),
            name=f"突破 {thr}%（{len(events)} 次）"
        ))

fig_yield.update_layout(
    height=400, hovermode="x unified",
    yaxis_title="殖利率（%）",
    xaxis_title="日期",
    legend=dict(orientation="h", yanchor="bottom", y=1.02)
)
st.plotly_chart(fig_yield, use_container_width=True)

# ==========================================
# 回測結果
# ==========================================
st.subheader("📋 各門檻突破後的基金績效")

for thr in sorted(thresholds):
    events = find_breakout_events(yield_data, thr)
    if not events:
        st.info(f"殖利率從未突破 {thr}%，跳過")
        continue

    st.markdown(f"### 🎯 突破 **{thr}%** 門檻（共 {len(events)} 次突破）")

    # 顯示突破日期
    event_strs = " | ".join([e.strftime("%Y-%m-%d") for e in events[:10]])
    if len(events) > 10:
        event_strs += f" ...等 {len(events)} 次"
    st.caption(f"突破日期：{event_strs}")

    # 計算各基金在各持有期間的績效
    all_results = []
    for fund_name, fund_s in fund_series_dict.items():
        row = {"基金": fund_name}
        for period_name, days in HOLDING_PERIODS.items():
            perfs = []
            for ev in events:
                p = calc_fund_perf_after_event(fund_s, ev, days)
                if p is not None:
                    perfs.append(p)
            if perfs:
                row[period_name] = np.mean(perfs)
            else:
                row[period_name] = None
        all_results.append(row)

    if not all_results:
        continue

    result_df = pd.DataFrame(all_results).set_index("基金")

    # 顯示表格（帶顏色）
    def color_perf(val):
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return "color: #999"
        if val >= 0.05:
            return "background-color: #c8e6c9; color: #1b5e20; font-weight: bold"
        elif val >= 0.02:
            return "background-color: #dcedc8; color: #33691e"
        elif val >= 0:
            return "background-color: #f1f8e9; color: #558b2f"
        elif val >= -0.02:
            return "background-color: #fff9c4; color: #f57f17"
        elif val >= -0.05:
            return "background-color: #ffe0b2; color: #e65100"
        else:
            return "background-color: #ffcdd2; color: #b71c1c; font-weight: bold"

    st.dataframe(
        result_df.style
            .applymap(color_perf)
            .format(lambda x: f"{x:.2%}" if x is not None and not np.isnan(x) else "-"),
        use_container_width=True
    )

    # 折線圖：各基金在不同持有期間的平均績效
    fig_perf = go.Figure()
    fund_colors = ["#1565c0", "#c62828", "#2e7d32", "#6a1b9a",
                   "#e65100", "#00838f", "#ad1457", "#f57f17",
                   "#4527a0", "#00695c", "#558b2f", "#1565c0"]
    periods = list(HOLDING_PERIODS.keys())
    for i, fund_name in enumerate(result_df.index):
        vals = [result_df.loc[fund_name, p] for p in periods]
        vals_pct = [v * 100 if v is not None and not np.isnan(v) else None for v in vals]
        fig_perf.add_trace(go.Scatter(
            x=periods, y=vals_pct,
            mode="lines+markers",
            name=fund_name[:15],
            line=dict(color=fund_colors[i % len(fund_colors)], width=2),
            marker=dict(size=8),
            connectgaps=False
        ))
    fig_perf.add_hline(y=0, line_dash="dash", line_color="#888")
    fig_perf.update_layout(
        height=380,
        yaxis_title="平均累積報酬（%）",
        hovermode="x unified",
        legend=dict(font=dict(size=11)),
        title=f"突破 {thr}% 後各持有期間平均報酬",
        plot_bgcolor="#f8f9ff"
    )
    st.plotly_chart(fig_perf, use_container_width=True)

    # 詳細事件明細（可展開）
    with st.expander(f"🔍 查看每次突破 {thr}% 的詳細績效"):
        for ev in events:
            st.markdown(f"**突破日：{ev.strftime('%Y-%m-%d')}**（殖利率：{yield_data.asof(ev):.2f}%）")
            ev_rows = []
            for fund_name, fund_s in fund_series_dict.items():
                row = {"基金": fund_name}
                for period_name, days in HOLDING_PERIODS.items():
                    p = calc_fund_perf_after_event(fund_s, ev, days)
                    row[period_name] = f"{p:.2%}" if p is not None else "-"
                ev_rows.append(row)
            ev_df = pd.DataFrame(ev_rows).set_index("基金")
            st.dataframe(ev_df, use_container_width=True)

st.markdown("---")
st.caption("※ 績效為各次突破後持有期間的平均累積報酬（未年化）。資料來源：FRED（殖利率）、Google Drive（基金淨值）。僅供內部參考，不代表未來績效。")
