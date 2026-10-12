"""Malá SQLite databáze: co už agent vyřídil a záznam všeho, co udělal."""
import json
import sqlite3
from datetime import datetime

from . import config


class Databaze:
    def __init__(self, path=None):
        # cesta se čte až teď, ne při importu – testy ji tak můžou přesměrovat do dočasné složky
        self.conn = sqlite3.connect(str(path or config.DB_PATH), timeout=15)
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS zpravy (
                message_id TEXT PRIMARY KEY,
                reservation_id TEXT,
                stav TEXT,
                pokusy INTEGER DEFAULT 0,
                cas TEXT
            );
            CREATE TABLE IF NOT EXISTS hodnoceni (
                reservation_id TEXT PRIMARY KEY,
                cas TEXT
            );
            CREATE TABLE IF NOT EXISTS udalosti (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cas TEXT,
                reservation_id TEXT,
                akce TEXT,
                detail TEXT
            );
            CREATE TABLE IF NOT EXISTS navrhy (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reservation_id TEXT,
                message_id TEXT,        -- zpráva hosta, na kterou návrh odpovídá
                text TEXT,              -- text pro hosta
                jazyk TEXT,
                hlavicka TEXT,
                stav TEXT,              -- ceka / odeslano / zahozeno / zastarale
                tg_message_id INTEGER,
                cas TEXT
            );
            CREATE TABLE IF NOT EXISTS chat (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kdo TEXT,
                text TEXT,
                cas TEXT
            );
            CREATE TABLE IF NOT EXISTS nastaveni (
                klic TEXT PRIMARY KEY,
                hodnota TEXT
            );
        """)
        try:  # starší databáze – doplnit sloupec pro naplánované odeslání
            self.conn.execute("ALTER TABLE navrhy ADD COLUMN odeslat_po TEXT")
        except sqlite3.OperationalError:
            pass
        self.conn.commit()

    @staticmethod
    def _ted():
        return datetime.now().isoformat(timespec="seconds")

    def zprava_vyrizena(self, message_id):
        row = self.conn.execute(
            "SELECT stav FROM zpravy WHERE message_id = ?", (str(message_id),)
        ).fetchone()
        return row is not None and row[0] != "chyba"

    def oznac_zpravu(self, message_id, reservation_id, stav):
        self.conn.execute(
            """INSERT INTO zpravy (message_id, reservation_id, stav, cas) VALUES (?, ?, ?, ?)
               ON CONFLICT(message_id) DO UPDATE SET stav = excluded.stav, cas = excluded.cas""",
            (str(message_id), str(reservation_id), stav, self._ted()),
        )
        self.conn.commit()

    def zapocitej_chybu(self, message_id, reservation_id):
        """Vrátí počet dosavadních neúspěšných pokusů o vyřízení zprávy."""
        self.conn.execute(
            """INSERT INTO zpravy (message_id, reservation_id, stav, pokusy, cas) VALUES (?, ?, 'chyba', 1, ?)
               ON CONFLICT(message_id) DO UPDATE SET pokusy = pokusy + 1, cas = excluded.cas""",
            (str(message_id), str(reservation_id), self._ted()),
        )
        self.conn.commit()
        return self.conn.execute(
            "SELECT pokusy FROM zpravy WHERE message_id = ?", (str(message_id),)
        ).fetchone()[0]

    def hodnoceni_hotovo(self, reservation_id):
        return self.conn.execute(
            "SELECT 1 FROM hodnoceni WHERE reservation_id = ?", (str(reservation_id),)
        ).fetchone() is not None

    def oznac_hodnoceni(self, reservation_id):
        self.conn.execute(
            "INSERT OR REPLACE INTO hodnoceni VALUES (?, ?)", (str(reservation_id), self._ted())
        )
        self.conn.commit()

    def zapis(self, reservation_id, akce, detail):
        if not isinstance(detail, str):
            detail = json.dumps(detail, ensure_ascii=False)
        self.conn.execute(
            "INSERT INTO udalosti (cas, reservation_id, akce, detail) VALUES (?, ?, ?, ?)",
            (self._ted(), str(reservation_id), akce, detail),
        )
        self.conn.commit()

    def novy_navrh(self, reservation_id, message_id, text, jazyk, hlavicka, odeslat_po=None):
        cur = self.conn.execute(
            """INSERT INTO navrhy (reservation_id, message_id, text, jazyk, hlavicka, stav, cas, odeslat_po)
               VALUES (?, ?, ?, ?, ?, 'ceka', ?, ?)""",
            (str(reservation_id), str(message_id or ""), text, jazyk, hlavicka, self._ted(), odeslat_po),
        )
        self.conn.commit()
        return cur.lastrowid

    def navrh(self, navrh_id):
        row = self.conn.execute(
            "SELECT id, reservation_id, message_id, text, jazyk, hlavicka, stav, tg_message_id, odeslat_po "
            "FROM navrhy WHERE id = ?",
            (navrh_id,),
        ).fetchone()
        if not row:
            return None
        return dict(zip(["id", "reservation_id", "message_id", "text", "jazyk", "hlavicka", "stav", "tg_message_id",
                         "odeslat_po"], row))

    def uprav_navrh(self, navrh_id, **hodnoty):
        for sloupec, hodnota in hodnoty.items():
            assert sloupec in ("stav", "tg_message_id", "text")
            self.conn.execute(f"UPDATE navrhy SET {sloupec} = ? WHERE id = ?", (hodnota, navrh_id))
        self.conn.commit()

    def chat_pridej(self, kdo, text):
        self.conn.execute("INSERT INTO chat (kdo, text, cas) VALUES (?, ?, ?)", (kdo, text, self._ted()))
        self.conn.commit()

    def chat_historie(self, pocet=50):
        radky = self.conn.execute("SELECT kdo, text, cas FROM chat ORDER BY id DESC LIMIT ?", (pocet,)).fetchall()
        return list(reversed(radky))

    def nastaveni(self, klic, vychozi=None):
        row = self.conn.execute("SELECT hodnota FROM nastaveni WHERE klic = ?", (klic,)).fetchone()
        return row[0] if row else vychozi

    def uloz_nastaveni(self, klic, hodnota):
        self.conn.execute("INSERT OR REPLACE INTO nastaveni VALUES (?, ?)", (klic, str(hodnota)))
        self.conn.commit()
