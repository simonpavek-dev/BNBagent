"""Ovládání agenta z příkazové řádky.

    python -m agent kontrola                 # zkontroluje nastavení a znalostní bázi
    python -m agent zkouska _priklad "Kde můžu zaparkovat?"   # vyzkouší odpověď bez Smoobu
    python -m agent apartmany                # vypíše apartmány ze Smoobu a jejich ID
    python -m agent nacist-smoobu            # předvyplní znalostní bázi ze Smoobu + stáhne historii zpráv
    python -m agent spustit                  # spustí agenta (běží nepřetržitě)
    python -m agent hodnoceni                # hned připraví návrhy hodnocení hostů
    python -m agent prijezdy                 # hned připraví instrukce k dnešním příjezdům
    python -m agent dashboard                # ovládací panel na http://localhost:8765
"""
import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta

from . import config, hodiny, kontext, mozek, navrhy, odchozi, oznameni, prace, telegram_ovladani, uklidy, znalosti
from .smoobu import SmoobuOvereni


def nastav_log():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(config.LOG_PATH, encoding="utf-8"), logging.StreamHandler()],
    )
    for hlucny in ("httpx", "httpcore", "urllib3", "anthropic"):
        logging.getLogger(hlucny).setLevel(logging.WARNING)


def kontrola(_args):
    ok = True
    print(f"Režim: {config.REZIM}  ·  Model: {config.MODEL}  ·  Interval: {config.INTERVAL_MINUT} min")
    for nazev, hodnota in [
        ("ANTHROPIC_API_KEY", os.getenv("ANTHROPIC_API_KEY")),
        ("SMOOBU_API_KEY", config.SMOOBU_API_KEY),
        ("TELEGRAM_BOT_TOKEN", config.TELEGRAM_BOT_TOKEN),
        ("TELEGRAM_CHAT_ID", config.TELEGRAM_CHAT_ID),
    ]:
        print(f"  {'✅' if hodnota else '❌'} {nazev}")
        ok = ok and bool(hodnota)
    print(f"  {'✅' if config.SMOOBU_API_SECRET else '❌'} SMOOBU_API_SECRET")
    if not config.SMOOBU_API_SECRET:
        print("     Bez něj agent Smoobu nepoužije – staré ověřování (Api-Key) Smoobu 31. 10. 2026 vypíná.")
        ok = False
    elif config.SMOOBU_API_KEY:
        spojeni_ok, text = prace.vytvor_smoobu().over_pripojeni()  # skutečné volání GET /api/apartments
        print(f"  {'✅' if spojeni_ok else '❌'} {text}")
        ok = ok and spojeni_ok
    if config.REZIM not in ("navrh", "ostre"):
        print("  ❌ REZIM musí být 'navrh' nebo 'ostre'")
        ok = False

    print("\nZnalostní báze apartmánů:")
    for soubor, data in znalosti.vsechny_apartmany():
        chybi = [k for k in ("smoobu_id", "nazev", "adresa") if not str(data.get(k) or "").strip()]
        stav = "✅" if not chybi else "⚠️  chybí: " + ", ".join(chybi)
        print(f"  {soubor}: {data.get('nazev') or '(bez názvu)'}  {stav}")
    print("\nVše připraveno ✅" if ok else "\nNěco chybí – doplň .env (viz README).")


def zkouska(args):
    obecne_text = znalosti.obecne_text()
    apartman, apartman_text = znalosti.apartman_podle_souboru(args.apartman)
    if not apartman_text:
        sys.exit(f"Soubor znalostni-baze/apartmany/{args.apartman}.yaml neexistuje.")
    dnes = kontext.dnes()
    rezervace = {
        "id": "TEST", "channel": {"name": args.kanal}, "guest-name": "Testovací host",
        "arrival": (dnes + timedelta(days=args.prijezd_za)).isoformat(),
        "departure": (dnes + timedelta(days=args.prijezd_za + 3)).isoformat(),
        "adults": 2, "children": 0,
    }
    zpravy = [{"type": 1, "message": args.zprava, "createdAt": hodiny.ted().strftime("%Y-%m-%d %H:%M")}]
    kod = ((apartman or {}).get("prijezd") or {}).get("keybox_kod")  # při zkoušce výchozí kód
    v = mozek.rozhodni_o_zprave(obecne_text, apartman_text, kontext.sestav(rezervace, zpravy, prace.popis_kodu(kod)))
    print(json.dumps(v, ensure_ascii=False, indent=2))


def apartmany(_args):
    for a in prace.vytvor_smoobu().apartments():
        print(f"  smoobu_id: {a.get('id'):<10}  {a.get('name')}")


def _krok(db, popis, fn, *args):
    """Spustí jeden krok cyklu agenta; chybu zaloguje a vrátí False, ostatní kroky běží dál."""
    try:
        fn(*args)
        return True
    except Exception as e:
        logging.getLogger("agent").exception("Chyba v kroku: %s", popis)
        db.zapis("", "chyba", f"{popis}: {e}")
        return False


