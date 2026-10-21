"""A2 Simulátor scénářů: celé dny hosta přes jeden_cyklus nad náhražkami (Smoobu, Telegram, model, aplikace úklidů).

Každý scénář běží dvakrát: v režimu návrhů (hostitelé každý návrh hned schválí ✅) a v ostrém režimu, s přepínači
jako na serveru. Agent běží každých 10 minut simulovaného času. Po každém scénáři se kontrolují společné zásady:
žádná zpráva hostovi neodešla dvakrát, žádná neobsahuje značku ([KÓD BYTU]…) ani „<“, každá zpráva hosta skončila
v jednom stavu a (pokud scénář nesimuluje výpadek) žádný krok cyklu neskončil chybou.
Všechna data jsou smyšlená."""
from datetime import datetime, timedelta

import pytest

from agent import config, hodiny, uklidy, znacky

PONDELI = datetime(2026, 11, 2, 9, 0)  # = začátek simulace (conftest.ZACATEK)
NA_SERVERU = ("PRIJEZDY_AUTOMATICKY", "ZDVORILOSTI_BEZ_MODELU", "OPRAVA_KODU_PO_UKLIDU", "HLASIT_AUTOMATICKE_ODPOVEDI",
              "KONTROLA_KALENDARE")


@pytest.fixture(params=["navrh", "ostre"])
def scenar(svet, monkeypatch, request):
    for prepinac in NA_SERVERU:
        monkeypatch.setattr(config, prepinac, True)
    monkeypatch.setattr(config, "REZIM", request.param)
    monkeypatch.setattr(config, "UKLIDY_URL", "https://uklidy.test")
    monkeypatch.setattr(config, "UKLIDY_LOGIN", "test")
    monkeypatch.setattr(config, "UKLIDY_HESLO", "test")
    svet.uklidy_data = []
    monkeypatch.setattr(uklidy, "_stahni", lambda: list(svet.uklidy_data))
    svet.rezim = request.param
    return svet


# ---------------------------------------------------------------- pomocníci

def uklid(svet, den, kod):
    """Uklízečky zapíšou do aplikace úklid bytu a kód keyboxu, který po úklidu nastavily."""
    svet.uklidy_data.append({"stay": {"id": f"u{den}", "checkOut": str(den), "cleaningDate": str(den), "codes": kod,
                                      "uklidStatus": "uklizeno"}, "apartment": {"name": "Testbyt 1"}})
    uklidy._cache.update(cas=0.0, pobyty=None)


def schval_navrhy(svet):
    """Režim návrhů: hostitelé hned schválí každý čekající návrh (✅)."""
    for z in svet.telegram.s_tlacitky():
        for _, data in z["tlacitka"]:
            if data.startswith("odeslat:") and svet.db.navrh(int(data.split(":")[1]))["stav"] == "ceka":
                svet.telegram.klikni(svet.smoobu, svet.db, "odeslat", int(data.split(":")[1]))


def do_casu(svet, kdy):
    """Agent běží každých 10 minut až do času kdy (včetně); v režimu návrhů hostitelé návrhy hned schvalují.
    Chybu cyklu zachytí a zapíše jako hlavní smyčka (__main__.spustit) – další cyklus běží dál."""
    while True:
        try:
            svet.cyklus()
        except Exception as e:
            svet.db.zapis("", "chyba", f"Chyba při kontrole zpráv: {e}")
        if svet.rezim == "navrh":
            schval_navrhy(svet)
        if hodiny.ted() >= kdy:
            return
        hodiny.posun(seconds=min(600, (kdy - hodiny.ted()).total_seconds()))


def odeslane(svet, obsahuje=""):
    return [text for _, text in svet.smoobu.odeslane if obsahuje in text]


