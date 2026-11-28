"""Hlídání Poslanecké sněmovny (přepínač HLIDANI_LEGISLATIVY): návrhy zákonů a jednání, které se týkají krátkodobého
ubytování – eTurista, registrace bytů, omezení počtu nocí, kolaudace, pravomoci Prahy a obcí a další omezení (TEMATA).
Zprávy („🏛️ SNĚMOVNA …“) jdou do skupiny hostitelů: hned, když se něco stane, a v pondělí ráno souhrn.

Zdroj: otevřená data psp.cz (tisky.zip, schuze.zip, steno.zip, poslanci.zip – úplný stav, aktualizují se denně),
text tisků (PDF) a stenozáznamy (HTML po 10 minutách). Data se stahují v LEGISLATIVA_HODINY; texty tisků a stenozáznamy
se pak stahují po dávkách (MAX_STAZENI_ZA_CYKLUS) v dalších cyklech, aby hlídání nezdrželo odpovědi hostům.
Model se volá jen u textu, ve kterém se témata opravdu objeví. Při prvním běhu se posoudí rozpracované tisky (a tisky
ukončené za POCATECNI_DNI) a přijde úvodní přehled; staré stenozáznamy se přeskočí.
Volá hlavní smyčka (`__main__.jeden_cyklus`).
"""
import html
import io
import json
import logging
import re
import zipfile
from datetime import datetime, timedelta

import requests

from . import config, hodiny, mozek, oznameni

log = logging.getLogger("agent")
logging.getLogger("pypdf").setLevel(logging.ERROR)  # poškozené PDF tisků jinak zaplní log varováními
PSP = "https://www.psp.cz"
MAX_STAZENI_ZA_CYKLUS = 3   # textů tisků a stenozáznamů v jednom cyklu agenta (velký tisk se čte i 10 s)
MAX_POKUSU = 3
POCATECNI_DNI = 120         # první běh: kromě rozpracovaných i tisky ukončené za tolik dní
MAX_STRAN_PDF = 150
MAX_VYNATKU = 12000         # znaků textu pro model
OKOLI = 400                 # znaků kolem nalezeného slova
NAVRHY_ZAKONU = ("1", "2")  # druh tisku: vládní návrh zákona, návrh zákona (poslanci, Senát, kraje)
STAV_PROJEDNANO = "6"       # typ_stavu: projednávání tisku skončilo
STAVY_BODU = {"0": "projednán", "1": "neprojednán", "2": "přerušen", "3": "vyřazen / neprojednatelný",
              "4": "právě se projednává", "5": "odročen", "6": "již projednán", "7": "vyřazen"}

TEMATA = {  # téma → regulární výraz (hledá se v textu tisků a stenozáznamů)
    "eTurista a evidence hostů": r"e-?turist|evidenc\w* (ubytovan|turist|host)|jednotn\w* registra",
    "registrace krátkodobého ubytování": r"registra\w*.{0,40}(ubytov|pronáj)|registračn\w* čísl\w*.{0,40}ubytov|2024/1028",
    "omezení počtu nocí a regulace obcemi": r"(počt|limit)\w* (nocí|dnů|dní).{0,60}(ubytov|pronáj)"
                                            r"|vyhlášk\w*.{0,80}krátkodob|regulac\w* krátkodob",
    "kolaudace a změna užívání bytů": r"kolaud\w*.{0,80}(byt|ubytov)|změn\w* (v )?užívání.{0,80}(byt|ubytov)",
    "pravomoci Prahy": r"hlavní\w* měst\w* praz\w*.{0,150}(ubytov|pronáj)|(krátkodob|ubytov)\w*.{0,150}hlavní\w* měst\w* praz",
    "krátkodobé ubytování obecně": r"krátkodob\w* (ubytov|pronáj|nájem|nájm)|airbnb|sdílen\w* (ubytov|ekonom)"
                                   r"|ubytovac\w* služ|online platform\w*.{0,60}ubytov",
    "poplatek z pobytu": r"poplat\w* z pobytu",
    "SVJ a krátkodobé pronájmy": r"společenstv\w* vlastník\w*.{0,200}(krátkodob|ubytov)",
}


# ---------------------------------------------------------------- stahování a data psp.cz

