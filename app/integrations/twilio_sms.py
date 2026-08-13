"""
Client Twilio — Envoi de SMS (confirmations + alertes urgences)
"""
import logging

from app.config import settings
from app.integrations.send_result import SendResult

logger = logging.getLogger(__name__)


class TwilioSMSClient:
    """
    Client Twilio pour l'envoi de SMS.
    Gère les confirmations de RDV et les alertes urgences.
    """

    def __init__(self):
        self.account_sid  = settings.TWILIO_ACCOUNT_SID
        self.auth_token   = settings.TWILIO_AUTH_TOKEN
        self.from_number  = settings.TWILIO_PHONE_NUMBER
        self._client      = None

    def _get_client(self):
        """Initialisation lazy du client Twilio."""
        if self._client is None:
            from twilio.rest import Client
            self._client = Client(self.account_sid, self.auth_token)
        return self._client

    async def send_sms(self, to: str, body: str) -> SendResult:
        """
        Envoie un SMS.

        Args:
            to   : Numéro destinataire (format E.164 : +33XXXXXXXXX)
            body : Contenu du message (max 160 chars recommandé)

        Returns:
            SendResult : truthy si envoyé ; porte le SID Twilio pour la traçabilité
        """
        if not self.account_sid or not self.auth_token:
            logger.warning("⚠️ Twilio non configuré — SMS non envoyé")
            return SendResult.failure("Twilio non configuré")

        # Normaliser le numéro
        to = self._normalize_phone(to)
        if not to:
            logger.error(f"❌ Numéro invalide : {to}")
            return SendResult.failure("Numéro destinataire invalide")

        # Tronquer si trop long (max 1600 chars pour Twilio)
        if len(body) > 1600:
            body = body[:1597] + "..."

        try:
            client  = self._get_client()
            message = client.messages.create(
                body=body,
                from_=self.from_number,
                to=to,
            )
            logger.info(
                f"✅ SMS envoyé | to={to} | "
                f"sid={message.sid} | status={message.status}"
            )
            return SendResult.success(provider_id=message.sid)

        except Exception as e:
            logger.error(f"❌ Erreur Twilio send_sms to={to} : {e}")
            return SendResult.failure(str(e))

    async def send_appointment_confirmation(
        self,
        to:               str,
        client_name:      str,
        service_type:     str,
        scheduled_at_fr:  str,
        garage_name:      str,
        garage_phone:     str,
    ) -> SendResult:
        """
        Envoie le SMS de confirmation de RDV au client.
        """
        body = (
            f"✅ RDV confirmé !\n"
            f"━━━━━━━━━━━━━━━\n"
            f"👤 {client_name}\n"
            f"🔧 {service_type.replace('_', ' ').title()}\n"
            f"📅 {scheduled_at_fr}\n"
            f"📍 {garage_name}\n"
            f"📞 {garage_phone}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"À bientôt !"
        )
        return await self.send_sms(to=to, body=body)

    async def send_urgency_alert(
        self,
        to:           str,
        garage_name:  str,
        caller_phone: str,
        location:     str,
        problem:      str,
        urgency:      str = "URGENT",
    ) -> SendResult:
        """
        Envoie une alerte SMS urgence au patron du garage.
        """
        emoji = "🚨" if urgency == "CRITIQUE" else "⚠️"
        body  = (
            f"{emoji} {urgency} — {garage_name}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📞 Client : {caller_phone}\n"
            f"📍 Lieu   : {location}\n"
            f"🔧 Pb     : {problem[:100]}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"→ Rappeler immédiatement !"
        )
        return await self.send_sms(to=to, body=body)

    async def send_missed_call_alert(
        self,
        to:           str,
        garage_name:  str,
        caller_phone: str,
        summary:      str,
    ) -> SendResult:
        """
        Alerte SMS pour un appel avec message laissé.
        """
        body = (
            f"📝 MESSAGE — {garage_name}\n"
            f"De : {caller_phone}\n"
            f"Résumé : {summary[:120]}\n"
            f"→ À rappeler dès que possible"
        )
        return await self.send_sms(to=to, body=body)

    def _normalize_phone(self, phone: str) -> str:
        """
        Normalise un numéro de téléphone au format E.164.
        Exemples :
            0612345678    → +33612345678
            +33612345678  → +33612345678 (inchangé)
            06 12 34 56 78 → +33612345678
        """
        if not phone:
            return ""

        # Supprimer espaces, tirets, points
        cleaned = phone.replace(" ", "").replace("-", "").replace(".", "")

        # Déjà au format E.164
        if cleaned.startswith("+"):
            return cleaned

        # Numéro français commençant par 0
        if cleaned.startswith("0") and len(cleaned) == 10:
            return "+33" + cleaned[1:]

        # Numéro sans indicatif (9 chiffres FR)
        if len(cleaned) == 9 and cleaned[0] in "6789":
            return "+33" + cleaned

        # Retourner tel quel si format inconnu
        return cleaned if cleaned else ""


# Instance globale
twilio_client = TwilioSMSClient()