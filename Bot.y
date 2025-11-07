import websocket
import json
import threading
import sqlite3
from flask import Flask, render_template_string, request

# === CONFIG ===
API_TOKEN = "YOUR_DERIV_API_TOKEN"  # Replace with your Deriv API token
SYMBOL = "R_100"                    # Trading symbol
STAKE = 1                            # Trade amount
DURATION = 1                         # Trade duration
DURATION_UNIT = "m"                   # Minutes
FAST_EMA_PERIOD = 5
SLOW_EMA_PERIOD = 15
DB_FILE = "trades.db"

# === GLOBALS ===
prices = []
fast_ema_value = None
slow_ema_value = None
bot_running = False

# === DATABASE SETUP ===
conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT,
    price REAL,
    direction TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()
conn.close()

# === HELPER FUNCTIONS ===
def calculate_ema(prices, period):
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period

def log_trade(symbol, price, direction):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO trades (symbol, price, direction) VALUES (?, ?, ?)",
                   (symbol, price, direction))
    conn.commit()
    conn.close()
    print(f"Trade logged: {direction} at {price}")

def place_trade(direction):
    global bot_running
    if not bot_running:
        return
    trade_request = {
        "buy": 1,
        "parameters": {
            "amount": STAKE,
            "basis": "stake",
            "contract_type": "CALL" if direction == "up" else "PUT",
            "currency": "USD",
            "duration": DURATION,
            "duration_unit": DURATION_UNIT,
            "symbol": SYMBOL
        },
        "authorization": API_TOKEN
    }
    ws.send(json.dumps(trade_request))
    log_trade(SYMBOL, prices[-1], direction)

# === WEBSOCKET CALLBACKS ===
def on_message(ws_app, message):
    global prices, fast_ema_value, slow_ema_value, bot_running
    data = json.loads(message)
    if "tick" in data:
        tick_price = data["tick"]["quote"]
        prices.append(tick_price)
        if len(prices) > 50:
            prices.pop(0)
        fast_ema_value = calculate_ema(prices, FAST_EMA_PERIOD)
        slow_ema_value = calculate_ema(prices, SLOW_EMA_PERIOD)
        if bot_running and fast_ema_value and slow_ema_value:
            if fast_ema_value > slow_ema_value:
                place_trade("up")
            elif fast_ema_value < slow_ema_value:
                place_trade("down")

def on_open(ws_app):
    print("Connected to Deriv!")
    ws_app.send(json.dumps({
        "ticks": SYMBOL,
        "subscribe": 1,
        "authorization": API_TOKEN
    }))

def on_close(ws_app):
    print("Disconnected")

def on_error(ws_app, error):
    print(f"Error: {error}")

# === START WEBSOCKET IN THREAD ===
def start_ws():
    global ws
    ws = websocket.WebSocketApp(
        "wss://ws.binaryws.com/websockets/v3?app_id=1089",
        on_open=on_open,
        on_message=on_message,
        on_close=on_close,
        on_error=on_error
    )
    ws.run_forever()

ws_thread = threading.Thread(target=start_ws)
ws_thread.daemon = True
ws_thread.start()

# === FLASK DASHBOARD ===
app = Flask(__name__)

HTML = """
<!DOCTYPE html>
<html>
<head>
<title>Deriv Scalper Dashboard</title>
<meta http-equiv="refresh" content="2">
</head>
<body>
<h1>Deriv Scalper Dashboard</h1>
<p><strong>Current Price:</strong> {{ current_price }}</p>
<p><strong>Fast EMA:</strong> {{ fast_ema }}</p>
<p><strong>Slow EMA:</strong> {{ slow_ema }}</p>

<form method="POST" action="/control">
<button name="action" value="start" type="submit">Start Bot</button>
<button name="action" value="stop" type="submit">Stop Bot</button>
</form>

<h2>Last 20 Trades</h2>
<table border="1">
<tr><th>ID</th><th>Symbol</th><th>Price</th><th>Direction</th><th>Timestamp</th></tr>
{% for trade in trades %}
<tr>
<td>{{ trade[0] }}</td>
<td>{{ trade[1] }}</td>
<td>{{ trade[2] }}</td>
<td>{{ trade[3] }}</td>
<td>{{ trade[4] }}</td>
</tr>
{% endfor %}
</table>
</body>
</html>
"""

@app.route('/')
def dashboard():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trades ORDER BY id DESC LIMIT 20")
    trades = cursor.fetchall()
    conn.close()
    current_price = prices[-1] if prices else "N/A"
    return render_template_string(HTML,
                                  trades=trades,
                                  current_price=current_price,
                                  fast_ema=fast_ema_value or "N/A",
                                  slow_ema=slow_ema_value or "N/A")

@app.route('/control', methods=['POST'])
def control_bot():
    global bot_running
    action = request.form.get("action")
    if action == "start":
        bot_running = True
    elif action == "stop":
        bot_running = False
    return dashboard()

# === RUN DASHBOARD ===
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)
