import os, time, requests, pandas as pd, numpy as np
from datetime import datetime, timezone

# ====== AYARLAR ======
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID        = os.getenv("CHAT_ID")

OKX_BASE       = "https://www.okx.com"
TOP_N          = int(os.getenv("TOP_N", "80"))
VOL_MIN_EARLY  = float(os.getenv("VOL_MIN_EARLY", "150000"))
VOL_MIN_CONF   = float(os.getenv("VOL_MIN_CONF", "250000"))
VRATIO_EARLY   = float(os.getenv("VRATIO_EARLY", "3.0"))
VRATIO_CONF    = float(os.getenv("VRATIO_CONF", "3.5"))
MOM_1M_MIN     = float(os.getenv("MOM_1M_MIN",   "0.0045"))
PULLBACK_MIN   = float(os.getenv("PULLBACK_MIN", "0.0025"))
PULLBACK_MAX   = float(os.getenv("PULLBACK_MAX", "0.0080"))
RSI5_CONF_MIN  = float(os.getenv("RSI5_CONF_MIN","53.0"))
MAX_MSG_COINS  = int(os.getenv("MAX_MSG_COINS", "10"))

# ====== YARDIMCI ======
def ts(): return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

def jget(path, params=None, retries=3, timeout=12):
    url = path if path.startswith("http") else OKX_BASE + path
    for _ in range(retries):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            if r.status_code == 200:
                j = r.json()
                if isinstance(j, dict) and str(j.get("code")) == "0" and "data" in j:
                    return j["data"]
        except:
            time.sleep(0.25)
    return None

def telegram(text):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print(text); return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"},
            timeout=15
        )
    except:
        pass

def ema(x, n): return x.ewm(span=n, adjust=False).mean()

def rsi(s, n=14):
    d = s.diff(); up = d.clip(lower=0); dn = -d.clip(upper=0)
    rs = up.ewm(alpha=1/n, adjust=False).mean() / (dn.ewm(alpha=1/n, adjust=False).mean() + 1e-12)
    return 100 - (100/(1+rs))

# ===== COIN LİSTESİ (OKX SPOT → USDT) =====
def okx_top_usdt_spot(limit=TOP_N):
    rows = jget("/api/v5/market/tickers", {"instType":"SPOT"}) or []
    fil = [r for r in rows if str(r.get("quoteCcy","")).upper() == "USDT"]
    fil.sort(key=lambda x: float(x.get("volCcy24h", "0")), reverse=True)
    return [r["instId"] for r in fil[:limit]]

# ====== KLINE ======
def kline_1m(instId, limit=60):
    d = jget("/api/v5/market/candles", {"instId":instId, "bar":"1m", "limit":limit})
    if not d: return None
    df = pd.DataFrame(d, columns=["ts","o","h","l","c","vol","volCcy","vol2","confirm"])
    df = df.astype({"o":"float64","h":"float64","l":"float64","c":"float64","vol":"float64","volCcy":"float64"})
    df["turnover"] = df["volCcy"]
    df = df.iloc[::-1].reset_index(drop=True)
    return df

def kline_5m(instId, limit=50):
    d = jget("/api/v5/market/candles", {"instId":instId, "bar":"5m", "limit":limit})
    if not d: return None
    df = pd.DataFrame(d, columns=["ts","o","h","l","c","vol","volCcy","vol2","confirm"])
    df = df.astype({"o":"float64","h":"float64","l":"float64","c":"float64","vol":"float64","volCcy":"float64"})
    df["turnover"] = df["volCcy"]
    df = df.iloc[::-1].reset_index(drop=True)
    return df

# ====== EARLY ======
def early_alert(df1):
    if df1 is None or len(df1) < 50: return False, {}
    t = df1["turnover"]
    if t.iloc[-1] < VOL_MIN_EARLY: return False, {}
    base = ema(t, 15)
    v_ratio = float(t.iloc[-1] / (base.iloc[-2] + 1e-12))
    if v_ratio < VRATIO_EARLY: return False, {}
    c = df1["c"]
    mom = float(c.iloc[-1]/(c.iloc[-2]+1e-12) - 1)
    if mom < MOM_1M_MIN: return False, {}
    e20 = float(ema(c, 20).iloc[-1])
    e50 = float(ema(c, 50).iloc[-1])
    if e20 <= e50: return False, {}
    return True, {"v_ratio": v_ratio, "mom": mom}

