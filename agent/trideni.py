"""Třídění zpráv hostů jednoduchými pravidly (bez modelu).

je_jednoducha: poděkování / „ok“ / oznámení času příjezdu – krátké, bez otázky, prosby a problému.
Takové zprávy může vyřídit levnější model (přepínač LEVNEJSI_MODEL_PRO_JEDNODUCHE). V pochybnostech vždy False –
zpráva pak jde na hlavní model, což je bezpečnější směr.
je_zdvorilost + odpoved_na_zdvorilost: čisté „díky / 👍 / ok“ vyřídí pravidlo úplně bez modelu
(přepínač ZDVORILOSTI_BEZ_MODELU).
"""
import re

from . import hodiny, kontext, znalosti

MAX_DELKA = 160
OTAZKA = re.compile(r"[?¿]")
PROBLEM = re.compile(
    r"discount|refund|cancel|storn|slev|problem|problém|broken|rozbit|not work|doesn.?t work|nefung|nejde|complain|"
    r"stížn|damage|škod|dirty|špinav|late check|early check|dřív|pozd|extra|price|cena|invoice|faktur|dog|pes |kočk|"
    r"party|help|pomoc|emergency|lost|ztrat|klíč|wifi|wi-fi|heating|topen|hot water|tepl|kaputt|funktioniert nicht|"
    r"rabatt|stornier|non funziona|sconto|cancell|no funciona|descuento|cancelar|remboursement|annul", re.I)
DIKY = re.compile(
    r"thank|thx|danke|merci|grazie|gracias|obrigad|dzięk|dziek|děkuj|dekuj|ďakuj|dakuj|díky|diky|\bok\b|okay|great|"
    r"perfect|super|wonderful|awesome|toll|perfekt|parfait|perfetto|perfecto|skvěl|výborn|👍|🙏|😊|❤️|🙂|👌", re.I)
PRIJEZD = re.compile(
    r"arriv|ankunft|ankomm|kommen\b.*\ban\b|llegar|llegamos|llegaremos|příjezd|přijedeme|prijedeme|přijedu|dorazíme|"
    r"prídeme|príchod|przyjedziemy|przyjazd|check.?in", re.I)
# prosba / požadavek – i bez otazníku to není „jednoduchá“ zpráva
POZADAVEK = re.compile(
    r"please|prosím|prosim|bitte|per favore|por favor|s'il vous|could|would|can we|can i|need|potřeb|potreb|možn|možné|"
    r"possible|möglich|early|earlier|skôr|skor|dřív|driv|früher|frueher|einchecken|luggage|bags|zavazad|batožin|"
    r"gepäck|bagag|equipaj|separate|změn|zmen|change|instead|vedieť|vědět|vedet|let us know|lass|würden|möchten|"
    r"vorrei|quisiera|voudrais|chcel|chtěl|chceme|chcem|wanted|want|wish", re.I)
CAS = re.compile(r"\b\d{1,2}([:.]\d{2})?\s*(h|hod|uhr|pm|am)?\b", re.I)


def je_jednoducha(text):
    text = (text or "").strip()
    if not text or len(text) > MAX_DELKA or OTAZKA.search(text) or PROBLEM.search(text) or POZADAVEK.search(text):
        return False
    return bool(DIKY.search(text) or (PRIJEZD.search(text) and CAS.search(text)))


def nevyrizeny_text(zpravy):
    """Text zpráv hosta od naší poslední zprávy (to, na co se odpovídá)."""
    posledni = []
    for m in reversed(zpravy):
        if m.get("type") != 1:
            break
        posledni.append((m.get("message") or "").strip())
    return " ".join(reversed(posledni))



# ---------------------------------------------------------------- naléhavé zprávy (bez čekání na další zprávy hosta)

