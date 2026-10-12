"""Charakterizační testy: zafixují dnešní chování agenta, než ho začneme měnit."""
from datetime import timedelta

from agent import hodiny


def _rezervace_s_dotazem(svet, za_dni=2):
    dnes = hodiny.dnes()
    svet.smoobu.pridej_rezervaci("R1", dnes + timedelta(days=za_dni), dnes + timedelta(days=za_dni + 3))
    svet.smoobu.napis_host("R1", "Where can we park?")


def test_nova_zprava_vytvori_navrh_v_telegramu(svet):
    _rezervace_s_dotazem(svet)
    svet.model.odpovez(text="Parking is on the street, use the EasyPark app.")
    svet.cyklus()
    assert svet.smoobu.odeslane == []  # v režimu návrhů hostovi nic neodejde
    [navrh] = svet.telegram.s_tlacitky()
    assert "NÁVRH ODPOVĚDI" in navrh["text"] and "EasyPark" in navrh["text"]
    assert [t for t, _ in navrh["tlacitka"]] == ["✅ Odeslat", "✏️ Upravit", "❌ Neposílat"]


def test_schvaleni_odesle_hostovi(svet):
    _rezervace_s_dotazem(svet)
    svet.model.odpovez(text="Parking is on the street.")
    svet.cyklus()
    svet.telegram.klikni(svet.smoobu, svet.db, "odeslat", svet.telegram.navrh_id())
    assert svet.smoobu.odeslane == [("R1", "Parking is on the street.")]
    assert svet.telegram.zpravy[-1]["text"].startswith("✅ Odesláno hostovi")


def test_host_mezitim_napsal_neodeslano(svet):
    _rezervace_s_dotazem(svet)
    svet.model.odpovez(text="Parking is on the street.")
    svet.cyklus()
    navrh_id = svet.telegram.navrh_id()
    svet.smoobu.napis_host("R1", "Also, can we check in early?")
    svet.telegram.klikni(svet.smoobu, svet.db, "odeslat", navrh_id)
    assert svet.smoobu.odeslane == []
    assert svet.db.navrh(navrh_id)["stav"] == "zastarale"
    assert "Neodesláno – mezitím host napsal další zprávu" in svet.telegram.zpravy[-1]["text"]


def test_instrukce_se_zmenenym_kodem_neodeslano(svet):
    hodiny.posun(hours=2)  # 11:00 – plánované odeslání v 10:00 už minulo, po schválení se posílá hned
    dnes = hodiny.dnes()
    svet.smoobu.pridej_rezervaci("R2", dnes, dnes + timedelta(days=2))
    svet.cyklus()  # agent připraví instrukce k dnešnímu příjezdu
    navrh_id = svet.telegram.navrh_id()
    assert "1111" in svet.db.navrh(navrh_id)["text"]
    svet.nastav_kod("2222", dnes.isoformat())  # hostitel mezitím kód změnil a ověřil
    svet.telegram.klikni(svet.smoobu, svet.db, "odeslat", navrh_id)
    assert svet.smoobu.odeslane == []
    assert svet.db.navrh(navrh_id)["stav"] == "zastarale"
    assert any("Kód keyboxu se mezitím změnil (1111 → 2222)" in z["text"] for z in svet.telegram.zpravy)


def test_401_pri_cteni_hned_upozorni_hostitele(svet):
    from agent import prace
    _rezervace_s_dotazem(svet)
    svet.smoobu.pri_odmitnuti = lambda chyba: prace.upozorni_na_odmitnuti(svet.db, chyba)
    svet.smoobu.porucha_cteni = "401"
    try:
        svet.cyklus()
    except Exception:
        pass  # smyčka chybu cyklu zaloguje a pokračuje
    assert any("Smoobu odmítá ověření" in z["text"] for z in svet.telegram.zpravy)


def test_timeout_po_odeslani_dnes_necha_navrh_cekat(svet):
    """Charakterizace dnešního chování: zpráva odejde, klient dostane timeout a návrh zůstane „čeká“
    (opakované kliknutí by ji poslalo podruhé – kandidát na opravu v kroku brány P1.4)."""
    import pytest
    import requests
    _rezervace_s_dotazem(svet)
    svet.model.odpovez(text="Parking is on the street.")
    svet.cyklus()
    navrh_id = svet.telegram.navrh_id()
    svet.smoobu.porucha = "timeout_po_odeslani"
    with pytest.raises(requests.Timeout):
        svet.telegram.klikni(svet.smoobu, svet.db, "odeslat", navrh_id)
    assert len(svet.smoobu.odeslane) == 1
    assert svet.db.navrh(navrh_id)["stav"] == "ceka"


def test_naplanovane_instrukce_odejdou_az_v_10(svet, monkeypatch):
    """Hodiny: v 9:00 se instrukce po schválení jen naplánují, odejdou až v cyklu po 10:00."""
    from agent import config
    monkeypatch.setattr(config, "PRIJEZDY_AUTOMATICKY", True)
    dnes = hodiny.dnes()
    svet.smoobu.pridej_rezervaci("R3", dnes, dnes + timedelta(days=1))
    svet.cyklus()                       # 9:00 – připraví a naplánuje na 10:00
    assert svet.smoobu.odeslane == []
    hodiny.posun(minutes=59)
    svet.cyklus()                       # 9:59 – pořád nic
    assert svet.smoobu.odeslane == []
    hodiny.posun(minutes=2)
    svet.cyklus()                       # 10:01 – odešlo
    assert [rid for rid, _ in svet.smoobu.odeslane] == ["R3"]
