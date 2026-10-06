"""Ovládací panel agenta – webová stránka jen pro tento Mac (http://localhost:8765)."""
import json
import logging
import re
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import config, navrhy, oznameni, prace, spravce
from .databaze import Databaze

log = logging.getLogger("agent")
PORT = 8765
HTML = Path(__file__).with_name("dashboard.html")
POVOLENE_HOSTY = {f"localhost:{PORT}", f"127.0.0.1:{PORT}"}

POPISKY_ROZHODNUTI = {
    "odpovedet": ("odpoved", "Odpověď připravena"),
    "eskalovat": ("eskalace", "Předáno tobě"),
    "neodpovidat": ("klid", "Bez odpovědi"),
}


def _stav(db):
    posledni = db.nastaveni("posledni_kontrola")
    bezi = bool(posledni) and datetime.now() - datetime.fromisoformat(posledni) < timedelta(
        seconds=config.INTERVAL_MINUT * 60 + 180)
    dnes = datetime.now().date().isoformat()
    rozhodnuti = db.conn.execute(
        "SELECT json_extract(detail, '$.rozhodnuti'), count(*) FROM udalosti "
        "WHERE akce = 'rozhodnuti' AND cas >= ? GROUP BY 1", (dnes,)).fetchall()
    odeslano = db.conn.execute(
        "SELECT count(*) FROM udalosti WHERE akce LIKE 'odeslano%' AND cas >= ?", (dnes,)).fetchone()[0]
    cekajici = db.conn.execute("SELECT count(*) FROM navrhy WHERE stav IN ('ceka', 'schvaleno')").fetchone()[0]
    return {
        "bezi": bezi,
        "posledni_kontrola": posledni,
        "cinnost": db.nastaveni("cinnost_chat") or db.nastaveni("cinnost") or "",
        "rezim": prace.rezim(db),
        "model": config.MODEL,
        "interval": config.INTERVAL_MINUT,
        "dnes": {"zprav": sum(p for _, p in rozhodnuti), "odeslano": odeslano,
                 **{k or "?": p for k, p in rozhodnuti}},
        "cekajici_navrhy": cekajici,
        "naklady": spravce.naklady(),
    }


def _aktivita(db, pocet=80):
    out = []
    for cas, rid, akce, detail in db.conn.execute(
            "SELECT cas, reservation_id, akce, detail FROM udalosti ORDER BY id DESC LIMIT ?", (pocet,)):
        try:
            d = json.loads(detail)
        except (ValueError, TypeError):
            d = detail
        polozka = {"cas": cas, "rezervace": rid, "druh": "info", "titulek": akce, "hlavicka": "", "text": "", "poznamka": ""}
        if akce == "rozhodnuti" and isinstance(d, dict):
            druh, titulek = POPISKY_ROZHODNUTI.get(d.get("rozhodnuti"), ("info", d.get("rozhodnuti")))
            polozka.update(druh=druh, titulek=titulek, hlavicka=d.get("hlavicka", ""),
                           text=d.get("zprava_hosta", ""), poznamka=d.get("duvod", ""))
        elif akce.startswith("odeslano"):
            kde = {"odeslano": "automaticky", "odeslano_z_telegramu": "schváleno v Telegramu",
                   "odeslano_z_panelu": "schváleno v panelu", "odeslano_z_planovace": "naplánované",
                   "odeslano_z_automaticky": "automaticky"}.get(akce, "")
            polozka.update(druh="odeslano", titulek=f"Odesláno hostovi ({kde})", text=d if isinstance(d, str) else "")
        elif akce == "hodnoceni" and isinstance(d, dict):
            polozka.update(druh="hodnoceni", titulek="Návrh hodnocení hosta", text=d.get("verejne_hodnoceni", ""))
        elif akce == "zmena_znalosti" and isinstance(d, dict):
            polozka.update(druh="zmena", titulek=f"Změna znalostní báze · {d.get('soubor', '')}", text=d.get("zmena", ""))
        elif akce == "zmena_rezimu":
            polozka.update(druh="zmena", titulek=f"Režim přepnut na „{d}“")
        elif akce == "chyba":
            polozka.update(druh="chyba", titulek="Chyba", text=str(d))
        else:
            continue
        out.append(polozka)
    return out


