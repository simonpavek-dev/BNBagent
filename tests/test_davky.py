"""Víc zpráv hosta za sebou = jedna odpověď (přepínač POCKAT_NA_DALSI_ZPRAVY).

Po každé zprávě hosta agent čeká POCKAT_NA_DALSI_ZPRAVY_MINUT (5 min), jestli host nenapíše ještě něco; každá další
zpráva odpočet spustí znovu. Pak odpoví jednou zprávou na všechny. Nejdéle se čeká MAX_CEKANI_MINUT od první zprávy;
naléhavé zprávy (nouze, host se nedostane dovnitř) bez čekání. Všechna data jsou smyšlená."""
from datetime import datetime, timedelta

import pytest

from agent import config, hodiny, prace, trideni


@pytest.fixture
def davky(svet, monkeypatch):
    monkeypatch.setattr(config, "POCKAT_NA_DALSI_ZPRAVY", True)
    monkeypatch.setattr(config, "POCKAT_NA_DALSI_ZPRAVY_MINUT", 5)
    monkeypatch.setattr(config, "REZIM", "ostre")
    dnes = hodiny.dnes()
    svet.smoobu.pridej_rezervaci("R1", dnes + timedelta(days=2), dnes + timedelta(days=4))
    svet.model.odpovez(text="Hi! We look forward to it, parking is on the street.")
    return svet


def _volani(svet):
    return [v for v in svet.model.volani if v["ucel"] == "zpráva hosta"]


def _pis(svet, text, za_minut=0):
    hodiny.posun(minutes=za_minut)
    svet.smoobu.napis_host("R1", text)
    svet.cyklus()


def test_tri_zpravy_za_sebou_jedna_odpoved(davky):
    svet = davky
    _pis(svet, "Hi!")
    _pis(svet, "We will arrive around 18:00.", za_minut=2)
    _pis(svet, "Where can we park?", za_minut=2)          # 9:04
    hodiny.posun(minutes=4)                               # 9:08 – od poslední zprávy jen 4 minuty
    svet.cyklus()
    assert _volani(svet) == [] and svet.smoobu.odeslane == []
    hodiny.posun(minutes=1)                               # 9:09 – 5 minut klid
    svet.cyklus()
    [volani] = _volani(svet)
    assert all(t in volani["kontext"] for t in ("Hi!", "around 18:00", "Where can we park?"))
    assert svet.smoobu.odeslane == [("R1", "Hi! We look forward to it, parking is on the street.")]
    for m in svet.smoobu.konverzace["R1"]:
        if m["type"] == 1:
            assert svet.db.zprava_vyrizena(m["id"]), m["message"]   # vyřízené jsou všechny tři


def test_navrh_ukaze_vsechny_zpravy_hosta(davky, monkeypatch):
    svet = davky
    monkeypatch.setattr(config, "REZIM", "navrh")
    _pis(svet, "Hi!")
    _pis(svet, "Where can we park?", za_minut=1)
    hodiny.posun(minutes=5)
    svet.cyklus()
    [z] = svet.telegram.s_tlacitky()
    assert "Hi!" in z["text"] and "Where can we park?" in z["text"]


def test_dalsi_zprava_spusti_odpocet_znovu_nejdele_15_minut(davky):
    svet = davky
    for _ in range(5):                                    # host píše každé 4 minuty: 9:00, 9:04 … 9:16
        _pis(svet, "Hello? Are you there?")
        if _volani(svet):
            break
        hodiny.posun(minutes=4)
    assert len(_volani(svet)) == 1
    assert hodiny.ted() == datetime(2026, 11, 2, 9, 16)   # první cyklus po 15 minutách od první zprávy


def test_nalehava_zprava_bez_cekani(davky):
    svet = davky
    svet.model.odpovez(rozhodnuti="eskalovat", text="We are on it, calling you now.", navrh="Voda!")
    _pis(svet, "Help! Water is leaking from the ceiling!")
    assert len(_volani(svet)) == 1
    assert any("POTŘEBUJU TĚ" in z["text"] for z in svet.telegram.zpravy)


@pytest.mark.parametrize("text", [
    "Help! Water is leaking from the ceiling", "We can't get in, the code doesn't work", "There is smoke in the kitchen",
    "Nemůžeme se dostat dovnitř", "Kód nefunguje", "Wir kommen nicht rein", "Es riecht nach Gas",
    "Non riusciamo ad entrare", "No podemos entrar", "La porte ne s'ouvre pas", "Nie możemy wejść",
    "Nevieme sa dostať dnu"])
def test_nalehave_ve_vsech_jazycich(text):
    assert trideni.je_nalehava(text)


@pytest.mark.parametrize("text", ["Hi!", "Where can we park?", "Thanks a lot", "Is there a hairdryer?",
                                  "We will arrive around 18:00."])
def test_bezne_zpravy_nejsou_nalehave(text):
    assert not trideni.je_nalehava(text)


@pytest.mark.parametrize("posun_smoobu", [timedelta(hours=-2), timedelta(hours=2)])
def test_cas_ze_smoobu_v_jinem_pasmu_ceka_podle_vlastnich_hodin(davky, posun_smoobu):
    svet = davky
    m = svet.smoobu.napis_host("R1", "Where can we park?")
    m["createdAt"] = (hodiny.ted() + posun_smoobu).strftime("%Y-%m-%d %H:%M:%S")
    svet.cyklus()
    assert _volani(svet) == []                            # nečeká 0 minut ani 2 hodiny, ale 5 minut
    hodiny.posun(minutes=5)
    svet.cyklus()
    assert len(_volani(svet)) == 1


def test_agent_se_probudi_presne_po_cekani(davky):
    svet = davky
    _pis(svet, "Where can we park?")
    assert prace.konec_cekani(svet.db) == datetime(2026, 11, 2, 9, 5)
    hodiny.posun(minutes=5)
    svet.cyklus()
    assert prace.konec_cekani(svet.db) is None


def test_vypnuto_odpovida_hned(davky, monkeypatch):
    svet = davky
    monkeypatch.setattr(config, "POCKAT_NA_DALSI_ZPRAVY", False)
    _pis(svet, "Where can we park?")
    assert len(_volani(svet)) == 1
