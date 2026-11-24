"""Podpis ve zprávách hostům jen na začátku a na konci konverzace (P3.1, přepínač PODPIS_JEN_ZACATEK_A_KONEC).

Se zapnutým přepínačem podpis nepíše model, ale doplní ho kód – jen do první zprávy, kterou hostovi v konverzaci
posíláme (konverzaci nezahájila třeba automatická zpráva Smoobu), a do zpráv po skončení pobytu. Instrukce k příjezdu
mají podpis vždy (host u dveří má po ruce WhatsApp), ty skládá `instrukce.py` ze šablony. Ostatní zprávy jsou bez
podpisu; kdyby ho model nebo hostitel přesto napsal, kód ho z konce zprávy odstraní i s pozdravem před ním.
Text podpisu je v obecne.yaml (hostitel.podpis). Volají `prace`, `navrhy`, `spravce`, `uklidy`.
"""
import re

from . import config, hodiny, kontext, znalosti

# řádek, kterým podpis začíná: „Rentys“, „Rentys team“, „Rentys – Simon & Michael“ (ne věta, která tak začíná)
RENTYS = re.compile(r"rentys(\s+team|\s*[-–—]\s*[^.?!]{0,40})?[.!]?", re.I)
# pozdrav před podpisem – krátký řádek s čárkou na konci, nebo běžné závěrečné formule
POZDRAV = re.compile(
    r"(best|kind|warm(est)?|many)?\s*(regards|wishes)|cheers|thanks again|(viele|liebe|beste)\s+grüße"
    r"|mit freundlichen grüßen|s pozdravem|se srdečným pozdravem|s pozdravom|cordialement|bien à vous"
    r"|(un\s+)?saludos?( cordiales)?|cordiali saluti|distinti saluti|pozdrawiam(y)?|z pozdrowieniami", re.I)
HLEDAT_V_POSLEDNICH_RADCICH = 8


def cely():
    """Celý podpis z obecne.yaml (s WhatsApp čísly)."""
    return str((znalosti.obecne().get("hostitel") or {}).get("podpis") or "").strip()


def _prvni_radky():
    """První řádky nastavených podpisů (malými písmeny) – podle nich se podpis pozná i bez slova Rentys."""
    hostitel = znalosti.obecne().get("hostitel") or {}
    radky = {str(hostitel.get(k) or "").strip().split("\n")[0].strip().lower() for k in ("podpis", "podpis_kratky")}
    return {r for r in radky if r}


def _je_pozdrav(radek):
    radek = radek.strip()
    if not radek or len(radek) > 40:
        return False
    return bool(POZDRAV.fullmatch(radek.rstrip(",.!"))) or (radek.endswith(",") and len(radek.split()) <= 4)


def odstran(text):
    """Text bez podpisu (a pozdravu před ním) na konci zprávy. Věta uprostřed, která zmíní Rentys, zůstane."""
    radky = (text or "").rstrip().split("\n")
    prvni = _prvni_radky()
    for i in range(len(radky) - 1, max(-1, len(radky) - 1 - HLEDAT_V_POSLEDNICH_RADCICH), -1):
        radek = radky[i].strip()
        if radek.lower() in prvni or RENTYS.fullmatch(radek):
            if i > 0 and _je_pozdrav(radky[i - 1]):
                i -= 1
            return "\n".join(radky[:i]).rstrip()
    return (text or "").rstrip()


def je_zacatek(zpravy):
    """Hostovi v konverzaci ještě nic nepřišlo (ani automatická zpráva Smoobu). None = konverzace neznámá → ne."""
    return zpravy is not None and not any(m.get("type") != 1 for m in zpravy)


def je_konec(odjezd):
    """Pobyt skončil (den po odjezdu a později) – zpráva hostovi už je rozloučení."""
    den = kontext._datum(odjezd) if odjezd else None
    return bool(den) and hodiny.dnes() > den


def uprav(text, zpravy, odjezd=None):
    """Zpráva hostovi s podpisem jen na začátku a na konci konverzace. Bez přepínače beze změny."""
    if not config.PODPIS_JEN_ZACATEK_A_KONEC or not (text or "").strip():
        return text
    text = odstran(text)
    if text and (je_zacatek(zpravy) or je_konec(odjezd)) and cely():
        return f"{text}\n\n{cely()}"
    return text