def jeden_cyklus(smoobu, db):
    """Jeden průchod agenta: zprávy hostů, instrukce k příjezdu, úklidy, naplánované zprávy, kalendář, hodnocení.
    Chyba ve vyřizování zpráv se propaguje (smyčka ji počítá); ostatní kroky jsou na sobě nezávislé."""
    log = logging.getLogger("agent")
    _krok(db, "fronta upozornění", oznameni.dorucit_frontu, db)  # i když Smoobu nejde
    db.uloz_nastaveni("cinnost", "Kontroluji nové zprávy ve Smoobu…")
    prace.vyrid_zpravy(smoobu, db)
    ted = hodiny.ted()
    db.uloz_nastaveni("posledni_kontrola", ted.isoformat(timespec="seconds"))
    # instrukce k příjezdu: dnešní (pokud se nestihly včera) a večer i zítřejší; každý příjezd jen jednou
    # další kroky jsou na sobě nezávislé – chyba v jednom nesmí zastavit ostatní
    _krok(db, "instrukce k příjezdu", prace.priprav_prijezdy, smoobu, db)
    if ted.hour >= config.PRIJEZD_HODINA:
        _krok(db, "instrukce na zítřek", prace.priprav_prijezdy, smoobu, db, kontext.dnes() + timedelta(days=1))
    try:  # aplikace úklidů: změny kódů, problémy, je byt k příjezdu uklizený?
        uklidy.zkontroluj(smoobu, db)
    except uklidy.UklidyChyba as e:
        log.warning("%s", e)
        if db.nastaveni("uklidy_chyba_den") != ted.date().isoformat():
            oznameni.posli(f"⚠️ {e} – kódy z ní teď nejde ověřit, instrukce s kódem neodešlu.")
            db.uloz_nastaveni("uklidy_chyba_den", ted.date().isoformat())
    except Exception:
        log.exception("Chyba v kontrole úklidů")
    _krok(db, "naplánované zprávy", navrhy.odesli_naplanovane, smoobu, db)
    _krok(db, "ověření nejistých odeslání", odchozi.over_nejiste, smoobu, db)
    posledni_kk = db.nastaveni("kontrola_kalendare")
    if config.KONTROLA_KALENDARE and (
            not posledni_kk or ted - datetime.fromisoformat(posledni_kk) > timedelta(hours=config.KONTROLA_KALENDARE_HODIN)):
        _krok(db, "kontrola kalendáře", prace.kontrola_kalendare, smoobu, db)  # hlásí jen problémy
    if (config.HODNOCENI_HOSTU and ted.hour >= config.HODNOCENI_HODINA
            and db.nastaveni("hodnoceni_den") != ted.date().isoformat()):
        if _krok(db, "návrhy hodnocení", prace.navrhni_hodnoceni, smoobu, db):
            db.uloz_nastaveni("hodnoceni_den", ted.date().isoformat())
    return ted


