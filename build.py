#!/usr/bin/env python3
"""
Floromtaler — statisk generator.
Leser data/reviews.csv (Lipscore-eksport) eller data/reviews_sample.csv (fallback)
+ data/products.json (fra florworks.no) og genererer docs/index.html.

Kjør:  python3 build.py
Output serveres statisk fra docs/ (GitHub Pages / Vercel).
"""
import csv, json, html, math, os, re, shutil, unicodedata
from datetime import datetime, date

BASE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(BASE, "docs")

# ---- lanseringsbrytere -------------------------------------------------------
NOINDEX = True          # sett False ved lansering på eget domene
CANONICAL = None        # f.eks. "https://floromtaler.no/" ved lansering
SITE_TITLE = "Kundeomtaler av Flor arbeidsklær"
SHOP_URL = "https://florworks.no"
SHOP_URL_SE = "https://florworks.se"
UTM = "utm_source=floromtaler&utm_medium=referral&utm_campaign=omtaleside"

# ---- CSV-kolonnemapping (fleksibel: første treff vinner) ---------------------
COLS = {
    "rating":  ["rating", "score", "stars", "vurdering", "karakter", "votes"],
    "text":    ["review_text", "text", "review", "omtale", "tekst", "body", "content", "comment"],
    "name":    ["display_name", "name", "author", "reviewer", "navn", "kunde", "user_name", "first_name"],
    "date":    ["created_at", "date", "created", "dato", "submitted_at", "time", "review_date"],
    "product": ["product_name", "product", "produkt", "item", "product_title", "internal_product_name"],
}

MND = ["januar", "februar", "mars", "april", "mai", "juni", "juli",
       "august", "september", "oktober", "november", "desember"]


def esc(s):
    return html.escape(str(s or "").strip())


