"""
Normalisation des numéros de téléphone.
Permet de comparer "+33612345678", "0612345678" et "06 12 34 56 78".
"""
import logging
from typing import Optional

import phonenumbers

logger = logging.getLogger(__name__)

DEFAULT_REGION = "FR"


def normalize_phone(raw: Optional[str], region: str = DEFAULT_REGION) -> Optional[str]:
    """
    Normalise un numéro au format E.164 ("+33612345678").
    Retourne None si le numéro est vide ou invalide.
    """
    if not raw or not str(raw).strip():
        return None

    try:
        parsed = phonenumbers.parse(str(raw).strip(), region)
        if not phonenumbers.is_valid_number(parsed):
            return None
        return phonenumbers.format_number(
            parsed, phonenumbers.PhoneNumberFormat.E164
        )
    except phonenumbers.NumberParseException:
        return None


def phones_match(a: Optional[str], b: Optional[str]) -> bool:
    """Compare deux numéros indépendamment de leur format."""
    na, nb = normalize_phone(a), normalize_phone(b)
    return na is not None and na == nb


# Valeurs transmises par Vapi/Twilio quand l'appelant masque son numéro
ANONYMOUS_MARKERS = {
    "unknown", "anonymous", "private", "restricted", "unavailable",
    "blocked", "withheld", "+266696687",   # « anonymous » composé sur un clavier
}


def is_anonymous(raw: Optional[str]) -> bool:
    """
    L'appelant masque-t-il son numéro ?

    Important pour la prestation : sans numéro, on ne peut ni rappeler, ni
    retrouver un RDV existant, ni envoyer de SMS de confirmation. L'agent doit
    donc demander le numéro au client au lieu de promettre un rappel impossible.
    """
    if not raw or not str(raw).strip():
        return True
    if str(raw).strip().lower() in ANONYMOUS_MARKERS:
        return True
    return normalize_phone(raw) is None
