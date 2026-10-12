"""Chat s agentem (ovládací panel i Telegram skupina): hostitel zadává změny, agent upravuje znalostní bázi a odpovídá na dotazy."""
import difflib
import json
import logging
import shutil
from datetime import datetime, timedelta

import yaml

from . import config, hodiny, kontext, mozek, oznameni, prace, uklidy

log = logging.getLogger("agent")
ZALOHY_DIR = config.DATA_DIR / "zalohy"
MAX_KOL = 10

INSTRUKCE = """Jsi AI agent, který za hostitele vyřizuje zprávy hostů jeho apartmánů na Airbnb a Booking.com přes Smoobu.
Teď si s tebou hostitel píše v ovládacím panelu nebo v Telegram skupině (tam je u zprávy jméno, kdo píše – hostitelů je víc).
Mluv česky, stručně a věcně.
Chat zobrazuje jen prostý text: nepoužívej Markdown (žádné **, #, tabulky ani `kód`), odrážky piš pomlčkou.

Co umíš:
- Upravovat znalostní bázi (YAML soubory), ze které odpovídáš hostům: obecne.yaml (tón, podpis, kdy eskalovat, pravidla),
  apartmany/<byt>.yaml (adresa, check-in, kódy, Wi-Fi, vybavení, parkování…) a poznamky-k-hostum.yaml (poznámky od úklidu k pobytům).
  Před úpravou si soubor vždy přečti. Měň jen to, o co hostitel žádá, zachovej strukturu a komentáře.
  Po úpravě stručně řekni, co přesně se změnilo. Když není jasné, kterého bytu se změna týká, zeptej se.
- Kódy keyboxů: hlavní zdroj je aplikace úklidů (agent z ní každých 15 minut přebírá kód zapsaný u úklidu). Aktuální kódy zjistíš
  nástrojem kody. Když hostitel řekne nový kód, zapiš ho do apartmany/<byt>.yaml jako keybox_kod a do keybox_kod_overeno dnešní
  datum (RRRR-MM-DD) – bez data by ho přebil starší kód z aplikace. Stálý kód od vchodu do domu je kod_vchod.
- Rezervace a konverzace s hosty ze Smoobu jen číst (rezervace, konverzace). Stav úklidů zjistíš nástrojem stav_uklidu.
- Zprávu hostovi nikdy neposíláš sám: nástrojem navrhni_zpravu_hostovi připravíš návrh, který hostitelé schválí tlačítkem.
- Říct, co jsi dělal (aktivita), kolik to stálo (naklady) a přepnout režim (nastav_rezim).
- Vrátit poslední změnu souboru ze zálohy (vrat_zmenu).

Co neumíš: měnit svůj program, klíče a přístupy (.env). Na takové požadavky odpověz, že je potřeba je zadat v Claude Code (vývojář).
Přepnutí do ostrého režimu (odpovídáš hostům sám bez schválení) proveď jen po výslovném potvrzení hostitele v tomto chatu."""


def _cesta(soubor):
    """Povolí jen soubory znalostní báze a poznámek – nic jiného agent z chatu číst ani měnit nesmí."""
    soubor = (soubor or "").strip().lstrip("/")
    if soubor == "poznamky-k-hostum.yaml":
        return config.ROOT / soubor
    cesta = (config.ZNALOSTI_DIR / soubor).resolve()
    if cesta.suffix != ".yaml" or config.ZNALOSTI_DIR.resolve() not in cesta.parents:
        raise ValueError(f"Soubor {soubor} není součástí znalostní báze")
    return cesta


def seznam_souboru():
    soubory = ["obecne.yaml"] + [f"apartmany/{p.name}" for p in sorted((config.ZNALOSTI_DIR / "apartmany").glob("*.yaml"))]
    return soubory + ["poznamky-k-hostum.yaml"]


def precti_soubor(soubor):
    return _cesta(soubor).read_text(encoding="utf-8")


