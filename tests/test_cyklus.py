"""Charakterizační testy: zafixují dnešní chování agenta, než ho začneme měnit."""
from datetime import timedelta

from agent import config, kontext, prace


def _rezervace_s_dotazem(svet, za_dni=2):
    dnes = kontext.dnes()
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


def test_instrukce_se_zmenenym_kodem_neodeslano(svet, monkeypatch):
    monkeypatch.setattr(config, "PRIJEZD_ODESLAT_HODINA", 0)  # čas odeslání už minul → po schválení hned
    dnes = kontext.dnes()
    svet.smoobu.pridej_rezervaci("R2", dnes, dnes + timedelta(days=2))
    prace.priprav_prijezdy(svet.smoobu, svet.db)
    navrh_id = svet.telegram.navrh_id()
    assert "1111" in svet.db.navrh(navrh_id)["text"]
    svet.nastav_kod("2222", (dnes - timedelta(days=0)).isoformat())  # hostitel mezitím kód změnil
    svet.telegram.klikni(svet.smoobu, svet.db, "odeslat", navrh_id)
    assert svet.smoobu.odeslane == []
    assert svet.db.navrh(navrh_id)["stav"] == "zastarale"
    assert any("Kód keyboxu se mezitím změnil (1111 → 2222)" in z["text"] for z in svet.telegram.zpravy)
