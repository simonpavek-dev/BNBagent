"""Upozornění pro hostitele – přes Telegram (i s tlačítky), případně jen do konzole a logu."""
import logging

import requests

from . import config

log = logging.getLogger("agent")
MAX_DELKA = 4000  # Telegram povolí max. 4096 znaků na zprávu


class TelegramChyba(requests.RequestException):
    pass


def _post(metoda, data, timeout):
    """Volání Telegram API. Chyby se hlásí bez URL, aby se token bota nedostal do logu."""
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/{metoda}", json=data, timeout=timeout
        )
    except requests.RequestException as e:
        raise TelegramChyba(f"Telegram {metoda}: spojení selhalo ({type(e).__name__})") from None
    if resp.status_code >= 400:
        popis = resp.json().get("description", "") if resp.content else ""
        raise TelegramChyba(f"Telegram {metoda}: {resp.status_code} {popis}")
    return resp.json().get("result")


def _api(metoda, timeout=20, **data):
    return _post(metoda, data, timeout)


def telegram_zapnuty():
    return bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID)


def akce_psani():
    """Ukáže ve skupině „Vasil píše…“, než připraví odpověď."""
    try:
        _api("sendChatAction", chat_id=config.TELEGRAM_CHAT_ID, action="typing")
    except requests.RequestException:
        pass


def posli(text, tlacitka=None, odpoved_na=None):
    """Pošle zprávu hostiteli. tlacitka = [(popisek, callback_data), ...] se připojí k poslední části.
    Vrací message_id poslední odeslané části (nebo None)."""
    log.info("UPOZORNĚNÍ:\n%s", text)
    if not telegram_zapnuty():
        print("\n" + "=" * 60 + "\n" + text + "\n" + "=" * 60)
        return None
    casti = [text[i:i + MAX_DELKA] for i in range(0, len(text), MAX_DELKA)] or [""]
    message_id = None
    for i, cast in enumerate(casti):
        data = {"chat_id": config.TELEGRAM_CHAT_ID, "text": cast, "disable_web_page_preview": True}
        if odpoved_na and i == 0:
            data["reply_parameters"] = {"message_id": odpoved_na, "allow_sending_without_reply": True}
        if tlacitka and i == len(casti) - 1:
            data["reply_markup"] = {
                "inline_keyboard": [[{"text": p, "callback_data": c}] for p, c in tlacitka]
            }
        try:
            message_id = _api("sendMessage", **data)["message_id"]
        except requests.RequestException as e:
            log.error("Nepodařilo se poslat upozornění na Telegram: %s", e)
            print(text)
            return None
    return message_id


def odeber_tlacitka(message_id):
    try:
        _api("editMessageReplyMarkup", chat_id=config.TELEGRAM_CHAT_ID, message_id=message_id,
             reply_markup={"inline_keyboard": []})
    except requests.RequestException as e:
        log.warning("Nepodařilo se odebrat tlačítka: %s", e)


def potvrd_kliknuti(callback_id, text=""):
    try:
        _api("answerCallbackQuery", callback_query_id=callback_id, text=text)
    except requests.RequestException as e:
        log.warning("Nepodařilo se potvrdit kliknutí: %s", e)


def nove_udalosti(offset, cekat=20):
    """Dlouhé dotazování na nové zprávy a kliknutí (čeká až `cekat` sekund)."""
    return _post("getUpdates", {"offset": offset, "timeout": cekat,
                                "allowed_updates": ["message", "callback_query"]}, cekat + 10) or []
