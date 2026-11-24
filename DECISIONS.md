# DECISIONS

Rozhodnutí, která může udělat jen hostitel. Každé s možnostmi; po rozhodnutí doplnit výsledek a datum.

## D1 – Citlivá data ve veřejném repozitáři (rozhodnuto 12. 10. 2026)
Repo `simonpavek-dev/BNBagent` je veřejné (při založení bylo soukromé). V repu je:
- v současném `znalostni-baze/obecne.yaml`: WhatsApp čísla Simona a Michaela (v podpisu a v `nouzove_kontakty`),
- v historii commitů (`65c9a7a` → smazáno v `6feb0d3`): jméno skutečné hostky v příkladu ve staré specifikaci API.
- e-mail a jméno autora ve všech commitech, interní ID bytů ve Smoobu a 2 ID rezervací (v historii).
Kódy, adresy, hesla ani klíče v historii nejsou (prověřeno grepem celé historie).

Možnosti:
- **A) Repo vrátit na soukromé** (GitHub → Settings → Danger zone → Change visibility). Nejrychlejší, nic se nemaže.
- **B) Nechat veřejné a vyčistit:** čísla přesunout z `obecne.yaml` mimo git (např. `.env` / soubor ignorovaný gitem),
  historii přepsat (`git filter-repo`) a force-push. Pozor: přepsání historie je nevratné a kopie (forky, cache)
  už mohou existovat – čísla by se tím z internetu jistě nesmazala.
- **C) Nechat veřejné, jen přesunout čísla mimo git** pro budoucnost; historii nechat.

Výsledek: **nechat všechno, jak je** – repo zůstává veřejné, historie se nepřepisuje, čísla zůstávají
v `obecne.yaml`. Nová data hostů do repa dál nesmí (pravidlo v CLAUDE.md).

## D2 – Výchozí stav existujících funkcí vs. pravidlo „nová funkce = přepínač, výchozí vypnuto“ (rozhodnuto 12. 10. 2026)
Napojení na aplikaci úklidů, nabídka dřívějšího check-inu a hodinová kontrola kalendáře běží bez vlastního přepínače.
Možnosti: A) doplnit přepínače, výchozí vypnuto, a na serveru je zapnout v `.env` (chování se nezmění);
B) nechat jak je a pravidlo platí jen pro nové funkce.

Výsledek: **A** – přepínače KONTROLA_KALENDARE, NABIDKA_DRIVEJSIHO_CHECKINU, HLIDANI_UKLIDU_K_PRIJEZDU,
OPRAVA_KODU_PO_UKLIDU, CHAT_PRES_TELEGRAM; HODNOCENI_HOSTU výchozí ne. Na serveru všechny zapnuté (chování beze změny).
Bez přepínače zůstávají bezpečnostní základy: fronta upozornění, brána, převzetí kódu z aplikace úklidů, vyřizování zpráv.

## D3 – Kód keyboxu pro hosta, před jehož příjezdem ještě neproběhl úklid (rozhodnuto 12. 10. 2026)
Instrukce se připravují večer předem / odcházejí v 10:00, úklid (a případná změna kódu) bývá až kolem poledne.
Možnosti: A) poslat instrukce až po odkliknutí úklidu (kód vždy správný, ale později);
B) poslat v 10:00 s aktuálním kódem a když se po úklidu kód změní, poslat hostovi opravu.

Výsledek: **B** – instrukce v 10:00 jako dosud; po změně kódu v aplikaci úklidů agent pošle hostům, kteří instrukce se
starým kódem už dostali, opravu s novým kódem (stejnou cestou jako instrukce – automaticky / ke schválení).

## D4 – Co dostane host, když se agent v ostrém režimu doptává hostitelů (21. 10. 2026)
Možnosti: A) hned krátkou průběžnou odpověď („podíváme se na to a brzy se ozveme“), hostitelé dostanou eskalaci
s návrhem; B) hostovi nic, dokud neodpoví hostitelé.

