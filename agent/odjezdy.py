"""Zprávy k odjezdu (P3.2, DECISIONS.md D6): text ze šablony, údaje doplní kód, model nanejvýš přeloží (jako instrukce).

- ZPRAVA_PRED_ODJEZDEM: večer před odjezdem (ZPRAVA_PRED_ODJEZDEM_HODINA, 18:00) připomenutí check-outu (čas a postup
  ze znalostní báze), poděkování a hostům z Airbnb sleva na další pobyt (SLEVA_NA_DALSI_POBYT_PROCENT, 0 = bez slevy).
- PROSBA_O_HODNOCENI: v den odjezdu (PROSBA_O_HODNOCENI_HODINA, 12:00 – po check-outu, kdy Airbnb hodnocení otevře)
  poděkování a prosba o hodnocení.

Sleva nesmí záviset na hodnocení (pravidla recenzí Airbnb a Bookingu) – zprávy na sebe neodkazují. Obě se připraví
2 hodiny předem a odejdou samy, hostitelé je ve skupině mohou zrušit; prosba o hodnocení po eskalaci během pobytu jen
ke schválení. Podpis mají vždy (konec konverzace). Pobyt na 1 noc večerní zprávu nedostane (přišla by pár hodin po
instrukcích). Když host už ten den od nás zprávu na stejné téma dostal (např. automatickou zprávu Smoobu), agent ji
neposílá a dá vědět. Šablony lze přepsat v obecne.yaml (sablona_zpravy_pred_odjezdem, sablona_slevy_na_dalsi_pobyt,
sablona_prosby_o_hodnoceni). Volá hlavní smyčka (`__main__.jeden_cyklus`).
"""
import logging
from datetime import datetime, time as cas, timedelta

from . import config, hodiny, instrukce, kontext, oznameni, podpis, znalosti

log = logging.getLogger("agent")
PRIPRAVIT_HODIN_PREDEM = 2   # hostitelé mají čas odeslání zrušit
POZDE_PO_HODINACH = 3        # agent neběžel – později už neposílat (jako navrhy.PROSLE_PO_HODINACH)

PRED_ODJEZDEM = """Hi {jmeno},

just a friendly reminder that tomorrow is your departure day – check-out is by {check_out}{odjezd_postup}

Thank you so much for staying with us, we hope you have enjoyed Prague!{sleva}

Have a lovely last evening!

{podpis}"""

SLEVA = ("\n\nIf you would like to come back one day, just message us here before booking – as a returning guest "
         "you get {procent} % off your next stay in any of our apartments.")

PROSBA_O_HODNOCENI = """Hi {jmeno},

thank you once more for staying with us! If you enjoyed your stay, we would be very grateful for a review – it helps us a lot.

Safe travels home!

{podpis}"""

DRUHY = {
    # druh: (název pro hostitele, ikona, klíč v nastavení, slova v naší zprávě, podle kterých host téma už dostal)
    "pred_odjezdem": ("ZPRÁVA PŘED ODJEZDEM", "👋", "odjezd_zprava", ("check-out", "checkout", "check out")),
    "hodnoceni": ("PROSBA O HODNOCENÍ", "⭐", "prosba_hodnoceni",
                  ("review", "hodnocení", "recenz", "bewertung", "valutazione", "reseña", "avis", "opini")),
}


def zkontroluj(smoobu, db):
    """Každý cyklus: připraví zprávy k odjezdu, kterým se blíží čas odeslání."""
    ted = hodiny.ted()
    ulohy = []
    if config.ZPRAVA_PRED_ODJEZDEM:
        ulohy.append(("pred_odjezdem", ted.date() + timedelta(days=1), config.ZPRAVA_PRED_ODJEZDEM_HODINA))
    if config.PROSBA_O_HODNOCENI:
        ulohy.append(("hodnoceni", ted.date(), config.PROSBA_O_HODNOCENI_HODINA))
    ulohy = [(druh, den, datetime.combine(ted.date(), cas(hodina))) for druh, den, hodina in ulohy]
    ulohy = [u for u in ulohy if u[2] - timedelta(hours=PRIPRAVIT_HODIN_PREDEM) <= ted
             < u[2] + timedelta(hours=POZDE_PO_HODINACH)]
    if not ulohy:
        return
    from . import prace  # prace → instrukce/uklidy…; import až za běhu
    rezervace = prace.aktivni_rezervace(smoobu)
    for druh, den_odjezdu, odeslat_v in ulohy:
        for r in rezervace:
            if kontext._datum(r.get("departure")) == den_odjezdu and not r.get("is-blocked-booking"):
                _priprav(smoobu, db, r, druh, odeslat_v)


def _noci(r):
    prijezd, odjezd = kontext._datum(r.get("arrival")), kontext._datum(r.get("departure"))
    return (odjezd - prijezd).days if prijezd and odjezd else None


def _uz_dostal(zpravy, slova, den):
    """Naše zpráva z daného dne na stejné téma (např. automatická zpráva Smoobu) – čas zprávy, nebo None."""
    for m in reversed(zpravy):
        text = (m.get("message") or "").lower()
        if (m.get("type") != 1 and str(m.get("createdAt") or "").startswith(den.isoformat())
                and any(s in text for s in slova)):
            return str(m.get("createdAt"))[11:16] or "dnes"
    return None


def _byla_eskalace(db, reservation_id):
    return db.conn.execute("SELECT 1 FROM zpravy WHERE reservation_id = ? AND stav = 'eskalovat' LIMIT 1",
                           (str(reservation_id),)).fetchone() is not None


