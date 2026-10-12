"""Napojení na naši aplikaci úklidů (uklid.kolbl-apartments.cz): stav úklidů a kódy keyboxů zapsané u úklidů.

Aplikace nemá API – agent se přihlásí vlastním účtem (UKLIDY_LOGIN / UKLIDY_HESLO v .env) a čte stránku /uklidy
(Next.js v ní posílá data o pobytech jako JSON). Když údaje v .env chybí, je napojení vypnuté.

V aplikaci je víc bytů než ve Smoobu. Agent pracuje jen s těmi, které spáruje se znalostní bází podle názvu
`uklidy_nazev` v souboru bytu (např. "Školská 3+1"). Ostatní byty ignoruje.

Kódy: aplikace je hlavní zdroj. Agent ji čte každých UKLIDY_INTERVAL_MINUT minut; nový kód zapsaný u úklidu převezme
(uloží do databáze, ohlásí ve skupině) a drží ho, dokud se neobjeví jiný. `keybox_kod` v souboru bytu platí jen tehdy,
když je jeho `keybox_kod_overeno` novější než poslední zápis v aplikaci.
"""
import html
import json
import logging
import re
import time
import unicodedata
from datetime import datetime, time as cas, timedelta

import requests

from . import config, hodiny, kontext, oznameni, znalosti
from .databaze import Databaze

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
    """Pobyty našich bytů (obnovují se každých UKLIDY_INTERVAL_MINUT): smoobu_id, byt, odjezd, datum úklidu, kód, uklizeno, host."""
    if _cache["pobyty"] is not None and time.time() - _cache["cas"] < config.UKLIDY_INTERVAL_MINUT * 60:
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


def _kod_ze_znalosti(smoobu_id):
    """(kód, den ověření) ze souboru bytu – platí, dokud v aplikaci nepřibude novější kód."""
    prijezd = _apartman(smoobu_id).get("prijezd") or {}
    return str(prijezd.get("keybox_kod") or "").strip(), str(prijezd.get("keybox_kod_overeno") or "").strip()


def _posledni_z_aplikace(smoobu_id):
    """(kód, datum úklidu) – poslední kód zapsaný v aplikaci u úklidu do dneška, nebo (None, "")."""
    dnes = kontext.dnes().isoformat()
    zapsane = [p for p in pobyty() if p["smoobu_id"] == str(smoobu_id) and p["kod"] and (p["datum"] or "") <= dnes]
    return (zapsane[-1]["kod"], zapsane[-1]["datum"]) if zapsane else (None, "")


def _ulozeny(db, smoobu_id):
    """(kód, datum úklidu) naposledy převzatý z aplikace a uložený v databázi agenta."""
    return db.nastaveni(f"kod_{smoobu_id}", ""), db.nastaveni(f"kod_{smoobu_id}_datum", "")


def _nejnovejsi(kandidati):
    """kandidati = [(datum, priorita, kód)] – vyhrává novější datum, při stejném datu vyšší priorita."""
    kandidati = [(d or "", pr, k) for d, pr, k in kandidati if k]
    return max(kandidati)[2] if kandidati else None


def aktualni_kod(smoobu_id, db=None):
    """Platný kód keyboxu: nejnovější z (soubor bytu + den ověření, kód převzatý z aplikace a uložený v databázi,
    kód právě zapsaný v aplikaci). Když aplikace nejde přečíst, platí poslední známý kód."""
    db = db or Databaze()
    kandidati = [_kandidat_znalosti(smoobu_id), _kandidat_db(db, smoobu_id)]
    if zapnuto():
        try:
            kod, datum = _posledni_z_aplikace(smoobu_id)
            kandidati.append((datum, 2, kod))
        except UklidyChyba as e:
            log.warning("%s – používám poslední známý kód", e)
    return _nejnovejsi(kandidati)


def _kandidat_znalosti(smoobu_id):
    kod, overeno = _kod_ze_znalosti(smoobu_id)
    return overeno, 0, kod


def _kandidat_db(db, smoobu_id):
    kod, datum = _ulozeny(db, smoobu_id)
    return datum, 1, kod


def kod_stale_plati(db, navrh):
    """Pojistka těsně před odesláním návrhu s kódem keyboxu. Vrací None, když je vše v pořádku,
    jinak důvod, proč návrh neodeslat."""
    instrukce = _instrukce(db, navrh["reservation_id"])
    stary, smoobu_id = instrukce.get("kod"), instrukce.get("smoobu_id")
    if not stary or stary not in navrh["text"] or not smoobu_id:
        return None
    aktualni = aktualni_kod(smoobu_id, db)
    if aktualni and aktualni != stary:
        zneplatni_instrukce(db, smoobu_id)
        return f"Kód keyboxu se mezitím změnil ({stary} → {aktualni}), instrukce připravím znovu."
    return None


