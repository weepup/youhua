import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(page_title="QQQ 信号灯", layout="centered")
st.title("🚦 QQQ 中长线择时策略信号灯（最终升级版）")
st.markdown("**趋势过滤 + 超卖建仓 + VIX>25过滤 + 分步止盈（30%-30%-40%）** ")

@st.cache_data(ttl=1800, show_spinner=False)
def get_strategy_signal():
    try:
        # 同时获取 QQQ 和 ^VIX（VIX过滤器需要）
        ticker_qqq = yf.Ticker("QQQ")
        ticker_vix = yf.Ticker("^VIX")
        df_qqq = ticker_qqq.history(period="max", auto_adjust=False, actions=False)['Close']
        df_vix = ticker_vix.history(period="max", auto_adjust=False, actions=False)['Close']

        # 对齐日期
        common_index = df_qqq.index.intersection(df_vix.index)
        df = pd.DataFrame({
            'close': df_qqq.loc[common_index],
            'vix': df_vix.loc[common_index]
        }).reset_index().rename(columns={'Date': 'date'})

        # 计算指标
        df['MA200'] = df['close'].rolling(200).mean()
        df['MA50'] = df['close'].rolling(50).mean()
        df['MA20'] = df['close'].rolling(20).mean()
        df['BB_lower'] = df['MA20'] - 2 * df['close'].rolling(20).std()
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        df = df.dropna().reset_index(drop=True)

        # 策略回测逻辑（含VIX过滤 + 分步止盈）
        cash = 100000.0
        shares = 0.0
        avg_entry = 0.0
        last_buy_price = 0.0
        add_stage = 0
        sell_stage = 0          # 0:未止盈, 1:已卖30%, 2:已卖60%, 3:已清仓
        today_action = "等待"
        today_signal = "gray"
        position_pct = 0
        unrealized = 0.0

        for i in range(len(df)):
            row = df.iloc[i]
            price = row['close']
            ma200 = row['MA200']
            ma50 = row['MA50']
            rsi = row['RSI']
            bb_lower = row['BB_lower']
            ma20 = row['MA20']
            vix = row['vix']
            current_equity = cash + shares * price

            # 1. 止损（全仓）
            if shares > 0:
                if (avg_entry > 0 and price < avg_entry * 0.92) or price < ma200:
                    cash += shares * price
                    shares = 0.0
                    avg_entry = 0.0
                    last_buy_price = 0.0
                    add_stage = 0
                    sell_stage = 0
                    if i == len(df) - 1:
                        today_action = "🔴 全仓止损"
                        today_signal = "red"
                    continue

            # 2. 分步止盈（30%-30%-40%）
            if shares > 0:
                deviate = (price / ma50 - 1) if ma50 > 0 else 0
                if rsi > 75 or deviate > 0.15:   # 止盈触发阈值
                    if sell_stage == 0:          # 第1步：卖30%
                        sell_shares = shares * 0.3
                        cash += sell_shares * price
                        shares -= sell_shares
                        sell_stage = 1
                        if i == len(df) - 1:
                            today_action = "🔴 分步止盈：卖出 30%"
                            today_signal = "red"
                    elif sell_stage == 1:        # 第2步：再卖30%
                        sell_shares = shares * 0.3
                        cash += sell_shares * price
                        shares -= sell_shares
                        sell_stage = 2
                        if i == len(df) - 1:
                            today_action = "🔴 分步止盈：卖出 30%"
                            today_signal = "red"
                    elif sell_stage == 2:        # 第3步：卖剩余40%
                        cash += shares * price
                        shares = 0.0
                        sell_stage = 3
                        if i == len(df) - 1:
                            today_action = "🔴 分步止盈完成：卖出剩余 40%"
                            today_signal = "red"
                    continue

            # 3. 入场 & 加仓（新增 VIX > 25 过滤）
            trend_ok = price > ma200
            oversold = (rsi <= 40) or (price <= bb_lower)
            vix_ok = vix > 25

            # 首次建仓 30%
            if trend_ok and oversold and vix_ok and shares == 0 and add_stage == 0:
                buy_amount = min(0.3 * current_equity, cash)
                if buy_amount > 0:
                    shares += buy_amount / price
                    cash -= buy_amount
                    avg_entry = price
                    last_buy_price = price
                    add_stage = 1
                    sell_stage = 0
                    if i == len(df) - 1:
                        today_action = "🟢 首次买入 30%（VIX>25）"
                        today_signal = "green"

            # 二次加仓（回调4% + VIX过滤）
            if shares > 0 and add_stage == 1 and price < last_buy_price * 0.96 and price > ma200 and vix_ok:
                buy_amount = min(0.3 * current_equity, cash)
                if buy_amount > 0:
                    buy_shares = buy_amount / price
                    shares += buy_shares
                    cash -= buy_amount
                    avg_entry = (avg_entry * (shares - buy_shares) + price * buy_shares) / shares
                    last_buy_price = price
                    add_stage = 2
                    if i == len(df) - 1:
                        today_action = "🟢 加仓 30%（二次）"
                        today_signal = "green"

            # 三次加仓（反弹 > MA20 + VIX过滤）
            if shares > 0 and add_stage == 2 and price > ma20 and vix_ok:
                buy_amount = min(0.4 * current_equity, cash)
                if buy_amount > 0:
                    buy_shares = buy_amount / price
                    shares += buy_shares
                    cash -= buy_amount
                    avg_entry = (avg_entry * (shares - buy_shares) + price * buy_shares) / shares
                    last_buy_price = price
                    add_stage = 3
                    if i == len(df) - 1:
                        today_action = "🟢 加仓 40%（三次）"
                        today_signal = "green"

        # 当前状态
        last_price = df.iloc[-1]['close']
        last_rsi = df.iloc[-1]['RSI']
        last_ma200 = df.iloc[-1]['MA200']
        last_vix = df.iloc[-1]['vix']
        trend_ok = last_price > last_ma200
        position_pct = round((shares * last_price) / (cash + shares * last_price) * 100, 1) if shares > 0 else 0
        unrealized = ((last_price - avg_entry) / avg_entry * 100) if shares > 0 and avg_entry > 0 else 0

        # 如果当天无新动作但有仓位 → 持仓观望
        if today_signal == "gray" and position_pct > 0:
            today_action = "🟡 持仓观望（VIX=" + f"{last_vix:.1f}" + "）"
            today_signal = "yellow"

        return {
            "today_action": today_action,
            "today_signal": today_signal,
            "last_price": last_price,
            "last_rsi": last_rsi,
            "last_vix": last_vix,
            "trend_ok": trend_ok,
            "position_pct": position_pct,
            "unrealized": unrealized,
            "date": df.iloc[-1]['date'].strftime("%Y-%m-%d")
        }

    except Exception as e:
        return {"error": str(e)}

