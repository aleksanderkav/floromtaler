#!/usr/bin/env python3
"""
Floromtaler — statisk generator (flerside, nb + sv).
Leser data/reviews.csv (sanert Lipscore-eksport, se import_reviews.py) eller
data/reviews_sample.csv (fallback) + data/products.json (fra florworks.no) og genererer:

  docs/index.html                 forsiden (norsk hub)
  docs/se/index.html              svensk forside (hreflang-alternativ, lenker til florworks.se)
  docs/<slug>/index.html          per-produkt omtaleside (>= MIN_PRODUCT_REVIEWS tekstomtaler)
  docs/beste-arbeidsbukse-dame/   temaside rangert på ekte omtaledata
  docs/sitemap.xml, robots.txt    crawl-oppsett (åpen for AI-crawlere)
  docs/llms.txt, llms-full.txt    AI-lesbart sammendrag + alle omtaler i ren tekst
  docs/<indexnow-key>.txt         IndexNow-nøkkelfil (ping ved lansering)

Kjør:  python3 build.py
Output serveres statisk fra docs/. Alle lenker er relative så siden virker både på
rot-domene (Vercel/eget domene) og underkatalog (GitHub Pages).
"""
import csv, json, html, math, os, re, secrets, shutil, unicodedata
from datetime import datetime, date

BASE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(BASE, "docs")

# ---- lanseringsbrytere -------------------------------------------------------
NOINDEX = True          # sett False ved lansering på eget domene
BASE_URL = "https://floromtaler.vercel.app"   # byttes til eget domene ved lansering
SITE_TITLE = "Kundeomtaler av Flor arbeidsklær"
SHOP_URL = "https://florworks.no"
SHOP_URL_SE = "https://florworks.se"
UTM = "utm_source=floromtaler&utm_medium=referral&utm_campaign=omtaleside"
WALL_BATCH = 30         # antall omtaler synlig på forsiden før «Vis flere»
MIN_PRODUCT_REVIEWS = 5 # tekstomtaler som kreves for egen produktside
THEME_SLUG = "beste-arbeidsbukse-dame"

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

# ---- språk -------------------------------------------------------------------

L_NB = {
    "lang": "nb",
    "months": ["januar", "februar", "mars", "april", "mai", "juni", "juli",
               "august", "september", "oktober", "november", "desember"],
    "of5": "av 5 stjerner",
    "verified": "Verifisert kjøp",
    "reply_label": "Svar fra Flor",
    "service_label": "Butikkomtale",
    "read_more": "Les mer",
    "read_less": "Vis mindre",
    "dist_title": "Fordeling av {n} vurderinger",
    "dist_note": "Trykk på en rad for å lese omtalene.",
    "visit_shop": "Besøk florworks.no",
    "h1": "Hva kundene sier om&nbsp;Flor",
    "hero_count": "av 5, fra {n} verifiserte kjøp",
    "hero_sub": ('Omtalene er samlet inn av <strong>Lipscore</strong> fra verifiserte kjøp hos '
                 '<a href="{shop}?{utm}" rel="noopener">florworks.no</a> — nettbutikken til Flor, '
                 'norsk produsent av arbeidsklær for damer.'),
    "cta_shop": "Se arbeidsklærne",
    "cta_reviews": "Les omtalene",
    "featured_h2": "Utvalgte omtaler",
    "featured_sub": "Automatisk utvalg blant de nyeste omtalene med toppvurdering.",
    "see_all": "Se alle omtalene",
    "products_h2": "Mest omtalte produkter",
    "ratings_word": "vurdering|vurderinger",
    "see_product": "Se produktet",
    "read_all_fmt": "Les alle {n} omtalene →",
    "wall_h2": "Alle omtaler",
    "wall_sub": "{n} omtaler med tekst, nyeste først.",
    "wall_silent": " I tillegg har {n} kunder gitt stjernevurdering uten tekst.",
    "orig_note": "",
    "chip_all": "Alle",
    "chip_star": "{n} stjerner",
    "chip_star1": "1 stjerne",
    "search_ph": "Søk i omtaler …",
    "search_aria": "Søk i omtaler",
    "filter_aria": "Filtrer omtaler",
    "showing": ["Viser ", " av ", " omtaler"],
    "show_more": "Vis flere omtaler",
    "about_h2": "Om Flor",
    "about_html": ('<p>Flor er en norsk produsent av <strong>arbeidsklær for damer</strong>, med base i Voss. '
                   'Plaggene er slitesterke, behagelige og laget for kvinner i alle slags yrker — fra fjøs og '
                   'hage til barnehage og verksted. Nettbutikken finner du på '
                   '<a href="{shop}?{utm}" rel="noopener">florworks.no</a> '
                   '(og <a href="{shop2}?{utm}" rel="noopener">florworks.se</a> i Sverige).</p>'),
    "trust": ["Fri frakt på kjøp over 1 999 kr", "Gratis bytte av varer",
              "14 dagers angrerett på alle nettkjøp", "Omtaler fra verifiserte kjøp via Lipscore"],
    "faq_h2": "Ofte stilte spørsmål",
    "faq": [
        ("Er det trygt å handle hos Flor?",
         "Ja. Flor AS er et norsk selskap (org.nr. 918 377 573) med adresse i Voss, og har solgt arbeidsklær "
         "på nett i en årrekke. Omtalene på denne siden samles inn av tredjeparten Lipscore og kommer fra "
         "verifiserte kjøp i nettbutikken."),
        ("Hva koster frakten?",
         "Fri frakt på kjøp over 1 999 kr. Under det koster PostNord Pakkeboks 99 kr, PostNord hentested "
         "149 kr og Bring hentested 169 kr."),
        ("Kan jeg bytte om størrelsen ikke passer?",
         "Ja, Flor har fri frakt ved bytte av varer. Du registrerer byttet i et skjema i nettbutikken og får "
         "fraktetikett tilsendt på e-post. Plagget må være ubrukt med merkelapper intakt."),
        ("Hva med retur og angrerett?",
         "Du har 14 dagers ubetinget angrerett fra den dagen du mottar varen. Ved retur trekkes "
         "returfrakt på 149 kr fra beløpet som refunderes."),
        ("Hvordan finner jeg riktig størrelse?",
         "Hvert produkt har eget størrelsesskjema. Er du usikker, hjelper Flor deg på kontakt@florworks.no."),
    ],
    "footer_html": ('<p><strong>Denne siden driftes av Flor AS</strong> (org.nr. 918 377 573, Vangsgata 39, '
                    '5700 Voss) og viser kundeomtaler av nettbutikken florworks.no. Omtalene samles inn av '
                    '<a href="https://www.lipscore.com" rel="noopener">Lipscore</a> fra verifiserte kjøp og '
                    'gjengis uredigert.</p>'),
    "updated": "Sist oppdatert",
    "lang_switch": '<a class="lang-link" href="se/" hreflang="sv">Svenska</a>',
}

