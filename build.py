#!/usr/bin/env python3
"""
Floromtaler — statisk generator.
Leser data/reviews.csv (sanert Lipscore-eksport, se import_reviews.py) eller
data/reviews_sample.csv (fallback) + data/products.json (fra florworks.no)
og genererer docs/index.html.

Kjør:  python3 build.py
Output serveres statisk fra docs/ (GitHub Pages / Vercel).
"""
import csv, json, html, math, os, re, shutil, unicodedata
from datetime import datetime, date

BASE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(BASE, "docs")

# ---- lanseringsbrytere -------------------------------------------------------
NOINDEX = True          # sett False ved lansering på eget domene
CANONICAL = None        # f.eks. "https://<domene>/" ved lansering
SITE_TITLE = "Kundeomtaler av Flor arbeidsklær"
SHOP_URL = "https://florworks.no"
SHOP_URL_SE = "https://florworks.se"
UTM = "utm_source=floromtaler&utm_medium=referral&utm_campaign=omtaleside"
WALL_BATCH = 30         # antall omtaler synlig før «Vis flere»

# ---- CSV-kolonnemapping (fleksibel: første treff vinner) ---------------------
COLS = {
    "rating":  ["rating", "score", "stars", "vurdering", "karakter", "votes"],
    "text":    ["review", "review_text", "text", "omtale", "tekst", "body", "content", "comment"],
    "name":    ["name", "display_name", "author", "reviewer", "navn", "kunde", "user_name", "first_name"],
    "date":    ["date", "created_at", "created", "dato", "submitted_at", "time", "review_date"],
    "product": ["product_name", "product", "produkt", "item", "product_title", "internal_product_name"],
    "url":     ["product_url", "url", "produkt_url"],
    "status":  ["review_status", "status"],
    "reply":   ["public_reply", "reply", "svar"],
}

MND = ["januar", "februar", "mars", "april", "mai", "juni", "juli",
       "august", "september", "oktober", "november", "desember"]


def esc(s):
    return html.escape(str(s or "").strip())


def parse_date(raw):
    raw = (raw or "").strip().replace(" UTC", "").replace("T", " ")
    if not raw:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
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


def handle_of(url):
    m = re.search(r"/products/([a-z0-9-]+)", url or "")
    return m.group(1) if m else None


def load_reviews():
    path = os.path.join(BASE, "data", "reviews.csv")
    sample = not os.path.exists(path)
    if sample:
        path = os.path.join(BASE, "data", "reviews_sample.csv")
    with open(path, encoding="utf-8-sig", newline="") as f:
        head = f.read(4096)
        f.seek(0)
        delim = ";" if head.count(";") > head.count(",") else ","
        reader = csv.DictReader(f, delimiter=delim)
        headers = {h.lower().strip(): h for h in (reader.fieldnames or [])}
        colmap = {}
        for field, cands in COLS.items():
            for c in cands:
                if c in headers:
                    colmap[field] = headers[c]
                    break
        missing = [f_ for f_ in ("rating", "text") if f_ not in colmap]
        if missing:
            raise SystemExit(f"FEIL: fant ikke kolonne for {missing} i {os.path.basename(path)}. "
                             f"Kolonner i fila: {reader.fieldnames}. Juster COLS i build.py.")

        def get(r, field):
            col = colmap.get(field)
            return (r.get(col) or "").strip() if col else ""

        votes, dropped = [], 0
        for r in reader:
            status = get(r, "status").lower()
            if status in ("removed", "unpublished", "rejected"):
                dropped += 1
                continue
            try:
                rating = float(get(r, "rating").replace(",", "."))
            except ValueError:
                continue
            if not (1 <= rating <= 5):
                continue
            votes.append({
                "rating": rating,
                "text": get(r, "text"),
                "name": get(r, "name") or "Anonym",
                "date": parse_date(get(r, "date")),
                "product": get(r, "product"),
                "handle": handle_of(get(r, "url")),
                "reply": get(r, "reply"),
            })
    votes.sort(key=lambda x: (x["date"] or date(1970, 1, 1)), reverse=True)
    if dropped:
        print(f"  ({dropped} fjernede/avpubliserte rader holdt utenfor)")
    return votes, sample


