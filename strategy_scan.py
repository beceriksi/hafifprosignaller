import os, time, requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

MEXC_FAPI = "https://contract.mexc.com"
COINGECKO_GLOBAL = "https://api.coingecko.com/api/v3/global"
BINANCE_ENDPOINTS = [
    "https://api-gcp.binance.com",
    "https://api1.binance.com",
    "https://api.binance.com",
    "https://api2.binance.com",
    "https://data-api.binance.vision"
]

# --------------- utils ---------------
def ts(): return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

def pick_binance():
    for base in BINANCE_ENDPOINTS:
        try:
            r = requests.get(f"{base}/api/v3/time", timeout=5)
            if r.status_code == 200:
                return base
        except:
            pass
    return BINANCE_ENDPOINTS[0]

BINANCE = pick_binance()

def jget(url, params=None, retries=3, timeout=12):
    for _ in range(retries):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            if r.status_code == 200:
                return r.json()
        except:
            time.sleep(1)
    return None

def telegram(text):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print(text); return
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                      json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"})
    except:
        pass

# --------------- indicators ---------------
def ema(x, n): return x.ewm(span=n, adjust=False).mean()

def rsi(s, n=14):
    d = s.diff()
    up = d.clip(lower=0); dn = -d.clip(upper=0)
    rs = up.ewm(alpha=1/n, adjust=False).mean() / (dn.ewm(alpha=1/n, adjust=False).mean() + 1e-12)
    return 100 - (100/(1+rs))

def macd(s, f=12, m=26, sig=9):
    fast = ema(s,f); slow = ema(s,m)
    line = fast - slow
    signal = line.ewm(span=sig, adjust=False).mean()
    return line, signal, line - signal