# ==================== 主界面 ====================
if st.button("🔄 更新最新数据（每日必点）", type="primary", use_container_width=True):
    st.rerun()

signal = get_strategy_signal()

if "error" in signal:
    st.error(f"❌ {signal['error']}")
    st.stop()

# 大信号灯
color_map = {"green": "🟢", "yellow": "🟡", "red": "🔴", "gray": "⚪"}
st.markdown(f"""
<div style="text-align:center; margin:30px 0;">
    <div style="font-size:120px; line-height:1;">{color_map[signal['today_signal']]}</div>
</div>
""", unsafe_allow_html=True)

st.markdown(f"<h2 style='text-align:center; color:#22c55e;'>{signal['today_action']}</h2>", unsafe_allow_html=True)

col1, col2, col3, col4 = st.columns(4)
col1.metric("最新收盘价", f"${signal['last_price']:.2f}")
col2.metric("RSI(14)", f"{signal['last_rsi']:.1f}")
col3.metric("VIX", f"{signal['last_vix']:.1f}")
col4.metric("趋势状态", "✅ MA200 之上" if signal['trend_ok'] else "❌ 已破位")

st.markdown("---")
st.write(f"**当前持仓**：{signal['position_pct']}%　|　**未实现盈亏**：{signal['unrealized']:.2f}%")
st.caption(f"数据日期：{signal['date']}（VIX过滤 + 分步止盈已启用）")

# 最近 K 线图
st.subheader("最近 120 天 K 线")
hist = yf.Ticker("QQQ").history(period="6mo")
fig = go.Figure(data=[go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'])])
fig.update_layout(height=400, template="plotly_dark")
st.plotly_chart(fig, use_container_width=True)

st.success("✅ 信号灯已就绪！每天打开点一次按钮即可获得今日交易建议（含VIX过滤与分步止盈提示）。")
st.caption("如需进一步增加邮件/钉钉推送、参数滑块优化、导出交易记录等功能，请告诉我")
