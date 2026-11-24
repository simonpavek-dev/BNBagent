"""Doporučení podniků z Google Maps (P3.3, přepínač DOPORUCENI_PODNIKU + klíč GOOGLE_MAPS_API_KEY).

Nástroj doporuc_podniky pro model: Google Places API (New), Text Search kolem adresy apartmánu. Kód vybere až 3 podniky:
- hodnocení aspoň DOPORUCENI_MIN_HODNOCENI z aspoň DOPORUCENI_MIN_RECENZI recenzí, podnik v provozu,
- otevřeno v den a čas, na který se host ptá (do 7 dní aktuální otevírací doba Googlu se svátky a výjimkami, dál běžná),
- nejvýš DOPORUCENI_MAX_PESKY_MIN minut pěšky (trasa z OpenStreetMap jako u nástroje trasa),
- pořadí podle hodnocení váženého počtem recenzí (4,9 z 30 recenzí nepředběhne 4,7 z 2 000).
Seznam (název, ⭐ hodnocení (počet), 🚶 minuty, 🕒 otevřeno, odkaz na Google Maps) vloží do odpovědi kód místo značky
[TIPY Z MAP n] – model hodnocení, otevírací doby ani odkazy nepíše. Volá `mozek` (nástroj při odpovědi hostovi).
"""
import logging
import math
from datetime import datetime

import requests

from . import config, hodiny, mapy

log = logging.getLogger("agent")
URL = "https://places.googleapis.com/v1/places:searchText"
POLE = ",".join("places." + p for p in (  # rating, počet recenzí a otevírací doba = SKU Text Search Enterprise
    "id", "displayName", "location", "rating", "userRatingCount", "regularOpeningHours", "currentOpeningHours",
    "googleMapsUri", "businessStatus"))
METRU_ZA_MINUTU = 80   # předběžný výběr podle vzdušné vzdálenosti
OKLIKA = 1.3           # odhad, když trasa pěšky nejde spočítat: skutečná cesta bývá o třetinu delší
POCET = 3
TYDEN = 7 * 24 * 60    # minut

NASTROJ = {
    "name": "doporuc_podniky",
    "description": (
        "Najde v Google Maps nejlepší podniky v pěší vzdálenosti od apartmánu (restaurace, kavárny, bary, obchody, "
        "lékárny…), které mají dobré hodnocení z dostatku recenzí a jsou otevřené v den a čas, na který se host ptá. "
        "Vrátí až 3 podniky a značku (např. [TIPY Z MAP 1]). Do odpovědi hostovi napiš krátký úvod a přesně tu značku – "
        "systém na její místo vloží seznam s hodnocením, časem pěšky, otevírací dobou a odkazem. Tyto údaje sám nepiš."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "odkud": {"type": "string", "description": "Adresa apartmánu ze znalostní báze, např. 'Vinohradská 12, Praha'"},
            "dotaz": {"type": "string", "description": "Co host hledá, anglicky a konkrétně, např. 'italian restaurant', "
                                                       "'specialty coffee', 'cocktail bar', 'pharmacy', 'supermarket'"},
            "kdy": {"type": "string", "description": "Kdy tam host chce jít, 'RRRR-MM-DD HH:MM' (čas v Praze). "
                                                     "Když to host neuvedl, aktuální datum a čas."},
        },
        "required": ["odkud", "dotaz", "kdy"],
        "additionalProperties": False,
    },
}


class PodnikyChyba(Exception):
    pass


def zapnuto():
    """Model dostane nástroj, jen když je přepínač zapnutý a je vyplněný klíč Google."""
    return bool(config.DOPORUCENI_PODNIKU and config.GOOGLE_MAPS_API_KEY)


