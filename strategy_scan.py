import os, time, requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

MEXC_FAPI = "https://contract.mexc.com"
BINANCE_ENDPOINTS = [
    "https://api-gcp.binance.com",
    "https://api1.binance.com",
    "https://api.binance.com",
    "https://api2.binance.com",
    "https://data-api.binance.vision"
]

# ---------- utils ----------
def ts(): return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
def pick_binance():
    for base in BINANCE_ENDPOINTS:
        try:
            r = requests.get(f"{base}/api/v3/time", timeout=5)
            if r.status_code == 200: return base
        except: pass
    return BINANCE_ENDPOINTS[0]
BINANCE = pick_binance()

def jget(url, params=None, retries=3, timeout=12):
    for _ in range(retries):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            if r.status_code == 200: return r.json()
        except: time.sleep(1)
    return None

def telegram(text):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print(text); return
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                      json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"})
    except: pass

# ---------- indicators ----------
def ema(x, n): return x.ewm(span=n, adjust=False).mean()
def rsi(s, n=14):
    d=s.diff(); up=d.clip(lower=0); dn=-d.clip(upper=0)
    rs=up.ewm(alpha=1/n, adjust=False).mean()/(dn.ewm(alpha=1/n, adjust=False).mean()+1e-12)
    return 100-(100/(1+rs))
def macd(s, f=12, m=26, sig=9):
    fast=ema(s,f); slow=ema(s,m); line=fast-slow; signal=line.ewm(span=sig, adjust=False).mean()
    return line, signal, line-signal
def adx(df, n=14):
    up_move=df['high'].diff(); dn_move=-df['low'].diff()
    plus_dm=np.where((up_move>dn_move)&(up_move>0), up_move, 0.0)
    minus_dm=np.where((dn_move>up_move)&(dn_move>0), dn_move, 0.0)
    tr1=df['high']-df['low']
    tr2=(df['high']-df['close'].shift()).abs()
    tr3=(df['low']-df['close'].shift()).abs()
    tr=pd.DataFrame({'a':tr1,'b':tr2,'c':tr3}).max(axis=1)
    atr=tr.ewm(alpha=1/n, adjust=False).mean()
    plus_di=100*pd.Series(plus_dm).ewm(alpha=1/n, adjust=False).mean()/(atr+1e-12)
    minus_di=100*pd.Series(minus_dm).ewm(alpha=1/n, adjust=False).mean()/(atr+1e-12)
    dx=((plus_di-minus_di).abs()/((plus_di+minus_di)+1e-12))*100
    return dx.ewm(alpha=1/n, adjust=False).mean()
def bos_up(df, look=40, excl=2):
    hh=df['high'][:-excl].tail(look).max()
    return df['close'].iloc[-1]>hh
def bos_dn(df, look=40, excl=2):
    ll=df['low'][:-excl].tail(look).min()
    return df['close'].iloc[-1]<ll
def volume_spike(df, n=20, r=1.5):
    if len(df)<n+2: return False, 1.0
    last=df['volume'].iloc[-1]; base=df['volume'].iloc[-(n+1):-1].mean()
    ratio=last/(base+1e-12)
    return ratio>=r, ratio

# ---------- states ----------
def state_coin(symbol):
    d=jget(f"{BINANCE}/api/v3/klines", {"symbol":symbol,"interval":"4h","limit":300})
    if not d: return "NÖTR"
    df=pd.DataFrame(d,columns=["t","o","h","l","c","v","ct","x1","x2","x3","x4","x5"]).astype(float)
    c=df['c']; e20,e50=ema(c,20).iloc[-1], ema(c,50).iloc[-1]; r=rsi(c,14).iloc[-1]
    if e20>e50 and r>50: return "GÜÇLÜ"
    if e20<e50 and r<50: return "ZAYIF"
    return "NÖTR"
def btc_eth_state():
    return state_coin("BTCUSDT"), state_coin("ETHUSDT")
def adaptive_vol_threshold(btc_state, eth_state):
    volatile=("GÜÇLÜ" in [btc_state,eth_state]) or ("ZAYIF" in [btc_state,eth_state])
    return 1.7 if volatile else 1.3

# ---------- data ----------
def mexc_symbols():
    d=jget(f"{MEXC_FAPI}/api/v1/contract/detail")
    if not d or "data" not in d: return []
    return [s["symbol"] for s in d["data"] if s.get("quoteCoin")=="USDT"]