def zasady(svet, vypadek=False):
    assert len(set(svet.smoobu.odeslane)) == len(svet.smoobu.odeslane), "zpráva hostovi odešla dvakrát"
    for _, text in svet.smoobu.odeslane:
        assert not znacky.zbyle_znacky(text) and "<" not in text, text
    for zpravy in svet.smoobu.konverzace.values():
        for m in zpravy:
            if m["type"] == 1:
                assert svet.db.zprava_vyrizena(m["id"]), f"zpráva hosta se ztratila: {m['message']}"
    if not vypadek:
        assert svet.db.conn.execute("SELECT detail FROM udalosti WHERE akce = 'chyba'").fetchall() == []


# ---------------------------------------------------------------- scénáře

def test_cesta_hosta_od_dotazu_po_odjezd(scenar):
    svet = scenar
    ut, st = PONDELI + timedelta(days=1), PONDELI + timedelta(days=2)
    uklid(svet, PONDELI.date(), "3333")  # po odjezdu předchozího hosta
    svet.smoobu.pridej_rezervaci("R1", ut.date(), (ut + timedelta(days=2)).date(), host="Anna Test")

    # Po 9:00 – dotaz před příjezdem
    svet.smoobu.napis_host("R1", "Hi, where can we park?")
    svet.model.odpovez(text="Hi Anna, you can park on the street right in front of the house.")
    do_casu(svet, PONDELI.replace(minute=30))
    assert odeslane(svet, "park on the street")

    # Po 18:00 – instrukce na zítřek se připraví a naplánují na 10:00, zatím nic neodejde
    do_casu(svet, PONDELI.replace(hour=18, minute=30))
    assert any("odešlu je hostovi sám" in z["text"] for z in svet.telegram.zpravy)
    assert not odeslane(svet, "Keybox code")

    # Út 10:00 – instrukce odejdou se správným kódem a Wi-Fi
    do_casu(svet, ut.replace(hour=10, minute=30))
    [instrukce] = odeslane(svet, "Keybox code")
    assert "Keybox code: 3333" in instrukce and "network TestNet / password test-heslo" in instrukce

    # Út 11:00 – uklízečky po úklidu nastaví nový kód → host dostane opravu
    uklid(svet, ut.date(), "4444")
    do_casu(svet, ut.replace(hour=11, minute=30))
    assert odeslane(svet, "new keybox code is 4444")

    # Út 12:00 – poděkování vyřídí pravidlo bez modelu; na další díky po našem rozloučení už se neodpovídá
    volani, pocet = len(svet.model.volani), len(svet.smoobu.odeslane)
    svet.smoobu.napis_host("R1", "Thank you!")
    do_casu(svet, ut.replace(hour=12, minute=20))
    assert len(svet.smoobu.odeslane) == pocet + 1
    svet.smoobu.napis_host("R1", "Thanks 👍")
    do_casu(svet, ut.replace(hour=12, minute=50))
    assert len(svet.smoobu.odeslane) == pocet + 1 and len(svet.model.volani) == volani

    # Út 16:00 – po příjezdu Wi-Fi: model napíše značku, host dostane skutečné heslo
    do_casu(svet, ut.replace(hour=16))
    svet.smoobu.napis_host("R1", "What is the wifi password please?")
    svet.model.odpovez(text="The Wi-Fi password is [WIFI HESLO]. Enjoy your stay!")
    do_casu(svet, ut.replace(hour=16, minute=30))
    assert odeslane(svet, "The Wi-Fi password is test-heslo.")

    # St 10:00 – sleva: hostitelé dostanou eskalaci, host krátkou průběžnou odpověď
    do_casu(svet, st.replace(hour=10))
    svet.smoobu.napis_host("R1", "Could we get a discount if we come back next year?")
    svet.model.odpovez(rozhodnuti="eskalovat", text="Thank you for asking, we will check and get back to you soon.",
                       navrh="Sleva – rozhodni.")
    do_casu(svet, st.replace(hour=10, minute=30))
    assert any("POTŘEBUJU TĚ" in z["text"] for z in svet.telegram.zpravy)
    assert odeslane(svet, "we will check and get back to you")

    # Čt – odjezd: agent už nic dalšího neposílá
    do_casu(svet, (st + timedelta(days=1)).replace(hour=14))
    assert len(svet.smoobu.odeslane) == 6
    hlaseni = [z for z in svet.telegram.zpravy if "odpověděl hostovi sám" in z["text"]]
    assert len(hlaseni) == (3 if svet.rezim == "ostre" else 0)  # parkování, díky, Wi-Fi
    zasady(svet)


