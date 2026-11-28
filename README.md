# AI agent pro Airbnb a Booking (přes Smoobu)

Agent hlídá zprávy od hostů ve Smoobu a za tebe:
- **odpovídá hostům** podle znalostní báze, kterou mu vyplníš,
- **pošle ti upozornění na Telegram**, když si neví rady nebo jde o citlivou věc (sleva, storno, stížnost, škoda…),
- **připraví návrh hodnocení hosta** po odjezdu (Airbnb), který jen zkopíruješ.

Automatické zprávy řeší přímo Smoobu (`navody/automaticke-zpravy.md`), ceny řeší PriceLabs (`navody/cenotvorba-pricelabs.md`).

```
Host napíše na Airbnb/Booking → Smoobu → agent (každé 3 min) → Claude rozhodne
      ├─ ví odpověď       → odpoví hostovi
      ├─ neví / citlivé   → hostovi „ověřím a ozvu se“ + tobě upozornění s návrhem odpovědi
      └─ jen „děkuji“     → nic
```

## Struktura
| Soubor / složka | Co to je |
|---|---|
| `znalostni-baze/obecne.yaml` | tón, podpis, **kdy tě má agent volat**, co nesmí nikdy dělat |
| `znalostni-baze/apartmany/apt-01…10.yaml` | informace o každém bytě (check-in, kódy, Wi-Fi, parkování, pravidla, FAQ) |
| `znalostni-baze/apartmany/_priklad.yaml` | vyplněný vymyšlený příklad na vyzkoušení |
| `poznamky-k-hostum.yaml` | poznámky od úklidu k pobytům (pro hodnocení hostů) |
| `.env` | klíče a nastavení (nikomu neposílej) |
| `data/` | databáze a log všeho, co agent udělal |
| `agent/` | kód agenta |

## Zprovoznění krok za krokem

### 1. Vyplň znalostní bázi
Otevři `znalostni-baze/obecne.yaml` a pak `apartmany/apt-01.yaml` atd. Inspiruj se v `_priklad.yaml`.
Soubory můžeš přejmenovat (třeba `vinohrady.yaml`). Na názvu nezáleží, důležité je `smoobu_id` uvnitř.
Nepotřebné soubory (máš-li méně bytů) smaž.

### 2. Klíč ke Claude API
Na **console.anthropic.com** si založ účet, nabij kredit (stačí 20 $ na začátek) a vytvoř API klíč.
Vlož ho do `.env` na řádek `ANTHROPIC_API_KEY=`.

### 3. Vyzkoušej agenta nanečisto (bez Smoobu)
V Terminálu ve složce projektu:
```bash
.venv/bin/python -m agent zkouska _priklad "Dobrý den, kde můžeme zaparkovat?"
```
Vyzkoušej různé dotazy, například na slevu, pozdní check-out, kódy s `--prijezd-za 5` / `--prijezd-za 0` nebo angličtinu.
Když agent odpoví špatně, doplň nebo oprav znalostní bázi.

### 4. Telegram pro upozornění
1. V Telegramu napiš **@BotFather** → `/newbot` → pojmenuj bota. Dostaneš **token**, vlož ho do `.env` jako `TELEGRAM_BOT_TOKEN`.
2. Napiš svému novému botovi jakoukoli zprávu.
3. Napiš **@userinfobot**. Odpoví ti tvým **ID**, vlož ho jako `TELEGRAM_CHAT_ID`.

### 5. Propojení se Smoobu
1. Ve Smoobu otevři nastavení v sekci **API / pro vývojáře** a vytvoř API klíč a secret. Vlož je do `.env`.
2. Vypiš si ID apartmánů a doplň je do souborů jako `smoobu_id`:
   ```bash
   .venv/bin/python -m agent apartmany
   ```
3. Zkontroluj, že je vše vyplněné:
   ```bash
   .venv/bin/python -m agent kontrola
   ```

### 6. Spusť agenta v režimu návrhů
V `.env` nech `REZIM=navrh`. Agent pak hostům **nic neposílá**, jen ti na Telegram posílá, co by odpověděl.
```bash
.venv/bin/python -m agent spustit
```
Na zprávy z doby před spuštěním agent neodpovídá, ty vyřídíš sám. Nech ho tak běžet týden a sleduj návrhy.

### 7. Ostrý provoz
Když jsou návrhy dobré, přepni v `.env` na `REZIM=ostre` a agenta restartuj (Ctrl+C a znovu `spustit`).

