import os, time, requests, pandas as pd
from utils import ts, telegram
from signals import early_alert, safe_confirmation, momentum_continuity, sell_pressure

OKX_BASE = "https://www.okx.com"
TOP_N    = int(os.getenv("TOP_N", "200"))

# özet daha geniş bakabilir, ama eşikler benzer kalsın
VOL_MIN_EARLY  = float(os.getenv("VOL_MIN_EARLY", "200000"))
VOL_MIN_CONF   = float(os.getenv("VOL_MIN_CONF", "300000"))
VRATIO_EARLY   = float(os.getenv("VRATIO_EARLY", "3.2"))
VRATIO_CONF    = float(os.getenv("VRATIO_CONF", "3.7"))
MOM_1M_MIN     = float(os.getenv("MOM_1M_MIN",   "0.0045"))
PULLBACK_MIN   = float(os.getenv("PULLBACK_MIN", "0.0025"))
PULLBACK_MAX   = float(os.getenv("PULLBACK_MAX", "0.0080"))
RSI5_CONF_MIN  = float(os.getenv("RSI5_CONF_MIN","53.0"))
MAX_MSG_COINS  = int(os.getenv("MAX_MSG_COINS", "20"))

def jget(path, params=None, retries=3, timeout=12):
    url = path if path.startswith("http") else OKX_BASE + path
    for _ in range(retries):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            if r.status_code == 200:
                j = r.json()
                if isinstance(j, dict) and j.get("code") == "0":
                    return j.get("data")
        except:
            time.sleep(0.25)
    return None

def okx_top_usdt_spot(limit=TOP_N):
    rows = jget("/api/v5/market/tickers", {"instType":"SPOT"}) or []
    rows = [r for r in rows if str(r.get("instId","")).endswith("-USDT")]
    rows.sort(key=lambda x: float(x.get("volCcy24h","0")), reverse=True)
    return [r["instId"] for r in rows[:limit]]

def kline(instId, bar="1m", limit=60):
    d = jget("/api/v5/market/candles", {"instId":instId, "bar":bar, "limit":limit})
    if not d: return None
    df = pd.DataFrame(d, columns=["ts","o","h","l","c","vol","volCcy","volCcyQuote","confirm"])
    df = df.astype({"o":"float64","h":"float64","l":"float64","c":"float64","vol":"float64","volCcy":"float64"})
    df["turnover"] = df["volCcy"]
    df = df.iloc[::-1].reset_index(drop=True)
    return df

def main():
    symbols = okx_top_usdt_spot()
    if not symbols:
        telegram(f"⛔ {ts()} — Günlük özet için OKX listesi alınamadı.")
        return

    buys, conts = [], []
    sell_count = 0

    for i, inst in enumerate(symbols):
        try:
            df1 = kline(inst, "1m", 60)
            df5 = kline(inst, "5m", 50)
            if df1 is None or df5 is None: continue

            ok_e, _ = early_alert(df1, VOL_MIN_EARLY, VRATIO_EARLY, MOM_1M_MIN)
            if not ok_e: 
                continue

            ok_b, bd = safe_confirmation(df1, df5, VOL_MIN_CONF, VRATIO_EARLY, VRATIO_CONF,
                                         PULLBACK_MIN, PULLBACK_MAX, RSI5_CONF_MIN)
            if ok_b:
                buys.append((bd["score"], f"- {inst} | 🟢 BUY | vR:{bd['v_ratio']:.2f} | Pull:{bd['pull']*100:.2f}% | RSI5:{bd['rsi5']:.1f} | Güven:{bd['score']}"))
            else:
                ok_c, cd = momentum_continuity(df1, df5)
                if ok_c:
                    conts.append((cd["score"], f"- {inst} | 📈 Devam | vR:{cd['v_ratio']:.2f} | RSI5:{cd['rsi5']:.1f} | Güven:{cd['score']}"))

            if sell_pressure(df1, df5):
                sell_count += 1

        except:
            pass
        if (i+1) % 14 == 0:
            time.sleep(0.25)

    buys.sort(key=lambda x: x[0], reverse=True)
    conts.sort(key=lambda x: x[0], reverse=True)

    lines = [f"🗞️ *Günlük Özet — OKX Top-{len(symbols)} (1m/5m)*",
             f"⏱ {ts()}",
             f"📉 SELL baskısı (bilgi): {sell_count}",
             ""]
    if buys:
        lines += ["📈 *Günün En Güçlü BUY Fırsatları*"] + [m for _, m in buys[:MAX_MSG_COINS]] + [""]
    if conts:
        lines += ["⏩ *Momentum Devamı Güçlü Olanlar*"] + [m for _, m in conts[:MAX_MSG_COINS]] + [""]

    if len(lines) <= 4:
        lines.append("_Bugün kayda değer sinyal yoktu._")
    telegram("\n".join(lines))

if __name__ == "__main__":
    main()
