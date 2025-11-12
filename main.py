import os, time, requests, pandas as pd, numpy as np
from datetime import datetime, timezone

# ====== AYARLAR ======
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID        = os.getenv("CHAT_ID")

OKX_BASE       = "https://www.okx.com"
TOP_N          = int(os.getenv("TOP_N", "200"))
VOL_MIN_EARLY  = float(os.getenv("VOL_MIN_EARLY", "150000"))  # düşürüldü
VOL_MIN_CONF   = float(os.getenv("VOL_MIN_CONF", "250000"))   # düşürüldü
VRATIO_EARLY   = float(os.getenv("VRATIO_EARLY", "2.8"))      # gevşetildi
VRATIO_CONF    = float(os.getenv("VRATIO_CONF", "3.2"))       # gevşetildi
MOM_1M_MIN     = float(os.getenv("MOM_1M_MIN", "0.0040"))     # daha esnek momentum
PULLBACK_MIN   = float(os.getenv("PULLBACK_MIN", "0.0020"))
PULLBACK_MAX   = float(os.getenv("PULLBACK_MAX", "0.0100"))
RSI5_CONF_MIN  = float(os.getenv("RSI5_CONF_MIN", "51.0"))    # RSI onayı biraz gevşetildi
MAX_MSG_COINS  = int(os.getenv("MAX_MSG_COINS", "25"))

# ====== FONKSİYONLAR ======
def ts(): return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

def jget(path, params=None, retries=3, timeout=10):
    url = OKX_BASE + path if not path.startswith("http") else path
    for _ in range(retries):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            if r.status_code == 200:
                j = r.json()
                if j.get("code") == "0": return j.get("data")
        except: time.sleep(0.3)
    return None

def telegram(msg):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print(msg); return
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                      json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=15)
    except: pass

def ema(x, n): return x.ewm(span=n, adjust=False).mean()
def rsi(s, n=14):
    d = s.diff(); up, dn = d.clip(lower=0), -d.clip(upper=0)
    rs = up.ewm(alpha=1/n).mean() / (dn.ewm(alpha=1/n).mean() + 1e-12)
    return 100 - (100 / (1 + rs))

# ====== COIN LİSTESİ ======
def okx_top_usdt_spot(limit=TOP_N):
    data = jget("/api/v5/market/tickers", {"instType": "SPOT"}) or []
    syms = [x["instId"] for x in data if str(x["instId"]).endswith("-USDT")]
    syms = sorted(set(syms))[:limit]
    return syms

# ====== KLINE ======
def kline(inst, bar="1m", limit=60):
    d = jget("/api/v5/market/candles", {"instId": inst, "bar": bar, "limit": limit})
    if not d: return None
    df = pd.DataFrame(d, columns=["ts","o","h","l","c","vol","volCcy","volCcyQuote","confirm"])
    df = df.astype(float)
    df["turnover"] = df["volCcy"]
    df = df.iloc[::-1].reset_index(drop=True)
    return df

# ====== ERKEN UYARI ======
def early_alert(df):
    if df is None or len(df) < 50: return False, {}
    t = df["turnover"]; c = df["c"]
    if t.iloc[-1] < VOL_MIN_EARLY: return False, {}
    v_ratio = t.iloc[-1] / (ema(t, 15).iloc[-2] + 1e-12)
    if v_ratio < VRATIO_EARLY: return False, {}
    mom = c.iloc[-1]/(c.iloc[-2]+1e-12) - 1
    if mom < MOM_1M_MIN: return False, {}
    if ema(c,20).iloc[-1] <= ema(c,50).iloc[-1]: return False, {}
    return True, {"v_ratio": v_ratio, "mom": mom}

# ====== BUY ======
def buy_signal(df1, df5):
    if df1 is None or len(df1) < 50 or df5 is None: return False, {}
    t, c = df1["turnover"], df1["c"]
    base = ema(t, 15)
    v_now = t.iloc[-1] / (base.iloc[-2] + 1e-12)
    if v_now < VRATIO_CONF: return False, {}
    if t.iloc[-1] < VOL_MIN_CONF: return False, {}
    r5 = rsi(df5["c"]).iloc[-1]
    if r5 < RSI5_CONF_MIN: return False, {}
    e20, e50 = ema(c,20).iloc[-1], ema(c,50).iloc[-1]
    if e20 <= e50: return False, {}
    mom = c.iloc[-1]/(c.iloc[-2]+1e-12)-1
    score = int(min(100, (v_now*18)+(mom*100)+((r5-50)*3)+(15 if e20>e50 else 0)))
    return True, {"v_ratio": v_now, "rsi5": r5, "score": score}

# ====== SELL ======
def sell_signal(df1, df5):
    if df1 is None or len(df1) < 50 or df5 is None: return False, {}
    c = df1["c"]; e20, e50 = ema(c,20).iloc[-1], ema(c,50).iloc[-1]
    if e20 >= e50: return False, {}
    r5 = rsi(df5["c"]).iloc[-1]
    if r5 > 45: return False, {}
    drop = c.iloc[-1]/(c.iloc[-3]+1e-12) - 1
    if drop > -0.011: return False, {}
    score = int(min(100, abs(drop)*100 + ((45-r5)*2) + 20))
    return True, {"rsi5": r5, "score": score}

# ====== MAIN ======
def main():
    symbols = okx_top_usdt_spot()
    if not symbols:
        telegram(f"⛔ {ts()} — OKX'ten coin listesi alınamadı.")
        return
    early, buys, sells = [], [], []
    for s in symbols:
        try:
            df1 = kline(s, "1m", 60)
            df5 = kline(s, "5m", 50)
            ok_e, e = early_alert(df1)
            if ok_e: early.append(f"⚠️ {s} | Hacim x{e['v_ratio']:.2f} | Δ1m:{e['mom']*100:.2f}%")
            ok_b, b = buy_signal(df1, df5)
            if ok_b: buys.append((b["score"], f"🟢 {s} | BUY | Güven:{b['score']} | RSI5:{b['rsi5']:.1f}"))
            ok_s, sdata = sell_signal(df1, df5)
            if ok_s: sells.append((sdata["score"], f"🔴 {s} | SELL | RSI5:{sdata['rsi5']:.1f} | Güven:{sdata['score']}"))
        except: pass
        time.sleep(0.2)

    buys.sort(key=lambda x: x[0], reverse=True)
    sells.sort(key=lambda x: x[0], reverse=True)

    if not early and not buys and not sells:
        print(f"{ts()} — sinyal yok.")
        return

    msg = [f"🧭 *OKX Hafifletilmiş Tarama*\n⏱ {ts()}\nTaranan: {len(symbols)} coin"]
    if early: msg.append("\n⚠️ *Erken Uyarılar*"); msg += early[:MAX_MSG_COINS]
    if buys: msg.append("\n📈 *BUY Sinyalleri*"); msg += [x[1] for x in buys[:MAX_MSG_COINS]]
    if sells: msg.append("\n📉 *SELL Sinyalleri*"); msg += [x[1] for x in sells[:MAX_MSG_COINS]]
    telegram("\n".join(msg))

if __name__ == "__main__":
    main()
