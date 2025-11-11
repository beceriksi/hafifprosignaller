import os, time, requests
from datetime import datetime, timezone

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID        = os.getenv("CHAT_ID")

def ts():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

def telegram(text: str):
    """Sinyalde anlık; özetlerde tek mesaj. TELEGRAM_TOKEN/CHAT_ID yoksa print eder."""
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print(text)
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"},
            timeout=15
        )
    except:
        pass
