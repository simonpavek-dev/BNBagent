"""Nedělní přehled pro hostitele (přepínač TYDENNI_PREHLED): na co Vasil za posledních 7 dní potřeboval hostitele
a jaké informace mu chybí ve znalostní bázi, aby to příště zvládl sám.

Čísla a seznam případů (eskalace, odpovědi zastavené kontrolou, návrhy přepsané ✏️ nebo zahozené) skládá kód
z databáze agenta; doporučení napíše model – jedno volání týdně, a jen když nějaké případy jsou. Když model nejde,
přehled přijde bez doporučení. Posílá hlavní smyčka v neděli v TYDENNI_PREHLED_HODINA, kdykoli příkaz /prehled
(`telegram_ovladani`).
"""
import json
import logging
from collections import Counter
from datetime import datetime, timedelta

from . import hodiny, mozek, oznameni, znacky, znalosti

log = logging.getLogger("agent")
DNI = 7
MAX_PRIPADU = 25   # do Telegramu i do modelu jen tolik nejnovějších případů
MAX_TEXT = 160     # zpráva hosta v Telegramu (model dostane až 600 znaků)
DNY = ("po", "út", "st", "čt", "pá", "so", "ne")
VYSLEDKY = {"ceka": "⏳ pořád čeká na vás", "zahozeno": "označeno jako vyřízené", "zastarale": "host mezitím psal znovu",
            "odeslano": "host dostal odpověď", "selhalo": "odeslání selhalo"}


def _zkrat(text, delka):
    text = " ".join(str(text or "").split())
    return text[:delka] + "…" if len(text) > delka else text


def _byt(hlavicka):
    return str(hlavicka or "?").split(" · ")[0]


def pripady(db, od):
    """Případy od `od` (ISO čas), kdy Vasil potřeboval hostitele, od nejstaršího."""
    navrhy = db.conn.execute(
        "SELECT id, reservation_id, message_id, text, stav, cas FROM navrhy WHERE cas >= ? ORDER BY id", (od,)).fetchall()
    out = []
    for cas, rid, detail in db.conn.execute(
            "SELECT cas, reservation_id, detail FROM udalosti WHERE akce = 'rozhodnuti' AND cas >= ? ORDER BY id", (od,)):
        try:
            d = json.loads(detail or "")
        except ValueError:
            continue
        if not isinstance(d, dict):
            continue
        rid = str(rid)
        kandidati = [n for n in navrhy if n[1] == rid and n[2] and n[5] >= cas]
        navrh = next((n for n in kandidati if n[3] == d.get("odpoved_hostovi")), kandidati[0] if kandidati else None)
        stav = navrh[4] if navrh else None
        if d.get("rozhodnuti") == "eskalovat":
            typ = "eskalace"
        elif d.get("kontrola"):
            typ = "kontrola"
        elif stav in ("nahrazeno", "zahozeno"):
            typ = "přepsáno" if stav == "nahrazeno" else "zahozeno"
        else:
            continue
        napsal = None
        if stav == "nahrazeno":  # hostitelův text přes ✏️ = další návrh téže rezervace bez zprávy hosta
            nahrada = next((n for n in navrhy if n[0] > navrh[0] and n[1] == rid and not n[2]), None)
            napsal = nahrada[3] if nahrada else None
        out.append({"typ": typ, "cas": cas, "byt": _byt(d.get("hlavicka")), "zprava_hosta": d.get("zprava_hosta") or "",
                    "duvod": d.get("kontrola") or d.get("duvod") or "", "navrh_vasila": d.get("navrh_pro_hostitele") or "",
                    "stav": stav, "hostitel_napsal": napsal})
    return out[-MAX_PRIPADU:]


def _pocty(db, od):
    zpravy = dict(db.conn.execute("SELECT stav, COUNT(*) FROM zpravy WHERE cas >= ? GROUP BY stav", (od,)).fetchall())
    sam = db.conn.execute(
        "SELECT COUNT(*) FROM odchozi o JOIN navrhy n ON n.id = o.navrh_id WHERE o.cas >= ? AND o.zdroj = 'automaticky' "
        "AND o.stav = 'odeslano' AND COALESCE(n.message_id, '') != ''", (od,)).fetchone()[0]
    return sum(zpravy.values()), sam