def uprav_soubor(soubor, puvodni_text, novy_text):
    cesta = _cesta(soubor)
    obsah = cesta.read_text(encoding="utf-8")
    pocet = obsah.count(puvodni_text)
    if pocet != 1:
        raise ValueError(f"Původní text se v souboru vyskytuje {pocet}× – musí přesně 1×. Soubor si přečti znovu.")
    novy_obsah = obsah.replace(puvodni_text, novy_text)
    yaml.safe_load(novy_obsah)  # nevalidní YAML se neuloží
    ZALOHY_DIR.mkdir(exist_ok=True)
    zaloha = ZALOHY_DIR / f"{soubor.replace('/', '__')}.{hodiny.ted():%Y%m%d-%H%M%S}"
    shutil.copy2(cesta, zaloha)
    cesta.write_text(novy_obsah, encoding="utf-8")
    rozdil = "\n".join(difflib.unified_diff(obsah.splitlines(), novy_obsah.splitlines(), lineterm="", n=0))
    log.info("Chat upravil %s:\n%s", soubor, rozdil)
    return f"Uloženo. Záloha: {zaloha.name}\nZměna:\n{rozdil}"


def vrat_zmenu(soubor):
    cesta = _cesta(soubor)
    zalohy = sorted(ZALOHY_DIR.glob(f"{soubor.replace('/', '__')}.*"))
    if not zalohy:
        raise ValueError("K tomuto souboru není žádná záloha")
    shutil.copy2(zalohy[-1], cesta)
    zalohy[-1].unlink()
    return f"Vráceno na stav ze zálohy {zalohy[-1].name}"


def aktivita(db, pocet=30):
    radky = db.conn.execute(
        "SELECT cas, reservation_id, akce, detail FROM udalosti ORDER BY id DESC LIMIT ?", (int(pocet),)
    ).fetchall()
    out = []
    for cas, rid, akce, detail in radky:
        try:
            d = json.loads(detail)
            detail = {k: d.get(k) for k in ("hlavicka", "rozhodnuti", "duvod", "zprava_hosta", "odpoved_hostovi") if k in d}
        except (ValueError, TypeError):
            pass
        out.append({"cas": cas, "rezervace": rid, "akce": akce, "detail": detail})
    return json.dumps(out, ensure_ascii=False)


def naklady():
    dnes = hodiny.dnes()
    soucty = {"dnes": 0.0, "7_dni": 0.0, "tento_mesic": 0.0}
    cesta = config.DATA_DIR / "naklady.jsonl"
    if cesta.exists():
        for radek in cesta.read_text(encoding="utf-8").splitlines():
            z = json.loads(radek)
            den = datetime.fromisoformat(z["cas"]).date()
            if den == dnes:
                soucty["dnes"] += z["usd"]
            if den > dnes - timedelta(days=7):
                soucty["7_dni"] += z["usd"]
            if (den.year, den.month) == (dnes.year, dnes.month):
                soucty["tento_mesic"] += z["usd"]
    return {k: round(v, 2) for k, v in soucty.items()}


