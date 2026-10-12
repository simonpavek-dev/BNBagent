"""Instrukce k příjezdu ze šablony (přepínač INSTRUKCE_ZE_SABLONY).

Kódy, Wi-Fi, adresu a časy dosazuje kód ze zdroje pravdy (aplikace úklidů / znalostní báze), nikdy model.
Rámec zprávy je v znalostni-baze/obecne.yaml (sablona_zpravy_k_prijezdu, místa {…}). Anglicky mluvící host
dostane zprávu bez modelu; ostatním ji model jen přeloží. Adresu, název a heslo Wi-Fi a kódy model vůbec nevidí: před překladem je kód nahradí značkami
⟦1⟧, ⟦2⟧… a po překladu je vrátí v přesném původním znění. Když značka nebo klíčový údaj v překladu chybí,
pošle se anglická verze.
"""
from . import mozek, znalosti

ANGLICTINA = ("en", "english", "angličtina", "anglictina")


def _jmeno(rezervace):
    jmeno = str(rezervace.get("guest-name") or "").strip().split(" ")[0]
    return jmeno.capitalize() if jmeno.isupper() else jmeno or "there"


def _jazyk(rezervace):
    return str(rezervace.get("language") or "en").strip().lower()


def _adresa(apartman):
    """(celá adresa do zprávy, přesná část, která se nikdy nepřekládá)."""
    presna = str(apartman.get("adresa_presna") or apartman.get("adresa") or "").strip()
    doplnek = str(apartman.get("adresa_doplnek_en") or "").strip()
    return (f"{presna}, {doplnek}" if presna and doplnek else presna), presna


def sestav(apartman, rezervace, kod):
    """Anglická zpráva z rámce. Vrací (text, chybějící údaje, klíčové údaje k ověření překladu)."""
    obecne = znalosti.obecne()
    prijezd, odjezd, wifi = apartman.get("prijezd") or {}, apartman.get("odjezd") or {}, apartman.get("wifi") or {}
    postup = str(prijezd.get("zprava_k_prijezdu") or prijezd.get("postup_en") or "").strip()
    kod_vchod = str(prijezd.get("kod_vchod") or "").strip()
    hodnoty = {
        "jmeno": _jmeno(rezervace),
        "adresa": _adresa(apartman)[0],
        "budova": f" ({apartman['nazev_budovy']})" if apartman.get("nazev_budovy") else "",
        "check_in": str(prijezd.get("check_in_od") or "").strip(),
        "postup": postup.replace("[KÓD DOMU]", kod_vchod).replace("[KÓD BYTU]", kod or ""),
        "wifi_sit": str(wifi.get("sit") or "").strip(),
        "wifi_heslo": str(wifi.get("heslo") or "").strip(),
        "check_out": str(odjezd.get("check_out_do") or "").strip(),
        "odjezd_postup": str(odjezd.get("postup_en") or "").strip(),
        "podpis": str((obecne.get("hostitel") or {}).get("podpis") or "").strip(),
    }
    chybi = [nazev for klic, nazev in (
        ("adresa", "adresa"), ("check_in", "čas check-inu"), ("postup", "postup do bytu (postup_en / zprava_k_prijezdu)"),
        ("wifi_sit", "Wi-Fi síť"), ("wifi_heslo", "Wi-Fi heslo"), ("check_out", "čas check-outu"),
        ("odjezd_postup", "postup při odjezdu (odjezd.postup_en)"), ("podpis", "podpis")) if not hodnoty[klic]]
    if not kod:
        chybi.append("kód keyboxu")
    if "[KÓD DOMU]" in postup and not kod_vchod:
        chybi.append("kód od domu (kod_vchod)")
    text = str(obecne.get("sablona_zpravy_k_prijezdu") or "").strip().format(**hodnoty)
    chranene = [h for h in (_adresa(apartman)[1], hodnoty["wifi_sit"], hodnoty["wifi_heslo"], kod,
                            kod_vchod if "[KÓD DOMU]" in postup else "") if h]
    klicove = chranene + [h for h in (hodnoty["check_in"], hodnoty["check_out"]) if h]
    return text, chybi, klicove, chranene


def _schovej(text, chranene):
    """Nahradí chráněné údaje značkami ⟦1⟧, ⟦2⟧… (nejdelší první, aby se kratší neschoval uvnitř delšího)."""
    znacky = {}
    for i, hodnota in enumerate(sorted(set(chranene), key=len, reverse=True), 1):
        znacka = f"⟦{i}⟧"
        text = text.replace(hodnota, znacka)
        znacky[znacka] = hodnota
    return text, znacky


def _vrat(text, znacky):
    """Vrátí původní údaje za značky; None, když některá značka v překladu chybí nebo je změněná."""
    if any(z not in text for z in znacky):
        return None
    for znacka, hodnota in znacky.items():
        text = text.replace(znacka, hodnota)
    return None if "⟦" in text else text  # cizí / pozměněná značka


def priprav(apartman, rezervace, kod, zpravy):
    """Stejný tvar výsledku jako dřív model: {poslat, zprava, jazyk_hosta, duvod} + poznamka pro hostitele."""
    jazyk = _jazyk(rezervace)
    if kod and any(m.get("type") != 1 and kod in (m.get("message") or "") for m in zpravy):
        return {"poslat": False, "zprava": "", "jazyk_hosta": jazyk, "poznamka": "",
                "duvod": f"host už instrukce s kódem {kod} v konverzaci má"}
    text, chybi, klicove, chranene = sestav(apartman, rezervace, kod)
    if chybi:
        return {"poslat": False, "zprava": text, "jazyk_hosta": jazyk, "poznamka": "",
                "duvod": "ve znalostní bázi chybí: " + ", ".join(chybi)}
    if jazyk in ANGLICTINA:
        return {"poslat": True, "zprava": text, "jazyk_hosta": "en", "duvod": "", "poznamka": ""}
    schovany, znacky = _schovej(text, chranene)
    preklad = _vrat(mozek.preloz_instrukce(schovany, jazyk), znacky) or ""
    chybi_v_prekladu = [h for h in klicove if h not in preklad] if preklad else ["adresa / Wi-Fi / kódy (značky)"]
    if chybi_v_prekladu:
        return {"poslat": True, "zprava": text, "jazyk_hosta": "en", "duvod": "",
                "poznamka": f"Překlad do jazyka hosta ({jazyk}) vynechal nebo změnil údaje {', '.join(chybi_v_prekladu)} "
                            "– posílám anglickou verzi."}
    return {"poslat": True, "zprava": preklad, "jazyk_hosta": jazyk, "duvod": "", "poznamka": ""}
