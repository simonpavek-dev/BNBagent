"""Hlavní práce agenta: vyřizování zpráv a návrhy hodnocení hostů."""
import logging
from datetime import datetime, timedelta

import yaml

from . import config, hodiny, instrukce, kody, kontext, mozek, oznameni, trideni, uklidy, znacky, znalosti
from .databaze import Databaze
from .smoobu import Smoobu

log = logging.getLogger("agent")
MAX_POKUSU = 3
POZNAMKY_PATH = config.ROOT / "poznamky-k-hostum.yaml"


def rezim(db):
    """Režim z dashboardu (uložený v databázi) má přednost před REZIM v .env."""
    return db.nastaveni("rezim") or config.REZIM


def aktivni_rezervace(smoobu):
    """Rezervace, u kterých se ještě komunikuje: od budoucích po ty, co skončily před max. 3 dny."""
    dnes = kontext.dnes()
    out = []
    for r in smoobu.reservations(dnes - timedelta(days=60), dnes + timedelta(days=365)):
        if r.get("is-blocked-booking"):
            continue
        odjezd = kontext._datum(r.get("departure"))
        if odjezd and odjezd < dnes - timedelta(days=3):
            continue
        out.append(r)
    return out


def _cekajici_zprava(zpravy, db=None, od=None):
    """Zpráva hosta, na kterou se má odpovědět: poslední zpráva konverzace, pokud je od hosta – nebo nejnovější zpráva
    hosta, za kterou jsou už jen naše zprávy (typicky automatická zpráva Smoobu), pokud ji agent ještě nezpracoval
    a přišla po `od` (nasazení této opravy – staré, dávno vyřízené dotazy se nevytahují)."""
    if zpravy and zpravy[-1].get("type") == 1:
        return zpravy[-1]
    if db is None or not od:
        return None
    posledni_hosta = next((m for m in reversed(zpravy) if m.get("type") == 1), None)
    if (posledni_hosta and str(posledni_hosta.get("createdAt") or "") >= od
            and not db.zprava_vyrizena(posledni_hosta["id"])):
        return posledni_hosta
    return None


def _hranice_nevyrizenych(db):
    """Od kdy hledat zprávy hosta přebité naší (automatickou) zprávou – nastaví se při prvním běhu opravy."""
    od = db.nastaveni("cekajici_od")
    if not od:
        od = hodiny.ted().strftime("%Y-%m-%d %H:%M:%S")
        db.uloz_nastaveni("cekajici_od", od)
    return od


def inicializace(smoobu, db):
    """Při úplně prvním spuštění označí existující nevyřízené zprávy jako 'tvoje', aby agent neodpovídal na staré."""
    stare = 0
    for r in aktivni_rezervace(smoobu):
        z = _cekajici_zprava(smoobu.messages(r["id"]))
        if z:
            db.oznac_zpravu(z["id"], r["id"], "prevzato_pri_startu")
            stare += 1
    db.uloz_nastaveni("inicializovano", "ano")
    oznameni.posli(
        f"🤖 Agent spuštěn (režim: {rezim(db)}). "
        f"Nevyřízených zpráv z doby před spuštěním: {stare} – ty prosím vyřiď sám, agent řeší jen nové."
    )


def vyrid_zpravy(smoobu, db):
    od = _hranice_nevyrizenych(db)
    for r in aktivni_rezervace(smoobu):
        zpravy = smoobu.messages(r["id"])
        zprava = _cekajici_zprava(zpravy, db, od)
        if not zprava or db.zprava_vyrizena(zprava["id"]):
            continue
        try:
            db.uloz_nastaveni("cinnost", f"Zpracovávám zprávu: {_hlavicka(r)}")
            _vyrid_jednu(smoobu, db, r, zpravy, zprava)
        except Exception as e:  # jedna chybná zpráva nesmí zastavit ostatní
            log.exception("Chyba při vyřizování rezervace %s", r.get("id"))
            pokusy = db.zapocitej_chybu(zprava["id"], r["id"])
            if pokusy >= MAX_POKUSU:
                db.oznac_zpravu(zprava["id"], r["id"], "selhalo")
                oznameni.posli(
                    f"⚠️ Agent nedokázal vyřídit zprávu ({pokusy}× chyba), vyřiď ji prosím sám.\n"
                    f"{_hlavicka(r)}\n\nZpráva hosta:\n{zprava.get('message', '')}\n\nChyba: {e}"
                )


