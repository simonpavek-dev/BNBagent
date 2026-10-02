"""Napojení na naši aplikaci úklidů (uklid.kolbl-apartments.cz): stav úklidů a kódy keyboxů zapsané u úklidů.

Aplikace nemá API – agent se přihlásí vlastním účtem (UKLIDY_LOGIN / UKLIDY_HESLO v .env) a čte stránku /uklidy
(Next.js v ní posílá data o pobytech jako JSON). Když údaje v .env chybí, je napojení vypnuté.

V aplikaci je víc bytů než ve Smoobu. Agent pracuje jen s těmi, které spáruje se znalostní bází podle názvu
`uklidy_nazev` v souboru bytu (např. "Školská 3+1"). Ostatní byty ignoruje.

Kódy: platný kód je `keybox_kod` ve znalostní bázi. Když je v aplikaci u novějšího úklidu zapsaný jiný kód,
agent kód hostům neposílá a zeptá se hostitele (`keybox_kod_overeno` = den, kdy hostitel kód naposledy ověřil).
"""
import html
import json
import logging
import re
import time
import unicodedata
from datetime import datetime, time as cas

import requests

from . import config, kontext, oznameni, znalosti

log = logging.getLogger("agent")
_session = [None]
_cache = {"cas": 0.0, "pobyty": None}


class UklidyChyba(Exception):
    pass


def zapnuto():
    return bool(config.UKLIDY_URL and config.UKLIDY_LOGIN and config.UKLIDY_HESLO)


def _klic(nazev):
    """„Školská 3+1“ a „skolska 3+1 “ jsou totéž."""
    return " ".join(unicodedata.normalize("NFKD", str(nazev or "")).encode("ascii", "ignore").decode().lower().split())


# ---------------------------------------------------------------- čtení aplikace

def _url(cesta):
    return config.UKLIDY_URL.rstrip("/") + cesta


def _prihlas(s):
    try:
        r = s.get(_url("/login"), timeout=20)
        form = re.search(r"<form.*?</form>", r.text, re.S)
        if not form:
            raise UklidyChyba("Aplikace úklidů: přihlašovací formulář nenalezen (změnila se aplikace?)")
        data = {html.unescape(n): html.unescape(v or "") for n, v in
                re.findall(r'<input type="hidden" name="([^"]+)"(?: value="([^"]*)")?', form.group(0))}
        data.update(email=config.UKLIDY_LOGIN, password=config.UKLIDY_HESLO)
        r = s.post(_url("/login"), files={k: (None, v) for k, v in data.items()}, allow_redirects=False, timeout=20)
    except requests.RequestException as e:
        raise UklidyChyba(f"Aplikace úklidů nedostupná ({type(e).__name__})") from None
    if r.status_code not in (302, 303):
        chyba = re.search(r'error\\?":\\?"([^"\\]+)', r.text)
        raise UklidyChyba(f"Aplikace úklidů: přihlášení se nepovedlo ({chyba.group(1) if chyba else r.status_code})")


def _stahni():
    """Všechny pobyty ze stránky /uklidy: [{"stay": {...}, "apartment": {...}}, ...]."""
    s = _session[0] or requests.Session()
    _session[0] = s
    try:
        r = s.get(_url("/uklidy"), timeout=30)
        if "/login" in r.url:
            _prihlas(s)
            r = s.get(_url("/uklidy"), timeout=30)
    except requests.RequestException as e:
        raise UklidyChyba(f"Aplikace úklidů nedostupná ({type(e).__name__})") from None
    if "/login" in r.url or r.status_code >= 400:
        raise UklidyChyba(f"Aplikace úklidů: stránku /uklidy nejde otevřít ({r.status_code})")
    casti = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', r.text, re.S)
    data = "".join(json.loads('"' + c + '"') for c in casti)
    dekoder, polozky = json.JSONDecoder(), []
    for m in re.finditer(r'\{"stay":', data):
        try:
            polozky.append(dekoder.raw_decode(data, m.start())[0])
        except ValueError:
            pass
    if not polozky:
        raise UklidyChyba("Aplikace úklidů: na stránce /uklidy nejsou žádné pobyty (změnila se aplikace?)")
    return polozky


def _nase_byty():
    """{název bytu v aplikaci úklidů: soubor bytu ve znalostní bázi} (pole uklidy_nazev)."""
    return {_klic(d.get("uklidy_nazev")): d for _, d in znalosti.vsechny_apartmany()
            if d.get("uklidy_nazev") and d.get("smoobu_id")}