def _kontext_pro_model(seznam):
    radky = []
    for i, p in enumerate(seznam, 1):
        radky.append(f"{i}. [{p['typ']}] byt: {p['byt']}\nHost napsal: {_zkrat(p['zprava_hosta'], 600)}\n"
                     f"Proč Vasil nevěděl / co se stalo: {p['duvod']}\nVasilův návrh pro hostitele: {p['navrh_vasila']}"
                     + (f"\nHostitel hostovi nakonec napsal: {_zkrat(p['hostitel_napsal'], 600)}" if p["hostitel_napsal"] else ""))
    return "PŘÍPADY Z POSLEDNÍHO TÝDNE:\n\n" + "\n\n".join(radky)


def _znalosti_bytu():
    """Znalostní báze všech bytů pro model – bez kódů a hesel (značky)."""
    casti = []
    for soubor, data in znalosti.vsechny_apartmany():
        _, text = znalosti.apartman_podle_souboru(soubor)
        casti.append(f"# {data.get('nazev') or soubor}\n" + znacky.schovej(text, data, znacky.hodnoty(data, None)))
    return "\n\n".join(casti)


def _doporuceni(seznam):
    try:
        return mozek.doporuc_doplneni(znalosti.obecne_text(), _znalosti_bytu(), _kontext_pro_model(seznam)), ""
    except Exception as e:
        log.exception("Doporučení pro týdenní přehled")
        return None, f"\n\n💡 Doporučení se teď nepodařilo připravit ({_zkrat(e, 120)}). Zkuste později /prehled."


def sestav(db, ted=None):
    ted = ted or hodiny.ted()
    od = ted - timedelta(days=DNI)
    od_iso = od.isoformat(timespec="seconds")
    seznam = pripady(db, od_iso)
    celkem, sam = _pocty(db, od_iso)
    druhy = Counter(p["typ"] for p in seznam)
    text = (f"📊 TÝDENNÍ PŘEHLED {od.day}. {od.month}. – {ted.day}. {ted.month}.\n"
            f"Zprávy hostů: {celkem} · Vasil odpověděl sám: {sam} · potřeboval vás: {druhy['eskalace']}"
            f" · zastavila kontrola: {druhy['kontrola']} · návrhy přepsané: {druhy['přepsáno']}, zahozené: {druhy['zahozeno']}")
    if not seznam:
        return text + "\n\n✅ Tento týden vás Vasil nepotřeboval – všechno vyřídil sám."
    text += f"\n\n🔔 Kde vás Vasil potřeboval ({len(seznam)}):"
    for i, p in enumerate(seznam, 1):
        kdy = datetime.fromisoformat(p["cas"])
        text += (f"\n{i}. {p['byt']} · {DNY[kdy.weekday()]} {kdy.day}. {kdy.month}. – „{_zkrat(p['zprava_hosta'], MAX_TEXT)}“"
                 f"\n   {p['typ'].capitalize()}: {_zkrat(p['duvod'], MAX_TEXT)}")
        if p["hostitel_napsal"]:
            text += f"\n   → odpověděli jste: „{_zkrat(p['hostitel_napsal'], MAX_TEXT)}“"
        elif p["stav"] in VYSLEDKY:
            text += f"\n   → {VYSLEDKY[p['stav']]}"
    vysledek, chyba = _doporuceni(seznam)
    if not vysledek:
        return text + chyba
    if vysledek.get("doporuceni"):
        text += "\n\n💡 Co doplnit, aby to příště zvládl sám:"
        for d in vysledek["doporuceni"]:
            text += f"\n• {d['byt']} – {d['co_doplnit']} ({d['proc']})\n  Stačí napsat: „{d['veta_pro_vasila']}“"
    else:
        text += "\n\n💡 Ve znalostní bázi nic nechybí – šlo o věci, které musíte rozhodnout vy."
    if vysledek.get("nechat_na_hostitelich"):
        text += "\n\n✋ I dál se vás bude ptát: " + ", ".join(vysledek["nechat_na_hostitelich"])
    if vysledek.get("shrnuti"):
        text += f"\n\n📝 {vysledek['shrnuti']}"
    return text


def posli(db):
    oznameni.posli(sestav(db))
