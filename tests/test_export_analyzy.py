"""Export pro analýzu „co Vasil neví“ (server/export_analyzy.py): jen čte a nic osobního ani tajného z něj neodejde.
Všechna data jsou smyšlená."""
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from agent.databaze import Databaze
from tests.nahrazky import FakeSmoobu

KOREN = Path(__file__).resolve().parent.parent
HLAVICKA = "Byt Test · Jana Nováková · Airbnb · 2026-10-20 → 2026-10-24 (rez. 555)"
KOD = "4821"
HESLO_WIFI = "tajneheslo123"


def _modul():
    spec = importlib.util.spec_from_file_location("export_analyzy", KOREN / "server" / "export_analyzy.py")
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def _rozhodnuti(db, rid, rozhodnuti, zprava_hosta, odpoved, duvod="", dotaz=""):
    db.zapis(rid, "rozhodnuti", {"rozhodnuti": rozhodnuti, "odpoved_hostovi": odpoved, "duvod": duvod,
                                 "navrh_pro_hostitele": dotaz, "jazyk_hosta": "en", "hlavicka": HLAVICKA,
                                 "zprava_hosta": zprava_hosta})


@pytest.fixture
def server(tmp_path):
    """Smyšlený server: znalostní báze, databáze agenta a konverzace ve Smoobu."""
    kb = tmp_path / "znalostni-baze" / "apartmany"
    kb.mkdir(parents=True)
    shutil.copy(KOREN / "znalostni-baze" / "apartmany" / "_sablona.yaml", kb)
    (kb / "byt-test.yaml").write_text(
        f'smoobu_id: "100"\nnazev: "Byt Test"\nadresa: "Testovací 1, Praha"\n'
        f'prijezd:\n  check_in_od: "15:00"\n  keybox_kod: "{KOD}"\n  postup: "Keybox je vlevo od dveří."\n'
        f'wifi:\n  sit: "TestNet"\n  heslo: "{HESLO_WIFI}"\n'
        f'odjezd:\n  pozdni_check_out: "do 12:00 za 1500 Kč"\n'
        f'caste_dotazy:\n  - otazka: "Je tu fén?"\n    odpoved: "Ano, v koupelně."\n'
        f'vlastni_sekce:\n  sauna: "Ne"\n', encoding="utf-8")
    (tmp_path / "znalostni-baze" / "obecne.yaml").write_text(
        'hostitel:\n  podpis: "Test team\\nWhatsApp: +000 000 000 000"\nmesto: "Praha"\n', encoding="utf-8")
    (tmp_path / "data").mkdir()
    db = Databaze(tmp_path / "data" / "agent.db")

    # 1) eskalace: model neví, hostitel odpověděl ručně ve Smoobu
    _rozhodnuti(db, 555, "eskalovat", "Hi, I am Jana, can we leave luggage after checkout? Call me +000 111 222 333",
                "Hi Jana, let me check with the hosts.", duvod="Úschova zavazadel není ve znalostech.",
                dotaz="Můžou si hosté nechat kufry po check-outu?")
    # 2) návrh, který hostitel upravil (✏️): v návrhu kód, hostitel ho opravil
    _rozhodnuti(db, 555, "odpovedet", "What is the code again? jana.novakova@example.com",
                f"Hi Jana, the code is {KOD}, Wi-Fi password {HESLO_WIFI}.")
    puvodni = db.novy_navrh(555, "m2", f"Hi Jana, the code is {KOD}, Wi-Fi password {HESLO_WIFI}.", "en", HLAVICKA)
    db.uprav_navrh(puvodni, stav="nahrazeno")
    novy = db.novy_navrh(555, "", "Hi Jana, the code is 7777, you will get it in the instructions.", "en", HLAVICKA)
    db.uprav_navrh(novy, stav="odeslano")
    # 3) zahozený návrh
    _rozhodnuti(db, 555, "odpovedet", "Can we bring a dog?", "Hi Jana, dogs are welcome!")
    zahozeny = db.novy_navrh(555, "m3", "Hi Jana, dogs are welcome!", "en", HLAVICKA)
    db.uprav_navrh(zahozeny, stav="zahozeno")
    # 4) běžná odpověď bez zásahu hostitele – jen do počtů
    _rozhodnuti(db, 555, "odpovedet", "Thanks!", "You are welcome, Jana!")
    db.zapis("", "kod_z_aplikace", {"smoobu_id": "100", "kod": "9911", "predtim": "8822"})
    db.zapis("", "zmena_znalosti", {"soubor": "byt-test.yaml", "zmena": "doplněna úschova zavazadel, Jana se ptala"})
    db.conn.close()

    smoobu = FakeSmoobu()
    smoobu.pridej_rezervaci(555, "2026-10-20", "2026-10-24", host="Jana Nováková")
    smoobu.konverzace["555"] = [
        {"id": 1, "type": 1, "createdAt": "2026-10-21 10:00:00",
         "message": "Hi, I am Jana, can we leave luggage after checkout? Call me +000 111 222 333"},
        {"id": 2, "type": 2, "createdAt": "2026-10-21 10:01:00", "message": "Hi Jana, let me check with the hosts."},
        {"id": 3, "type": 2, "createdAt": "2026-10-21 11:30:00",
         "message": "Hi Jana, sure, you can leave the bags in the hallway until 14:00."},
        {"id": 4, "type": 2, "createdAt": "2026-10-23 18:00:00",
         "message": "Hi Jana, tomorrow is your departure day, check-out is by 10:00."},
        {"id": 5, "type": 2, "createdAt": "2026-10-25 12:00:00",
         "message": "Hi Jana, thank you for staying with us, a review would help us a lot."},
    ]
    return tmp_path, smoobu


