"""Napojení na naši aplikaci úklidů (uklid.kolbl-apartments.cz) – kódy keyboxů, stav úklidu, poznámky uklízeček.

Specifikace API: docs/api-uklidy.md. Když v .env chybí UKLIDY_API_URL / UKLIDY_API_KEY, je napojení vypnuté
a agent bere kódy ze znalostní báze jako dřív.

V aplikaci je víc bytů než ve Smoobu. Agent pracuje jen s těmi, které spáruje se svou znalostní bází:
podle `smoobu_id` z API, nebo podle názvu `uklidy_nazev` v souboru bytu (např. "Školská 3+1").
"""
import json
import logging
import unicodedata
from datetime import datetime, time as cas, timedelta

import requests

from . import config, kontext, oznameni, znalosti

log = logging.getLogger("agent")

TYP_PROBLEMU = {"damage": "škoda", "missing_item": "něco chybí", "lost_and_found": "host něco zapomněl",
                "dirty": "velký nepořádek", "other": "jiné"}


class UklidyChyba(Exception):
    pass


def zapnuto():
    return bool(config.UKLIDY_API_URL and config.UKLIDY_API_KEY)


def _get(cesta, params=None):
    try:
        resp = requests.get(config.UKLIDY_API_URL.rstrip("/") + "/api/v1" + cesta, params=params or {},
                            headers={"Authorization": f"Bearer {config.UKLIDY_API_KEY}"}, timeout=20)
    except requests.RequestException as e:
        raise UklidyChyba(f"Aplikace úklidů nedostupná ({type(e).__name__})") from None
    if resp.status_code >= 400:
        raise UklidyChyba(f"Aplikace úklidů: {cesta} → {resp.status_code} {resp.text[:200]}")
    return resp.json()


def _klic(nazev):
    """„Školská 3+1“ a „skolska 3+1 “ jsou totéž."""
    return " ".join(unicodedata.normalize("NFKD", str(nazev or "")).encode("ascii", "ignore").decode().lower().split())


def _nase_byty():
    """{název bytu v aplikaci úklidů: smoobu_id} podle znalostní báze (pole uklidy_nazev)."""
    return {_klic(d.get("uklidy_nazev")): str(d.get("smoobu_id")).strip()
            for _, d in znalosti.vsechny_apartmany() if d.get("uklidy_nazev") and d.get("smoobu_id")}


def byty():
    """{smoobu_id: byt} – jen naše byty ze Smoobu, ostatní byty v aplikaci úklidů se ignorují."""
    nase = _nase_byty()
    out = {}
    for b in _get("/apartments").get("apartments", []):
        smoobu_id = str(b.get("smoobu_id") or nase.get(_klic(b.get("name"))) or "")
        if smoobu_id:
            out[smoobu_id] = dict(b, smoobu_id=smoobu_id, name=str(b.get("name") or "").strip())
    return out


def kod_bytu(smoobu_id):
    """Aktuální kód keyboxu podle aplikace úklidů, nebo None (byt tam není / nemá kód)."""
    kod = str((byty().get(str(smoobu_id)) or {}).get("keybox_code") or "").strip()
    return kod or None


def uklidy(smoobu_id=None, **params):
    """Úklidy našich bytů (s doplněným smoobu_id); úklidy ostatních bytů v aplikaci se zahodí."""
    podle_id = {str(b.get("id")): sid for sid, b in byty().items()}
    out = []
    for u in _get("/cleanings", params).get("cleanings", []):
        sid = podle_id.get(str(u.get("apartment_id")))
        if not sid or u.get("status") == "cancelled" or (smoobu_id and sid != str(smoobu_id)):
            continue
        out.append(dict(u, smoobu_id=sid))
    return out


def _cas(hodnota):
    try:
        return datetime.fromisoformat(str(hodnota)).replace(tzinfo=None)
    except ValueError:
        return None


