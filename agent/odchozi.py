"""Brána pro všechny zprávy hostům – jediné místo, které volá smoobu.send_message (krok P1.4).

Každé odeslání se zapíše do tabulky `odchozi` se stavem:
  odesila → odeslano | selhalo | nejiste
Timeout / výpadek spojení neznamená, že zpráva neodešla. Brána proto přečte konverzaci ve Smoobu:
  zpráva tam je → odeslano (druhé kliknutí už nic nepošle), není → selhalo (jde poslat znovu),
  konverzaci nejde přečíst → nejiste (opakované odeslání je zablokované; ověří se v dalším cyklu).
Obchodní kontroly (je návrh aktuální, platí kód…) dělá navrhy.odeslat – brána jen bezpečně odešle.
"""
import logging
import re
from datetime import timedelta

import requests

from . import hodiny, oznameni

log = logging.getLogger("agent")
NEJISTE_MAX_HODIN = 2  # tak dlouho se nejisté odeslání zkouší ověřit, pak se předá hostitelům


def _norm(text):
    return re.sub(r"\s+", " ", text or "").strip()


def je_v_konverzaci(zpravy, text):
    """Je naše zpráva s tímto textem v konverzaci? (Smoobu může přidat mezery / zalomení.)"""
    hledany = _norm(text)[:200]
    return bool(hledany) and any(m.get("type") != 1 and hledany in _norm(m.get("message")) for m in zpravy)


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
        return stav
    except Exception as e:
        _zapis(db, zaznam_id, "selhalo", str(e)[:300])
        raise
    _zapis(db, zaznam_id, "odeslano")
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
