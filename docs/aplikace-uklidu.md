# Napojení na aplikaci úklidů (uklid.kolbl-apartments.cz)

Aplikace nemá API. Agent se přihlásí vlastním účtem a čte stránku **/uklidy** (kód: `agent/uklidy.py`).

## Nastavení
- `.env`: `UKLIDY_URL`, `UKLIDY_LOGIN`, `UKLIDY_HESLO` (účet agenta, stačí mu číst /uklidy). Prázdné = vypnuto.
- Soubor bytu: `uklidy_nazev` = **přesný název bytu v aplikaci** (Petrská 303, Sokolská 403, Školská 3+1).
  Ostatní byty v aplikaci agent ignoruje. Když se byt v aplikaci přejmenuje, je potřeba upravit i `uklidy_nazev`.

## Co agent z aplikace čte
U každého pobytu: byt, datum odjezdu a úklidu, **kód** (pole „codes“, když ho někdo vyplní), stav **uklizeno**.

## Co s tím dělá
1. **Kódy – aplikace je hlavní zdroj.** Každých 10 minut (`UKLIDY_INTERVAL_MINUT`) agent aplikaci přečte.
   Když se u úklidu objeví nový kód, převezme ho (uloží do své databáze), ohlásí ve skupině a zneplatní
   čekající instrukce se starým kódem. Pak kód drží, dokud se v aplikaci neobjeví jiný.
2. `keybox_kod` v souboru bytu platí jen, když je `keybox_kod_overeno` novější než poslední zápis v aplikaci
   (třeba když hostitel kód opraví ručně). Když aplikace nejde přečíst, platí poslední známý kód.
3. **Pojistka před odesláním** instrukcí: kód se ověří ještě jednou těsně před odesláním.
4. **V den příjezdu ve 14:00** upozorní, když úklid před příjezdem není odkliknutý.
5. **Dřívější check-in:** k žádosti hosta přidá, jestli je byt uklizený (rozhoduje hostitel).
6. **Byt uklizený dřív:** když host přijíždí dnes, instrukce s kódem už má, check-in je od 15:00 a úklid je v aplikaci
   odkliknutý mezi `DRIVEJSI_CHECKIN_OD` (10:00) a 14:30, agent hostovi napíše, že může přijít hned
   (v režimu návrhů jen jako návrh ke schválení). Funguje jen pro byty, které jsou v aplikaci úklidů.

## Doporučení pro aplikaci
- Kód zapisovat do aplikace, kdykoli se na keyboxu změní (agent ho do 10 minut převezme).
- Neměnit vzhled/strukturu stránky /uklidy bez domluvy. Když agent stránku nepřečte, pošle upozornění
  a dál používá poslední známý kód.
