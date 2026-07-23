#!/usr/bin/env python3
"""
Saner en rå Lipscore-eksport til data/reviews.csv.

Bruk:  python3 import_reviews.py ~/Downloads/export.csv

Beholder KUN feltene siden trenger (dato, navn, rating, tekst, status, produkt,
produkt-URL, offentlig svar). E-post, telefon, ordre-ID-er og andre personfelt
i råeksporten skal ALDRI inn i repoet — denne fila er offentlig.
Dedupliserer identiske rader (navn + dato + produkt + tekst).
"""
import csv, os, sys

KEEP = ["date", "name", "rating", "review", "review_status",
        "product_name", "product_url", "public_reply"]

FORBUDT = {"email", "phone", "internal_order_id", "internal_customer_id"}


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Bruk: python3 import_reviews.py <rå-lipscore-eksport.csv>")
    src = os.path.expanduser(sys.argv[1])
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "reviews.csv")

    with open(src, encoding="utf-8-sig", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        delim = ";" if sample.count(";") > sample.count(",") else ","
        rows = list(csv.DictReader(f, delimiter=delim))
    if not rows:
        raise SystemExit("Tom eksport?")

    mangler = [k for k in ("rating", "review") if k not in rows[0]]
    if mangler:
        raise SystemExit(f"Fant ikke kolonnene {mangler} i eksporten. Kolonner: {list(rows[0])}")

    sett, ut, dupl = set(), [], 0
    for r in rows:
        nokkel = (r.get("name", ""), r.get("date", ""), r.get("product_name", ""), r.get("review", ""))
        if nokkel in sett:
            dupl += 1
            continue
        sett.add(nokkel)
        ut.append({k: (r.get(k) or "").strip() for k in KEEP})

    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=KEEP)
        w.writeheader()
        w.writerows(ut)

    lekk = FORBUDT & set(KEEP)
    assert not lekk, f"Sensitive felt i KEEP: {lekk}"
    print(f"OK: {len(ut)} rader skrevet til data/reviews.csv ({dupl} duplikater fjernet). "
          f"Kjør 'python3 build.py' for å bygge.")


if __name__ == "__main__":
    main()