def klines_mexc(sym, interval="4h", limit=260):
    d=jget(f"{MEXC_FAPI}/api/v1/contract/kline/{sym}", {"interval":interval,"limit":limit})
    if not d or "data" not in d: return None
    df=pd.DataFrame(d["data"],columns=["ts","open","high","low","close","volume","turnover"]).astype(
        {"open":"float64","high":"float64","low":"float64","close":"float64","volume":"float64","turnover":"float64"}
    )
    return df

# ---------- analysis ----------
def confidence_score(side, rsi_val, macd_up, adx_val, v_ratio, bos_flag, btc_state, eth_state):
    score=0
    # RSI
    if side=="AL": score+=max(0, min(20, (rsi_val-50)*2))
    if side=="SAT": score+=max(0, min(20, (50-rsi_val)*2))
    # MACD
    score+=20 if macd_up== (side=="AL") else 10
    # ADX
    score+=20 if adx_val>=25 else (10 if adx_val>=15 else 0)
    # Volume
    score+=min(20, (v_ratio-1.0)*20)
    # BTC/ETH uyumu
    if (side=="AL" and ("GÜÇLÜ" in [btc_state,eth_state])) or (side=="SAT" and ("ZAYIF" in [btc_state,eth_state])):
        score+=10
    # BoS
    score+=10 if bos_flag else 5
    return int(min(100, score))

def analyze_symbol(sym, btc_state, eth_state, vol_r):
    df=klines_mexc(sym,"4h",260)
    if df is None or len(df)<120: return None, None

    last_turnover=float(df["turnover"].iloc[-1])
    if last_turnover<1_000_000: return None,"lowliq"

    c=df['close']; h=df['high']; l=df['low']
    e20,e50=ema(c,20).iloc[-1], ema(c,50).iloc[-1]
    trend_up=e20>e50
    r=float(rsi(c,14).iloc[-1])
    m_line,m_sig,_=macd(c)
    macd_up=m_line.iloc[-1]>m_sig.iloc[-1]; macd_dn=not macd_up
    adx_val=float(adx(pd.DataFrame({'high':h,'low':l,'close':c}),14).iloc[-1])
    strong_trend=adx_val>=15
    bosU,bosD=bos_up(df), bos_dn(df)
    v_ok,v_ratio=volume_spike(df,n=20,r=vol_r)
    last_down=float(c.iloc[-1])<float(c.iloc[-2])
    sell_vol_strong=last_down and v_ok

    allow_buy=("ZAYIF" not in [btc_state,eth_state])
    allow_sell=("GÜÇLÜ" not in [btc_state,eth_state])

    side=None
    if allow_buy and trend_up and r>52 and macd_up and strong_trend and (bosU or v_ok):
        side="AL"; bos_flag=bosU
    elif allow_sell and (not trend_up) and r<48 and macd_dn and strong_trend and (bosD or sell_vol_strong):
        side="SAT"; bos_flag=bosD
    if not side: return None,None

    score=confidence_score(side,r,macd_up,adx_val,v_ratio,bos_flag,btc_state,eth_state)
    bos_txt="↑" if bosU else ("↓" if bosD else "-"); trend_txt="↑" if trend_up else "↓"; vol_txt=f"x{v_ratio:.2f}"
    px=float(c.iloc[-1])
    msg=f"✅ {sym} — *{side}* | Trend:{trend_txt} | RSI:{r:.1f} | MACD:{'↑' if macd_up else '↓'} | ADX:{adx_val:.0f} | Hacim {vol_txt} | BoS:{bos_txt} | Fiyat:{px}\n🧭 Güven skoru: {score}/100"
    return msg,None

def main():
    btc_state,eth_state=btc_eth_state()
    vol_r=adaptive_vol_threshold(btc_state,eth_state)
    syms=mexc_symbols()
    if not syms:
        telegram("⚠️ Sembol listesi alınamadı (MEXC)."); return

    header=[f"⏱ {ts()} — *Strateji Taraması* (BTC: {btc_state} | ETH: {eth_state} | HacimEşik: x{vol_r:.1f})"]
    signals=[]; skipped=0
    for i,s in enumerate(syms):
        try:
            res,flag=analyze_symbol(s,btc_state,eth_state,vol_r)
            if flag=="lowliq": skipped+=1
            if res: signals.append(res)
        except: pass
        if i%15==0: time.sleep(0.3)

    if not signals:
        header.append("ℹ️ Şu an kriterlere uyan sinyal yok.")
    else:
        header.extend(signals[:25])
    header.append(f"\n📊 Özet: {len(signals)} sinyal | Düşük likidite nedeniyle atlanan: {skipped}")
    telegram("\n".join(header))

if __name__=="__main__":
    main()
