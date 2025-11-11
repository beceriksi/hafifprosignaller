import requests

OKX_BASE = "https://www.okx.com"

def test_list():
    print("🔍 OKX COIN LİSTE TESTİ BAŞLIYOR...")

    url = OKX_BASE + "/api/v5/market/tickers"
    params = {"instType": "SPOT"}

    try:
        r = requests.get(url, params=params, timeout=12)
        print("HTTP Status:", r.status_code)
        if r.status_code != 200:
            print("❌ HTTP hata")
            return
        j = r.json()
    except Exception as e:
        print("❌ İstek hatası:", e)
        return

    print("\nRaw first 300 chars:")
    print(str(j)[:300], "\n")

    # OKX structure: {"code":"0","data":[...]}
    code = j.get("code", None)
    print("code:", code)
    if code != "0":
        print("❌ OKX 'code' ≠ 0 → API hatalı\n")
        return
    print("✅ OKX 'code' = 0")

    data = j.get("data", [])
    if not isinstance(data, list):
        print("❌ data list değil!\n")
        return

    print(f"✅ data bulunuyor ({len(data)} adet ticker)")

    # FILTRELE — USDT quote içerenler (instId formatı: BTC-USDT veya BTC-USDC olabilir)
    usdt = [x for x in data if "USDT" in x.get("instId", "")]
    print("USDT eşleşen coin sayısı:", len(usdt))

    if not usdt:
        print("❌ USDT filtresi boş — OKX instId formatı değişmiş olabilir.")
    else:
        print("✅ USDT filtresi çalışıyor.")

    print("\n✅ TEST BİTTİ")

if __name__ == "__main__":
    test_list()
