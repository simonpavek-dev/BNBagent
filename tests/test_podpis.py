"""P3.1 Podpis jen na začátku a na konci konverzace (přepínač PODPIS_JEN_ZACATEK_A_KONEC, výchozí vypnuto).

Podpis nepíše model, doplní ho kód: první zpráva, kterou hostovi v konverzaci posíláme, a zprávy po skončení
pobytu. Instrukce k příjezdu mají podpis vždy. Ostatní zprávy jsou bez podpisu, i když ho model napíše.
Všechna data jsou smyšlená."""
from datetime import timedelta

import pytest

from agent import config, hodiny, instrukce, mozek, navrhy, podpis

PODPIS = "Test team\nWhatsApp: +000 000 000 000"   # = hostitel.podpis v conftest.OBECNE


@pytest.fixture
def zapnuto(svet, monkeypatch):
    monkeypatch.setattr(config, "PODPIS_JEN_ZACATEK_A_KONEC", True, raising=False)
    return svet


def _navrh_text(svet):
    return svet.db.navrh(svet.telegram.navrh_id())["text"]


def _rezervace(svet, za_dni=2):
    dnes = hodiny.dnes()
    svet.smoobu.pridej_rezervaci("R1", dnes + timedelta(days=za_dni), dnes + timedelta(days=za_dni + 2))


def test_prvni_zprava_s_podpisem_dalsi_bez(zapnuto):
    svet = zapnuto
    _rezervace(svet)
    svet.smoobu.napis_host("R1", "Hi, where can we park?")
    svet.model.odpovez(text="Hi! You can park on the street.\n\nBest regards,\nRentys team")
    svet.cyklus()
    assert _navrh_text(svet) == f"Hi! You can park on the street.\n\n{PODPIS}"

    svet.telegram.klikni(svet.smoobu, svet.db, "odeslat", svet.telegram.navrh_id())
    svet.smoobu.napis_host("R1", "Is there a hairdryer?")
    svet.model.odpovez(text=f"Yes, there is one in the bathroom.\n\n{PODPIS}")
    svet.cyklus()
    assert _navrh_text(svet) == "Yes, there is one in the bathroom."


def test_po_automaticke_zprave_smoobu_bez_podpisu(zapnuto):
    svet = zapnuto
    _rezervace(svet)
    svet.smoobu.napis_my("R1", "Thank you for your booking!")   # konverzaci už zahájilo Smoobu
    svet.smoobu.napis_host("R1", "Where can we park?")
    svet.model.odpovez(text="You can park on the street.\nTest team")
    svet.cyklus()
    assert _navrh_text(svet) == "You can park on the street."


def test_zdvorilost_uprostred_konverzace_bez_podpisu(zapnuto, monkeypatch):
    monkeypatch.setattr(config, "ZDVORILOSTI_BEZ_MODELU", True)
    svet = zapnuto
    _rezervace(svet)
    svet.smoobu.napis_my("R1", "Here are the check-in details …")
    svet.smoobu.napis_host("R1", "Thank you!")
    svet.cyklus()
    text = _navrh_text(svet)
    assert "We look forward" in text and "Test team" not in text


def test_po_skonceni_pobytu_s_podpisem(zapnuto):
    svet = zapnuto
    _rezervace(svet, za_dni=-3)                      # odjezd byl včera
    svet.smoobu.napis_my("R1", "Thank you for staying with us!")
    svet.smoobu.napis_host("R1", "We forgot a charger in the room, can you check?")
    svet.model.odpovez(rozhodnuti="eskalovat", text="We will check and get back to you.", navrh="Nabíječka.")
    svet.cyklus()
    assert _navrh_text(svet) == f"We will check and get back to you.\n\n{PODPIS}"


def test_instrukce_k_prijezdu_maji_podpis_vzdy(zapnuto):
    svet = zapnuto
    _rezervace(svet, za_dni=0)                       # příjezd dnes, instrukce se připraví na 10:00
    svet.smoobu.napis_my("R1", "Thank you for your booking!")
    svet.cyklus()
    text = _navrh_text(svet)
    assert "Keybox code: 1111" in text and text.endswith(PODPIS)


def test_oprava_kodu_bez_podpisu(zapnuto):
    text, _, _ = instrukce.oprava_kodu({"guest-name": "Anna Test", "language": "en"}, "4444")
    assert "4444" in text and "Test team" not in text and text == text.strip()


@pytest.mark.parametrize("uz_jsme_psali", [False, True])
def test_text_hostitele_podpis_jen_na_zacatku(zapnuto, uz_jsme_psali):
    """✏️ Upravit: hostitelův text dostane podpis, jen když hostovi v konverzaci píšeme poprvé."""
    svet = zapnuto
    _rezervace(svet)
    if uz_jsme_psali:
        svet.smoobu.napis_my("R1", "Thank you for your booking!")
    svet.smoobu.napis_host("R1", "Can we bring a dog?")
    svet.model.odpovez(rozhodnuti="eskalovat", text="We will check and get back to you.", navrh="Pes.")
    svet.cyklus()
    puvodni = svet.db.navrh(svet.telegram.navrh_id())
    novy = svet.db.navrh(navrhy.nahradit(svet.db, puvodni, "Bohužel psi nejsou povoleni."))
    assert novy["text"].startswith("[en] Bohužel psi nejsou povoleni.")
    assert novy["text"].endswith(PODPIS) is not uz_jsme_psali


@pytest.mark.parametrize("text,ocekavane", [
    ("Hi!\n\nBest regards,\nRentys team\nFor a quicker reply you can also reach us on WhatsApp:\nSimon +000 000 000",
     "Hi!"),
    ("Hallo!\n\nViele Grüße\nRentys – Simon & Michael\nWhatsApp: +000 000 000 000", "Hallo!"),
    ("Hi!\nTest team", "Hi!"),
    ("Rentys team will contact you tomorrow about the invoice.",
     "Rentys team will contact you tomorrow about the invoice."),
    ("Hi, see you soon!", "Hi, see you soon!"),
])
def test_odstran_podpis(svet, text, ocekavane):
    assert podpis.odstran(text) == ocekavane


def test_vypnuto_beze_zmeny(svet):
    _rezervace(svet)
    svet.smoobu.napis_my("R1", "Thank you for your booking!")
    svet.smoobu.napis_host("R1", "Where can we park?")
    svet.model.odpovez(text="On the street.\nRentys team")
    svet.cyklus()
    assert _navrh_text(svet) == "On the street.\nRentys team"


def test_model_podpis_nepise(monkeypatch):
    assert "Drž se tónu a podpisu z obecných pravidel" in mozek.instrukce_zpravy()
    monkeypatch.setattr(config, "PODPIS_JEN_ZACATEK_A_KONEC", True, raising=False)
    assert "Podpis ani pozdrav na konec nepiš" in mozek.instrukce_zpravy()