def _hlavicka(r):
    return (
        f"{(r.get('apartment') or {}).get('name', '?')} · {r.get('guest-name', '?')} · "
        f"{(r.get('channel') or {}).get('name', '?')} · {r.get('arrival')} → {r.get('departure')} "
        f"(rez. {r.get('id')})"
    )


def _vyrid_jednu(smoobu, db, r, zpravy, zprava):
    apt_id = (r.get("apartment") or {}).get("id")
    apartman, apartman_text = znalosti.apartman_podle_smoobu_id(apt_id)
    if not apartman_text:
        db.oznac_zpravu(zprava["id"], r["id"], "chybi_znalosti")
        oznameni.posli(
            f"❓ Nová zpráva, ale apartmán (Smoobu ID {apt_id}) nemá znalostní bázi – vyřiď sám.\n"
            f"{_hlavicka(r)}\n\n{zprava.get('message', '')}"
        )
        return

    try:
        kod = kody.kod_pro_rezervaci(smoobu, apartman, r)
    except Exception:
        log.exception("Nepodařilo se dopočítat kód keyboxu pro rezervaci %s", r.get("id"))
        kod = None  # agent pak kód neprozradí a případně eskaluje
    text_hosta = trideni.nevyrizeny_text(zpravy)
    if config.ZDVORILOSTI_BEZ_MODELU and trideni.je_zdvorilost(text_hosta):
        vysledek = trideni.odpoved_na_zdvorilost(r, zpravy)  # čisté „díky / 👍“ bez modelu
    else:
        model = None  # None = hlavní model (config.MODEL)
        if config.LEVNEJSI_MODEL_PRO_JEDNODUCHE and trideni.je_jednoducha(text_hosta):
            model = config.MODEL_JEDNODUCHE
        vysledek = zeptej_se_modelu(r, zpravy, apartman, apartman_text, kod, model)
    rozhodnuti = vysledek["rozhodnuti"]
    db.zapis(r["id"], "rozhodnuti", dict(vysledek, hlavicka=_hlavicka(r), zprava_hosta=zprava.get("message", "")))
    odeslano = False

    if (rezim(db) == "ostre" and rozhodnuti in ("odpovedet", "eskalovat") and vysledek["odpoved_hostovi"].strip()
            and not vysledek.get("kontrola")):  # podezřelý kód / zbylá značka → jen ke kontrole
        from .navrhy import odeslat
        navrh_id = db.novy_navrh(r["id"], zprava.get("id"), vysledek["odpoved_hostovi"], vysledek["jazyk_hosta"],
                                 _hlavicka(r))
        odeslano, zprava_brany = odeslat(smoobu, db, db.navrh(navrh_id), "automaticky")  # jediná brána
        if not odeslano:
            db.uprav_navrh(navrh_id, stav="zastarale")
            log.warning("Ostrý režim – neodesláno: %s", zprava_brany)

    db.oznac_zpravu(zprava["id"], r["id"], rozhodnuti)
    _upozorni(db, r, zprava, vysledek, odeslano)
    if odeslano and kod and kod in vysledek["odpoved_hostovi"]:
        oznameni.posli(f"🔑 Agent poslal hostovi kód keyboxu {kod}\n{_hlavicka(r)}\nZkontroluj, že na keyboxu je nastavený.")


def zeptej_se_modelu(r, zpravy, apartman, apartman_text, kod, model=None):
    """Rozhodnutí modelu o zprávě hosta. Kódy a Wi-Fi model nevidí (značky), skutečné hodnoty dosadí kód."""
    hodnoty = znacky.hodnoty(apartman, kod)
    doplnek = "\n\n".join(x for x in (popis_kodu(kod), uklidy.popis_pro_zpravu(r)) if x)
    vysledek = mozek.rozhodni_o_zprave(
        znalosti.obecne_text(), znacky.schovej(apartman_text, apartman, hodnoty),
        znacky.schovej(kontext.sestav(r, zpravy, doplnek), apartman, hodnoty), model=model)
    return znacky.zpracuj(vysledek, hodnoty)