## Instrukce k příjezdu ze šablony
Zprávu k příjezdu skládá vždy kód podle rámce `sablona_zpravy_k_prijezdu` v `obecne.yaml`:
kódy, Wi-Fi, adresu (`adresa_presna` – nikdy se nepřekládá, + `adresa_doplnek_en`), postup (`postup_en` / `zprava_k_prijezdu`) a časy dosadí ze zdroje pravdy.
Anglicky mluvící host ji dostane bez modelu; jiným ji model přeloží. Adresu, název a heslo Wi-Fi a kódy model vůbec
nevidí (dostane místo nich značky ⟦1⟧…) – po překladu se vrátí v přesném původním znění; když značka chybí, jde anglická verze.
Chybí-li bytu údaj (Wi-Fi, postup…), instrukce se nepošlou a hostitelé dostanou upozornění s návrhem.

## Kódy a Wi-Fi v odpovědích hostům
Model skutečné kódy ani Wi-Fi nevidí: ve znalostní bázi i v konverzaci je dostane jako značky `[KÓD BYTU]`, `[KÓD DOMU]`,
`[WIFI SÍŤ]`, `[WIFI HESLO]` a stejně je napíše do odpovědi. Skutečné hodnoty dosadí agent (kód keyboxu z aplikace úklidů,
zbytek ze znalostní báze). Když v odpovědi zůstane značka bez hodnoty nebo číslo, které vypadá jako kód, agent ji sám
nepošle a dá ji hostitelům ke kontrole.

## Víc zpráv hosta za sebou = jedna odpověď
S `POCKAT_NA_DALSI_ZPRAVY=ano` agent po zprávě hosta počká `POCKAT_NA_DALSI_ZPRAVY_MINUT` (5 minut), jestli host
nenapíše ještě něco. Každá další zpráva odpočet spustí znovu; pak agent odpoví na všechny jednou zprávou (v Telegramu
jsou u návrhu všechny zprávy hosta pohromadě). Nejdéle čeká 15 minut od první zprávy. Naléhavé zprávy (voda, oheň,
kouř, plyn, host se nedostane dovnitř, nefunguje kód – 8 jazyků) vyřídí hned. Čas měří i podle vlastních hodin,
takže jiné časové pásmo v datech Smoobu čekání nerozbije.

## Podpis jen na začátku a na konci konverzace
S `PODPIS_JEN_ZACATEK_A_KONEC=ano` podpis (`hostitel.podpis` v `obecne.yaml`) nepíše model, ale doplní ho agent:
- do první zprávy, kterou hostovi v konverzaci posíláme (když konverzaci zahájila automatická zpráva Smoobu, už ne),
- do zpráv po skončení pobytu (den po odjezdu a později),
- do instrukcí k příjezdu vždy (host u dveří má po ruce WhatsApp).

Ostatní odpovědi, odpovědi na „díky“, oprava kódu i texty hostitelů přes ✏️ jsou bez podpisu. Když model nebo hostitel
podpis přesto napíše, agent ho z konce zprávy odstraní i s pozdravem před ním („Best regards,“).

## Zprávy k odjezdu: rozloučení, sleva a prosba o hodnocení
- `ZPRAVA_PRED_ODJEZDEM=ano`: večer před odjezdem v `ZPRAVA_PRED_ODJEZDEM_HODINA` (18:00) odejde hostovi připomínka
  check-outu (čas a `odjezd.postup_en` ze znalostní báze), poděkování a hostům z Airbnb nabídka slevy
  `SLEVA_NA_DALSI_POBYT_PROCENT` na další pobyt (host napíše před rezervací, vy mu pošlete speciální nabídku na Airbnb).
  Pobyt na 1 noc ji nedostane (check-out má v instrukcích).
- `PROSBA_O_HODNOCENI=ano`: v den odjezdu v `PROSBA_O_HODNOCENI_HODINA` (12:00, po check-outu) poděkování a prosba
  o hodnocení. Když host během pobytu eskaloval (stížnost, porucha…), přijde vám jen ke schválení.

Sleva **nesmí záviset na hodnocení** (pravidla recenzí Airbnb a Bookingu, `DECISIONS.md` D6) – proto jsou to dvě
zprávy, které na sebe neodkazují. Obě se připraví 2 hodiny předem a do skupiny přijde oznámení s ❌ Zrušit odeslání.
Text skládá agent ze šablony (anglicky, jinému jazyku ji model přeloží jako instrukce); šablony jde přepsat v
`obecne.yaml` klíči `sablona_zpravy_pred_odjezdem`, `sablona_slevy_na_dalsi_pobyt`, `sablona_prosby_o_hodnoceni`.
Když host ten den už od nás zprávu na stejné téma dostal (třeba automatickou zprávu Smoobu), agent ji nepošle a dá
vědět – ve Smoobu proto vypněte automatické zprávy č. 5 a 6 z `navody/automaticke-zpravy.md`.

