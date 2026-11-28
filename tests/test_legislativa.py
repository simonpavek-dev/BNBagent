"""Hlídání Poslanecké sněmovny (HLIDANI_LEGISLATIVY): návrhy zákonů a jednání ke krátkodobému ubytování.
Otevřená data psp.cz jsou tu smyšlená (stejný formát: UNL, oddělovač |, kódování cp1250), síť se nevolá."""
from datetime import datetime

import pytest
from nahrazky import FakePsp

from agent import config, hodiny, legislativa

UTERY_7 = datetime(2026, 11, 3, 7, 0)
TEXT_RELEVANTNI = "Obec může obecně závaznou vyhláškou omezit krátkodobé ubytování a stanovit počet nocí za rok pro ubytování."
TEXT_NERELEVANTNI = "Zákon o myslivosti upravuje lov zvěře a hospodaření v honitbách."


@pytest.fixture
def snemovna(svet, monkeypatch):
    monkeypatch.setattr(config, "HLIDANI_LEGISLATIVY", True)
    monkeypatch.setattr(config, "LEGISLATIVA_HODINY", [7, 19])
    monkeypatch.setattr(config, "LEGISLATIVA_SOUHRN_HODINA", 8)
    psp = FakePsp()
    psp.tisk("5001", "106", "Novela z. o cestovním ruchu", TEXT_RELEVANTNI)
    psp.tisk("5002", "200", "Novela z. o myslivosti", TEXT_NERELEVANTNI, druh="1")
    psp.hist.append(("10", "5001", "2026-03-11 00:00", "100", ""))
    monkeypatch.setattr(legislativa, "_stahni", psp.stahni)
    monkeypatch.setattr(legislativa, "_text_pdf", lambda obsah: psp.texty[obsah.decode()])
    svet.model.odpovedi["legislativa – tisk"] = {"relevantni": True, "temata": ["omezení počtu nocí a regulace obcemi"],
                                                "shrnuti": "Obce by mohly omezit krátkodobé ubytování.",
                                                "dopad": "Praha by mohla zavést limit nocí."}
    svet.model.odpovedi["legislativa – rozprava"] = {"relevantni": True, "shrnuti": "Poslanci řešili limit nocí.",
                                                    "dopad": "Zatím nic nového."}
    svet.psp = psp
    hodiny.zmraz(UTERY_7)
    return svet


def _snemovna(svet):
    return [z for z in svet.telegram.zpravy if "SNĚMOVN" in z["text"]]


def _volani(svet, ucel):
    return [v for v in svet.model.volani if v["ucel"] == ucel]


def test_prvni_beh_uvodni_prehled(snemovna):
    svet = snemovna
    svet.cyklus()
    [z] = _snemovna(svet)
    assert "HLÍDÁNÍ SNĚMOVNY SPUŠTĚNO" in z["text"] and "Tisk 106" in z["text"] and "limit nocí" in z["text"]
    assert "Tisk 200" not in z["text"]
    [volani] = _volani(svet, "legislativa – tisk")                    # myslivost bez klíčových slov → bez modelu
    assert "106" in volani["kontext"] and "počet nocí" in volani["kontext"]


def test_novy_krok_projednavani_hlasi_se_jednou(snemovna):
    svet = snemovna
    svet.cyklus()
    svet.psp.hist.append(("11", "5001", "2026-11-03 12:00", "101", "37"))
    hodiny.zmraz(UTERY_7.replace(hour=19))
    svet.cyklus()
    [z] = [z for z in _snemovna(svet) if "pohnulo" in z["text"]]
    assert "schválen v 1. čtení" in z["text"] and "37. schůze" in z["text"] and "historie.sqw?o=10&t=106" in z["text"]
    hodiny.zmraz(UTERY_7.replace(day=4))
    svet.cyklus()
    assert len([z for z in _snemovna(svet) if "pohnulo" in z["text"]]) == 1


def test_zarazeni_na_program_schuze(snemovna):
    svet = snemovna
    svet.cyklus()
    svet.psp.schuze.append(("901", "38", "2026-12-03 09", ""))
    svet.psp.body.append(("70", "901", "5001", "15", "1"))
    hodiny.zmraz(UTERY_7.replace(hour=19))
    svet.cyklus()
    [z] = [z for z in _snemovna(svet) if "na programu" in z["text"]]
    assert "38. schůze" in z["text"] and "3. 12. 2026" in z["text"] and "bod 15" in z["text"]