def test_vypadek_smoobu_a_telegramu(scenar):
    svet = scenar
    svet.smoobu.pridej_rezervaci("R1", (PONDELI + timedelta(days=5)).date(), (PONDELI + timedelta(days=7)).date())
    svet.smoobu.napis_host("R1", "Can we bring a small dog?")
    svet.model.odpovez(rozhodnuti="eskalovat", text="Thank you, we will check and get back to you.", navrh="Pes.")

    # Smoobu vrací 503 a Telegram nejde – cyklus nespadne, nic se neodešle ani neztratí
    svet.smoobu.porucha_cteni = "503"
    svet.telegram.vypadek = True
    do_casu(svet, PONDELI.replace(minute=30))
    assert svet.smoobu.odeslane == [] and svet.model.volani == []

    # Smoobu zase jde, Telegram pořád ne – eskalace čeká ve frontě upozornění
    svet.smoobu.porucha_cteni = None
    do_casu(svet, PONDELI.replace(hour=10))
    assert not any("POTŘEBUJU TĚ" in z["text"] for z in svet.telegram.zpravy)

    # Telegram jde – eskalace dorazí (zpožděně) a tlačítka fungují
    svet.telegram.vypadek = False
    do_casu(svet, PONDELI.replace(hour=10, minute=30))
    [eskalace] = [z for z in svet.telegram.zpravy if "POTŘEBUJU TĚ" in z["text"]]
    assert "Zpožděné upozornění" in eskalace["text"]
    assert [v["ucel"] for v in svet.model.volani] == ["zpráva hosta"]  # zpráva se zpracovala jednou
    assert odeslane(svet) == ["Thank you, we will check and get back to you."]
    zasady(svet, vypadek=True)


def test_timeout_pri_odeslani_bez_dvoji_zpravy(scenar):
    svet = scenar
    svet.smoobu.pridej_rezervaci("R1", (PONDELI + timedelta(days=2)).date(), (PONDELI + timedelta(days=4)).date())
    svet.smoobu.napis_host("R1", "Is there a hairdryer?")
    svet.model.odpovez(text="Yes, there is a hairdryer in the bathroom.")
    svet.smoobu.porucha = "timeout_po_odeslani"  # zpráva odejde, ale Smoobu neodpoví
    do_casu(svet, PONDELI.replace(minute=10))
    svet.smoobu.porucha = None
    do_casu(svet, PONDELI.replace(hour=11))
    assert odeslane(svet) == ["Yes, there is a hairdryer in the bathroom."]
    zasady(svet)


def test_smoobu_zkrati_zpravu_hostitele_hned_vi(scenar):
    svet = scenar
    svet.smoobu.pridej_rezervaci("R1", (PONDELI + timedelta(days=2)).date(), (PONDELI + timedelta(days=4)).date())
    svet.smoobu.napis_host("R1", "How do we get from the airport?")
    svet.model.odpovez(text="Take bus 119 <---- to the metro, then line A to the centre. See you soon!")
    svet.smoobu.orez_ulozenych = 25  # Smoobu uloží jen začátek zprávy
    do_casu(svet, PONDELI.replace(minute=30))
    [text] = odeslane(svet)
    assert "‹----" in text  # „<“ brána nahradila, jinak by Smoobu zbytek zahodilo
    [upozorneni] = [z for z in svet.telegram.zpravy if "ZKRÁTILO" in z["text"]]
    assert text in upozorneni["text"]  # celé znění k ručnímu odeslání
    zasady(svet)
