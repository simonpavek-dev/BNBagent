"""Smoobu: jen HMAC, RFC 3986 v podpisu, 401 = okamžité upozornění, 429 = čekání jen u GET.
Všechny klíče jsou smyšlené (příklad z docs.smoobu.com, sekce HMAC)."""
import json
import time
from email.utils import formatdate

import pytest

from agent import __main__ as cli, config, oznameni, prace, smoobu
from agent.databaze import Databaze

KLIC, SECRET, CAS = "usr_live_abc123", "your_api_secret", "2026-04-01T12:00:00Z"


# ---------------------------------------------------------------- podpis podle dokumentace

def test_podpis_post_podle_dokumentace():
    # referenční hodnota spočítaná přesně příkazem z dokumentace (echo -en "$CANONICAL" | openssl dgst -sha256 -hmac …)
    telo = b'{"apartmentId":123,"from":"2026-04-01","to":"2026-04-10"}'
    assert smoobu.podpis("POST", "/api/reservations", "", CAS, "550e8400-e29b-41d4-a716-446655440000",
                         telo, KLIC, SECRET) == "64zVmuaX7u9BPPU7J8ruvr5rzoaCcpZtYgFoKGJOdig="


def test_podpis_get_s_parametry_podle_dokumentace():
    query = smoobu.query_rfc3986({"to": "2026-04-10", "from": "2026-04-01"})
    assert query == "from=2026-04-01&to=2026-04-10"  # seřazeno abecedně
    assert smoobu.podpis("GET", "/api/reservations", query, CAS, "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
                         b"", KLIC, SECRET) == "Bu2/61pneyRyjQejH7PoCJC2P8iRm3NnC9R6CGFOQho="


def test_query_rfc3986_mezera_a_hranate_zavorky():
    query = smoobu.query_rfc3986({"start_date": "2026-04-01", "apartments[]": 3529986, "note": "a b",
                                  "end_date": "2026-04-10"})
    assert query == "apartments%5B%5D=3529986&end_date=2026-04-10&note=a%20b&start_date=2026-04-01"
    assert "+" not in query
    assert smoobu.podpis("GET", "/api/rates", query, CAS, "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
                         b"", KLIC, SECRET) == "WXHrQQ4lPRNPQJbh4iaNl8dOVuYrVPHDRgGRSsUmwz4="


# ---------------------------------------------------------------- falešné HTTP odpovědi

class Odpoved:
    def __init__(self, status=200, data=None, headers=None, text=None):
        self.status_code = status
        self.headers = headers or {}
        self.text = text if text is not None else json.dumps(data or {})
        self.content = self.text.encode()

    def json(self):
        return json.loads(self.text)


def klient(odpovedi, **kwargs):
    """Smoobu klient, kterému HTTP vrací připravené odpovědi; zaznamenává odeslané požadavky."""
    s = smoobu.Smoobu(KLIC, SECRET, **kwargs)
    s.pozadavky = []

    def request(method, url, data=None, headers=None, timeout=None):
        s.pozadavky.append({"method": method, "url": url, "headers": headers})
        return odpovedi.pop(0)
    s.session.request = request
    return s


def test_chybejici_secret_nepouzije_stare_overeni():
    with pytest.raises(smoobu.SmoobuError, match="SMOOBU_API_SECRET"):
        smoobu.Smoobu(KLIC, "")


def test_hlavicky_jen_hmac_a_url_v_rfc3986():
    s = klient([Odpoved(200, {"data": {}})])
    s._request("GET", "/api/rates", {"apartments[]": 1, "note": "a b"})
    pozadavek = s.pozadavky[0]
    assert "Api-Key" not in pozadavek["headers"]
    assert {"X-API-Key", "X-Timestamp", "X-Nonce", "X-Signature"} <= set(pozadavek["headers"])
    assert pozadavek["url"].endswith("/api/rates?apartments%5B%5D=1&note=a%20b")


# ---------------------------------------------------------------- 401

