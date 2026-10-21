"""Testy nikdy nesmí sáhnout na skutečné Smoobu, Telegram ani Claude: smyšlené klíče a zákaz sítě."""
from datetime import datetime

import pytest
import requests

from agent import config


@pytest.fixture(autouse=True)
def bez_skutecnych_sluzeb(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "SMOOBU_API_KEY", "usr_live_abc123")
    monkeypatch.setattr(config, "SMOOBU_API_SECRET", "your_api_secret")
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "")
    monkeypatch.setattr(config, "UKLIDY_HESLO", "")
    # přepínače a režimy na výchozí hodnoty – testy nesmí záviset na tom, co je zapnuté ve skutečném .env
    for prepinac in ("ZDVORILOSTI_BEZ_MODELU", "LEVNEJSI_MODEL_PRO_JEDNODUCHE", "PRIJEZDY_AUTOMATICKY",
                     "KONTROLA_KALENDARE", "NABIDKA_DRIVEJSIHO_CHECKINU",
                     "HLIDANI_UKLIDU_K_PRIJEZDU", "OPRAVA_KODU_PO_UKLIDU", "CHAT_PRES_TELEGRAM", "HODNOCENI_HOSTU"):
        monkeypatch.setattr(config, prepinac, False, raising=False)
    monkeypatch.setattr(config, "REZIM", "navrh")
    monkeypatch.setattr(config, "MODEL", "claude-opus-5")
    monkeypatch.setattr(config, "MODEL_JEDNODUCHE", "claude-sonnet-5")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "agent.db")
    monkeypatch.setattr(config, "LOG_PATH", tmp_path / "agent.log")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")

    def zadna_sit(*args, **kwargs):
        raise AssertionError("Test se pokusil o skutečný síťový požadavek")
    monkeypatch.setattr(requests.Session, "request", zadna_sit)
    monkeypatch.setattr(requests, "post", zadna_sit)
    monkeypatch.setattr(requests, "get", zadna_sit)


# ---------------------------------------------------------------- simulovaný svět pro testy cyklu

OBECNE = """hostitel:
  podpis: |
    Test team
    WhatsApp: +000 000 000 000
vzdy_eskalovat:
  - Slevy
sablona_zpravy_k_prijezdu: |
  Hi {jmeno},

  welcome to Prague! Here are your check-in details for {adresa}{budova}. Self check-in is possible from {check_in}.

  {postup}

  Wi-Fi: network {wifi_sit} / password {wifi_heslo}

  Check-out is by {check_out} - {odjezd_postup}

  {podpis}
"""

BYT = """smoobu_id: "100"
nazev: "Testbyt"
uklidy_nazev: "Testbyt 1"
adresa: "Testovací 1, Praha, byt č. 7"
adresa_presna: "Testovací 1, Praha 9"
adresa_doplnek_en: "apartment no. 7"
prijezd:
  check_in_od: "15:00"
  postup: "Keybox vlevo od dveří."
  postup_en: "The keybox is to the left of the door. Keybox code: [KÓD BYTU]"
  kod_vchod: ""
  keybox_kod: "{kod}"
  keybox_kod_overeno: "{overeno}"
  kody_sdelit_nejdrive_dni_pred_prijezdem: 0
odjezd:
  check_out_do: "10:00"
  postup_en: "please put the keys back into the keybox."
wifi:
  sit: "{wifi_sit}"
  heslo: "test-heslo"
"""


ZACATEK = datetime(2026, 11, 2, 9, 0)  # pondělí 9:00 – výchozí zmrazený čas simulace


class Svet:
    def __init__(self, monkeypatch, tmp_path):
        from agent import hodiny, prace, uklidy, znalosti
        from agent.databaze import Databaze
        from nahrazky import FakeModel, FakeSmoobu, FakeTelegram

        kb = tmp_path / "znalostni-baze"
        (kb / "apartmany").mkdir(parents=True)
        (kb / "obecne.yaml").write_text(OBECNE, encoding="utf-8")
        self.byt_soubor = kb / "apartmany" / "testbyt.yaml"
        self.nastav_kod("1111", "2026-01-01")
        monkeypatch.setattr(config, "ZNALOSTI_DIR", kb)
        monkeypatch.setattr(znalosti, "APARTMANY_DIR", kb / "apartmany")
        monkeypatch.setattr(prace, "POZNAMKY_PATH", tmp_path / "poznamky.yaml")
        monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", str(FakeTelegram.CHAT))
        monkeypatch.setattr(config, "REZIM", "navrh")
        monkeypatch.setattr(config, "PRIJEZDY_AUTOMATICKY", False)
        monkeypatch.setattr(config, "HODNOCENI_HOSTU", False)

        hodiny.zmraz(ZACATEK)
        uklidy._cache.update(cas=0.0, pobyty=None)
        self.smoobu = FakeSmoobu()
        self.telegram = FakeTelegram(monkeypatch)
        self.model = FakeModel(monkeypatch)
        self.db = Databaze()
        monkeypatch.setattr(prace, "vytvor_smoobu", lambda: self.smoobu)

    def nastav_kod(self, kod, overeno, wifi_sit="TestNet"):
        self.byt_soubor.write_text(BYT.format(kod=kod, overeno=overeno, wifi_sit=wifi_sit), encoding="utf-8")

    def cyklus(self):
        """Jeden celý průchod agenta (__main__.jeden_cyklus) nad náhražkami."""
        from agent import __main__ as cli
        return cli.jeden_cyklus(self.smoobu, self.db)


@pytest.fixture
def svet(monkeypatch, tmp_path):
    from agent import hodiny
    yield Svet(monkeypatch, tmp_path)
    hodiny.rozmraz()
