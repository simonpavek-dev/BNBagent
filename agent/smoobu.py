"""Klient pro Smoobu API (https://docs.smoobu.com/)."""
import base64
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import urlencode

import requests

BASE_URL = "https://login.smoobu.com"


class SmoobuError(Exception):
    pass


class Smoobu:
    def __init__(self, api_key, api_secret=""):
        if not api_key:
            raise SmoobuError("Chybí SMOOBU_API_KEY v souboru .env")
        self.api_key = api_key
        self.api_secret = api_secret
        self.session = requests.Session()

    def _hlavicky(self, method, path, query, data):
        """Hlavičky s podpisem – pro každý pokus nové (Smoobu odmítne opakovaný nonce)."""
        headers = {"Content-Type": "application/json", "Cache-Control": "no-cache"}
        if not self.api_secret:
            headers["Api-Key"] = self.api_key
            return headers
        # Nové HMAC ověřování (od 2026). Starý hlavičkový klíč Api-Key končí 31. 10. 2026.
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        nonce = str(uuid.uuid4())
        canonical = "\n".join([
            method, path, query, timestamp, nonce,
            hashlib.sha256(data).hexdigest(), self.api_key,
        ])
        signature = base64.b64encode(
            hmac.new(self.api_secret.encode(), canonical.encode(), hashlib.sha256).digest()
        ).decode()
        headers.update({"X-API-Key": self.api_key, "X-Timestamp": timestamp, "X-Nonce": nonce, "X-Signature": signature})
        return headers

    def _request(self, method, path, params=None, body=None):
        query = urlencode(sorted((params or {}).items()))
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else b""
        url = BASE_URL + path + ("?" + query if query else "")
        for pokus in range(3):  # krátké výpadky sítě / pomalá odpověď Smoobu – zkusit znovu
            try:
                resp = self.session.request(method, url, data=data or None,
                                            headers=self._hlavicky(method, path, query, data), timeout=30)
                break
            except (requests.ConnectionError, requests.Timeout):
                if pokus == 2 or method != "GET":  # odeslání zprávy neopakovat, aby neodešla dvakrát
                    raise
                time.sleep(5 * (pokus + 1))
        if resp.status_code >= 400:
            raise SmoobuError(f"{method} {path} → {resp.status_code}: {resp.text[:300]}")
        return resp.json() if resp.content else {}

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