def load_products():
    with open(os.path.join(BASE, "data", "products.json"), encoding="utf-8") as f:
        prods = json.load(f)
    by_handle = {p["handle"]: p for p in prods}
    by_title = {norm(p["title"]): p for p in prods}
    return by_handle, by_title


def match_product(r, by_handle, by_title):
    if r["handle"] and r["handle"] in by_handle:
        return by_handle[r["handle"]]
    return by_title.get(norm(r["product"]))


STAR_PATH = 'M10 1.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8L1.5 7.7l5.9-.9z'
STAR_DEFS = ('<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>'
             '<g id="strow">'
             + "".join(f'<path d="{STAR_PATH}" transform="translate({i * 22},0)"/>' for i in range(5))
             + '</g></defs></svg>')


def stars_svg(rating, size=18, label=True):
    """5 stjerner med delvis fyll via delt symbol. Aktiv #A57D85, inaktiv #DFC8CB (Flors Lipscore-farger)."""
    pct = max(0, min(100, rating / 5 * 100))
    lab = f' role="img" aria-label="{str(round(rating, 1)).replace(".", ",")} av 5 stjerner"' if label else ' aria-hidden="true"'
    return (f'<span class="stars"{lab}><svg width="{size * 5.5:.0f}" height="{size}" viewBox="0 0 110 20">'
            f'<use href="#strow" fill="#DFC8CB"/>'
            f'<g clip-path="inset(0 {100 - pct:.1f}% 0 0)"><use href="#strow" fill="#A57D85"/></g></svg></span>')


CHECK_SVG = ('<svg width="12" height="12" viewBox="0 0 16 16" aria-hidden="true">'
             '<path fill="currentColor" d="M8 0a8 8 0 1 0 0 16A8 8 0 0 0 8 0zm3.6 6-4.2 4.6a.9.9 0 0 1-1.3 0L4.4 8.8a.8.8 0 0 1 1.2-1.1l1.2 1.2 3.6-4a.8.8 0 1 1 1.2 1.1z"/></svg>')


def review_card(r, by_handle, by_title, featured=False, hidden=False):
    d = fmt_date(r["date"])
    prod_html = ""
    if r["product"]:
        p = match_product(r, by_handle, by_title)
        if p:
            prod_html = (f'<a class="card-product" href="{SHOP_URL}/products/{p["handle"]}?{UTM}" '
                         f'rel="noopener">{esc(r["product"])}</a>')
        else:
            prod_html = f'<span class="card-product">{esc(r["product"])}</span>'
    reply_html = ""
    if r["reply"]:
        reply_html = (f'<div class="card-reply"><span class="reply-label">Svar fra Flor</span>'
                      f'<p>{esc(r["reply"])}</p></div>')
    search = norm(f'{r["text"]} {r["name"]} {r["product"]}')
    cls = "card featured" if featured else "card"
    if hidden:
        cls += " batch-hidden"
    return (f'<article class="{cls}" data-rating="{int(round(r["rating"]))}" data-search="{esc(search)}">'
            f'<div class="card-top">{stars_svg(r["rating"], 15)}{f"<time>{d}</time>" if d else ""}</div>'
            f'<p class="card-text">{esc(r["text"])}</p>'
            f'{reply_html}'
            f'<footer class="card-foot">'
            f'<div class="card-who"><span class="card-name">{esc(r["name"])}</span>'
            f'<span class="verified" title="Samlet inn via Lipscore fra verifisert kjøp">{CHECK_SVG} Verifisert kjøp</span></div>'
            f'{prod_html}'
            f'</footer></article>')


def breakdown_html(votes):
    n = len(votes) or 1
    teller = {i: 0 for i in (5, 4, 3, 2, 1)}
    for r in votes:
        teller[max(1, min(5, int(round(r["rating"]))))] += 1
    star = (f'<svg width="13" height="13" viewBox="0 0 20 20" aria-hidden="true">'
            f'<path fill="#A57D85" d="{STAR_PATH}"/></svg>')
    rows = []
    for i in (5, 4, 3, 2, 1):
        pct = teller[i] / n * 100
        rows.append(
            f'<button class="brow" data-r="{i}" aria-label="Vis omtaler med {i} stjerner">'
            f'<span class="brow-label">{i} {star}</span>'
            f'<span class="brow-track"><span class="brow-fill" style="width:{pct:.1f}%"></span></span>'
            f'<span class="brow-n">{teller[i]}</span></button>')
    return (f'<div class="breakdown-card"><p class="breakdown-title">Fordeling av {len(votes)} vurderinger</p>'
            + "".join(rows) +
            '<p class="breakdown-note">Trykk på en rad for å lese omtalene.</p></div>')