def test_401_vyvola_chybu_overeni_a_upozorneni():
    zachyceno = []
    s = klient([Odpoved(401, text='{"detail":"Invalid signature"}')], pri_odmitnuti=zachyceno.append)
    with pytest.raises(smoobu.SmoobuOvereni):
        s.apartments()
    assert len(zachyceno) == 1


def test_upozorneni_na_401_nejvys_jednou_za_hodinu(tmp_path, monkeypatch):
    zpravy = []
    monkeypatch.setattr(oznameni, "posli", lambda text, *a, **k: zpravy.append(text))
    db = Databaze(tmp_path / "t.db")
    chyba = smoobu.SmoobuOvereni("401 test")
    prace.upozorni_na_odmitnuti(db, chyba)
    prace.upozorni_na_odmitnuti(db, chyba)
    assert len(zpravy) == 1
    assert "Smoobu odmítá ověření – agent nečte ani neposílá zprávy" in zpravy[0]
    db.uloz_nastaveni("smoobu_odmitnuti_cas", "2000-01-01T00:00:00")  # od posledního upozornění uběhla hodina
    prace.upozorni_na_odmitnuti(db, chyba)
    assert len(zpravy) == 2


def test_overeni_ok():
    s = klient([Odpoved(200, {"apartments": [{"id": 1}, {"id": 2}]})])
    ok, text = s.over_pripojeni()
    assert ok and text.startswith("Smoobu HMAC: OK")


@pytest.mark.parametrize("odpoved, cast_duvodu", [
    (Odpoved(401, text='{"detail":"Unauthorized"}', headers={"Date": formatdate(usegmt=True)}), "klíč nebo secret"),
    (Odpoved(401, text='{"detail":"Unauthorized"}', headers={"Date": formatdate(time.time() - 600, usegmt=True)}),
     "hodiny"),
    (Odpoved(401, text='{"detail":"Nonce already used"}', headers={"Date": formatdate(usegmt=True)}), "nonce"),
])
def test_overeni_presny_duvod(odpoved, cast_duvodu):
    s = klient([odpoved])
    ok, text = s.over_pripojeni()
    assert not ok and cast_duvodu in text


# ---------------------------------------------------------------- 429

def test_429_get_pocka_a_zopakuje(monkeypatch):
    spanek = []
    monkeypatch.setattr(smoobu.time, "sleep", spanek.append)
    za_chvili = str(int(time.time()) + 3)
    s = klient([Odpoved(429, headers={"X-RateLimit-Retry-After": za_chvili}), Odpoved(200, {"apartments": []})])
    assert s.apartments() == []
    assert len(s.pozadavky) == 2
    assert spanek and 1 <= spanek[0] <= 5


def test_429_post_se_neopakuje(monkeypatch):
    monkeypatch.setattr(smoobu.time, "sleep", lambda *_: None)
    s = klient([Odpoved(429, headers={"X-RateLimit-Retry-After": str(int(time.time()) + 3)}),
                Odpoved(200, {})])
    with pytest.raises(smoobu.SmoobuError):
        s.send_message(1, "ahoj")
    assert len(s.pozadavky) == 1


# ---------------------------------------------------------------- příkazy kontrola / spustit

def test_kontrola_bez_secretu_ukaze_krizek(monkeypatch, capsys):
    monkeypatch.setattr(config, "SMOOBU_API_SECRET", "")
    cli.kontrola(None)
    vystup = capsys.readouterr().out
    assert "❌ SMOOBU_API_SECRET" in vystup
    assert "Vše připraveno" not in vystup


def test_spustit_bez_secretu_skonci_srozumitelnou_chybou(monkeypatch):
    monkeypatch.setattr(config, "SMOOBU_API_SECRET", "")
    # pojistka: kdyby kontrola chyběla, agent se nesmí rozběhnout (smyčka by běžela donekonečna)
    monkeypatch.setattr(prace, "vytvor_smoobu", lambda: pytest.fail("spustit pokračoval bez SMOOBU_API_SECRET"))
    monkeypatch.setattr(cli, "nastav_log", lambda: None)
    with pytest.raises(SystemExit, match="SMOOBU_API_SECRET"):
        cli.spustit(None)
