# AI agent pro apartmány (Vasil)

Python 3.9+, `agent/` = kód, `znalostni-baze/` = YAML pro model, běží na serveru Hetzner (`server/`).
Komunikace s hostitelem česky, kód a komentáře česky.

## Postup při změnách kódu
1. **Nejdřív test**, který chybu/požadavek zachytí (`tests/`, pytest) – musí nejdřív selhat.
2. Pak oprava.
3. `.venv/bin/python -m pytest` musí být zelený.
4. Commit na **vlastní větev** (např. `ps-1-…`), **nepushovat do `main`** a nenasazovat na server bez souhlasu.

## Tajné údaje
- `.env` obsahuje klíče (Smoobu, Claude, Telegram, aplikace úklidů). **Hodnoty nikdy nečíst ani nevypisovat** –
  pracovat jen s názvy proměnných (např. `grep -c '^SMOOBU_API_SECRET=.' .env`).
- Testy používají jen smyšlené hodnoty.
- Na GitHub nesmí: `.env`, `data/`, soubory skutečných bytů v `znalostni-baze/apartmany/`, `poznamky-k-hostum.yaml`.

## Smoobu
- Jen HMAC ověřování (hlavičky X-API-Key, X-Timestamp, X-Nonce, X-Signature); staré `Api-Key` Smoobu vypíná 31. 10. 2026.
- Query string pro podpis i URL: RFC 3986, klíče seřazené abecedně (mezera `%20`, `[]` → `%5B%5D`).
- 429: u GET počkat do `X-RateLimit-Retry-After` (Unix čas) a zopakovat; POST (odeslání zprávy) nikdy neopakovat.

## Nasazení
`server/nahrat-na-server.sh <IP>` – nejdřív stáhne změny znalostní báze provedené přes Telegram, pak nahraje a restartuje.
