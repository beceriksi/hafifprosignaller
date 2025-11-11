import requests

OKX_BASE = "https://www.okx.com"

def test_list():
    print("🔍 OKX COIN LİSTE TESTİ BAŞLIYOR...")

    url = OKX_BASE + "/api/v5/market/tickers"
    params = {"instType": "SPOT"}

    try:
        r = requests.get(url, params=params, timeout=10)
        print("HTTP Status:", r.status_code)
        if r.status_code != 200:
            print("❌ HTTP hata")
            return
        j = r.json()
    except Exception as e:
        print("❌ İstek hatası:", e)
        return

    print("Raw first 200 chars:")
    print(str(j)[:200])

    if j.get("code") != "0":
        print("❌ OKX 'code' ≠ 0 → Hata")
        return

    data = j.get("data", [])
    print("Toplam kayıt:", len(data))

    if not data:
        print("❌ Data boş")
        return

    print("Örnek instId:", data[0].get("instId"))

    # ✅ Hacme göre sırala test
    try:
        data_sorted = sorted(data, key=lambda x: float(x.get("volCcy24h", "0")), reverse=True)
        print("✅ İlk 5 coin (hacme göre):")
        for r in data_sorted[:5]:
            print("-", r.get("instId"), r.get("volCcy24h"))
    except:
        print("⚠️ Sıralama başarısız")

    print("✅ TEST BİTTİ")

if __name__ == "__main__":
    test_list()