def vzdalenost_m(lat1, lon1, lat2, lon2):
    """Vzdušná vzdálenost dvou bodů v metrech."""
    f1, f2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((f2 - f1) / 2) ** 2
         + math.cos(f1) * math.cos(f2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6_371_000 * math.asin(math.sqrt(a))


def _souradnice(adresa):
    lat, lon, _ = mapy._najdi(adresa)
    return lat, lon


def _pesky_min(lat1, lon1, lat2, lon2):
    """Čas pěšky po skutečné trase (jako nástroj trasa); když trasa nejde spočítat, odhad ze vzdušné vzdálenosti."""
    try:
        minuty = mapy._trasa_osrm(lat1, lon1, lat2, lon2)["duration"] / 60
    except Exception as e:
        log.warning("Trasu pěšky k podniku nejde spočítat (%s) – použiju odhad", e)
        minuty = vzdalenost_m(lat1, lon1, lat2, lon2) * OKLIKA / METRU_ZA_MINUTU
    return mapy._upraveny_cas(minuty)


def _hledej(dotaz, lat, lon, polomer_m, min_hodnoceni):
    """Google Places API (New) – Text Search kolem bodu. Vrací seznam míst (pole podle POLE)."""
    resp = requests.post(URL, timeout=20, headers={
        "X-Goog-Api-Key": config.GOOGLE_MAPS_API_KEY, "X-Goog-FieldMask": POLE,
    }, json={
        "textQuery": dotaz, "languageCode": "en", "regionCode": "cz", "pageSize": 20,
        "minRating": math.floor(min_hodnoceni * 2) / 2,  # Google bere jen násobky 0,5; přesně filtruje kód
        "locationBias": {"circle": {"center": {"latitude": lat, "longitude": lon}, "radius": float(polomer_m)}},
    })
    if resp.status_code != 200:
        raise PodnikyChyba(f"Google Places odpověděl {resp.status_code}: {resp.text[:300]}")
    return resp.json().get("places") or []


def _cas_dotazu(kdy):
    for format_ in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(kdy or "").strip(), format_)
        except ValueError:
            continue
    return hodiny.ted()  # host čas neuvedl (nebo ho model zapsal jinak) – teď


def _periody(misto, kdy):
    """Do 7 dní aktuální otevírací doba Googlu (svátky, výjimky), dál běžná. None = otevírací doba neznámá."""
    aktualni = (misto.get("currentOpeningHours") or {}).get("periods")
    if aktualni is not None and 0 <= (kdy.date() - hodiny.dnes()).days < 7:
        return aktualni
    return (misto.get("regularOpeningHours") or {}).get("periods")


def _minuta_tydne(bod):
    return bod.get("day", 0) * 1440 + bod.get("hour", 0) * 60 + bod.get("minute", 0)


def _cas(bod):
    return f"{bod.get('hour', 0)}:{bod.get('minute', 0):02d}"


def otevreno(periody, kdy):
    """Úsek otevírací doby, ve kterém je v čas kdy otevřeno ('11:00–23:00', přes půlnoc '18:00–2:00'),
    nebo None – zavřeno nebo otevírací doba neznámá. Dny jako v Google Places: 0 = neděle."""
    t = ((kdy.weekday() + 1) % 7) * 1440 + kdy.hour * 60 + kdy.minute
    for p in periody or []:
        if "close" not in p:  # Google takhle zapisuje nonstop
            return "0:00–24:00"
        od, do = _minuta_tydne(p["open"]), _minuta_tydne(p["close"])
        if do <= od:
            do += TYDEN  # přes konec týdne (sobota večer → neděle ráno)
        if od <= t < do or od <= t + TYDEN < do:
            return f"{_cas(p['open'])}–{_cas(p['close'])}"
    return None


def _skore(misto):
    """Hodnocení vážené počtem recenzí: málo recenzí táhne hodnocení k minimu (DOPORUCENI_MIN_HODNOCENI)."""
    r, n, m = misto["rating"], misto["userRatingCount"], max(1, config.DOPORUCENI_MIN_RECENZI)
    return (n * r + m * config.DOPORUCENI_MIN_HODNOCENI) / (n + m)


