import os, time, requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone

# -------- Secrets
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# -------- Endpoints
MEXC = "https://contract.mexc.com"
BINANCE = "https://api.binance.com"
COINGECKO = "https://api.coingecko.com/api/v3/global"

# -------- Utils
def ts(): return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

def jget(url, params=None, retries=3, timeout=12):
    for _ in range(retries):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            if r.status_code == 200: return r.json()
        except: time.sleep(0.4)
    return None

def telegram(text):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print(text); return
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                      json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"})
    except: pass

# -------- Indicators
def ema(x,n): return x.ewm(span=n, adjust=False).mean()
def rsi(s,n=14):
    d=s.diff(); up=d.clip(lower=0); dn=-d.clip(upper=0)
    rs=up.ewm(alpha=1/n, adjust=False).mean()/(dn.ewm(alpha=1/n, adjust=False).mean()+1e-12)
    return 100-(100/(1+rs))
def adx(df,n=14):
    up=df['high'].diff(); dn=-df['low'].diff()
    plus=np.where((up>dn)&(up>0),up,0.0); minus=np.where((dn>up)&(dn>0),dn,0.0)
    tr1=df['high']-df['low']; tr2=(df['high']-df['close'].shift()).abs(); tr3=(df['low']-df['close'].shift()).abs()
    tr=pd.DataFrame({'a':tr1,'b':tr2,'c':tr3}).max(axis=1)
    atr=tr.ewm(alpha=1/n, adjust=False).mean()
    plus_di=100*pd.Series(plus).ewm(alpha=1/n, adjust=False).mean()/(atr+1e-12)
    minus_di=100*pd.Series(minus).ewm(alpha=1/n, adjust=False).mean()/(atr+1e-12)
    dx=((plus_di-minus_di).abs()/((plus_di+minus_di)+1e-12))*100
    return dx.ewm(alpha=1/n, adjust=False).mean()

def volume_signal(df, n, r_min, z_min, ramp_min):
    """USDT turnover tabanlı hacim tetikleyici: EMA oran + z-score + ramp (3'lü)"""
    t = df['turnover'].astype(float)
    if len(t) < max(3, n+2): return False, {"ratio":1.0,"z":0.0,"ramp":1.0}
    base_ema = t.ewm(span=n, adjust=False).mean()
    ratio = float(t.iloc[-1] / (base_ema.iloc[-2] + 1e-12))
    roll = t.rolling(n)
    mu = np.log((roll.median().iloc[-1] or 1e-12) + 1e-12)
    sd = np.log((roll.std().iloc[-1] or 1e-12) + 1e-12)
    z = (np.log(t.iloc[-1] + 1e-12) - mu) / (sd + 1e-12)
    ramp = float(t.iloc[-3:].sum() / ((roll.mean().iloc[-1] * 3) + 1e-12))
    ok = (ratio >= r_min) or (z >= z_min) or (ramp >= ramp_min)
    return ok, {"ratio":ratio, "z":z, "ramp":ramp}

def gap_ok(c, pct):
    if len(c) < 2: return False
    return abs(float(c.iloc[-1] / c.iloc[-2] - 1)) <= pct

# -------- Market notes
def coin_state(symbol, interval):
    d=jget(f"{BINANCE}/api/v3/klines",{"symbol":symbol,"interval":interval,"limit":200})
    if not d: return "NÖTR"
    df=pd.DataFrame(d,columns=["t","o","h","l","c","v","ct","a","b","c2","d","e"]).astype(float)
    c=df['c']; e20,e50=ema(c,20).iloc[-1], ema(c,50).iloc[-1]; rr=rsi(c,14).iloc[-1]
    if e20>e50 and rr>50: return "GÜÇLÜ"
    if e20<e50 and rr<50: return "ZAYIF"
    return "NÖTR"