def pobyty():
    """Pobyty našich bytů (nejvýš minutu staré): smoobu_id, byt, odjezd, datum úklidu, kód, uklizeno, host."""
    if _cache["pobyty"] is not None and time.time() - _cache["cas"] < 60:
        return _cache["pobyty"]
    nase = _nase_byty()
    out = []
    for x in _stahni():
        stay, byt = x.get("stay") or {}, x.get("apartment") or {}
        apartman = nase.get(_klic(byt.get("name")))
        if not apartman:
            continue  # cizí byt, který nemáme ve Smoobu
        out.append({
            "smoobu_id": str(apartman["smoobu_id"]).strip(), "byt": str(byt.get("name") or "").strip(),
            "id": stay.get("id"), "odjezd": stay.get("checkOut"), "datum": stay.get("cleaningDate") or stay.get("checkOut"),
            "kod": str(stay.get("codes") or "").strip() or None, "uklizeno": stay.get("uklidStatus") == "uklizeno",
            "host": stay.get("guestName"),
        })
    out.sort(key=lambda p: (p["datum"] or "", p["id"] or ""))
    _cache.update(cas=time.time(), pobyty=out)
    return out


# ---------------------------------------------------------------- kódy

def _apartman(smoobu_id):
    return next((d for _, d in znalosti.vsechny_apartmany() if str(d.get("smoobu_id")).strip() == str(smoobu_id)), {})


def rozpor_v_kodu(smoobu_id, den=None):
    """Je v aplikaci u úklidu (nejpozději v daný den) zapsaný jiný kód než ve znalostní bázi, a to později,
    než ho hostitel naposledy ověřil? Vrací popis rozporu, nebo None."""
    prijezd = (_apartman(smoobu_id).get("prijezd") or {})
    kod = str(prijezd.get("keybox_kod") or "").strip()
    overeno = str(prijezd.get("keybox_kod_overeno") or "").strip()
    den = (den or kontext.dnes()).isoformat()
    zapsane = [p for p in pobyty() if p["smoobu_id"] == str(smoobu_id) and p["kod"] and (p["datum"] or "") <= den]
    if not zapsane or not kod:
        return None
    posledni = zapsane[-1]
    if posledni["kod"] == kod or (overeno and posledni["datum"] <= overeno):
        return None
    return f"v aplikaci úklidů je u úklidu {posledni['datum']} zapsaný kód {posledni['kod']}, ve znalostní bázi {kod}"


def kod_stale_plati(db, navrh):
    """Pojistka těsně před odesláním návrhu s kódem keyboxu. Vrací None, když je vše v pořádku,
    jinak důvod, proč návrh neodeslat."""
    instrukce = _instrukce(db, navrh["reservation_id"])
    stary, smoobu_id = instrukce.get("kod"), instrukce.get("smoobu_id")
    if not stary or stary not in navrh["text"] or not smoobu_id:
        return None
    aktualni = str((_apartman(smoobu_id).get("prijezd") or {}).get("keybox_kod") or "").strip()
    if aktualni and aktualni != stary:
        zneplatni_instrukce(db, smoobu_id)
        return f"Kód keyboxu se mezitím změnil ({stary} → {aktualni}), instrukce připravím znovu."
    if not zapnuto():
        return None
    try:
        rozpor = rozpor_v_kodu(smoobu_id)
    except UklidyChyba as e:
        return f"Nepodařilo se ověřit kód v aplikaci úklidů ({e}), proto zprávu s kódem {stary} neodesílám."
    return f"Kód nesedí – {rozpor}. Ověřte, který platí." if rozpor else None


def _instrukce(db, reservation_id):
    """Poslední připravené instrukce k příjezdu dané rezervace (kód a byt, pro který byly), nebo {}."""
    radek = db.conn.execute("SELECT detail FROM udalosti WHERE akce = 'instrukce_prijezd' AND reservation_id = ? "
                            "ORDER BY id DESC LIMIT 1", (str(reservation_id),)).fetchone()
    return json.loads(radek[0]) if radek else {}


def zneplatni_instrukce(db, smoobu_id):
    """Čekající/naplánované instrukce s kódem, který už neplatí, se neodešlou – agent je připraví znovu."""
    aktualni = str((_apartman(smoobu_id).get("prijezd") or {}).get("keybox_kod") or "").strip()
    for navrh_id, rid, text, tg in db.conn.execute(
            "SELECT id, reservation_id, text, tg_message_id FROM navrhy WHERE stav IN ('ceka', 'schvaleno')").fetchall():
        instrukce = _instrukce(db, rid)
        stary = instrukce.get("kod")
        if str(instrukce.get("smoobu_id")) != str(smoobu_id) or not stary or stary not in text:
            continue
        if stary == aktualni and not (zapnuto() and rozpor_v_kodu(smoobu_id)):
            continue
        db.uprav_navrh(navrh_id, stav="zastarale")
        db.uloz_nastaveni(f"prijezd_{rid}", "")  # v příštím cyklu se připraví znovu
        oznameni.odeber_tlacitka(tg)
        oznameni.posli(f"♻️ Instrukce k příjezdu (rez. {rid}) obsahovaly kód {stary}, který teď nemusí platit – "
                       "neodešlu je. Až bude kód jasný, připravím nové ke schválení.")


