# SCRATCHPAD

Pracovní poznámky mezi úkoly. Na začátku každého úkolu přečíst, na konci aktualizovat.

## Hotovo
- A1 (větev `p2-1-jen-sablona`): instrukce k příjezdu jen ze šablony; stará cesta přes model (`mozek.priprav_instrukce_k_prijezdu`)
  a přepínač `INSTRUKCE_ZE_SABLONY` odstraněny; chybějící údaj bytu = upozornění s návrhem.
- Zkrácené zprávy (větev `p1-7-zkracene-zpravy`): Smoobu usekne text od „<“ → brána „<“ nahradí („‹“), po odeslání
  ověří uloženou zprávu (`odchozi.zkraceno`, zkrácení = upozornění s celým zněním); Vasil má nástroj `odeslane_zpravy`;
  šipky ve Vojtěšské 2kk/1kk → ⬅️/➡️. Zasaženo 12., 14. a 18. 10. (3 hosté ve Vojtěšské 2kk).
- D2 přepínače (větev `p1-6-prepinace`): KONTROLA_KALENDARE, NABIDKA_DRIVEJSIHO_CHECKINU, HLIDANI_UKLIDU_K_PRIJEZDU,
  OPRAVA_KODU_PO_UKLIDU, CHAT_PRES_TELEGRAM (výchozí ne), HODNOCENI_HOSTU výchozí ne; test hlídá výchozí stav a .env.example.
- P1.4 brána `odchozi.py` (větev `p1-5-brana`): jediné `send_message`, tabulka `odchozi` (odesila/odeslano/selhalo/nejiste),
  po timeoutu ověření v konverzaci, nejisté se ověří v dalším cyklu; ostrý režim jde přes návrh a bránu.
- Opravy 3 chyb nasazeny (12. 10. 19:55), `cekajici_od` nastaveno, žádné staré dotazy se nevytáhly.
- Opraveny 3 známé chyby (větev `p1-4-zname-chyby`), žádný xfail:
  1) dotaz hosta za automatickou zprávou Smoobu se zpracuje (jen zprávy po nasazení – `cekajici_od`); návrh zastará,
     jen když host napsal znovu nebo někdo odpověděl PO vzniku návrhu;
  2) P1.5 fronta upozornění: `oznameni.posli` při výpadku Telegramu uloží do `fronta_upozorneni`, cyklus doručí
     (s poznámkou „Zpožděné upozornění“, u návrhů se spáruje tg_message_id → tlačítka fungují);
  3) varianta B (D3): po změně kódu v aplikaci úklidů dostanou hosté se starým kódem opravu (automaticky / ke schválení).
- P1.3 zdvořilosti bez modelu (`ZDVORILOSTI_BEZ_MODELU`, výchozí ne): čisté díky/👍/ok → hotová věta v jazyce hosta
  (8 jazyků, před/během/po pobytu); na naše rozloučení se neodpovídá (stav „neodpovidat“) (větev `p1-3-zdvorilosti`).
- P1.2 levnější model (`LEVNEJSI_MODEL_PRO_JEDNODUCHE`, výchozí ne): `trideni.je_jednoducha` – krátké, bez otázky,
  prosby a problému; na historii 4 ze 48 zpráv (jen čistá poděkování) (větev `p1-2-levnejsi-model`).
- P1.1 nasazeno a zapnuto na serveru (`INSTRUKCE_ZE_SABLONY=ano`, 12. 10.).
- P1.1 instrukce ze šablony (`INSTRUKCE_ZE_SABLONY`, výchozí ne): kódy/Wi-Fi/časy dosazuje kód, model jen překládá
  a překlad se ověřuje (jinak anglicky); adresa (`adresa_presna`), název a heslo Wi-Fi a kódy se před překladem
  nahradí značkami ⟦n⟧ – nikdy se nepřekládají; u všech 6 bytů `adresa_presna`, `adresa_doplnek_en`, `postup_en`,
  `odjezd.postup_en` (větev `p1-1-instrukce-sablona`).
- Smoobu jen přes HMAC, RFC 3986, 401 → okamžité upozornění, 429 jen u GET (`23243ce`, nasazeno na server, `kontrola` = OK).
- Odolnost smyčky: neúspěšné naplánované odeslání jen 1×, chyba v jednom kroku nezastaví ostatní (`97fb936`).
- Instrukce k příjezdu: před odesláním kontrola konverzace (už poslané → neposílat), po skončení pobytu neposílat (`6bcd822`).
- Kontrola kalendáře každou hodinu na rok dopředu, upozornění bez opakování (`65551f9`).
- Instrukce k příjezdu odchází samy v 10:00 (`PRIJEZDY_AUTOMATICKY=ano`), odpovědi hostům ke schválení (`REZIM=navrh`).
- Ovládání přes Telegram („Vasile…“), aplikace úklidů jako zdroj kódů, nabídka dřívějšího check-inu (vždy ke schválení).
- Testy: 22 zelených + 3 xfail; náhražky Smoobu/Telegram/model, `svet.cyklus()`, hodiny `hodiny.ted()` (větev `p0-2-testy`).
- `Databaze()` čte cestu až za běhu (dřív se při importu zamkla na skutečnou databázi – riziko pro testy).

## Rozhodnuto
- Adresy a názvy Wi-Fi sítí se nikdy nepřekládají – vždy v původním znění (hostitel, 12. 10.).
- Kódy keyboxů: hlavní zdroj je aplikace úklidů; `keybox_kod` v YAML platí, jen když je `keybox_kod_overeno` novější.
- Sokolská: číslo bytu pro hosty (adresa v YAML) a název v aplikaci úklidů (`uklidy_nazev`) se liší – obojí je správně.
- Podpis „Rentys team“ + WhatsApp Simon a Michael; časy Vojtěšská check-in 15:00, check-out 11:00, ostatní 10:00.
- Dřívější check-in nabízet jen jako návrh ke schválení, i v ostrém režimu.
- Repo veřejné, historie se nepřepisuje, WhatsApp čísla zůstávají v `obecne.yaml` (`DECISIONS.md` D1).

## Další
- Zprávy hostů: agent řeší nejnovější nezpracovanou zprávu hosta; víc nezodpovězených dotazů za sebou model vidí v konverzaci.
- Simulátor scénářů: základ je fixture `svet` + `svet.cyklus()` + `hodiny.posun()`; rozšířit o scénáře.
- `server/nahrat-na-server.sh`: výpis `kontrola | head -6` uřízne řádek „Smoobu HMAC“ → zvětšit.

## Zaseknuté
- (nic)
