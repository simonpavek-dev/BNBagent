"""Sestavení textu, který agent dostane k rozhodnutí (rezervace + konverzace)."""
from datetime import date

from . import hodiny


def dnes():
    return hodiny.dnes()


def _datum(hodnota):
    try:
        return date.fromisoformat(str(hodnota)[:10])
    except ValueError:
        return None


def popis_rezervace(r):
    prijezd, odjezd = _datum(r.get("arrival")), _datum(r.get("departure"))
    radky = [
        f"ID rezervace: {r.get('id')}",
        f"Kanál: {(r.get('channel') or {}).get('name', '?')}",
        f"Host: {r.get('guest-name', '?')}",
        f"Příjezd: {r.get('arrival')}   Odjezd: {r.get('departure')}",
        f"Osob: {r.get('adults', '?')} dospělí, {r.get('children', 0)} děti",
    ]
    if r.get("check-in") or r.get("check-out"):
        radky.append(f"Čas příjezdu/odjezdu uvedený v rezervaci: {r.get('check-in')} / {r.get('check-out')}")
    if r.get("language"):
        radky.append(f"Jazyk hosta podle rezervace: {r.get('language')}")
    if r.get("notice"):
        radky.append(f"Poznámka k rezervaci: {r.get('notice')}")
    if prijezd:
        dni = (prijezd - dnes()).days
        if dni > 0:
            stav = f"host přijede za {dni} dní"
        elif dni == 0:
            stav = "host přijíždí dnes"
        elif odjezd and dnes() < odjezd:
            stav = "host je právě ubytovaný"
        elif odjezd and dnes() == odjezd:
            stav = "dnes je den odjezdu"
        else:
            stav = "pobyt už skončil"
        radky.append(f"Stav pobytu: {stav} (dní do příjezdu: {dni})")
    return "\n".join(radky)


def popis_konverzace(zpravy):
    radky = []
    for m in zpravy:
        kdo = "HOST" if m.get("type") == 1 else "HOSTITEL"
        text = (m.get("message") or "").strip()
        radky.append(f"[{m.get('createdAt', '')}] {kdo}:\n{text}")
    return "\n\n".join(radky) if radky else "(žádné zprávy)"


def sestav(rezervace, zpravy, doplnek=""):
    ted = hodiny.ted().strftime("%A %d. %m. %Y %H:%M")
    casti = [
        f"Aktuální datum a čas (Praha): {ted}",
        "REZERVACE:\n" + popis_rezervace(rezervace),
        "KONVERZACE (od nejstarší):\n" + popis_konverzace(zpravy),
    ]
    if doplnek:
        casti.append(doplnek)
    return "\n\n".join(casti)