def product_cards(votes, by_handle, by_title):
    agg = {}
    for r in votes:
        p = match_product(r, by_handle, by_title)
        if not p:
            continue
        a = agg.setdefault(p["handle"], {"sum": 0, "n": 0, "p": p})
        a["sum"] += r["rating"]
        a["n"] += 1
    ranked = sorted([a for a in agg.values() if a["n"] >= 2],
                    key=lambda a: (a["sum"] / a["n"]) * math.log(a["n"] + 1), reverse=True)
    cards = []
    for a in ranked[:4]:
        p, avg = a["p"], a["sum"] / a["n"]
        pris = ""
        if p.get("price"):
            kr = f'{float(p["price"]):,.0f}'.replace(",", " ")
            pris = f'<span class="p-price">{kr} kr</span>'
        cards.append(
            f'<a class="pcard" href="{SHOP_URL}/products/{p["handle"]}?{UTM}" rel="noopener">'
            f'<img src="{p["image"]}&width=480" alt="{esc(p["title"])}" loading="lazy" width="480" height="600">'
            f'<span class="p-title">{esc(p["title"])}</span>'
            f'{stars_svg(avg, 14)}<span class="p-count">{a["n"]} vurdering{"er" if a["n"] != 1 else ""}</span>{pris}'
            f'<span class="p-cta">Se produktet</span></a>')
    return "".join(cards)