def stav_pro_prijezd(smoobu_id, den):
    """Stav úklidu bytu k příjezdu v daný den: (uklizeno, popis pro agenta/hostitele)."""
    seznam = sorted(uklidy(smoobu_id=smoobu_id, date_from=(den - timedelta(days=7)).isoformat(),
                           date_to=den.isoformat()), key=lambda u: (u.get("date") or "", u.get("id") or 0))
    if not seznam:
        return False, "V aplikaci úklidů není na posledních 7 dní žádný úklid tohoto bytu."
    posledni = seznam[-1]
    if posledni.get("status") == "done":
        hotovo = _cas(posledni.get("finished_at"))
        kdy = f"{hotovo:%d. %m. v %H:%M}" if hotovo else posledni.get("date")
        return True, f"Byt je uklizený (úklid dokončen {kdy}, {posledni.get('cleaner') or 'uklízečka neuvedena'})."
    nazvy = {"planned": "naplánovaný", "in_progress": "právě probíhá", "problem": "uklízečka nahlásila problém"}
    return False, f"Úklid {posledni.get('date')}: {nazvy.get(posledni.get('status'), posledni.get('status'))}."


def popis_pro_zpravu(rezervace):
    """Doplněk ke kontextu zprávy hosta (hlavně kvůli dřívějšímu check-inu). Při chybě API prázdný."""
    if not zapnuto():
        return ""
    prijezd = kontext._datum(rezervace.get("arrival"))
    if not prijezd or not 0 <= (prijezd - kontext.dnes()).days <= 1:
        return ""
    try:
        _, popis = stav_pro_prijezd((rezervace.get("apartment") or {}).get("id"), prijezd)
    except UklidyChyba as e:
        log.warning("%s", e)
        return ""
    return ("STAV ÚKLIDU BYTU K PŘÍJEZDU (z aplikace úklidů, jen pro tvou informaci – o dřívějším check-inu "
            f"rozhoduje hostitel, hostovi nic neslibuj): {popis}")


def poznamky_k_pobytu(rezervace):
    """Poznámky a problémy z úklidu po odjezdu hosta – pro návrh hodnocení.
    Úklid se k pobytu přiřadí podle ID rezervace ze Smoobu, jinak podle bytu, data odjezdu a jména hosta."""
    if not zapnuto():
        return ""
    od = (kontext.dnes() - timedelta(days=5)).isoformat()
    radky = []
    for u in uklidy(date_from=od, date_to=kontext.dnes().isoformat()):
        stejna_rez = str(u.get("departed_reservation_id") or "") == str(rezervace.get("id"))
        stejny_pobyt = (u.get("smoobu_id") == str((rezervace.get("apartment") or {}).get("id"))
                        and u.get("date") == str(rezervace.get("departure"))[:10]
                        and _klic(u.get("departed_guest")) == _klic(rezervace.get("guest-name")))
        if not (stejna_rez or stejny_pobyt):
            continue
        if u.get("notes"):
            radky.append(f"Úklid ({u.get('cleaner') or '?'}): {u['notes']}")
        radky += [f"Problém – {TYP_PROBLEMU.get(p.get('type'), p.get('type'))}: {p.get('text', '')}"
                  for p in u.get("issues") or []]
    return "\n".join(radky)


# ---------------------------------------------------------------- hlídání (volá se v každém cyklu agenta)

def _nazev(u, byty_):
    return (byty_.get(str(u.get("smoobu_id"))) or {}).get("name") or f"byt {u.get('smoobu_id')}"


def zkontroluj(smoobu, db):
    """Projde nově dokončené úklidy (kód keyboxu, problémy) a v den příjezdu hlídá, že je byt uklizený."""
    if not zapnuto():
        return
    ted = datetime.now().astimezone()
    od = db.nastaveni("uklidy_od") or (ted - timedelta(hours=12)).isoformat(timespec="seconds")
    byty_ = byty()
    for u in sorted(uklidy(updated_since=od), key=lambda u: u.get("updated_at") or ""):
        if u.get("status") not in ("done", "problem") or db.nastaveni(f"uklid_{u['id']}") == u.get("updated_at"):
            continue
        _vyhodnot(smoobu, db, u, _nazev(u, byty_))
        db.uloz_nastaveni(f"uklid_{u['id']}", u.get("updated_at"))
    db.uloz_nastaveni("uklidy_od", (ted - timedelta(minutes=10)).isoformat(timespec="seconds"))  # rezerva na zpoždění
    _hlidej_prijezdy(smoobu, db, byty_)