## Příkaz /status – stav bytů a kódy
S `PRIKAZ_STATUS=ano` stačí ve skupině napsat `/status` a Vasil hned pošle stav všech bytů – 🔴 obsazeno (do kdy),
🟡 dnes odjezd / příjezd, 🟢 volno (do dalšího příjezdu) – a kódy ke dveřím: 🚪 dům (znalostní báze) a 🔑 byt (kód, který
je teď na keyboxu, z aplikace úklidů; v den úklidu i kód platný do úklidu). Zpráva se po 15 minutách smaže i s příkazem,
aby kódy nezůstaly v historii skupiny. Funguje jen ve vaší skupině.

## Nedělní přehled
S `TYDENNI_PREHLED=ano` přijde každou neděli v `TYDENNI_PREHLED_HODINA` (19:00) přehled za posledních 7 dní: kolik zpráv
přišlo a kolik jich Vasil vyřídil sám, kde vás potřeboval (dotaz hosta, proč to nezvládl, jak to dopadlo) a doporučení,
co doplnit do znalostní báze, aby to příště zvládl sám – i s hotovou větou „Vasile, do … doplň: …“. Věci, o kterých
musíte rozhodnout vy (slevy, stížnosti, výjimky), doplnit nedoporučí. Kdykoli na požádání: příkaz `/prehled`.

## Hlídání Sněmovny
S `HLIDANI_LEGISLATIVY=ano` Vasil hlídá Poslaneckou sněmovnu (otevřená data psp.cz) kvůli všemu, co může omezit krátkodobé
ubytování: eTurista a evidence hostů, registrace bytů (i nařízení EU 2024/1028), limit nocí a regulace obcemi, kolaudace
a změna užívání, pravomoci Prahy, poplatek z pobytu, SVJ. Data stahuje v `LEGISLATIVA_HODINY` (7 a 19 h), u každého
návrhu zákona prohledá jeho plný text (PDF) a stenozáznamy jednání; model shrne jen to, kde se témata opravdu objeví.
Do skupiny přijde „🏛️ SNĚMOVNA …“: nový návrh, který se vás týká, každý krok projednávání, zařazení na program schůze
a co zaznělo v rozpravě; v pondělí v `LEGISLATIVA_SOUHRN_HODINA` (8:00) souhrn. Při spuštění přijde přehled stavu k dnešku.

## Doporučení podniků z Google Maps
S `DOPORUCENI_PODNIKU=ano` a klíčem `GOOGLE_MAPS_API_KEY` agent na dotaz hosta („kam na večeři?“, „dobrá kavárna
na zítřek ráno?“) prohledá Google Maps kolem bytu a doporučí až 3 podniky, které:
- mají hodnocení aspoň `DOPORUCENI_MIN_HODNOCENI` (4,0) z aspoň `DOPORUCENI_MIN_RECENZI` (100) recenzí,
- jsou otevřené v den a čas, na který se host ptá (do 7 dní včetně svátků a výjimek podle Googlu),
- jsou nejvýš `DOPORUCENI_MAX_PESKY_MIN` (15) minut pěšky.

Pořadí je podle hodnocení váženého počtem recenzí. Seznam vkládá do zprávy kód (model hodnocení ani otevírací doby
nepíše), např.:
```
📍 Google Maps
1. Pizza Test – ⭐ 4.8 (2 000) · 🚶 4 min · 🕒 11:00–23:00
https://maps.google.com/?cid=…
```
Když nic nevyhoví, Vasil se zeptá vás. Klíč: console.cloud.google.com → APIs & Services → zapnout **Places API (New)**
→ Credentials → API key (omezit jen na Places API). Cena 35 $ za 1 000 dotazů, prvních 1 000 měsíčně zdarma.

## Hlášení automatických odpovědí
S `HLASIT_AUTOMATICKE_ODPOVEDI=ano` přijde po každé odpovědi, kterou agent v ostrém režimu poslal sám, do skupiny
„✅ Vasil odpověděl hostovi sám“ se zprávou hosta i odpovědí – máte přehled a můžete případně opravit ručně.

## Pojistka proti zacyklení
V ostrém režimu agent jedné rezervaci pošle sám nejvýš 4 odpovědi za 24 hodin. Další odpověď dostanou hostitelé
ke schválení („🔔 ZKONTROLUJ ODPOVĚĎ“), aby si agent s hostem (nebo s jiným robotem) nepsali donekonečna.

