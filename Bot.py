 os
import threading
import time
from flask import Flask, render_template_string
from websocket import create_connection
import json

# ---------------------------
# Deriv API Setup
# ---------------------------
API_TOKEN = os.getenv("DERIV_API_TOKEN")
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
    ws = create_connection(DERIV_URL)
    ws.send(json.dumps({"authorize": API_TOKEN}))
    time.sleep(1)
    ws.send(json.dumps({"ticks": "R_100"}))  # Example symbol

    while bot_running:
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
)
