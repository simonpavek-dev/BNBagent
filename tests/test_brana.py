"""Krok P1.4: jediná brána pro zprávy hostům (agent/odchozi.py) – pojistka proti dvojímu odeslání po timeoutu."""
import pathlib
import re
from datetime import timedelta

from agent import config, hodiny, odchozi


def _navrh(svet, text="Parking is on the street."):
    dnes = hodiny.dnes()
    svet.smoobu.pridej_rezervaci("R1", dnes + timedelta(days=2), dnes + timedelta(days=4))
    svet.smoobu.napis_host("R1", "Where can we park?")
    svet.model.odpovez(text=text)
    svet.cyklus()
    return svet.telegram.navrh_id()


def test_jen_brana_posila_zpravy_hostum():
    """Pojistka: smoobu.send_message smí volat jen agent/odchozi.py."""
    volajici = [p.name for p in pathlib.Path("agent").glob("*.py")
                if p.name not in ("odchozi.py", "smoobu.py") and re.search(r"\.send_message\(", p.read_text())]
    assert volajici == [], f"zprávy hostům mimo bránu: {volajici}"


def test_timeout_po_uspesnem_odeslani_se_nezopakuje(svet):
    navrh_id = _navrh(svet)
    svet.smoobu.porucha = "timeout_po_odeslani"
    svet.telegram.klikni(svet.smoobu, svet.db, "odeslat", navrh_id)
    assert len(svet.smoobu.odeslane) == 1
    assert svet.db.navrh(navrh_id)["stav"] == "odeslano"   # brána ověřila v konverzaci, že zpráva odešla
    svet.smoobu.porucha = None
    svet.telegram.klikni(svet.smoobu, svet.db, "odeslat", navrh_id)  # druhé kliknutí
    assert len(svet.smoobu.odeslane) == 1


def test_timeout_bez_odeslani_jde_zopakovat(svet):
    navrh_id = _navrh(svet)
    svet.smoobu.porucha = "timeout_bez_odeslani"
    svet.telegram.klikni(svet.smoobu, svet.db, "odeslat", navrh_id)
    assert svet.smoobu.odeslane == []
    assert svet.db.navrh(navrh_id)["stav"] == "ceka"         # ověřeno, že neodešlo → jde poslat znovu
    assert "Neodesláno" in svet.telegram.zpravy[-1]["text"]
    svet.smoobu.porucha = None
    svet.telegram.klikni(svet.smoobu, svet.db, "odeslat", navrh_id)
    assert len(svet.smoobu.odeslane) == 1


def test_nejiste_odeslani_se_overi_v_dalsim_cyklu(svet):
    navrh_id = _navrh(svet)
    svet.smoobu.porucha = "timeout_po_odeslani"
    svet.smoobu.cteni_po_odeslani = "401"                     # po timeoutu nejde ani přečíst konverzaci
    svet.telegram.klikni(svet.smoobu, svet.db, "odeslat", navrh_id)
    assert svet.db.navrh(navrh_id)["stav"] == "nejiste"
    assert any("Nevím, jestli zpráva odešla" in z["text"] for z in svet.telegram.zpravy)
    svet.smoobu.porucha = svet.smoobu.porucha_cteni = svet.smoobu.cteni_po_odeslani = None
    hodiny.posun(minutes=3)
    svet.cyklus()
    assert svet.db.navrh(navrh_id)["stav"] == "odeslano"
    assert any("odešla" in z["text"] and "ověřeno" in z["text"].lower() for z in svet.telegram.zpravy)
    assert len(svet.smoobu.odeslane) == 1


def test_ostry_rezim_posila_pres_branu(svet, monkeypatch):
    monkeypatch.setattr(config, "REZIM", "ostre")
    dnes = hodiny.dnes()
    svet.smoobu.pridej_rezervaci("R1", dnes + timedelta(days=2), dnes + timedelta(days=4))
    svet.smoobu.napis_host("R1", "Where can we park?")
    svet.model.odpovez(text="Parking is on the street.")
    svet.cyklus()
    assert svet.smoobu.odeslane == [("R1", "Parking is on the street.")]
    stav = svet.db.conn.execute("SELECT stav FROM odchozi").fetchall()
    assert stav == [("odeslano",)]


def test_ostry_rezim_timeout_po_odeslani_bez_duplicity(svet, monkeypatch):
    monkeypatch.setattr(config, "REZIM", "ostre")
    dnes = hodiny.dnes()
    svet.smoobu.pridej_rezervaci("R1", dnes + timedelta(days=2), dnes + timedelta(days=4))
    svet.smoobu.napis_host("R1", "Where can we park?")
    svet.model.odpovez(text="Parking is on the street.")
    svet.smoobu.porucha = "timeout_po_odeslani"
    svet.cyklus()
    svet.smoobu.porucha = None
    hodiny.posun(minutes=3)
    svet.cyklus()
    assert len(svet.smoobu.odeslane) == 1


def test_pojistka_proti_zacykleni_max_4_automaticke_odpovedi_za_24_h(svet, monkeypatch):
    """B5: host a agent si nesmí donekonečna psát. Pátá automatická odpověď za 24 h jde jen ke schválení."""
    monkeypatch.setattr(config, "REZIM", "ostre")
    dnes = hodiny.dnes()
    svet.smoobu.pridej_rezervaci("R1", dnes, dnes + timedelta(days=3))
    svet.model.odpovez(text="You are welcome!")
    for i in range(5):
        svet.smoobu.napis_host("R1", f"Thanks again {i}")
        svet.cyklus()
        hodiny.posun(minutes=10)
    assert len(svet.smoobu.odeslane) == 4
    [z] = [z for z in svet.telegram.s_tlacitky() if "ZKONTROLUJ" in z["text"]]
    assert "zacykl" in z["text"]
    # po 24 hodinách od první odpovědi zase odpovídá sám
    hodiny.posun(hours=24)
    svet.smoobu.napis_host("R1", "One more question")
    svet.cyklus()
    assert len(svet.smoobu.odeslane) == 5


def test_pojistka_nepocita_instrukce_k_prijezdu(svet, monkeypatch):
    monkeypatch.setattr(config, "REZIM", "ostre")
    dnes = hodiny.dnes()
    svet.smoobu.pridej_rezervaci("R1", dnes, dnes + timedelta(days=3))
    for _ in range(4):  # automaticky odeslané instrukce / opravy kódu (návrh bez zprávy hosta)
        navrh_id = svet.db.novy_navrh("R1", "", "Hi, check-in details", "en", "hlavička")
        odchozi.odeslat(svet.smoobu, svet.db, "R1", "Hi, check-in details", "automaticky", navrh_id=navrh_id)
    svet.smoobu.napis_host("R1", "Where can we park?")
    svet.model.odpovez(text="Parking is on the street.")
    svet.cyklus()
    assert svet.smoobu.odeslane[-1] == ("R1", "Parking is on the street.")
