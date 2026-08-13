"""
Service de notifications — envoi ET traçabilité.

Tout SMS / email sortant doit passer par ce service : il délègue l'envoi au client
(Twilio, Resend) puis enregistre une ligne dans la table `notifications`.

Pourquoi c'est important : sans cette trace, impossible de prouver a posteriori qu'une
confirmation de RDV est bien partie (litige client), et le dashboard de monitoring
n'a aucune visibilité sur les échecs d'envoi.

La traçabilité ne doit JAMAIS faire échouer un envoi : l'écriture en base est
encapsulée dans un try/except qui se contente de logguer.
"""
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from app.integrations.send_result import SendResult

logger = logging.getLogger(__name__)


class NotificationService:
    """Envoie les notifications sortantes et les journalise dans `notifications`."""

    def __init__(self):
        self.db = None  # initialisé au runtime (évite les imports circulaires)

    def _lazy_init(self):
        if self.db is None:
            from app.db.supabase_client import get_supabase_client
            self.db = get_supabase_client()

    # ── Envois ───────────────────────────────────────────────────────────────

    async def send_sms(
        self,
        *,
        to:             str,
        body:           str,
        garage_id:      UUID | str,
        recipient_type: str = "client",          # "client" | "garage"
        call_id:        Optional[str] = None,
        appointment_id: Optional[str] = None,
    ) -> SendResult:
        """Envoie un SMS via Twilio et le trace."""
        from app.integrations.twilio_sms import twilio_client

        result = await twilio_client.send_sms(to=to, body=body)

        self._trace(
            garage_id=garage_id,
            channel="sms",
            recipient_type=recipient_type,
            recipient_phone=to,
            body=body,
            result=result,
            call_id=call_id,
            appointment_id=appointment_id,
        )
        return result

    async def send_appointment_confirmation_email(
        self,
        *,
        to:             str,
        appointment:    dict,
        garage_id:      UUID | str,
        call_id:        Optional[str] = None,
        appointment_id: Optional[str] = None,
    ) -> SendResult:
        """Envoie l'email de confirmation de RDV via Resend et le trace."""
        from app.integrations.resend_email import resend_client

        result = await resend_client.send_appointment_confirmation(
            to=to, appointment=appointment,
        )

        self._trace(
            garage_id=garage_id,
            channel="email",
            recipient_type="client",
            recipient_email=to,
            subject=f"✅ RDV confirmé — {appointment.get('garage_name', 'le garage')}",
            body=appointment.get("title", "Confirmation de rendez-vous"),
            result=result,
            call_id=call_id,
            appointment_id=appointment_id,
        )
        return result

    # ── Traçabilité ──────────────────────────────────────────────────────────

    def _trace(
        self,
        *,
        garage_id:       UUID | str,
        channel:         str,                    # notification_channel
        recipient_type:  str,
        result:          SendResult,
        body:            str,
        recipient_phone: Optional[str] = None,
        recipient_email: Optional[str] = None,
        subject:         Optional[str] = None,
        call_id:         Optional[str] = None,
        appointment_id:  Optional[str] = None,
    ) -> None:
        """Écrit une ligne dans `notifications`. Ne lève jamais."""
        try:
            self._lazy_init()

            row = {
                "garage_id":       str(garage_id),
                "call_id":         call_id,
                "appointment_id":  appointment_id,
                "recipient_type":  recipient_type,
                "recipient_phone": recipient_phone,
                "recipient_email": recipient_email,
                "channel":         channel,
                "subject":         subject,
                # Le corps est tronqué : il peut contenir un email HTML complet
                "body":            (body or "")[:2000],
                "status":          "sent" if result.ok else "failed",
                "sent_at":         datetime.now(timezone.utc).isoformat() if result.ok else None,
                "error_message":   result.error,
            }

            if channel == "sms":
                row["twilio_message_sid"] = result.provider_id
            elif channel == "email":
                row["resend_email_id"] = result.provider_id

            self.db.table("notifications").insert(row).execute()

        except Exception as e:
            # Une notification non tracée est un problème d'observabilité,
            # pas une raison de casser l'appel en cours.
            logger.error(f"❌ Traçabilité notification impossible ({channel}) : {e}")


# Instance globale
notification_service = NotificationService()
