import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

# ==================== 1. 数据获取 ====================
ticker = "QQQ"
df = yf.download(ticker, start="2010-01-01", end="2026-03-27", progress=False)
df = df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
df.columns = ['open', 'high', 'low', 'close', 'volume']
df = df.reset_index().rename(columns={'Date': 'date'})

# ==================== 2. 计算技术指标 ====================
df['MA200'] = df['close'].rolling(window=200).mean()
df['MA50'] = df['close'].rolling(window=50).mean()
df['MA20'] = df['close'].rolling(window=20).mean()
df['BB_std'] = df['close'].rolling(window=20).std()
df['BB_upper'] = df['MA20'] + 2 * df['BB_std']
df['BB_lower'] = df['MA20'] - 2 * df['BB_std']

# RSI(14)
delta = df['close'].diff()
gain = delta.where(delta > 0, 0).rolling(window=14).mean()
loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
rs = gain / loss
df['RSI'] = 100 - (100 / (1 + rs))

df = df.dropna().reset_index(drop=True)

# ==================== 3. 回测逻辑（已按我的优化逻辑修改） ====================
initial_capital = 100000.0
cash = initial_capital
shares = 0.0
avg_entry = 0.0
last_buy_price = 0.0
add_stage = 0          # 0:待首次, 1:已首次, 2:已二次, 3:已满仓
entry_date = None
trades = []
equity_curve = []
dates = []

for i in range(len(df)):
    row = df.iloc[i]
    price = row['close']
    ma200 = row['MA200']
    ma50 = row['MA50']
    rsi = row['RSI']
    bb_lower = row['BB_lower']
    ma20 = row['MA20']
    current_equity = cash + shares * price
    equity_curve.append(current_equity)
    dates.append(row['date'])

    # 1. 止损优先（严格不变）
    if shares > 0:
        stop_triggered = False
        if avg_entry > 0 and price < avg_entry * 0.92:
            stop_triggered = True
        elif price < ma200:
            stop_triggered = True
        if stop_triggered:
            cash += shares * price
            pnl = (price - avg_entry) / avg_entry if avg_entry > 0 else 0
            trades.append({'entry_date': entry_date, 'exit_date': row['date'], 'pnl_pct': pnl, 'win': pnl > 0})
            shares = 0.0
            avg_entry = 0.0
            last_buy_price = 0.0
            add_stage = 0
            entry_date = None
            continue

    # 2. 优化后的止盈条件（关键修改：RSI>75 或 偏离15%）
    if shares > 0:
        deviate = (price / ma50 - 1) if ma50 > 0 else 0
        if rsi > 75 or deviate > 0.15:          # ←←← 原70/0.10 改为75/0.15
            cash += shares * price
            pnl = (price / avg_entry - 1) if avg_entry > 0 else 0
            trades.append({'entry_date': entry_date, 'exit_date': row['date'], 'pnl_pct': pnl, 'win': pnl > 0})
            shares = 0.0
            avg_entry = 0.0
            last_buy_price = 0.0
            add_stage = 0
            entry_date = None
            continue

    # 3. 入场 & 加仓逻辑（二次加仓回调优化为4%）
    trend_ok = price > ma200
    oversold = (rsi <= 40) or (price <= bb_lower)

    # 首次建仓 30%
    if trend_ok and oversold and shares == 0 and add_stage == 0:
        buy_amount = min(0.3 * current_equity, cash)
        if buy_amount > 0:
            buy_shares = buy_amount / price
            shares += buy_shares
            cash -= buy_amount
            avg_entry = price
            last_buy_price = price
            add_stage = 1
            entry_date = row['date']
        continue

    # 二次加仓：回调4%（原5% → 优化为更容易触发）
    if shares > 0 and add_stage == 1 and price < last_buy_price * 0.96 and price > ma200:
        buy_amount = min(0.3 * current_equity, cash)
        if buy_amount > 0:
            buy_shares = buy_amount / price
            prev_shares = shares
            prev_cost = avg_entry * prev_shares
            new_cost = price * buy_shares
            shares += buy_shares
            cash -= buy_amount
            avg_entry = (prev_cost + new_cost) / shares
            last_buy_price = price
            add_stage = 2
        continue

    # 三次加仓：反弹确认（> MA20）
    if shares > 0 and add_stage == 2 and price > ma20:
        buy_amount = min(0.4 * current_equity, cash)
        if buy_amount > 0:
            buy_shares = buy_amount / price
            prev_shares = shares
            prev_cost = avg_entry * prev_shares
            new_cost = price * buy_shares
            shares += buy_shares
            cash -= buy_amount
            avg_entry = (prev_cost + new_cost) / shares
            last_buy_price = price
            add_stage = 3
        continue

# ==================== 4. 计算绩效指标 ====================
final_equity = cash + shares * df.iloc[-1]['close']
equity_series = pd.Series(equity_curve, index=dates)

total_years = (dates[-1] - dates[0]).days / 365.25
annualized_return = (final_equity / initial_capital) ** (1 / total_years) - 1

daily_returns = equity_series.pct_change().dropna()
sharpe_ratio = daily_returns.mean() / daily_returns.std() * np.sqrt(252) if daily_returns.std() != 0 else 0

running_max = equity_series.cummax()
max_dd = ((equity_series - running_max) / running_max).min()

calmar_ratio = annualized_return / abs(max_dd) if max_dd != 0 else np.inf

num_trades = len(trades)
win_rate = sum(1 for t in trades if t['win']) / num_trades * 100 if num_trades > 0 else 0
avg_trades_year = num_trades / total_years

# Buy & Hold 基准
bh_final = initial_capital * (df.iloc[-1]['close'] / df.iloc[0]['close'])
bh_annualized = (bh_final / initial_capital) ** (1 / total_years) - 1
bh_dd = ((df['close'].cummax() - df['close']) / df['close'].cummax()).min() * -1
bh_daily = df['close'].pct_change().dropna()
bh_sharpe = bh_daily.mean() / bh_daily.std() * np.sqrt(252) if len(bh_daily) > 0 and bh_daily.std() != 0 else 0
bh_calmar = bh_annualized / abs(bh_dd) if bh_dd != 0 else np.inf

# 输出表格
print("\n=== 优化后策略回测结果（2012-2026 ≈14.2年） ===")
print(f"年化收益率 (Strategy): {annualized_return*100:.2f}%")
print(f"夏普比率 (Strategy): {sharpe_ratio:.2f}")
print(f"最大回撤 (Strategy): {max_dd*100:.2f}%")
print(f"胜率 (Strategy): {win_rate:.2f}%")
print(f"年均交易次数 (Strategy): {avg_trades_year:.2f}")
print(f"Calmar比率 (Strategy): {calmar_ratio:.2f}")
print(f"Buy & Hold 年化收益率: {bh_annualized*100:.2f}%")
print(f"Buy & Hold 夏普比率: {bh_sharpe:.2f}")
print(f"Buy & Hold 最大回撤: {bh_dd*100:.2f}%")
print(f"Buy & Hold Calmar比率: {bh_calmar:.2f}")
print(f"总交易次数: {num_trades}")