def _instrukce(db, reservation_id):
    """Poslední připravené instrukce k příjezdu dané rezervace (kód a byt, pro který byly), nebo {}."""
    radek = db.conn.execute("SELECT detail FROM udalosti WHERE akce = 'instrukce_prijezd' AND reservation_id = ? "
                            "ORDER BY id DESC LIMIT 1", (str(reservation_id),)).fetchone()
    return json.loads(radek[0]) if radek else {}


def zneplatni_instrukce(db, smoobu_id):
    """Čekající/naplánované instrukce se starým kódem se neodešlou – agent je připraví znovu s platným kódem."""
    aktualni = aktualni_kod(smoobu_id, db)
    for navrh_id, rid, text, tg in db.conn.execute(
            "SELECT id, reservation_id, text, tg_message_id FROM navrhy WHERE stav IN ('ceka', 'schvaleno')").fetchall():
        instrukce = _instrukce(db, rid)
        stary = instrukce.get("kod")
        if str(instrukce.get("smoobu_id")) != str(smoobu_id) or not stary or stary == aktualni or stary not in text:
            continue
        db.uprav_navrh(navrh_id, stav="zastarale")
        db.uloz_nastaveni(f"prijezd_{rid}", "")  # v příštím cyklu se připraví znovu
        oznameni.odeber_tlacitka(tg)
        oznameni.posli(f"♻️ Instrukce k příjezdu (rez. {rid}) obsahovaly starý kód {stary} – neodešlu je, "
                       f"připravím nové s kódem {aktualni} ke schválení.")


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
    """Převezme nové kódy zapsané v aplikaci (data se obnovují každých UKLIDY_INTERVAL_MINUT)
    a v den příjezdu hlídá, že je uklizeno."""
    if not zapnuto():
        return
    for smoobu_id in {p["smoobu_id"] for p in pobyty()}:
        _prevezmi_kod(db, smoobu_id, smoobu)
    if config.HLIDANI_UKLIDU_K_PRIJEZDU:
        _hlidej_prijezdy(smoobu, db)
    if config.NABIDKA_DRIVEJSIHO_CHECKINU:
        _nabidni_drivejsi_checkin(smoobu, db)


TEXT_DRIVEJSI_CHECKIN = ("Dobrá zpráva! Náš úklidový tým už všechno stihl a byt je pro vás připravený už teď – "
                         "nemusíte čekat do {check_in}, můžete se ubytovat kdykoli. Přístupové údaje jsou stejné "
                         "jako v naší předchozí zprávě. Příjemný pobyt!")


def _nabidni_drivejsi_checkin(smoobu, db):
    """V den příjezdu: instrukce už host má, check-in je až od 15:00 a úklid je v aplikaci odkliknutý dřív
    → hostovi nabídnout, že může přijít hned. Vždy jen jako návrh ke schválení ve skupině."""
    from . import mozek, navrhy, prace  # prace importuje kody → uklidy; tady až za běhu
    ted = hodiny.ted()
    nase = {p["smoobu_id"] for p in pobyty()}
    for r in smoobu.reservations(kontext.dnes(), kontext.dnes()):
        smoobu_id = str((r.get("apartment") or {}).get("id"))
        if r.get("is-blocked-booking") or smoobu_id not in nase or db.nastaveni(f"drivejsi_{r['id']}"):
            continue
        check_in = str((_apartman(smoobu_id).get("prijezd") or {}).get("check_in_od") or "15:00")
        konec = datetime.combine(ted.date(), datetime.strptime(check_in, "%H:%M").time()) - timedelta(minutes=30)
        if not (datetime.strptime(config.DRIVEJSI_CHECKIN_OD, "%H:%M").time() <= ted.time() < konec.time()):
            continue
        if not stav_pro_prijezd(smoobu_id, kontext.dnes())[0]:
            continue  # ještě neuklizeno – zkusí se za 10 minut
        kod = aktualni_kod(smoobu_id, db)
        zpravy = smoobu.messages(r["id"])
        if not kod or not any(m.get("type") != 1 and kod in (m.get("message") or "") for m in zpravy):
            continue  # instrukce s kódem host ještě nemá
        jazyk = _instrukce(db, r["id"]).get("jazyk_hosta") or r.get("language") or "angličtina"
        text = mozek.priprav_zpravu_hostitele(TEXT_DRIVEJSI_CHECKIN.format(check_in=check_in), jazyk)
        hlavicka = prace._hlavicka(r)
        db.uloz_nastaveni(f"drivejsi_{r['id']}", ted.isoformat(timespec="seconds"))
        # vždy jen návrh ke schválení – i v ostrém režimu (přání hostitele)
        navrh_id = db.novy_navrh(r["id"], zpravy[-1].get("id") if zpravy else "", text, jazyk, hlavicka)
        db.uprav_navrh(navrh_id, tg_message_id=oznameni.posli(
            f"🧹✅ BYT JE UKLIZENÝ DŘÍV – nabídnout hostovi dřívější check-in?\n{hlavicka}\n\n{text}",
            navrhy.TLACITKA_NAVRHU(navrh_id), navrh_id=navrh_id))


