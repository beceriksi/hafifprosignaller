import requests, time, json

OKX = "https://www.okx.com"

def test():
    print("🔍 OKX SPOT LİSTE TESTİ BAŞLIYOR...\n")

    try:
        r = requests.get(OKX + "/api/v5/market/tickers", params={"instType":"SPOT"}, timeout=15)
        print("HTTP Status:", r.status_code)
        print("Raw first 300 chars:")
        print(r.text[:300])

        if r.status_code != 200:
            print("\n❌ HTTP ERROR")
            return
        
        j = r.json()
        if not isinstance(j, dict):
            print("\n❌ JSON FORMAT HATALI")
            return
        
        code = j.get("code")
        data = j.get("data")

        print("\ncode:", code)
        if code != "0":
            print("❌ OKX 'code' SUCCESS DEĞİL")
            return

        print("✅ OKX 'code' = 0")
        if not data:
            print("❌ data boş")
            return

        print(f"✅ data bulunuyor ({len(data)} adet ticker)\n")

        # USDT quote filtre
        usdt = [row for row in data if row.get("quoteCcy") == "USDT"]
        print(f"USDT eşleşen coin sayısı: {len(usdt)}")

        if len(usdt) == 0:
            print("❌ USDT filtresi boş — format değişmiş olabilir.")
        else:
            print("✅ USDT filtresi DOĞRU çalışıyor.")
            print("Örnek:", usdt[0])

    except Exception as e:
        print("❌ HATA:", e)

    print("\n✅ TEST BİTTİ")


if __name__ == "__main__":
    test()
