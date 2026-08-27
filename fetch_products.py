#!/usr/bin/env python3
"""
Henter produktkatalogene fra begge Flor-butikkene og skriver dem slanket til data/.

  data/products.json      florworks.no  — norske titler, NOK-priser (kilde for produktsider)
  data/products_se.json   florworks.se  — svenske titler, SEK-priser (overstyrer /se/)

Handles er felles mellom butikkene, så products_se.json brukes som et overlegg:
samme produkt, men navnet og prisen slik en svensk kunde faktisk møter dem.

Kjør før build.py når produkter er lagt til, endret pris eller tatt ut av sortimentet:
    python3 fetch_products.py && python3 build.py
"""
import json, os, urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
KILDER = [
    ("https://florworks.no/products.json?limit=250", "products.json"),
    ("https://florworks.se/products.json?limit=250", "products_se.json"),
]


def slank(p):
    """Kun feltene siden bruker. Produkter uten pris eller bilde hoppes over."""
    variant = (p.get("variants") or [{}])[0]
    bilde = (p.get("images") or [{}])[0].get("src")
    if not variant.get("price") or not bilde:
        return None
    return {"title": p["title"], "handle": p["handle"], "image": bilde,
            "price": variant["price"], "type": p.get("product_type") or ""}


def hent(url):
    req = urllib.request.Request(url, headers={"User-Agent": "floromtaler-build/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    return [q for q in (slank(p) for p in data.get("products", [])) if q]


def main():
    kataloger = {}
    for url, filnavn in KILDER:
        prods = hent(url)
        sti = os.path.join(BASE, "data", filnavn)
        gamle = []
        if os.path.exists(sti):
            with open(sti, encoding="utf-8") as f:
                gamle = json.load(f)
        with open(sti, "w", encoding="utf-8") as f:
            json.dump(sorted(prods, key=lambda p: p["handle"]), f, ensure_ascii=False, indent=1)
            f.write("\n")
        kataloger[filnavn] = {p["handle"] for p in prods}
        borte = {p["handle"] for p in gamle} - kataloger[filnavn]
        nye = kataloger[filnavn] - {p["handle"] for p in gamle}
        print(f"{filnavn}: {len(prods)} produkter"
              + (f" · {len(nye)} nye" if nye else "")
              + (f" · {len(borte)} utgått: {', '.join(sorted(borte))}" if borte else ""))

    mangler = kataloger["products.json"] - kataloger["products_se.json"]
    if mangler:
        print(f"MERK: {len(mangler)} produkter finnes bare på .no — lenkes ikke fra /se/: "
              + ", ".join(sorted(mangler)))


if __name__ == "__main__":
    main()
