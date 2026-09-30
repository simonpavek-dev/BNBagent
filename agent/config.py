"""Nastavení agenta – čte se ze souboru .env v kořeni projektu."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

ZNALOSTI_DIR = ROOT / "znalostni-baze"
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "agent.db"
LOG_PATH = DATA_DIR / "agent.log"

SMOOBU_API_KEY = os.getenv("SMOOBU_API_KEY", "").strip()
SMOOBU_API_SECRET = os.getenv("SMOOBU_API_SECRET", "").strip()

MODEL = os.getenv("MODEL", "claude-opus-5").strip()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# "navrh" = agent hostům nic neposílá, jen ti posílá návrhy odpovědí
# "ostre" = agent odpovídá hostům sám
REZIM = os.getenv("REZIM", "navrh").strip().lower()
INTERVAL_MINUT = int(os.getenv("INTERVAL_MINUT", "3"))
HODNOCENI_HOSTU = os.getenv("HODNOCENI_HOSTU", "ano").strip().lower() == "ano"
HODNOCENI_HODINA = int(os.getenv("HODNOCENI_HODINA", "11"))  # kdy denně připravit návrhy hodnocení
# Instrukce k příjezdu: večer (PRIJEZD_HODINA) se připraví na zítřek ke schválení,
# schválené se odešlou v den příjezdu v PRIJEZD_ODESLAT_HODINA
PRIJEZD_HODINA = int(os.getenv("PRIJEZD_HODINA", "18"))
PRIJEZD_ODESLAT_HODINA = int(os.getenv("PRIJEZD_ODESLAT_HODINA", "10"))

# Aplikace úklidů (kolbl.goldenpathai.com) – prázdné = napojení vypnuté, kódy se berou ze znalostní báze
UKLIDY_API_URL = os.getenv("UKLIDY_API_URL", "").strip()
UKLIDY_API_KEY = os.getenv("UKLIDY_API_KEY", "").strip()
UKLID_KONTROLA_HODINA = int(os.getenv("UKLID_KONTROLA_HODINA", "14"))  # v den příjezdu: je už uklizeno?

TIMEZONE = "Europe/Prague"
