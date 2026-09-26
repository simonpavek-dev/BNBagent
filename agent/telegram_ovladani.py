"""Ovládání agenta z Telegramu: tlačítka ✅ Odeslat / ✏️ Upravit / ❌ Neposílat a odpovědi hostitele."""
import logging

from . import config, navrhy, oznameni

log = logging.getLogger("agent")


def zpracuj(smoobu, db, cekat=20):
    """Vyřídí nová kliknutí a zprávy z Telegramu (čeká na ně až `cekat` sekund)."""
    if db.nastaveni("tg_offset") is None:  # první spuštění – staré zprávy botovi (např. „ahoj“) přeskočit
        stare = oznameni.nove_udalosti(0, 0)
        db.uloz_nastaveni("tg_offset", stare[-1]["update_id"] + 1 if stare else 0)
        return
    offset = int(db.nastaveni("tg_offset", "0"))
    for udalost in oznameni.nove_udalosti(offset, cekat):
        db.uloz_nastaveni("tg_offset", udalost["update_id"] + 1)
        try:
            if "callback_query" in udalost:
                _kliknuti(smoobu, db, udalost["callback_query"])
            elif "message" in udalost:
                _zprava(db, udalost["message"])
        except Exception as e:
            log.exception("Chyba při zpracování Telegramu")
            oznameni.posli(f"⚠️ Akci se nepodařilo provést: {e}")


def _od_hostitele(chat):
    return str((chat or {}).get("id")) == str(config.TELEGRAM_CHAT_ID)


def _jmeno(uzivatel):
    """Jméno toho, kdo ve skupině klikl nebo psal (např. „Šimon“)."""
    u = uzivatel or {}
    return " ".join(x for x in (u.get("first_name"), u.get("last_name")) if x) or u.get("username") or ""


def _klic_upravy(uzivatel):
    """Každý člen skupiny má vlastní rozpracovanou úpravu, aby se texty dvou lidí nepletly."""
    return f"upravuje_navrh_{(uzivatel or {}).get('id', '')}"


def _kliknuti(smoobu, db, cq):
    if not _od_hostitele((cq.get("message") or {}).get("chat")):
        return
    akce, _, navrh_id = (cq.get("data") or "").partition(":")
    navrh = db.navrh(int(navrh_id)) if navrh_id.isdigit() else None
    zrusit_planovane = akce == "zahodit" and navrh and navrh["stav"] == "schvaleno"
    if not navrh or (navrh["stav"] != "ceka" and not zrusit_planovane):
        oznameni.potvrd_kliknuti(cq["id"], "Tenhle návrh už je vyřízený.")
        return
    oznameni.potvrd_kliknuti(cq["id"])  # Telegram chce potvrzení hned, výsledek přijde zprávou
    kdo = _jmeno(cq.get("from"))

    if akce == "odeslat":
        _, zprava = navrhy.schvalit(smoobu, db, navrh, "telegramu", kdo)
        if zprava:
            oznameni.posli(zprava)

    elif akce == "upravit":
        db.uloz_nastaveni(_klic_upravy(cq.get("from")), navrh["id"])
        oznameni.posli(
            f"✏️ {kdo + ', n' if kdo else 'N'}apiš mi, co má host dostat – klidně česky a stručně. Přeložím to do jazyka hosta "
            f"({navrh['jazyk']}), doplním podpis a ukážu ti ke schválení.\n{navrh['hlavicka']}\n\n"
            "Zrušit: napiš /zrusit"
        )

    elif akce == "zahodit":
        navrhy.zahodit(db, navrh, kdo)
        if zrusit_planovane:
            oznameni.posli(f"❌ Naplánované odeslání zrušeno{navrhy._kdo(kdo)}, hostovi nic nepošlu.\n{navrh['hlavicka']}")
        else:
            oznameni.posli(f"❌ Neposílám{navrhy._kdo(kdo)}.\n{navrh['hlavicka']}")


def _zprava(db, msg):
    if not _od_hostitele(msg.get("chat")):
        return
    text = (msg.get("text") or "").strip()
    klic = _klic_upravy(msg.get("from"))
    upravuje = db.nastaveni(klic, "")
    if text.split("@")[0] == "/zrusit":  # ve skupině Telegram posílá „/zrusit@Vasilbnb_bot“
        db.uloz_nastaveni(klic, "")
        oznameni.posli("Úprava zrušena. Původní návrh má pořád svoje tlačítka.")
        return
    if not upravuje or not text:
        # ve skupině si spolu můžete normálně psát – bot reaguje jen na toho, kdo klikl na ✏️ Upravit
        if (msg.get("chat") or {}).get("type") == "private":
            oznameni.posli("Na návrhy odpovídej tlačítky pod nimi (✅ Odeslat / ✏️ Upravit / ❌ Neposílat).")
        return

    puvodni = db.navrh(int(upravuje))
    db.uloz_nastaveni(klic, "")
    if not puvodni or puvodni["stav"] != "ceka":
        oznameni.posli("Tenhle návrh už je vyřízený, text jsem nikam neposlal.")
        return
    navrhy.nahradit(db, puvodni, text, _jmeno(msg.get("from")))
