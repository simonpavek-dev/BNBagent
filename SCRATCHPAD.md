# SCRATCHPAD

Pracovní poznámky mezi úkoly. Na začátku každého úkolu přečíst, na konci aktualizovat.

## Hotovo
- P4.1 (větev `p4-1-prehled-status`): `/status` (`PRIKAZ_STATUS`, `stav_bytu.py`) – obsazenost + kód domu a bytu,
  smazání po 15 min i s příkazem (`smazat_zpravy` v nastavení, mazání v každém cyklu, max 47 h); `/prehled` a nedělní
  přehled v 19:00 (`TYDENNI_PREHLED`, `prehled.py`, 1 volání modelu týdně); příkazy se registrují v Telegramu při startu;
  text začínající „/“ už nikdy není text pro hosta (ani při ✏️). Nový scénář v simulátoru (týden hostitelů).
- Smoobu `/api/reservations` bez parametru `from` vrací jen neskončené pobyty (výchozí from = dnes) – minulé
  (od 27. 8. 2026, všechny s `reference-id`) jen s `from`. Proto je v `server/export_analyzy.py` sekce
  `odjezdy_smoobu` prázdná – opravit při další práci na exportu.
- 27. 11. 9:22 nasazeno P3.1–P3.4 (main `cfe2dcd`): zapnuto `PODPIS_JEN_ZACATEK_A_KONEC`, `ZPRAVA_PRED_ODJEZDEM`,
  `PROSBA_O_HODNOCENI`; `SLEVA_NA_DALSI_POBYT_PROCENT` zatím 0 (5 % čeká na výslovný souhlas hostitele);
  `DOPORUCENI_PODNIKU` vypnuto (chybí klíč Google). Podpis na serveru: první řádek „Rentys – Simon & Michael“
  (záloha `data/obecne.yaml.zaloha-2026-11-27`). První cykly bez chyb.
- P3.3 doporučení podniků (větev `p3-3-doporuceni-podniku` z `p3-2-rozlouceni`, `podniky.py`, DECISIONS D7):
  nástroj `doporuc_podniky` jen s `DOPORUCENI_PODNIKU=ano` a `GOOGLE_MAPS_API_KEY`; Places API (New) Text Search kolem
  bytu, filtr kódem (≥ 4,0, ≥ 100 recenzí, v provozu, otevřeno v čase dotazu – do 7 dní currentOpeningHours, přes
  půlnoc i nonstop, ≤ 15 min pěšky přes OSRM), pořadí bayesovsky vážené; seznam přes značku [TIPY Z MAP n]
  (`mozek._zavolej` → `_doplnky` → `prace.zeptej_se_modelu` → `znacky.zpracuj`); značka bez nástroje = ke kontrole.
  Skutečné volání Googlu netestováno (žádný klíč) – po nasazení vyzkoušet `zkouska` s dotazem na restauraci.
  Při nasazení: na serveru `DOPORUCENI_PODNIKU=ano` + `GOOGLE_MAPS_API_KEY`, `kontrola` ukáže, jestli klíč je.
- P3.2 zprávy k odjezdu (větev `p3-2-rozlouceni` z `p3-1-podpis`, `odjezdy.py`, DECISIONS D6): `ZPRAVA_PRED_ODJEZDEM`
  (18:00 den před odjezdem: check-out + `odjezd.postup_en`, poděkování, Airbnb sleva `SLEVA_NA_DALSI_POBYT_PROCENT`),
  `PROSBA_O_HODNOCENI` (12:00 v den odjezdu; po eskalaci během pobytu jen ke schválení). Připraví se 2 h předem
  s ❌ Zrušit odeslání, po výpadku agenta nejvýš 3 h pozdě; 1 noc = bez večerní zprávy; když host ten den už dostal
  zprávu na stejné téma (Smoobu), neposílá a hlásí. Podpis vždy. Zapnuto i v simulátoru scénářů (sleva 5 %).
  Při nasazení na serveru: `ZPRAVA_PRED_ODJEZDEM=ano`, `SLEVA_NA_DALSI_POBYT_PROCENT=5`, `PROSBA_O_HODNOCENI=ano`
  a ve Smoobu vypnout automatické zprávy č. 5 a 6 (pokud jsou zapnuté).
