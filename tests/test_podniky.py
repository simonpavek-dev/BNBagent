"""P3.3 Doporučení podniků z Google Maps (přepínač DOPORUCENI_PODNIKU, výchozí vypnuto).

Model zavolá nástroj doporuc_podniky; kód vybere až 3 podniky v okolí bytu: hodnocení aspoň DOPORUCENI_MIN_HODNOCENI
z aspoň DOPORUCENI_MIN_RECENZI recenzí, otevřeno v den a čas, na který se host ptá, do DOPORUCENI_MAX_PESKY_MIN pěšky.
Seznam (název, hodnocení, čas pěšky, otevírací doba, odkaz) vloží do odpovědi kód místo značky [TIPY Z MAP n] –
model hodnocení ani otevírací doby nepíše. Google se v testech nevolá. Všechna data jsou smyšlená."""
import json
from types import SimpleNamespace as NS

import pytest

from agent import config, hodiny, mozek, podniky
from conftest import ZACATEK

BYT = (50.0800, 14.4200)


def kazdy_den(od, do, krome=()):
    """Otevírací doba ve tvaru Google Places: každý den od–do (do > 24 = přes půlnoc). Den 0 = neděle."""
    return [{"open": {"day": d, "hour": od, "minute": 0},
             "close": {"day": (d + do // 24) % 7, "hour": do % 24, "minute": 0}} for d in range(7) if d not in krome]


def misto(id_, nazev, hodnoceni, pocet, vzdalenost_m=300, periody=None, aktualni=None, stav="OPERATIONAL"):
    m = {"id": id_, "displayName": {"text": nazev}, "rating": hodnoceni, "userRatingCount": pocet,
         "location": {"latitude": BYT[0] + vzdalenost_m / 111_320, "longitude": BYT[1]},
         "googleMapsUri": f"https://maps.google.com/?cid={id_}", "businessStatus": stav,
         "regularOpeningHours": {"periods": kazdy_den(11, 23) if periody is None else periody}}
    if aktualni is not None:
        m["currentOpeningHours"] = {"periods": aktualni}
    return m


@pytest.fixture
def google(monkeypatch):
    """Zapnuté doporučení; místo Googlu a map seznam míst v paměti (g.mista), dotazy do Googlu v g.dotazy.
    Hodiny zmrazené na po 2. 11. 2026 9:00 (aktuální otevírací doba Googlu platí 7 dní od „dnes“)."""
    hodiny.zmraz(ZACATEK)
    monkeypatch.setattr(config, "DOPORUCENI_PODNIKU", True, raising=False)
    monkeypatch.setattr(config, "GOOGLE_MAPS_API_KEY", "test", raising=False)
    monkeypatch.setattr(config, "DOPORUCENI_MIN_HODNOCENI", 4.0, raising=False)
    monkeypatch.setattr(config, "DOPORUCENI_MIN_RECENZI", 100, raising=False)
    monkeypatch.setattr(config, "DOPORUCENI_MAX_PESKY_MIN", 15, raising=False)
    g = NS(mista=[], dotazy=[])
    monkeypatch.setattr(podniky, "_hledej", lambda *a: g.dotazy.append(a) or list(g.mista))
    monkeypatch.setattr(podniky, "_souradnice", lambda adresa: BYT)
    monkeypatch.setattr(podniky, "_pesky_min", lambda lat1, lon1, lat2, lon2:
                        max(1, round(podniky.vzdalenost_m(lat1, lon1, lat2, lon2) / 80)))
    yield g
    hodiny.rozmraz()


MISTA = [
    misto("A", "Pizza A", 4.8, 2000),
    misto("B", "Malý B", 4.9, 50),                                     # málo recenzí
    misto("C", "Velký C", 3.9, 5000),                                  # nízké hodnocení
    misto("D", "Zavřeno v pondělí D", 4.6, 800, periody=kazdy_den(11, 23, krome=(1,))),
    misto("E", "Bar E", 4.5, 300, periody=kazdy_den(18, 26)),          # 18:00–2:00
    misto("F", "Daleko F", 4.7, 1000, vzdalenost_m=3000),
    misto("G", "Bistro G", 4.4, 150),
    misto("H", "Zrušený H", 4.9, 900, stav="CLOSED_PERMANENTLY"),
]


def test_top3_podle_hodnoceni_recenzi_a_oteviraci_doby(google):
    google.mista = MISTA
    vysledek, blok = podniky.doporuc("Testovací 1, Praha", "restaurant", "2026-11-02 19:00")   # pondělí 19:00
    assert [p["nazev"] for p in vysledek["podniky"]] == ["Pizza A", "Bar E", "Bistro G"]
    assert blok.startswith("📍 Google Maps")
    assert "1. Pizza A – ⭐ 4.8 (2 000) · 🚶 4 min · 🕒 11:00–23:00\nhttps://maps.google.com/?cid=A" in blok
    assert "2. Bar E – ⭐ 4.5 (300) · 🚶 4 min · 🕒 18:00–2:00" in blok
    [(dotaz, lat, lon, polomer, min_hodnoceni)] = google.dotazy
    assert (dotaz, (lat, lon), polomer, min_hodnoceni) == ("restaurant", BYT, 1200, 4.0)


def test_v_noci_jen_otevrene(google):
    google.mista = MISTA
    vysledek, _ = podniky.doporuc("Testovací 1, Praha", "bar", "2026-11-03 01:00")   # úterý 1:00
    assert [p["nazev"] for p in vysledek["podniky"]] == ["Bar E"]                    # otevřeno od pondělí 18:00


def test_pres_pulnoc_ze_soboty_na_nedeli(google):
    google.mista = [misto("S", "Klub S", 4.6, 500, periody=[{"open": {"day": 6, "hour": 22, "minute": 0},
                                                             "close": {"day": 0, "hour": 3, "minute": 0}}])]
    vysledek, blok = podniky.doporuc("Testovací 1, Praha", "club", "2026-11-08 01:00")   # neděle 1:00
    assert [p["nazev"] for p in vysledek["podniky"]] == ["Klub S"] and "🕒 22:00–3:00" in blok


def test_nonstop(google):
    google.mista = [misto("N", "Nonstop N", 4.3, 400, periody=[{"open": {"day": 0, "hour": 0, "minute": 0}}])]
    vysledek, blok = podniky.doporuc("Testovací 1, Praha", "pharmacy", "2026-11-04 03:30")
    assert vysledek["nalezeno"] == 1 and "🕒 0:00–24:00" in blok


def test_svatek_podle_aktualni_oteviraci_doby(google):
    """Do 7 dní platí aktuální otevírací doba Googlu (svátky, výjimky), dál běžná."""
    google.mista = [misto("K", "Kavárna K", 4.7, 600, aktualni=kazdy_den(11, 23, krome=(1,)))]   # tento týden po zavřeno
    assert podniky.doporuc("Testovací 1, Praha", "cafe", "2026-11-02 12:00")[0]["nalezeno"] == 0
    assert podniky.doporuc("Testovací 1, Praha", "cafe", "2026-11-16 12:00")[0]["nalezeno"] == 1


def test_nic_nevyhovuje(google):
    google.mista = [misto("B", "Malý B", 4.9, 50)]
    vysledek, blok = podniky.doporuc("Testovací 1, Praha", "restaurant", "2026-11-02 19:00")
    assert vysledek["nalezeno"] == 0 and blok == "" and "eskaluj" in vysledek["poznamka"]


def test_bez_casu_plati_ted(google):
    google.mista = MISTA
    vysledek, _ = podniky.doporuc("Testovací 1, Praha", "restaurant", "")   # pondělí 9:00 – vše zavřeno
    assert vysledek["nalezeno"] == 0 and vysledek["kdy"].startswith("2026-11-02 09:00")


def test_bez_klice_chyba(google, monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_MAPS_API_KEY", "")
    with pytest.raises(podniky.PodnikyChyba):
        podniky.doporuc("Testovací 1, Praha", "restaurant", "2026-11-02 19:00")


# ---------------------------------------------------------------- model a nástroj

def test_nastroj_a_pokyn_jen_kdyz_zapnuto_s_klicem(monkeypatch):
    def nazvy():
        return [n["name"] for n in mozek.nastroje_zpravy()]
    assert "doporuc_podniky" not in nazvy() and "doporuc_podniky" not in mozek.instrukce_zpravy()
    monkeypatch.setattr(config, "DOPORUCENI_PODNIKU", True, raising=False)
    assert "doporuc_podniky" not in nazvy()                              # bez klíče Google nástroj nedostane
    monkeypatch.setattr(config, "GOOGLE_MAPS_API_KEY", "test", raising=False)
    assert "doporuc_podniky" in nazvy() and "[TIPY Z MAP" in mozek.instrukce_zpravy()


class FakeKlient:
    """Místo anthropic.Anthropic(): vrací připravené odpovědi a zaznamenává parametry volání."""

    def __init__(self, odpovedi):
        self.odpovedi, self.volani = list(odpovedi), []
        self.messages = self
        self.beta = NS(messages=self)

    def create(self, **params):
        self.volani.append(params)
        return self.odpovedi.pop(0)


def _odpoved(stop_reason, obsah):
    return NS(stop_reason=stop_reason, content=obsah,
              usage=NS(input_tokens=1, output_tokens=1, cache_creation_input_tokens=0, cache_read_input_tokens=0))


def test_model_zavola_nastroj_a_seznam_doplni_kod(monkeypatch):
    monkeypatch.setattr(config, "DOPORUCENI_PODNIKU", True, raising=False)
    monkeypatch.setattr(config, "GOOGLE_MAPS_API_KEY", "test", raising=False)
    blok = "📍 Google Maps\n1. Pizza A – ⭐ 4.8 (2 000) · 🚶 4 min · 🕒 11:00–23:00\nhttps://maps.google.com/?cid=A"
    monkeypatch.setattr(podniky, "doporuc", lambda odkud, dotaz, kdy: ({"nalezeno": 1, "podniky": []}, blok))
    odpoved = {"rozhodnuti": "odpovedet", "odpoved_hostovi": "Here are our tips for tonight:\n\n[TIPY Z MAP 1]",
               "navrh_pro_hostitele": "", "duvod": "tipy", "jazyk_hosta": "en"}
    klient = FakeKlient([
        _odpoved("tool_use", [NS(type="tool_use", name="doporuc_podniky", id="t1",
                                 input={"odkud": "Testovací 1, Praha", "dotaz": "restaurant", "kdy": "2026-11-02 19:00"})]),
        _odpoved("end_turn", [NS(type="text", text=json.dumps(odpoved))]),
    ])
    monkeypatch.setattr(mozek, "_client", klient)
    v = mozek.rozhodni_o_zprave("obecne", "byt", "kontext")
    assert v["_doplnky"] == {"[TIPY Z MAP 1]": blok}
    assert "doporuc_podniky" in [n["name"] for n in klient.volani[0]["tools"]]
    vysledek_nastroje = klient.volani[1]["messages"][-1]["content"][0]
    assert vysledek_nastroje["tool_use_id"] == "t1" and "[TIPY Z MAP 1]" in vysledek_nastroje["content"]


def _dotaz_hosta(svet, odpoved, doplnky):
    dnes = hodiny.dnes()
    from datetime import timedelta
    svet.smoobu.pridej_rezervaci("R1", dnes - timedelta(days=1), dnes + timedelta(days=2))
    svet.smoobu.napis_my("R1", "Welcome!")
    svet.smoobu.napis_host("R1", "Can you recommend a good restaurant for tonight?")
    svet.model.odpovedi["zpráva hosta"] = {"rozhodnuti": "odpovedet", "odpoved_hostovi": odpoved,
                                           "navrh_pro_hostitele": "", "duvod": "tipy", "jazyk_hosta": "en",
                                           "_doplnky": doplnky}
    svet.cyklus()


def test_seznam_v_odpovedi_hostovi(svet):
    blok = "📍 Google Maps\n1. Pizza A – ⭐ 4.8 (2 000) · 🚶 4 min · 🕒 11:00–23:00\nhttps://maps.google.com/?cid=A"
    _dotaz_hosta(svet, "Here are our tips for tonight:\n\n[TIPY Z MAP 1]", {"[TIPY Z MAP 1]": blok})
    text = svet.db.navrh(svet.telegram.navrh_id())["text"]
    assert text == f"Here are our tips for tonight:\n\n{blok}"
    assert not any("ZKONTROLUJ" in z["text"] for z in svet.telegram.zpravy)


def test_znacka_bez_nastroje_jen_ke_kontrole(svet):
    _dotaz_hosta(svet, "Here are our tips:\n\n[TIPY Z MAP 1]", {})
    assert any("ZKONTROLUJ" in z["text"] and "[TIPY Z MAP 1]" in z["text"] for z in svet.telegram.zpravy)