def popis_kodu(kod):
    if kod:
        return ("KÓD KEYBOXU PRO TUTO REZERVACI je známý – v odpovědi místo něj napiš přesně značku [KÓD BYTU], "
                "skutečný kód doplní systém.")
    return "KÓD KEYBOXU PRO TUTO REZERVACI NENÍ ZNÁMÝ – pokud ho host potřebuje, eskaluj (značku [KÓD BYTU] nepiš)."


def _upozorni(db, r, zprava, v, odeslano):
    host_text = zprava.get("message", "").strip()
    hlavicka = _hlavicka(r)
    if v["rozhodnuti"] == "neodpovidat":
        log.info("Bez odpovědi (%s): %s", v["duvod"], hlavicka)
        return
    if v["rozhodnuti"] == "odpovedet" and odeslano:
        log.info("Odpovězeno automaticky: %s", hlavicka)
        return

    navrh_id = db.novy_navrh(r["id"], zprava.get("id"), v["odpoved_hostovi"], v["jazyk_hosta"], hlavicka)
    if v.get("kontrola"):  # podezřelý kód / značka bez hodnoty – sám to neposílám
        text = (f"🔔 ZKONTROLUJ ODPOVĚĎ – sám ji neposílám: {v['kontrola']}\n{hlavicka}\n\n"
                f"Host napsal:\n{host_text}\n\nNavrhuji odpovědět:\n{v['odpoved_hostovi']}")
        if v["rozhodnuti"] == "eskalovat":
            text += f"\n\nProč se ptám: {v['duvod']}\nNávrh pro tebe: {v['navrh_pro_hostitele']}"
        tlacitka = [("✅ Odeslat", f"odeslat:{navrh_id}"), ("✏️ Upravit", f"upravit:{navrh_id}"),
                    ("❌ Neposílat", f"zahodit:{navrh_id}")]
    elif v["rozhodnuti"] == "eskalovat":
        text = (
            f"🔔 POTŘEBUJU TĚ\n{hlavicka}\n\nHost napsal:\n{host_text}\n\n"
            f"Proč: {v['duvod']}\n\nNávrh, jak odpovědět:\n{v['navrh_pro_hostitele']}"
        )
        tlacitka = []
        if odeslano:
            text += f"\n\n(Hostovi jsem zatím poslal: „{v['odpoved_hostovi']}“)"
        elif v["odpoved_hostovi"].strip():
            text += f"\n\nPrůběžná odpověď pro hosta:\n{v['odpoved_hostovi']}"
            tlacitka.append(("✅ Poslat průběžnou odpověď", f"odeslat:{navrh_id}"))
        tlacitka += [("✏️ Napsat odpověď", f"upravit:{navrh_id}"), ("❌ Vyřízeno / neposílat", f"zahodit:{navrh_id}")]
    else:  # režim návrhů
        text = (
            f"✍️ NÁVRH ODPOVĚDI\n{hlavicka}\n\n"
            f"Host napsal:\n{host_text}\n\nNavrhuji odpovědět:\n{v['odpoved_hostovi']}"
        )
        tlacitka = [("✅ Odeslat", f"odeslat:{navrh_id}"), ("✏️ Upravit", f"upravit:{navrh_id}"),
                    ("❌ Neposílat", f"zahodit:{navrh_id}")]
    db.uprav_navrh(navrh_id, tg_message_id=oznameni.posli(text, tlacitka, navrh_id=navrh_id))


# ---------------------------------------------------------------- kontrola kalendáře