def _stahni(url, timeout=120):
    odpoved = requests.get(url, timeout=timeout, headers={"User-Agent": "Vasil-agent (hlidani legislativy, kratkodobe ubytovani)"})
    odpoved.raise_for_status()
    return odpoved.content


def _unl(archiv, soubor):
    with archiv.open(soubor) as f:
        for radek in io.TextIOWrapper(f, encoding="cp1250", errors="replace"):
            if radek.strip():
                yield radek.rstrip("\r\n").split("|")


def _archiv(nazev):
    return zipfile.ZipFile(io.BytesIO(_stahni(f"{PSP}/eknih/cdrom/opendata/{nazev}.zip")))


def _datum(text):
    """„10.02.2026“ / „2026-02-10 09“ → datetime (nebo None)."""
    text = str(text or "").strip()
    for vzor, delka in (("%Y-%m-%d %H:%M", 16), ("%Y-%m-%d %H", 13), ("%Y-%m-%d", 10), ("%d.%m.%Y", 10)):
        try:
            return datetime.strptime(text[:delka], vzor)
        except ValueError:
            continue
    return None


def nacti():
    """Stáhne otevřená data a vrátí, co hlídání potřebuje – jen pro aktuální volební období."""
    poslanci, tisky, schuze, steno = (_archiv(n) for n in ("poslanci", "tisky", "schuze", "steno"))
    obdobi = max((r for r in _unl(poslanci, "organy.unl") if re.fullmatch(r"PSP\d+", r[3]) and not r[7].strip()),
                 key=lambda r: _datum(r[6]) or datetime.min)
    org, cislo, rok = obdobi[0], int(obdobi[3][3:]), (_datum(obdobi[6]) or hodiny.ted()).year
    typ_stavu = {r[0]: r[1] for r in _unl(tisky, "typ_stavu.unl")}
    stavy = {r[0]: r for r in _unl(tisky, "stavy.unl")}
    akce = {r[0]: r[1] for r in _unl(tisky, "typ_akce.unl")}
    prechody = {r[0]: r for r in _unl(tisky, "prechody.unl")}
    vysledek = {"obdobi": {"org": org, "cislo": cislo, "rok": rok}, "tisky": {}, "schuze": {}, "steno": []}
    for r in _unl(tisky, "tisky.unl"):
        if r[7] == org and r[1] in NAVRHY_ZAKONU and r[4] in ("0", ""):
            stav = stavy.get(r[2]) or ["", ""]
            vysledek["tisky"][r[0]] = {"ct": r[3], "zkratka": r[10], "nazev": r[15] or r[10], "predlozeno": r[11],
                                       "stav": typ_stavu.get(stav[1], ""), "skonceno": stav[1] == STAV_PROJEDNANO,
                                       "hist": [], "program": []}
    for r in _unl(tisky, "hist.unl"):
        tisk = vysledek["tisky"].get(r[1])
        if tisk:
            prechod = prechody.get(r[4]) or ["", "", "", ""]
            tisk["hist"].append({"id": int(r[0]), "datum": r[2], "akce": akce.get(prechod[3], ""),
                                 "stav": typ_stavu.get((stavy.get(prechod[2]) or ["", ""])[1], ""), "schuze": r[6]})
    for r in _unl(schuze, "schuze.unl"):
        if r[1] == org:
            vysledek["schuze"][r[0]] = {"cislo": r[2], "od": r[3], "do": r[4]}
    for r in _unl(schuze, "bod_schuze.unl"):
        tisk, s = vysledek["tisky"].get(r[2]), vysledek["schuze"].get(r[1])
        if tisk and s and not r[9].strip():  # schválený pořad (ne pozvánka)
            tisk["program"].append({"schuze": s["cislo"], "od": s["od"], "bod": r[4], "stav": STAVY_BODU.get(r[8], "")})
    for r in _unl(steno, "steno.unl"):
        if r[1] == org:
            vysledek["steno"].append({"id": r[0], "schuze": int(r[2]), "turn": int(r[3]), "datum": r[4]})
    for tisk in vysledek["tisky"].values():
        tisk["hist"].sort(key=lambda h: h["id"])
    return vysledek


def _odkaz_tisku(obdobi, ct):
    return f"{PSP}/sqw/historie.sqw?o={obdobi['cislo']}&t={ct}"


