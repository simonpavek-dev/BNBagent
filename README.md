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