def spustit(_args):
    if not config.SMOOBU_API_SECRET:
        sys.exit("❌ Chybí SMOOBU_API_SECRET v .env – agent bez něj nepoběží (staré ověřování Api-Key Smoobu "
                 "31. 10. 2026 vypíná). Secret vytvoříš ve Smoobu: Settings → Advanced → API Keys → Generate Secret.")
    import fcntl
    zamek = open(config.DATA_DIR / "agent.lock", "w")
    try:
        fcntl.flock(zamek, fcntl.LOCK_EX | fcntl.LOCK_NB)  # drží se po celou dobu běhu
    except OSError:
        sys.exit("Agent už běží (nejspíš automaticky na pozadí). Druhou instanci nespouštím.")
    nastav_log()
    log = logging.getLogger("agent")
    smoobu, db = prace.vytvor_smoobu(), prace.vytvor_db()
    if db.nastaveni("inicializovano") != "ano":
        prace.inicializace(smoobu, db)
    log.info("Agent běží (režim %s, kontrola každé %s min). Ukončíš Ctrl+C.", prace.rezim(db), config.INTERVAL_MINUT)
    chyby_za_sebou = 0
    dalsi_kontrola = 0.0
    posledni_tik = time.time()
    spanek_od = None  # kdy Mac usnul (poznáme podle mezery v běhu smyčky)
    while True:
        if time.time() - posledni_tik > 300:  # smyčka stála > 5 min = Mac spal
            spanek_od = spanek_od or posledni_tik
            chyby_za_sebou = 0
            dalsi_kontrola = 0.0  # po probuzení hned zkontrolovat zprávy
        posledni_tik = time.time()
        if time.time() >= dalsi_kontrola:
            dalsi_kontrola = time.time() + config.INTERVAL_MINUT * 60
            try:
                ted = jeden_cyklus(smoobu, db)
                chyby_za_sebou = 0
                if spanek_od:
                    od = datetime.fromtimestamp(spanek_od)
                    if time.time() - spanek_od > 30 * 60:
                        oznameni.posli(f"💤 Mac spal od {od:%d. %m. %H:%M} do {ted:%H:%M} – agent mezitím neběžel. "
                                       "Zprávy, které přišly, teď dohnal.")
                    db.zapis("", "spanek", f"Mac spal od {od:%d. %m. %H:%M} do {ted:%H:%M}")
                    spanek_od = None
            except Exception as e:
                if spanek_od:  # chyba při krátkém probuzení Macu ze spánku (Power Nap) – nepočítat
                    log.warning("Kontrola během spánku Macu se nepovedla: %s", e)
                    dalsi_kontrola = 0.0
                    time.sleep(10)
                    continue
                chyby_za_sebou += 1
                log.exception("Chyba v cyklu agenta")
                db.zapis("", "chyba", f"Chyba při kontrole zpráv: {e}")
                if chyby_za_sebou == 5 and not isinstance(e, SmoobuOvereni):  # 401 se hlásí hned (prace.upozorni_na_odmitnuti)
                    oznameni.posli(f"⚠️ Agent má opakovaně potíže (např. Smoobu nedostupné): {e}")
        db.uloz_nastaveni("cinnost", "Čekám na nové zprávy hostů")
        # mezi kontrolami Smoobu reaguje na tlačítka a zprávy z Telegramu (okamžitě)
        if oznameni.telegram_zapnuty():
            try:
                telegram_ovladani.zpracuj(smoobu, db, cekat=max(1, min(20, int(dalsi_kontrola - time.time()))))
            except Exception:
                log.exception("Chyba při čtení Telegramu")
                time.sleep(10)
        else:
            time.sleep(max(1, dalsi_kontrola - time.time()))


def hodnoceni(_args):
    nastav_log()
    prace.navrhni_hodnoceni(prace.vytvor_smoobu(), prace.vytvor_db())


def nacist_smoobu(_args):
    from . import import_smoobu
    smoobu = prace.vytvor_smoobu()
    print("Vytvářím znalostní bázi ze Smoobu…")
    soubory, globalni = import_smoobu.vytvor_soubory(smoobu)
    for soubor, stav in soubory:
        print(f"  {soubor}.yaml – {stav}")
    if globalni:
        print("\nGlobální texty ve Smoobu (platí pro všechny byty):")
        for p in globalni:
            print(f"  {p.get('key')}: {p.get('defaultValue')}")
    print("\nStahuji historii konverzací s hosty za poslední rok…")
    for apt, pocet in import_smoobu.export_historie(smoobu).items():
        print(f"  {apt}: {pocet} konverzací")
    print(f"\nHotovo. Historie je ve složce {import_smoobu.HISTORIE_DIR}")


def prijezdy(args):
    nastav_log()
    den = kontext.dnes() + timedelta(days=1 if args.zitra else 0)
    prace.priprav_prijezdy(prace.vytvor_smoobu(), prace.vytvor_db(), den)


def kontrola_kalendare(_args):
    nastav_log()
    problemy = prace.kontrola_kalendare(prace.vytvor_smoobu(), prace.vytvor_db(), hlasit_ok=True)
    print("\n".join(problemy) or "Kalendář je v pořádku.")


def dashboard(_args):
    nastav_log()
    from . import dashboard as panel
    panel.spust()


def main():
    p = argparse.ArgumentParser(prog="python -m agent", description="AI agent pro Airbnb/Booking přes Smoobu")
    sub = p.add_subparsers(dest="prikaz", required=True)
    sub.add_parser("kontrola").set_defaults(fn=kontrola)
    z = sub.add_parser("zkouska")
    z.add_argument("apartman", help="název souboru apartmánu bez .yaml, např. apt-01 nebo _priklad")
    z.add_argument("zprava", help="zpráva od hosta")
    z.add_argument("--prijezd-za", type=int, default=5, help="za kolik dní host přijede (výchozí 5)")
    z.add_argument("--kanal", default="Airbnb")
    z.set_defaults(fn=zkouska)
    sub.add_parser("apartmany").set_defaults(fn=apartmany)
    sub.add_parser("nacist-smoobu").set_defaults(fn=nacist_smoobu)
    sub.add_parser("spustit").set_defaults(fn=spustit)
    sub.add_parser("hodnoceni").set_defaults(fn=hodnoceni)
    sub.add_parser("dashboard").set_defaults(fn=dashboard)
    sub.add_parser("kontrola-kalendare").set_defaults(fn=kontrola_kalendare)
    pr = sub.add_parser("prijezdy")
    pr.add_argument("--zitra", action="store_true", help="připravit instrukce pro zítřejší příjezdy")
    pr.set_defaults(fn=prijezdy)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