- P3.1 podpis (větev `p3-1-podpis`, `PODPIS_JEN_ZACATEK_A_KONEC`, `podpis.py`, DECISIONS D5): podpis nepíše model,
  kód ho doplní do první naší zprávy v konverzaci, do zpráv po skončení pobytu a do instrukcí (vždy); jinde ho
  odstraní i s pozdravem. Platí pro odpovědi modelu, zdvořilosti, ✏️ texty hostitelů, návrhy od Vasila z Telegramu,
  nabídku dřívějšího check-inu a opravu kódu. Zapnuto i v simulátoru scénářů (`NA_SERVERU`).
  Při nasazení: na serveru `PODPIS_JEN_ZACATEK_A_KONEC=ano` a v `obecne.yaml` první řádek podpisu změnit na
  „Rentys – Simon & Michael“ přes Telegram („Vasile, …“) – ne v gitu (nasazení by přepsalo úpravy KB ze serveru).
- Dávky zpráv (větev `p2-7-davky-zprav`, `POCKAT_NA_DALSI_ZPRAVY`): po zprávě hosta 5 min čekání (každá další
  zpráva odpočet obnoví, nejdéle 15 min od první, naléhavé hned – `trideni.je_nalehava`), pak jedna odpověď na celou
  dávku; všechny zprávy dávky se označí stejným stavem; hlavní smyčka se probudí přesně (`prace.konec_cekani`).
  Nasazeno a zapnuto na serveru 23. 10. 20:03 (main `c06cde0`), první cykly bez chyb.
- 21. 10. 17:13 nasazeno (main `d0e0529`) a přepnuto na `REZIM=ostre`, `HLASIT_AUTOMATICKE_ODPOVEDI=ano`;
  `INSTRUKCE_ZE_SABLONY` z `.env` odstraněn; v DB serveru není `rezim` (platí `.env`). První cykly bez chyb.
- A2 (větev `p2-6-simulator-scenaru`): `tests/test_scenare.py` – cesta hosta (dotaz → instrukce 10:00 → změna kódu
  + oprava → díky → Wi-Fi přes značku → sleva/eskalace → odjezd), výpadek Smoobu 503 + Telegramu, timeout při odeslání,
  zkrácená zpráva; vše v režimu návrhů i ostrém. Ověřeno, že rozbitá pojistka scénáře shodí.
- B6 (větev `p2-5-hlaseni-odpovedi`): `HLASIT_AUTOMATICKE_ODPOVEDI=ano` → po každé automatické odpovědi
  oznámení do skupiny (zpráva hosta + odpověď, bez tlačítek).
- B5 (větev `p2-4-pojistka-smycky`): v ostrém režimu nejvýš 4 automatické odpovědi na zprávy hosta jedné rezervaci
  za 24 h (`prace.MAX_AUTOMATICKYCH_ZA_DEN`), další jen ke kontrole; instrukce k příjezdu a opravy kódu se nepočítají.
- B4 (větev `p2-3-znacky-kodu`): model u odpovědí hostům nevidí ani nepíše kódy a Wi-Fi – dostane značky
  [KÓD BYTU]/[KÓD DOMU]/[WIFI SÍŤ]/[WIFI HESLO], hodnoty dosadí `znacky.py`; zbylá značka nebo 4–8místné číslo
  = odpověď jen ke kontrole („🔔 ZKONTROLUJ ODPOVĚĎ“), ✅ se zbylou značkou neodešle. Bez přepínače – vynucuje
  nepřekročitelné pravidlo z CLAUDE.md.
- A3 (větev `p2-2-vypis-nasazeni`): `nahrat-na-server.sh` vypíše celou `kontrola` (dřív `head -6` uřízl „Smoobu HMAC“).
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
- Analýza eskalací a úprav návrhů → doplnění KB: hostitel nechce SSH klíč z Windows PC, data pošle z Macu.
  Export `server/export_analyzy.py` (jen čte, anonymizovaný JSON, větev `p3-4-analyza`) – spustit z Macu
  (příkaz v hlavičce skriptu), soubor `vasil-export.json` přenést na Windows PC. Do gitu nesmí.
  Export obsahuje i zprávy po odjezdu → ověřit, že Smoobu neposílá vlastní zprávy #5/#6 (navody/automaticke-zpravy.md).
- C8: sledovat první automatické odpovědi (odchozi zdroj=automaticky, „🔔 ZKONTROLUJ“, eskalace) a dát přehled.
- Zprávy hostů: agent řeší nejnovější nezpracovanou zprávu hosta; víc nezodpovězených dotazů za sebou model vidí v konverzaci.

## Zaseknuté
- (nic)