Výsledek: **A** (doporučení, hostitel schválil plán bez výhrady) – chování jako dosud. Změna = jen úprava v
`prace._vyrid_jednu` (ostrý režim posílá i `eskalovat`), kdykoli na pokyn hostitele.

## D5 – Podpis ve zprávách hostům (rozhodnuto 24. 11. 2026)
Dosud byl „Rentys team“ + WhatsApp Simon a Michael pod každou zprávou. Hostitel chce podpis jen při zahájení
a ukončení konverzace, ve tvaru „Rentys – …“.
Možnosti textu: A) „Rentys team“, B) „Rentys Prague“, C) „Rentys – Simon & Michael“ a pod tím WhatsApp čísla.
Instrukce k příjezdu (uprostřed konverzace): A) dál s plným podpisem, B) bez podpisu.

Výsledek: text **C**, instrukce **A** (s WhatsApp čísly). Podpis doplňuje kód (`podpis.py`, přepínač
`PODPIS_JEN_ZACATEK_A_KONEC`): první naše zpráva v konverzaci, zprávy po skončení pobytu, instrukce k příjezdu
a rozlučkové zprávy (P3.2). Text podpisu se mění v `obecne.yaml` na serveru (přes „Vasile, …“), ne v gitu.

## D6 – Zpráva před odjezdem, prosba o hodnocení a sleva na další pobyt (rozhodnuto 24. 11. 2026)
Hostitel navrhl 5% slevu na další pobyt výměnou za hodnocení. Pravidla recenzí Airbnb zakazují dávat cokoli
hodnotného (slevu, refundaci) výměnou za recenzi – hrozí smazání recenzí a omezení účtu; Booking má podobné pravidlo.
Možnosti: A) jen prosba o hodnocení, B) sleva pro všechny vracející se hosty nezávisle na recenzi, C) sleva za hodnocení.

Výsledek: zprávy rozdělit – **večer před odjezdem v 18:00** informace k check-outu, poděkování a nabídka slevy na
další pobyt; **v den odjezdu** zvlášť prosba o hodnocení. Podmínka, aby to bylo v pořádku: sleva nesmí záviset na
hodnocení – dostane ji každý vracející se host, texty na sebe neodkazují (zpráva o slevě nezmiňuje recenzi a naopak).
Uplatnění jen přes platformu (platba mimo Airbnb/Booking je v `nikdy`): host napíše před další rezervací a hostitelé
mu pošlou speciální nabídku na Airbnb. Slevu zmiňovat jen hostům z Airbnb (Booking individuální slevu jednoduše
neumí), prosba o hodnocení ve 12:00 v den odjezdu (po check-outu), pobyt na 1 noc bez večerní zprávy, prosba
o hodnocení po eskalaci během pobytu jen ke schválení – hostitel potvrdil 24. 11. („pokračuj“ po plánu P3.2).

## D7 – Doporučení podniků z Google Maps (rozhodnuto 24. 11. 2026)
Hostitel chce, aby agent na dotaz hosta sám prošel Google Maps v okolí bytu a doporučil top 3 podniky: hodnocení
aspoň 4 hvězdičky z rozumného počtu recenzí a otevírací doba, která sedí na den a čas, na který se host ptá.
Možnosti zdroje: A) Google Places API (New) – placené (35 $ / 1 000 dotazů, 1 000 měsíčně zdarma), spolehlivá data
o hodnocení a otevírací době; B) hledání na webu – zdarma, ale hodnocení a otevírací doby nespolehlivé; C) stahování
stránek Google Maps – porušuje podmínky Googlu.

Výsledek: **A** (plán schválen 24. 11.). Výchozí meze: hodnocení ≥ 4,0, ≥ 100 recenzí, ≤ 15 min pěšky (vše v `.env`).
Seznam vkládá kód (značka [TIPY Z MAP n]), model hodnocení ani otevírací doby nepíše. Klíč Google zakládá hostitel.