NASTROJE = [
    {"name": "seznam_souboru", "description": "Seznam souborů znalostní báze.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "precti_soubor", "description": "Přečte soubor znalostní báze (cesta ze seznam_souboru).",
     "input_schema": {"type": "object", "properties": {"soubor": {"type": "string"}},
                      "required": ["soubor"], "additionalProperties": False}},
    {"name": "uprav_soubor",
     "description": "Nahradí v souboru přesně jeden úsek textu jiným (puvodni_text musí v souboru být právě jednou, "
                    "včetně odsazení). Před uložením zkontroluje YAML a uloží zálohu. Vrátí provedenou změnu.",
     "input_schema": {"type": "object", "properties": {
         "soubor": {"type": "string"}, "puvodni_text": {"type": "string"}, "novy_text": {"type": "string"}},
         "required": ["soubor", "puvodni_text", "novy_text"], "additionalProperties": False}},
    {"name": "vrat_zmenu", "description": "Vrátí poslední změnu souboru ze zálohy.",
     "input_schema": {"type": "object", "properties": {"soubor": {"type": "string"}},
                      "required": ["soubor"], "additionalProperties": False}},
    {"name": "aktivita", "description": "Poslední události agenta (rozhodnutí o zprávách hostů, odeslané odpovědi, chyby).",
     "input_schema": {"type": "object", "properties": {"pocet": {"type": "integer"}},
                      "required": ["pocet"], "additionalProperties": False}},
    {"name": "naklady", "description": "Útrata za Claude API v dolarech (dnes, 7 dní, tento měsíc).",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "rezervace", "description": "Rezervace ze Smoobu s příjezdem v rozmezí dat (RRRR-MM-DD): byt, host, kanál, termín, ID.",
     "input_schema": {"type": "object", "properties": {"od": {"type": "string"}, "do": {"type": "string"}},
                      "required": ["od", "do"], "additionalProperties": False}},
    {"name": "konverzace", "description": "Konverzace s hostem k rezervaci (ID ze Smoobu), od nejstarší zprávy.",
     "input_schema": {"type": "object", "properties": {"reservation_id": {"type": "string"}},
                      "required": ["reservation_id"], "additionalProperties": False}},
    {"name": "kody", "description": "Aktuální kódy keyboxů, které agent posílá hostům (podle aplikace úklidů a znalostní báze).",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "stav_uklidu", "description": "Úklidy našich bytů z aplikace úklidů v rozmezí dat (RRRR-MM-DD): datum, kód, uklizeno.",
     "input_schema": {"type": "object", "properties": {"od": {"type": "string"}, "do": {"type": "string"}},
                      "required": ["od", "do"], "additionalProperties": False}},
    {"name": "navrhni_zpravu_hostovi",
     "description": "Připraví návrh zprávy hostovi k rezervaci a pošle ho do Telegram skupiny s tlačítky Odeslat/Upravit/Neposílat. "
                    "Hostovi se nic neodešle, dokud to hostitel neschválí. Text piš v jazyce hosta, podpis podle obecne.yaml.",
     "input_schema": {"type": "object", "properties": {"reservation_id": {"type": "string"}, "text": {"type": "string"}},
                      "required": ["reservation_id", "text"], "additionalProperties": False}},
    {"name": "nastav_rezim",
     "description": "Přepne režim: 'navrh' = hostům nic neposílá bez schválení, 'ostre' = odpovídá hostům sám. "
                    "Do 'ostre' jen po výslovném potvrzení hostitele.",
     "input_schema": {"type": "object", "properties": {"rezim": {"type": "string", "enum": ["navrh", "ostre"]}},
                      "required": ["rezim"], "additionalProperties": False}},
]


