# floromtaler — kundeomtaleside for Flor (florworks.no)

Statisk omtaleside som viser Lipscore-kundeomtaler av [florworks.no](https://florworks.no).
Bygget av Seal Media. Arbeidstittel `floromtaler` — endelig domenenavn bestemmes av kunden.

## slik fungerer det

- `build.py` leser `data/reviews.csv` (Lipscore-eksport) og `data/products.json`
  (produktdata fra florworks.no) og genererer hele siden til `docs/`:
  forsiden, én omtaleside per produkt med 5+ tekstomtaler (16 stk per juli 2026),
  `sitemap.xml`, `robots.txt` (åpen for søke- og AI-crawlere) samt `llms.txt` og
  `llms-full.txt` (AI-lesbart sammendrag + alle omtaler i ren tekst, llmstxt.org).
  Produktsidene har Product/AggregateRating/Review-schema (stjerner i SERP mulig).
- `docs/` serveres statisk (GitHub Pages nå; Vercel: importer repoet, ingen build nødvendig).
- Finnes ikke `data/reviews.csv`, brukes `data/reviews_sample.csv` og siden viser
  forhåndsvisningsbanner + noindex (eksempeldata skal aldri indekseres).

## legge inn ekte omtaler

1. Eksporter omtaler fra Lipscore-admin som CSV.
2. Lagre fila som `data/reviews.csv`.
3. Kjør `python3 build.py` (kun standardbibliotek, ingen avhengigheter).
4. Commit og push — siden oppdateres automatisk.

Kolonner gjenkjennes fleksibelt (se `COLS` i `build.py`). Minimum: en rating-kolonne
(`rating`/`score`/`stars` …) og en tekstkolonne (`review_text`/`text`/`review` …).
Valgfritt: navn, dato, produktnavn. Produktnavn som matcher `data/products.json`
blir lenket til produktet med UTM-parametre.

## oppdatere produktdata

Kjør `python3 fetch_products.py` før `build.py`. Den henter begge butikkene og skriver
slankede kataloger:

- `data/products.json` — florworks.no: norske navn, NOK-priser. Styrer produktsidene.
- `data/products_se.json` — florworks.se: svenske navn, SEK-priser. Overstyrer `/se/`.

Butikkene deler produkt-handles, så den svenske fila brukes som et overlegg: samme produkt,
men navnet og prisen slik en svensk kunde faktisk møter dem. Uten overlegget ville `/se/`
vist «God snekkerbukse 1 799 kr» der butikken selger «God snickarbyxor» til 1 899 SEK.

Produkter som er tatt ut av sortimentet forsvinner fra katalogen, og da fjerner `build.py`
både produktsiden og lenkene til dem ved neste bygg. Skriptet skriver ut hva som er nytt
og hva som er utgått.

## lansering på eget domene (sjekkliste)

1. I `build.py`: sett `NOINDEX = False` og `BASE_URL = "https://<domene>"`, bygg og push.
   Canonical, hreflang, og:url, sitemap og llms-lenker genereres fra `BASE_URL`.
2. Pek domenet til hostingen (Vercel: Domains i prosjektet; GitHub Pages: CNAME).
3. Footer-lenke fra florworks.no og florworks.se til omtalesiden («Kundeomtaler ⭐ 4,7»).
4. Google Search Console + Bing Webmaster Tools: legg til domenet, send inn sitemap.xml.
5. IndexNow-ping (nøkkelfila ligger allerede i docs/):
   `curl "https://api.indexnow.org/indexnow?url=https://<domene>/&key=$(cat data/indexnow-key.txt)"`
   Gjenta gjerne etter hver dataoppdatering.

Svensk versjon ligger på `/se/` med hreflang begge veier (nb ↔ sv). Temasiden
`/beste-arbeidsbukse-dame/` regenereres automatisk fra omtaledataene.

## design

Designtokens fra florworks.no (tema SEAL | Symmetry): Montserrat 400 (headinger),
Jost (brødtekst), mauve `#A57D85`, lys rosa `#DFC8CB` (inaktive stjerner, Flors egne
Lipscore-farger), beige `#F5F3EE`, tekst `#232323`, lenker `#6E7F71`.