## Úspora tokenů
- `ZDVORILOSTI_BEZ_MODELU=ano`: čisté „díky / 👍 / ok“ vyřídí pravidlo bez modelu (hotové věty v 8 jazycích).
- `LEVNEJSI_MODEL_PRO_JEDNODUCHE=ano`: krátké zprávy bez otázky a prosby (např. čas příjezdu) vyřídí `MODEL_JEDNODUCHE`.

## Ovládání přes Telegram
Ve skupině stačí Vasila oslovit – zpráva začínající „Vasile“ (nebo zmínka @bota či odpověď na jeho zprávu):
- „Vasile, jaké kódy teď posíláš?“ · „Vasile, kdo přijíždí tento týden?“ · „Vasile, jak je na tom Petrská s úklidem?“
- „Vasile, do Školské doplň, že je tam kávovar na kapsle Nespresso.“ (upraví znalostní bázi, ukáže změnu)
- „Vasile, napiš hostovi ve Vojtěšské 2+1, že…“ (připraví návrh – odešle se až po ✅)
Ostatní zprávy ve skupině Vasil ignoruje. Změny znalostní báze z Telegramu jsou na serveru;
`server/nahrat-na-server.sh` si je před nahráním stáhne zpět.

## Kde bude agent běžet
- **Na začátek na tvém Macu.** Funguje, jen když je Mac zapnutý a nespí.
  - Spuštění: dvojklik na `spustit-agenta.command` (otevře okno Terminálu, nech ho otevřené/minimalizované).
  - Automaticky po zapnutí Macu: Nastavení systému → Obecné → Otevřít po přihlášení → **+** → vyber `spustit-agenta.command`.
  - Agent nemůže běžet dvakrát – druhé spuštění se samo ukončí.
- **Pro trvalý provoz na malém serveru** (Hetzner, DigitalOcean, cca 5 €/měsíc), který běží 24/7:
  1. Založ server s Ubuntu 24.04 a při zakládání mu přidej svůj SSH klíč (`cat ~/.ssh/id_ed25519.pub`).
  2. První přesun (zastaví agenta na Macu, přenese klíče, znalostní bázi i databázi):
     ```bash
     server/nahrat-na-server.sh IP_SERVERU --prvni
     ```
  3. Po každé změně znalostní báze nebo kódu stačí `server/nahrat-na-server.sh IP_SERVERU`.
  4. Ovládací panel: `ssh -N -L 8765:localhost:8765 root@IP_SERVERU` a v prohlížeči http://localhost:8765.
     Log: `ssh root@IP_SERVERU journalctl -u airbnb-agent -f`.
  - Agent nesmí běžet zároveň na Macu i na serveru. Po přesunu už `spustit-agenta.command` nespouštěj.
  - Export pro analýzu (co agent neví, eskalace, úpravy návrhů): `server/export_analyzy.py`, příkaz je v jeho
    hlavičce. Jen čte, jména hostů, kontakty a kódy nahradí značkami. Výsledný soubor do repa nepatří.

## Náklady
- Smoobu: podle ceníku, na 10 bytů cca 100–150 €/měsíc
- PriceLabs: cca 20 $/byt/měsíc (volitelné)
- Claude API: podle počtu zpráv, řádově jednotky až nízké desítky dolarů měsíčně.
  Levnější model nastavíš v `.env` přes `MODEL=claude-sonnet-5`.

## Bezpečnost
- Soubor `.env` a znalostní báze obsahují kódy a klíče. Neposílej je nikomu a nedávej je na internet.
- Agent se nenechá přemluvit hostem („majitel mi slíbil slevu…“). Takové zprávy eskaluje.
- Všechno, co agent udělal, je v `data/agent.log` a v databázi `data/agent.db`.

## Instalace na novém Macu
```bash
cd ~/Desktop/airbnb-agent
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```
Pak do `.env` vyplň vlastní klíče (Smoobu, Claude, Telegram) a do `znalostni-baze/` svoje byty
(`python -m agent nacist-smoobu` je předvyplní ze Smoobu). Ověření: `.venv/bin/python -m agent kontrola`.

## Kódy keyboxů
V souboru bytu: `keybox_kod` = kód. Když se kód nemění, nech `keybox_kod_plati_pro_rezervaci` prázdné.
Když ho měníš u každé rezervace o +1010, vyplň ID rezervace ze Smoobu, pro kterou kód platí.

## Testy
```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```
Testy běží bez internetu a bez `.env` (náhražky Smoobu, Telegramu a modelu v `tests/nahrazky.py`).
