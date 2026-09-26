"""Mapy: vyhledání místa a trasy pěšky přes OpenStreetMap + odkazy na Google Maps (zdarma, bez klíče)."""
import json
import subprocess
import time
from urllib.parse import urlencode

import requests

from . import znalosti

HEADERS = {"User-Agent": "airbnb-agent/1.0 (hostitel apartmanu v Praze)"}
_posledni_dotaz = [0.0]

NASTROJ_TRASA = {
    "name": "trasa",
    "description": (
        "Najde místo na mapě (OpenStreetMap) a spočítá skutečnou trasu pěšky z adresy apartmánu. "
        "Vrátí nalezenou adresu cíle, vzdálenost, čas chůze a odkazy na Google Maps (pěšky a MHD), "
        "které můžeš poslat hostovi. Cíl zadej co nejpřesněji, ideálně konkrétní adresou nebo názvem místa "
        "a městem (např. 'Staroměstské náměstí, Praha'), ne obecně ('vánoční trhy')."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "odkud": {"type": "string", "description": "Adresa apartmánu, např. 'Vinohradská 12, Praha'"},
            "kam": {"type": "string", "description": "Cílové místo nebo adresa, např. 'Náměstí Míru, Praha'"},
        },
        "required": ["odkud", "kam"],
        "additionalProperties": False,
    },
}


def _najdi(misto):
    # Nominatim povoluje max. 1 dotaz za sekundu
    cekat = 1.1 - (time.time() - _posledni_dotaz[0])
    if cekat > 0:
        time.sleep(cekat)
    _posledni_dotaz[0] = time.time()
    resp = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": misto, "format": "json", "limit": 1, "countrycodes": "cz", "accept-language": "cs"},
        headers=HEADERS, timeout=20,
    )
    resp.raise_for_status()
    vysledky = resp.json()
    if not vysledky:
        raise ValueError(f"Místo nenalezeno: {misto}")
    return float(vysledky[0]["lat"]), float(vysledky[0]["lon"]), vysledky[0].get("display_name", misto)


def _google_odkaz(odkud, kam, rezim):
    return "https://www.google.com/maps/dir/?" + urlencode(
        {"api": 1, "origin": odkud, "destination": kam, "travelmode": rezim}
    )


def _trasa_osrm(lat1, lon1, lat2, lon2):
    # Přes systémový curl – Python na macOS (LibreSSL) se s tímto serverem nedomluví na TLS.
    url = (f"https://routing.openstreetmap.de/routed-foot/route/v1/driving/"
           f"{lon1},{lat1};{lon2},{lat2}?overview=false&steps=true")
    out = subprocess.run(["curl", "-s", "--max-time", "20", "-A", HEADERS["User-Agent"], url],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)["routes"][0]


def _upraveny_cas(minuty):
    """Čas pěšky pro hosty – podle obecne.yaml (trasy.zkraceni_casu_pesky) trochu kratší než reálný."""
    koeficient = float((znalosti.obecne().get("trasy") or {}).get("zkraceni_casu_pesky") or 1)
    cas = minuty * koeficient
    return max(1, round(cas / 5) * 5 if cas >= 12 else round(cas))


def trasa(odkud, kam):
    lat1, lon1, adresa_od = _najdi(odkud)
    lat2, lon2, adresa_do = _najdi(kam)
    route = _trasa_osrm(lat1, lon1, lat2, lon2)
    ulice = []
    for krok in route["legs"][0]["steps"]:
        if krok.get("name") and krok["name"] not in ulice:
            ulice.append(krok["name"])
    return {
        "odkud_nalezeno": adresa_od,
        "kam_nalezeno": adresa_do,
        "cas_pesky_min": _upraveny_cas(route["duration"] / 60),
        "vzdalenost_pesky_km": round(route["distance"] / 1000, 1),
        "trasa_vede_ulicemi": ulice,
        "google_maps_pesky": _google_odkaz(odkud, kam, "walking"),
        "google_maps_mhd": _google_odkaz(odkud, kam, "transit"),
        "poznamka": "Hostovi uváděj cas_pesky_min (už upravený podle hostitele). MHD nástroj nepočítá – "
                    "konkrétní spoj uveď jen ověřený přes web_search, jinak pošli odkaz google_maps_mhd.",
    }