def _odkaz_steno(obdobi, schuze, turn):
    return f"{PSP}/eknih/{obdobi['rok']}ps/stenprot/{schuze:03d}schuz/s{schuze:03d}{turn:03d}.htm"


def _text_pdf(obsah):
    from pypdf import PdfReader
    ctecka = PdfReader(io.BytesIO(obsah))
    return "\n".join((strana.extract_text() or "") for strana in ctecka.pages[:MAX_STRAN_PDF])


def _text_tisku(obdobi, ct):
    """Plný text sněmovního tisku: první dokument na stránce tisku („Celý sněmovní tisk“, PDF)."""
    stranka = _stahni(f"{PSP}/sqw/text/tiskt.sqw?o={obdobi['cislo']}&ct={ct}&ct1=0", timeout=60).decode("cp1250", "replace")
    dokument = re.search(r"orig2\.sqw\?idd=(\d+)", stranka)
    if not dokument:
        return ""
    return _text_pdf(_stahni(f"{PSP}/sqw/text/orig2.sqw?idd={dokument.group(1)}"))


def _text_html(obsah):
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", obsah.decode("cp1250", "replace"))
    return html.unescape(re.sub(r"<[^>]+>", " ", text))


def vynatky(text):
    """(témata, výňatky kolem nalezených slov) – prázdné, když se tam témata neobjeví."""
    text = re.sub(r"\s+", " ", text or "")
    temata, useky = [], []
    for tema, vzor in TEMATA.items():
        for m in re.finditer(vzor, text, re.I):
            if tema not in temata:
                temata.append(tema)
            useky.append((max(0, m.start() - OKOLI), min(len(text), m.end() + OKOLI)))
    sloucene = []
    for od, do in sorted(useky):
        if sloucene and od <= sloucene[-1][1]:
            sloucene[-1][1] = max(sloucene[-1][1], do)
        else:
            sloucene.append([od, do])
    return temata, "\n…\n".join(text[od:do] for od, do in sloucene)[:MAX_VYNATKU]


# ---------------------------------------------------------------- zprávy do skupiny

def _posli(db, text):
    oznameni.posli(text)
    db.conn.execute("INSERT INTO leg_zpravy (cas, text) VALUES (?, ?)", (hodiny.ted_iso(), text))
    db.conn.commit()


def _den(text):
    d = _datum(text)
    return f"{d.day}. {d.month}. {d.year}" if d else str(text or "?")


def _hlavicka(t):
    return f"Tisk {t['ct']} – {t['nazev']}"


# ---------------------------------------------------------------- porovnání dat (v LEGISLATIVA_HODINY)

