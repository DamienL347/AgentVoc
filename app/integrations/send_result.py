"""
Résultat d'un envoi (SMS ou email).

Reste compatible avec l'ancien contrat booléen (`if sms_sent:`) grâce à __bool__,
tout en exposant l'identifiant du fournisseur nécessaire à la traçabilité
(table `notifications` : twilio_message_sid / resend_email_id).
"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SendResult:
    ok:          bool
    provider_id: Optional[str] = None   # SID Twilio ou id Resend
    error:       Optional[str] = None   # message d'erreur si ok=False

    def __bool__(self) -> bool:
        return self.ok

    @classmethod
    def success(cls, provider_id: Optional[str] = None) -> "SendResult":
        return cls(ok=True, provider_id=provider_id)

    @classmethod
    def failure(cls, error: str) -> "SendResult":
        return cls(ok=False, error=error)