def build():
    votes, sample = load_reviews()
    by_handle, by_title = load_products()
    n_votes = len(votes)
    avg = sum(r["rating"] for r in votes) / n_votes if n_votes else 0
    avg_str = str(round(avg, 1)).replace(".", ",")

    cards = [r for r in votes if r["text"]]
    n_cards = len(cards)
    n_stille = n_votes - n_cards

    featured = [r for r in cards if r["rating"] >= 5 and len(r["text"]) >= 80][:6]
    if len(featured) < 6:
        featured = sorted(cards, key=lambda r: (r["rating"], len(r["text"])), reverse=True)[:6]
    feat_html = "".join(review_card(r, by_handle, by_title, featured=True) for r in featured)
    wall_html = "".join(review_card(r, by_handle, by_title, hidden=(i >= WALL_BATCH))
                        for i, r in enumerate(cards))
    prods_html = product_cards(votes, by_handle, by_title)
    breakdown = breakdown_html(votes)

    stille_note = (f' I tillegg har {n_stille} kunder gitt stjernevurdering uten tekst.'
                   if n_stille > 0 else '')

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
                                "ratingCount": n_votes, "reviewCount": n_cards,
                                "bestRating": 5, "worstRating": 1},
        }, ensure_ascii=False) + "</script>")

    oppdatert = fmt_date(date.today())

    html_out = f"""<!DOCTYPE html>
<html lang="nb">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{SITE_TITLE} — {avg_str} av 5 basert på {n_votes} vurderinger</title>
<meta name="description" content="Les {n_cards} kundeomtaler av Flor arbeidsklær for damer. Samlet vurdering {avg_str} av 5 stjerner fra {n_votes} verifiserte kjøp, samlet inn via Lipscore.">
{head_extra}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Jost:wght@400;500&family=Montserrat:wght@400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="style.css">
<link rel="icon" href="favicon.svg" type="image/svg+xml">
{schema}
</head>
<body>
{STAR_DEFS}
{banner}
<header class="site-header">
  <a class="logo" href="#"><img src="assets/logo-white.png" alt="Flor" width="140" height="44"></a>
  <a class="btn btn-outline" href="{SHOP_URL}?{UTM}" rel="noopener">Besøk florworks.no</a>
</header>

<main>
<section class="hero">
  <div class="hero-inner">
    <div class="hero-main">
      <h1>Hva kundene sier om&nbsp;Flor</h1>
      <div class="hero-rating">
        <span class="hero-avg">{avg_str}</span>
        <span class="hero-stars">{stars_svg(avg, 24)}<span class="hero-count">av 5, fra {n_votes} verifiserte kjøp</span></span>
      </div>
      <p class="hero-sub">Omtalene er samlet inn av <strong>Lipscore</strong> fra verifiserte kjøp hos
      <a href="{SHOP_URL}?{UTM}" rel="noopener">florworks.no</a> — nettbutikken til Flor, norsk produsent av arbeidsklær for damer.</p>
      <div class="hero-cta">
        <a class="btn btn-primary" href="{SHOP_URL}?{UTM}" rel="noopener">Se arbeidsklærne</a>
        <a class="btn btn-ghost" href="#alle">Les omtalene</a>
      </div>
    </div>
    {breakdown}
  </div>
</section>

<section class="section">
  <h2>Utvalgte omtaler</h2>
  <p class="section-sub">Automatisk utvalg blant de nyeste omtalene med toppvurdering.</p>
  <div class="masonry m3">{feat_html}</div>
</section>

<section class="section section-beige">
  <h2>Mest omtalte produkter</h2>
  <div class="grid grid-products">{prods_html}</div>
</section>

<section class="section" id="alle">
  <h2>Alle omtaler</h2>
  <p class="section-sub">{n_cards} omtaler med tekst, nyeste først.{stille_note}</p>
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
  <div class="masonry m3" id="vegg">{wall_html}</div>
  <div class="mer-wrap"><button class="btn btn-primary" id="mer">Vis flere omtaler</button></div>
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
      mer = document.getElementById('mer'), merWrap = mer.parentElement,
      BATCH = {WALL_BATCH}, limit = BATCH, aktiv = 'alle';

  function sjekkKlamp() {{
    document.querySelectorAll('.card:not(.klampsjekket)').forEach(function (c) {{
      if (c.offsetParent === null) return;
      c.classList.add('klampsjekket');
      var t = c.querySelector('.card-text');
      if (t && t.scrollHeight > t.clientHeight + 3) {{
        var b = document.createElement('button');
        b.className = 'lesmer';
        b.textContent = 'Les mer';
        b.addEventListener('click', function () {{
          var apen = c.classList.toggle('expanded');
          b.textContent = apen ? 'Vis mindre' : 'Les mer';
        }});
        t.after(b);
      }}
    }});
  }}

  function oppdater() {{
    var q = (sok.value || '').toLowerCase().trim(), treff = 0, vist = 0,
        filtrert = aktiv !== 'alle' || q;
    cards.forEach(function (c) {{
      var ok = (aktiv === 'alle' || c.dataset.rating === aktiv) &&
               (!q || c.dataset.search.indexOf(q) !== -1);
      if (ok) treff++;
      var vis = ok && (filtrert || treff <= limit);
      c.style.display = vis ? '' : 'none';
      if (vis) vist++;
    }});
    merWrap.style.display = (!filtrert && treff > limit) ? '' : 'none';
    status.textContent = filtrert ? 'Viser ' + vist + ' av ' + cards.length + ' omtaler' : '';
    sjekkKlamp();
  }}

  chips.forEach(function (ch) {{
    ch.addEventListener('click', function () {{
      aktiv = ch.dataset.filter;
      chips.forEach(function (o) {{ o.classList.toggle('active', o === ch); o.setAttribute('aria-pressed', o === ch); }});
      oppdater();
    }});
  }});
  sok.addEventListener('input', oppdater);
  mer.addEventListener('click', function () {{ limit += BATCH; oppdater(); }});

  document.querySelectorAll('.brow').forEach(function (b) {{
    b.addEventListener('click', function () {{
      var chip = document.querySelector('.chip[data-filter="' + b.dataset.r + '"]');
      if (chip) chip.click();
      document.getElementById('alle').scrollIntoView({{ behavior: 'smooth' }});
    }});
  }});

  oppdater();
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(sjekkKlamp);
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
    print(f"OK: docs/index.html generert — {n_votes} vurderinger ({n_cards} med tekst), "
          f"snitt {avg_str}/5, modus: {mode}")


if __name__ == "__main__":
    build()
