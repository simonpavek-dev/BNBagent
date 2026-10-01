# API aplikace úklidů pro AI agenta (verze 1)

Aplikace: **https://uklid.kolbl-apartments.cz** (Next.js)

Agent „Vasil“ odpovídá hostům na Airbnb/Booking přes Smoobu. Z aplikace úklidů potřebuje číst
kódy keyboxů, jestli je byt uklizený, a co uklízečka zjistila (škody, zapomenuté věci…).

- API je **jen pro čtení** – agent v aplikaci nic nemění.
- Adresy: `https://uklid.kolbl-apartments.cz/api/v1/…`
- Formát: JSON, UTF-8. Časy ISO 8601 s časovou zónou (`2026-10-01T11:42:00+02:00`), data `YYYY-MM-DD`.
- Agent se ptá zhruba každé 3 minuty – stačí obyčejné GET dotazy, žádné webhooky.
- Vracej **všechny byty** – agent si sám vybere jen ty, které má ve Smoobu (teď Petrská, Sokolská, Školská 3+1).
  Páruje je podle názvu (`name`), takže **název bytu v aplikaci prosím neměňte** (nebo dej vědět).

## Jak to v Next.js udělat

Dva Route Handlery, např. `app/api/v1/apartments/route.ts` a `app/api/v1/cleanings/route.ts`:

```ts
export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const auth = req.headers.get("authorization") ?? "";
  if (auth !== `Bearer ${process.env.AGENT_API_KEY}`) {
    return Response.json({ error: "unauthorized" }, { status: 401 });
  }
  // … načíst z databáze a vrátit Response.json({ apartments: [...] })
}
```

- **Middleware / ochrana přihlášením:** cesty `/api/v1/*` musí projít bez session (teď všechno
  přesměrovává na `/login`). Chrání je jen API klíč.
- `AGENT_API_KEY` = náhodný řetězec min. 32 znaků (např. `openssl rand -hex 32`) v proměnných prostředí
  serveru. Stejnou hodnotu pošli Šimonovi – vloží ji agentovi do nastavení.
- Klíč porovnávej v konstantním čase (`crypto.timingSafeEqual`), pokud to jde.

## Změna v aplikaci pro uklízečky (důležité!)

Při **odkliknutí hotového úklidu** musí uklízečka povinně potvrdit kód na keyboxu. Bez toho úklid nejde dokončit:

```
Kód na keyboxu:   ( ) Sedí – je nastavený 1234
                  ( ) Změnil(a) jsem ho na: [____]
```

- „Sedí“ → u úklidu `keybox.status = "confirmed"`, u bytu se uloží čas a jméno potvrzení.
- „Změnil(a)“ → nový kód se uloží jako **aktuální kód bytu**, u úklidu `keybox.status = "changed"`
  a `previous_code` = starý kód. Kód: 3–8 číslic.
- Starší úklidy bez potvrzení mají `keybox.status = "not_checked"`.
- Bytu jde kód nastavit i v adminu (např. při výměně keyboxu) – i tak se mění `keybox_code`.

## 1. Byty a jejich aktuální kódy

`GET /api/v1/apartments`

```json
{
  "apartments": [
    {
      "id": 7,
      "name": "Školská 3+1",
      "keybox_code": "1234",
      "keybox_code_changed_at": "2026-09-20T12:10:00+02:00",
      "keybox_code_confirmed_at": "2026-09-30T11:42:00+02:00",
      "keybox_code_confirmed_by": "Jana"
    }
  ]
}
```

- `id` = ID bytu v aplikaci (na něj odkazují úklidy).
- `keybox_code` = kód, který na keyboxu **teď** je (po posledním potvrzení/změně). Byty bez keyboxu: `null`.
- Volitelně `smoobu_id` (ID apartmánu ve Smoobu) – když ho aplikace zná, agent páruje podle něj místo názvu.

## 2. Úklidy

`GET /api/v1/cleanings`

