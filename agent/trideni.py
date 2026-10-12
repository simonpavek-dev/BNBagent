"""Třídění zpráv hostů jednoduchými pravidly (bez modelu).

je_jednoducha: poděkování / „ok“ / oznámení času příjezdu – krátké, bez otázky, prosby a problému.
Takové zprávy může vyřídit levnější model (přepínač LEVNEJSI_MODEL_PRO_JEDNODUCHE). V pochybnostech vždy False –
zpráva pak jde na hlavní model, což je bezpečnější směr.
"""
import re

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