def adx(df, n=14):
    up_move = df['high'].diff()
    dn_move = -df['low'].diff()
    plus_dm = np.where((up_move > dn_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((dn_move > up_move) & (dn_move > 0), dn_move, 0.0)
    tr1 = df['high'] - df['low']
    tr2 = (df['high'] - df['close'].shift()).abs()
    tr3 = (df['low'] - df['close'].shift()).abs()
    tr = pd.DataFrame({'a':tr1, 'b':tr2, 'c':tr3}).max(axis=1)
    atr = tr.ewm(alpha=1/n, adjust=False).mean()
    plus_di = 100 * pd.Series(plus_dm).ewm(alpha=1/n, adjust=False).mean() / (atr + 1e-12)
    minus_di = 100 * pd.Series(minus_dm).ewm(alpha=1/n, adjust=False).mean() / (atr + 1e-12)
    dx = ((plus_di - minus_di).abs() / ((plus_di + minus_di) + 1e-12)) * 100
    return dx.ewm(alpha=1/n, adjust=False).mean()

def bos_up(df, look=40, excl=2):
    hh = df['high'][:-excl].tail(look).max()
    return df['close'].iloc[-1] > hh

def bos_dn(df, look=40, excl=2):
    ll = df['low'][:-excl].tail(look).min()
    return df['close'].iloc[-1] < ll

def volume_spike(df, n=20, r=1.5):
    if len(df) < n+2: return False, 1.0
    last = df['volume'].iloc[-1]
    base = df['volume'].iloc[-(n+1):-1].mean()
    ratio = last / (base + 1e-12)
    return ratio >= r, ratio

# --------------- market state / notes ---------------
def btc_state_4h():
    d = jget(f"{BINANCE}/api/v3/klines", {"symbol":"BTCUSDT","interval":"4h","limit":300})
    if not d: return "NÖTR"
    df = pd.DataFrame(d, columns=["t","o","h","l","c","v","ct","x1","x2","x3","x4","x5"]).astype(float)
    c = df['c']
    e20, e50 = ema(c,20).iloc[-1], ema(c,50).iloc[-1]
    r = rsi(c,14).iloc[-1]
    if e20 > e50 and r > 50: return "GÜÇLÜ"
    if e20 < e50 and r < 50: return "ZAYIF"
    return "NÖTR"

def btc_24h_change_pct():
    d = jget(f"{BINANCE}/api/v3/ticker/24hr", {"symbol":"BTCUSDT"})
    try:
        return float(d["priceChangePercent"])
    except: return None

def global_24h_change_pct_and_btc_dominance():
    g = jget(COINGECKO_GLOBAL)
    try:
        total_chg = float(g["data"]["market_cap_change_percentage_24h_usd"])
        btc_dom  = float(g["data"]["market_cap_percentage"]["btc"])
        return total_chg, btc_dom
    except:
        return None, None

def btc_d_trend_note():
    btc_pct = btc_24h_change_pct()
    total_pct, btc_dom = global_24h_change_pct_and_btc_dominance()
    if btc_pct is None or total_pct is None or btc_dom is None:
        return "Piyasa: veri alınamadı."
    # Heuristic: BTC 24h % total 24h %'ten büyükse BTC.D ↑; küçükse ↓
    dom_trend = "↑" if btc_pct > total_pct else ("↓" if btc_pct < total_pct else "→")
    # BTC yön oku
    btc_dir = "↑" if btc_pct > 0 else ("↓" if btc_pct < 0 else "→")
    return f"Piyasa: BTC {btc_dir} + BTC.D {dom_trend} (BTC.D {btc_dom:.1f}%)."

# --------------- mexc data ---------------
def mexc_symbols():
    d = jget(f"{MEXC_FAPI}/api/v1/contract/detail")
    if not d or "data" not in d: return []
    return [s["symbol"] for s in d["data"] if s.get("quoteCoin")=="USDT"]

def klines_mexc(sym, interval="4h", limit=260):
    d = jget(f"{MEXC_FAPI}/api/v1/contract/kline/{sym}", {"interval": interval, "limit": limit})
    if not d or "data" not in d: return None
    df = pd.DataFrame(d["data"], columns=["ts","open","high","low","close","volume","turnover"]).astype(
        {"open":"float64","high":"float64","low":"float64","close":"float64","volume":"float64","turnover":"float64"}
    )
    return df

def funding_rate_mexc(sym):
    # Sadece uyarı amaçlı (sinyali engellemez)
    d = jget(f"{MEXC_FAPI}/api/v1/contract/funding_rate", {"symbol": sym})
    try:
        rate = float(d["data"]["fundingRate"])
        return rate
    except:
        return None

# --------------- scoring ---------------
def confidence_score(side, rsi_val, macd_up, adx_val, v_ratio, bos_flag, btc_state):
    score = 0
    # RSI
    if side == "AL":  score += max(0, min(20, (rsi_val-50)*2))
    if side == "SAT": score += max(0, min(20, (50-rsi_val)*2))
    # MACD
    score += 20 if (macd_up == (side=="AL")) else 10
    # ADX
    score += 20 if adx_val >= 25 else (10 if adx_val >= 15 else 0)
    # Volume
    score += min(20, (v_ratio-1.0)*20)
    # BTC global state (yalın etki)
    if (side=="AL" and btc_state!="ZAYIF") or (side=="SAT" and btc_state!="GÜÇLÜ"):
        score += 10
    # BoS
    score += 10 if bos_flag else 5
    return int(min(100, score))

# --------------- analysis ---------------
def analyze_symbol(sym, btc_state, vol_ratio_required):
    df = klines_mexc(sym, "4h", 260)
    if df is None or len(df) < 120: return None, None, None

    # Likidite: son 4H turnover >= 1M USDT
    if float(df["turnover"].iloc[-1]) < 1_000_000:
        return None, "lowliq", None

    # GAP filtresi: son 4H %8'den fazla hareket varsa atla
    c = df['close']
    last_change = abs(float(c.iloc[-1]/c.iloc[-2] - 1))
    if last_change > 0.08:
        return None, "gap", None

    h = df['high']; l = df['low']
    e20, e50 = ema(c,20).iloc[-1], ema(c,50).iloc[-1]
    trend_up = e20 > e50
    r = float(rsi(c,14).iloc[-1])
    m_line, m_sig, _ = macd(c)
    macd_up = m_line.iloc[-1] > m_sig.iloc[-1]
    macd_dn = not macd_up
    adx_val = float(adx(pd.DataFrame({'high':h,'low':l,'close':c}),14).iloc[-1])
    strong_trend = adx_val >= 15
    bosU, bosD = bos_up(df), bos_dn(df)

    # Hacim: ZORUNLU (hem AL hem SAT)
    v_ok, v_ratio = volume_spike(df, n=20, r=vol_ratio_required)
    if not v_ok:
        return None, "novol", None

    # Sell için: fiyat düşüş + hacim artışı
    last_down = float(c.iloc[-1]) < float(c.iloc[-2])
    sell_vol_strong = last_down and v_ok

    side = None; bos_flag = False
    if trend_up and r > 52 and macd_up and strong_trend:
        side = "AL"; bos_flag = bosU
    elif (not trend_up) and r < 48 and macd_dn and strong_trend and sell_vol_strong:
        side = "SAT"; bos_flag = bosD
    else:
        return None, None, None

    score = confidence_score(side, r, macd_up, adx_val, v_ratio, bos_flag, btc_state)
    trend_txt = "↑" if trend_up else "↓"
    bos_txt = "↑" if bosU else ("↓" if bosD else "-")
    vol_txt = f"x{v_ratio:.2f}"
    px = float(c.iloc[-1])

    # Funding uyarısı (opsiyonel, engellemez)
    fr = funding_rate_mexc(sym)
    fr_note = ""
    if fr is not None:
        if fr > 0.01:
            fr_note = f"\n⚠️ Funding pozitif ({fr:.3f}) — long dolu, ters hareket riski."
        elif fr < -0.01:
            fr_note = f"\n⚠️ Funding negatif ({fr:.3f}) — short dolu, short squeeze olası."

    msg = (
        f"✅ {sym} — *{side}* | Trend:{trend_txt} | RSI:{r:.1f} | MACD:{'↑' if macd_up else '↓'} | "
        f"ADX:{adx_val:.0f} | Hacim {vol_txt} | BoS:{bos_txt} | Fiyat:{px}\n"
        f"🧭 Güven skoru: {score}/100{fr_note}"
    )
    return msg, None, score

def main():
    btc_state = btc_state_4h()
    # BTC.D uyarı notu (sinyali engellemez)
    market_note = btc_d_trend_note()

    # Hacim eşiği: sade (x1.5) — sabit bırakıyoruz
    vol_r = 1.5

    syms = mexc_symbols()
    if not syms:
        telegram("⚠️ Sembol listesi alınamadı (MEXC)."); return

    header = [f"⏱ {ts()} — *Strateji Taraması* (BTC: {btc_state} | HacimEşik: x{vol_r:.1f})"]
    signals = []; skipped = {"lowliq":0, "gap":0, "novol":0}
    for i, s in enumerate(syms):
        try:
            res, flag, _ = analyze_symbol(s, btc_state, vol_r)
            if flag in skipped: skipped[flag]+=1
            if res: signals.append(res)
        except:
            pass
        if i % 15 == 0: time.sleep(0.3)

    if not signals:
        header.append("ℹ️ Şu an kriterlere uyan sinyal yok.")
    else:
        header.extend(signals[:25])

    header.append(f"\n📊 Özet: {len(signals)} sinyal | Atlanan (likidite:{skipped['lowliq']}, gap:{skipped['gap']}, hacim:{skipped['novol']})")
    header.append(f"ℹ️ {market_note}")
    telegram("\n".join(header))

if __name__ == "__main__":
    main()