def _spust(db, nazev, vstup):
    if nazev == "seznam_souboru":
        return json.dumps(seznam_souboru(), ensure_ascii=False)
    if nazev == "precti_soubor":
        return precti_soubor(vstup["soubor"])
    if nazev == "uprav_soubor":
        vysledek = uprav_soubor(vstup["soubor"], vstup["puvodni_text"], vstup["novy_text"])
        db.zapis("", "zmena_znalosti", {"soubor": vstup["soubor"], "zmena": vysledek.split("Změna:\n", 1)[-1]})
        return vysledek
    if nazev == "vrat_zmenu":
        vysledek = vrat_zmenu(vstup["soubor"])
        db.zapis("", "zmena_znalosti", {"soubor": vstup["soubor"], "zmena": vysledek})
        return vysledek
    if nazev == "aktivita":
        return aktivita(db, vstup.get("pocet") or 30)
    if nazev == "naklady":
        return json.dumps(naklady())
    if nazev == "rezervace":
        smoobu = prace.vytvor_smoobu()
        od, do = kontext._datum(vstup["od"]), kontext._datum(vstup["do"])
        return json.dumps([{"id": r.get("id"), "byt": (r.get("apartment") or {}).get("name"), "host": r.get("guest-name"),
                            "kanal": (r.get("channel") or {}).get("name"), "prijezd": r.get("arrival"), "odjezd": r.get("departure"),
                            "osob": r.get("adults"), "blokace": r.get("is-blocked-booking")}
                           for r in smoobu.reservations(od, do)], ensure_ascii=False)
    if nazev == "konverzace":
        return kontext.popis_konverzace(prace.vytvor_smoobu().messages(vstup["reservation_id"]))[-12000:]
    if nazev == "kody":
        from . import znalosti
        return json.dumps({d.get("nazev"): uklidy.aktualni_kod(d.get("smoobu_id"), db) for _, d in znalosti.vsechny_apartmany()},
                          ensure_ascii=False)
    if nazev == "stav_uklidu":
        if not uklidy.zapnuto():
            return "Napojení na aplikaci úklidů není zapnuté."
        return json.dumps([p for p in uklidy.pobyty() if vstup["od"] <= (p["datum"] or "") <= vstup["do"]], ensure_ascii=False)
    if nazev == "navrhni_zpravu_hostovi":
        from .navrhy import TLACITKA_NAVRHU
        r = prace.vytvor_smoobu().reservation(vstup["reservation_id"])
        hlavicka = prace._hlavicka(r)
        navrh_id = db.novy_navrh(r["id"], "", vstup["text"], r.get("language") or "", hlavicka)
        db.uprav_navrh(navrh_id, tg_message_id=oznameni.posli(
            f"✍️ NÁVRH ZPRÁVY (z pokynu hostitele)\n{hlavicka}\n\n{vstup['text']}", TLACITKA_NAVRHU(navrh_id), navrh_id=navrh_id))
        return f"Návrh {navrh_id} je ve skupině ke schválení."
    if nazev == "nastav_rezim":
        db.uloz_nastaveni("rezim", vstup["rezim"])
        db.zapis("", "zmena_rezimu", vstup["rezim"])
        return f"Režim je teď '{vstup['rezim']}' (platí od příští zprávy hosta)."
    raise ValueError(f"Neznámý nástroj {nazev}")


def odpovez(db, text_hostitele):
    """Zpracuje zprávu hostitele z chatu a vrátí odpověď agenta. Historie se ukládá do tabulky chat."""
    db.chat_pridej("hostitel", text_hostitele)
    historie = db.chat_historie(20)
    messages = [{"role": "user" if r == "hostitel" else "assistant", "content": t} for r, t, _ in historie]
    while messages and messages[0]["role"] != "user":
        messages.pop(0)
    kontext = (f"Dnes je {hodiny.ted():%d. %m. %Y %H:%M}. Režim agenta: {prace.rezim(db)}. "
               f"Soubory znalostní báze: {', '.join(seznam_souboru())}")
    for _ in range(MAX_KOL):
        response = mozek.client().messages.create(
            model=config.MODEL, max_tokens=16000,
            cache_control={"type": "ephemeral"},  # každé další kolo s nástroji čte předchozí text z cache (~10× levněji)
            system=[{"type": "text", "text": INSTRUKCE}, {"type": "text", "text": kontext}],
            tools=NASTROJE, messages=messages,
        )
        mozek.zapis_naklady(response, "chat s hostitelem")
        if response.stop_reason != "tool_use":
            break
        messages.append({"role": "assistant", "content": response.content})
        vysledky = []
        for blok in response.content:
            if blok.type != "tool_use":
                continue
            db.uloz_nastaveni("cinnost_chat", f"Chat: {blok.name}")
            try:
                vysledky.append({"type": "tool_result", "tool_use_id": blok.id, "content": _spust(db, blok.name, blok.input)})
            except Exception as e:
                vysledky.append({"type": "tool_result", "tool_use_id": blok.id, "content": f"Chyba: {e}", "is_error": True})
        messages.append({"role": "user", "content": vysledky})
    db.uloz_nastaveni("cinnost_chat", "")
    odpoved = "\n".join(b.text for b in response.content if b.type == "text").strip() or "(bez odpovědi)"
    db.chat_pridej("agent", odpoved)
    return odpoved