L_SV = {
    "lang": "sv",
    "months": ["januari", "februari", "mars", "april", "maj", "juni", "juli",
               "augusti", "september", "oktober", "november", "december"],
    "of5": "av 5 stjärnor",
    "verified": "Verifierat köp",
    "reply_label": "Svar från Flor",
    "service_label": "Butiksrecension",
    "read_more": "Läs mer",
    "read_less": "Visa mindre",
    "dist_title": "Fördelning av {n} betyg",
    "dist_note": "Klicka på en rad för att läsa recensionerna.",
    "visit_shop": "Besök florworks.se",
    "h1": "Vad kunderna säger om&nbsp;Flor",
    "hero_count": "av 5, från {n} verifierade köp",
    "hero_sub": ('Recensionerna samlas in av <strong>Lipscore</strong> från verifierade köp hos Flor — '
                 'norsk tillverkare av arbetskläder för damer. Svenska webbutiken hittar du på '
                 '<a href="{shop}?{utm}" rel="noopener">florworks.se</a>.'),
    "cta_shop": "Se arbetskläderna",
    "cta_reviews": "Läs recensionerna",
    "featured_h2": "Utvalda recensioner",
    "featured_sub": "Automatiskt urval bland de senaste recensionerna med toppbetyg.",
    "see_all": "Se alla recensioner",
    "products_h2": "Mest recenserade produkter",
    "ratings_word": "betyg|betyg",
    "see_product": "Se produkten",
    "read_all_fmt": "",
    "wall_h2": "Alla recensioner",
    "wall_sub": "{n} recensioner med text, senaste först.",
    "wall_silent": " Dessutom har {n} kunder lämnat stjärnbetyg utan text.",
    "orig_note": " Recensionerna visas på originalspråket (norska).",
    "chip_all": "Alla",
    "chip_star": "{n} stjärnor",
    "chip_star1": "1 stjärna",
    "search_ph": "Sök i recensioner …",
    "search_aria": "Sök i recensioner",
    "filter_aria": "Filtrera recensioner",
    "showing": ["Visar ", " av ", " recensioner"],
    "show_more": "Visa fler recensioner",
    "about_h2": "Om Flor",
    "about_html": ('<p>Flor är en norsk tillverkare av <strong>arbetskläder för damer</strong>, med bas i Voss. '
                   'Plaggen är slitstarka, bekväma och gjorda för kvinnor i alla slags yrken — från ladugård och '
                   'trädgård till förskola och verkstad. Den svenska webbutiken hittar du på '
                   '<a href="{shop}?{utm}" rel="noopener">florworks.se</a> '
                   '(och <a href="{shop2}?{utm}" rel="noopener">florworks.no</a> i Norge).</p>'),
    "trust": ["Fri frakt vid köp över 1 000 kr (startkampanj)", "Byte och retur via kontakt@florworks.no",
              "14 dagars ångerrätt enligt lag", "Recensioner från verifierade köp via Lipscore"],
    "faq_h2": "Vanliga frågor",
    "faq": [
        ("Är det tryggt att handla hos Flor?",
         "Ja. Flor AS är ett norskt företag (org.nr 918 377 573) med adress i Voss, och har sålt arbetskläder "
         "på nätet i många år. Recensionerna på den här sidan samlas in av tredje parten Lipscore och kommer "
         "från verifierade köp i webbutiken."),
        ("Vad kostar frakten till Sverige?",
         "Fri frakt vid köp över 1 000 kr (startkampanj). För ordrar under 1 000 kr är fraktkostnaden 199 kr."),
        ("Kan jag byta om storleken inte passar?",
         "Ja. Skicka ett e-postmeddelande till kontakt@florworks.no med ordernummer, namnet på beställningen "
         "och vilket plagg det gäller. Plagget ska vara oanvänt med etiketter kvar."),
        ("Vad gäller för retur och ångerrätt?",
         "Du har 14 dagars ångerrätt enligt lag. Kontakta kontakt@florworks.no så hjälper Flor dig med returen."),
        ("Hur hittar jag rätt storlek?",
         "Varje produkt har en egen storleksguide. Är du osäker hjälper Flor dig på kontakt@florworks.no."),
    ],
    "footer_html": ('<p><strong>Den här sidan drivs av Flor AS</strong> (org.nr 918 377 573, Vangsgata 39, '
                    '5700 Voss, Norge) och visar kundrecensioner av webbutiken florworks.se/florworks.no. '
                    'Recensionerna samlas in av <a href="https://www.lipscore.com" rel="noopener">Lipscore</a> '
                    'från verifierade köp och återges oredigerade.</p>'),
    "updated": "Senast uppdaterad",
    "lang_switch": '<a class="lang-link" href="../" hreflang="nb">Norsk</a>',
}

CUR = L_NB


def set_lang(L):
    global CUR
    CUR = L


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
    return f"{d.day}. {CUR['months'][d.month - 1]} {d.year}" if d else ""


def no_num(x, nd=1):
    return str(round(x, nd)).replace(".", ",")


def norm(s):
    s = unicodedata.normalize("NFKD", (s or "").lower().strip())
    return re.sub(r"\s+", " ", s)


def handle_of(url):
    m = re.search(r"/products/([a-z0-9-]+)", url or "")
    return m.group(1) if m else None


def is_service(r):
    return norm(r["product"]) in ("service reviews", "service review")


# ---- data --------------------------------------------------------------------

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