def test_rozprava_ze_stenozaznamu(snemovna):
    svet = snemovna
    svet.psp.steno.append(("1", 36, 1, "2026-10-20"))                # starý záznam z doby před spuštěním – přeskočí se
    svet.cyklus()
    svet.psp.steno += [("2", 37, 5, "2026-11-03"), ("3", 37, 6, "2026-11-03")]
    zaklad = "https://www.psp.cz/eknih/2025ps/stenprot/037schuz/s037"
    svet.psp.steno_texty[f"{zaklad}005.htm"] = "Poslanec: Navrhuji, aby obce mohly regulovat krátkodobé ubytování."
    svet.psp.steno_texty[f"{zaklad}006.htm"] = "Předsedající: Přerušuji schůzi do zítřka."
    hodiny.zmraz(UTERY_7.replace(hour=19))
    svet.cyklus()
    [z] = [z for z in _snemovna(svet) if "mluvilo se" in z["text"]]
    assert "Poslanci řešili limit nocí." in z["text"] and f"{zaklad}005.htm" in z["text"]
    [volani] = _volani(svet, "legislativa – rozprava")
    assert "regulovat krátkodobé ubytování" in volani["kontext"] and "Přerušuji" not in volani["kontext"]
    assert not any("036schuz" in u for u in svet.psp.stazeno)


def test_novy_relevantni_navrh_po_spusteni(snemovna):
    svet = snemovna
    svet.cyklus()
    svet.psp.tisk("5003", "350", "Novela z. o evidenci", "Ubytovatel zapíše hosta do systému eTurista.")
    hodiny.zmraz(UTERY_7.replace(hour=19))
    svet.cyklus()
    [z] = [z for z in _snemovna(svet) if "nový návrh" in z["text"]]
    assert "Tisk 350" in z["text"] and "Praha by mohla zavést limit nocí." in z["text"]


def test_pondelni_souhrn(snemovna):
    svet = snemovna
    svet.cyklus()
    svet.psp.schuze.append(("901", "38", "2026-11-10 09", ""))
    svet.psp.body.append(("70", "901", "5001", "15", "1"))
    hodiny.zmraz(datetime(2026, 11, 9, 7, 0))                        # pondělí 7:00 – data, ještě bez souhrnu
    svet.cyklus()
    assert not [z for z in _snemovna(svet) if "SOUHRN" in z["text"]]
    hodiny.zmraz(datetime(2026, 11, 9, 8, 0))
    svet.cyklus()
    [z] = [z for z in _snemovna(svet) if "SOUHRN" in z["text"]]
    assert "Tento týden na programu" in z["text"] and "38. schůze" in z["text"] and "Tisk 106" in z["text"]
    assert "na programu" in z["text"].split("Minulý týden:")[1]   # zpráva o zařazení na program z minulého týdne
    hodiny.zmraz(datetime(2026, 11, 9, 9, 0))
    svet.cyklus()
    assert len([z for z in _snemovna(svet) if "SOUHRN" in z["text"]]) == 1


def test_po_davkach_aby_nezdrzelo_hosty(snemovna, monkeypatch):
    svet = snemovna
    for i in range(10):
        svet.psp.tisk(f"60{i}", f"40{i}", f"Novela {i}", TEXT_NERELEVANTNI)
    svet.cyklus()
    stazene_texty = [u for u in svet.psp.stazeno if "orig2" in u]
    assert len(stazene_texty) == legislativa.MAX_STAZENI_ZA_CYKLUS
    assert _snemovna(svet) == []                                       # úvod až po posouzení všech
    cyklu = 1
    while not _snemovna(svet) and cyklu < 10:
        hodiny.posun(minutes=3)
        svet.cyklus()
        cyklu += 1
    assert cyklu == -(-12 // legislativa.MAX_STAZENI_ZA_CYKLUS)       # 12 tisků po dávkách
    assert len([z for z in _snemovna(svet) if "SPUŠTĚNO" in z["text"]]) == 1


def test_vypadek_psp_nezastavi_agenta_a_zkusi_se_znovu(snemovna, monkeypatch):
    svet = snemovna
    puvodni = svet.psp.stahni

    def nejde(url, timeout=120):
        raise legislativa.requests.ConnectionError("psp.cz nejde")
    monkeypatch.setattr(legislativa, "_stahni", nejde)
    svet.cyklus()                                                      # chyba v kroku, cyklus doběhne
    assert _snemovna(svet) == []
    monkeypatch.setattr(legislativa, "_stahni", puvodni)
    hodiny.posun(minutes=3)
    svet.cyklus()
    assert len(_snemovna(svet)) == 1


def test_vypnuto_nic_nestahuje(snemovna, monkeypatch):
    svet = snemovna
    monkeypatch.setattr(config, "HLIDANI_LEGISLATIVY", False)
    svet.cyklus()
    assert svet.psp.stazeno == []


def test_vynatky_najdou_temata():
    temata, text = legislativa.vynatky("Úvod. " * 200 + "Hostitel zapíše hosta do systému eTurista. " + "Konec. " * 200)
    assert temata == ["eTurista a evidence hostů"] and "eTurista" in text and len(text) < 1500
    assert legislativa.vynatky(TEXT_NERELEVANTNI) == ([], "")