def kontrola_kalendare(smoobu, db, dni=365, hlasit_ok=False):
    """Hlídá dvojí rezervace: každá obsazená noc musí být v kalendáři Smoobu zavřená
    a dvě rezervace se v jednom bytě nesmí překrývat. Problémy pošle hostiteli."""
    dnes = kontext.dnes()
    konec = dnes + timedelta(days=dni)
    rezervace = [r for r in smoobu.reservations(dnes - timedelta(days=30), konec)
                 if not r.get("is-blocked-booking") and kontext._datum(r.get("departure")) > dnes]
    problemy = []
    po_bytech = {}
    for r in rezervace:
        po_bytech.setdefault((r.get("apartment") or {}).get("id"), []).append(r)
    for apt_id, rr in po_bytech.items():
        nazev = (rr[0].get("apartment") or {}).get("name", apt_id)
        dostupnost = smoobu._request("GET", "/api/rates", {
            "apartments[]": apt_id, "start_date": dnes.isoformat(), "end_date": konec.isoformat(),
        })["data"].get(str(apt_id), {})
        rr.sort(key=lambda r: r["arrival"])
        for i, r in enumerate(rr):
            den = max(kontext._datum(r["arrival"]), dnes)
            while den < kontext._datum(r["departure"]) and den <= konec:
                if (dostupnost.get(den.isoformat()) or {}).get("available"):
                    problemy.append(f"🔓 {nazev}: noc {den:%d. %m.} je v prodeji, i když ji má {r.get('guest-name')}")
                den += timedelta(days=1)
            for jina in rr[i + 1:]:
                if kontext._datum(jina["arrival"]) < kontext._datum(r["departure"]):
                    problemy.append(f"👥 {nazev}: {r.get('guest-name')} ({r['arrival']}→{r['departure']}) se kryje "
                                    f"s {jina.get('guest-name')} ({jina['arrival']}→{jina['departure']})")
    db.uloz_nastaveni("kontrola_kalendare", datetime_ted())
    db.zapis("", "kontrola_kalendare", {"problemu": len(problemy), "detail": problemy[:30]})
    otisk = "\n".join(sorted(problemy))
    posledni = db.nastaveni("kalendar_hlaseno_cas")
    znovu = not posledni or datetime_ted() > (datetime.fromisoformat(posledni) + timedelta(hours=24)).isoformat()
    if problemy and (hlasit_ok or otisk != db.nastaveni("kalendar_hlaseno", "") or znovu):
        nove = otisk != db.nastaveni("kalendar_hlaseno", "")
        oznameni.posli(("🚨 KONTROLA KALENDÁŘE – hrozí dvojí rezervace" if nove else "🔁 Připomínka – dvojí rezervace pořád trvá")
                       + ":\n" + "\n".join(problemy[:30]) +
                       "\n\nZkontroluj ve Smoobu i Bookings → Filters → Status → Overbooking.")
        db.uloz_nastaveni("kalendar_hlaseno_cas", datetime_ted())
    elif not problemy and db.nastaveni("kalendar_hlaseno"):
        oznameni.posli("✅ Kontrola kalendáře: dřív hlášené dvojí rezervace už jsou vyřešené.")
    elif hlasit_ok:
        oznameni.posli(f"✅ Kontrola kalendáře: {len(rezervace)} rezervací v {len(po_bytech)} bytech, "
                       "všechny obsazené noci jsou zavřené a nic se nepřekrývá.")
    db.uloz_nastaveni("kalendar_hlaseno", otisk)
    return problemy


def datetime_ted():
    return hodiny.ted_iso()


# ---------------------------------------------------------------- instrukce k příjezdu

KANALY_SE_ZPRAVAMI = ("airbnb", "booking.com")