def _tisice(n):
    return f"{n:,}".replace(",", " ")


def doporuc(odkud, dotaz, kdy=""):
    """Až 3 nejlepší otevřené podniky v okolí. Vrací (výsledek pro model, hotový seznam pro hosta; "" = nic)."""
    if not config.GOOGLE_MAPS_API_KEY:
        raise PodnikyChyba("Chybí GOOGLE_MAPS_API_KEY – doporučení z Google Maps nejde.")
    cas = _cas_dotazu(kdy)
    lat, lon = _souradnice(odkud)
    max_m = config.DOPORUCENI_MAX_PESKY_MIN * METRU_ZA_MINUTU
    kandidati = []
    for m in _hledej(dotaz, lat, lon, max_m, config.DOPORUCENI_MIN_HODNOCENI):
        poloha = m.get("location") or {}
        if (m.get("businessStatus", "OPERATIONAL") != "OPERATIONAL" or "latitude" not in poloha
                or (m.get("rating") or 0) < config.DOPORUCENI_MIN_HODNOCENI
                or (m.get("userRatingCount") or 0) < config.DOPORUCENI_MIN_RECENZI
                or vzdalenost_m(lat, lon, poloha["latitude"], poloha["longitude"]) > max_m):
            continue
        doba = otevreno(_periody(m, cas), cas)
        if doba:
            kandidati.append((m, doba))
    vybrane = []
    for m, doba in sorted(kandidati, key=lambda k: -_skore(k[0])):
        pesky = _pesky_min(lat, lon, m["location"]["latitude"], m["location"]["longitude"])
        if pesky > config.DOPORUCENI_MAX_PESKY_MIN:
            continue
        vybrane.append({"nazev": (m.get("displayName") or {}).get("text") or "?", "hodnoceni": m["rating"],
                        "pocet_hodnoceni": m["userRatingCount"], "pesky_min": pesky, "otevreno": doba,
                        "odkaz": m.get("googleMapsUri") or ""})
        if len(vybrane) == POCET:
            break
    kdy_text = cas.strftime("%Y-%m-%d %H:%M")
    log.info("Doporučení podniků '%s' na %s: %s z %s kandidátů", dotaz, kdy_text, len(vybrane), len(kandidati))
    if not vybrane:
        return {"nalezeno": 0, "kdy": kdy_text, "podniky": [], "poznamka": (
            f"Žádný podnik nevyhovuje (hodnocení aspoň {config.DOPORUCENI_MIN_HODNOCENI} z aspoň "
            f"{config.DOPORUCENI_MIN_RECENZI} recenzí, otevřeno {kdy_text}, do {config.DOPORUCENI_MAX_PESKY_MIN} min "
            "pěšky) – nic si nevymýšlej a eskaluj.")}, ""
    blok = "📍 Google Maps\n" + "\n".join(
        f"{i}. {p['nazev']} – ⭐ {p['hodnoceni']:.1f} ({_tisice(p['pocet_hodnoceni'])}) · 🚶 {p['pesky_min']} min · "
        f"🕒 {p['otevreno']}" + (f"\n{p['odkaz']}" if p["odkaz"] else "") for i, p in enumerate(vybrane, 1))
    return {"nalezeno": len(vybrane), "kdy": kdy_text,
            "podniky": [{k: p[k] for k in ("nazev", "hodnoceni", "pocet_hodnoceni", "pesky_min", "otevreno")}
                        for p in vybrane],
            "poznamka": ("Hostovi napiš krátký úvod a pak přesně značku z pole znacka – seznam s hodnocením, časem "
                         "pěšky, otevírací dobou a odkazem na Google Maps doplní systém. Názvy můžeš zmínit, ale "
                         "hodnocení, otevírací doby ani odkazy sám nepiš.")}, blok
