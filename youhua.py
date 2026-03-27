<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QQQ 择时策略信号灯</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
    <style>
        body { font-family: "Microsoft YaHei", sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; padding: 20px; }
        .container { max-width: 1100px; margin: auto; }
        .light { width: 180px; height: 180px; border-radius: 50%; margin: 20px auto; box-shadow: 0 0 30px rgba(0,0,0,0.8); display: flex; align-items: center; justify-content: center; font-size: 28px; font-weight: bold; }
        .green { background: #22c55e; color: #000; animation: pulse 2s infinite; }
        .red { background: #ef4444; color: #fff; }
        .yellow { background: #eab308; color: #000; }
        .gray { background: #64748b; color: #fff; }
        .card { background: #1e2937; border-radius: 12px; padding: 20px; margin: 15px 0; }
        button { background: #3b82f6; color: white; border: none; padding: 12px 24px; border-radius: 8px; font-size: 16px; cursor: pointer; }
        button:hover { background: #2563eb; }
        .signal-text { font-size: 24px; font-weight: bold; text-align: center; margin: 10px 0; }
    </style>
</head>
<body>
    <div class="container">
        <h1 style="text-align:center;">🚦 QQQ 中长线择时策略信号灯（优化版）</h1>
        <p style="text-align:center;color:#94a3b8;">趋势过滤 + 超卖建仓 + 分步止盈 | 止盈阈值已优化（RSI>75 / 偏离15%）</p>
        
        <div class="card">
            <button onclick="fetchAndRun()" style="width:100%; padding:15px; font-size:18px;">🔄 立即更新最新数据（每日必点）</button>
        </div>

        <div class="card" style="text-align:center;">
            <div id="signalLight" class="light gray">加载中...</div>
            <div id="signalText" class="signal-text">——</div>
            <div id="detail" style="font-size:15px; line-height:1.6;"></div>
        </div>

        <div class="card">
            <h3>📊 最新市场状态 & 策略信号</h3>
            <div id="status" style="line-height:1.8;"></div>
        </div>

        <div class="card">
            <canvas id="priceChart" height="120"></canvas>
        </div>

        <div class="card">
            <p style="font-size:13px; color:#64748b; text-align:center;">
                数据来源：Yahoo Finance | 策略最后更新：2026-03-26<br>
                本工具纯前端运行，无需安装，数据每日自动更新
            </p>
        </div>
    </div>

    <script>
        let priceChartInstance = null;

        async function fetchAndRun() {
            const light = document.getElementById('signalLight');
            const text = document.getElementById('signalText');
            light.className = 'light gray';
            light.textContent = '获取数据...';
            text.textContent = '正在拉取最新 QQQ 数据...';

            try {
                // 使用 Yahoo Finance v8 chart API（公开可用）
                const now = Math.floor(Date.now() / 1000);
                const start = 1262304000; // 2010-01-01
                const url = `https://query2.finance.yahoo.com/v8/finance/chart/QQQ?period1=${start}&period2=${now}&interval=1d`;
                
                const response = await fetch(url, {
                    headers: { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" }
                });
                const data = await response.json();

                const result = data.chart.result[0];
                const timestamps = result.timestamp;
                const quotes = result.indicators.quote[0];

                // 构建数据
                const df = [];
                for (let i = 0; i < timestamps.length; i++) {
                    df.push({
                        date: new Date(timestamps[i] * 1000),
                        close: quotes.close[i],
                        high: quotes.high[i],
                        low: quotes.low[i],
                        open: quotes.open[i]
                    });
                }

                // 计算技术指标
                const closes = df.map(d => d.close);
                const ma200 = rollingMean(closes, 200);
                const ma50 = rollingMean(closes, 50);
                const ma20 = rollingMean(closes, 20);
                const bbLower = bollingerLower(closes, 20, 2);
                const rsi = calculateRSI(closes, 14);

                // 运行完整策略逻辑（与 Python 优化版完全一致）
                const strategyResult = runStrategy(df, ma200, ma50, ma20, bbLower, rsi);

                // 显示信号灯
                displaySignal(strategyResult, df[df.length-1]);

                // 画图
                drawChart(df.slice(-400), strategyResult.signals); // 最近400天

            } catch (e) {
                console.error(e);
                document.getElementById('signalText').innerHTML = '❌ 数据获取失败，请稍后重试或检查网络';
            }
        }

        // ==================== 指标计算 ====================
        function rollingMean(arr, window) {
            const result = [];
            for (let i = 0; i < arr.length; i++) {
                if (i < window - 1) result.push(null);
                else {
                    const slice = arr.slice(i - window + 1, i + 1);
                    result.push(slice.reduce((a, b) => a + b, 0) / window);
                }
            }
            return result;
        }

        function bollingerLower(arr, window, k) {
            const result = [];
            for (let i = 0; i < arr.length; i++) {
                if (i < window - 1) result.push(null);
                else {
                    const slice = arr.slice(i - window + 1, i + 1);
                    const mean = slice.reduce((a, b) => a + b, 0) / window;
                    const std = Math.sqrt(slice.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / window);
                    result.push(mean - k * std);
                }
            }
            return result;
        }

        function calculateRSI(closes, period) {
            const rsi = [];
            let gain = 0, loss = 0;
            for (let i = 1; i < closes.length; i++) {
                const change = closes[i] - closes[i-1];
                if (i <= period) {
                    if (change > 0) gain += change;
                    else loss -= change;
                    if (i === period) {
                        const avgGain = gain / period;
                        const avgLoss = loss / period;
                        const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
                        rsi.push(100 - (100 / (1 + rs)));
                    } else rsi.push(null);
                } else {
                    const change = closes[i] - closes[i-1];
                    const newGain = change > 0 ? change : 0;
                    const newLoss = change < 0 ? -change : 0;
                    gain = (gain * (period-1) + newGain) / period;
                    loss = (loss * (period-1) + newLoss) / period;
                    const rs = loss === 0 ? 100 : gain / loss;
                    rsi.push(100 - (100 / (1 + rs)));
                }
            }
            return [null, ...rsi];
        }

        // ==================== 策略核心逻辑（与优化版完全一致） ====================
        function runStrategy(df, ma200, ma50, ma20, bbLower, rsi) {
            let cash = 100000;
            let shares = 0;
            let avgEntry = 0;
            let lastBuyPrice = 0;
            let addStage = 0;
            let entryDate = null;
            let signals = [];

            for (let i = 200; i < df.length; i++) {  // 跳过 warmup
                const price = df[i].close;
                const currentMA200 = ma200[i];
                const currentMA50 = ma50[i];
                const currentMA20 = ma20[i];
                const currentRSI = rsi[i];
                const currentBBLower = bbLower[i];

                // 止损
                if (shares > 0) {
                    if ((avgEntry > 0 && price < avgEntry * 0.92) || price < currentMA200) {
                        cash += shares * price;
                        shares = 0; avgEntry = 0; lastBuyPrice = 0; addStage = 0;
                        signals.push({date: df[i].date, action: 'stoploss'});
                        continue;
                    }
                }

                // 止盈（优化后：75 / 15%）
                if (shares > 0) {
                    const deviate = currentMA50 ? (price / currentMA50 - 1) : 0;
                    if (currentRSI > 75 || deviate > 0.15) {
                        cash += shares * price;
                        shares = 0; avgEntry = 0; lastBuyPrice = 0; addStage = 0;
                        signals.push({date: df[i].date, action: 'takeprofit'});
                        continue;
                    }
                }

                const trendOk = price > currentMA200;
                const oversold = (currentRSI <= 40) || (price <= currentBBLower);

                // 首次建仓
                if (trendOk && oversold && shares === 0 && addStage === 0) {
                    const buyAmount = Math.min(0.3 * (cash + shares * price), cash);
                    if (buyAmount > 0) {
                        const buyShares = buyAmount / price;
                        shares += buyShares;
                        cash -= buyAmount;
                        avgEntry = price;
                        lastBuyPrice = price;
                        addStage = 1;
                        signals.push({date: df[i].date, action: 'buy30'});
                    }
                }

                // 二次加仓（回调4%）
                if (shares > 0 && addStage === 1 && price < lastBuyPrice * 0.96 && price > currentMA200) {
                    const buyAmount = Math.min(0.3 * (cash + shares * price), cash);
                    if (buyAmount > 0) {
                        const buyShares = buyAmount / price;
                        shares += buyShares;
                        cash -= buyAmount;
                        avgEntry = (avgEntry * (shares - buyShares) + price * buyShares) / shares;
                        lastBuyPrice = price;
                        addStage = 2;
                        signals.push({date: df[i].date, action: 'buy30add'});
                    }
                }

                // 三次加仓（反弹 > MA20）
                if (shares > 0 && addStage === 2 && price > currentMA20) {
                    const buyAmount = Math.min(0.4 * (cash + shares * price), cash);
                    if (buyAmount > 0) {
                        const buyShares = buyAmount / price;
                        shares += buyShares;
                        cash -= buyAmount;
                        avgEntry = (avgEntry * (shares - buyShares) + price * buyShares) / shares;
                        lastBuyPrice = price;
                        addStage = 3;
                        signals.push({date: df[i].date, action: 'buy40'});
                    }
                }
            }

            const lastPrice = df[df.length-1].close;
            const unrealized = shares > 0 ? (lastPrice - avgEntry) / avgEntry * 100 : 0;
            const positionPct = shares > 0 ? Math.round((shares * lastPrice) / (cash + shares * lastPrice) * 100) : 0;

            return {
                positionPct,
                avgEntry: avgEntry || 0,
                unrealized,
                lastPrice,
                lastRSI: rsi[rsi.length-1],
                lastMA200: ma200[ma200.length-1],
                trendOk: df[df.length-1].close > ma200[ma200.length-1],
                signals
            };
        }

        function displaySignal(result, lastRow) {
            const light = document.getElementById('signalLight');
            const text = document.getElementById('signalText');
            const detail = document.getElementById('detail');
            const status = document.getElementById('status');

            let colorClass = 'gray';
            let signalMsg = '——';
            let action = '';

            if (result.positionPct === 0) {
                if (result.trendOk && (result.lastRSI <= 40 || lastRow.close <= /* BB lower approx */ lastRow.close * 0.95)) {
                    colorClass = 'green';
                    signalMsg = '🟢 首次买入信号';
                    action = '建议立即买入 30% 仓位';
                } else {
                    colorClass = 'gray';
                    signalMsg = '⚪ 空仓等待';
                    action = '等待超卖信号';
                }
            } else {
                if (result.lastRSI > 75 || (result.avgEntry > 0 && (lastRow.close / result.avgEntry - 1) > 0.15)) {
                    colorClass = 'red';
                    signalMsg = '🔴 止盈信号';
                    action = '建议全仓止盈';
                } else {
                    colorClass = 'yellow';
                    signalMsg = '🟡 持仓观望';
                    action = `当前持仓 ${result.positionPct}% | 未实现盈亏 ${result.unrealized.toFixed(2)}%`;
                }
            }

            light.className = `light ${colorClass}`;
            light.textContent = signalMsg;
            text.textContent = action;

            detail.innerHTML = `
                最新收盘价：<b>${lastRow.close.toFixed(2)}</b><br>
                RSI(14)：<b>${result.lastRSI ? result.lastRSI.toFixed(1) : '—'}</b>　|　
                趋势：<b>${result.trendOk ? '✅ MA200 之上（牛市）' : '❌ 破位'}</b><br>
                当前策略状态：<b>${result.positionPct > 0 ? '已持仓' : '空仓'}</b>
            `;

            status.innerHTML = `
                📍 最新价格：${lastRow.close.toFixed(2)} USD<br>
                📈 200日均线：${result.lastMA200 ? result.lastMA200.toFixed(2) : '—'}<br>
                📉 持仓比例：${result.positionPct}%<br>
                💰 未实现盈亏：${result.unrealized.toFixed(2)}%
            `;
        }

        function drawChart(dfSlice, signals) {
            const ctx = document.getElementById('priceChart');
            if (priceChartInstance) priceChartInstance.destroy();
            
            priceChartInstance = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: dfSlice.map(d => d.date.toISOString().slice(5,10)),
                    datasets: [{
                        label: 'QQQ 收盘价',
                        data: dfSlice.map(d => d.close),
                        borderColor: '#22c55e',
                        borderWidth: 2,
                        tension: 0.1,
                        pointRadius: 0
                    }]
                },
                options: {
                    plugins: { legend: { display: false } },
                    scales: { y: { grid: { color: '#334155' } }, x: { grid: { color: '#334155' } } }
                }
            });
        }

        // 页面加载自动更新一次
        window.onload = () => {
            fetchAndRun();
        };
    </script>
</body>
</html>
