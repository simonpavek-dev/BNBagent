"""Zkrácené zprávy hostům (18. 10. 2026): Smoobu zahodí text od znaku „<“ (šipka „LEFT <----“ ve Vojtěšské 2kk).
Brána proto „<“ před odesláním nahradí a po odeslání ověří, že Smoobu uložilo celou zprávu."""
import json
from datetime import timedelta

from agent import hodiny, spravce


def _navrh(svet, text):
    dnes = hodiny.dnes()
    svet.smoobu.pridej_rezervaci("R1", dnes + timedelta(days=2), dnes + timedelta(days=4))
    svet.smoobu.napis_host("R1", "How do we get in?")
    svet.model.odpovez(text=text)
    svet.cyklus()
    return svet.telegram.navrh_id()


def test_znak_mensi_nez_neusekne_zpravu(svet):
    navrh_id = _navrh(svet, "Your apartment is the most LEFT <---- To unlock your apartment use code: 4242. Wi-Fi: Net")
    svet.telegram.klikni(svet.smoobu, svet.db, "odeslat", navrh_id)
    ulozena = svet.smoobu.konverzace["R1"][-1]["message"]
    assert "4242" in ulozena and "Wi-Fi: Net" in ulozena      # host dostane celou zprávu
    assert "<" not in svet.smoobu.odeslane[0][1]


def test_zkracena_zprava_ve_smoobu_hned_upozorni(svet):
    navrh_id = _navrh(svet, "Hi! Here are your check-in details. Keybox code: 4242. Wi-Fi: TestNet / test-heslo.")
    svet.smoobu.orez_ulozenych = 30                           # Smoobu z nějakého důvodu uloží jen začátek
    svet.telegram.klikni(svet.smoobu, svet.db, "odeslat", navrh_id)
    upozorneni = [z["text"] for z in svet.telegram.zpravy if "zkrátilo" in z["text"].lower()]
    assert upozorneni, "hostitelé se o zkrácené zprávě nedozvěděli"
    assert "Keybox code: 4242" in upozorneni[0]               # celé znění k ručnímu odeslání
    assert svet.db.conn.execute("SELECT zkraceno FROM odchozi").fetchone()[0] == 1


def test_cela_zprava_bez_upozorneni(svet):
    navrh_id = _navrh(svet, "Hi! Keybox code: 4242. Wi-Fi: TestNet / test-heslo.")
    svet.telegram.klikni(svet.smoobu, svet.db, "odeslat", navrh_id)
    assert not any("zkrátilo" in z["text"].lower() for z in svet.telegram.zpravy)
    assert svet.db.conn.execute("SELECT zkraceno FROM odchozi").fetchone()[0] == 0


def test_vasil_vidi_zkracene_zpravy(svet):
    navrh_id = _navrh(svet, "Hi! Here are your check-in details. Keybox code: 4242.")
    svet.smoobu.orez_ulozenych = 20
    svet.telegram.klikni(svet.smoobu, svet.db, "odeslat", navrh_id)
    vypis = json.loads(spravce._spust(svet.db, "odeslane_zpravy", {"od": hodiny.dnes().isoformat()}))
    assert vypis and vypis[0]["zkraceno_ve_smoobu"] is True