def slug_of(handle, opptatt):
    """URL-slug uten Shopifys årsprefiks; faller tilbake til full handle ved kollisjon."""
    slug = re.sub(r"^(19|20)\d{2}-", "", handle)
    return slug if slug not in opptatt else handle


def product_pages_data(votes, by_handle):
    """Handles som fortjener egen side: >= MIN_PRODUCT_REVIEWS tekstomtaler og finnes i products.json."""
    per = {}
    for r in votes:
        if r["handle"] and r["handle"] in by_handle:
            per.setdefault(r["handle"], []).append(r)
    sider, opptatt = {}, {THEME_SLUG, "se"}
    for h in sorted(per):
        rs = per[h]
        tekster = [r for r in rs if r["text"]]
        if len(tekster) >= MIN_PRODUCT_REVIEWS:
            slug = slug_of(h, opptatt)
            opptatt.add(slug)
            sider[h] = {"votes": rs, "texts": tekster, "p": by_handle[h], "slug": slug}
    return sider


# ---- byggeklosser ------------------------------------------------------------

STAR_PATH = 'M10 1.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8L1.5 7.7l5.9-.9z'
STAR_DEFS = ('<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>'
             '<g id="strow">'
             + "".join(f'<path d="{STAR_PATH}" transform="translate({i * 22},0)"/>' for i in range(5))
             + '</g></defs></svg>')

CHECK_SVG = ('<svg width="12" height="12" viewBox="0 0 16 16" aria-hidden="true">'
             '<path fill="currentColor" d="M8 0a8 8 0 1 0 0 16A8 8 0 0 0 8 0zm3.6 6-4.2 4.6a.9.9 0 0 1-1.3 0L4.4 8.8a.8.8 0 0 1 1.2-1.1l1.2 1.2 3.6-4a.8.8 0 1 1 1.2 1.1z"/></svg>')


def stars_svg(rating, size=18, label=True):
    """5 stjerner med delvis fyll via delt symbol. Aktiv #A57D85, inaktiv #DFC8CB (Flors Lipscore-farger)."""
    pct = max(0, min(100, rating / 5 * 100))
    lab = f' role="img" aria-label="{no_num(rating)} {CUR["of5"]}"' if label else ' aria-hidden="true"'
    return (f'<span class="stars"{lab}><svg width="{size * 5.5:.0f}" height="{size}" viewBox="0 0 110 20">'
            f'<use href="#strow" fill="#DFC8CB"/>'
            f'<g clip-path="inset(0 {100 - pct:.1f}% 0 0)"><use href="#strow" fill="#A57D85"/></g></svg></span>')


def review_card(r, resolve_link, featured=False, hidden=False, show_product=True):
    """resolve_link(r) -> (href, is_internal) eller None for ren tekstetikett."""
    d = fmt_date(r["date"])
    prod_html = ""
    if show_product:
        if is_service(r):
            prod_html = f'<span class="card-product">{CUR["service_label"]}</span>'
        elif r["product"]:
            lenke = resolve_link(r)
            if lenke:
                href, internal = lenke
                rel = "" if internal else ' rel="noopener"'
                prod_html = f'<a class="card-product" href="{href}"{rel}>{esc(r["product"])}</a>'
            else:
                prod_html = f'<span class="card-product">{esc(r["product"])}</span>'
    reply_html = ""
    if r["reply"]:
        reply_html = (f'<div class="card-reply"><span class="reply-label">{CUR["reply_label"]}</span>'
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
            f'<span class="verified" title="Lipscore">{CHECK_SVG} {CUR["verified"]}</span></div>'
            f'{prod_html}'
            f'</footer></article>')


def est_card_height(r):
    """Grovt høydeestimat i px for kolonnebalansering (16px Jost, ~42 tegn/linje, klamp 8 linjer)."""
    lines = min(8, max(1, math.ceil(len(r["text"]) / 42)))
    h = 150 + lines * 25
    if r["reply"]:
        h += 45 + math.ceil(len(r["reply"]) / 45) * 21
    if r["product"]:
        h += 26
    return h


def featured_columns(featured, resolve_link):
    """Fordel utvalgte kort i 3 kolonner etter estimert høyde (LPT: høyeste først,
    alltid i den korteste kolonnen) så bunnkantene blir tilnærmet jevne."""
    items = sorted(featured, key=est_card_height, reverse=True)
    cols, heights = [[] for _ in range(3)], [0.0] * 3
    for r in items:
        i = heights.index(min(heights))
        cols[i].append(r)
        heights[i] += est_card_height(r)
    return "".join(
        '<div class="fcol">' + "".join(review_card(r, resolve_link, featured=True) for r in col) + '</div>'
        for col in cols)


def rating_counts(votes):
    teller = {i: 0 for i in (5, 4, 3, 2, 1)}
    for r in votes:
        teller[max(1, min(5, int(round(r["rating"]))))] += 1
    return teller


def breakdown_html(votes, clickable=True):
    n = len(votes) or 1
    teller = rating_counts(votes)
    star = (f'<svg width="13" height="13" viewBox="0 0 20 20" aria-hidden="true">'
            f'<path fill="#A57D85" d="{STAR_PATH}"/></svg>')
    rows = []
    for i in (5, 4, 3, 2, 1):
        pct = teller[i] / n * 100
        indre = (f'<span class="brow-label">{i} {star}</span>'
                 f'<span class="brow-track"><span class="brow-fill" style="width:{pct:.1f}%"></span></span>'
                 f'<span class="brow-n">{teller[i]}</span>')
        if clickable:
            rows.append(f'<button class="brow" data-r="{i}">{indre}</button>')
        else:
            rows.append(f'<div class="brow brow-static">{indre}</div>')
    note = f'<p class="breakdown-note">{CUR["dist_note"]}</p>' if clickable else ''
    return (f'<div class="breakdown-card"><p class="breakdown-title">{CUR["dist_title"].format(n=len(votes))}</p>'
            + "".join(rows) + note + '</div>')


