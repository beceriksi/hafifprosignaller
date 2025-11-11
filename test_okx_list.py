import requests
import json

url = "https://www.okx.com/api/v5/market/tickers?instType=SPOT"

try:
    r = requests.get(url, timeout=15)
    print("Status:", r.status_code)
    print("First 300 chars:", r.text[:300])
except Exception as e:
    print("EXCEPTION:", e)
