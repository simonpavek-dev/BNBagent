"""Jediný zdroj času pro rozhodování agenta. V testech jde čas zmrazit a posouvat.

Skutečný čas zůstává jen tam, kde ho vyžaduje technika: podpis HMAC a čekání u 429 (smoobu.py), pauzy mezi
dotazy na mapy (mapy.py), mezipaměť aplikace úklidů (uklidy.py) a časování smyčky (__main__.py).
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import config

_zmrazeno = [None]


def ted():
    """Aktuální pražský čas bez časové zóny (stejný tvar, jaký agent dřív bral z datetime.now() na serveru v Praze)."""
    if _zmrazeno[0] is not None:
        return _zmrazeno[0]
    return datetime.now(ZoneInfo(config.TIMEZONE)).replace(tzinfo=None)


def dnes():
    return ted().date()


def ted_iso():
    """Čas pro zápis do databáze a logu: 2026-10-12T17:55:14."""
    return ted().isoformat(timespec="seconds")


# ---------------------------------------------------------------- jen pro testy

def zmraz(cas):
    _zmrazeno[0] = cas


def posun(**kolik):
    """Posune zmrazený čas, např. posun(minutes=30) nebo posun(days=1)."""
    _zmrazeno[0] = ted() + timedelta(**kolik)


def rozmraz():
    _zmrazeno[0] = None
