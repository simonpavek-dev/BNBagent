"""Akce s návrhy odpovědí – společné pro Telegram i dashboard."""
from datetime import datetime

from . import mozek, oznameni, uklidy


def kdy(odeslat_po):
    d = datetime.fromisoformat(odeslat_po)
    return f"{d.day}. {d.month}. v {d:%H:%M}"


def TLACITKA_NAVRHU(navrh_id, odeslat_po=None):
    schvalit = f"✅ Schválit – odešlu {kdy(odeslat_po)}" if odeslat_po else "✅ Odeslat"
    return [(schvalit, f"odeslat:{navrh_id}"), ("✏️ Upravit", f"upravit:{navrh_id}"),
            ("❌ Neposílat", f"zahodit:{navrh_id}")]


def _kdo(kdo):
    """Doplněk ke zprávě ve skupině: kdo akci provedl (prázdné = neznámo, např. z panelu)."""
    return f" ({kdo})" if kdo else ""


def schvalit(smoobu, db, navrh, zdroj, kdo=""):
    """✅ z Telegramu/panelu: buď hned odešle, nebo naplánuje na čas odeslat_po."""
    if navrh["stav"] != "ceka":
        return False, "Tenhle návrh už je vyřízený."
    if navrh.get("odeslat_po") and datetime.fromisoformat(navrh["odeslat_po"]) > datetime.now():
        db.uprav_navrh(navrh["id"], stav="schvaleno")
        db.zapis(navrh["reservation_id"], "naplanovano", f"Odeslání naplánováno na {navrh['odeslat_po']}")
        oznameni.odeber_tlacitka(navrh["tg_message_id"])
        oznameni.posli(f"🕙 Schváleno{_kdo(kdo)} – hostovi to odešlu {kdy(navrh['odeslat_po'])}.\n{navrh['hlavicka']}",
                       [("❌ Zrušit odeslání", f"zahodit:{navrh['id']}")])
        return True, ""
    return odeslat(smoobu, db, navrh, zdroj, kdo)


def odesli_naplanovane(smoobu, db):
    """Odešle schválené návrhy, kterým nastal čas odeslání."""
    ted = datetime.now().isoformat(timespec="seconds")
    for (navrh_id,) in db.conn.execute(
            "SELECT id FROM navrhy WHERE stav = 'schvaleno' AND odeslat_po <= ?", (ted,)).fetchall():
        _, zprava = odeslat(smoobu, db, db.navrh(navrh_id), "planovace")
        oznameni.posli(zprava)


def odeslat(smoobu, db, navrh, zdroj, kdo=""):
    """Pošle návrh hostovi. Vrací (ok, zpráva pro hostitele)."""
    if navrh["stav"] not in ("ceka", "schvaleno"):
        return False, "Tenhle návrh už je vyřízený."
    if navrh["message_id"]:  # návrh agenta – nepředbíhá ho nová zpráva?
        zpravy = smoobu.messages(navrh["reservation_id"])
        if zpravy and str(zpravy[-1].get("id")) != navrh["message_id"]:
            db.uprav_navrh(navrh["id"], stav="zastarale")
            oznameni.odeber_tlacitka(navrh["tg_message_id"])
            proc = "host napsal další zprávu" if zpravy[-1].get("type") == 1 else "hostovi už někdo odpověděl"
            return False, (f"⚠️ Neodesláno – mezitím {proc}.\n{navrh['hlavicka']}\n"
                           "Agent na novou zprávu hosta připraví nový návrh sám.")
    problem_s_kodem = uklidy.kod_stale_plati(db, navrh)
    if problem_s_kodem:
        oznameni.odeber_tlacitka(navrh["tg_message_id"])
        return False, f"⚠️ Neodesláno – {problem_s_kodem}\n{navrh['hlavicka']}"
    smoobu.send_message(navrh["reservation_id"], navrh["text"])
    db.uprav_navrh(navrh["id"], stav="odeslano")
    db.zapis(navrh["reservation_id"], f"odeslano_z_{zdroj}", navrh["text"])
    if kdo:
        db.zapis(navrh["reservation_id"], "schvalil", kdo)
    oznameni.odeber_tlacitka(navrh["tg_message_id"])
    return True, f"✅ Odesláno hostovi{_kdo(kdo)}\n{navrh['hlavicka']}"


def zahodit(db, navrh, kdo=""):
    db.uprav_navrh(navrh["id"], stav="zahozeno")
    if kdo:
        db.zapis(navrh["reservation_id"], "zahodil", kdo)
    oznameni.odeber_tlacitka(navrh["tg_message_id"])


def nahradit(db, puvodni, text_hostitele, kdo=""):
    """Z hostitelova textu udělá zprávu v jazyce hosta jako nový návrh (i s tlačítky v Telegramu)."""
    hotovy = mozek.priprav_zpravu_hostitele(text_hostitele, puvodni["jazyk"])
    db.uprav_navrh(puvodni["id"], stav="nahrazeno")
    oznameni.odeber_tlacitka(puvodni["tg_message_id"])
    # message_id prázdné = hostitelův vlastní text, před odesláním se nekontroluje, jestli je konverzace aktuální
    novy_id = db.novy_navrh(puvodni["reservation_id"], "", hotovy, puvodni["jazyk"], puvodni["hlavicka"])
    db.uprav_navrh(novy_id, tg_message_id=oznameni.posli(
        f"👀 KONTROLA PŘED ODESLÁNÍM{_kdo(kdo)}\n{puvodni['hlavicka']}\n\n{hotovy}", TLACITKA_NAVRHU(novy_id)
    ))
    return novy_id