def parse_date(raw):
    raw = (raw or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
                "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(raw[:len(fmt) + 6 if "%z" in fmt else len(raw)], fmt).date()
        except ValueError:
            continue
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    return None


def fmt_date(d):
    return f"{d.day}. {MND[d.month - 1]} {d.year}" if d else ""


def norm(s):
    s = unicodedata.normalize("NFKD", (s or "").lower().strip())
    return re.sub(r"\s+", " ", s)


def load_reviews():
    path = os.path.join(BASE, "data", "reviews.csv")
    sample = not os.path.exists(path)
    if sample:
        path = os.path.join(BASE, "data", "reviews_sample.csv")
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = {h.lower().strip(): h for h in (reader.fieldnames or [])}
        colmap = {}
        for field, cands in COLS.items():
            for c in cands:
                if c in headers:
                    colmap[field] = headers[c]
                    break
        missing = [f for f in ("rating", "text") if f not in colmap]
        if missing:
            raise SystemExit(f"FEIL: fant ikke kolonne for {missing} i {os.path.basename(path)}. "
                             f"Kolonner i fila: {reader.fieldnames}. Juster COLS i build.py.")
        rows = []
        for r in reader:
            try:
                rating = float(str(r.get(colmap["rating"], "")).replace(",", "."))
            except ValueError:
                continue
            if not (1 <= rating <= 5):
                continue
            rows.append({
                "rating": rating,
                "text": (r.get(colmap["text"]) or "").strip(),
                "name": (r.get(colmap.get("name", ""), "") or "").strip() or "Anonym",
                "date": parse_date(r.get(colmap.get("date", ""), "")),
                "product": (r.get(colmap.get("product", ""), "") or "").strip(),
            })
    rows.sort(key=lambda x: (x["date"] or date(1970, 1, 1)), reverse=True)
    return rows, sample


def load_products():
    with open(os.path.join(BASE, "data", "products.json"), encoding="utf-8") as f:
        prods = json.load(f)
    return {norm(p["title"]): p for p in prods}


def stars_svg(rating, size=18, label=True):
    """5 stjerner med delvis fyll. Aktiv #A57D85, inaktiv #DFC8CB (Flors Lipscore-farger)."""
    pct = max(0, min(100, rating / 5 * 100))
    lab = f' role="img" aria-label="{str(round(rating, 1)).replace(".", ",")} av 5 stjerner"' if label else ' aria-hidden="true"'
    star = 'M10 1.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8L1.5 7.7l5.9-.9z'
    row = "".join(f'<path d="{star}" transform="translate({i * 22},0)"/>' for i in range(5))
    return (f'<span class="stars"{lab}><svg width="{size * 5.5:.0f}" height="{size}" viewBox="0 0 110 20">'
            f'<g fill="#DFC8CB">{row}</g>'
            f'<g fill="#A57D85" clip-path="inset(0 {100 - pct:.1f}% 0 0)">{row}</g></svg></span>')


def review_card(r, products, featured=False):
    d = fmt_date(r["date"])
    prod_html = ""
    if r["product"]:
        p = products.get(norm(r["product"]))
        if p:
            prod_html = (f'<a class="card-product" href="{SHOP_URL}/products/{p["handle"]}?{UTM}" '
                         f'rel="noopener">{esc(r["product"])}</a>')
        else:
            prod_html = f'<span class="card-product">{esc(r["product"])}</span>'
    search = norm(f'{r["text"]} {r["name"]} {r["product"]}')
    cls = "card featured" if featured else "card"
    return (f'<article class="{cls}" data-rating="{int(round(r["rating"]))}" data-search="{esc(search)}">'
            f'{stars_svg(r["rating"], 16)}'
            f'<p class="card-text">{esc(r["text"])}</p>'
            f'<footer class="card-meta"><span class="card-name">{esc(r["name"])}</span>'
            f'{f"<time>{d}</time>" if d else ""}{prod_html}'
            f'<span class="verified" title="Samlet inn via Lipscore fra verifisert kjøp">Verifisert kjøp</span>'
            f'</footer></article>')


def product_cards(reviews, products):
    agg = {}
    for r in reviews:
        if not r["product"]:
            continue
        key = norm(r["product"])
        if key not in products:
            continue
        a = agg.setdefault(key, {"sum": 0, "n": 0})
        a["sum"] += r["rating"]
        a["n"] += 1
    ranked = sorted(agg.items(), key=lambda kv: (kv[1]["sum"] / kv[1]["n"]) * math.log(kv[1]["n"] + 1), reverse=True)
    cards = []
    for key, a in ranked[:4]:
        p = products[key]
        avg = a["sum"] / a["n"]
        pris = ""
        if p.get("price"):
            kr = f'{float(p["price"]):,.0f}'.replace(",", " ")
            pris = f'<span class="p-price">{kr} kr</span>'
        cards.append(
            f'<a class="pcard" href="{SHOP_URL}/products/{p["handle"]}?{UTM}" rel="noopener">'
            f'<img src="{p["image"]}&width=480" alt="{esc(p["title"])}" loading="lazy" width="480" height="600">'
            f'<span class="p-title">{esc(p["title"])}</span>'
            f'{stars_svg(avg, 14)}<span class="p-count">{a["n"]} omtale{"r" if a["n"] != 1 else ""}</span>{pris}'
            f'<span class="p-cta">Se produktet</span></a>')
    return "".join(cards)


def build():
    reviews, sample = load_reviews()
    products = load_products()
    n = len(reviews)
    avg = sum(r["rating"] for r in reviews) / n if n else 0
    avg_str = str(round(avg, 1)).replace(".", ",")

    featured = sorted([r for r in reviews if len(r["text"]) >= 60],
                      key=lambda r: (r["rating"], len(r["text"])), reverse=True)[:6]
    feat_html = "".join(review_card(r, products, featured=True) for r in featured)
    wall_html = "".join(review_card(r, products) for r in reviews)
    prods_html = product_cards(reviews, products)

    banner = ""
    if sample:
        banner = ('<div class="preview-banner" role="status">Forhåndsvisning med eksempeldata — '
                  'ekte kundeomtaler fra Lipscore legges inn før lansering.</div>')

    head_extra = '<meta name="robots" content="noindex">' if (NOINDEX or sample) else ""
    if CANONICAL and not sample:
        head_extra += f'<link rel="canonical" href="{CANONICAL}">'

    schema = ""
    if not sample:
        schema = ('<script type="application/ld+json">' + json.dumps({
            "@context": "https://schema.org",
            "@type": "OnlineStore",
            "name": "Flor",
            "legalName": "Flor AS",
            "url": SHOP_URL,
            "logo": f"{SHOP_URL}/cdn/shop/files/Logo-white-400.png",
            "address": {"@type": "PostalAddress", "streetAddress": "Vangsgata 39",
                        "postalCode": "5700", "addressLocality": "Voss", "addressCountry": "NO"},
            "aggregateRating": {"@type": "AggregateRating", "ratingValue": round(avg, 2),
                                "reviewCount": n, "bestRating": 5, "worstRating": 1},
        }, ensure_ascii=False) + "</script>")

    oppdatert = fmt_date(date.today())

    html_out = f"""<!DOCTYPE html>
<html lang="nb">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{SITE_TITLE} — {avg_str} av 5 fra {n} kunder</title>
<meta name="description" content="Les {n} kundeomtaler av Flor arbeidsklær for damer. Samlet vurdering {avg_str} av 5 stjerner, samlet inn via Lipscore fra verifiserte kjøp.">
{head_extra}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Jost:wght@400;500&family=Montserrat:wght@400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="style.css">
<link rel="icon" href="favicon.svg" type="image/svg+xml">
{schema}
</head>
<body>
{banner}
<header class="site-header">
  <a class="logo" href="#"><img src="assets/logo-white.png" alt="Flor" width="140" height="44"></a>
  <a class="btn btn-outline" href="{SHOP_URL}?{UTM}" rel="noopener">Besøk florworks.no</a>
</header>

<main>
<section class="hero">
  <h1>Hva kundene sier om&nbsp;Flor</h1>
  <div class="hero-rating">
    <span class="hero-avg">{avg_str}</span>
    {stars_svg(avg, 26)}
    <span class="hero-count">av 5, basert på {n} omtaler</span>
  </div>
  <p class="hero-sub">Omtalene er samlet inn av <strong>Lipscore</strong> fra verifiserte kjøp hos
  <a href="{SHOP_URL}?{UTM}" rel="noopener">florworks.no</a> — nettbutikken til Flor, norsk produsent av arbeidsklær for damer.</p>
  <a class="btn btn-primary" href="{SHOP_URL}?{UTM}" rel="noopener">Se arbeidsklærne</a>
</section>

<section class="section">
  <h2>Utvalgte omtaler</h2>
  <p class="section-sub">Automatisk utvalg blant de best vurderte omtalene.</p>
  <div class="grid grid-featured">{feat_html}</div>
</section>

<section class="section section-beige">
  <h2>Mest omtalte produkter</h2>
  <div class="grid grid-products">{prods_html}</div>
</section>

<section class="section" id="alle">
  <h2>Alle omtaler</h2>
  <div class="filters" role="group" aria-label="Filtrer omtaler">
    <button class="chip active" data-filter="alle" aria-pressed="true">Alle</button>
    <button class="chip" data-filter="5" aria-pressed="false">5 stjerner</button>
    <button class="chip" data-filter="4" aria-pressed="false">4 stjerner</button>
    <button class="chip" data-filter="3" aria-pressed="false">3 stjerner</button>
    <button class="chip" data-filter="2" aria-pressed="false">2 stjerner</button>
    <button class="chip" data-filter="1" aria-pressed="false">1 stjerne</button>
    <input type="search" id="sok" placeholder="Søk i omtaler …" aria-label="Søk i omtaler">
  </div>
  <p class="filter-status" id="status" aria-live="polite"></p>
  <div class="grid grid-wall" id="vegg">{wall_html}</div>
</section>

<section class="section section-beige">
  <h2>Om Flor</h2>
  <div class="about">
    <p>Flor er en norsk produsent av <strong>arbeidsklær for damer</strong>, med base i Voss.
    Plaggene er slitesterke, behagelige og laget for kvinner i alle slags yrker — fra fjøs og hage
    til barnehage og verksted. Nettbutikken finner du på
    <a href="{SHOP_URL}?{UTM}" rel="noopener">florworks.no</a>
    (og <a href="{SHOP_URL_SE}?{UTM}" rel="noopener">florworks.se</a> i Sverige).</p>
    <ul class="trust">
      <li>Fri frakt på kjøp over 1 999 kr</li>
      <li>Gratis bytte av varer</li>
      <li>14 dagers angrerett på alle nettkjøp</li>
      <li>Omtaler fra verifiserte kjøp via Lipscore</li>
    </ul>
  </div>
</section>

<section class="section">
  <h2>Ofte stilte spørsmål</h2>
  <details><summary>Er det trygt å handle hos Flor?</summary>
  <p>Ja. Flor AS er et norsk selskap (org.nr. 918 377 573) med adresse i Voss, og har solgt arbeidsklær
  på nett i en årrekke. Omtalene på denne siden samles inn av tredjeparten Lipscore og kommer fra
  verifiserte kjøp i nettbutikken.</p></details>
  <details><summary>Hva koster frakten?</summary>
  <p>Fri frakt på kjøp over 1 999 kr. Under det koster PostNord Pakkeboks 99 kr, PostNord hentested
  149 kr og Bring hentested 169 kr.</p></details>
  <details><summary>Kan jeg bytte om størrelsen ikke passer?</summary>
  <p>Ja, Flor har fri frakt ved bytte av varer. Du registrerer byttet i et skjema i nettbutikken og får
  fraktetikett tilsendt på e-post. Plagget må være ubrukt med merkelapper intakt.</p></details>
  <details><summary>Hva med retur og angrerett?</summary>
  <p>Du har 14 dagers ubetinget angrerett fra den dagen du mottar varen. Ved retur trekkes
  returfrakt på 149 kr fra beløpet som refunderes.</p></details>
  <details><summary>Hvordan finner jeg riktig størrelse?</summary>
  <p>Hvert produkt har eget størrelsesskjema. Er du usikker, hjelper Flor deg på
  <a href="mailto:kontakt@florworks.no">kontakt@florworks.no</a>.</p></details>
</section>
</main>

<footer class="site-footer">
  <p><strong>Denne siden driftes av Flor AS</strong> (org.nr. 918 377 573, Vangsgata 39, 5700 Voss) og viser
  kundeomtaler av nettbutikken florworks.no. Omtalene samles inn av
  <a href="https://www.lipscore.com" rel="noopener">Lipscore</a> fra verifiserte kjøp og gjengis uredigert.</p>
  <nav><a href="{SHOP_URL}?{UTM}" rel="noopener">florworks.no</a> ·
  <a href="{SHOP_URL_SE}?{UTM}" rel="noopener">florworks.se</a> ·
  <a href="mailto:kontakt@florworks.no">kontakt@florworks.no</a></nav>
  <p class="updated">Sist oppdatert {oppdatert}</p>
</footer>

<script>
(function () {{
  var chips = document.querySelectorAll('.chip'), sok = document.getElementById('sok'),
      cards = document.querySelectorAll('#vegg .card'), status = document.getElementById('status'),
      aktiv = 'alle';
  function oppdater() {{
    var q = (sok.value || '').toLowerCase().trim(), vist = 0;
    cards.forEach(function (c) {{
      var ok = (aktiv === 'alle' || c.dataset.rating === aktiv) &&
               (!q || c.dataset.search.indexOf(q) !== -1);
      c.style.display = ok ? '' : 'none';
      if (ok) vist++;
    }});
    status.textContent = vist === cards.length ? '' : 'Viser ' + vist + ' av ' + cards.length + ' omtaler';
  }}
  chips.forEach(function (ch) {{
    ch.addEventListener('click', function () {{
      aktiv = ch.dataset.filter;
      chips.forEach(function (o) {{ o.classList.toggle('active', o === ch); o.setAttribute('aria-pressed', o === ch); }});
      oppdater();
    }});
  }});
  sok.addEventListener('input', oppdater);
}})();
</script>
</body>
</html>"""

    os.makedirs(DOCS, exist_ok=True)
    os.makedirs(os.path.join(DOCS, "assets"), exist_ok=True)
    with open(os.path.join(DOCS, "index.html"), "w", encoding="utf-8") as f:
        f.write(html_out)
    shutil.copy(os.path.join(BASE, "src", "style.css"), os.path.join(DOCS, "style.css"))
    shutil.copy(os.path.join(BASE, "assets", "logo-white.png"), os.path.join(DOCS, "assets", "logo-white.png"))
    shutil.copy(os.path.join(BASE, "src", "favicon.svg"), os.path.join(DOCS, "favicon.svg"))
    open(os.path.join(DOCS, ".nojekyll"), "w").close()
    mode = "SAMPLE (forhåndsvisning)" if sample else "PRODUKSJON"
    print(f"OK: docs/index.html generert — {n} omtaler, snitt {avg_str}/5, modus: {mode}")


if __name__ == "__main__":
    build()
