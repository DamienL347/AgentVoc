"""
Lecture des horaires d'ouverture d'un garage.

Sert à décider, en cours d'appel, si l'agent peut transférer vers le patron
(garage ouvert) ou s'il doit prendre un message (garage fermé). Sans cette
distinction, l'agent promet un transfert vers un téléphone qui sonne dans le
vide — le pire scénario pour un client déjà mécontent ou en urgence.

Format attendu (colonne `garages.business_hours`, jsonb) :
    {"monday": {"open": "08:00", "close": "18:00", "closed": false}, ...}
"""
import logging
from datetime import datetime, time
from typing import Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

PARIS_TZ = ZoneInfo("Europe/Paris")

JOURS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

JOURS_FR = {
    "monday": "lundi", "tuesday": "mardi", "wednesday": "mercredi",
    "thursday": "jeudi", "friday": "vendredi", "saturday": "samedi",
    "sunday": "dimanche",
}


def _parse_heure(valeur: Optional[str]) -> Optional[time]:
    if not valeur:
        return None
    try:
        heures, minutes = str(valeur).split(":")[:2]
        return time(int(heures), int(minutes))
    except (ValueError, AttributeError):
        return None


def is_open_at(business_hours: Optional[dict], moment: Optional[datetime] = None) -> bool:
    """
    Le garage est-il ouvert à cet instant ?

    En l'absence d'horaires exploitables, on répond False : mieux vaut prendre un
    message à tort que promettre un transfert qui n'aboutira pas.
    """
    if not isinstance(business_hours, dict):
        return False

    moment = (moment or datetime.now(PARIS_TZ)).astimezone(PARIS_TZ)
    jour   = business_hours.get(JOURS[moment.weekday()])

    if not isinstance(jour, dict) or jour.get("closed"):
        return False

    ouverture = _parse_heure(jour.get("open"))
    fermeture = _parse_heure(jour.get("close"))
    if not ouverture or not fermeture:
        return False

    return ouverture <= moment.time() < fermeture


def describe_hours_fr(business_hours: Optional[dict]) -> str:
    """Résumé lisible des horaires, à faire dire à l'agent."""
    if not isinstance(business_hours, dict):
        return "Nos horaires ne sont pas renseignés."

    lignes = []
    for cle in JOURS:
        jour = business_hours.get(cle)
        if not isinstance(jour, dict) or jour.get("closed"):
            continue
        ouverture, fermeture = jour.get("open"), jour.get("close")
        if ouverture and fermeture:
            lignes.append(f"{JOURS_FR[cle]} {ouverture}-{fermeture}")

    return ", ".join(lignes) if lignes else "Nos horaires ne sont pas renseignés."


def next_opening_fr(business_hours: Optional[dict],
                    moment: Optional[datetime] = None) -> str:
    """
    Prochaine ouverture, en français naturel (« demain à 8h », « lundi à 8h »).
    Permet à l'agent d'annoncer QUAND le garage rappellera.
    """
    if not isinstance(business_hours, dict):
        return "dès la réouverture"

    depart = (moment or datetime.now(PARIS_TZ)).astimezone(PARIS_TZ)

    for décalage in range(0, 8):
        jour_cible = depart.replace(hour=0, minute=0, second=0, microsecond=0)
        jour_cible = jour_cible.fromordinal(jour_cible.toordinal() + décalage) \
                               .replace(tzinfo=PARIS_TZ)
        jour = business_hours.get(JOURS[jour_cible.weekday()])

        if not isinstance(jour, dict) or jour.get("closed"):
            continue
        ouverture = _parse_heure(jour.get("open"))
        if not ouverture:
            continue

        instant = jour_cible.replace(hour=ouverture.hour, minute=ouverture.minute)
        if instant <= depart:
            continue

        heure_txt = f"{ouverture.hour}h{ouverture.minute:02d}" if ouverture.minute \
                    else f"{ouverture.hour}h"
        if décalage == 0:
            return f"aujourd'hui à {heure_txt}"
        if décalage == 1:
            return f"demain à {heure_txt}"
        return f"{JOURS_FR[JOURS[jour_cible.weekday()]]} à {heure_txt}"

    return "dès la réouverture"