def porovnej(db, data):
    """Nové tisky do fronty k posouzení, u relevantních nahlásí nové kroky projednávání a zařazení na program schůze;
    nové stenozáznamy do fronty."""
    obdobi = data["obdobi"]
    db.uloz_nastaveni("leg_obdobi", json.dumps(obdobi))
    prvni = db.nastaveni("leg_uvod") != "hotovo" and not db.conn.execute("SELECT 1 FROM leg_tisky LIMIT 1").fetchone()
    hranice = hodiny.ted() - timedelta(days=POCATECNI_DNI)
    for id_tisk, t in data["tisky"].items():
        hist_max = t["hist"][-1]["id"] if t["hist"] else 0
        program = json.dumps([[p["schuze"], p["od"], p["bod"], p["stav"]] for p in t["program"]])
        radek = db.conn.execute("SELECT posouzeni, posledni_hist, schuze FROM leg_tisky WHERE id_tisk = ?",
                                (id_tisk,)).fetchone()
        if not radek:
            posledni = _datum(t["hist"][-1]["datum"]) if t["hist"] else _datum(t["predlozeno"])
            if prvni and t["skonceno"] and (not posledni or posledni < hranice):
                continue  # dávno ukončené tisky z doby před spuštěním hlídání
            db.conn.execute(
                "INSERT INTO leg_tisky (id_tisk, ct, nazev, stav, posouzeni, posledni_hist, hist_max, schuze, program, cas) "
                "VALUES (?, ?, ?, ?, 'ceka', ?, ?, ?, ?, ?)",
                (id_tisk, t["ct"], t["zkratka"] or t["nazev"], t["stav"], hist_max, hist_max,
                 json.dumps(sorted({p["schuze"] for p in t["program"]})), program, hodiny.ted_iso()))
            continue
        posouzeni, posledni_hist, nahlasene = radek
        db.conn.execute("UPDATE leg_tisky SET stav = ?, hist_max = ?, program = ? WHERE id_tisk = ?",
                        (t["stav"], hist_max, program, id_tisk))
        if posouzeni != "relevantni":
            continue
        nove = [h for h in t["hist"] if h["id"] > (posledni_hist or 0)]
        if nove:
            kroky = "\n".join(f"• {_den(h['datum'])}: {h['akce']}" + (f" → {h['stav']}" if h["stav"] else "")
                              + (f" ({h['schuze']}. schůze)" if h["schuze"] else "") for h in nove)
            _posli(db, f"🏛️ SNĚMOVNA – pohnulo se to\n{_hlavicka(t)}\nNové kroky projednávání:\n{kroky}\nStav: {t['stav']}\n{_odkaz_tisku(obdobi, t['ct'])}")
        nahlasene = set(json.loads(nahlasene or "[]"))
        dnes = hodiny.ted().replace(hour=0, minute=0)
        for p in t["program"]:
            od = _datum(p["od"])
            if p["schuze"] not in nahlasene and od and od >= dnes - timedelta(days=1):
                _posli(db, f"📅 SNĚMOVNA – na programu\n{_hlavicka(t)}\nJe na programu {p['schuze']}. schůze Sněmovny (od {_den(p['od'])}), "
                           f"bod {p['bod']}.\n{_odkaz_tisku(obdobi, t['ct'])}")
                nahlasene.add(p["schuze"])
        db.conn.execute("UPDATE leg_tisky SET posledni_hist = ?, schuze = ? WHERE id_tisk = ?",
                        (hist_max, json.dumps(sorted(nahlasene)), id_tisk))
    for s in data["steno"]:
        if db.conn.execute("SELECT 1 FROM leg_steno WHERE id_steno = ?", (s["id"],)).fetchone():
            continue
        db.conn.execute("INSERT INTO leg_steno (id_steno, url, schuze, datum, stav) VALUES (?, ?, ?, ?, ?)",
                        (s["id"], _odkaz_steno(obdobi, s["schuze"], s["turn"]), str(s["schuze"]), s["datum"],
                         "stare" if prvni else "ceka"))
    db.conn.commit()


# ---------------------------------------------------------------- fronta (po dávkách v každém cyklu)

def _posud(db, obdobi, id_tisk, ct, nazev, stav, uvod_hotov):
    temata, text = vynatky(_text_tisku(obdobi, ct))
    if not temata:
        db.conn.execute("UPDATE leg_tisky SET posouzeni = 'nerelevantni' WHERE id_tisk = ?", (id_tisk,))
        return
    v = mozek.posud_tisk(f"SNĚMOVNÍ TISK {ct}: {nazev}\nSTAV PROJEDNÁVÁNÍ: {stav}\nNALEZENÁ TÉMATA: {', '.join(temata)}"
                         f"\n\nVÝŇATKY Z TEXTU:\n{text}")
    db.conn.execute("UPDATE leg_tisky SET posouzeni = ?, temata = ?, shrnuti = ?, dopad = ? WHERE id_tisk = ?",
                    ("relevantni" if v["relevantni"] else "nerelevantni", json.dumps(v["temata"], ensure_ascii=False),
                     v["shrnuti"], v["dopad"], id_tisk))
    if v["relevantni"] and uvod_hotov:
        _posli(db, f"🆕 SNĚMOVNA – nový návrh zákona, který se vás týká\n{_hlavicka({'ct': ct, 'nazev': nazev})}\n"
                   f"Témata: {', '.join(v['temata'])}\n{v['shrnuti']}\nCo to pro vás znamená: {v['dopad']}\n"
                   f"Stav: {stav}\n{_odkaz_tisku(obdobi, ct)}")


