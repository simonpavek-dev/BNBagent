# Vasil – AI agent pro apartmány (Smoobu → Claude → Telegram)

Python 3.9+, kód a komentáře česky. Běží na serveru Hetzner jako služby `airbnb-agent` a `airbnb-panel` (`server/`).
Znalostní báze = YAML v `znalostni-baze/` (skutečné byty nejsou v gitu). Testy: `.venv/bin/python -m pytest`.

## Mapa modulů (`agent/`)
- `__main__.py` – příkazy (kontrola, zkouska, spustit…), smyčka a `jeden_cyklus()`; spouští ho systemd.
- `hodiny.py` – jediný zdroj času pro rozhodování (`ted()`, `dnes()`); v testech `zmraz()` / `posun()`.
- `config.py` – nastavení z `.env`; importují ho všechny moduly.
- `smoobu.py` – klient Smoobu API (jen HMAC, 401/429); instanci dělá `prace.vytvor_smoobu`.
- `prace.py` – zprávy hostů, instrukce k příjezdu, kontrola kalendáře, hodnocení, upozornění na 401; volá `__main__`.
- `mozek.py` – volání Claude (rozhodnutí o zprávě, instrukce, hodnocení, překlad); volají `prace`, `navrhy`, `spravce`, `uklidy`.
- `navrhy.py` – návrhy pro hosty: schválení, plánované odeslání, kontroly před odesláním (`odeslat()`).
- `odchozi.py` – **brána**: jediné místo s `smoobu.send_message`; po timeoutu ověří konverzaci (žádné dvojí odeslání).
- `telegram_ovladani.py` – tlačítka a zprávy ze skupiny, „Vasile…“ → `spravce`; volá hlavní smyčka.
- `oznameni.py` – Telegram: `posli` (při výpadku do fronty, `dorucit_frontu` v cyklu), tlačítka, getUpdates.
- `spravce.py` – chat s hostitelem (panel i Telegram) s nástroji: znalostní báze, rezervace, kódy, návrh zprávy.
- `uklidy.py` – aplikace úklidů (čte `/uklidy`): kódy, stav úklidu, nabídka dřívějšího check-inu; volá hlavní smyčka, `kody`.
- `instrukce.py` – instrukce k příjezdu ze šablony (jediná cesta), model jen překládá; volá `prace`.
- `trideni.py` – pravidla bez modelu: jednoduchá zpráva (→ levnější model), čistá zdvořilost (→ odpověď bez modelu); volá `prace`.
- `kody.py` – platný kód keyboxu pro rezervaci (aplikace úklidů / znalostní báze); volají `prace`, `spravce`.
- `kontext.py` – text rezervace + konverzace pro model, dnešní datum; volají `prace`, `mozek`, `spravce`.
- `znalosti.py` – načtení YAML znalostní báze (před modelem skrývá `keybox_kod`); volají `prace`, `uklidy`, `mozek`.
- `mapy.py` – nástroj `trasa` (OpenStreetMap, pěší trasa); volá `mozek`.
- `databaze.py` – SQLite: zprávy, návrhy, události, nastavení, chat; používají všechny moduly.
- `dashboard.py` + `dashboard.html` – ovládací panel na localhost:8765 (zvenku přes SSH tunel).
- `import_smoobu.py` – předvyplnění znalostní báze a export historie konverzací (příkaz `nacist-smoobu`).

## Nepřekročitelná pravidla
- Každá zpráva hosta skončí v jednom stavu: odpovězeno, čeká na schválení, eskalováno, vědomě bez odpovědi. Nikdy se neztratí.
- Hostovi nic neodejde mimo bránu `odchozi.odeslat` (přes `navrhy.odeslat`); hlídá to test `test_jen_brana_posila_zpravy_hostum`.
- Kódy, Wi-Fi, adresy a časy nikdy nepíše model, doplňuje je kód ze zdroje pravdy.
- Upozornění hostiteli se nesmí ztratit – jen přes `oznameni.posli` (fronta při výpadku Telegramu); u návrhů `navrh_id`.
- Nová funkce = přepínač v `.env`, výchozí vypnuto, popsaný v `.env.example`, přidaný do `PREPINACE` v `tests/test_prepinace.py`.
- Žádná skutečná data hostů, kódy ani telefonní čísla v testech, příkladech a commitech. Repo je veřejné.
- Hodnoty z `.env` nikdy nečti ani nevypisuj, jen názvy proměnných (např. `grep -c '^SMOOBU_API_SECRET=.' .env`).

## Postup každého úkolu
1. Přečti `SCRATCHPAD.md` a posledních 10 commitů.
2. Změna ve víc souborech = nejdřív plán a počkej na schválení.
3. Nejdřív test, který problém ukáže, a ukaž, že padá.
4. Oprava, celý pytest zelený, simulátor scénářů zelený (až bude).
5. Aktualizuj `SCRATCHPAD.md`, `LESSONS_LEARNED.md` (když něco trvalo přes 10 minut), `.env.example` a README.
6. Commit na větev pojmenovanou podle kroku (např. `p1-4-brana`). Do `main` nepushuj bez souhlasu.
7. Rozhodnutí, která může udělat jen hostitel, zapiš do `DECISIONS.md` s možnostmi a zastav se.

## Testy a bezpečnost
- `tests/conftest.py` zakazuje síť a nastavuje smyšlené klíče – test nikdy nesmí sáhnout na Smoobu, Telegram ani Claude.
- Fixture `svet`: FakeSmoobu / FakeTelegram / FakeModel (`tests/nahrazky.py`), smyšlený byt, hodiny zmrazené na
  po 2. 11. 2026 9:00; `svet.cyklus()` = celý `jeden_cyklus`. Čas nikdy přes `datetime.now()`, vždy `hodiny.ted()`.
- Známé chyby = `xfail(strict=True)`; po opravě značku odstranit. Nový přepínač nastav i v `tests/conftest.py`.
- Nikdy nespouštěj `python -m agent spustit` lokálně, když běží server (dva agenti = dvojí zprávy).
- Na GitHub nesmí: `.env`, `data/`, skutečné byty v `znalostni-baze/apartmany/`, `poznamky-k-hostum.yaml`.

## Smoobu
- Jen HMAC (X-API-Key, X-Timestamp, X-Nonce, X-Signature); staré `Api-Key` Smoobu vypíná 31. 10. 2026.
- Query string pro podpis i URL: RFC 3986, klíče abecedně (mezera `%20`, `[]` → `%5B%5D`).
- 429: GET počká do `X-RateLimit-Retry-After` (Unix čas) a zopakuje; POST (odeslání zprávy) nikdy neopakuje.
- Znak `<` ve zprávě Smoobu bere jako HTML a zbytek zahodí – brána ho nahrazuje a ověřuje uložený text.

## Nasazení
`server/nahrat-na-server.sh <IP>` – nejdřív stáhne změny znalostní báze provedené přes Telegram, pak nahraje kód,
`.env` a znalostní bázi a restartuje služby. Před nasazením počkat, až `cinnost` = „Čekám…“. Po nasazení `kontrola` na serveru.
