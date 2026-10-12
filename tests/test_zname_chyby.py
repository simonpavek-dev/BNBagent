"""Známé chyby – opravíme v dalších krocích. strict=True: až chybu opravíme, test „projde neočekávaně“
a připomene odstranit značku xfail."""
from datetime import timedelta

import pytest

from agent import config, hodiny, prace, uklidy


@pytest.mark.xfail(strict=True, reason="prace._cekajici_zprava bere jen poslední zprávu konverzace – když po dotazu "
                                       "hosta přijde automatická zpráva Smoobu (type 2), dotaz zůstane bez odpovědi")
def test_dotaz_hosta_a_po_nem_automaticka_zprava_smoobu(svet):
    dnes = hodiny.dnes()
    svet.smoobu.pridej_rezervaci("R1", dnes + timedelta(days=3), dnes + timedelta(days=5))
    svet.smoobu.napis_host("R1", "Is there a hairdryer in the apartment?")
    svet.smoobu.napis_my("R1", "Hi! Your stay is coming up soon … (automatická zpráva Smoobu)")
    svet.model.odpovez(text="Yes, there is a hairdryer in the bathroom.")
    svet.cyklus()
    assert any(v["ucel"] == "zpráva hosta" for v in svet.model.volani), "dotaz hosta nikdo nezpracoval"
    assert svet.telegram.s_tlacitky(), "hostitelé nedostali návrh odpovědi"


@pytest.mark.xfail(strict=True, reason="když Telegram nejde, oznameni.posli vrátí None, ale zpráva hosta je už "
                                       "označená jako vyřízená – eskalace se ztratí a další cyklus ji nezopakuje")
def test_eskalace_pri_vypadku_telegramu_se_neztrati(svet):
    dnes = hodiny.dnes()
    svet.smoobu.pridej_rezervaci("R1", dnes + timedelta(days=3), dnes + timedelta(days=5))
    svet.smoobu.napis_host("R1", "Can we get a discount for a longer stay?")
    svet.model.odpovez(rozhodnuti="eskalovat", text="We'll check and get back to you.",
                       navrh="Sleva – rozhodni.")
    svet.telegram.vypadek = True
    svet.cyklus()                      # Telegram nejde
    svet.telegram.vypadek = False
    hodiny.posun(minutes=3)
    svet.cyklus()                      # Telegram zase jde – eskalace musí dorazit
    assert any("POTŘEBUJU TĚ" in z["text"] for z in svet.telegram.zpravy), "eskalace se ztratila"


@pytest.mark.xfail(strict=True, reason="kody.kod_pro_rezervaci při zapnuté aplikaci úklidů vrací aktuální kód bytu "
                                       "bez ohledu na datum příjezdu – zítřejší host dostane kód hosta, který tam teď bydlí")
def test_zitrejsi_host_nedostane_kod_soucasneho_hosta(svet, monkeypatch):
    monkeypatch.setattr(config, "UKLIDY_URL", "https://uklidy.test")
    monkeypatch.setattr(config, "UKLIDY_LOGIN", "test")
    monkeypatch.setattr(config, "UKLIDY_HESLO", "test")
    dnes = hodiny.dnes()
    vcera, zitra = dnes - timedelta(days=1), dnes + timedelta(days=1)
    monkeypatch.setattr(uklidy, "_stahni", lambda: [
        # včerejší úklid před současným hostem: uklízečka nastavila kód 3333 (platí pro současného hosta)
        {"stay": {"id": "u1", "checkOut": str(vcera), "cleaningDate": str(vcera), "codes": "3333",
                  "uklidStatus": "uklizeno"}, "apartment": {"name": "Testbyt 1"}},
        # zítřejší úklid po současném hostovi: ještě neproběhl, nový kód zatím neznáme
        {"stay": {"id": "u2", "checkOut": str(zitra), "cleaningDate": str(zitra), "codes": None,
                  "uklidStatus": None}, "apartment": {"name": "Testbyt 1"}},
    ])
    svet.smoobu.pridej_rezervaci("TED", vcera, zitra, host="Současný Host")
    svet.smoobu.pridej_rezervaci("ZITRA", zitra, zitra + timedelta(days=3), host="Zítřejší Host")
    hodiny.posun(hours=10)             # 19:00 – agent připravuje instrukce na zítřek
    prace.priprav_prijezdy(svet.smoobu, svet.db, zitra)
    kontext_zitra = next(v["kontext"] for v in svet.model.volani
                         if v["ucel"] == "instrukce k příjezdu" and "Zítřejší Host" in v["kontext"])
    assert "3333" not in kontext_zitra, "zítřejší host by dostal kód současného hosta"
