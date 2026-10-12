"""Opravené známé chyby (dřív xfail) a varianta B pro kód keyboxu (DECISIONS.md D3)."""
from datetime import datetime, timedelta

import pytest

from agent import config, hodiny, uklidy


def _rezervace(svet, rid="R1", za_dni=3, delka=2, **kw):
    dnes = hodiny.dnes()
    return svet.smoobu.pridej_rezervaci(rid, dnes + timedelta(days=za_dni), dnes + timedelta(days=za_dni + delka), **kw)


# ---------------------------------------------------------------- chyba 1: dotaz přebitý automatickou zprávou

def test_dotaz_hosta_a_po_nem_automaticka_zprava_smoobu(svet):
    _rezervace(svet)
    svet.smoobu.napis_host("R1", "Is there a hairdryer in the apartment?")
    svet.smoobu.napis_my("R1", "Hi! Your stay is coming up soon … (automatická zpráva Smoobu)")
    svet.model.odpovez(text="Yes, there is a hairdryer in the bathroom.")
    svet.cyklus()
    assert any(v["ucel"] == "zpráva hosta" for v in svet.model.volani), "dotaz hosta nikdo nezpracoval"
    assert svet.telegram.s_tlacitky(), "hostitelé nedostali návrh odpovědi"


def test_stare_dotazy_z_doby_pred_nasazenim_se_nevytahnou(svet):
    hodiny.zmraz(datetime(2026, 11, 1, 20, 0))       # den před nasazením opravy
    _rezervace(svet)
    svet.smoobu.napis_host("R1", "Is there a hairdryer?")
    svet.smoobu.napis_my("R1", "Yes, in the bathroom.")
    hodiny.zmraz(datetime(2026, 11, 2, 9, 0))        # nasazení – první cyklus nové verze
    svet.model.odpovez(text="(nemělo by se volat)")
    svet.cyklus()
    assert svet.model.volani == []


def test_navrh_po_automaticke_zprave_jde_schvalit(svet):
    _rezervace(svet)
    svet.smoobu.napis_host("R1", "Is there a hairdryer in the apartment?")
    svet.smoobu.napis_my("R1", "Hi! Your stay is coming up soon … (automatická zpráva Smoobu)")
    svet.model.odpovez(text="Yes, there is a hairdryer in the bathroom.")
    svet.cyklus()
    hodiny.posun(minutes=5)
    svet.telegram.klikni(svet.smoobu, svet.db, "odeslat", svet.telegram.navrh_id())
    assert svet.smoobu.odeslane == [("R1", "Yes, there is a hairdryer in the bathroom.")]


def test_navrh_je_zastaraly_kdyz_mezitim_odpovedel_hostitel(svet):
    _rezervace(svet)
    svet.smoobu.napis_host("R1", "Is there a hairdryer in the apartment?")
    svet.model.odpovez(text="Yes, there is a hairdryer in the bathroom.")
    svet.cyklus()
    navrh_id = svet.telegram.navrh_id()
    hodiny.posun(minutes=5)
    svet.smoobu.napis_my("R1", "Yes, it's in the bathroom drawer.")   # hostitel odpověděl ručně po vzniku návrhu
    svet.telegram.klikni(svet.smoobu, svet.db, "odeslat", navrh_id)
    assert svet.smoobu.odeslane == []
    assert svet.db.navrh(navrh_id)["stav"] == "zastarale"


# ---------------------------------------------------------------- chyba 2: upozornění při výpadku Telegramu

def test_eskalace_pri_vypadku_telegramu_se_neztrati(svet):
    _rezervace(svet)
    svet.smoobu.napis_host("R1", "Can we get a discount for a longer stay?")
    svet.model.odpovez(rozhodnuti="eskalovat", text="We'll check and get back to you.", navrh="Sleva – rozhodni.")
    svet.telegram.vypadek = True
    svet.cyklus()                      # Telegram nejde
    svet.telegram.vypadek = False
    hodiny.posun(minutes=3)
    svet.cyklus()                      # Telegram zase jde – eskalace musí dorazit
    assert any("POTŘEBUJU TĚ" in z["text"] for z in svet.telegram.zpravy), "eskalace se ztratila"
    assert any("Zpožděné upozornění" in z["text"] for z in svet.telegram.zpravy)


def test_navrh_doruceny_z_fronty_ma_funkcni_tlacitka(svet):
    _rezervace(svet)
    svet.smoobu.napis_host("R1", "Where can we park?")
    svet.model.odpovez(text="Parking is on the street.")
    svet.telegram.vypadek = True
    svet.cyklus()
    svet.telegram.vypadek = False
    hodiny.posun(minutes=3)
    svet.cyklus()
    navrh_id = svet.telegram.navrh_id()
    assert svet.db.navrh(navrh_id)["tg_message_id"]          # zpráva s tlačítky je doručená a spárovaná s návrhem
    svet.telegram.klikni(svet.smoobu, svet.db, "odeslat", navrh_id)
    assert svet.smoobu.odeslane == [("R1", "Parking is on the street.")]