# nouze a „nedostaneme se dovnitř“ v 8 jazycích; omyl nevadí – zpráva se jen vyřídí hned, bez čekání
NALEHAVE = re.compile("|".join([
    r"\bhelp\s*!|urgent|emergenc|\bfire\b|smoke|\bgas\b|leak|flood|police|ambulance|injur",                   # en
    r"can'?t get in|cannot get in|can not get in|locked out|(can'?t|cannot|unable to) (open|enter|get into)",
    r"(code|key|keybox|door|lock)[^.!?]{0,25}(not|n't) (work|open)",
    r"nemůž(eme|u) se dostat|nejd(e|ou) otevřít|(kód|klíč|dveře|zámek)[^.!?]{0,25}(nefung|nejd)|nefunguje (kód|klíč)",
    r"hoří|požár|kouř|plyn|teče voda|voda teče|vytop|polici|záchrank|pomoc\s*!|naléhav",                         # cs
    r"nevieme sa dostať|nemôžeme sa dostať|nejde otvoriť|(kód|kľúč|dvere)[^.!?]{0,25}(nefung|nejd)",              # sk
    r"horí|požiar|\bdym|tečie voda|polícia",
    r"kommen nicht (rein|hinein)|nicht reinkommen|(code|schlüssel|tür|schloss)[^.!?]{0,25}(funktioniert|geht) nicht",
    r"feuer|\bbrand\b|rauch|wasser läuft|wasserschaden|polizei|notfall|krankenwagen|hilfe\s*!",                  # de
    r"non riusciamo (ad |a )?entrare|non possiamo entrare|(codice|chiave|porta)[^.!?]{0,25}non (funziona|si apre)",
    r"non si apre|incendio|fuoco|fumo|perdita|allagat|polizia|emergenza|aiuto\s*!",                              # it
    r"no (podemos|puedo) entrar|(código|codigo|llave|puerta)[^.!?]{0,25}no (funciona|abre|se abre)",
    r"fuego|humo|fuga|inund|policía|ayuda\s*!",                                                                  # es
    r"ne (peut|peux|pouvons) pas entrer|(code|clé|cle|porte)[^.!?]{0,25}ne (marche|fonctionne|s['’]ouvre) pas",
    r"ne s['’]ouvre pas|incendie|\bfeu\b|fumée|fuite|inond|urgence|au secours|à l['’]aide",                       # fr
    r"nie (możemy|mogę) (wejść|się dostać)|(kod|klucz|drzwi)[^.!?]{0,25}nie (działa|otwier)",
    r"pożar|ogień|wyciek|zalan|policj|pogotowie|ratunku",                                                         # pl
]), re.I)


def je_nalehava(text):
    """Nouze nebo host se nedostane dovnitř – agent nečeká, jestli host napíše ještě něco."""
    return bool(NALEHAVE.search(text or ""))


# ---------------------------------------------------------------- P1.3 zdvořilosti bez modelu

MAX_DELKA_ZDVORILOSTI = 80


def je_zdvorilost(text):
    """Čisté poděkování / 👍 / ok – bez otázky, prosby, problému i času příjezdu (ten se má potvrdit modelem)."""
    text = (text or "").strip()
    return (len(text) <= MAX_DELKA_ZDVORILOSTI and je_jednoducha(text)
            and not CAS.search(text) and not PRIJEZD.search(text))


# jazyk: podle slov ve zprávě (nejspolehlivější), pak podle rezervace, jinak angličtina
JAZYK_PODLE_SLOV = [("de", r"danke|vielen"), ("it", r"grazie"), ("es", r"gracias"), ("fr", r"merci"),
                    ("pl", r"dzięk|dziek"), ("sk", r"ďakuj|dakuj"), ("cs", r"děkuj|dekuj|díky|diky")]

