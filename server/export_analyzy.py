"""Export pro analýzu „co Vasil neví a na co potřebuje hostitele“. Jen čte – nic nemění a nic neposílá.

Spouští se z Macu, výsledek (JSON) se uloží na plochu:

  curl -fsSL https://raw.githubusercontent.com/simonpavek-dev/BNBagent/p3-4-analyza/server/export_analyzy.py \
    | ssh root@IP_SERVERU "cd /opt/airbnb-agent && .venv/bin/python -B -" > ~/Desktop/vasil-export.json

V exportu: eskalace a návrhy, které hostitel upravil (✏️) nebo zahodil, i s tím, co hostitel hostovi nakonec napsal
ve Smoobu; změny znalostní báze přes Telegram; naše zprávy po odjezdu (jestli chodí automatické zprávy Smoobu č. 5
a 6); znalostní báze bez kódů a hesla k Wi-Fi.
Bez: jmen hostů, telefonů, e-mailů, kódů, hesel a čísel rezervací – místo nich [HOST], [TELEFON], [E-MAIL], [KÓD],
[ČÍSLO] a R1, R2…. Databázi otevírá jen pro čtení, ze Smoobu jen čte (GET).
"""
import sys

sys.dont_write_bytecode = True  # běží jako root – nenechat po sobě soubory .pyc

import copy  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import sqlite3  # noqa: E402
from collections import Counter  # noqa: E402
from datetime import date, datetime, timedelta  # noqa: E402
from pathlib import Path  # noqa: E402

import yaml  # noqa: E402

MAX_TEXT = 700
MAX_REZERVACI_SMOOBU = 60   # u kolika rezervací nejvýš dohledat konverzaci ve Smoobu
DNI_ODJEZDU = 21            # zprávy po odjezdu: rezervace, které skončily za posledních N dní
MAX_ODJEZDU = 15
TAJNE = (("prijezd", "keybox_kod"), ("prijezd", "kod_vchod"), ("prijezd", "keybox_kod_overeno"),
         ("prijezd", "keybox_kod_plati_pro_rezervaci"), ("wifi", "heslo"))
TECHNICKE = {"smoobu_id", "uklidy_nazev", "prijezd.kody_sdelit_nejdrive_dni_pred_prijezdem"}
CASTICE = {"van", "von", "der", "den", "del", "della", "dos", "das", "les", "the", "and"}


def _bez_html(text):
    return re.sub(r"<[^>]+>", " ", str(text or ""))


def _normalizuj(text):
    return re.sub(r"\s+", " ", _bez_html(text)).strip().lower()