def priprav_prijezdy(smoobu, db, den=None):
    """Pro příjezdy v daný den (výchozí dnes) připraví instrukce ke check-inu a pošle je hostiteli ke schválení.
    Po schválení se odešlou v den příjezdu v PRIJEZD_ODESLAT_HODINA (nebo hned, pokud ten čas už minul)."""
    from datetime import datetime, time as cas
    from .navrhy import TLACITKA_NAVRHU, kdy
    den = den or kontext.dnes()
    odeslat_po = datetime.combine(den, cas(config.PRIJEZD_ODESLAT_HODINA))
    odeslat_po = odeslat_po.isoformat(timespec="seconds") if odeslat_po > hodiny.ted() else None
    for r in smoobu.reservations(den, den):
        if r.get("is-blocked-booking") or db.nastaveni(f"prijezd_{r['id']}") == "hotovo":
            continue
        db.uloz_nastaveni("cinnost", f"Připravuji instrukce k příjezdu: {_hlavicka(r)}")
        apartman, apartman_text = znalosti.apartman_podle_smoobu_id((r.get("apartment") or {}).get("id"))
        if not apartman_text:
            oznameni.posli(f"❓ Dnes přijíždí host, ale apartmán nemá znalostní bázi – instrukce pošli sám.\n{_hlavicka(r)}")
            db.uloz_nastaveni(f"prijezd_{r['id']}", "hotovo")
            continue
        try:
            kod = kody.kod_pro_rezervaci(smoobu, apartman, r)
            # kódy, Wi-Fi, adresu a časy dosadí kód ze šablony, model nanejvýš přeloží
            v = instrukce.priprav(apartman, r, kod, smoobu.messages(r["id"]))
        except uklidy.UklidyChyba as e:  # výpadek aplikace úklidů hlásí hlavní smyčka jednou denně
            log.warning("Instrukce k příjezdu pro %s počkají, kód nejde ověřit: %s", r.get("id"), e)
            continue
        except Exception as e:
            log.exception("Instrukce k příjezdu pro %s selhaly", r.get("id"))
            oznameni.posli(f"⚠️ Nepodařilo se připravit instrukce k příjezdu – pošli je prosím sám.\n{_hlavicka(r)}\nChyba: {e}")
            continue
        db.uloz_nastaveni(f"prijezd_{r['id']}", "hotovo")
        db.zapis(r["id"], "instrukce_prijezd", dict(v, hlavicka=_hlavicka(r), kod=kod,
                                                    smoobu_id=str((r.get("apartment") or {}).get("id"))))
        if not v["poslat"] and v.get("zprava"):  # ve znalostní bázi chybí údaj – návrh s mezerami pro hostitele
            oznameni.posli(f"⚠️ Instrukce k příjezdu NEJDE poslat – {v['duvod']}. Doplň údaj do znalostní báze "
                           f"(třeba „Vasile, …“) a instrukce pošli sám:\n{_hlavicka(r)}\n\n{v['zprava']}")
            continue
        if not v["poslat"]:
            oznameni.posli(f"ℹ️ Instrukce k příjezdu neposílám: {v['duvod']}\n{_hlavicka(r)}")
            continue
        if v.get("poznamka"):
            oznameni.posli(f"ℹ️ {v['poznamka']}\n{_hlavicka(r)}")
        kanal = (r.get("channel") or {}).get("name", "").lower()
        if any(k in kanal for k in KANALY_SE_ZPRAVAMI):
            navrh_id = db.novy_navrh(r["id"], "", v["zprava"], v["jazyk_hosta"], _hlavicka(r), odeslat_po)
            if config.PRIJEZDY_AUTOMATICKY:  # instrukce odchází samy, hostitelé je mohou jen zrušit
                from .navrhy import odeslat
                if odeslat_po:
                    db.uprav_navrh(navrh_id, stav="schvaleno")
                    db.uprav_navrh(navrh_id, tg_message_id=oznameni.posli(
                        f"🔑 INSTRUKCE K PŘÍJEZDU {den.day}. {den.month}. – odešlu je hostovi sám {kdy(odeslat_po)} "
                        f"(kód {kod})\n{_hlavicka(r)}\n\n{v['zprava']}",
                        [("❌ Zrušit odeslání", f"zahodit:{navrh_id}")], navrh_id=navrh_id))
                else:
                    try:
                        _, zprava = odeslat(smoobu, db, db.navrh(navrh_id), "automaticky")
                        oznameni.posli(f"{zprava} – instrukce k příjezdu (kód {kod})\n\n{v['zprava']}")
                    except Exception as e:
                        db.uprav_navrh(navrh_id, stav="selhalo")
                        oznameni.posli(f"⚠️ Instrukce k příjezdu se NEPODAŘILO odeslat (Smoobu: {str(e)[:200]}). "
                                       f"Pošli je prosím ručně:\n{_hlavicka(r)}\n\n{v['zprava']}")
                continue
            planek = f"po schválení odešlu {kdy(odeslat_po)}" if odeslat_po else "po schválení odešlu hned"
            db.uprav_navrh(navrh_id, tg_message_id=oznameni.posli(
                f"🔑 INSTRUKCE K PŘÍJEZDU {den.day}. {den.month}. – kód keyboxu {kod} ({planek})\n"
                f"{_hlavicka(r)}\n\n{v['zprava']}",
                TLACITKA_NAVRHU(navrh_id, odeslat_po), navrh_id=navrh_id))
        else:
            oznameni.posli(
                f"📋 INSTRUKCE K PŘÍJEZDU – ZKOPÍRUJ A POŠLI SÁM (rezervace není napojená na Airbnb/Booking, "
                f"agent ji odeslat nemůže) – kód keyboxu {kod}\n{_hlavicka(r)}\n\n{v['zprava']}")


