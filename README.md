# floromtaler — kundeomtalesider for Flor

Statiske omtalesider som viser Lipscore-kundeomtaler av Flor. Bygget av Seal Media.
Ett `build.py` genererer **to selvstendige nettsteder**, ett per marked:

| Marked | Domene | Utmappe | Vercel-prosjekt | Root Directory |
|---|---|---|---|---|
| Norge (nb) | `floromtaler.no` | `docs/` | `floromtaler` | repo-rot |
| Sverige (sv) | `florrecensioner.se` | `site-se/docs/` | `florrecensioner` | `site-se` |

Egen ccTLD per marked er poenget: et `.no`-domene forteller Google at innholdet hører til
Norge, og drar ned på brede svenske søk. Sidene er oversettelser av hverandre og bindes
sammen med `hreflang` begge veier, per side. `floromtaler.no/se/` finnes ikke lenger, den
301-redirigeres til `florrecensioner.se` i `vercel.json`.

## slik fungerer det

- `build.py` leser `data/reviews.csv` (Lipscore-eksport) og `data/products.json`
  (produktdata fra florworks.no) og genererer hele siden til `docs/`:
  forsiden, én omtaleside per produkt med 5+ tekstomtaler (16 stk per juli 2026),
  `sitemap.xml`, `robots.txt` (åpen for søke- og AI-crawlere) samt `llms.txt` og
  `llms-full.txt` (AI-lesbart sammendrag + alle omtaler i ren tekst, llmstxt.org).
  Produktsidene har Product/AggregateRating/Review-schema (stjerner i SERP mulig).
- `site-se/docs/` får samme behandling på svensk: svenske produktnavn og SEK-priser fra
  `data/products_se.json`, svenske slugger fra det svenske produktnavnet
  (`god-snickarbyxor`, ikke `god-snekkerbukse`), egen temaside `basta-arbetsbyxan-dam`,
  eget sitemap/robots/llms og `utm_source=florrecensioner`. Produkter som ikke selges på
  florworks.se utelates fra den svenske siden i stedet for å lenke til noe kunden ikke får kjøpt.
- Begge mapper serveres statisk av hvert sitt Vercel-prosjekt, ingen build nødvendig.
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

1. I `build.py`: `NOINDEX = False` og riktig `BASE_URL_NB` / `BASE_URL_SV`, bygg og push.
   Canonical, hreflang, og:url, sitemap og llms-lenker genereres fra `BASE_URL`, som
   `set_site()` setter per nettsted.
2. Pek domenet til Vercel-prosjektet (Domains i prosjektet). Apex er kanonisk, `www`
   308-redirigeres til apex.
3. Footer-lenke fra florworks.no og florworks.se til omtalesiden («Kundeomtaler ⭐ 4,7»).
4. Google Search Console + Bing Webmaster Tools: legg til domenet, send inn sitemap.xml.
5. IndexNow-ping (nøkkelfila ligger allerede i docs/):
   `curl "https://api.indexnow.org/indexnow?url=https://<domene>/&key=$(cat data/indexnow-key.txt)"`
   Gjenta gjerne etter hver dataoppdatering.

Temasidene `/beste-arbeidsbukse-dame/` og `/basta-arbetsbyxan-dam/` regenereres automatisk
fra omtaledataene. Rangeringen beregnes på det norske produktnavnet, som er produktets
identitet på tvers av butikkene, slik at de to sidene blir ekte oversettelser av hverandre.

## design

Designtokens fra florworks.no (tema SEAL | Symmetry): Montserrat 400 (headinger),
Jost (brødtekst), mauve `#A57D85`, lys rosa `#DFC8CB` (inaktive stjerner, Flors egne
Lipscore-farger), beige `#F5F3EE`, tekst `#232323`, lenker `#6E7F71`.
