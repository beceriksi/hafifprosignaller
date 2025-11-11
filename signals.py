import pandas as pd
import numpy as np

# ----- indikatörler
def ema(x, n): return x.ewm(span=n, adjust=False).mean()

def rsi(s, n=14):
    d = s.diff(); up = d.clip(lower=0); dn = -d.clip(upper=0)
    rs = up.ewm(alpha=1/n, adjust=False).mean() / (dn.ewm(alpha=1/n, adjust=False).mean() + 1e-12)
    return 100 - (100/(1+rs))

# ====== ERKEN UYARI
def early_alert(df1, vol_min_early, vratio_early, mom_1m_min):
    """
    Şartlar:
      - son 1m turnover >= vol_min_early
      - hacim oranı (son 1m / EMA(15m)) >= vratio_early
      - son 1m fiyat değişimi >= mom_1m_min
      - 1m trend: EMA20 > EMA50
    """
    if df1 is None or len(df1) < 50: return False, {}
    t = df1["turnover"]
    if float(t.iloc[-1]) < vol_min_early: return False, {}
    base = ema(t, 15)
    v_ratio = float(t.iloc[-1] / (base.iloc[-2] + 1e-12))
    if v_ratio < vratio_early: return False, {}
    c = df1["c"]; mom = float(c.iloc[-1]/(c.iloc[-2]+1e-12) - 1)
    if mom < mom_1m_min: return False, {}
    e20 = float(ema(c, 20).iloc[-1]); e50 = float(ema(c, 50).iloc[-1])
    if e20 <= e50: return False, {}
    return True, {"v_ratio": v_ratio, "mom": mom}

# ====== GÜVENLİ ONAY (spike→pullback→yeniden kırılım)
def safe_confirmation(df1, df5, vol_min_conf, vratio_early, vratio_conf,
                      pullback_min, pullback_max, rsi5_conf_min):
    if df1 is None or len(df1) < 50: return False, {}
    if df5 is None or len(df5) < 20: return False, {}

    t = df1["turnover"]; c = df1["c"]
    base = ema(t, 15)
    v_now = float(t.iloc[-1] / (base.iloc[-2] + 1e-12))
    v_m1  = float(t.iloc[-2] / (base.iloc[-3] + 1e-12))
    v_m2  = float(t.iloc[-3] / (base.iloc[-4] + 1e-12))
    spikes = []
    for k,vr in [(-3,v_m2),(-2,v_m1),(-1,v_now)]:
        if vr >= vratio_early:
            spikes.append(k)
    if not spikes: return False, {}

    k = spikes[0]
    idx = len(c) + k
    spike_close = float(c.iloc[idx])
    since = c.iloc[idx: -1]
    if len(since) < 1: return False, {}
    min_after = float(since.min())
    pull = (min_after / spike_close) - 1.0
    if not (-pullback_max <= pull <= -pullback_min):
        return False, {}

    max_after = float(since.max())
    if float(c.iloc[-1]) <= max_after:
        return False, {}
    if v_now < vratio_conf:
        return False, {}

    r5 = float(rsi(df5["c"], 14).iloc[-1])
    if r5 < rsi5_conf_min: return False, {}
    e20 = float(ema(c,20).iloc[-1]); e50 = float(ema(c,50).iloc[-1])
    if e20 <= e50: return False, {}
    if float(t.iloc[-1]) < vol_min_conf:
        return False, {}

    mom = float(c.iloc[-1]/(c.iloc[-2]+1e-12) - 1.0)
    score = int(min(100, (v_now*18) + (mom*100) + ((r5-50)*3) + (15 if e20>e50 else 0)))
    return True, {"v_ratio": v_now, "pull": pull, "rsi5": r5, "score": score}

# ====== MOMENTUM DEVAM (pozisyondaysan tutmaya değer mi?)
def momentum_continuity(df1, df5):
    if df1 is None or len(df1) < 40 or df5 is None or len(df5) < 20:
        return False, {}
    c = df1["c"]; t = df1["turnover"]
    r5 = float(rsi(df5["c"], 14).iloc[-1])
    if r5 < 57: return False, {}
    e20 = float(ema(c,20).iloc[-1]); e50 = float(ema(c,50).iloc[-1])
    if e20 <= e50: return False, {}
    base = ema(t, 15)
    v_now = float(t.iloc[-1] / (base.iloc[-2] + 1e-12))
    if v_now < 2.0: return False, {}
    mom = float(c.iloc[-1]/(c.iloc[-2]+1e-12) - 1.0)
    score = int(min(100, (v_now*12) + (mom*100) + ((r5-55)*2) + 10))
    return True, {"v_ratio": v_now, "rsi5": r5, "score": score}

# ====== SELL baskısı (toplu risk ölçümü için)
def sell_pressure(df1, df5):
    if df1 is None or len(df1) < 50 or df5 is None or len(df5) < 20:
        return False
    c = df1["c"]; r5 = float(rsi(df5["c"], 14).iloc[-1])
    e20 = float(ema(c,20).iloc[-1]); e50 = float(ema(c,50).iloc[-1])
    drop3 = float(c.iloc[-1]/(c.iloc[-3]+1e-12) - 1)
    if e20 < e50 and r5 < 45 and drop3 < -0.012:
        return True
    return False