# ====== CONFIRMED BUY ======
def safe_confirmation(df1, df5):
    if df1 is None or len(df1) < 50 or df5 is None or len(df5) < 20: return False, {}
    t = df1["turnover"]; c = df1["c"]
    base = ema(t, 15)
    v_now  = float(t.iloc[-1] / (base.iloc[-2] + 1e-12))
    v_m1   = float(t.iloc[-2] / (base.iloc[-3] + 1e-12))
    v_m2   = float(t.iloc[-3] / (base.iloc[-4] + 1e-12))
    spikes = []
    for k,vr in [(-3,v_m2),(-2,v_m1),(-1,v_now)]:
        if vr >= VRATIO_EARLY:
            spikes.append(k)
    if not spikes: return False, {}
    idx = len(c) + spikes[0]
    spike_close = float(c.iloc[idx])
    since = c.iloc[idx:-1]
    if len(since) < 1: return False, {}
    min_after = float(since.min())
    pull = (min_after / spike_close) - 1
    if not (-PULLBACK_MAX <= pull <= -PULLBACK_MIN):
        return False, {}
    max_after = float(since.max())
    if float(c.iloc[-1]) <= max_after: return False, {}
    if v_now < VRATIO_CONF: return False, {}
    r5 = float(rsi(df5["c"], 14).iloc[-1])
    if r5 < RSI5_CONF_MIN: return False, {}
    e20 = float(ema(c,20).iloc[-1])
    e50 = float(ema(c,50).iloc[-1])
    if e20 <= e50: return False, {}
    if float(t.iloc[-1]) < VOL_MIN_CONF: return False, {}
    mom = float(c.iloc[-1]/(c.iloc[-2]+1e-12) - 1)
    score = int(min(100, (v_now*18) + (mom*100) + ((r5-50)*3) + 15))
    return True, {"v_ratio": v_now, "pull": pull, "rsi5": r5, "score": score}

# ====== SELL ======
def sell_signal(df1, df5):
    if df1 is None or len(df1) < 50 or df5 is None or len(df5) < 20: return False, {}
    c = df1["c"]
    e20 = float(ema(c,20).iloc[-1]); e50 = float(ema(c,50).iloc[-1])
    if e20 >= e50: return False, {}
    r5 = float(rsi(df5["c"], 14).iloc[-1])
    if r5 > 45: return False, {}
    drop2 = float(c.iloc[-1]/(c.iloc[-3]+1e-12) - 1)
    if drop2 > -0.011: return False, {}
    score = int(min(100, (abs(drop2)*100) + ((45-r5)*2) + 20))
    return True, {"rsi5": r5, "drop2": drop2, "score": score}

# ====== MAIN ======
def main():
    symbols = okx_top_usdt_spot()
    if not symbols:
        telegram(f"⛔ {ts()} — OKX'ten coin listesi alınamadı!")
        return

    buys, sells, early = [], [], []

    for i, inst in enumerate(symbols):
        try:
            df1 = kline_1m(inst, 60)
            if df1 is None: continue

            ok_e, edata = early_alert(df1)
            if ok_e:
                early.append(f"- {inst} | ⚠️ Erken | vRatio:{edata['v_ratio']:.2f} | Δ1m:{edata['mom']*100:.2f}%")

            df5 = kline_5m(inst, 50)
            ok_b, bdata = safe_confirmation(df1, df5)
            if ok_b:
                buys.append((bdata["score"], f"- {inst} | 🟢 BUY | vRatio:{bdata['v_ratio']:.2f} | Pull:{bdata['pull']*100:.2f}% | RSI5:{bdata['rsi5']:.1f} | Güven:{bdata['score']}"))

            ok_s, sdata = sell_signal(df1, df5)
            if ok_s:
                sells.append((sdata["score"], f"- {inst} | 🔴 SELL | Δ2m:{sdata['drop2']*100:.2f}% | RSI5:{sdata['rsi5']:.1f} | Güven:{sdata['score']}"))

        except:
            pass

        if (i+1) % 12 == 0:
            time.sleep(0.25)

    if not buys and not sells and not early:
        print(f"{ts()} — sinyal yok")
        return

    buys.sort(key=lambda x: x[0], reverse=True)
    sells.sort(key=lambda x: x[0], reverse=True)

    msg = [f"🧭 *OKX 1m/5m Tarama*\n⏱ {ts()}\nTaranan: {len(symbols)} coin"]
    if early:
        msg.append("\n⏳ *Erken Uyarılar*")
        msg += early[:MAX_MSG_COINS]
    if buys:
        msg.append("\n📈 *BUY*")
        msg += [m for _, m in buys[:MAX_MSG_COINS]]
    if sells:
        msg.append("\n📉 *SELL*")
        msg += [m for _, m in sells[:MAX_MSG_COINS]]

    telegram("\n".join(msg))

if __name__ == "__main__":
    main()
