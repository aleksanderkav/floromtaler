# floromtaler — kundeomtaleside for Flor (florworks.no)

Statisk omtaleside som viser Lipscore-kundeomtaler av [florworks.no](https://florworks.no).
Bygget av Seal Media. Arbeidstittel `floromtaler` — endelig domenenavn bestemmes av kunden.

## slik fungerer det

- `build.py` leser `data/reviews.csv` (Lipscore-eksport) og `data/products.json`
  (produktdata fra florworks.no) og genererer hele siden til `docs/`.
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

`data/products.json` er hentet fra `https://florworks.no/products.json?limit=250` (slanket).
Hent på nytt ved behov for nye produkter/bilder.

## lansering på eget domene

I `build.py`: sett `NOINDEX = False` og `CANONICAL = "https://<domene>/"`, bygg på nytt.
Pek domenet til hostingen (GitHub Pages: CNAME, Vercel: domener i dashbordet).
Husk footer-lenke fra florworks.no og florworks.se til omtalesiden.

## design

Designtokens fra florworks.no (tema SEAL | Symmetry): Montserrat 400 (headinger),
Jost (brødtekst), mauve `#A57D85`, lys rosa `#DFC8CB` (inaktive stjerner, Flors egne
Lipscore-farger), beige `#F5F3EE`, tekst `#232323`, lenker `#6E7F71`.