def _navrhy(db):
    radky = db.conn.execute(
        "SELECT id, reservation_id, text, jazyk, hlavicka, cas, stav, odeslat_po FROM navrhy "
        "WHERE stav IN ('ceka', 'schvaleno') ORDER BY id DESC").fetchall()
    out = []
    for nid, rid, text, jazyk, hlavicka, cas, stav, odeslat_po in radky:
        zprava = db.conn.execute(
            "SELECT json_extract(detail, '$.zprava_hosta') FROM udalosti WHERE akce = 'rozhodnuti' "
            "AND reservation_id = ? AND cas <= ? ORDER BY id DESC LIMIT 1", (rid, cas)).fetchone()
        out.append({"id": nid, "hlavicka": hlavicka, "text": text, "jazyk": jazyk, "cas": cas, "stav": stav,
                    "odeslat_po": odeslat_po, "zprava_hosta": zprava[0] if zprava else ""})
    return out


class Obsluha(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _odpovez(self, data, kod=200, typ="application/json"):
        telo = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
        self.send_response(kod)
        self.send_header("Content-Type", typ + "; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(telo)

    def _povoleno(self):
        # jen z tohoto počítače (ochrana proti DNS rebinding a požadavkům z cizích webů)
        return self.headers.get("Host", "") in POVOLENE_HOSTY

    def do_GET(self):
        if not self._povoleno():
            return self._odpovez({"chyba": "zakázáno"}, 403)
        db = Databaze()
        cesta = self.path.split("?")[0]
        if cesta == "/":
            return self._odpovez(HTML.read_bytes(), typ="text/html")
        if cesta == "/api/stav":
            return self._odpovez(_stav(db))
        if cesta == "/api/aktivita":
            return self._odpovez(_aktivita(db))
        if cesta == "/api/navrhy":
            return self._odpovez(_navrhy(db))
        if cesta == "/api/chat":
            return self._odpovez([{"kdo": k, "text": t, "cas": c} for k, t, c in db.chat_historie(100)])
        self._odpovez({"chyba": "nenalezeno"}, 404)

    def do_POST(self):
        # vlastní hlavička = prohlížeč ji z cizí stránky bez CORS povolení neodešle
        if not self._povoleno() or self.headers.get("X-Agent-Panel") != "1":
            return self._odpovez({"chyba": "zakázáno"}, 403)
        delka = int(self.headers.get("Content-Length") or 0)
        data = json.loads(self.rfile.read(delka) or b"{}")
        db = Databaze()
        try:
            if self.path == "/api/chat":
                text = (data.get("text") or "").strip()
                if not text:
                    return self._odpovez({"chyba": "prázdná zpráva"}, 400)
                return self._odpovez({"odpoved": spravce.odpovez(db, text)})
            m = re.fullmatch(r"/api/navrh/(\d+)/(odeslat|zahodit|upravit)", self.path)
            if m:
                navrh = db.navrh(int(m.group(1)))
                if not navrh or not (navrh["stav"] == "ceka" or (navrh["stav"] == "schvaleno" and m.group(2) == "zahodit")):
                    return self._odpovez({"ok": False, "zprava": "Tenhle návrh už je vyřízený."})
                if m.group(2) == "odeslat":
                    ok, zprava = navrhy.schvalit(prace.vytvor_smoobu(), db, navrh, "panelu")
                    if zprava:
                        oznameni.posli(zprava)
                    return self._odpovez({"ok": ok, "zprava": zprava or "Schváleno, odeslání je naplánované"})
                if m.group(2) == "zahodit":
                    navrhy.zahodit(db, navrh)
                    return self._odpovez({"ok": True, "zprava": "Návrh zahozen"})
                novy = navrhy.nahradit(db, navrh, (data.get("text") or "").strip())
                return self._odpovez({"ok": True, "zprava": "Nový návrh připraven ke schválení", "id": novy})
        except Exception as e:
            log.exception("Chyba v panelu")
            return self._odpovez({"ok": False, "chyba": str(e)}, 500)
        self._odpovez({"chyba": "nenalezeno"}, 404)


def spust():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Obsluha)
    print(f"Ovládací panel běží na http://localhost:{PORT}")
    server.serve_forever()
