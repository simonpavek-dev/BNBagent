# SCRATCHPAD

Pracovní poznámky mezi úkoly. Na začátku každého úkolu přečíst, na konci aktualizovat.

## Hotovo
- Smoobu jen přes HMAC, RFC 3986, 401 → okamžité upozornění, 429 jen u GET (`23243ce`, nasazeno na server, `kontrola` = OK).
- Odolnost smyčky: neúspěšné naplánované odeslání jen 1×, chyba v jednom kroku nezastaví ostatní (`97fb936`).
- Instrukce k příjezdu: před odesláním kontrola konverzace (už poslané → neposílat), po skončení pobytu neposílat (`6bcd822`).
- Kontrola kalendáře každou hodinu na rok dopředu, upozornění bez opakování (`65551f9`).
- Instrukce k příjezdu odchází samy v 10:00 (`PRIJEZDY_AUTOMATICKY=ano`), odpovědi hostům ke schválení (`REZIM=navrh`).
- Ovládání přes Telegram („Vasile…“), aplikace úklidů jako zdroj kódů, nabídka dřívějšího check-inu (vždy ke schválení).
- Testy: 22 zelených + 3 xfail; náhražky Smoobu/Telegram/model, `svet.cyklus()`, hodiny `hodiny.ted()` (větev `p0-2-testy`).
- `Databaze()` čte cestu až za běhu (dřív se při importu zamkla na skutečnou databázi – riziko pro testy).

## Rozhodnuto
- Kódy keyboxů: hlavní zdroj je aplikace úklidů; `keybox_kod` v YAML platí, jen když je `keybox_kod_overeno` novější.
- Sokolská: číslo bytu pro hosty (adresa v YAML) a název v aplikaci úklidů (`uklidy_nazev`) se liší – obojí je správně.
- Podpis „Rentys team“ + WhatsApp Simon a Michael; časy Vojtěšská check-in 15:00, check-out 11:00, ostatní 10:00.
- Dřívější check-in nabízet jen jako návrh ke schválení, i v ostrém režimu.
- Repo veřejné (podle zadání) – viz otevřené rozhodnutí v `DECISIONS.md` o citlivých datech v historii.

## Další
- Opravit 3 známé chyby z `tests/test_zname_chyby.py`: dotaz hosta přebitý automatickou zprávou Smoobu,
  ztracená eskalace při výpadku Telegramu (P1.5), kód současného hosta pro zítřejší příjezd.
- Timeout po úspěšném odeslání nechá návrh „čeká“ → druhé kliknutí pošle zprávu podruhé (test
  `test_timeout_po_odeslani_dnes_necha_navrh_cekat`) – řešit v bráně P1.4.
- P1.4: jedna brána pro odchozí zprávy hostům → modul `odchozi.py` (dnes `navrhy.odeslat`, ale přímé `send_message` je ještě
  v `prace._vyrid_jednu` pro ostrý režim).
- P1.5: fronta upozornění hostiteli (dnes `oznameni.posli` přímo; při výpadku Telegramu se upozornění ztratí).
- Kódy, Wi-Fi, adresy a časy dnes do instrukcí píše model podle YAML → přesunout do kódu (šablona + dosazení ze zdroje pravdy).
- Zprávy hostů: agent řeší jen poslední zprávu v konverzaci – starší neodpovězené (např. z výpadku Smoobu) se můžou ztratit.
- Existující funkce bez přepínače / se zapnutým výchozím stavem (napojení na úklidy, dřívější check-in, kontrola kalendáře)
  sladit s pravidlem „nová funkce = přepínač, výchozí vypnuto“.
- Simulátor scénářů: základ je fixture `svet` + `svet.cyklus()` + `hodiny.posun()`; rozšířit o scénáře.
- `server/nahrat-na-server.sh`: výpis `kontrola | head -6` uřízne řádek „Smoobu HMAC“ → zvětšit.
- WhatsApp čísla jsou v `znalostni-baze/obecne.yaml` (veřejné repo) → viz `DECISIONS.md`.

## Zaseknuté
- Citlivá data ve veřejném repu (telefonní čísla, jméno hosta v historii) – čeká na rozhodnutí hostitele (`DECISIONS.md`).
