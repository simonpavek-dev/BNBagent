"""Značky místo kódů a Wi-Fi v odpovědích hostům (B4): model skutečné hodnoty nevidí ani nepíše.

Text pro model (znalostní báze bytu, konverzace) dostane místo hodnot značky [KÓD BYTU], [KÓD DOMU], [WIFI SÍŤ],
[WIFI HESLO]. V odpovědi modelu se značky nahradí hodnotami ze zdroje pravdy (kód keyboxu z aplikace úklidů,
kód domu a Wi-Fi ze znalostní báze). Zbylá značka nebo číslo, které vypadá jako kód = odpověď se sama neodešle,
hostitelé ji dostanou ke kontrole. Volá `prace`, `navrhy`.
"""
import re

# značka velkými písmeny v hranatých závorkách – i vymyšlená ([KÓD VCHODU], [DOPLNIT]…)
ZNACKA = re.compile(r"\[[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ0-9 _-]{2,}\]")
# údaje s čísly, které kód nejsou: datum, částka, desetinné číslo (souřadnice v odkazu)
BEZPECNE = re.compile(r"\d{1,2}\.\s?\d{1,2}\.\s?\d{4}|\d{4}-\d{2}-\d{2}|\d+[.,]\d+"
                      r"|(?:Kč|CZK|EUR|€|\$|USD|£)\s?\d+|\d+\s?(?:Kč|CZK|EUR|€|USD|,-)")
# 4–8 číslic samostatně (ne součást telefonu, odkazu nebo slova)
CISLO = re.compile(r"(?<![\w:/+=&?#-])\d{4,8}(?![\w:/=&-])")
MIN_DELKA = 3  # kratší hodnoty se v textu neschovávají (nahradily by i běžná slova)


def hodnoty(apartman, kod):
    """{značka: skutečná hodnota} pro tuto rezervaci; prázdné údaje chybí (jejich značka pak zůstane = problém)."""
    prijezd = (apartman or {}).get("prijezd") or {}
    wifi = (apartman or {}).get("wifi") or {}
    h = {"[KÓD BYTU]": kod, "[KÓD DOMU]": prijezd.get("kod_vchod"),
         "[WIFI SÍŤ]": wifi.get("sit"), "[WIFI HESLO]": wifi.get("heslo")}
    return {z: str(v).strip() for z, v in h.items() if v is not None and str(v).strip()}


def schovej(text, apartman, hodnoty_):
    """Nahradí v textu pro model skutečné hodnoty značkami (i výchozí kód keyboxu ze znalostní báze)."""
    dvojice = [(v, z) for z, v in hodnoty_.items()]
    vychozi = str(((apartman or {}).get("prijezd") or {}).get("keybox_kod") or "").strip()
    if vychozi and vychozi not in hodnoty_.values():
        dvojice.append((vychozi, "[KÓD BYTU]"))
    for hodnota, znacka in sorted(dvojice, key=lambda d: -len(d[0])):
        if len(hodnota) >= MIN_DELKA:
            text = re.sub(rf"(?<!\w){re.escape(hodnota)}(?!\w)", znacka, text or "")
    return text


def zbyle_znacky(text):
    return sorted(set(ZNACKA.findall(text or "")))


def dosad(text, hodnoty_):
    """Dosadí do odpovědi modelu skutečné hodnoty. Vrací (text, problémy) – problémy = proč ji neposlat bez kontroly."""
    problemy = [f"číslo {m.group()} vypadá jako kód (model kódy psát nesmí)"
                for m in CISLO.finditer(BEZPECNE.sub(" ", text or ""))]
    for znacka, hodnota in hodnoty_.items():
        text = (text or "").replace(znacka, hodnota)
    problemy += [f"značka {z} nemá skutečnou hodnotu" for z in zbyle_znacky(text)]
    return text, problemy


def zpracuj(vysledek, hodnoty_):
    """Rozhodnutí modelu o zprávě: dosadí hodnoty; problém v odpovědi hostovi → vysledek['kontrola']."""
    vysledek = dict(vysledek)
    vysledek["odpoved_hostovi"], problemy = dosad(vysledek.get("odpoved_hostovi", ""), hodnoty_)
    vysledek["navrh_pro_hostitele"], _ = dosad(vysledek.get("navrh_pro_hostitele", ""), hodnoty_)
    if problemy and vysledek["odpoved_hostovi"].strip():
        vysledek["kontrola"] = "; ".join(problemy)
    return vysledek