def sestav(druh, apartman, r):
    """Anglická zpráva ze šablony. Vrací (text, chybějící údaje, klíčové údaje, které musí zůstat v překladu)."""
    obecne = znalosti.obecne()
    hodnoty = {"jmeno": instrukce._jmeno(r), "podpis": podpis.cely()}
    klicove = []
    if druh == "pred_odjezdem":
        odjezd = (apartman or {}).get("odjezd") or {}
        postup = str(odjezd.get("postup_en") or "").strip()
        procent = config.SLEVA_NA_DALSI_POBYT_PROCENT
        sleva = ""
        if procent > 0 and "airbnb" in ((r.get("channel") or {}).get("name") or "").lower():
            sleva = str(obecne.get("sablona_slevy_na_dalsi_pobyt") or SLEVA).rstrip().format(procent=procent)
            klicove.append(f"{procent}")
        hodnoty.update(check_out=str(odjezd.get("check_out_do") or "").strip(),
                       odjezd_postup=f" – {postup}" if postup else ".", sleva=sleva)
        klicove.append(hodnoty["check_out"])
        sablona = obecne.get("sablona_zpravy_pred_odjezdem") or PRED_ODJEZDEM
    else:
        sablona = obecne.get("sablona_prosby_o_hodnoceni") or PROSBA_O_HODNOCENI
    chybi = [nazev for klic, nazev in (("check_out", "čas check-outu (odjezd.check_out_do)"), ("podpis", "podpis"))
             if klic in hodnoty and not hodnoty[klic]]
    return str(sablona).strip().format(**hodnoty), chybi, [k for k in klicove if k]


def _priprav(smoobu, db, r, druh, odeslat_v):
    from . import navrhy, prace
    nazev, ikona, klic, slova = DRUHY[druh]
    klic = f"{klic}_{r['id']}"
    if db.nastaveni(klic):
        return
    db.uloz_nastaveni(klic, "hotovo")  # každá rezervace nejvýš jednou, i když se něco pokazí
    hlavicka = prace._hlavicka(r)
    kanal = ((r.get("channel") or {}).get("name") or "").lower()
    if not any(k in kanal for k in prace.KANALY_SE_ZPRAVAMI):
        db.zapis(r["id"], "odjezd", f"{nazev}: rezervace není z Airbnb/Bookingu – neposílám")
        return
    if druh == "pred_odjezdem" and (_noci(r) or 0) <= 1:
        db.zapis(r["id"], "odjezd", f"{nazev}: pobyt na 1 noc – neposílám (check-out je v instrukcích)")
        return
    dnes = hodiny.dnes()
    uz = _uz_dostal(smoobu.messages(r["id"]), slova, dnes)
    if uz:
        oznameni.posli(f"ℹ️ {nazev} neposílám – host už dnes v {uz} od nás dostal zprávu na stejné téma (nejspíš "
                       f"automatickou zprávu Smoobu). Jestli ji Smoobu posílá samo, nechte zapnutou jen jednu.\n{hlavicka}")
        return
    apartman, _ = znalosti.apartman_podle_smoobu_id((r.get("apartment") or {}).get("id"))
    text, chybi, klicove = sestav(druh, apartman, r)
    if chybi:
        oznameni.posli(f"⚠️ {nazev} NEJDE poslat – ve znalostní bázi chybí: {', '.join(chybi)}.\n{hlavicka}")
        return
    zprava, jazyk, poznamka = instrukce._preloz(text, instrukce._jazyk(r), [], klicove)
    if poznamka:
        oznameni.posli(f"ℹ️ {poznamka}\n{hlavicka}")
    odeslat_po = odeslat_v.isoformat(timespec="seconds") if odeslat_v > hodiny.ted() else None
    navrh_id = db.novy_navrh(r["id"], "", zprava, jazyk, hlavicka, odeslat_po)
    db.zapis(r["id"], "odjezd", {"druh": druh, "navrh_id": navrh_id, "jazyk": jazyk})

    if druh == "hodnoceni" and _byla_eskalace(db, r["id"]):  # nespokojeného hosta o hodnocení neprosit bez schválení
        planek = f"po schválení odešlu {navrhy.kdy(odeslat_po)}" if odeslat_po else "po schválení odešlu hned"
        db.uprav_navrh(navrh_id, tg_message_id=oznameni.posli(
            f"{ikona} {nazev} – během pobytu byla eskalace, sám ji neposílám ({planek})\n{hlavicka}\n\n{zprava}",
            navrhy.TLACITKA_NAVRHU(navrh_id, odeslat_po), navrh_id=navrh_id))
        return
    if odeslat_po:
        db.uprav_navrh(navrh_id, stav="schvaleno")
        db.uprav_navrh(navrh_id, tg_message_id=oznameni.posli(
            f"{ikona} {nazev} – odešlu ji hostovi sám {navrhy.kdy(odeslat_po)}\n{hlavicka}\n\n{zprava}",
            [("❌ Zrušit odeslání", f"zahodit:{navrh_id}")], navrh_id=navrh_id))
        return
    try:  # čas odeslání už minul (agent neběžel) – nejvýš o POZDE_PO_HODINACH
        _, vysledek = navrhy.odeslat(smoobu, db, db.navrh(navrh_id), "automaticky")
    except Exception as e:
        log.exception("%s pro %s se nepodařilo odeslat", nazev, r.get("id"))
        db.uprav_navrh(navrh_id, stav="selhalo")
        vysledek = f"⚠️ {nazev} se NEPODAŘILO odeslat ({str(e)[:150]}) – pošli ji prosím ručně"
    oznameni.posli(f"{vysledek} – {nazev.lower()}\n\n{zprava}")
