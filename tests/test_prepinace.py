"""D2 (varianta A): existující funkce mají přepínač v .env, výchozí vypnuto, popsaný v .env.example."""
import pathlib
import re
from datetime import timedelta

import pytest

from agent import config, hodiny, spravce, telegram_ovladani, uklidy

PREPINACE = ["KONTROLA_KALENDARE", "NABIDKA_DRIVEJSIHO_CHECKINU", "HLIDANI_UKLIDU_K_PRIJEZDU",
             "OPRAVA_KODU_PO_UKLIDU", "CHAT_PRES_TELEGRAM", "HODNOCENI_HOSTU",
             "ZDVORILOSTI_BEZ_MODELU", "LEVNEJSI_MODEL_PRO_JEDNODUCHE", "INSTRUKCE_ZE_SABLONY", "PRIJEZDY_AUTOMATICKY"]


@pytest.mark.parametrize("nazev", PREPINACE)
def test_prepinac_vychozi_vypnuto_a_popsany(nazev):
    zdroj = pathlib.Path("agent/config.py").read_text()
    assert re.search(rf'os\.getenv\("{nazev}", "ne"\)', zdroj), f"{nazev}: výchozí hodnota v config.py musí být ne"
    assert re.search(rf"^{nazev}=ne$", pathlib.Path(".env.example").read_text(), re.M), f"{nazev} chybí v .env.example"
    assert getattr(config, nazev) is False  # conftest ho v testech vypíná


# ---------------------------------------------------------------- jednotlivé funkce

@pytest.mark.parametrize("zapnuto", [False, True])
def test_kontrola_kalendare(svet, monkeypatch, zapnuto):
    monkeypatch.setattr(config, "KONTROLA_KALENDARE", zapnuto)
    svet.cyklus()
    assert bool(svet.db.nastaveni("kontrola_kalendare")) is zapnuto


@pytest.fixture
def s_uklidy(svet, monkeypatch):
    monkeypatch.setattr(config, "UKLIDY_URL", "https://uklidy.test")
    monkeypatch.setattr(config, "UKLIDY_LOGIN", "test")
    monkeypatch.setattr(config, "UKLIDY_HESLO", "test")
    svet.uklidy_data = []
    monkeypatch.setattr(uklidy, "_stahni", lambda: list(svet.uklidy_data))
    return svet


def _uklid(svet, den, kod, uklizeno):
    svet.uklidy_data.append({"stay": {"id": f"u{den}{kod}", "checkOut": str(den), "cleaningDate": str(den), "codes": kod,
                                      "uklidStatus": "uklizeno" if uklizeno else None}, "apartment": {"name": "Testbyt 1"}})
    uklidy._cache.update(cas=0.0, pobyty=None)


@pytest.mark.parametrize("zapnuto", [False, True])
def test_nabidka_drivejsiho_checkinu(s_uklidy, monkeypatch, zapnuto):
    monkeypatch.setattr(config, "NABIDKA_DRIVEJSIHO_CHECKINU", zapnuto)
    dnes = hodiny.dnes()
    _uklid(s_uklidy, dnes, None, uklizeno=True)
    s_uklidy.smoobu.pridej_rezervaci("R1", dnes, dnes + timedelta(days=2))
    s_uklidy.smoobu.napis_my("R1", "Hi! Keybox code: 1111")       # instrukce už má
    s_uklidy.db.uloz_nastaveni("prijezd_R1", "hotovo")
    hodiny.posun(hours=3)                                          # 12:00
    s_uklidy.cyklus()
    assert any("UKLIZENÝ DŘÍV" in z["text"] for z in s_uklidy.telegram.zpravy) is zapnuto


@pytest.mark.parametrize("zapnuto", [False, True])
def test_hlidani_uklidu_k_prijezdu(s_uklidy, monkeypatch, zapnuto):
    monkeypatch.setattr(config, "HLIDANI_UKLIDU_K_PRIJEZDU", zapnuto)
    dnes = hodiny.dnes()
    _uklid(s_uklidy, dnes, None, uklizeno=False)
    s_uklidy.smoobu.pridej_rezervaci("R1", dnes, dnes + timedelta(days=2))
    s_uklidy.db.uloz_nastaveni("prijezd_R1", "hotovo")
    hodiny.posun(hours=5, minutes=30)                              # 14:30
    s_uklidy.cyklus()
    assert any("není uklizený" in z["text"] for z in s_uklidy.telegram.zpravy) is zapnuto


@pytest.mark.parametrize("zapnuto", [False, True])
def test_oprava_kodu_po_uklidu(s_uklidy, monkeypatch, zapnuto):
    monkeypatch.setattr(config, "OPRAVA_KODU_PO_UKLIDU", zapnuto)
    monkeypatch.setattr(config, "PRIJEZDY_AUTOMATICKY", True)
    dnes = hodiny.dnes()
    _uklid(s_uklidy, dnes - timedelta(days=1), "3333", uklizeno=True)
    s_uklidy.smoobu.pridej_rezervaci("Z", dnes + timedelta(days=1), dnes + timedelta(days=3))
    s_uklidy.smoobu.napis_my("Z", "Hi! Keybox code: 3333")
    s_uklidy.db.uloz_nastaveni("prijezd_Z", "hotovo")
    s_uklidy.db.zapis("Z", "instrukce_prijezd", {"kod": "3333", "smoobu_id": "100"})
    s_uklidy.cyklus()
    hodiny.posun(days=1, hours=3)
    _uklid(s_uklidy, dnes + timedelta(days=1), "4444", uklizeno=True)
    s_uklidy.cyklus()
    assert any("4444" in text for _, text in s_uklidy.smoobu.odeslane) is zapnuto


@pytest.mark.parametrize("zapnuto", [False, True])
def test_chat_pres_telegram(svet, monkeypatch, zapnuto):
    monkeypatch.setattr(config, "CHAT_PRES_TELEGRAM", zapnuto)
    dotazy = []
    monkeypatch.setattr(spravce, "odpovez", lambda db, text: dotazy.append(text) or "Odpověď")
    telegram_ovladani._zprava(svet.db, {"chat": {"id": svet.telegram.CHAT, "type": "group"},
                                        "from": {"id": 1, "first_name": "Tester"}, "text": "Vasile, jaké máš kódy?",
                                        "message_id": 5})
    assert bool(dotazy) is zapnuto
