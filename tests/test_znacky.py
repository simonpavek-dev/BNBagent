"""B4: model nikdy nepíše kódy ani Wi-Fi. Vidí jen značky ([KÓD BYTU], [KÓD DOMU], [WIFI SÍŤ], [WIFI HESLO]),
skutečné hodnoty do odpovědi dosadí kód ze zdroje pravdy. Zbylá značka nebo číslo, které vypadá jako kód,
= odpověď neodejde sama, hostitelé ji dostanou ke kontrole."""
from datetime import timedelta

import pytest

from agent import config, hodiny, znacky

HODNOTY = {"[KÓD BYTU]": "1111", "[WIFI SÍŤ]": "TestNet", "[WIFI HESLO]": "test-heslo"}


def _host_se_pta(svet, otazka="What is the wifi password?", prijezd_za=0):
    dnes = hodiny.dnes()
    svet.smoobu.pridej_rezervaci("R1", dnes + timedelta(days=prijezd_za), dnes + timedelta(days=prijezd_za + 2))
    svet.smoobu.napis_my("R1", "Hi! Keybox code: 1111, Wi-Fi TestNet / test-heslo")  # dřívější instrukce
    hodiny.posun(minutes=5)
    svet.smoobu.napis_host("R1", otazka)


def test_model_nevidi_kody_ani_wifi(svet):
    _host_se_pta(svet)
    svet.model.odpovez(text="The password is [WIFI HESLO].")
    svet.cyklus()
    [volani] = [v for v in svet.model.volani if v["ucel"] == "zpráva hosta"]
    videl = volani["kontext"] + volani["apartman"]
    for tajne in ("1111", "TestNet", "test-heslo"):
        assert tajne not in videl, tajne
    assert "[KÓD BYTU]" in videl and "[WIFI HESLO]" in videl


def test_znacky_v_odpovedi_dosadi_kod(svet):
    _host_se_pta(svet)
    svet.model.odpovez(text="Wi-Fi: [WIFI SÍŤ] / [WIFI HESLO], keybox code [KÓD BYTU].")
    svet.cyklus()
    navrh = svet.db.navrh(svet.telegram.navrh_id())
    assert navrh["text"] == "Wi-Fi: TestNet / test-heslo, keybox code 1111."


def test_ostre_odejde_se_skutecnymi_hodnotami(svet, monkeypatch):
    monkeypatch.setattr(config, "REZIM", "ostre")
    _host_se_pta(svet)
    svet.model.odpovez(text="The password is [WIFI HESLO].")
    svet.cyklus()
    assert svet.smoobu.odeslane == [("R1", "The password is test-heslo.")]


def test_vymysleny_kod_neodejde_ostre(svet, monkeypatch):
    monkeypatch.setattr(config, "REZIM", "ostre")
    _host_se_pta(svet, "What is the keybox code?")
    svet.model.odpovez(text="Your keybox code is 9876.")
    svet.cyklus()
    assert svet.smoobu.odeslane == []
    [z] = svet.telegram.s_tlacitky()
    assert "ZKONTROLUJ" in z["text"] and "9876" in z["text"]
    assert svet.db.zprava_vyrizena(svet.smoobu.konverzace["R1"][-1]["id"])  # zpráva hosta se neztratila


def test_znacka_bez_hodnoty_neodejde(svet, monkeypatch):
    monkeypatch.setattr(config, "REZIM", "ostre")
    _host_se_pta(svet, "What is the building door code?")
    svet.model.odpovez(text="The building code is [KÓD DOMU].")   # testbyt kód domu nemá
    svet.cyklus()
    assert svet.smoobu.odeslane == []
    assert any("[KÓD DOMU]" in z["text"] and "ZKONTROLUJ" in z["text"] for z in svet.telegram.s_tlacitky())


def test_schvaleni_navrhu_se_zbylou_znackou_neodesle(svet):
    _host_se_pta(svet)
    svet.model.odpovez(text="The building code is [KÓD DOMU].")
    svet.cyklus()
    svet.telegram.klikni(svet.smoobu, svet.db, "odeslat", svet.telegram.navrh_id())
    assert svet.smoobu.odeslane == []
    assert any("značk" in z["text"] for z in svet.telegram.zpravy)


@pytest.mark.parametrize("text", [
    "Check-in is from 15:00, check-out by 10:00.",
    "Parking costs 1500 Kč per day (60 EUR).",
    "See you on 2. 11. 2026! Test team, WhatsApp: +000 000 000 000",
    "It is a 12 min walk: https://www.google.com/maps/dir/?api=1&destination=50.0875,14.4213",
])
def test_bezne_udaje_nejsou_podezrele(text):
    vysledek, problemy = znacky.dosad(text, HODNOTY)
    assert problemy == [] and vysledek == text


@pytest.mark.parametrize("text", ["Your code is 9876.", "Code: 123456", "Use [KÓD VCHODU] at the door."])
def test_podezrele_cislo_nebo_neznama_znacka(text):
    _, problemy = znacky.dosad(text, HODNOTY)
    assert problemy
