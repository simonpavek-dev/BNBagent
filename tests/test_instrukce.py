"""Instrukce k příjezdu ze šablony (přepínač INSTRUKCE_ZE_SABLONY): kódy, Wi-Fi, adresu a časy dosazuje kód,
model jen překládá – a překlad se kontroluje, že v něm všechny tyto údaje zůstaly."""
from datetime import timedelta

import pytest

from agent import config, hodiny


@pytest.fixture
def sablona(svet, monkeypatch):
    monkeypatch.setattr(config, "INSTRUKCE_ZE_SABLONY", True, raising=False)
    monkeypatch.setattr(config, "PRIJEZD_ODESLAT_HODINA", 0)  # po schválení hned
    hodiny.posun(hours=2)  # 11:00
    return svet


def _prijezd(svet, jazyk="en", host="Anna Test"):
    dnes = hodiny.dnes()
    r = svet.smoobu.pridej_rezervaci("R9", dnes, dnes + timedelta(days=2), host=host)
    r["language"] = jazyk
    svet.smoobu.rezervace["R9"]["language"] = jazyk
    svet.cyklus()
    return svet.db.navrh(svet.telegram.navrh_id())["text"] if svet.telegram.s_tlacitky() else None


def test_anglicky_host_bez_modelu_a_s_presnymi_udaji(sablona):
    text = _prijezd(sablona)
    assert [v for v in sablona.model.volani if v["ucel"] in ("instrukce k příjezdu", "překlad instrukcí")] == []
    assert text.startswith("Hi Anna,")
    for udaj in ("Testovací 1, Prague, apartment no. 7", "from 15:00", "Keybox code: 1111",
                 "network TestNet / password test-heslo", "Check-out is by 10:00", "Test team", "+000 000 000 000"):
        assert udaj in text, udaj
    assert "[KÓD" not in text and "{" not in text


def test_jiny_jazyk_model_jen_preklada(sablona):
    sablona.model.odpovedi["překlad instrukcí"] = lambda kontext: {"zprava": "Hallo Anna! " + kontext}
    text = _prijezd(sablona, jazyk="de")
    [preklad] = [v for v in sablona.model.volani if v["ucel"] == "překlad instrukcí"]
    assert "Keybox code: 1111" in preklad["kontext"]   # model dostal hotovou anglickou zprávu
    assert text.startswith("Hallo Anna!")


def test_preklad_ktery_vynecha_kod_se_nepouzije(sablona):
    sablona.model.odpovedi["překlad instrukcí"] = {"zprava": "Hallo Anna! Der Code ist im Keybox."}
    text = _prijezd(sablona, jazyk="de")
    assert "Keybox code: 1111" in text and text.startswith("Hi Anna,")  # anglická verze
    assert any("překlad" in z["text"].lower() and "anglick" in z["text"].lower() for z in sablona.telegram.zpravy)


def test_bez_wifi_se_instrukce_neposlou(sablona):
    sablona.nastav_kod("1111", "2026-01-01", wifi_sit="")
    assert _prijezd(sablona) is None
    assert any("Wi-Fi" in z["text"] for z in sablona.telegram.zpravy)


def test_host_uz_kod_ma_instrukce_se_nepripravi(sablona):
    dnes = hodiny.dnes()
    sablona.smoobu.pridej_rezervaci("R9", dnes, dnes + timedelta(days=2), host="Anna Test")
    sablona.smoobu.napis_my("R9", "Hi Anna, your keybox code is 1111.")  # hostitel poslal ručně
    sablona.cyklus()
    assert sablona.telegram.s_tlacitky() == []


def test_vypnuty_prepinac_pouzije_model_jako_dosud(svet, monkeypatch):
    monkeypatch.setattr(config, "INSTRUKCE_ZE_SABLONY", False, raising=False)
    monkeypatch.setattr(config, "PRIJEZD_ODESLAT_HODINA", 0)
    hodiny.posun(hours=2)
    text = _prijezd(svet)
    assert any(v["ucel"] == "instrukce k příjezdu" for v in svet.model.volani)
    assert "1111" in text