def zpracuj_frontu(db):
    obdobi = json.loads(db.nastaveni("leg_obdobi") or "null")
    if not obdobi:
        return
    uvod_hotov = db.nastaveni("leg_uvod") == "hotovo"
    zbyva = MAX_STAZENI_ZA_CYKLUS
    for id_tisk, ct, nazev, stav, pokusy in db.conn.execute(
            "SELECT id_tisk, ct, nazev, stav, pokusy FROM leg_tisky WHERE posouzeni = 'ceka' "
            "ORDER BY CAST(ct AS INTEGER) DESC LIMIT ?", (zbyva,)).fetchall():
        zbyva -= 1
        try:
            _posud(db, obdobi, id_tisk, ct, nazev, stav, uvod_hotov)
        except Exception as e:
            log.warning("Tisk %s se nepodařilo posoudit: %s", ct, e)
            db.conn.execute("UPDATE leg_tisky SET pokusy = pokusy + 1, posouzeni = CASE WHEN pokusy + 1 >= ? "
                            "THEN 'chyba' ELSE 'ceka' END WHERE id_tisk = ?", (MAX_POKUSU, id_tisk))
        db.conn.commit()
    for id_steno, url in db.conn.execute(
            "SELECT id_steno, url FROM leg_steno WHERE stav = 'ceka' ORDER BY CAST(id_steno AS INTEGER) LIMIT ?",
            (max(zbyva, 0),)).fetchall():
        try:
            temata, text = vynatky(_text_html(_stahni(url, timeout=60)))
            db.conn.execute("UPDATE leg_steno SET stav = ?, vynatek = ? WHERE id_steno = ?",
                            ("shoda" if temata else "bez", text if temata else None, id_steno))
        except Exception as e:
            log.warning("Stenozáznam %s se nepodařilo stáhnout: %s", url, e)
            db.conn.execute("UPDATE leg_steno SET pokusy = pokusy + 1, stav = CASE WHEN pokusy + 1 >= ? "
                            "THEN 'chyba' ELSE 'ceka' END WHERE id_steno = ?", (MAX_POKUSU, id_steno))
        db.conn.commit()
    _nahlas_rozpravy(db)
    if not uvod_hotov and not db.conn.execute("SELECT 1 FROM leg_tisky WHERE posouzeni = 'ceka' LIMIT 1").fetchone() \
            and db.conn.execute("SELECT 1 FROM leg_tisky LIMIT 1").fetchone():
        _posli(db, _uvodni_prehled(db, obdobi))
        db.uloz_nastaveni("leg_uvod", "hotovo")


def _nahlas_rozpravy(db):
    """Výňatky ze stenozáznamů jednoho dne → jedna zpráva, až jsou stažené všechny úseky toho dne."""
    for schuze, datum in db.conn.execute(
            "SELECT DISTINCT schuze, datum FROM leg_steno WHERE stav = 'shoda'").fetchall():
        if db.conn.execute("SELECT 1 FROM leg_steno WHERE schuze = ? AND datum = ? AND stav = 'ceka' LIMIT 1",
                           (schuze, datum)).fetchone():
            continue
        useky = db.conn.execute("SELECT id_steno, url, vynatek FROM leg_steno WHERE schuze = ? AND datum = ? "
                                "AND stav = 'shoda' ORDER BY CAST(id_steno AS INTEGER)", (schuze, datum)).fetchall()
        kontext = f"{schuze}. SCHŮZE SNĚMOVNY, {_den(datum)}\n\n" + "\n\n".join(
            f"[úsek {i}]\n{vynatek}" for i, (_, _, vynatek) in enumerate(useky, 1))
        v = mozek.shrn_rozpravu(kontext[:MAX_VYNATKU * 2])
        if v["relevantni"]:
            _posli(db, f"🗣️ SNĚMOVNA {_den(datum)} ({schuze}. schůze) – mluvilo se o vašich tématech\n{v['shrnuti']}\n"
                       f"Co to pro vás znamená: {v['dopad']}\nStenozáznam: {useky[0][1]}")
        db.conn.executemany("UPDATE leg_steno SET stav = 'nahlaseno' WHERE id_steno = ?", [(u[0],) for u in useky])
        db.conn.commit()


# ---------------------------------------------------------------- přehledy

def _relevantni(db):
    return db.conn.execute("SELECT ct, nazev, stav, temata, shrnuti, dopad, program FROM leg_tisky "
                           "WHERE posouzeni = 'relevantni' ORDER BY CAST(ct AS INTEGER)").fetchall()