def _prevezmi_kod(db, smoobu_id, smoobu=None):
    kod, datum = _posledni_z_aplikace(smoobu_id)
    ulozeny_kod, ulozeny_datum = _ulozeny(db, smoobu_id)
    if not kod or (kod, datum) == (ulozeny_kod, ulozeny_datum) or datum < ulozeny_datum:
        return
    _, overeno = _kod_ze_znalosti(smoobu_id)
    if overeno and datum < overeno:
        return  # starší zápis v aplikaci, než kdy hostitel kód naposledy ověřil
    predtim = _nejnovejsi([_kandidat_znalosti(smoobu_id), _kandidat_db(db, smoobu_id)])
    db.uloz_nastaveni(f"kod_{smoobu_id}", kod)
    db.uloz_nastaveni(f"kod_{smoobu_id}_datum", datum)
    db.zapis("", "kod_z_aplikace", {"smoobu_id": smoobu_id, "kod": kod, "datum_uklidu": datum, "predtim": predtim})
    if kod != predtim:
        nazev = _apartman(smoobu_id).get("nazev") or smoobu_id
        oznameni.posli(f"🔑 {nazev}: v aplikaci úklidů je u úklidu {datum} nový kód keyboxu {kod} "
                       f"(dosud {predtim or '?'}). Agent od teď posílá hostům {kod}.")
        zneplatni_instrukce(db, smoobu_id)
        if smoobu is not None and config.OPRAVA_KODU_PO_UKLIDU:
            _oprav_odeslane_instrukce(smoobu, db, smoobu_id, predtim, kod, datum)


def _oprav_odeslane_instrukce(smoobu, db, smoobu_id, stary, novy, datum_uklidu):
    """Varianta B (DECISIONS.md D3): hosté, kteří přijíždějí po tomto úklidu a instrukce se starým kódem už dostali,
    dostanou opravu s novým kódem – stejnou cestou jako instrukce (automaticky / ke schválení)."""
    from . import instrukce, navrhy, prace  # prace → kody → uklidy: import až za běhu
    if not stary:
        return
    dnes = hodiny.dnes()
    for r in smoobu.reservations(kontext._datum(datum_uklidu), dnes + timedelta(days=1)):
        odjezd = kontext._datum(r.get("departure"))
        if (str((r.get("apartment") or {}).get("id")) != str(smoobu_id) or r.get("is-blocked-booking")
                or (odjezd and odjezd <= dnes) or db.nastaveni(f"oprava_kodu_{r['id']}") == novy):
            continue
        nase = [m.get("message") or "" for m in smoobu.messages(r["id"]) if m.get("type") != 1]
        if not any(stary in t for t in nase) or any(novy in t for t in nase):
            continue  # instrukce se starým kódem nedostal, nebo už nový kód má
        text, jazyk, poznamka = instrukce.oprava_kodu(r, novy)
        hlavicka = prace._hlavicka(r)
        navrh_id = db.novy_navrh(r["id"], "", text, jazyk, hlavicka)
        db.uloz_nastaveni(f"oprava_kodu_{r['id']}", novy)
        db.zapis(r["id"], "instrukce_prijezd", {"kod": novy, "smoobu_id": str(smoobu_id), "oprava_z": stary,
                                               "jazyk_hosta": jazyk})
        if poznamka:
            oznameni.posli(f"ℹ️ {poznamka}\n{hlavicka}")
        if config.PRIJEZDY_AUTOMATICKY:
            try:
                _, vysledek = navrhy.odeslat(smoobu, db, db.navrh(navrh_id), "automaticky")
            except Exception as e:
                db.uprav_navrh(navrh_id, stav="selhalo")
                vysledek = f"⚠️ NEPODAŘILO se ji odeslat ({str(e)[:150]}) – pošli ji prosím ručně"
            oznameni.posli(f"🔑 Oprava kódu ({stary} → {novy}) pro hosta s už odeslanými instrukcemi: {vysledek}\n"
                           f"{hlavicka}\n\n{text}")
        else:
            db.uprav_navrh(navrh_id, tg_message_id=oznameni.posli(
                f"🔑 OPRAVA KÓDU KEYBOXU ({stary} → {novy}) – host už má instrukce se starým kódem, ke schválení\n"
                f"{hlavicka}\n\n{text}", navrhy.TLACITKA_NAVRHU(navrh_id), navrh_id=navrh_id))


def _hlidej_prijezdy(smoobu, db):
    if hodiny.ted().time() < cas(config.UKLID_KONTROLA_HODINA):
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
