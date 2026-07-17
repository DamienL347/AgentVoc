"""
Formatage des dates en français parlé.
Indispensable pour le TTS : ne jamais envoyer un ISO 8601 brut à la voix.
"""
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

TZ_PARIS = ZoneInfo("Europe/Paris")

DAYS_FR = [
    "lundi", "mardi", "mercredi", "jeudi",
    "vendredi", "samedi", "dimanche",
]

MONTHS_FR = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


def parse_iso(value: str | datetime) -> datetime:
    """Parse une date ISO (avec ou sans timezone) vers Europe/Paris."""
    if isinstance(value, datetime):
        dt = value
    else:
        # Supporte "2026-07-19T14:00:00Z" et les offsets explicites
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))

    if dt.tzinfo is None:
        # Dates naïves : on suppose qu'elles sont déjà en heure de Paris
        return dt.replace(tzinfo=TZ_PARIS)
    return dt.astimezone(TZ_PARIS)


def format_datetime_fr(value: str | datetime) -> str:
    """
    "2026-07-19T14:30:00Z" → "dimanche 19 juillet à 16h30"
    (converti en heure de Paris, lisible par un TTS français)
    """
    try:
        dt = parse_iso(value)
    except (ValueError, TypeError):
        logger.warning(f"⚠️ Date non parsable : {value!r}")
        return str(value)

    day_name  = DAYS_FR[dt.weekday()]
    month     = MONTHS_FR[dt.month - 1]
    day_num   = "premier" if dt.day == 1 else str(dt.day)

    if dt.minute == 0:
        time_str = f"{dt.hour}h"
    else:
        time_str = f"{dt.hour}h{dt.minute:02d}"

    return f"{day_name} {day_num} {month} à {time_str}"


def format_date_fr(value: str | datetime) -> str:
    """"2026-07-19" → "dimanche 19 juillet" (sans l'heure)."""
    try:
        dt = parse_iso(value)
    except (ValueError, TypeError):
        return str(value)

    day_num = "premier" if dt.day == 1 else str(dt.day)
    return f"{DAYS_FR[dt.weekday()]} {day_num} {MONTHS_FR[dt.month - 1]}"