# ---------------------------------------------------------------- hodnocení hostů

def _poznamky_k_hostum():
    if not POZNAMKY_PATH.exists():
        return {}
    return {str(k): v for k, v in (yaml.safe_load(POZNAMKY_PATH.read_text(encoding="utf-8")) or {}).items()}


def navrhni_hodnoceni(smoobu, db):
    """Pro hosty z Airbnb, kteří odjeli včera nebo předevčírem, připraví návrh hodnocení."""
    dnes = kontext.dnes()
    poznamky = _poznamky_k_hostum()
    for r in aktivni_rezervace(smoobu):
        odjezd = kontext._datum(r.get("departure"))
        kanal = (r.get("channel") or {}).get("name", "").lower()
        if not odjezd or not (dnes - timedelta(days=2) <= odjezd < dnes):
            continue
        if "airbnb" not in kanal or db.hodnoceni_hotovo(r["id"]):
            continue
        db.uloz_nastaveni("cinnost", f"Připravuji hodnocení hosta: {_hlavicka(r)}")
        _, apartman_text = znalosti.apartman_podle_smoobu_id((r.get("apartment") or {}).get("id"))
        poznamka = poznamky.get(str(r["id"]), "")
        doplnek = "POZNÁMKY HOSTITELE / ÚKLIDU K TOMUTO POBYTU:\n" + (poznamka or "(žádné)")
        try:
            v = mozek.navrhni_hodnoceni(
                znalosti.obecne_text(), apartman_text or "(chybí)",
                kontext.sestav(r, smoobu.messages(r["id"]), doplnek),
            )
        except Exception:
            log.exception("Nepodařilo se připravit hodnocení pro %s", r.get("id"))
            continue
        db.zapis(r["id"], "hodnoceni", v)
        db.oznac_hodnoceni(r["id"])
        varovani = f"⚠️ ZKONTROLUJ: {v['poznamka_pro_hostitele']}\n\n" if v["zkontrolovat"] else ""
        oznameni.posli(
            f"⭐ NÁVRH HODNOCENÍ HOSTA – zkopíruj do Airbnb (Hodnocení → Napsat hodnocení)\n"
            f"{_hlavicka(r)}\n\n{varovani}"
            f"Čistota {v['cistota']}/5 · Pravidla {v['dodrzovani_pravidel']}/5 · "
            f"Komunikace {v['komunikace']}/5 · Doporučit: {'ano' if v['doporucit'] else 'ne'}\n\n"
            f"Veřejné hodnocení:\n{v['verejne_hodnoceni']}\n\n"
            f"Soukromá zpráva hostovi:\n{v['soukroma_zprava_hostovi']}"
        )


def upozorni_na_odmitnuti(db, chyba):
    """401 ze Smoobu = hned upozornit hostitele, nejvýš jednou za hodinu."""
    posledni = db.nastaveni("smoobu_odmitnuti_cas")
    if posledni and datetime.fromisoformat(posledni) > hodiny.ted() - timedelta(hours=1):
        return
    db.uloz_nastaveni("smoobu_odmitnuti_cas", datetime_ted())
    db.zapis("", "chyba", str(chyba))
    oznameni.posli(f"🔐 Smoobu odmítá ověření – agent nečte ani neposílá zprávy.\nDůvod: {str(chyba).split('401: ', 1)[-1]}")


def vytvor_smoobu():
    return Smoobu(config.SMOOBU_API_KEY, config.SMOOBU_API_SECRET,
                  pri_odmitnuti=lambda chyba: upozorni_na_odmitnuti(vytvor_db(), chyba))


def vytvor_db():
    return Databaze()
