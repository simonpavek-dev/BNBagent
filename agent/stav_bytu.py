"""Příkaz /status v Telegramu (přepínač PRIKAZ_STATUS): stav bytů (obsazeno / dnes odjezd či příjezd / volno)
a kódy ke dveřím domu a bytu – když do bytu jdou hostitelé nebo úklid a nechtějí kódy lovit.

Kód bytu je ten, který je teď na keyboxu (poslední zapsaný v aplikaci úklidů, `uklidy.aktualni_kod`); když se dnes
uklízí a nový kód je v aplikaci zapsaný předem, ukáže i kód platný do úklidu. Kód domu je ze znalostní báze.
Zpráva s kódy se po SMAZAT_PO_MINUTACH smaže i s příkazem, aby kódy nezůstaly v historii skupiny (mazání hlídá
hlavní smyčka – smaz_prosle). Odpověď nejde přes frontu upozornění: zastaralý stav s kódy by byl k ničemu.
Volá `telegram_ovladani`, `__main__`.
"""
import json
import logging
from datetime import datetime, timedelta

from . import config, hodiny, kontext, oznameni, uklidy, znalosti

log = logging.getLogger("agent")
SMAZAT_PO_MINUTACH = 15
SMAZAT_NEJPOZDEJI_HODIN = 47  # Telegram dovolí botovi mazat zprávy jen 48 hodin
DNY = ("po", "út", "st", "čt", "pá", "so", "ne")


def _den(d):
    return f"{d.day}. {d.month}."


def _stav(rezervace, dnes, byt):
    check_in = str(((byt.get("prijezd") or {}).get("check_in_od")) or "").strip()
    check_out = str(((byt.get("odjezd") or {}).get("check_out_do")) or "").strip()
    pobyty = [(kontext._datum(r.get("arrival")), kontext._datum(r.get("departure"))) for r in rezervace]
    pobyty = [(p, o) for p, o in pobyty if p and o]
    bydli = next((o for p, o in pobyty if p < dnes < o), None)
    if bydli:
        return f"🔴 obsazeno do {_den(bydli)}" + (f" (check-out {check_out})" if check_out else "")
    odjezd_dnes = any(o == dnes for _, o in pobyty)
    prijezd_dnes = any(p == dnes for p, _ in pobyty)
    dalsi = min((p for p, _ in pobyty if p > dnes), default=None)
    volno = f"volno do {_den(dalsi)}" if dalsi else "volno"
    odjezd = "dnes odjezd" + (f" do {check_out}" if check_out else "")
    prijezd = "příjezd" + (f" od {check_in}" if check_in else "")
    if odjezd_dnes and prijezd_dnes:
        return f"🟡 {odjezd}, {prijezd}"
    if odjezd_dnes:
        return f"🟡 {odjezd}, pak {volno}"
    if prijezd_dnes:
        return f"🟡 dnes {prijezd}"
    return f"🟢 {volno}"


def _kod_pred_dnesnim_uklidem(smoobu_id, pobyty):
    """Dnes se uklízí a nový kód je v aplikaci zapsaný předem → do konce úklidu platí předchozí kód."""
    dnes = kontext.dnes().isoformat()
    zapsane = [p for p in pobyty or [] if p["smoobu_id"] == smoobu_id and p["kod"] and (p["datum"] or "") <= dnes]
    if len(zapsane) >= 2 and zapsane[-1]["datum"] == dnes and not zapsane[-1]["uklizeno"]:
        return zapsane[-2]["kod"]
    return None


def _kody(byt, db, pobyty):
    smoobu_id = str(byt.get("smoobu_id") or "").strip()
    casti = []
    dum = str(((byt.get("prijezd") or {}).get("kod_vchod")) or "").strip()
    if dum:
        casti.append(f"🚪 dům {dum}")
    kod = uklidy.aktualni_kod(smoobu_id, db)
    pred_uklidem = _kod_pred_dnesnim_uklidem(smoobu_id, pobyty)
    if kod and pred_uklidem and pred_uklidem != kod:
        casti.append(f"🔑 byt {pred_uklidem} (po dnešním úklidu {kod})")
    else:
        casti.append(f"🔑 byt {kod}" if kod else "🔑 kód bytu neznám")
    return " · ".join(casti)


def text(smoobu, db):
    ted = hodiny.ted()
    dnes = ted.date()
    rezervace = [r for r in smoobu.reservations(dnes - timedelta(days=60), dnes + timedelta(days=365))
                 if not r.get("is-blocked-booking")]
    pobyty, varovani = None, ""
    if uklidy.zapnuto():
        try:
            pobyty = uklidy.pobyty()
        except Exception as e:
            log.warning("Aplikace úklidů pro /status: %s", e)
            varovani = "\n⚠️ Aplikace úklidů teď nejde – kódy bytů jsou poslední známé."
    radky = [f"🏠 Byty – {DNY[ted.weekday()]} {ted.day}. {ted.month}. {ted:%H:%M}"]
    for _, byt in znalosti.vsechny_apartmany():
        smoobu_id = str(byt.get("smoobu_id") or "").strip()
        jeho = [r for r in rezervace if str((r.get("apartment") or {}).get("id")) == smoobu_id]
        radky.append(f"{byt.get('nazev') or smoobu_id} – {_stav(jeho, dnes, byt)}")
        radky.append(f"   {_kody(byt, db, pobyty)}")
    return "\n".join(radky) + varovani + f"\n\n(Zpráva se za {SMAZAT_PO_MINUTACH} minut smaže i s příkazem.)"


def odpovez(smoobu, db, prikaz_id):
    """Odpověď na /status ve skupině hostitelů."""
    if not config.PRIKAZ_STATUS:
        oznameni.posli_hned("Příkaz /status je vypnutý (PRIKAZ_STATUS v .env).", odpoved_na=prikaz_id)
        return
    try:
        zprava = text(smoobu, db)
    except Exception as e:
        log.exception("Stav bytů pro /status")
        oznameni.posli_hned(f"⚠️ Stav bytů teď nejde zjistit: {str(e)[:200]}", odpoved_na=prikaz_id)
        return
    _naplanuj_smazani(db, [prikaz_id, oznameni.posli_hned(zprava, odpoved_na=prikaz_id)])


def _naplanuj_smazani(db, message_ids):
    kdy = (hodiny.ted() + timedelta(minutes=SMAZAT_PO_MINUTACH)).isoformat(timespec="seconds")
    seznam = json.loads(db.nastaveni("smazat_zpravy") or "[]")
    seznam += [{"id": m, "kdy": kdy} for m in message_ids if m]
    db.uloz_nastaveni("smazat_zpravy", json.dumps(seznam))


def smaz_prosle(db):
    """V každém cyklu: smaže zprávy s kódy, kterým uplynul čas. Když Telegram nejde, zkusí to příště."""
    seznam = json.loads(db.nastaveni("smazat_zpravy") or "[]")
    if not seznam:
        return
    ted, zbyva = hodiny.ted(), []
    for zprava in seznam:
        kdy = datetime.fromisoformat(zprava["kdy"])
        if ted < kdy:
            zbyva.append(zprava)
        elif not oznameni.smaz_zpravu(zprava["id"]):
            if ted - kdy < timedelta(hours=SMAZAT_NEJPOZDEJI_HODIN):
                zbyva.append(zprava)
            else:
                log.warning("Zprávu %s s kódy se nepodařilo smazat ani po %s h", zprava["id"], SMAZAT_NEJPOZDEJI_HODIN)
    db.uloz_nastaveni("smazat_zpravy", json.dumps(zbyva))