def klamp_js():
    return """
  function sjekkKlamp(rot) {
    document.querySelectorAll(rot + ' .card:not(.klampsjekket)').forEach(function (c) {
      if (c.offsetParent === null) return;
      c.classList.add('klampsjekket');
      var t = c.querySelector('.card-text');
      if (t && t.scrollHeight > t.clientHeight + 3) {
        var b = document.createElement('button');
        b.className = 'lesmer';
        b.textContent = '""" + CUR["read_more"] + """';
        b.addEventListener('click', function () {
          var apen = c.classList.toggle('expanded');
          b.textContent = apen ? '""" + CUR["read_less"] + """' : '""" + CUR["read_more"] + """';
        });
        t.after(b);
      }
    });
  }"""


def page_shell(*, title, desc, path, body, prefix="", schema="", og_image=None, sample=False,
               alternates=None, shop_href=None, nav_extra=""):
    """Felles HTML-skall. path er URL-stien relativt til rot ('' for forsiden, 'slug/' for underside)."""
    head_extra = '<meta name="robots" content="noindex">' if (NOINDEX or sample) else ""
    if not NOINDEX and not sample:
        head_extra += f'<link rel="canonical" href="{BASE_URL}/{path}">'
    for hl, url in (alternates or []):
        head_extra += f'<link rel="alternate" hreflang="{hl}" href="{url}">'
    og = (f'<meta property="og:title" content="{esc(title)}">'
          f'<meta property="og:description" content="{esc(desc)}">'
          f'<meta property="og:type" content="website">'
          f'<meta property="og:url" content="{BASE_URL}/{path}">')
    if og_image:
        og += f'<meta property="og:image" content="{og_image}">'
    banner = ""
    if sample:
        banner = ('<div class="preview-banner" role="status">Forhåndsvisning med eksempeldata — '
                  'ekte kundeomtaler fra Lipscore legges inn før lansering.</div>')
    shop_href = shop_href or f"{SHOP_URL}?{UTM}"
    oppdatert = fmt_date(date.today())
    return f"""<!DOCTYPE html>
<html lang="{CUR['lang']}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
{head_extra}
{og}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Jost:wght@400;500&family=Montserrat:wght@400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{prefix}style.css">
<link rel="icon" href="{prefix}favicon.svg" type="image/svg+xml">
{schema}
</head>
<body>
{STAR_DEFS}
{banner}
<header class="site-header">
  <a class="logo" href="{prefix if prefix else '#'}"><img src="{prefix}assets/logo-white.png" alt="Flor" width="140" height="44"></a>
  <div class="header-right">{nav_extra}<a class="btn btn-outline" href="{shop_href}" rel="noopener">{CUR['visit_shop']}</a></div>
</header>
{body}
<footer class="site-footer">
  {CUR['footer_html']}
  <nav><a href="{SHOP_URL}?{UTM}" rel="noopener">florworks.no</a> ·
  <a href="{SHOP_URL_SE}?{UTM}" rel="noopener">florworks.se</a> ·
  <a href="mailto:kontakt@florworks.no">kontakt@florworks.no</a></nav>
  <p class="updated">{CUR['updated']} {oppdatert}</p>
</footer>
</body>
</html>"""


# ---- produktsider (norsk) ----------------------------------------------------

def product_schema(h, d):
    p, rs, tekster = d["p"], d["votes"], d["texts"]
    avg = sum(r["rating"] for r in rs) / len(rs)
    reviews = []
    for r in tekster[:10]:
        item = {"@type": "Review",
                "reviewRating": {"@type": "Rating", "ratingValue": r["rating"], "bestRating": 5},
                "author": {"@type": "Person", "name": r["name"]},
                "reviewBody": r["text"]}
        if r["date"]:
            item["datePublished"] = r["date"].isoformat()
        reviews.append(item)
    data = {"@context": "https://schema.org", "@type": "Product",
            "name": p["title"], "image": p["image"],
            "brand": {"@type": "Brand", "name": "Flor"},
            "url": f"{BASE_URL}/{d['slug']}/",
            "aggregateRating": {"@type": "AggregateRating", "ratingValue": round(avg, 2),
                                "ratingCount": len(rs), "reviewCount": len(tekster),
                                "bestRating": 5, "worstRating": 1},
            "review": reviews}
    if p.get("price"):
        data["offers"] = {"@type": "Offer", "price": p["price"], "priceCurrency": "NOK",
                          "availability": "https://schema.org/InStock",
                          "url": f"{SHOP_URL}/products/{h}"}
    crumbs = {"@context": "https://schema.org", "@type": "BreadcrumbList",
              "itemListElement": [
                  {"@type": "ListItem", "position": 1, "name": SITE_TITLE, "item": f"{BASE_URL}/"},
                  {"@type": "ListItem", "position": 2, "name": p["title"], "item": f"{BASE_URL}/{d['slug']}/"}]}
    return ('<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False) + '</script>'
            '<script type="application/ld+json">' + json.dumps(crumbs, ensure_ascii=False) + '</script>')


def build_product_page(h, d, sample):
    set_lang(L_NB)
    p, rs, tekster = d["p"], d["votes"], d["texts"]
    avg = sum(r["rating"] for r in rs) / len(rs)
    avg_str = no_num(avg)
    resolve = lambda r: None
    cards = "".join(review_card(r, resolve, show_product=False) for r in tekster)
    pris = ""
    if p.get("price"):
        kr = f'{float(p["price"]):,.0f}'.replace(",", " ")
        pris = f'<p class="phero-price">{kr} kr hos florworks.no</p>'
    body = f"""
<main>
<section class="phero">
  <div class="phero-inner">
    <a class="phero-img" href="{SHOP_URL}/products/{h}?{UTM}" rel="noopener">
      <img src="{p["image"]}&width=640" alt="{esc(p["title"])}" width="640" height="800">
    </a>
    <div class="phero-main">
      <nav class="crumbs"><a href="../">Alle omtaler av Flor</a> <span aria-hidden="true">/</span> {esc(p["title"])}</nav>
      <h1>Omtaler av {esc(p["title"])}</h1>
      <div class="hero-rating">
        <span class="hero-avg">{avg_str}</span>
        <span class="hero-stars">{stars_svg(avg, 24)}<span class="hero-count">av 5, fra {len(rs)} verifiserte kjøp</span></span>
      </div>
      {pris}
      <div class="hero-cta">
        <a class="btn btn-primary" href="{SHOP_URL}/products/{h}?{UTM}" rel="noopener">Se produktet hos florworks.no</a>
      </div>
      <p class="phero-trust">Fri frakt over 1 999 kr · Gratis bytte · 14 dagers angrerett</p>
    </div>
    {breakdown_html(rs, clickable=False)}
  </div>
</section>

<section class="section">
  <h2>{len(tekster)} omtaler av {esc(p["title"])}</h2>
  <p class="section-sub">Fra verifiserte kjøp via Lipscore, nyeste først. Samlet vurdering {avg_str} av 5 fra {len(rs)} kjøp.</p>
  <div class="masonry m3" id="palle">{cards}</div>
  <p class="tilbake"><a href="../">← Se alle omtaler av Flor</a></p>
</section>
</main>

<script>
(function () {{{klamp_js()}
  sjekkKlamp('#palle');
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () {{ sjekkKlamp('#palle'); }});
}})();
</script>"""
    title = f'{p["title"]} — omtaler fra {len(rs)} verifiserte kjøp ({avg_str} av 5)'
    desc = (f'Les {len(tekster)} kundeomtaler av {p["title"]} fra Flor. '
            f'Samlet vurdering {avg_str} av 5 stjerner fra {len(rs)} verifiserte kjøp via Lipscore.')
    return page_shell(title=title, desc=desc, path=f"{d['slug']}/", body=body, prefix="../",
                      schema="" if sample else product_schema(h, d),
                      og_image=p["image"], sample=sample)


