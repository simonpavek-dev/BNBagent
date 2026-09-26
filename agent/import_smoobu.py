"""Předvyplnění znalostní báze ze Smoobu a export historie konverzací s hosty."""
import re
import time
import unicodedata
from datetime import timedelta

from . import config, kontext, znalosti

HISTORIE_DIR = config.DATA_DIR / "historie"
SABLONA = znalosti.APARTMANY_DIR / "_sablona.yaml"


def _slug(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "apartman"


def _yaml_str(text):
    return '"' + str(text).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'


def _vypln(sablona, klic, hodnota):
    """Nahradí první prázdný řádek `klic: ""` v šabloně hodnotou (zachová komentáře)."""
    return re.sub(rf'^(\s*{klic}): ""', lambda m: f"{m.group(1)}: {_yaml_str(hodnota)}", sablona, count=1, flags=re.M)


def _popis_loznic(rooms):
    casti = []
    if (rooms.get("maxOccupancy") or 0) > 1:
        casti.append(f"max. {rooms['maxOccupancy']} osob")
    nazvy = {
        "bedrooms": "ložnic", "bathrooms": "koupelen", "doubleBeds": "manželských postelí",
        "kingSizeBeds": "king-size postelí", "queenSizeBeds": "queen-size postelí",
        "singleBeds": "jednolůžek", "sofaBeds": "rozkládacích gaučů", "couches": "gaučů",
        "childBeds": "dětských postýlek",
    }
    for klic, nazev in nazvy.items():
        if rooms.get(klic):
            casti.append(f"{rooms[klic]} {nazev}")
    return ", ".join(casti)


def vytvor_soubory(smoobu):
    """Pro každý apartmán ze Smoobu vytvoří YAML (existující soubory nepřepisuje). Vrátí seznam (soubor, stav)."""
    existujici = {str(d.get("smoobu_id") or "").strip(): s for s, d in znalosti.vsechny_apartmany()}
    placeholdery = smoobu.custom_placeholders()
    sablona = SABLONA.read_text(encoding="utf-8")
    vysledek = []

    for a in smoobu.apartments():
        apt_id = str(a["id"])
        if apt_id in existujici:
            vysledek.append((existujici[apt_id], "už existuje – nechávám beze změny"))
            continue
        detail = smoobu.apartment(apt_id)
        loc = detail.get("location") or {}
        mesto = " ".join(str(x) for x in [loc.get("zip"), loc.get("city")] if x)
        adresa = ", ".join(str(x) for x in [loc.get("street"), mesto] if x)

        text = sablona
        text = _vypln(text, "smoobu_id", apt_id)
        text = _vypln(text, "nazev", a.get("name", ""))
        if adresa:
            text = _vypln(text, "adresa", adresa)
        if _popis_loznic(detail.get("rooms") or {}):
            text = _vypln(text, "loznice", _popis_loznic(detail.get("rooms") or {}))
        vybaveni = detail.get("amenities") or detail.get("equipments") or []
        if vybaveni:
            text = _vypln(text, "ostatni", "Vybavení podle Smoobu: " + ", ".join(map(str, vybaveni)))

        vlastni = [p for p in placeholdery if p.get("type") == 2 and str(p.get("foreignId")) == apt_id]
        if vlastni:
            text += "\n# Texty uložené ve Smoobu u tohoto apartmánu (vlastní proměnné) – agent je také zná\nsmoobu_texty:\n"
            text += "".join(f"  {p['key']}: {_yaml_str(p.get('defaultValue') or '')}\n" for p in vlastni)

        soubor = _slug(a.get("name", apt_id))
        path = znalosti.APARTMANY_DIR / f"{soubor}.yaml"
        if path.exists():
            soubor = f"{soubor}-{apt_id}"
            path = znalosti.APARTMANY_DIR / f"{soubor}.yaml"
        path.write_text(text, encoding="utf-8")
        vysledek.append((soubor, "vytvořeno"))

    # prázdné šablony apt-01…apt-10, které nikdo nevyplnil, už nejsou potřeba
    for path in znalosti.APARTMANY_DIR.glob("apt-[0-9][0-9].yaml"):
        if path.read_text(encoding="utf-8") == sablona:
            path.unlink()

    globalni = [p for p in placeholdery if p.get("type") is None]
    return vysledek, globalni


def export_historie(smoobu, dni=365):
    """Uloží konverzace s hosty za poslední rok do data/historie/<apartmán>.md (podklad pro časté dotazy)."""
    HISTORIE_DIR.mkdir(exist_ok=True)
    dnes = kontext.dnes()
    po_apartmanech = {}
    for r in smoobu.reservations(dnes - timedelta(days=dni), dnes + timedelta(days=60)):
        if r.get("is-blocked-booking"):
            continue
        zpravy = smoobu.messages(r["id"])
        time.sleep(0.1)  # šetrně k limitu Smoobu API
        if not any(m.get("type") == 1 for m in zpravy):
            continue
        apt = (r.get("apartment") or {}).get("name", "neznamy")
        po_apartmanech.setdefault(apt, []).append(
            f"## Rezervace {r.get('id')} · {(r.get('channel') or {}).get('name', '?')} · "
            f"{r.get('arrival')} → {r.get('departure')}\n\n{kontext.popis_konverzace(zpravy)}\n"
        )
    for apt, konverzace in po_apartmanech.items():
        (HISTORIE_DIR / f"{_slug(apt)}.md").write_text(f"# {apt}\n\n" + "\n".join(konverzace), encoding="utf-8")
    return {apt: len(k) for apt, k in po_apartmanech.items()}