class Anonymizace:
    """Nahrazuje jména hostů, kontakty, kódy a čísla rezervací značkami."""

    def __init__(self, tajne):
        self.tajne = sorted({str(t).strip() for t in tajne if t is not None and len(str(t).strip()) >= 3},
                            key=len, reverse=True)
        self.jmena = {}        # rezervace → části jména hosta
        self.pseudonymy = {}   # rezervace → R1, R2…

    def rez(self, rid):
        rid = str(rid or "")
        if not rid:
            return ""
        return self.pseudonymy.setdefault(rid, f"R{len(self.pseudonymy) + 1}")

    def pridej_jmeno(self, rid, jmeno):
        for cast in re.split(r"[\s,.\-/]+", str(jmeno or "")):
            if len(cast) >= 3 and cast.lower() not in CASTICE:
                self.jmena.setdefault(str(rid), set()).add(cast)

    def text(self, text, rid=None, delka=MAX_TEXT, jmena=True, cisla=True):
        """rid=None → jména hostů všech rezervací."""
        t = _bez_html(text)
        for tajne in self.tajne:
            t = t.replace(tajne, "[KÓD]")
        t = re.sub(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", "[E-MAIL]", t)
        t = re.sub(r"\+?\d[\d ()/-]{7,}\d",
                   lambda m: "[TELEFON]" if len(re.sub(r"\D", "", m.group())) >= 9 else m.group(), t)
        if jmena:
            casti = self.jmena.get(str(rid), set()) if rid is not None else set().union(*self.jmena.values())
            for cast in sorted(casti, key=len, reverse=True):
                t = re.sub(rf"(?<!\w){re.escape(cast)}(?!\w)", "[HOST]", t, flags=re.I)
        if cisla:  # kódy keyboxu z dřívějška, čísla rezervací; roky nechat
            t = re.sub(r"(?<!\d)\d{4,8}(?!\d)",
                       lambda m: m.group() if re.fullmatch(r"20[2-3]\d", m.group()) else "[ČÍSLO]", t)
        t = t.strip()
        return t[:delka] + "…" if delka and len(t) > delka else t

    def data(self, data):
        """Znalostní báze: jen kódy a telefony (jména hostů tam nejsou, ceny a časy zůstanou)."""
        if isinstance(data, dict):
            return {k: self.data(v) for k, v in data.items()}
        if isinstance(data, list):
            return [self.data(v) for v in data]
        if isinstance(data, str):
            return self.text(data, delka=None, jmena=False, cisla=False)
        return data


# ---------------------------------------------------------------- znalostní báze

def _koncove(data, cesta=()):
    for klic, hodnota in (data or {}).items():
        if isinstance(hodnota, dict):
            yield from _koncove(hodnota, cesta + (str(klic),))
        else:
            yield cesta + (str(klic),)


def _hodnota(data, cesta):
    for klic in cesta:
        if not isinstance(data, dict):
            return None
        data = data.get(klic)
    return data


def _prazdne(hodnota):
    if hodnota is None:
        return True
    if isinstance(hodnota, str):
        return not hodnota.strip()
    if isinstance(hodnota, list):
        return all(_prazdne(v) for v in hodnota)
    if isinstance(hodnota, dict):
        return all(_prazdne(v) for v in hodnota.values())
    return False


def _nacti_znalosti(slozka, chyby):
    byty, obecne, tajne = [], {}, []
    try:
        sablona = yaml.safe_load((slozka / "apartmany" / "_sablona.yaml").read_text("utf-8")) or {}
    except Exception as e:
        chyby.append(f"šablona bytu: {e}")
        sablona = {}
    for soubor in sorted((slozka / "apartmany").glob("*.yaml")):
        if soubor.name.startswith("_"):
            continue
        try:
            data = yaml.safe_load(soubor.read_text("utf-8")) or {}
        except Exception as e:
            chyby.append(f"{soubor.name}: {e}")
            continue
        tajne += [_hodnota(data, cesta) for cesta in TAJNE]
        cesty = [c for c in _koncove(sablona) if c not in TAJNE and ".".join(c) not in TECHNICKE]
        bez_tajnych = copy.deepcopy(data)
        for sekce, klic in TAJNE:
            if isinstance(bez_tajnych.get(sekce), dict):
                bez_tajnych[sekce].pop(klic, None)
        byty.append({
            "soubor": soubor.name,
            "nazev": data.get("nazev"),
            "prazdna_pole": [".".join(c) for c in cesty if _prazdne(_hodnota(data, c))],
            "navic": [k for k in data if k not in sablona],
            "pocet_castych_dotazu": sum(1 for d in data.get("caste_dotazy") or []
                                        if isinstance(d, dict) and not _prazdne(d.get("otazka"))),
            "obsah": bez_tajnych,
        })
    try:
        obecne = yaml.safe_load((slozka / "obecne.yaml").read_text("utf-8")) or {}
    except Exception as e:
        chyby.append(f"obecne.yaml: {e}")
    return byty, obecne, tajne


# ---------------------------------------------------------------- databáze agenta

def _detail(text):
    try:
        hodnota = json.loads(text or "")
    except (TypeError, ValueError):
        return text
    return hodnota


def _nacti_databazi(cesta):
    conn = sqlite3.connect(Path(cesta).resolve().as_uri() + "?mode=ro", uri=True)  # jen pro čtení
    conn.row_factory = sqlite3.Row
    try:
        def radky(sql):
            try:
                return [dict(r) for r in conn.execute(sql)]
            except sqlite3.OperationalError:  # starší databáze bez tabulky
                return []
        return {
            "udalosti": radky("SELECT id, cas, reservation_id, akce, detail FROM udalosti ORDER BY id"),
            "navrhy": radky("SELECT id, reservation_id, message_id, text, hlavicka, stav, cas FROM navrhy ORDER BY id"),
            "odchozi": radky("SELECT reservation_id, text FROM odchozi"),
            "zpravy": {r["stav"]: r["pocet"] for r in radky("SELECT stav, COUNT(*) AS pocet FROM zpravy GROUP BY stav")},
        }
    finally:
        conn.close()


def _casti_hlavicky(hlavicka):
    """„Byt · Jméno · Kanál · příjezd → odjezd (rez. id)“ → (byt, jméno, kanál)."""
    casti = [c.strip() for c in str(hlavicka or "").split(" · ")]
    return (casti[0] if casti else "?"), (casti[1] if len(casti) > 1 else ""), (casti[2] if len(casti) > 2 else "")


def _kody_z_udalosti(udalosti):
    kody = []
    for u in udalosti:
        if u["akce"] in ("kod_z_aplikace", "instrukce_prijezd"):
            d = _detail(u["detail"])
            if isinstance(d, dict):
                kody += [d.get("kod"), d.get("predtim"), d.get("oprava_z")]
    return kody


def _prirad_navrhy(rozhodnuti, navrhy):
    """Ke každému rozhodnutí návrh, který z něj vznikl (stejný text, jinak nejbližší následující)."""
    podle_rez = {}
    for n in navrhy:
        if n["message_id"]:
            podle_rez.setdefault(str(n["reservation_id"]), []).append(n)
    pouzite = set()
    for i, r in enumerate(rozhodnuti):
        dalsi = next((x["cas"] for x in rozhodnuti[i + 1:] if x["rid"] == r["rid"]), "9999")
        kandidati = [n for n in podle_rez.get(r["rid"], []) if n["id"] not in pouzite and r["cas"] <= n["cas"] <= dalsi]
        navrh = next((n for n in kandidati if n["text"] == r.get("odpoved_hostovi")), None) or \
            next((n for n in kandidati if n["cas"] < dalsi), None)
        if navrh:
            pouzite.add(navrh["id"])
        r["navrh"] = navrh


def _nahrada(navrh, navrhy):
    """Hostitelův text (✏️) = další návrh téže rezervace bez zprávy hosta, vzniklý hned po nahrazení."""
    return next((n for n in navrhy if n["id"] > navrh["id"] and str(n["reservation_id"]) == str(navrh["reservation_id"])
                 and not n["message_id"] and n["hlavicka"] == navrh["hlavicka"]), None)


# ---------------------------------------------------------------- Smoobu

class Konverzace:
    def __init__(self, smoobu, chyby, anon):
        self.smoobu, self.chyby, self.anon = smoobu, chyby, anon
        self.cache = {}

    def __call__(self, rid):
        rid = str(rid)
        if self.smoobu is None:
            return None
        if rid not in self.cache:
            try:
                self.cache[rid] = self.smoobu.messages(rid)
            except Exception as e:
                self.chyby.append(f"Smoobu {self.anon.rez(rid)}: {e}")
                self.cache[rid] = None
        return self.cache[rid]


def _cas(text):
    try:
        return datetime.fromisoformat(str(text or "")[:19].replace("T", " "))
    except ValueError:
        return None


def _od_vasila(text, nase):
    zacatek = _normalizuj(text)[:60]
    return bool(zacatek) and any(n.startswith(zacatek) or zacatek.startswith(n[:60]) for n in nase if n)


def _nase_dalsi_zpravy(zpravy, zprava_hosta, nase, anon, rid):
    """Naše zprávy ve Smoobu po zprávě hosta (do jeho další zprávy) – od Vasila, nebo ruční / automatické."""
    cil = _normalizuj(zprava_hosta)
    index = None
    for i, m in enumerate(zpravy):
        text = _normalizuj(m.get("message"))
        if m.get("type") == 1 and text and text[:80] in cil:
            index = i
    if index is None:
        return None
    out = []
    od = _cas(zpravy[index].get("createdAt"))
    for m in zpravy[index + 1:]:
        if m.get("type") == 1 or len(out) >= 3:
            break
        if od and _cas(m.get("createdAt")) and _cas(m.get("createdAt")) - od > timedelta(days=1):
            break  # o den později už to není odpověď na tuhle zprávu (spíš automatická zpráva)
        if m.get("type") == 2:
            out.append({"kdy": str(m.get("createdAt") or "")[:16], "od_vasila": _od_vasila(m.get("message"), nase),
                        "text": anon.text(m.get("message"), rid)})
    return out


def _zpravy_po_odjezdu(smoobu, konverzace, dnes, anon, nase, chyby):
    if smoobu is None:
        return []
    try:
        rezervace = smoobu.reservations(dnes - timedelta(days=DNI_ODJEZDU + 45), dnes)
    except Exception as e:
        chyby.append(f"Smoobu rezervace: {e}")
        return []
    vybrane = []
    for r in rezervace:
        try:
            odjezd = date.fromisoformat(str(r.get("departure"))[:10])
        except ValueError:
            continue
        if not r.get("is-blocked-booking") and dnes - timedelta(days=DNI_ODJEZDU) <= odjezd < dnes:
            vybrane.append((odjezd, r))
    out = []
    for odjezd, r in sorted(vybrane, key=lambda x: x[0], reverse=True)[:MAX_ODJEZDU]:
        rid = str(r.get("id"))
        for klic in ("guest-name", "firstname", "lastname"):
            anon.pridej_jmeno(rid, r.get(klic))
        for m in konverzace(rid) or []:
            if m.get("type") != 2:
                continue
            try:
                den = date.fromisoformat(str(m.get("createdAt"))[:10])
            except ValueError:
                continue
            if den >= odjezd - timedelta(days=1):
                out.append({"rezervace": anon.rez(rid), "byt": (r.get("apartment") or {}).get("name"),
                            "kanal": (r.get("channel") or {}).get("name"), "den": (den - odjezd).days,
                            "cas": str(m.get("createdAt"))[11:16],
                            "od_vasila": _od_vasila(m.get("message"), nase.get(rid, [])),
                            "text": anon.text(m.get("message"), rid, delka=300)})
    return out


# ---------------------------------------------------------------- export

def export(koren, smoobu=None, dnes=None):
    koren = Path(koren)
    dnes = dnes or date.today()
    chyby = []
    byty, obecne, tajne_baze = _nacti_znalosti(koren / "znalostni-baze", chyby)
    db = _nacti_databazi(koren / "data" / "agent.db")
    anon = Anonymizace(tajne_baze + _kody_z_udalosti(db["udalosti"]))

    for n in db["navrhy"]:
        anon.pridej_jmeno(n["reservation_id"], _casti_hlavicky(n["hlavicka"])[1])
    rozhodnuti = []
    for u in db["udalosti"]:
        d = _detail(u["detail"])
        if u["akce"] == "rozhodnuti" and isinstance(d, dict):
            rozhodnuti.append(dict(d, cas=u["cas"] or "", rid=str(u["reservation_id"])))
            anon.pridej_jmeno(u["reservation_id"], _casti_hlavicky(d.get("hlavicka"))[1])
    _prirad_navrhy(rozhodnuti, db["navrhy"])

    nase = {}  # rezervace → naše texty (návrhy, odeslané zprávy) pro poznání Vasilových zpráv ve Smoobu
    for r in rozhodnuti:
        nase.setdefault(r["rid"], []).append(_normalizuj(r.get("odpoved_hostovi")))
    for n in db["navrhy"] + db["odchozi"]:
        nase.setdefault(str(n["reservation_id"]), []).append(_normalizuj(n["text"]))

    pripady, zdroje, podle_bytu = [], [], {}
    for r in rozhodnuti:
        byt, _, kanal = _casti_hlavicky(r.get("hlavicka"))
        navrh = r["navrh"]
        stav = navrh["stav"] if navrh else None
        if r.get("rozhodnuti") == "eskalovat":
            typ = "eskalace"
        elif stav in ("nahrazeno", "zahozeno"):
            typ = {"nahrazeno": "upraveno", "zahozeno": "zahozeno"}[stav]
        elif r.get("kontrola"):
            typ = "kontrola"
        else:
            typ = None
        pocty = podle_bytu.setdefault(byt, Counter())
        pocty["rozhodnuti"] += 1
        if typ:
            pocty[typ] += 1
        if not typ:
            continue
        rid = r["rid"]
        pripad = {
            "typ": typ, "kdy": r["cas"][:16].replace("T", " "), "rezervace": anon.rez(rid), "byt": byt,
            "kanal": kanal, "jazyk": r.get("jazyk_hosta"), "zprava_hosta": anon.text(r.get("zprava_hosta"), rid),
            "rozhodnuti": r.get("rozhodnuti"), "duvod": anon.text(r.get("duvod"), rid),
            "dotaz_pro_hostitele": anon.text(r.get("navrh_pro_hostitele"), rid),
            "kontrola": anon.text(r.get("kontrola"), rid), "navrh_vasila": anon.text(r.get("odpoved_hostovi"), rid),
            "vysledek_navrhu": stav,
        }
        if stav == "nahrazeno":
            nahrada = _nahrada(navrh, db["navrhy"])
            pripad["odeslano_misto_navrhu"] = anon.text(nahrada["text"], rid) if nahrada else None
            pripad["vysledek_upravy"] = nahrada["stav"] if nahrada else None
        pripady.append(pripad)
        zdroje.append((pripad, r))

    # co jsme hostovi nakonec napsali (Smoobu) – jen u nejnovějších rezervací, ať export netrvá dlouho
    konverzace = Konverzace(smoobu, chyby, anon)
    nejnovejsi = []
    for _, r in sorted(zdroje, key=lambda x: x[1]["cas"], reverse=True):
        if r["rid"] not in nejnovejsi:
            nejnovejsi.append(r["rid"])
    for pripad, r in zdroje:
        if r["rid"] in nejnovejsi[:MAX_REZERVACI_SMOOBU]:
            zpravy = konverzace(r["rid"])
            if zpravy is not None:
                pripad["nase_dalsi_zpravy"] = _nase_dalsi_zpravy(zpravy, r.get("zprava_hosta"),
                                                                 nase.get(r["rid"], []), anon, r["rid"])

    zmeny = []
    for u in db["udalosti"]:
        d = _detail(u["detail"])
        if u["akce"] == "zmena_znalosti" and isinstance(d, dict):
            zmeny.append({"kdy": (u["cas"] or "")[:16].replace("T", " "), "soubor": d.get("soubor"),
                          "zmena": anon.text(d.get("zmena"), None, delka=500)})

    odjezdy = _zpravy_po_odjezdu(smoobu, konverzace, dnes, anon, nase, chyby)

    navrhy_hostum = Counter(n["stav"] for n in db["navrhy"] if n["message_id"])
    casy = [u["cas"] for u in db["udalosti"] if u["cas"]]
    return {
        "verze": 1,
        "vytvoreno": datetime.now().isoformat(timespec="minutes"),
        "souhrn": {
            "obdobi": [min(casy)[:10], max(casy)[:10]] if casy else None,
            "zpravy_hostu_podle_stavu": db["zpravy"],
            "rozhodnuti": dict(Counter(r.get("rozhodnuti") for r in rozhodnuti)),
            "navrhy_odpovedi_podle_stavu": dict(navrhy_hostum),
            "podle_bytu": {byt: dict(p) for byt, p in podle_bytu.items()},
        },
        "pripady": pripady,
        "zmeny_znalosti": zmeny,
        "odjezdy_smoobu": odjezdy,
        "znalostni_baze": {
            "byty": [dict(b, obsah=anon.data(b["obsah"])) for b in byty],
            "obecne": anon.data(obecne),
        },
        "chyby": [anon.text(c) for c in chyby],
    }


if __name__ == "__main__":
    koren = Path.cwd()
    if not (koren / "agent").is_dir() or not (koren / "data" / "agent.db").is_file():
        sys.exit("Spusť v adresáři agenta na serveru (cd /opt/airbnb-agent).")
    sys.path.insert(0, str(koren))
    smoobu = None
    try:
        from agent import config
        from agent.smoobu import Smoobu
        smoobu = Smoobu(config.SMOOBU_API_KEY, config.SMOOBU_API_SECRET)  # bez upozorňování – jen čte
    except Exception as e:
        print(f"Smoobu nedostupné, export bude bez konverzací: {e}", file=sys.stderr)
    vysledek = export(koren, smoobu)
    sys.stdout.reconfigure(encoding="utf-8")
    json.dump(vysledek, sys.stdout, ensure_ascii=False, indent=1)
    print(f"Hotovo: {len(vysledek['pripady'])} případů, {len(vysledek['znalostni_baze']['byty'])} bytů, "
          f"chyb {len(vysledek['chyby'])}.", file=sys.stderr)
