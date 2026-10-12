# LESSONS LEARNED

Co nás stálo čas (přes 10 minut) a jak se tomu příště vyhnout.

## Kód keyboxu ze znalostní báze byl zastaralý (Sokolská, 27. 9. a 1. 10.)
Dva hosté dostali nefunkční kód, protože uklízečky kód změnily a YAML o tom nevěděl.
→ Zdroj pravdy pro kódy je aplikace úklidů; YAML jen s datem ověření. Před odesláním instrukcí kód ověřit znovu.

## Výpadek Smoobu zablokoval celou smyčku (8.–12. 10.)
Jedna neodeslatelná naplánovaná zpráva se zkoušela každé 3 minuty (1 187×) a výjimka zastavila kalendář i hodnocení.
→ Každý krok smyčky izolovaně (`_krok`), neúspěšné odeslání jen 1× a předat hostitelům.

## Po opravě odešla fronta starých zpráv pozdě
Po odblokování se odeslaly instrukce, které čekaly od minulých dnů (2 hosté je dostali pozdě).
→ Před nasazením opravy fronty projít naplánované zprávy; prošlé neposílat; instrukce jen když host kód ještě nemá
a pobyt neskončil.

## Konec zkušební verze Smoobu odpojil Airbnb
Kanál Airbnb zůstal „Not fully connected“, zprávy hostům z Airbnb padaly na „recipient isEmpty“ a nové rezervace
se nenačítaly (riziko overbookingu).
→ Po změně předplatného Smoobu zkontrolovat Channels (oba kanály Connected, mapování, Price Sync).

## Test spustil skutečného agenta (12. 10.)
Test `spustit` proti starému kódu rozběhl smyčku se skutečnými klíči z `.env` (Smoobu naštěstí odmítlo ověření).
→ `tests/conftest.py`: smyšlené klíče, vypnutý Telegram, zákaz sítě. Testy smyček vždy s pojistkou proti nekonečnému běhu.

## Úprava přes Telegram rozbila párování s aplikací úklidů (7. 10.)
Pokyn „změň číslo bytu všude“ přepsal i `uklidy_nazev`, i když aplikace úklidů byt vede pod původním názvem.
→ Technické klíče (párovací názvy, ID) od popisných údajů oddělit; nástroje správce by je neměly měnit bez kontroly.

## X-RateLimit-Retry-After je Unix čas, ne sekundy
→ Vždy číst dokumentaci API, ne odhadovat význam hlavičky podle názvu.

## Nasazení přepisovalo změny znalostní báze z Telegramu
→ `nahrat-na-server.sh` nejdřív stáhne novější soubory ze serveru (`rsync -au --existing`).