def _hash(soubor):
    return hashlib.sha256(Path(soubor).read_bytes()).hexdigest()


def test_export_nic_osobniho_ani_tajneho(server):
    koren, smoobu = server
    vysledek = _modul().export(koren, smoobu, dnes=date(2026, 11, 2))
    text = json.dumps(vysledek, ensure_ascii=False)
    for zakazane in ("Jana", "Nováková", "novakova", "111 222", "example.com", KOD, HESLO_WIFI, "9911", "8822",
                     "7777", "555", "+000 000"):
        assert zakazane not in text, zakazane
    assert "[HOST]" in text and "[KÓD]" in text and "[TELEFON]" in text and "[E-MAIL]" in text


def test_export_obsahuje_co_je_potreba_pro_analyzu(server):
    koren, smoobu = server
    vysledek = _modul().export(koren, smoobu, dnes=date(2026, 11, 2))

    pripady = {p["typ"]: p for p in vysledek["pripady"]}
    assert set(pripady) == {"eskalace", "upraveno", "zahozeno"}
    eskalace = pripady["eskalace"]
    assert eskalace["rezervace"] == "R1" and eskalace["byt"] == "Byt Test" and eskalace["kanal"] == "Airbnb"
    assert eskalace["dotaz_pro_hostitele"] == "Můžou si hosté nechat kufry po check-outu?"
    # průběžná odpověď Vasila, pak ruční odpověď hostitele ve Smoobu = to, co Vasilovi chybělo ve znalostech
    assert [o["od_vasila"] for o in eskalace["nase_dalsi_zpravy"]] == [True, False]
    assert "hallway until 14:00" in eskalace["nase_dalsi_zpravy"][1]["text"]
    assert "you will get it in the instructions" in pripady["upraveno"]["odeslano_misto_navrhu"]
    assert pripady["zahozeno"]["zprava_hosta"] == "Can we bring a dog?"
    assert vysledek["souhrn"]["rozhodnuti"] == {"eskalovat": 1, "odpovedet": 3}

    byt = vysledek["znalostni_baze"]["byty"][0]
    assert "doprava.parkovani" in byt["prazdna_pole"] and "prijezd.postup" not in byt["prazdna_pole"]
    assert byt["obsah"]["odjezd"]["pozdni_check_out"] == "do 12:00 za 1500 Kč"   # ceny v bázi zůstávají
    assert "keybox_kod" not in byt["obsah"]["prijezd"] and "heslo" not in byt["obsah"]["wifi"]
    assert byt["navic"] == ["vlastni_sekce"]
    assert vysledek["zmeny_znalosti"][0]["zmena"] == "doplněna úschova zavazadel, [HOST] se ptala"

    # zprávy po odjezdu: večer před odjezdem (−1) a den po odjezdu (+1) – automatické zprávy Smoobu č. 5 a 6
    odjezdy = vysledek["odjezdy_smoobu"]
    assert [(z["den"], z["od_vasila"]) for z in odjezdy] == [(-1, False), (1, False)]


def test_export_jen_cte(server):
    koren, smoobu = server
    db = koren / "data" / "agent.db"
    pred = _hash(db)
    _modul().export(koren, smoobu, dnes=date(2026, 11, 2))
    assert _hash(db) == pred
    assert smoobu.odeslane == []


def test_spusteni_jako_z_macu(server):
    """`… | ssh root@IP "cd /opt/airbnb-agent && .venv/bin/python -B -"` – skript přijde na standardní vstup."""
    koren, _ = server
    shutil.copytree(KOREN / "agent", koren / "agent", ignore=shutil.ignore_patterns("__pycache__"))
    prostredi = {k: v for k, v in os.environ.items() if not k.startswith(("SMOOBU", "TELEGRAM", "ANTHROPIC"))}
    beh = subprocess.run([sys.executable, "-B", "-"], input=(KOREN / "server" / "export_analyzy.py").read_bytes(),
                         cwd=koren, capture_output=True, env=prostredi, timeout=60)
    assert beh.returncode == 0, beh.stderr.decode("utf-8", "replace")
    vysledek = json.loads(beh.stdout.decode("utf-8"))
    assert len(vysledek["pripady"]) == 3
    assert "Smoobu nedostupné" in beh.stderr.decode("utf-8", "replace")   # bez klíčů jen bez konverzací
    assert not (koren / "agent" / "__pycache__").exists()                 # na serveru nic nezůstane


def test_export_bez_smoobu(server):
    """Bez přístupu ke Smoobu export proběhne, jen bez konverzací."""
    koren, _ = server
    vysledek = _modul().export(koren, None, dnes=date(2026, 11, 2))
    assert len(vysledek["pripady"]) == 3 and vysledek["odjezdy_smoobu"] == []
