"""Příkaz /status (PRIKAZ_STATUS): stav bytů a kódy ke dveřím, zpráva se po 15 minutách smaže.
Nedělní přehled (TYDENNI_PREHLED): kde Vasil za týden potřeboval hostitele a co doplnit do znalostní báze.
Všechna data jsou smyšlená."""
from datetime import datetime, timedelta

import pytest

from agent import config, hodiny, uklidy

NEDELE = datetime(2026, 11, 8, 19, 0)  # neděle po týdnu simulace (začíná po 2. 11. 9:00)


# ---------------------------------------------------------------- /status

@pytest.fixture
def status(svet, monkeypatch):
    monkeypatch.setattr(config, "PRIKAZ_STATUS", True)
    return svet


def _status(svet, text="/status"):
    pred = len(svet.telegram.zpravy)
    prikaz = svet.telegram.napis(svet.smoobu, svet.db, text)
    nove = svet.telegram.zpravy[pred:]
    return prikaz, nove


def test_status_obsazeny_byt_a_kody(status):
    svet = status
    svet.byt_soubor.write_text(svet.byt_soubor.read_text().replace('kod_vchod: ""', 'kod_vchod: "2468"'))
    dnes = hodiny.dnes()
    svet.smoobu.pridej_rezervaci("R1", dnes - timedelta(days=1), dnes + timedelta(days=2))
    _, [z] = _status(svet)
    assert "Testbyt – 🔴 obsazeno do 4. 11. (check-out 10:00)" in z["text"]
    assert "🚪 dům 2468" in z["text"] and "🔑 byt 1111" in z["text"]


def test_status_dnes_odjezd_a_prijezd(status):
    svet = status
    dnes = hodiny.dnes()
    svet.smoobu.pridej_rezervaci("R1", dnes - timedelta(days=2), dnes)
    svet.smoobu.pridej_rezervaci("R2", dnes, dnes + timedelta(days=3))
    _, [z] = _status(svet)
    assert "Testbyt – 🟡 dnes odjezd do 10:00, příjezd od 15:00" in z["text"]


@pytest.mark.parametrize("prijezd_za, ocekavano", [(5, "🟢 volno do 7. 11."), (None, "🟢 volno")])
def test_status_volny_byt(status, prijezd_za, ocekavano):
    svet = status
    if prijezd_za is not None:
        dnes = hodiny.dnes()
        svet.smoobu.pridej_rezervaci("R1", dnes + timedelta(days=prijezd_za), dnes + timedelta(days=prijezd_za + 2))
    _, [z] = _status(svet)
    assert f"Testbyt – {ocekavano}" in z["text"]


def test_status_v_den_uklidu_ukaze_i_kod_pred_uklidem(status, monkeypatch):
    svet = status
    monkeypatch.setattr(config, "UKLIDY_URL", "https://uklidy.test")
    monkeypatch.setattr(config, "UKLIDY_LOGIN", "test")
    monkeypatch.setattr(config, "UKLIDY_HESLO", "test")
    dnes = hodiny.dnes()
    data = [{"stay": {"id": "u1", "checkOut": str(dnes - timedelta(days=3)), "cleaningDate": str(dnes - timedelta(days=3)),
                      "codes": "3333", "uklidStatus": "uklizeno"}, "apartment": {"name": "Testbyt 1"}},
            {"stay": {"id": "u2", "checkOut": str(dnes), "cleaningDate": str(dnes), "codes": "4444",
                      "uklidStatus": None}, "apartment": {"name": "Testbyt 1"}}]
    monkeypatch.setattr(uklidy, "_stahni", lambda: list(data))
    uklidy._cache.update(cas=0.0, pobyty=None)
    _, [z] = _status(svet)
    assert "🔑 byt 3333 (po dnešním úklidu 4444)" in z["text"]


def test_status_se_po_15_minutach_smaze_i_s_prikazem(status):
    svet = status
    prikaz, [z] = _status(svet, "/status@Vasilbnb_bot")
    assert "smaže" in z["text"]
    hodiny.posun(minutes=14)
    svet.cyklus()
    assert svet.telegram.smazane == []
    hodiny.posun(minutes=1)
    svet.cyklus()
    assert sorted(svet.telegram.smazane) == sorted([prikaz, z["id"]])
    hodiny.posun(minutes=3)
    svet.cyklus()
    assert len(svet.telegram.smazane) == 2  # jen jednou


def test_status_smazani_pri_vypadku_telegramu_zkusi_znovu(status):
    svet = status
    prikaz, [z] = _status(svet)
    hodiny.posun(minutes=15)
    svet.telegram.vypadek = True
    svet.cyklus()
    svet.telegram.vypadek = False
    hodiny.posun(minutes=3)
    svet.cyklus()
    assert sorted(svet.telegram.smazane) == sorted([prikaz, z["id"]])


def test_status_jen_ve_skupine_hostitelu(status):
    svet = status
    pred = len(svet.telegram.zpravy)
    svet.telegram.napis(svet.smoobu, svet.db, "/status", chat=-999)
    assert len(svet.telegram.zpravy) == pred


def test_status_vypnuty(svet):
    _, [z] = _status(svet)
    assert "vypnut" in z["text"] and "1111" not in z["text"]