# ---- temaside: beste arbeidsbukse dame (norsk) -------------------------------

def bukse_ranking(sider):
    kandidater = [(h, d) for h, d in sider.items() if re.search(r"bukse", d["p"]["title"], re.I)]
    def score(kv):
        rs = kv[1]["votes"]
        a = sum(r["rating"] for r in rs) / len(rs)
        return a * math.log(len(rs) + 1)
    return sorted(kandidater, key=score, reverse=True)


def build_theme_page(sider, sample):
    set_lang(L_NB)
    ranked = bukse_ranking(sider)
    if len(ranked) < 3:
        return None
    tot_votes = sum(len(d["votes"]) for _, d in ranked)
    aar = date.today().year
    rows, items = [], []
    for i, (h, d) in enumerate(ranked, 1):
        p, rs, tekster = d["p"], d["votes"], d["texts"]
        avg = sum(r["rating"] for r in rs) / len(rs)
        sitat = max((r for r in tekster if r["rating"] >= 4), key=lambda r: min(len(r["text"]), 180),
                    default=None)
        sitat_html = ""
        if sitat:
            kort = sitat["text"] if len(sitat["text"]) <= 180 else sitat["text"][:177].rstrip() + "…"
            sitat_html = f'<blockquote class="rank-quote">«{esc(kort)}»<cite>— {esc(sitat["name"])}, verifisert kjøp</cite></blockquote>'
        pris = ""
        if p.get("price"):
            kr = f'{float(p["price"]):,.0f}'.replace(",", " ")
            pris = f'<span class="p-price">{kr} kr</span>'
        rows.append(f"""
  <article class="rank-item">
    <span class="rank-nr">{i}</span>
    <a class="rank-img" href="{d['slug']}/"><img src="{p['image']}&width=480" alt="{esc(p['title'])}" loading="lazy" width="480" height="600"></a>
    <div class="rank-main">
      <h3><a href="{d['slug']}/">{esc(p['title'])}</a></h3>
      <div class="rank-rating">{stars_svg(avg, 16)}<span>{no_num(avg)} av 5 · {len(rs)} vurderinger</span>{pris}</div>
      {sitat_html}
      <div class="rank-links">
        <a class="btn btn-primary" href="{SHOP_URL}/products/{h}?{UTM}" rel="noopener">Se produktet</a>
        <a class="btn btn-ghost" href="{d['slug']}/">Les alle {len(tekster)} omtalene</a>
      </div>
    </div>
  </article>""")
        items.append({"@type": "ListItem", "position": i,
                      "item": {"@type": "Product", "name": p["title"], "image": p["image"],
                               "url": f"{BASE_URL}/{d['slug']}/",
                               "aggregateRating": {"@type": "AggregateRating",
                                                   "ratingValue": round(avg, 2),
                                                   "ratingCount": len(rs), "bestRating": 5}}})
    schema = ('<script type="application/ld+json">'
              + json.dumps({"@context": "https://schema.org", "@type": "ItemList",
                            "name": f"Beste arbeidsbukse for damer {aar}, rangert av kundene",
                            "itemListElement": items}, ensure_ascii=False)
              + '</script>')
    i_dag = fmt_date(date.today())
    body = f"""
<main>
<section class="hero">
  <div class="hero-inner hero-single">
    <div class="hero-main">
      <nav class="crumbs"><a href="../">Alle omtaler av Flor</a> <span aria-hidden="true">/</span> Beste arbeidsbukse for damer</nav>
      <h1>Beste arbeidsbukse for damer — rangert av kundene</h1>
      <p class="hero-sub">{len(ranked)} buksemodeller fra Flor, rangert etter {tot_votes} verifiserte
      kundevurderinger samlet inn via Lipscore. Rangeringen beregnes av snittvurdering og antall
      vurderinger, oppdatert {i_dag}.</p>
    </div>
  </div>
</section>
<section class="section">
  <div class="rank-list">{''.join(rows)}</div>
  <p class="tilbake"><a href="../">← Se alle omtaler av Flor</a></p>
</section>
</main>"""
    title = f"Beste arbeidsbukse for damer {aar} — rangert av {tot_votes} kunder"
    desc = (f"Hvilken arbeidsbukse for damer er best? {len(ranked)} buksemodeller fra Flor rangert etter "
            f"{tot_votes} verifiserte kundevurderinger via Lipscore.")
    return page_shell(title=title, desc=desc, path=f"{THEME_SLUG}/", body=body, prefix="../",
                      schema="" if sample else schema, sample=sample)


# ---- forside (nb + sv) -------------------------------------------------------