# ---------------------------------------------------------------- chyba 3 / D3 varianta B: oprava kódu

@pytest.fixture
def uklidy_zapnute(svet, monkeypatch):
    monkeypatch.setattr(config, "OPRAVA_KODU_PO_UKLIDU", True, raising=False)
    monkeypatch.setattr(config, "UKLIDY_URL", "https://uklidy.test")
    monkeypatch.setattr(config, "UKLIDY_LOGIN", "test")
    monkeypatch.setattr(config, "UKLIDY_HESLO", "test")
    data = []
    monkeypatch.setattr(uklidy, "_stahni", lambda: list(data))
    svet.uklidy_data = data
    return svet


def _uklid(svet, den, kod, uklizeno=True, uid=None):
    svet.uklidy_data.append({"stay": {"id": uid or f"u{den}", "checkOut": str(den), "cleaningDate": str(den),
                                      "codes": kod, "uklidStatus": "uklizeno" if uklizeno else None},
                             "apartment": {"name": "Testbyt 1"}})
    uklidy._cache.update(cas=0.0, pobyty=None)


def _host_s_instrukcemi(svet, rid, prijezd, kod):
    svet.smoobu.pridej_rezervaci(rid, prijezd, prijezd + timedelta(days=2), host=f"Host {rid}")
    svet.smoobu.napis_my(rid, f"Hi! … Keybox code: {kod} …")          # instrukce už odešly
    svet.db.uloz_nastaveni(f"prijezd_{rid}", "hotovo")
    svet.db.zapis(rid, "instrukce_prijezd", {"kod": kod, "smoobu_id": "100"})


def test_po_zmene_kodu_dostane_host_s_instrukcemi_opravu(uklidy_zapnute, monkeypatch):
    svet = uklidy_zapnute
    monkeypatch.setattr(config, "PRIJEZDY_AUTOMATICKY", True)
    dnes = hodiny.dnes()
    _uklid(svet, dnes - timedelta(days=1), "3333")
    _host_s_instrukcemi(svet, "ZITRA", dnes + timedelta(days=1), "3333")
    svet.cyklus()                                  # dnes: platí 3333
    assert svet.smoobu.odeslane == []
    hodiny.posun(days=1, hours=3)                  # zítra 12:00 – po úklidu je nový kód 4444
    _uklid(svet, dnes + timedelta(days=1), "4444")
    svet.cyklus()
    [(rid, text)] = svet.smoobu.odeslane
    assert rid == "ZITRA" and "4444" in text and "3333" not in text
    assert any("4444" in z["text"] and "oprav" in z["text"].lower() for z in svet.telegram.zpravy)


def test_oprava_kodu_ke_schvaleni_kdyz_instrukce_nejsou_automaticke(uklidy_zapnute, monkeypatch):
    svet = uklidy_zapnute
    monkeypatch.setattr(config, "PRIJEZDY_AUTOMATICKY", False)
    dnes = hodiny.dnes()
    _uklid(svet, dnes - timedelta(days=1), "3333")
    _host_s_instrukcemi(svet, "ZITRA", dnes + timedelta(days=1), "3333")
    svet.cyklus()
    hodiny.posun(days=1, hours=3)
    _uklid(svet, dnes + timedelta(days=1), "4444")
    svet.cyklus()
    assert svet.smoobu.odeslane == []
    assert any("4444" in z["text"] for z in svet.telegram.s_tlacitky())


def test_oprava_jen_pro_hosty_po_uklidu_a_s_instrukcemi(uklidy_zapnute, monkeypatch):
    svet = uklidy_zapnute
    monkeypatch.setattr(config, "PRIJEZDY_AUTOMATICKY", True)
    dnes = hodiny.dnes()
    _uklid(svet, dnes - timedelta(days=1), "3333")
    _host_s_instrukcemi(svet, "TED", dnes - timedelta(days=1), "3333")       # bydlí tam už před úklidem
    svet.smoobu.pridej_rezervaci("BEZ", dnes + timedelta(days=1), dnes + timedelta(days=2))  # instrukce ještě nemá
    svet.db.uloz_nastaveni("prijezd_BEZ", "hotovo")
    svet.cyklus()
    hodiny.posun(hours=3)
    _uklid(svet, dnes, "4444", uid="dnes")
    svet.cyklus()
    assert svet.smoobu.odeslane == []
