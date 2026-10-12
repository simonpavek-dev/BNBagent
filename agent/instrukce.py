"""Instrukce k příjezdu ze šablony (přepínač INSTRUKCE_ZE_SABLONY).

Kódy, Wi-Fi, adresu a časy dosazuje kód ze zdroje pravdy (aplikace úklidů / znalostní báze), nikdy model.
Rámec zprávy je v znalostni-baze/obecne.yaml (sablona_zpravy_k_prijezdu, místa {…}). Anglicky mluvící host
dostane zprávu bez modelu; ostatním ji model jen přeloží a kód ověří, že v překladu zůstaly všechny klíčové údaje
– jinak se pošle anglická verze.
"""
from . import mozek, znalosti

ANGLICTINA = ("en", "english", "angličtina", "anglictina")


def _jmeno(rezervace):
    jmeno = str(rezervace.get("guest-name") or "").strip().split(" ")[0]
    return jmeno.capitalize() if jmeno.isupper() else jmeno or "there"


def _jazyk(rezervace):
    return str(rezervace.get("language") or "en").strip().lower()


def sestav(apartman, rezervace, kod):
    """Anglická zpráva z rámce. Vrací (text, chybějící údaje, klíčové údaje k ověření překladu)."""
    obecne = znalosti.obecne()
    prijezd, odjezd, wifi = apartman.get("prijezd") or {}, apartman.get("odjezd") or {}, apartman.get("wifi") or {}
    postup = str(prijezd.get("zprava_k_prijezdu") or prijezd.get("postup_en") or "").strip()
    kod_vchod = str(prijezd.get("kod_vchod") or "").strip()
    hodnoty = {
        "jmeno": _jmeno(rezervace),
        "adresa": str(apartman.get("adresa_en") or apartman.get("adresa") or "").strip(),
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
    klicove = [h for h in (kod, kod_vchod if "[KÓD DOMU]" in postup else "", hodnoty["wifi_sit"], hodnoty["wifi_heslo"],
                           hodnoty["check_in"], hodnoty["check_out"]) if h]
    return text, chybi, klicove


def priprav(apartman, rezervace, kod, zpravy):
    """Stejný tvar výsledku jako dřív model: {poslat, zprava, jazyk_hosta, duvod} + poznamka pro hostitele."""
    jazyk = _jazyk(rezervace)
    if kod and any(m.get("type") != 1 and kod in (m.get("message") or "") for m in zpravy):
        return {"poslat": False, "zprava": "", "jazyk_hosta": jazyk, "poznamka": "",
                "duvod": f"host už instrukce s kódem {kod} v konverzaci má"}
    text, chybi, klicove = sestav(apartman, rezervace, kod)
    if chybi:
        return {"poslat": False, "zprava": text, "jazyk_hosta": jazyk, "poznamka": "",
                "duvod": "ve znalostní bázi chybí: " + ", ".join(chybi)}
    if jazyk in ANGLICTINA:
        return {"poslat": True, "zprava": text, "jazyk_hosta": "en", "duvod": "", "poznamka": ""}
    preklad = mozek.preloz_instrukce(text, jazyk)
    chybi_v_prekladu = [h for h in klicove if h not in preklad]
    if chybi_v_prekladu:
        return {"poslat": True, "zprava": text, "jazyk_hosta": "en", "duvod": "",
                "poznamka": f"Překlad do jazyka hosta ({jazyk}) vynechal nebo změnil údaje {', '.join(chybi_v_prekladu)} "
                            "– posílám anglickou verzi."}
    return {"poslat": True, "zprava": preklad, "jazyk_hosta": jazyk, "duvod": "", "poznamka": ""}