def index_schema(votes, cards_n, avg, L, shop):
    org = {"@context": "https://schema.org", "@type": "OnlineStore",
           "name": "Flor", "legalName": "Flor AS", "url": shop,
           "logo": f"{SHOP_URL}/cdn/shop/files/Logo-white-400.png",
           "address": {"@type": "PostalAddress", "streetAddress": "Vangsgata 39",
                       "postalCode": "5700", "addressLocality": "Voss", "addressCountry": "NO"},
           "aggregateRating": {"@type": "AggregateRating", "ratingValue": round(avg, 2),
                               "ratingCount": len(votes), "reviewCount": cards_n,
                               "bestRating": 5, "worstRating": 1}}
    faq = {"@context": "https://schema.org", "@type": "FAQPage",
           "mainEntity": [{"@type": "Question", "name": q,
                           "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in L["faq"]]}
    return ('<script type="application/ld+json">' + json.dumps(org, ensure_ascii=False) + '</script>'
            '<script type="application/ld+json">' + json.dumps(faq, ensure_ascii=False) + '</script>')


def product_cards_html(votes, by_handle, by_title, sider, shop, internal):
    agg = {}
    for r in votes:
        p = by_handle.get(r["handle"]) or by_title.get(norm(r["product"]))
        if not p:
            continue
        a = agg.setdefault(p["handle"], {"sum": 0, "n": 0, "p": p})
        a["sum"] += r["rating"]
        a["n"] += 1
    ranked = sorted([a for a in agg.values() if a["n"] >= 2],
                    key=lambda a: (a["sum"] / a["n"]) * math.log(a["n"] + 1), reverse=True)
    ent, fler = CUR["ratings_word"].split("|")
    cards = []
    for a in ranked[:4]:
        p, avg = a["p"], a["sum"] / a["n"]
        h = p["handle"]
        pris = ""
        if p.get("price"):
            kr = f'{float(p["price"]):,.0f}'.replace(",", " ")
            pris = f'<span class="p-price">{kr} kr</span>'
        intern = ""
        if internal and h in sider and CUR["read_all_fmt"]:
            intern = (f'<a class="pcard-reviews" href="{sider[h]["slug"]}/">'
                      f'{CUR["read_all_fmt"].format(n=len(sider[h]["texts"]))}</a>')
        cards.append(
            f'<div class="pcard">'
            f'<a class="pcard-main" href="{shop}/products/{h}?{UTM}" rel="noopener">'
            f'<img src="{p["image"]}&width=480" alt="{esc(p["title"])}" loading="lazy" width="480" height="600">'
            f'<span class="p-title">{esc(p["title"])}</span>'
            f'{stars_svg(avg, 14)}<span class="p-count">{a["n"]} {fler if a["n"] != 1 else ent}</span>{pris}'
            f'<span class="p-cta">{CUR["see_product"]}</span></a>'
            f'{intern}</div>')
    return "".join(cards)


def build_index(votes, by_handle, by_title, sider, sample, L):
    set_lang(L)
    nb = L["lang"] == "nb"
    shop = SHOP_URL if nb else SHOP_URL_SE
    shop2 = SHOP_URL_SE if nb else SHOP_URL
    path = "" if nb else "se/"
    prefix = "" if nb else "../"
    n_votes = len(votes)
    avg = sum(r["rating"] for r in votes) / n_votes if n_votes else 0
    avg_str = no_num(avg)
    cards = [r for r in votes if r["text"]]
    n_cards = len(cards)
    n_stille = n_votes - n_cards

    def resolve(r):
        if nb and r["handle"] and r["handle"] in sider:
            return (f'{sider[r["handle"]]["slug"]}/', True)
        p = by_handle.get(r["handle"]) or by_title.get(norm(r["product"]))
        if p:
            return (f'{shop}/products/{p["handle"]}?{UTM}', False)
        return None

    featured = [r for r in cards if r["rating"] >= 5 and len(r["text"]) >= 80][:12]
    if len(featured) < 12:
        featured = sorted(cards, key=lambda r: (r["rating"], len(r["text"])), reverse=True)[:12]
    feat_html = featured_columns(featured, resolve)
    wall_html = "".join(review_card(r, resolve, hidden=(i >= WALL_BATCH)) for i, r in enumerate(cards))
    prods_html = product_cards_html(votes, by_handle, by_title, sider, shop, internal=nb)
    breakdown = breakdown_html(votes)
    stille = L["wall_silent"].format(n=n_stille) if n_stille > 0 else ""
    faq_html = "".join(f'<details><summary>{esc(q)}</summary><p>{esc(a)}</p></details>' for q, a in L["faq"])
    trust_html = "".join(f"<li>{esc(t)}</li>" for t in L["trust"])
    chips = [f'<button class="chip active" data-filter="alle" aria-pressed="true">{L["chip_all"]}</button>']
    for i in (5, 4, 3, 2):
        chips.append(f'<button class="chip" data-filter="{i}" aria-pressed="false">{L["chip_star"].format(n=i)}</button>')
    chips.append(f'<button class="chip" data-filter="1" aria-pressed="false">{L["chip_star1"]}</button>')
    s0, s1, s2 = L["showing"]

    body = f"""
<main>
<section class="hero">
  <div class="hero-inner">
    <div class="hero-main">
      <h1>{L['h1']}</h1>
      <div class="hero-rating">
        <span class="hero-avg">{avg_str}</span>
        <span class="hero-stars">{stars_svg(avg, 24)}<span class="hero-count">{L['hero_count'].format(n=n_votes)}</span></span>
      </div>
      <p class="hero-sub">{L['hero_sub'].format(shop=shop, utm=UTM)}</p>
      <div class="hero-cta">
        <a class="btn btn-primary" href="{shop}?{UTM}" rel="noopener">{L['cta_shop']}</a>
        <a class="btn btn-ghost" href="#alle">{L['cta_reviews']}</a>
      </div>
    </div>
    {breakdown}
  </div>
</section>

<section class="section">
  <h2>{L['featured_h2']}</h2>
  <p class="section-sub">{L['featured_sub']}</p>
  <div class="featured-wrap">
    <div class="featured-cols">{feat_html}</div>
    <div class="fade-cta"><a class="btn btn-primary" href="#alle">{L['see_all']}</a></div>
  </div>
</section>

<section class="section section-beige">
  <h2>{L['products_h2']}</h2>
  <div class="grid grid-products">{prods_html}</div>
</section>

<section class="section" id="alle">
  <h2>{L['wall_h2']}</h2>
  <p class="section-sub">{L['wall_sub'].format(n=n_cards)}{stille}{L['orig_note']}</p>
  <div class="filters" role="group" aria-label="{L['filter_aria']}">
    {''.join(chips)}
    <input type="search" id="sok" placeholder="{L['search_ph']}" aria-label="{L['search_aria']}">
  </div>
  <p class="filter-status" id="status" aria-live="polite"></p>
  <div class="wall-wrap" id="vegg-wrap">
    <div class="masonry m3" id="vegg">{wall_html}</div>
    <div class="mer-wrap"><button class="btn btn-primary" id="mer">{L['show_more']}</button></div>
  </div>
</section>

<section class="section section-beige">
  <h2>{L['about_h2']}</h2>
  <div class="about">
    {L['about_html'].format(shop=shop, shop2=shop2, utm=UTM)}
    <ul class="trust">{trust_html}</ul>
  </div>
</section>

<section class="section">
  <h2>{L['faq_h2']}</h2>
  {faq_html}
</section>
</main>

<script>
(function () {{
  var chips = document.querySelectorAll('.chip'), sok = document.getElementById('sok'),
      cards = document.querySelectorAll('#vegg .card'), status = document.getElementById('status'),
      mer = document.getElementById('mer'), merWrap = mer.parentElement,
      wrap = document.getElementById('vegg-wrap'),
      BATCH = {WALL_BATCH}, limit = BATCH, aktiv = 'alle';
{klamp_js()}

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
    var flere = !filtrert && treff > limit;
    merWrap.style.display = flere ? '' : 'none';
    wrap.classList.toggle('has-more', flere);
    status.textContent = filtrert ? '{s0}' + vist + '{s1}' + cards.length + '{s2}' : '';
    sjekkKlamp('#vegg');
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
    if (!b.dataset.r) return;
    b.addEventListener('click', function () {{
      var chip = document.querySelector('.chip[data-filter="' + b.dataset.r + '"]');
      if (chip) chip.click();
      document.getElementById('alle').scrollIntoView({{ behavior: 'smooth' }});
    }});
  }});

  oppdater();
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () {{ sjekkKlamp('#vegg'); }});
}})();
</script>"""

    if nb:
        title = f"{SITE_TITLE} — {avg_str} av 5 basert på {n_votes} vurderinger"
        desc = (f"Les {n_cards} kundeomtaler av Flor arbeidsklær for damer. Samlet vurdering {avg_str} av 5 "
                f"stjerner fra {n_votes} verifiserte kjøp, samlet inn via Lipscore.")
    else:
        title = f"Kundrecensioner av Flor arbetskläder — {avg_str} av 5 från {n_votes} verifierade köp"
        desc = (f"Läs {n_cards} kundrecensioner av Flor arbetskläder för damer. Samlat betyg {avg_str} av 5 "
                f"stjärnor från {n_votes} verifierade köp, insamlade via Lipscore.")
    alternates = [("nb", f"{BASE_URL}/"), ("sv", f"{BASE_URL}/se/"), ("x-default", f"{BASE_URL}/")]
    return page_shell(title=title, desc=desc, path=path, body=body, prefix=prefix,
                      schema="" if sample else index_schema(votes, n_cards, avg, L, shop),
                      sample=sample, alternates=alternates,
                      shop_href=f"{shop}?{UTM}", nav_extra=L["lang_switch"])


# ---- sitemap, robots, llms, indexnow -----------------------------------------

def build_sitemap(paths):
    i_dag = date.today().isoformat()
    urls = "".join(f"<url><loc>{BASE_URL}/{p}</loc><lastmod>{i_dag}</lastmod></url>" for p in paths)
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + urls + '</urlset>')


def build_robots():
    bots = ["GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-SearchBot",
            "anthropic-ai", "PerplexityBot", "Google-Extended", "Applebot-Extended",
            "meta-externalagent", "CCBot"]
    ai = "".join(f"User-agent: {b}\nAllow: /\n\n" for b in bots)
    return (f"# floromtaler — kundeomtaler av Flor (florworks.no)\n"
            f"# Søkemotorer og AI-crawlere er velkomne. Se også /llms.txt og /llms-full.txt.\n\n"
            f"User-agent: *\nAllow: /\n\n{ai}Sitemap: {BASE_URL}/sitemap.xml\n")


def indexnow_key():
    """Stabil nøkkel, generert én gang og committet (data/indexnow-key.txt)."""
    sti = os.path.join(BASE, "data", "indexnow-key.txt")
    if os.path.exists(sti):
        return open(sti).read().strip()
    key = secrets.token_hex(16)
    with open(sti, "w") as f:
        f.write(key + "\n")
    return key


def build_llms(votes, sider, avg):
    i_dag = fmt_date(date.today())
    linjer = [f"# {SITE_TITLE}", "",
              f"> {len(votes)} verifiserte kundevurderinger (snitt {no_num(avg)} av 5) av Flor, norsk produsent "
              f"av arbeidsklær for damer. Nettbutikk: {SHOP_URL}. Omtalene er samlet inn av Lipscore fra "
              f"verifiserte kjøp og gjengis uredigert. Denne siden driftes av Flor AS.", "",
              "Nøkkelfakta:",
              "- Flor AS, org.nr. 918 377 573, Vangsgata 39, 5700 Voss, Norge",
              f"- Samlet vurdering: {no_num(avg)} av 5 basert på {len(votes)} verifiserte kjøp (per {i_dag})",
              "- Fri frakt over 1 999 kr (Norge), gratis bytte, 14 dagers angrerett",
              f"- Nettbutikker: {SHOP_URL} (Norge) og {SHOP_URL_SE} (Sverige)",
              f"- Svensk versjon av omtalesiden: {BASE_URL}/se/", "",
              "## Produkter med omtaler", ""]
    rangert = sorted(sider.items(), key=lambda kv: len(kv[1]["votes"]), reverse=True)
    for h, d in rangert:
        a = sum(r["rating"] for r in d["votes"]) / len(d["votes"])
        linjer.append(f"- [{d['p']['title']}]({BASE_URL}/{d['slug']}/): {no_num(a)} av 5 fra "
                      f"{len(d['votes'])} vurderinger ({len(d['texts'])} med tekst)")
    linjer += ["", "## Guider", "",
               f"- [Beste arbeidsbukse for damer, rangert av kundene]({BASE_URL}/{THEME_SLUG}/)",
               "", "## Full tekst", "",
               f"- [Alle omtaler i ren tekst]({BASE_URL}/llms-full.txt)"]
    return "\n".join(linjer) + "\n"


def build_llms_full(votes, sider, avg):
    linjer = [f"# {SITE_TITLE} — alle omtaler", "",
              f"Snitt {no_num(avg)} av 5 fra {len(votes)} verifiserte kjøp via Lipscore. "
              f"Butikk: {SHOP_URL} (Norge), {SHOP_URL_SE} (Sverige). Driftes av Flor AS, Voss.", ""]
    rangert = sorted(sider.items(), key=lambda kv: len(kv[1]["votes"]), reverse=True)
    dekket = set()
    for h, d in rangert:
        a = sum(r["rating"] for r in d["votes"]) / len(d["votes"])
        linjer += [f"## {d['p']['title']} — {no_num(a)} av 5 ({len(d['votes'])} vurderinger)",
                   f"Produktside: {SHOP_URL}/products/{h}", ""]
        for r in d["texts"]:
            dekket.add(id(r))
            dato = f", {fmt_date(r['date'])}" if r["date"] else ""
            linjer.append(f"- {no_num(r['rating'], 0)}/5 ({r['name']}{dato}): {r['text']}")
            if r["reply"]:
                linjer.append(f"  - Svar fra Flor: {r['reply']}")
        linjer.append("")
    rest = [r for r in votes if r["text"] and id(r) not in dekket]
    if rest:
        linjer += ["## Øvrige omtaler (butikk og andre produkter)", ""]
        for r in rest:
            dato = f", {fmt_date(r['date'])}" if r["date"] else ""
            hva = "butikken" if is_service(r) else (r["product"] or "produkt")
            linjer.append(f"- {no_num(r['rating'], 0)}/5 om {hva} ({r['name']}{dato}): {r['text']}")
            if r["reply"]:
                linjer.append(f"  - Svar fra Flor: {r['reply']}")
        linjer.append("")
    linjer += ["## Ofte stilte spørsmål", ""]
    for q, a in L_NB["faq"]:
        linjer += [f"### {q}", a, ""]
    return "\n".join(linjer) + "\n"


# ---- hovedløp ----------------------------------------------------------------

def build():
    votes, sample = load_reviews()
    by_handle, by_title = load_products()
    sider = product_pages_data(votes, by_handle)
    avg = sum(r["rating"] for r in votes) / len(votes) if votes else 0

    # rydd gamle undermapper så nedlagte sider ikke blir liggende
    if os.path.isdir(DOCS):
        for navn in os.listdir(DOCS):
            sti = os.path.join(DOCS, navn)
            if os.path.isdir(sti) and navn != "assets":
                shutil.rmtree(sti)
    os.makedirs(DOCS, exist_ok=True)
    os.makedirs(os.path.join(DOCS, "assets"), exist_ok=True)

    with open(os.path.join(DOCS, "index.html"), "w", encoding="utf-8") as f:
        f.write(build_index(votes, by_handle, by_title, sider, sample, L_NB))
    os.makedirs(os.path.join(DOCS, "se"), exist_ok=True)
    with open(os.path.join(DOCS, "se", "index.html"), "w", encoding="utf-8") as f:
        f.write(build_index(votes, by_handle, by_title, sider, sample, L_SV))
    for h, d in sider.items():
        os.makedirs(os.path.join(DOCS, d["slug"]), exist_ok=True)
        with open(os.path.join(DOCS, d["slug"], "index.html"), "w", encoding="utf-8") as f:
            f.write(build_product_page(h, d, sample))
    tema = build_theme_page(sider, sample)
    if tema:
        os.makedirs(os.path.join(DOCS, THEME_SLUG), exist_ok=True)
        with open(os.path.join(DOCS, THEME_SLUG, "index.html"), "w", encoding="utf-8") as f:
            f.write(tema)

    set_lang(L_NB)
    paths = ["", "se/"] + (([f"{THEME_SLUG}/"]) if tema else []) + sorted(f"{d['slug']}/" for d in sider.values())
    with open(os.path.join(DOCS, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(build_sitemap(paths))
    with open(os.path.join(DOCS, "robots.txt"), "w", encoding="utf-8") as f:
        f.write(build_robots())
    key = indexnow_key()
    with open(os.path.join(DOCS, f"{key}.txt"), "w") as f:
        f.write(key + "\n")
    if not sample:
        with open(os.path.join(DOCS, "llms.txt"), "w", encoding="utf-8") as f:
            f.write(build_llms(votes, sider, avg))
        with open(os.path.join(DOCS, "llms-full.txt"), "w", encoding="utf-8") as f:
            f.write(build_llms_full(votes, sider, avg))

    shutil.copy(os.path.join(BASE, "src", "style.css"), os.path.join(DOCS, "style.css"))
    shutil.copy(os.path.join(BASE, "assets", "logo-white.png"), os.path.join(DOCS, "assets", "logo-white.png"))
    shutil.copy(os.path.join(BASE, "src", "favicon.svg"), os.path.join(DOCS, "favicon.svg"))
    open(os.path.join(DOCS, ".nojekyll"), "w").close()

    n_cards = sum(1 for r in votes if r["text"])
    mode = "SAMPLE (forhåndsvisning)" if sample else "PRODUKSJON"
    print(f"OK: forside (nb+sv) + {len(sider)} produktsider + {'temaside' if tema else 'ingen temaside'} — "
          f"{len(votes)} vurderinger ({n_cards} med tekst), snitt {no_num(avg)}/5, modus: {mode}")
    print(f"    sitemap.xml ({len(paths)} URL-er), robots.txt, IndexNow-nøkkel {key[:8]}…"
          + (", llms.txt, llms-full.txt" if not sample else " (llms-filer hoppes over i sample-modus)"))


if __name__ == "__main__":
    build()