def market_note():
    g=jget(COINGECKO)
    try:
        total=float(g["data"]["market_cap_change_percentage_24h_usd"])
        btcd=float(g["data"]["market_cap_percentage"]["btc"])
        usdt=float(g["data"]["market_cap_percentage"]["usdt"])
    except: return "Piyasa: veri alınamadı."
    tkr=jget(f"{BINANCE}/api/v3/ticker/24hr",{"symbol":"BTCUSDT"})
    btc=float(tkr["priceChangePercent"]) if tkr and "priceChangePercent" in tkr else None
    arrow="↑" if (btc is not None and btc>total) else ("↓" if (btc is not None and btc<total) else "→")
    dirb ="↑" if (btc is not None and btc>0) else ("↓" if (btc is not None and btc<0) else "→")
    total2="↑ (Altlara giriş)" if arrow=="↓" and total>=0 else ("↓ (Çıkış)" if arrow=="↑" and total<=0 else "→ (Karışık)")
    usdt_note=f"{usdt:.1f}%"; 
    if usdt>=7: usdt_note+=" (riskten kaçış)"
    elif usdt<=5: usdt_note+=" (risk alımı)"
    return f"Piyasa: BTC {dirb} + BTC.D {arrow} (BTC.D {btcd:.1f}%) | Total2: {total2} | USDT.D: {usdt_note}"

# -------- MEXC data
def mexc_symbols():
    d=jget(f"{MEXC}/api/v1/contract/detail")
    if not d or "data" not in d: return []
    return [s["symbol"] for s in d["data"] if s.get("quoteCoin")=="USDT"]

def klines(sym, interval, limit):
    d=jget(f"{MEXC}/api/v1/contract/kline/{sym}",{"interval":interval,"limit":limit})
    if not d or "data" not in d: return None
    return pd.DataFrame(d["data"],columns=["ts","open","high","low","close","volume","turnover"]).astype(
        {"open":"float64","high":"float64","low":"float64","close":"float64","volume":"float64","turnover":"float64"}
    )

def funding(sym):
    d=jget(f"{MEXC}/api/v1/contract/funding_rate",{"symbol":sym})
    try: return float(d["data"]["fundingRate"])
    except: return None

# -------- Core scan per timeframe
def scan_timeframe(sym, tf, cfg):
    """
    cfg = dict(
        interval="1h"/"4h"/"1d", limit=int,
        turnover_min=float,
        gap_pct=float,
        vol_n=int, vol_ratio=float, vol_z=float, vol_ramp=float,
        rsi_buy=float, rsi_sell=float
    )
    """
    df = klines(sym, cfg["interval"], cfg["limit"])
    if df is None or len(df) < cfg["vol_n"]+5: return None, "short"

    # likidite tabanı
    if float(df["turnover"].iloc[-1]) < cfg["turnover_min"]: return None, "lowliq"

    c,h,l = df["close"], df["high"], df["low"]
    if not gap_ok(c, cfg["gap_pct"]): return None, "gap"

    # Trend & RSI (ADX sadece bilgi)
    e20,e50 = ema(c,20).iloc[-1], ema(c,50).iloc[-1]
    trend_up = e20 > e50
    rr = float(rsi(c,14).iloc[-1])
    adx_val = float(adx(pd.DataFrame({"high":h,"low":l,"close":c}),14).iloc[-1])

    v_ok, v = volume_signal(df, cfg["vol_n"], cfg["vol_ratio"], cfg["vol_z"], cfg["vol_ramp"])
    if not v_ok: return None, "novol"

    last_down = float(c.iloc[-1]) < float(c.iloc[-2])

    side = None
    # Hafifletilmiş ama güvenli:
    if trend_up and rr > cfg["rsi_buy"]:
        side = "BUY"
    elif (not trend_up) and rr < cfg["rsi_sell"] and last_down:
        side = "SELL"
    else:
        return None, None

    fr = funding(sym); frtxt=""
    if fr is not None:
        if fr > 0.01: frtxt = f" | Funding:+{fr:.3f}"
        elif fr < -0.01: frtxt = f" | Funding:{fr:.3f}"

    line = (f"{sym} | {tf} | Trend:{'↑' if trend_up else '↓'} | RSI:{rr:.1f} | "
            f"Hacim x{v['ratio']:.2f} z:{v['z']:.2f} ramp:{v['ramp']:.2f} | "
            f"ADX:{adx_val:.0f} | Fiyat:{float(c.iloc[-1])}{frtxt}")
    return (side, line), None

