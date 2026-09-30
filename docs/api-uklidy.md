# API aplikace úklidů pro AI agenta (verze 1)

Agent „Vasil“ (odpovídá hostům na Airbnb/Booking přes Smoobu) potřebuje z aplikace úklidů číst:
kódy keyboxů, jestli je byt uklizený, a co uklízečka zjistila (škody, zapomenuté věci…).

- API je **jen pro čtení** – agent v aplikaci nic nemění.
- Adresa: `https://kolbl.goldenpathai.com/api/v1/…`
- Formát: JSON, UTF-8, časy ve formátu ISO 8601 s časovou zónou (`2026-10-01T11:42:00+02:00`), data `YYYY-MM-DD`.
- Agent se ptá zhruba každé 3 minuty, takže stačí obyčejné dotazy – žádné webhooky ani fronty.

## Přihlášení

V admin rozhraní přidej možnost vytvořit **API klíč** (náhodný řetězec, min. 32 znaků, jde zneplatnit).
Agent ho posílá v hlavičce:

```
Authorization: Bearer <API_KLIC>
```

Bez platného klíče vrať `401`. Klíč ukládej jen jako hash, stejně jako hesla.

## Změna v aplikaci pro uklízečky (důležité!)

Při **odkliknutí hotového úklidu** musí uklízečka povinně potvrdit kód na keyboxu – bez toho úklid nejde dokončit:

```
Kód na keyboxu:   ( ) Sedí – je nastavený 1234
                  ( ) Změnil(a) jsem ho na: [____]
```

- „Sedí“ → u bytu se uloží čas a jméno potvrzení (`keybox.status = "confirmed"`).
- „Změnil(a)“ → nový kód se uloží jako **aktuální kód bytu** a u úklidu `keybox.status = "changed"`
  a `previous_code` = starý kód. Kód: 4 číslice (povol i 3–8, kdyby se měnil keybox).
- Starší úklidy bez potvrzení mají `keybox.status = "not_checked"`.

## 1. Seznam bytů a jejich aktuální kódy

`GET /api/v1/apartments`

```json
{
  "apartments": [
    {
      "id": 1,
      "name": "Petrská",
      "smoobu_id": "3529986",
      "keybox_code": "1234",
      "keybox_code_changed_at": "2026-09-20T12:10:00+02:00",
      "keybox_code_confirmed_at": "2026-09-30T11:42:00+02:00",
      "keybox_code_confirmed_by": "Jana"
    }
  ]
}
```

- `smoobu_id` = ID apartmánu ve Smoobu – podle něj agent byt spáruje. V adminu u bytu stačí textové pole.
  Aktuální ID: Petrská `3529986`, Sokolská `3529991`, Školská `3529996`,
  Vojtěšská 1 `3530001`, Vojtěšská 2 `3530006`, Vojtěšská 3 `3530011`.
- `keybox_code` = kód, který na keyboxu **teď** je (po posledním potvrzení/změně).

## 2. Úklidy

`GET /api/v1/cleanings?updated_since=2026-09-30T10:00:00%2B02:00`

Parametry (všechny volitelné, lze kombinovat):

| parametr | význam |
|---|---|
| `updated_since` | jen úklidy změněné od tohoto času (vytvoření, změna stavu, poznámka…) |
| `date_from`, `date_to` | jen úklidy s datem v rozmezí (včetně) |
| `smoobu_id` | jen úklidy jednoho bytu |

```json
{
  "cleanings": [
    {
      "id": 123,
      "smoobu_id": "3529986",
      "date": "2026-10-01",
      "status": "done",
      "cleaner": "Jana",
      "started_at": "2026-10-01T10:15:00+02:00",
      "finished_at": "2026-10-01T11:42:00+02:00",
      "updated_at": "2026-10-01T11:42:00+02:00",
      "departed_reservation_id": "157226906",
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
          "photo_urls": ["https://kolbl.goldenpathai.com/media/…/1.jpg"]
        }
      ]
    }
  ]
}
```

| pole | hodnoty / význam |
|---|---|
| `status` | `planned` (naplánováno), `in_progress` (uklízí se), `done` (hotovo), `problem` (uklízečka nahlásila, že byt nejde připravit) |
| `departed_reservation_id` | ID rezervace ve Smoobu hosta, **po kterém** se uklízí (pokud ho aplikace zná; jinak `null`). Agent podle něj píše návrh hodnocení hosta. |
| `keybox.status` | `confirmed` (kód sedí), `changed` (kód změněn), `not_checked` (nepotvrzeno) |
| `keybox.code` | kód, který je na keyboxu po úklidu |
| `issues[].type` | `damage` (škoda), `missing_item` (něco chybí), `lost_and_found` (host něco zapomněl), `dirty` (extrémní nepořádek), `other` |
| `notes` | volná poznámka uklízečky (může být prázdná) |

Zrušený úklid buď nevracej, nebo vrať se `status: "cancelled"`.

## Chybové stavy

- `401` špatný/chybějící klíč, `400` špatný parametr (`{"error": "popis"}`), `500` chyba serveru.
- Když API nefunguje, agent kódy hostům **neposílá** a upozorní hostitele – nic se nerozbije.

## Co s tím agent dělá

1. **Kódy:** instrukce k příjezdu bere kód z `keybox_code`. Před odesláním schválených instrukcí
   ho znovu ověří – když se mezitím při úklidu změnil, instrukce se starým kódem **neodešle**
   a připraví nové.
2. **Kontrola po úklidu:** u každého hotového úklidu zkontroluje potvrzení kódu. Změněný kód ohlásí
   ve skupině, nepotvrzený kód ohlásí jako problém.
3. **Byt připravený k příjezdu:** v den příjezdu ve 14:00 zkontroluje, že je úklid `done`. Jinak upozorní.
4. **Dřívější check-in:** k žádosti hosta přidá, jestli a od kdy je byt uklizený (rozhoduje hostitel).
5. **Hodnocení hostů:** poznámky a problémy z úklidu použije v návrhu hodnocení.

## Minimální verze

Když je potřeba začít rychle, stačí **bod 1 (byty a kódy)** a v úklidech pole
`id, smoobu_id, date, status, finished_at, updated_at, keybox`. Zbytek jde doplnit později.