def _vyhodnot(smoobu, db, u, nazev):
    kdo = u.get("cleaner") or "uklízečka"
    keybox = u.get("keybox") or {}
    db.zapis(u.get("departed_reservation_id") or "", "uklid", u)
    if u.get("status") == "problem":
        oznameni.posli(f"🧹❗ {nazev}: {kdo} nahlásila, že byt nejde připravit.\n{u.get('notes') or ''}")
    elif keybox.get("status") == "changed":
        oznameni.posli(f"🔑 {nazev}: {kdo} po úklidu změnila kód keyboxu {keybox.get('previous_code') or '?'} → "
                       f"{keybox.get('code')}. Agent od teď posílá nový kód.")
        zneplatni_instrukce(db, u.get("smoobu_id"), keybox.get("code"))
    elif keybox.get("status") != "confirmed":
        oznameni.posli(f"⚠️ {nazev}: úklid je hotový, ale {kdo} nepotvrdila kód na keyboxu. "
                       "Než pošlete hostovi instrukce, ověř kód.")
    problemy = [f"• {TYP_PROBLEMU.get(p.get('type'), p.get('type'))}: {p.get('text', '')}" for p in u.get("issues") or []]
    if problemy:
        oznameni.posli(f"🧹 {nazev} – {kdo} při úklidu zjistila:\n" + "\n".join(problemy))


def _instrukce(db, reservation_id):
    """Poslední připravené instrukce k příjezdu dané rezervace (kód a byt, pro který byly), nebo {}."""
    radek = db.conn.execute("SELECT detail FROM udalosti WHERE akce = 'instrukce_prijezd' AND reservation_id = ? "
                            "ORDER BY id DESC LIMIT 1", (str(reservation_id),)).fetchone()
    return json.loads(radek[0]) if radek else {}


def zneplatni_instrukce(db, smoobu_id, novy_kod):
    """Čekající/naplánované instrukce k příjezdu se starým kódem se neodešlou – agent připraví nové."""
    for navrh_id, rid, text, tg in db.conn.execute(
            "SELECT id, reservation_id, text, tg_message_id FROM navrhy WHERE stav IN ('ceka', 'schvaleno')").fetchall():
        instrukce = _instrukce(db, rid)
        stary = instrukce.get("kod")
        if str(instrukce.get("smoobu_id")) != str(smoobu_id) or not stary or stary == novy_kod or stary not in text:
            continue
        db.uprav_navrh(navrh_id, stav="zastarale")
        db.uloz_nastaveni(f"prijezd_{rid}", "")  # v příštím cyklu se připraví znovu s novým kódem
        oznameni.odeber_tlacitka(tg)
        oznameni.posli(f"♻️ Instrukce k příjezdu (rez. {rid}) obsahovaly starý kód {stary} – neodešlu je, "
                       f"připravím nové s kódem {novy_kod} ke schválení.")


def kod_stale_plati(db, navrh):
    """Pojistka těsně před odesláním: obsahuje návrh kód keyboxu, který už na keyboxu není?
    Vrací None, když je vše v pořádku, jinak text upozornění pro hostitele."""
    if not zapnuto():
        return None
    instrukce = _instrukce(db, navrh["reservation_id"])
    stary = instrukce.get("kod")
    if not stary or stary not in navrh["text"] or not instrukce.get("smoobu_id"):
        return None
    try:
        aktualni = kod_bytu(instrukce["smoobu_id"])
    except UklidyChyba as e:
        return f"Nepodařilo se ověřit kód keyboxu v aplikaci úklidů ({e}), proto zprávu s kódem {stary} neodesílám."
    if aktualni and aktualni != stary:
        zneplatni_instrukce(db, instrukce["smoobu_id"], aktualni)
        return f"Kód keyboxu se mezitím změnil ({stary} → {aktualni}), instrukce připravím znovu."
    return None


def _hlidej_prijezdy(smoobu, db, byty_):
    ted = datetime.now()
    if ted.time() < cas(config.UKLID_KONTROLA_HODINA):
        return
    dnes = kontext.dnes()
    for r in smoobu.reservations(dnes, dnes):
        if r.get("is-blocked-booking") or db.nastaveni(f"uklid_kontrola_{r['id']}") == "hotovo":
            continue
        smoobu_id = (r.get("apartment") or {}).get("id")
        if str(smoobu_id) not in byty_:
            continue  # byt v aplikaci úklidů (zatím) není
        uklizeno, popis = stav_pro_prijezd(smoobu_id, dnes)
        if not uklizeno:
            oznameni.posli(f"🧹⏰ Dnes přijíždí {r.get('guest-name')} do bytu {(r.get('apartment') or {}).get('name')} "
                           f"(check-in od 15:00), ale byt podle aplikace ještě není uklizený.\n{popis}")
        db.uloz_nastaveni(f"uklid_kontrola_{r['id']}", "hotovo")
