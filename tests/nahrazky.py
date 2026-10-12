"""Náhražky pro testy celého cyklu agenta bez internetu: Smoobu, Telegram a model Claude.
Všechna data jsou smyšlená (byt, hosté, kódy)."""
import re

import requests

from agent import mozek, oznameni, telegram_ovladani
from agent.smoobu import SmoobuLimit, SmoobuOvereni


class FakeSmoobu:
    """Rezervace a konverzace v paměti. Zprávy: type 1 = host, type 2 = my (i automatické zprávy Smoobu).

    porucha: None | "timeout_po_odeslani" (zpráva odejde, ale klient dostane timeout) | "401" | "429".
    Porucha platí pro odesílání; porucha_cteni totéž pro čtení (rezervace, zprávy)."""

    def __init__(self):
        self.rezervace = {}
        self.konverzace = {}
        self.odeslane = []
        self.porucha = None
        self.porucha_cteni = None
        self.pri_odmitnuti = None
        self._dalsi_id = 1000

    # ---- příprava scénáře
    def pridej_rezervaci(self, rid, prijezd, odjezd, byt_id=100, byt="Testbyt", host="Test Host", kanal="Airbnb"):
        self.rezervace[str(rid)] = {
            "id": rid, "arrival": str(prijezd), "departure": str(odjezd), "guest-name": host,
            "channel": {"name": kanal}, "apartment": {"id": byt_id, "name": byt},
            "adults": 2, "children": 0, "is-blocked-booking": False, "language": "en",
        }
        self.konverzace.setdefault(str(rid), [])
        return self.rezervace[str(rid)]

    def _zprava(self, rid, typ, text):
        self._dalsi_id += 1
        m = {"id": self._dalsi_id, "type": typ, "message": text, "createdAt": f"2026-01-01 00:{self._dalsi_id % 60:02d}"}
        self.konverzace.setdefault(str(rid), []).append(m)
        return m

    def napis_host(self, rid, text):
        return self._zprava(rid, 1, text)

    def napis_my(self, rid, text):
        """Naše zpráva – ruční odpověď hostitele nebo automatická zpráva Smoobu."""
        return self._zprava(rid, 2, text)

    # ---- poruchy
    def _selhani(self, druh, co):
        if druh == "401":
            chyba = SmoobuOvereni(f"{co} → 401: simulované odmítnutí")
            if self.pri_odmitnuti:
                self.pri_odmitnuti(chyba)
            raise chyba
        if druh == "429":
            raise SmoobuLimit(f"{co} → 429: simulovaný limit")

    # ---- rozhraní jako agent.smoobu.Smoobu
    def reservations(self, od, do):
        self._selhani(self.porucha_cteni, "GET /api/reservations")
        return [dict(r) for r in self.rezervace.values() if str(od) <= r["arrival"] <= str(do)]

    def reservation(self, rid):
        self._selhani(self.porucha_cteni, "GET /api/reservations/id")
        return dict(self.rezervace[str(rid)])

    def messages(self, rid):
        self._selhani(self.porucha_cteni, "GET /api/reservations/id/messages")
        return [dict(m) for m in self.konverzace.get(str(rid), [])]

    def send_message(self, rid, text):
        self._selhani(self.porucha, "POST send-message-to-guest")
        self.odeslane.append((str(rid), text))
        self._zprava(rid, 2, text)
        if self.porucha == "timeout_po_odeslani":
            raise requests.Timeout("simulovaný timeout – zpráva přitom odešla")
        return {}

    def apartments(self):
        return [{"id": 100, "name": "Testbyt"}]

    def _request(self, method, path, params=None, body=None):
        if path == "/api/rates":  # kontrola kalendáře: všechny noci zavřené
            return {"data": {str(params.get("apartments[]")): {}}}
        raise AssertionError(f"FakeSmoobu nezná {method} {path}")


class FakeTelegram:
    """Zachytává oznameni.posli (text, tlačítka); umí simulovat kliknutí a výpadek Telegramu."""

    CHAT = -100

    def __init__(self, monkeypatch):
        self.zpravy = []
        self.vypadek = False
        monkeypatch.setattr(oznameni, "posli", self.posli)
        monkeypatch.setattr(oznameni, "odeber_tlacitka", lambda *a, **k: None)
        monkeypatch.setattr(oznameni, "potvrd_kliknuti", lambda *a, **k: None)
        monkeypatch.setattr(oznameni, "akce_psani", lambda *a, **k: None)
        monkeypatch.setattr(oznameni, "nove_udalosti", lambda *a, **k: [])

    def posli(self, text, tlacitka=None, odpoved_na=None):
        if self.vypadek:
            return None  # jako skutečné oznameni.posli při chybě Telegramu
        self.zpravy.append({"id": len(self.zpravy) + 1, "text": text, "tlacitka": tlacitka or []})
        return len(self.zpravy)

    def s_tlacitky(self):
        return [z for z in self.zpravy if z["tlacitka"]]

    def navrh_id(self, zprava=None):
        """ID návrhu z tlačítka ✅ (výchozí: poslední zpráva s tlačítky)."""
        zprava = zprava or self.s_tlacitky()[-1]
        return int(next(c for _, c in zprava["tlacitka"] if c.startswith("odeslat:")).split(":")[1])

    def klikni(self, smoobu, db, akce, navrh_id, kdo="Tester"):
        telegram_ovladani._kliknuti(smoobu, db, {
            "id": "cb", "from": {"id": 1, "first_name": kdo},
            "message": {"chat": {"id": self.CHAT}}, "data": f"{akce}:{navrh_id}",
        })


class FakeModel:
    """Místo mozek._zavolej vrací připravený JSON podle účelu volání; zaznamenává kontext, který dostal."""

    def __init__(self, monkeypatch):
        self.odpovedi = {"instrukce k příjezdu": self._instrukce}
        self.volani = []
        monkeypatch.setattr(mozek, "_zavolej", self._zavolej)
        monkeypatch.setattr(mozek, "priprav_zpravu_hostitele", lambda text, jazyk: f"[{jazyk}] {text}")

    def _zavolej(self, instrukce, obecne_text, apartman_text, kontext, schema, nastroje=None, ucel=""):
        self.volani.append({"ucel": ucel, "kontext": kontext})
        odpoved = self.odpovedi[ucel]
        return odpoved(kontext) if callable(odpoved) else dict(odpoved)

    @staticmethod
    def _instrukce(kontext):
        kod = re.search(r"AKTUÁLNÍ KÓD KEYBOXU PRO TUTO REZERVACI: (\S+)", kontext)
        if not kod:
            return {"poslat": False, "zprava": "", "jazyk_hosta": "en", "duvod": "chybí kód"}
        return {"poslat": True, "zprava": f"Hi! Keybox code: {kod.group(1)}", "jazyk_hosta": "en", "duvod": ""}

    def odpovez(self, rozhodnuti="odpovedet", text="Thank you for your message!", navrh=""):
        """Nastaví odpověď na zprávy hostů."""
        self.odpovedi["zpráva hosta"] = {"rozhodnuti": rozhodnuti, "odpoved_hostovi": text,
                                         "navrh_pro_hostitele": navrh, "duvod": "test", "jazyk_hosta": "en"}