def _popis_tisku(obdobi, radek, s_shrnutim=True):
    ct, nazev, stav, temata, shrnuti, dopad, program = radek
    text = f"• Tisk {ct} – {nazev}\n  Stav: {stav or '?'}"
    if s_shrnutim:
        text += f"\n  {shrnuti}\n  Co to pro vás znamená: {dopad}"
    posledni = (json.loads(program or "[]") or [None])[-1]
    if posledni:
        text += f"\n  Naposledy na programu: {posledni[0]}. schůze (od {_den(posledni[1])}), bod {posledni[2]} – {posledni[3]}"
    return text + f"\n  {_odkaz_tisku(obdobi, ct)}"


def _uvodni_prehled(db, obdobi):
    radky = _relevantni(db)
    if not radky:
        return ("📋 HLÍDÁNÍ SNĚMOVNY SPUŠTĚNO\nV aktuálních návrzích zákonů jsem nenašel nic, co by se týkalo krátkodobého "
                "ubytování. Ozvu se, jakmile se něco objeví.")
    return ("📋 HLÍDÁNÍ SNĚMOVNY SPUŠTĚNO – stav k dnešku\nNávrhy zákonů, které se týkají krátkodobého ubytování:\n\n"
            + "\n\n".join(_popis_tisku(obdobi, r) for r in radky)
            + "\n\nOd teď vám dám vědět hned, když se u nich něco pohne, a v pondělí ráno pošlu souhrn.")


def tydenni_souhrn(db):
    obdobi = json.loads(db.nastaveni("leg_obdobi") or "null") or {}
    ted = hodiny.ted()
    za_tyden = ted + timedelta(days=7)
    radky = _relevantni(db)
    text = f"📰 SNĚMOVNA – SOUHRN K {ted.day}. {ted.month}. {ted.year}"
    program = [(r[0], r[1], p) for r in radky for p in json.loads(r[6] or "[]")
               if _datum(p[1]) and ted - timedelta(days=1) <= _datum(p[1]) <= za_tyden]
    text += "\n\n📅 Tento týden na programu:\n" + ("\n".join(
        f"• Tisk {ct} – {nazev}: {p[0]}. schůze (od {_den(p[1])}), bod {p[2]}" for ct, nazev, p in program)
        if program else "• nic z vašich témat")
    minule = db.conn.execute("SELECT text FROM leg_zpravy WHERE cas >= ? ORDER BY id",
                             ((ted - timedelta(days=7)).isoformat(timespec="seconds"),)).fetchall()
    minule = [t.split("\n")[0] for (t,) in minule if not t.startswith(("📰", "📋"))]
    text += "\n\n🗓️ Minulý týden:\n" + ("\n".join(f"• {m}" for m in minule) if minule else "• žádná změna")
    text += "\n\n📌 Stav témat:\n" + ("\n".join(_popis_tisku(obdobi, r, s_shrnutim=False) for r in radky)
                                      if radky else "• žádný návrh zákona se vašich témat zatím netýká")
    return text


# ---------------------------------------------------------------- vstup z hlavní smyčky

def zkontroluj(db):
    """Každý cyklus: v LEGISLATIVA_HODINY stáhne a porovná data psp.cz, po dávkách zpracuje frontu, v pondělí souhrn."""
    ted = hodiny.ted()
    hodina = max((h for h in config.LEGISLATIVA_HODINY if h <= ted.hour), default=None)
    if hodina is not None and db.nastaveni("leg_kontrola") != f"{ted.date()} {hodina}":
        porovnej(db, nacti())  # při výpadku psp.cz výjimka → zkusí se znovu v dalším cyklu
        db.uloz_nastaveni("leg_kontrola", f"{ted.date()} {hodina}")
    zpracuj_frontu(db)
    if (ted.weekday() == 0 and ted.hour >= config.LEGISLATIVA_SOUHRN_HODINA and db.nastaveni("leg_uvod") == "hotovo"
            and db.nastaveni("leg_souhrn_den") != ted.date().isoformat()):
        _posli(db, tydenni_souhrn(db))
        db.uloz_nastaveni("leg_souhrn_den", ted.date().isoformat())