# (před příjezdem, během pobytu, po odjezdu)
ODPOVEDI = {
    "en": ("You're welcome! We look forward to welcoming you 😊", "You're welcome! Enjoy your stay 😊",
           "Safe travels and thank you for staying with us! 😊"),
    "de": ("Gern geschehen! Wir freuen uns auf Sie 😊", "Gern geschehen! Einen schönen Aufenthalt 😊",
           "Gute Heimreise und danke für Ihren Aufenthalt! 😊"),
    "cs": ("Rádi pomůžeme, těšíme se na vás 😊", "Rádi jsme pomohli, užijte si pobyt 😊",
           "Šťastnou cestu a děkujeme za pobyt! 😊"),
    "sk": ("Radi pomôžeme, tešíme sa na vás 😊", "Radi sme pomohli, užite si pobyt 😊",
           "Šťastnú cestu a ďakujeme za pobyt! 😊"),
    "it": ("Prego! Vi aspettiamo 😊", "Prego! Buon soggiorno 😊", "Buon viaggio e grazie per il soggiorno! 😊"),
    "es": ("¡De nada! Os esperamos 😊", "¡De nada! Disfrutad de la estancia 😊",
           "¡Buen viaje y gracias por alojaros con nosotros! 😊"),
    "fr": ("Avec plaisir ! Au plaisir de vous accueillir 😊", "Avec plaisir ! Bon séjour 😊",
           "Bon retour et merci pour votre séjour ! 😊"),
    "pl": ("Nie ma za co! Czekamy na Was 😊", "Nie ma za co! Miłego pobytu 😊",
           "Szczęśliwej podróży i dziękujemy za pobyt! 😊"),
}

# naše předchozí zpráva už byla odpověď na zdvořilost / rozloučení → na další „díky“ neodpovídat (žádná nekonečná výměna)
NASE_ROZLOUCENI = re.compile(
    r"you're welcome|enjoy your stay|safe travels|our pleasure|rádi jsme|rádi pomůžeme|užijte|šťastnou cestu|radi sme|"
    r"užite|gern geschehen|schönen aufenthalt|gute heimreise|prego|buon soggiorno|buon viaggio|de nada|buen viaje|"
    r"avec plaisir|bon séjour|bon retour|nie ma za co|miłego pobytu", re.I)


def _jazyk(text, rezervace):
    for jazyk, vzor in JAZYK_PODLE_SLOV:
        if re.search(vzor, text, re.I):
            return jazyk
    jazyk = str(rezervace.get("language") or "").strip().lower()[:2]
    return jazyk if jazyk in ODPOVEDI else "en"


def odpoved_na_zdvorilost(rezervace, zpravy):
    """Rozhodnutí ve stejném tvaru jako od modelu (rozhodnuti, odpoved_hostovi, …) – bez volání modelu."""
    text = nevyrizeny_text(zpravy)
    jazyk = _jazyk(text, rezervace)
    nase = [m for m in zpravy if m.get("type") != 1]
    if nase and NASE_ROZLOUCENI.search(nase[-1].get("message") or ""):
        return {"rozhodnuti": "neodpovidat", "odpoved_hostovi": "", "navrh_pro_hostitele": "", "jazyk_hosta": jazyk,
                "duvod": "Host jen poděkoval na naše rozloučení – vyřízeno pravidlem bez modelu, bez odpovědi."}
    dnes = hodiny.dnes()
    prijezd, odjezd = kontext._datum(rezervace.get("arrival")), kontext._datum(rezervace.get("departure"))
    faze = 0 if prijezd and dnes < prijezd else (2 if odjezd and dnes >= odjezd else 1)
    hostitel = znalosti.obecne().get("hostitel") or {}
    podpis = str(hostitel.get("podpis_kratky") or str(hostitel.get("podpis") or "").strip().split("\n")[0]).strip()
    return {"rozhodnuti": "odpovedet", "odpoved_hostovi": f"{ODPOVEDI[jazyk][faze]}\n{podpis}".strip(),
            "navrh_pro_hostitele": "", "jazyk_hosta": jazyk,
            "duvod": "Krátká zdvořilost hosta – odpověď z hotových vět, bez modelu."}