# ---------------------------------------------------------------- stav úklidu

def stav_pro_prijezd(smoobu_id, den):
    """Stav posledního úklidu bytu před příjezdem v daný den: (uklizeno, popis)."""
    pred = [p for p in pobyty() if p["smoobu_id"] == str(smoobu_id) and (p["datum"] or "") <= den.isoformat()]
    if not pred:
        return False, "V aplikaci úklidů není žádný úklid tohoto bytu před příjezdem."
    p = pred[-1]
    if p["uklizeno"]:
        return True, f"Byt je uklizený (úklid {p['datum']} je v aplikaci odkliknutý)."
    return False, f"Úklid {p['datum']} zatím v aplikaci není odkliknutý jako uklizený."


def popis_pro_zpravu(rezervace):
    """Doplněk ke kontextu zprávy hosta (hlavně kvůli dřívějšímu check-inu). Při chybě aplikace prázdný."""
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


# ---------------------------------------------------------------- hlídání (volá se v každém cyklu agenta)

def zkontroluj(smoobu, db):
    """Po každém odkliknutém úklidu zkontroluje kód, hlídá rozpory v kódech a v den příjezdu, že je uklizeno."""
    if not zapnuto():
        return
    dnes = kontext.dnes().isoformat()
    prvni_beh = db.nastaveni("uklidy_inicializovano") != "ano"
    for p in pobyty():
        if not p["uklizeno"] or db.nastaveni(f"uklid_{p['id']}") == "zkontrolovano":
            continue
        if not prvni_beh and p["datum"] >= dnes:  # starší úklidy z doby před zapnutím napojení nehlásit
            _po_uklidu(db, p)
        db.uloz_nastaveni(f"uklid_{p['id']}", "zkontrolovano")
    db.uloz_nastaveni("uklidy_inicializovano", "ano")
    for smoobu_id in {p["smoobu_id"] for p in pobyty()}:
        _hlidej_rozpor(db, smoobu_id)
    _hlidej_prijezdy(smoobu, db)


def _po_uklidu(db, p):
    kod = str((_apartman(p["smoobu_id"]).get("prijezd") or {}).get("keybox_kod") or "").strip()
    if p["kod"] and p["kod"] == kod:
        db.zapis("", "uklid", {"byt": p["byt"], "datum": p["datum"], "kod": "sedí"})
    elif not p["kod"]:
        oznameni.posli(f"🧹 {p['byt']}: úklid {p['datum']} je odkliknutý, ale v aplikaci u něj není zapsaný kód. "
                       f"Ověřte prosím, že na keyboxu je {kod or '(kód ve znalostní bázi chybí)'}.")
    # jiný kód hlásí _hlidej_rozpor


def _hlidej_rozpor(db, smoobu_id):
    rozpor = rozpor_v_kodu(smoobu_id)
    if not rozpor or db.nastaveni(f"rozpor_kodu_{smoobu_id}") == rozpor:
        return
    nazev = _apartman(smoobu_id).get("nazev") or smoobu_id
    oznameni.posli(f"🔑❗ {nazev}: {rozpor}. Dokud nebude jasné, který kód platí, agent ho hostům neposílá. "
                   "Napište mi správný kód (nebo ho opravte v aplikaci úklidů).")
    db.uloz_nastaveni(f"rozpor_kodu_{smoobu_id}", rozpor)
    zneplatni_instrukce(db, smoobu_id)


def _hlidej_prijezdy(smoobu, db):
    if datetime.now().time() < cas(config.UKLID_KONTROLA_HODINA):
        return
    dnes = kontext.dnes()
    nase = {p["smoobu_id"] for p in pobyty()}
    for r in smoobu.reservations(dnes, dnes):
        smoobu_id = str((r.get("apartment") or {}).get("id"))
        if r.get("is-blocked-booking") or smoobu_id not in nase or db.nastaveni(f"uklid_kontrola_{r['id']}") == "hotovo":
            continue
        uklizeno, popis = stav_pro_prijezd(smoobu_id, dnes)
        if not uklizeno:
            oznameni.posli(f"🧹⏰ Dnes přijíždí {r.get('guest-name')} do bytu {(r.get('apartment') or {}).get('name')} "
                           f"(check-in od 15:00), ale byt podle aplikace ještě není uklizený.\n{popis}")
        db.uloz_nastaveni(f"uklid_kontrola_{r['id']}", "hotovo")
