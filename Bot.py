import os
import threading
import time
from flask import Flask, render_template_string, jsonify
from websocket import create_connection, WebSocketException
import json

# ---------------------------
# Deriv API Setup
# ---------------------------
API_TOKEN = os.getenv("DERIV_API_TOKEN")
if not API_TOKEN:
    print("ERROR: DERIV_API_TOKEN environment variable is missing!")

DERIV_URL = "wss://ws.binaryws.com/websockets/v3?app_id=1089"

# ---------------------------
# Bot State
# ---------------------------
bot_running = False
prices = []
fast_emas = []
slow_emas = []
last_trades = []

# ---------------------------
# EMA Calculation
# ---------------------------
def calculate_ema(prices, period):
    if len(prices) < period:
        return None
    k = 2 / (period + 1)
    ema = prices[0]
    for price in prices[1:]:
        ema = price * k + ema * (1 - k)
    return ema

# ---------------------------
# Bot Logic
# ---------------------------
def run_bot():
    global bot_running, prices, fast_emas, slow_emas, last_trades
    if not API_TOKEN:
        print("Cannot start bot: Missing DERIV_API_TOKEN.")
        bot_running = False
        return

    try:
        ws = create_connection(DERIV_URL)
        ws.send(json.dumps({"authorize": API_TOKEN}))
        time.sleep(1)
        ws.send(json.dumps({"ticks": "R_100"}))  # Example symbol
    except WebSocketException as e:
        print("WebSocket connection failed:", e)
        bot_running = False
        return
    except Exception as e:
        print("Unknown error connecting to Deriv:", e)
        bot_running = False
        return

    while bot_running:
        try:
            result = ws.recv()
            data = json.loads(result)
            if 'tick' in data:
                price = data['tick']['quote']
                prices.append(price)
                if len(prices) > 50:
                    prices.pop(0)

                fast_ema = calculate_ema(prices, 5)
                slow_ema = calculate_ema(prices, 20)
                fast_emas.append(fast_ema if fast_ema else 0)
                slow_emas.append(slow_ema if slow_ema else 0)

                if len(fast_emas) > 50:
                    fast_emas.pop(0)
                    slow_emas.pop(0)

                # EMA strategy: log trades
                if fast_ema and slow_ema:
                    if fast_ema > slow_ema:
                        last_trades.append({"price": price, "direction": "up"})
                    elif fast_ema < slow_ema:
                        last_trades.append({"price": price, "direction": "down"})
                    if len(last_trades) > 20:
                        last_trades.pop(0)
        except WebSocketException as e:
            print("WebSocket error during receive:", e)
            break
        except Exception as e:
            print("Unknown error during bot run:", e)
            break
        time.sleep(1)
    ws.close()
    print("Bot stopped.")

# ---------------------------
# Flask App
# ---------------------------
app = Flask(__name__)

HTML_TEMPLATE = """
<!doctype html>
<html>
<head>
    <title>Deriv Scalper Bot</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
<h1>Deriv Scalper Dashboard</h1>

<p>Current Price: <span id="current_price">{{ current_price }}</span></p>

<form method="post" action="/start">
    <button type="submit">Start Bot</button>
</form>
<form method="post" action="/stop">
    <button type="submit">Stop Bot</button>
</form>

<h2>Price & EMA Chart</h2>
<canvas id="emaChart" width="400" height="200"></canvas>

<h2>Last Trades</h2>
<ul id="trade_list">
{% for trade in trades %}
  <li>{{ trade.direction }} at {{ trade.price }}</li>
{% endfor %}
</ul>

<script>
const ctx = document.getElementById('emaChart').getContext('2d');
let chart = new Chart(ctx, {
    type: 'line',
    data: {
        labels: [],
        datasets: [
            { label: 'Price', data: [], borderColor: 'blue', fill: false },
            { label: 'Fast EMA', data: [], borderColor: 'green', fill: false },
            { label: 'Slow EMA', data: [], borderColor: 'red', fill: false }
        ]
    },
    options: { animation: false, responsive: true }
});

const MAX_POINTS = 50;

async function updateChart() {
    const res = await fetch('/data');
    const data = await res.json();

    chart.data.labels = data.labels.slice(-MAX_POINTS);
    chart.data.datasets[0].data = data.prices.slice(-MAX_POINTS);
    chart.data.datasets[1].data = data.fast_emas.slice(-MAX_POINTS);
    chart.data.datasets[2].data = data.slow_emas.slice(-MAX_POINTS);
    chart.update();

    document.getElementById('current_price').innerText = data.current_price;

    const tradeList = document.getElementById('trade_list');
    tradeList.innerHTML = '';
    data.trades.forEach(trade => {
        const li = document.createElement('li');
        li.innerText = `${trade.direction} at ${trade.price}`;
        tradeList.appendChild(li);
    });
}

setInterval(updateChart, 1000);
</script>
</body>
</html>
"""

@app.route("/")
def index():
    current_price = prices[-1] if prices else "N/A"
    return render_template_string(
        HTML_TEMPLATE,
        current_price=current_price,
        trades=last_trades
    )

@app.route("/data")
def data():
    labels = list(range(len(prices)))
    return jsonify({
        "prices": prices,
        "fast_emas": fast_emas,
        "slow_emas": slow_emas,
        "trades": last_trades,
        "labels": labels,
        "current_price": prices[-1] if prices else "N/A"
    })

@app.route("/start", methods=["POST"])
def start_bot():
    global bot_running
    if not bot_running:
        bot_running = True
        threading.Thread(target=run_bot).start()
    return index()

@app.route("/stop", methods=["POST"])
def stop_bot():
    global bot_running
    bot_running = False
    return index()

# ---------------------------
# Run Flask for Render
# ---------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("Starting Flask on port", port)
    app.run(host="0.0.0.0", port=port)
