"""Instrukce k příjezdu ze šablony: kódy, Wi-Fi, adresu a časy dosazuje kód, model jen překládá – a překlad se
kontroluje, že v něm všechny tyto údaje zůstaly. Jiná cesta (model píše celé instrukce) neexistuje."""
from datetime import timedelta

import pytest

from agent import config, hodiny


@pytest.fixture
def sablona(svet, monkeypatch):
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
    for udaj in ("Testovací 1, Praha 9, apartment no. 7", "from 15:00", "Keybox code: 1111",
                 "network TestNet / password test-heslo", "Check-out is by 10:00", "Test team", "+000 000 000 000"):
        assert udaj in text, udaj
    assert "[KÓD" not in text and "{" not in text


def test_jiny_jazyk_model_jen_preklada(sablona):
    sablona.model.odpovedi["překlad instrukcí"] = lambda kontext: {"zprava": "Hallo Anna! " + kontext}
    text = _prijezd(sablona, jazyk="de")
    [preklad] = [v for v in sablona.model.volani if v["ucel"] == "překlad instrukcí"]
    # adresu, název a heslo Wi-Fi ani kódy model vůbec nevidí – dostane místo nich značky
    for chraneno in ("Testovací 1, Praha 9", "TestNet", "test-heslo", "1111"):
        assert chraneno not in preklad["kontext"], chraneno
    assert "⟦" in preklad["kontext"]
    assert text.startswith("Hallo Anna!")
    for udaj in ("Testovací 1, Praha 9", "network TestNet / password test-heslo", "Keybox code: 1111"):
        assert udaj in text, udaj   # po překladu se vrátí přesně v původním znění


def test_preklad_ktery_zmeni_adresu_nebo_wifi_se_nepouzije(sablona):
    # model „přeloží“ značky (adresu a Wi-Fi) – agent to pozná a pošle anglickou verzi
    sablona.model.odpovedi["překlad instrukcí"] = lambda kontext: {
        "zprava": "Hallo Anna! " + __import__("re").sub(r"⟦\d+⟧", "Prag", kontext, count=1)}
    text = _prijezd(sablona, jazyk="de")
    assert text.startswith("Hi Anna,") and "Testovací 1, Praha 9" in text


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


def test_instrukce_vzdy_ze_sablony_model_je_nepise(svet, monkeypatch):
    from agent import mozek
    assert not hasattr(mozek, "priprav_instrukce_k_prijezdu")   # stará cesta, kde kódy psal model, je pryč
    assert not hasattr(config, "INSTRUKCE_ZE_SABLONY")
    monkeypatch.setattr(config, "PRIJEZD_ODESLAT_HODINA", 0)
    hodiny.posun(hours=2)
    text = _prijezd(svet)
    assert [v for v in svet.model.volani if v["ucel"] == "instrukce k příjezdu"] == []
    assert "Keybox code: 1111" in text
