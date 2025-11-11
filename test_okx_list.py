from main import jget

rows = jget("/api/v5/market/tickers", {"instType":"SPOT"})
print("Toplam kayıt:", len(rows))

rows_sorted = sorted(rows, key=lambda x: float(x.get("volCcy24h","0")), reverse=True)

print("İlk 10 kayıt:")
for r in rows_sorted[:10]:
    print("-", r.get("instId"), "Hacim:", r.get("volCcy24h"))
