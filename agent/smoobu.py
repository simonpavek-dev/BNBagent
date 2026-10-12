"""Klient pro Smoobu API (https://docs.smoobu.com/) – jen HMAC ověřování.

Staré ověřování hlavičkou Api-Key Smoobu vypíná 31. 10. 2026, proto se nepoužívá vůbec: bez SMOOBU_API_SECRET
klient nevznikne. Podpis podle dokumentace (sekce HMAC): METHOD, cesta, query (RFC 3986, klíče abecedně),
čas, nonce, SHA-256 těla a API klíč, oddělené novým řádkem → HMAC-SHA256 se secretem → Base64.
"""
import base64
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import requests

BASE_URL = "https://login.smoobu.com"
MAX_POSUN_HODIN_S = 300      # Smoobu odmítne požadavek s časem posunutým o víc než 5 minut
MAX_CEKANI_429_S = 65        # limit je na minutové okno – déle než minutu nečekat


class SmoobuError(Exception):
    pass


class SmoobuOvereni(SmoobuError):
    """401 – Smoobu odmítá ověření (špatný klíč/secret, posunuté hodiny, opakovaný nonce)."""


class SmoobuLimit(SmoobuError):
    """429 – překročený limit požadavků (u odeslání zprávy se neopakuje)."""


def _rfc3986(hodnota):
    return quote(str(hodnota), safe="-._~")


def query_rfc3986(params):
    """Query string pro podpis i URL: klíče seřazené abecedně, kódování RFC 3986 (mezera %20, [] → %5B%5D)."""
    return "&".join(f"{_rfc3986(k)}={_rfc3986(v)}" for k, v in sorted((params or {}).items()))


def podpis(method, path, query, timestamp, nonce, telo, api_key, api_secret):
    canonical = "\n".join([method, path, query, timestamp, nonce, hashlib.sha256(telo).hexdigest(), api_key])
    return base64.b64encode(hmac.new(api_secret.encode(), canonical.encode(), hashlib.sha256).digest()).decode()