def test_prikaz_behem_upravy_navrhu_neni_text_pro_hosta(status):
    svet = status
    dnes = hodiny.dnes()
    svet.smoobu.pridej_rezervaci("R1", dnes + timedelta(days=2), dnes + timedelta(days=4))
    svet.smoobu.napis_host("R1", "Where can we park?")
    svet.model.odpovez(text="Parking is on the street.")
    svet.cyklus()
    navrh_id = svet.telegram.navrh_id()
    svet.telegram.klikni(svet.smoobu, svet.db, "upravit", navrh_id)
    _, nove = _status(svet)
    assert svet.db.navrh(navrh_id)["stav"] == "ceka"            # návrh zůstal, /status ho nenahradil
    assert any("🔑 byt" in z["text"] for z in nove)


# ---------------------------------------------------------------- nedělní přehled

@pytest.fixture
def prehled(svet, monkeypatch):
    monkeypatch.setattr(config, "TYDENNI_PREHLED", True)
    monkeypatch.setattr(config, "TYDENNI_PREHLED_HODINA", 19)
    svet.model.odpovedi["týdenní přehled"] = {
        "doporuceni": [{"byt": "Testbyt", "co_doplnit": "Jestli je k dispozici dětská postýlka.",
                        "proc": "Ptali se na ni 2 hosté.", "veta_pro_vasila": "Vasile, do Testbytu doplň: postýlka je ve skříni."}],
        "nechat_na_hostitelich": ["Slevy"], "shrnuti": "Klidný týden."}
    return svet


def _eskalace(svet, rid, text, duvod):
    dnes = hodiny.dnes()
    svet.smoobu.pridej_rezervaci(rid, dnes + timedelta(days=10), dnes + timedelta(days=12))
    svet.smoobu.napis_host(rid, text)
    svet.model.odpovez(rozhodnuti="eskalovat", text="We will check and get back to you.", navrh=duvod)
    svet.model.odpovedi["zpráva hosta"]["duvod"] = duvod
    svet.cyklus()


def _prehledy(svet):
    return [z for z in svet.telegram.zpravy if "TÝDENNÍ PŘEHLED" in z["text"]]


def test_nedelni_prehled_s_pripady_a_doporucenim(prehled):
    svet = prehled
    hodiny.zmraz(datetime(2026, 10, 30, 10, 0))                  # 9 dní před nedělí – do přehledu nepatří
    svet.db.zapis("STARA", "rozhodnuti", {"rozhodnuti": "eskalovat", "hlavicka": "Testbyt · Starý Host",
                                          "zprava_hosta": "Old question about a crib", "duvod": "staré"})
    hodiny.zmraz(datetime(2026, 11, 3, 10, 0))
    _eskalace(svet, "R1", "Do you have a baby crib?", "Ve znalostní bázi není postýlka.")
    hodiny.zmraz(datetime(2026, 11, 5, 15, 0))
    _eskalace(svet, "R2", "Can we get a discount?", "Sleva – vždy na hostitelích.")
    hodiny.zmraz(NEDELE - timedelta(minutes=10))
    svet.cyklus()
    assert _prehledy(svet) == []                                   # ještě není 19:00
    hodiny.zmraz(NEDELE)
    svet.cyklus()
    [z] = _prehledy(svet)
    for co in ("Do you have a baby crib?", "Can we get a discount?", "Ve znalostní bázi není postýlka.",
               "Vasile, do Testbytu doplň: postýlka je ve skříni.", "Slevy"):
        assert co in z["text"], co
    assert "Old question" not in z["text"]
    [volani] = [v for v in svet.model.volani if v["ucel"] == "týdenní přehled"]
    assert "Do you have a baby crib?" in volani["kontext"] and "Old question" not in volani["kontext"]
    hodiny.posun(minutes=30)
    svet.cyklus()
    assert len(_prehledy(svet)) == 1                               # jen jednou za neděli


def test_prehled_jen_v_nedeli(prehled):
    svet = prehled
    hodiny.zmraz(NEDELE - timedelta(days=1))                       # sobota 19:00
    svet.cyklus()
    assert _prehledy(svet) == []


def test_prehled_bez_modelu_prijde_i_tak(prehled):
    svet = prehled
    hodiny.zmraz(datetime(2026, 11, 3, 10, 0))
    _eskalace(svet, "R1", "Do you have a baby crib?", "Ve znalostní bázi není postýlka.")

    def model_nejde(kontext):
        raise RuntimeError("401 invalid x-api-key")
    svet.model.odpovedi["týdenní přehled"] = model_nejde
    hodiny.zmraz(NEDELE)
    svet.cyklus()
    [z] = _prehledy(svet)
    assert "Do you have a baby crib?" in z["text"] and "doporučení" in z["text"].lower()


def test_prehled_klidny_tyden_bez_modelu(prehled):
    svet = prehled
    hodiny.zmraz(NEDELE)
    svet.cyklus()
    [z] = _prehledy(svet)
    assert "nepotřeboval" in z["text"]
    assert [v for v in svet.model.volani if v["ucel"] == "týdenní přehled"] == []


def test_prikaz_prehled_kdykoli(prehled):
    svet = prehled
    hodiny.zmraz(datetime(2026, 11, 4, 10, 0))
    _eskalace(svet, "R1", "Do you have a baby crib?", "Ve znalostní bázi není postýlka.")
    svet.telegram.napis(svet.smoobu, svet.db, "/prehled")
    [z] = _prehledy(svet)
    assert "Do you have a baby crib?" in z["text"]


def test_prehled_vypnuty(svet):
    hodiny.zmraz(NEDELE)
    svet.cyklus()
    assert _prehledy(svet) == []
