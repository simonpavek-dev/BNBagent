"""P3.2 Zprávy k odjezdu (DECISIONS.md D6): večer před odjezdem připomenutí check-outu, poděkování a sleva pro
vracející se hosty (ZPRAVA_PRED_ODJEZDEM); v den odjezdu zvlášť prosba o hodnocení (PROSBA_O_HODNOCENI).
Sleva nesmí záviset na hodnocení – zprávy na sebe neodkazují. Obě odejdou samy (hostitelé je mohou zrušit), prosba
o hodnocení po eskalaci během pobytu jen ke schválení. Všechna data jsou smyšlená."""
from datetime import timedelta

import pytest

from agent import config, hodiny
from conftest import ZACATEK

PODPIS = "Test team\nWhatsApp: +000 000 000 000"   # = hostitel.podpis v conftest.OBECNE


@pytest.fixture
def zapnuto(svet, monkeypatch):
    monkeypatch.setattr(config, "ZPRAVA_PRED_ODJEZDEM", True, raising=False)
    monkeypatch.setattr(config, "PROSBA_O_HODNOCENI", True, raising=False)
    monkeypatch.setattr(config, "SLEVA_NA_DALSI_POBYT_PROCENT", 5, raising=False)
    return svet


def _rezervace(svet, prijezd_za, odjezd_za, kanal="Airbnb", jazyk="en"):
    dnes = hodiny.dnes()
    r = svet.smoobu.pridej_rezervaci("R1", dnes + timedelta(days=prijezd_za), dnes + timedelta(days=odjezd_za),
                                     host="Anna Test", kanal=kanal)
    r["language"] = jazyk


def do_casu(svet, hodina, minuta=0, den=0):
    """Agent běží každých 10 minut až do zadaného času (den = kolik dní po začátku simulace)."""
    cil = ZACATEK.replace(hour=hodina, minute=minuta) + timedelta(days=den)
    while hodiny.ted() < cil:
        hodiny.posun(minutes=10)
        svet.cyklus()


def _oznameni(svet, obsahuje):
    return [z for z in svet.telegram.zpravy if obsahuje in z["text"]]


def test_zprava_pred_odjezdem_odejde_v_18_se_slevou(zapnuto):
    svet = zapnuto
    _rezervace(svet, -2, 1)                                     # odjezd zítra
    do_casu(svet, 15, 50)
    assert svet.smoobu.odeslane == [] and not _oznameni(svet, "PŘED ODJEZDEM")
    do_casu(svet, 16, 10)                                       # připraveno, hostitelé ho mohou zrušit
    [oznameni] = _oznameni(svet, "PŘED ODJEZDEM")
    assert all(d.startswith("zahodit:") for _, d in oznameni["tlacitka"]) and svet.smoobu.odeslane == []
    do_casu(svet, 18, 10)
    [(_, text)] = svet.smoobu.odeslane
    assert text.startswith("Hi Anna,")
    assert "check-out is by 10:00" in text and "please put the keys back into the keybox." in text
    assert "5 % off your next stay" in text
    assert "review" not in text.lower()                         # sleva nesmí souviset s hodnocením
    assert text.endswith(PODPIS)
    do_casu(svet, 21)
    assert len(svet.smoobu.odeslane) == 1                       # jen jednou


@pytest.mark.parametrize("kanal,procent", [("Booking.com", 5), ("Airbnb", 0)])
def test_bez_slevy_booking_nebo_nula_procent(zapnuto, monkeypatch, kanal, procent):
    monkeypatch.setattr(config, "SLEVA_NA_DALSI_POBYT_PROCENT", procent)
    _rezervace(zapnuto, -2, 1, kanal=kanal)
    do_casu(zapnuto, 18, 10)
    [(_, text)] = zapnuto.smoobu.odeslane
    assert "check-out is by 10:00" in text and "% off" not in text


def test_pobyt_na_jednu_noc_bez_vecerni_zpravy(zapnuto):
    _rezervace(zapnuto, 0, 1)                                   # přijíždí dnes, odjíždí zítra
    do_casu(zapnuto, 19)
    assert not _oznameni(zapnuto, "PŘED ODJEZDEM") and zapnuto.smoobu.odeslane == []


def test_smoobu_uz_check_out_pripomnelo(zapnuto):
    _rezervace(zapnuto, -2, 1)
    zapnuto.smoobu.napis_my("R1", "Reminder: tomorrow is your check-out day.")   # např. automatická zpráva Smoobu
    do_casu(zapnuto, 18, 30)
    assert zapnuto.smoobu.odeslane == []
    assert _oznameni(zapnuto, "neposílám")                      # hostitelé vědí, že zprávu posílá někdo jiný


def test_prosba_o_hodnoceni_v_den_odjezdu(zapnuto):
    svet = zapnuto
    _rezervace(svet, -2, 0)                                     # odjezd dnes
    do_casu(svet, 10, 10)
    [oznameni] = _oznameni(svet, "PROSBA O HODNOCENÍ")
    assert all(d.startswith("zahodit:") for _, d in oznameni["tlacitka"]) and svet.smoobu.odeslane == []
    do_casu(svet, 12, 10)
    [(_, text)] = svet.smoobu.odeslane
    assert "review" in text and "%" not in text                 # prosba o hodnocení slevu nezmiňuje
    assert text.endswith(PODPIS)


def test_po_eskalaci_prosba_o_hodnoceni_jen_ke_schvaleni(zapnuto):
    svet = zapnuto
    _rezervace(svet, -2, 0)
    svet.db.oznac_zpravu("m1", "R1", "eskalovat")                # během pobytu si host stěžoval
    do_casu(svet, 12, 30)
    assert svet.smoobu.odeslane == []
    [oznameni] = _oznameni(svet, "PROSBA O HODNOCENÍ")
    assert any(d.startswith("odeslat:") for _, d in oznameni["tlacitka"])
    assert "eskal" in oznameni["text"]


def test_preklad_do_jazyka_hosta(zapnuto):
    svet = zapnuto
    _rezervace(svet, -2, 1, jazyk="de")
    svet.model.odpovedi["překlad instrukcí"] = lambda kontext: {
        "zprava": "Hallo Anna,\n\nmorgen ist Ihr Abreisetag – Check-out bis 10:00. 5 % Rabatt beim nächsten Mal."
                  f"\n\n{PODPIS}"}
    do_casu(svet, 18, 10)
    [(_, text)] = svet.smoobu.odeslane
    assert text.startswith("Hallo Anna,") and "Check-out bis 10:00" in text


def test_vypnuto_nic_neposila(svet):
    _rezervace(svet, -2, 1)
    do_casu(svet, 12, 30, den=1)                                # večer před odjezdem i den odjezdu
    assert svet.smoobu.odeslane == []
    assert not _oznameni(svet, "PŘED ODJEZDEM") and not _oznameni(svet, "PROSBA O HODNOCENÍ")
