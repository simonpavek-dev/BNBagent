"""Krok P1.2: jednoduché zprávy hostů (poděkování, potvrzení času příjezdu) jdou na levnější model,
všechno ostatní dál na hlavní model. Přepínač LEVNEJSI_MODEL_PRO_JEDNODUCHE, výchozí vypnuto."""
from datetime import timedelta

import pytest

from agent import config, hodiny, trideni

JEDNODUCHE = [
    "Thank you so much!", "Thanks 👍", "Perfect, thank you", "Ok, great",
    "We'll arrive around 18:00", "We will arrive at 7 pm", "Wir kommen gegen 19 Uhr an. Danke!",
    "Přijedeme kolem 17:30, děkujeme", "Arriveremo verso le 20", "Llegaremos a las 16:00",
]
SLOZITE = [
    "Where can we park?", "Can we get a discount? We arrive at 18:00", "The heating is not working, thanks",
    "Thanks! Is there a hairdryer?", "We would like to cancel the reservation", "Děkuji, ale nefunguje Wi-Fi",
    "Thank you. " + "We are really looking forward to it and wanted to ask about several things. " * 3,
    # ze skutečné historie: požadavky schované za poděkováním / bez otazníku
    "Thx Michal!! Your appartement looks great. I come with a friend and need separate bedrooms",
    "Prosím ak je možné, náš príchod do Prahy je medzi 12-13h, ubytovať sa aj skôr ako o 16tej",
    "V poriadku, prosím ak to bude možné, dajte nám vedeť ak by sa vám podarilo sprístupniť ubytovanie skôr",
    "We arrive at 11, could we leave our luggage earlier",
    "Danke, wir kommen um 12 Uhr an und würden gerne früher einchecken",
]


@pytest.mark.parametrize("text", JEDNODUCHE)
def test_jednoducha_zprava(text):
    assert trideni.je_jednoducha(text)


@pytest.mark.parametrize("text", SLOZITE)
def test_slozita_zprava(text):
    assert not trideni.je_jednoducha(text)


def _zprava_hosta(svet, text):
    dnes = hodiny.dnes()
    svet.smoobu.pridej_rezervaci("R1", dnes + timedelta(days=2), dnes + timedelta(days=4))
    svet.smoobu.napis_my("R1", "Hello! Looking forward to your stay.")
    svet.smoobu.napis_host("R1", text)
    svet.model.odpovez(text="Thanks, see you soon!")
    svet.cyklus()
    return [v["model"] for v in svet.model.volani if v["ucel"] == "zpráva hosta"]


def test_zapnuto_jednoducha_jde_na_levnejsi_model(svet, monkeypatch):
    monkeypatch.setattr(config, "LEVNEJSI_MODEL_PRO_JEDNODUCHE", True, raising=False)
    monkeypatch.setattr(config, "MODEL_JEDNODUCHE", "claude-sonnet-5", raising=False)
    assert _zprava_hosta(svet, "We'll arrive around 18:00, thank you!") == ["claude-sonnet-5"]


def test_zapnuto_slozita_jde_na_hlavni_model(svet, monkeypatch):
    monkeypatch.setattr(config, "LEVNEJSI_MODEL_PRO_JEDNODUCHE", True, raising=False)
    monkeypatch.setattr(config, "MODEL_JEDNODUCHE", "claude-sonnet-5", raising=False)
    assert _zprava_hosta(svet, "Where can we park?") == [None]


def test_vypnuto_vse_na_hlavni_model(svet, monkeypatch):
    monkeypatch.setattr(config, "LEVNEJSI_MODEL_PRO_JEDNODUCHE", False, raising=False)
    assert _zprava_hosta(svet, "Thank you so much!") == [None]
