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
# ano = instrukce k příjezdu se v PRIJEZD_ODESLAT_HODINA odešlou samy (bez schválení, jde je jen zrušit);
# odpovědi na zprávy hostů se dál řídí REZIM
KONTROLA_KALENDARE_HODIN = float(os.getenv("KONTROLA_KALENDARE_HODIN", "1"))  # jak často hlídat dvojí rezervace
# ano = instrukce k příjezdu skládá kód ze šablony (kódy, Wi-Fi, časy ze zdroje pravdy), model jen překládá
# ano = jednoduché zprávy hostů (díky, ok, čas příjezdu – trideni.je_jednoducha) vyřizuje levnější MODEL_JEDNODUCHE
LEVNEJSI_MODEL_PRO_JEDNODUCHE = os.getenv("LEVNEJSI_MODEL_PRO_JEDNODUCHE", "ne").strip().lower() == "ano"
MODEL_JEDNODUCHE = os.getenv("MODEL_JEDNODUCHE", "claude-sonnet-5").strip()
INSTRUKCE_ZE_SABLONY = os.getenv("INSTRUKCE_ZE_SABLONY", "ne").strip().lower() == "ano"
PRIJEZDY_AUTOMATICKY = os.getenv("PRIJEZDY_AUTOMATICKY", "ne").strip().lower() == "ano"

# Aplikace úklidů (uklid.kolbl-apartments.cz) – účet agenta; prázdné = napojení vypnuté
UKLIDY_URL = os.getenv("UKLIDY_URL", "").strip()
UKLIDY_LOGIN = os.getenv("UKLIDY_LOGIN", "").strip()
UKLIDY_HESLO = os.getenv("UKLIDY_HESLO", "").strip()
UKLIDY_INTERVAL_MINUT = int(os.getenv("UKLIDY_INTERVAL_MINUT", "10"))  # jak často číst aplikaci úklidů
# Dřívější check-in: když je úklid v den příjezdu hotový mezi DRIVEJSI_CHECKIN_OD a půl hodinou před check-inem,
# agent hostovi nabídne, že může přijít dřív (v režimu návrhů jen ke schválení)
DRIVEJSI_CHECKIN_OD = os.getenv("DRIVEJSI_CHECKIN_OD", "10:00").strip()
UKLID_KONTROLA_HODINA = int(os.getenv("UKLID_KONTROLA_HODINA", "14"))  # v den příjezdu: je už uklizeno?

TIMEZONE = "Europe/Prague"
