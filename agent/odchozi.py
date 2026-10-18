"""Brána pro všechny zprávy hostům – jediné místo, které volá smoobu.send_message (krok P1.4).

Každé odeslání se zapíše do tabulky `odchozi` se stavem:
  odesila → odeslano | selhalo | nejiste
Timeout / výpadek spojení neznamená, že zpráva neodešla. Brána proto přečte konverzaci ve Smoobu:
  zpráva tam je → odeslano (druhé kliknutí už nic nepošle), není → selhalo (jde poslat znovu),
  konverzaci nejde přečíst → nejiste (opakované odeslání je zablokované; ověří se v dalším cyklu).
Obchodní kontroly (je návrh aktuální, platí kód…) dělá navrhy.odeslat – brána jen bezpečně odešle.

Smoobu bere znak „<“ jako začátek HTML značky a zbytek zprávy zahodí (18. 10. 2026 – šipka „LEFT <----“).
Brána ho proto před odesláním nahradí a po odeslání ověří, že Smoobu uložilo celou zprávu (sloupec zkraceno);
když ne, hned upozorní hostitele i s celým zněním k ručnímu odeslání.
"""
import logging
import re
from datetime import timedelta

import requests

from . import hodiny, oznameni

log = logging.getLogger("agent")
NEJISTE_MAX_HODIN = 2  # tak dlouho se nejisté odeslání zkouší ověřit, pak se předá hostitelům
NAHRADY_ZNAKU = {"<": "‹"}  # znaky, které Smoobu/platformy rozbijí (HTML)


def _norm(text):
    return re.sub(r"\s+", " ", text or "").strip()


def je_v_konverzaci(zpravy, text):
    """Je naše zpráva s tímto textem v konverzaci? (Smoobu může přidat mezery / zalomení.)"""
    hledany = _norm(text)[:200]
    return bool(hledany) and any(m.get("type") != 1 and hledany in _norm(m.get("message")) for m in zpravy)


def bezpecny_text(text):
    for znak, nahrada in NAHRADY_ZNAKU.items():
        text = text.replace(znak, nahrada)
    return text


def _over_ulozeni(smoobu, db, zaznam_id, reservation_id, text, navrh_id):
    """Uložilo Smoobu celou zprávu? Porovná naši poslední zprávu v konverzaci s odeslaným textem."""
    try:
        nase = [m for m in smoobu.messages(reservation_id) if m.get("type") != 1]
    except Exception as e:
        log.warning("Po odeslání nejde ověřit uloženou zprávu (rez. %s): %s", reservation_id, e)
        return
    odeslany = _norm(text)
    if any(odeslany in _norm(m.get("message")) for m in nase):
        zkraceno = 0
    elif nase and _norm(nase[-1].get("message")) and odeslany.startswith(_norm(nase[-1].get("message"))):
        zkraceno = 1
    else:
        return  # naši zprávu v konverzaci nepoznáme – nic nehlásit
    db.conn.execute("UPDATE odchozi SET zkraceno = ? WHERE id = ?", (zkraceno, zaznam_id))
    db.conn.commit()
    if zkraceno:
        ulozeno = len(_norm(nase[-1].get("message")))
        hlavicka = (db.navrh(navrh_id) or {}).get("hlavicka", "") if navrh_id else ""
        oznameni.posli(f"⚠️ Smoobu zprávu hostovi ZKRÁTILO (uložilo jen {ulozeno} z {len(odeslany)} znaků) – host ji "
                       f"nejspíš nedostal celou. Pošli mu prosím ručně celé znění:\n{hlavicka or f'rez. {reservation_id}'}"
                       f"\n\n{text}")


def _zapis(db, zaznam_id, stav, chyba=""):
    db.conn.execute("UPDATE odchozi SET stav = ?, chyba = ?, zmena = ? WHERE id = ?",
                    (stav, chyba, hodiny.ted_iso(), zaznam_id))
    db.conn.commit()


def odeslat(smoobu, db, reservation_id, text, zdroj, navrh_id=None):
    """Pošle zprávu hostovi. Vrací "odeslano" | "selhalo" | "nejiste".
    Jiné chyby Smoobu (401, 400, 429…) zapíše jako selhalo a předá volajícímu (výjimka)."""
    if navrh_id and db.conn.execute(
            "SELECT 1 FROM odchozi WHERE navrh_id = ? AND stav IN ('odesila', 'odeslano', 'nejiste')",
            (navrh_id,)).fetchone():
        return "odeslano"  # tenhle návrh už odešel (nebo se ověřuje) – nikdy podruhé
    text = bezpecny_text(text)
    zaznam_id = db.conn.execute(
        "INSERT INTO odchozi (navrh_id, reservation_id, text, zdroj, stav, cas) VALUES (?, ?, ?, ?, 'odesila', ?)",
        (navrh_id, str(reservation_id), text, zdroj, hodiny.ted_iso())).lastrowid
    db.conn.commit()
    try:
        smoobu.send_message(reservation_id, text)
    except (requests.Timeout, requests.ConnectionError) as e:
        log.warning("Odeslání hostovi (rez. %s) skončilo %s – ověřuji v konverzaci", reservation_id, type(e).__name__)
        try:
            zpravy = smoobu.messages(reservation_id)
        except Exception as e2:
            _zapis(db, zaznam_id, "nejiste", f"{type(e).__name__}; konverzaci nejde přečíst: {e2}")
            return "nejiste"
        stav = "odeslano" if je_v_konverzaci(zpravy, text) else "selhalo"
        _zapis(db, zaznam_id, stav, type(e).__name__)
        if stav == "odeslano":
            _over_ulozeni(smoobu, db, zaznam_id, reservation_id, text, navrh_id)
        return stav
    except Exception as e:
        _zapis(db, zaznam_id, "selhalo", str(e)[:300])
        raise
    _zapis(db, zaznam_id, "odeslano")
    _over_ulozeni(smoobu, db, zaznam_id, reservation_id, text, navrh_id)
    return "odeslano"


def over_nejiste(smoobu, db):
    """V každém cyklu: nejistá odeslání ověří v konverzaci. Po NEJISTE_MAX_HODIN je předá hostitelům."""
    for zaznam_id, navrh_id, rid, text, cas in db.conn.execute(
            "SELECT id, navrh_id, reservation_id, text, cas FROM odchozi WHERE stav = 'nejiste'").fetchall():
        hlavicka = (db.navrh(navrh_id) or {}).get("hlavicka", f"rez. {rid}") if navrh_id else f"rez. {rid}"
        try:
            odeslano = je_v_konverzaci(smoobu.messages(rid), text)
        except Exception as e:
            log.warning("Nejisté odeslání %s zatím nejde ověřit: %s", zaznam_id, e)
            odeslano = None
        if odeslano:
            _zapis(db, zaznam_id, "odeslano", "ověřeno v konverzaci")
            if navrh_id:
                db.uprav_navrh(navrh_id, stav="odeslano")
            oznameni.posli(f"✅ Ověřeno: zpráva hostovi odešla.\n{hlavicka}")
        elif odeslano is False or cas < (hodiny.ted() - timedelta(hours=NEJISTE_MAX_HODIN)).isoformat():
            _zapis(db, zaznam_id, "selhalo", "v konverzaci není" if odeslano is False else "nešlo ověřit")
            if navrh_id:
                db.uprav_navrh(navrh_id, stav="selhalo")
            oznameni.posli(f"⚠️ Zpráva hostovi NEODEŠLA (v konverzaci ve Smoobu není) – pošli ji prosím ručně:\n"
                           f"{hlavicka}\n\n{text}")