def _duvod_401(resp):
    """Lidsky čitelný důvod odmítnutí podle odpovědi Smoobu (hodnoty klíčů nikdy nevypisuje)."""
    text = (resp.text or "").lower()
    try:
        posun = abs((parsedate_to_datetime(resp.headers.get("Date", "")) - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError):
        posun = 0
    if posun > MAX_POSUN_HODIN_S:
        return f"hodiny serveru jsou posunuté o {posun / 60:.0f} min (Smoobu povoluje max. 5 min) – zapni synchronizaci času (NTP)"
    if "nonce" in text:
        return "opakovaný nonce (stejný požadavek odeslaný dvakrát)"
    if "timestamp" in text or "expired" in text:
        return "neplatný čas požadavku (X-Timestamp) – zkontroluj hodiny serveru"
    return ("špatný API klíč nebo secret, případně zrušený klíč – zkontroluj SMOOBU_API_KEY a SMOOBU_API_SECRET "
            "(Smoobu → Settings → Advanced → API Keys)")


class Smoobu:
    def __init__(self, api_key, api_secret, pri_odmitnuti=None):
        if not api_key:
            raise SmoobuError("Chybí SMOOBU_API_KEY v souboru .env")
        if not api_secret:
            raise SmoobuError("Chybí SMOOBU_API_SECRET v souboru .env – staré ověřování (Api-Key) Smoobu "
                              "31. 10. 2026 vypíná, agent ho nepoužívá. Secret vytvoříš ve Smoobu: "
                              "Settings → Advanced → API Keys → Generate Secret.")
        self.api_key = api_key
        self.api_secret = api_secret
        self.pri_odmitnuti = pri_odmitnuti  # zavolá se při každém 401 (upozornění hostitele)
        self.session = requests.Session()

    def _hlavicky(self, method, path, query, data):
        """HMAC hlavičky – pro každý pokus nové (Smoobu odmítne opakovaný nonce)."""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        nonce = str(uuid.uuid4())
        return {
            "Content-Type": "application/json", "Cache-Control": "no-cache",
            "X-API-Key": self.api_key, "X-Timestamp": timestamp, "X-Nonce": nonce,
            "X-Signature": podpis(method, path, query, timestamp, nonce, data, self.api_key, self.api_secret),
        }

    def _request(self, method, path, params=None, body=None):
        query = query_rfc3986(params)
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else b""
        url = BASE_URL + path + ("?" + query if query else "")
        for pokus in range(3):
            try:
                resp = self.session.request(method, url, data=data or None,
                                            headers=self._hlavicky(method, path, query, data), timeout=30)
            except (requests.ConnectionError, requests.Timeout):
                if pokus == 2 or method != "GET":  # odeslání zprávy neopakovat, aby neodešla dvakrát
                    raise
                time.sleep(5 * (pokus + 1))
                continue
            if resp.status_code == 429 and method == "GET" and pokus < 2:
                time.sleep(self._cekani_429(resp))
                continue
            break
        if resp.status_code == 401:
            chyba = SmoobuOvereni(f"{method} {path} → 401: {_duvod_401(resp)}")
            if self.pri_odmitnuti:
                self.pri_odmitnuti(chyba)
            raise chyba
        if resp.status_code == 429:
            raise SmoobuLimit(f"{method} {path} → 429: překročený limit požadavků Smoobu"
                              + (" – zprávu neopakuji, aby neodešla dvakrát" if method != "GET" else ""))
        if resp.status_code >= 400:
            raise SmoobuError(f"{method} {path} → {resp.status_code}: {resp.text[:300]}")
        return resp.json() if resp.content else {}

    @staticmethod
    def _cekani_429(resp):
        """X-RateLimit-Retry-After je Unix čas konce minutového okna → kolik sekund počkat."""
        try:
            sekund = int(resp.headers.get("X-RateLimit-Retry-After", "")) - time.time()
        except ValueError:
            sekund = 10
        return min(max(sekund, 1), MAX_CEKANI_429_S)

    def over_pripojeni(self):
        """Skutečné volání GET /api/apartments. Vrací (ok, text pro hostitele)."""
        try:
            pocet = len(self.apartments())
        except SmoobuOvereni as e:
            return False, f"Smoobu HMAC: odmítnuto – {str(e).split('401: ', 1)[-1]}"
        except (SmoobuError, requests.RequestException) as e:
            return False, f"Smoobu HMAC: nepodařilo se ověřit – {str(e)[:200]}"
        return True, f"Smoobu HMAC: OK ({pocet} apartmánů)"

    def apartments(self):
        return self._request("GET", "/api/apartments").get("apartments", [])

    def apartment(self, apartment_id):
        return self._request("GET", f"/api/apartments/{apartment_id}")

    def custom_placeholders(self):
        return self._request("GET", "/api/custom-placeholders").get("customPlaceholders", [])

    def reservations(self, arrival_from, arrival_to):
        """Všechny rezervace s příjezdem v daném rozmezí (datumy jako date)."""
        out, page = [], 1
        while True:
            data = self._request("GET", "/api/reservations", {
                "arrivalFrom": arrival_from.isoformat(),
                "arrivalTo": arrival_to.isoformat(),
                "pageSize": 100,
                "page": page,
            })
            out.extend(data.get("bookings", []))
            if page >= int(data.get("page_count") or 1):
                return out
            page += 1

    def reservation(self, reservation_id):
        return self._request("GET", f"/api/reservations/{reservation_id}")

    def messages(self, reservation_id):
        """Konverzace k rezervaci, seřazená od nejstarší. type 1 = od hosta, 2 = od nás."""
        out, page = [], 1
        while True:
            data = self._request("GET", f"/api/reservations/{reservation_id}/messages", {
                "onlyRelatedToGuest": "false",
                "page": page,
            })
            if isinstance(data, list):
                out.extend(data)
                break
            out.extend(data.get("messages", []))
            if page >= int(data.get("page_count") or 1):
                break
            page += 1
        return sorted(out, key=lambda m: (str(m.get("createdAt") or ""), m.get("id") or 0))

    def send_message(self, reservation_id, text):
        return self._request(
            "POST",
            f"/api/reservations/{reservation_id}/messages/send-message-to-guest",
            body={"messageBody": text},
        )
