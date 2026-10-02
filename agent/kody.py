"""Kódy keyboxů: u každé další rezervace se ke kódu přičte 1010 (1111 → 2121, 7988 → 8998).
Když keybox_kod_plati_pro_rezervaci necháš prázdné, bere se keybox_kod jako stálý kód.

V YAML apartmánu je uložen jeden známý kód (keybox_kod) a rezervace, pro kterou platí
(keybox_kod_plati_pro_rezervaci). Kód pro jinou rezervaci se dopočítá podle toho,
o kolik rezervací (seřazených podle příjezdu) je dál nebo blíž.
"""
from . import kontext, uklidy

KROK = 1010  # o kolik se kód zvýší u každé další rezervace


def posun(kod, kroku):
    """Kód o `kroku` rezervací dál (záporné = dřív). Mimo rozsah 0000–9999 vrátí None."""
    kod = str(kod)
    if not kod.isdigit():
        return None
    novy = int(kod) + KROK * kroku
    if not 0 <= novy < 10 ** len(kod):
        return None  # např. po 9999 – pravidlo neznáme, radši se zeptat hostitele
    return str(novy).zfill(len(kod))


def kod_pro_rezervaci(smoobu, apartman, rezervace):
    """Vrátí kód keyboxu pro danou rezervaci, nebo None, když ho nejde spolehlivě určit."""
    if uklidy.zapnuto():  # poslední kód z aplikace úklidů (nebo znalostní báze, pokud je novější)
        return uklidy.aktualni_kod((rezervace.get("apartment") or {}).get("id"))
    prijezd_info = (apartman or {}).get("prijezd") or {}
    zakladni_kod = str(prijezd_info.get("keybox_kod") or "").strip()
    zakladni_rez = str(prijezd_info.get("keybox_kod_plati_pro_rezervaci") or "").strip()
    if not zakladni_kod:
        return None
    if not zakladni_rez:  # stálý kód, který se nemění
        return zakladni_kod
    if str(rezervace.get("id")) == zakladni_rez:
        return zakladni_kod

    zaklad = smoobu.reservation(zakladni_rez)
    prijezdy = [kontext._datum(zaklad.get("arrival")), kontext._datum(rezervace.get("arrival"))]
    if None in prijezdy:
        return None
    apt_id = (rezervace.get("apartment") or {}).get("id")
    seznam = [
        r for r in smoobu.reservations(min(prijezdy), max(prijezdy))
        if (r.get("apartment") or {}).get("id") == apt_id and not r.get("is-blocked-booking")
    ]
    seznam.sort(key=lambda r: (str(r.get("arrival")), r.get("id") or 0))
    ids = [str(r.get("id")) for r in seznam]
    if zakladni_rez not in ids or str(rezervace.get("id")) not in ids:
        return None  # např. výchozí rezervace byla zrušena – radši nehádat
    return posun(zakladni_kod, ids.index(str(rezervace.get("id"))) - ids.index(zakladni_rez))
