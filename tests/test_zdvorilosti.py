"""Krok P1.3: čisté zdvořilosti hostů (díky, 👍, ok) vyřídí pravidlo bez modelu (přepínač ZDVORILOSTI_BEZ_MODELU,
výchozí vypnuto). Odpověď jde stejnou cestou jako ostatní – v režimu návrhů ke schválení."""
from datetime import timedelta

import pytest

from agent import config, hodiny, trideni

ZDVORILOSTI = ["Thank you so much!", "Danke 👍", "Ok thanks", "Děkujeme!", "👍", "Grazie mille!",
               "Thank you so much! This is great! Have a nice day"]
NE = ["We'll arrive at 18:00, thanks",          # čas příjezdu – potvrdit, to už není jen zdvořilost
      "Thanks, where can we park?", "Thanks, could we check in earlier", "Thank you, the heating is not working",
      "Hello, we booked for 4 people"]


@pytest.mark.parametrize("text", ZDVORILOSTI)
def test_je_zdvorilost(text):
    assert trideni.je_zdvorilost(text)


@pytest.mark.parametrize("text", NE)
def test_neni_zdvorilost(text):
    assert not trideni.je_zdvorilost(text)


@pytest.fixture
def zapnuto(svet, monkeypatch):
    monkeypatch.setattr(config, "ZDVORILOSTI_BEZ_MODELU", True, raising=False)
    return svet


def _konverzace(svet, nase, hosta, jazyk="en", za_dni=2):
    dnes = hodiny.dnes()
    svet.smoobu.pridej_rezervaci("R1", dnes + timedelta(days=za_dni), dnes + timedelta(days=za_dni + 3))
    svet.smoobu.rezervace["R1"]["language"] = jazyk
    svet.smoobu.napis_my("R1", nase)
    svet.smoobu.napis_host("R1", hosta)
    svet.model.odpovez(text="(odpověď modelu)")
    svet.cyklus()


def test_podekovani_bez_modelu_s_navrhem_v_jazyce_hosta(zapnuto):
    _konverzace(zapnuto, "Here are the check-in details …", "Danke schön!", jazyk="de")
    assert [v for v in zapnuto.model.volani if v["ucel"] == "zpráva hosta"] == []
    [navrh] = zapnuto.telegram.s_tlacitky()
    assert "Gern geschehen" in navrh["text"] and "Test team" in navrh["text"]
    assert zapnuto.smoobu.odeslane == []   # režim návrhů – nic neodešlo bez schválení


def test_na_nase_rozlouceni_uz_neodpovida(zapnuto):
    _konverzace(zapnuto, "You're welcome! Enjoy your stay 😊\nTest team", "Thanks!")
    assert [v for v in zapnuto.model.volani if v["ucel"] == "zpráva hosta"] == []
    assert zapnuto.telegram.s_tlacitky() == []
    stav = zapnuto.db.conn.execute("SELECT stav FROM zpravy").fetchone()[0]
    assert stav == "neodpovidat"  # zpráva vědomě bez odpovědi, neztratila se


def test_po_odjezdu_jina_veta(zapnuto):
    dnes = hodiny.dnes()
    zapnuto.smoobu.pridej_rezervaci("R1", dnes - timedelta(days=3), dnes - timedelta(days=1))
    zapnuto.smoobu.napis_my("R1", "Thank you for staying with us! Please leave us a review.")
    zapnuto.smoobu.napis_host("R1", "Thank you, it was lovely!")
    zapnuto.cyklus()
    [navrh] = zapnuto.telegram.s_tlacitky()
    assert "Safe travels" in navrh["text"]


def test_zdvorilost_s_dotazem_jde_na_model(zapnuto):
    _konverzace(zapnuto, "Here are the check-in details …", "Thanks, where can we park?")
    assert any(v["ucel"] == "zpráva hosta" for v in zapnuto.model.volani)


def test_vypnuto_jde_na_model(svet, monkeypatch):
    monkeypatch.setattr(config, "ZDVORILOSTI_BEZ_MODELU", False, raising=False)
    _konverzace(svet, "Here are the check-in details …", "Thank you so much!")
    assert any(v["ucel"] == "zpráva hosta" for v in svet.model.volani)
