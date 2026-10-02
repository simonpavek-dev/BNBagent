# Napojení na aplikaci úklidů (uklid.kolbl-apartments.cz)

Aplikace nemá API. Agent se přihlásí vlastním účtem a čte stránku **/uklidy** (kód: `agent/uklidy.py`).

## Nastavení
- `.env`: `UKLIDY_URL`, `UKLIDY_LOGIN`, `UKLIDY_HESLO` (účet agenta, stačí mu číst /uklidy). Prázdné = vypnuto.
- Soubor bytu: `uklidy_nazev` = **přesný název bytu v aplikaci** (Petrská 303, Sokolská 403, Školská 3+1).
  Ostatní byty v aplikaci agent ignoruje. Když se byt v aplikaci přejmenuje, je potřeba upravit i `uklidy_nazev`.

## Co agent z aplikace čte
U každého pobytu: byt, datum odjezdu a úklidu, **kód** (pole „codes“, když ho někdo vyplní), stav **uklizeno**.

## Co s tím dělá
1. **Po každém odkliknutém úklidu** zkontroluje kód:
   - stejný jako ve znalostní bázi → v pořádku,
   - chybí → připomene ve skupině, ať kód na keyboxu ověříte,
   - jiný → **kód hostům přestane posílat**, zneplatní čekající instrukce a zeptá se, který platí.
2. **Platný kód** je vždy `keybox_kod` v souboru bytu. `keybox_kod_overeno` = den, kdy jste kód naposledy ověřili;
   starší zápisy v aplikaci pak agent neřeší.
3. **Pojistka před odesláním** instrukcí: kód se ověří ještě jednou těsně před odesláním.
4. **V den příjezdu ve 14:00** upozorní, když úklid před příjezdem není odkliknutý.
5. **Dřívější check-in:** k žádosti hosta přidá, jestli je byt uklizený (rozhoduje hostitel).

## Doporučení pro aplikaci
- Při odkliknutí úklidu **vždy vyplnit kód** na keyboxu (i když se nezměnil) – jinak agent pokaždé připomíná.
- Neměnit vzhled/strukturu stránky /uklidy bez domluvy. Když agent stránku nepřečte, pošle upozornění
  a kódy hostům neposílá.