Parametry (všechny volitelné, lze kombinovat):

| parametr | význam |
|---|---|
| `updated_since` | jen úklidy změněné od tohoto času (vytvoření, změna stavu, poznámka…) |
| `date_from`, `date_to` | jen úklidy s datem v rozmezí (včetně) |

```json
{
  "cleanings": [
    {
      "id": 123,
      "apartment_id": 7,
      "date": "2026-10-01",
      "status": "done",
      "cleaner": "Jana",
      "started_at": "2026-10-01T10:15:00+02:00",
      "finished_at": "2026-10-01T11:42:00+02:00",
      "updated_at": "2026-10-01T11:42:00+02:00",
      "departed_guest": "Gabriela Krause",
      "departed_reservation_id": "157226631",
      "keybox": {
        "status": "changed",
        "code": "5678",
        "previous_code": "1234"
      },
      "notes": "Hosté nechali byt v pořádku.",
      "issues": [
        {
          "type": "damage",
          "text": "Prasklá sklenice, chybí 1 ručník",
          "photo_urls": ["https://uklid.kolbl-apartments.cz/…/1.jpg"]
        }
      ]
    }
  ]
}
```

| pole | hodnoty / význam |
|---|---|
| `status` | `planned` (naplánováno), `in_progress` (uklízí se), `done` (hotovo), `problem` (byt nejde připravit), `cancelled` (zrušeno) |
| `departed_guest`, `departed_reservation_id` | host, **po kterém** se uklízí. `departed_reservation_id` = ID rezervace ve Smoobu, pokud ho aplikace má (rezervace bere ze Smoobu/kalendáře?). Jinak `null` – stačí aspoň jméno hosta. |
| `keybox.status` | `confirmed` (kód sedí), `changed` (kód změněn), `not_checked` (nepotvrzeno) |
| `keybox.code` | kód na keyboxu po úklidu |
| `issues[].type` | `damage` (škoda), `missing_item` (něco chybí), `lost_and_found` (host něco zapomněl), `dirty` (extrémní nepořádek), `other` |
| `notes` | volná poznámka uklízečky (může být prázdná) |

## Chybové stavy

- `401` špatný/chybějící klíč, `400` špatný parametr (`{"error": "popis"}`), `500` chyba serveru.
- Když API nefunguje, agent kódy hostům **neposílá** a upozorní hostitele – nic se nerozbije.

## Co s tím agent dělá

1. **Kódy:** instrukce k příjezdu bere kód z `keybox_code`. Těsně před odesláním schválených instrukcí
   ho znovu ověří – když se mezitím změnil, instrukce se starým kódem **neodešle** a připraví nové.
2. **Kontrola po úklidu:** změněný kód ohlásí hostitelům ve skupině, nepotvrzený kód ohlásí jako problém.
3. **Byt připravený k příjezdu:** v den příjezdu ve 14:00 zkontroluje, že je úklid `done`, jinak upozorní.
4. **Dřívější check-in:** k žádosti hosta přidá, jestli a od kdy je byt uklizený (rozhoduje hostitel).
5. **Hodnocení hostů:** poznámky a problémy z úklidu použije v návrhu hodnocení.

## Minimální verze (na začátek stačí)

- `GET /api/v1/apartments` s poli `id, name, keybox_code`
- `GET /api/v1/cleanings` s poli `id, apartment_id, date, status, finished_at, updated_at, keybox`
- povinné potvrzení kódu při dokončení úklidu

Zbytek (poznámky, problémy, host) jde doplnit později – agent si s chybějícími poli poradí.

## Jak si to otestovat

```bash
curl -H "Authorization: Bearer $AGENT_API_KEY" https://uklid.kolbl-apartments.cz/api/v1/apartments
curl -H "Authorization: Bearer $AGENT_API_KEY" "https://uklid.kolbl-apartments.cz/api/v1/cleanings?date_from=2026-10-01"
```