def run_scan(cfg, tf_label):
    syms = mexc_symbols()
    buys, sells = [], []
    skipped = {"short":0,"lowliq":0,"gap":0,"novol":0}
    if not syms: return buys, sells, skipped, "⚠️ MEXC sembol listesi alınamadı."

    for i, s in enumerate(syms):
        try:
            res, flag = scan_timeframe(s, tf_label, cfg)
            if flag in skipped: skipped[flag]+=1
            if res:
                side, line = res
                (buys if side=="BUY" else sells).append(f"- {line}")
        except: pass
        if i % 15 == 0: time.sleep(0.25)
    return buys, sells, skipped, None

def main():
    note = market_note()
    btc1, eth1 = coin_state("BTCUSDT","1h"), coin_state("ETHUSDT","1h")
    btc4, eth4 = coin_state("BTCUSDT","4h"), coin_state("ETHUSDT","4h")
    btcD = f"BTC(1H): {btc1} | BTC(4H): {btc4} | ETH(1H): {eth1} | ETH(4H): {eth4}"

    # Hafifletilmiş ama güvenli eşikler
    CFG_1H = dict(interval="1h", limit=200, turnover_min=400_000, gap_pct=0.08,
                  vol_n=10, vol_ratio=1.10, vol_z=0.8, vol_ramp=1.3, rsi_buy=49.0, rsi_sell=51.0)
    CFG_4H = dict(interval="4h", limit=260, turnover_min=800_000, gap_pct=0.08,
                  vol_n=20, vol_ratio=1.15, vol_z=0.9, vol_ramp=1.4, rsi_buy=50.0, rsi_sell=50.0)
    CFG_1D = dict(interval="1d", limit=400, turnover_min=5_000_000, gap_pct=0.12,
                  vol_n=30, vol_ratio=1.25, vol_z=1.0, vol_ramp=1.5, rsi_buy=55.0, rsi_sell=45.0)

    b1, s1, k1, e1 = run_scan(CFG_1H, "1H")
    b4, s4, k4, e4 = run_scan(CFG_4H, "4H")
    bD, sD, kD, eD = run_scan(CFG_1D, "1D")

    if (not b1 and not s1) and (not b4 and not s4) and (not bD and not sD):
        # Tamamen sessiz: spam atma, sadece logla
        print("No signals across 1H/4H/1D at", ts())
        return

    parts = [f"🧭 *Çoklu Tarama (1H • 4H • 1D)*\n⏱ {ts()}\n{btcD}\n{note}"]

    if b1 or s1:
        parts.append("\n⏰ *1H Sinyaller*")
        if b1: parts += ["🟢 BUY:"] + b1[:20]
        if s1: parts += ["🔴 SELL:"] + s1[:20]
        parts.append(f"Özet(1H): BUY:{len(b1)} | SELL:{len(s1)} | Atl:(liq:{k1['lowliq']}, gap:{k1['gap']}, hacim:{k1['novol']})")
    if b4 or s4:
        parts.append("\n🟣 *4H Sinyaller*")
        if b4: parts += ["🟢 BUY:"] + b4[:20]
        if s4: parts += ["🔴 SELL:"] + s4[:20]
        parts.append(f"Özet(4H): BUY:{len(b4)} | SELL:{len(s4)} | Atl:(liq:{k4['lowliq']}, gap:{k4['gap']}, hacim:{k4['novol']})")
    if bD or sD:
        parts.append("\n🟢 *1D (Günlük) Sinyaller*")
        if bD: parts += ["🟢 BUY:"] + bD[:20]
        if sD: parts += ["🔴 SELL:"] + sD[:20]
        parts.append(f"Özet(1D): BUY:{len(bD)} | SELL:{len(sD)} | Atl:(liq:{kD['lowliq']}, gap:{kD['gap']}, hacim:{kD['novol']})")

    telegram("\n".join(parts))

if __name__ == "__main__":
    main()
