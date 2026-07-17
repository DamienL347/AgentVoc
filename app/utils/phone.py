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
