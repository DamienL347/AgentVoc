"""
Client Resend — Envoi d'emails de confirmation RDV
"""
import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


# ============================================================
# TEMPLATES EMAIL HTML
# ============================================================

def _build_confirmation_html(
    client_name:     str,
    service_type:    str,
    scheduled_at_fr: str,
    garage_name:     str,
    garage_address:  str,
    garage_phone:    str,
    vehicle_info:    str = "",
    notes:           str = "",
) -> str:
    """Génère le HTML de l'email de confirmation RDV."""

    vehicle_section = ""
    if vehicle_info:
        vehicle_section = f"""
        <tr>
            <td style="padding:8px 0;color:#666;font-size:14px;">🚗 Véhicule</td>
            <td style="padding:8px 0;font-size:14px;font-weight:600;">{vehicle_info}</td>
        </tr>"""

    notes_section = ""
    if notes:
        notes_section = f"""
        <div style="margin-top:20px;padding:15px;background:#fff8e1;border-left:4px solid #ffc107;border-radius:4px;">
            <p style="margin:0;font-size:13px;color:#666;">📝 Note : {notes}</p>
        </div>"""

    return f"""
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Confirmation de rendez-vous</title>
</head>
<body style="margin:0;padding:0;font-family:Arial,sans-serif;background:#f5f5f5;">
    <div style="max-width:600px;margin:40px auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">

        <!-- Header -->
        <div style="background:#1a1a2e;padding:30px;text-align:center;">
            <h1 style="color:#fff;margin:0;font-size:22px;">✅ Rendez-vous confirmé</h1>
            <p style="color:#a0a0c0;margin:8px 0 0;font-size:14px;">{garage_name}</p>
        </div>

        <!-- Body -->
        <div style="padding:30px;">
            <p style="font-size:16px;color:#333;margin-top:0;">
                Bonjour <strong>{client_name}</strong>,
            </p>
            <p style="color:#555;font-size:14px;line-height:1.6;">
                Votre rendez-vous a bien été enregistré. Voici le récapitulatif :
            </p>

            <!-- Détails RDV -->
            <div style="background:#f8f9fa;border-radius:8px;padding:20px;margin:20px 0;">
                <table style="width:100%;border-collapse:collapse;">
                    <tr>
                        <td style="padding:8px 0;color:#666;font-size:14px;">🔧 Intervention</td>
                        <td style="padding:8px 0;font-size:14px;font-weight:600;">{service_type.replace('_', ' ').title()}</td>
                    </tr>
                    <tr>
                        <td style="padding:8px 0;color:#666;font-size:14px;">📅 Date & Heure</td>
                        <td style="padding:8px 0;font-size:14px;font-weight:600;color:#2196F3;">{scheduled_at_fr}</td>
                    </tr>
                    {vehicle_section}
                    <tr>
                        <td style="padding:8px 0;color:#666;font-size:14px;">📍 Adresse</td>
                        <td style="padding:8px 0;font-size:14px;">{garage_address}</td>
                    </tr>
                    <tr>
                        <td style="padding:8px 0;color:#666;font-size:14px;">📞 Téléphone</td>
                        <td style="padding:8px 0;font-size:14px;">{garage_phone}</td>
                    </tr>
                </table>
            </div>

            {notes_section}

            <!-- CTA Annulation -->
            <div style="margin-top:25px;padding:15px;background:#fff3f3;border-radius:8px;text-align:center;">
                <p style="margin:0;font-size:13px;color:#666;">
                    Besoin d'annuler ou modifier ? Appelez-nous au
                    <a href="tel:{garage_phone}" style="color:#e53935;font-weight:600;">{garage_phone}</a>
                </p>
            </div>
        </div>

        <!-- Footer -->
        <div style="background:#f8f9fa;padding:20px;text-align:center;border-top:1px solid #eee;">
            <p style="margin:0;font-size:12px;color:#999;">
                Cet email a été envoyé automatiquement par l'assistant vocal de {garage_name}.
            </p>
            <p style="margin:8px 0 0;font-size:12px;color:#bbb;">
                Propulsé par <strong>AgentLumy</strong> — agentlumy.com
            </p>
        </div>
    </div>
</body>
</html>"""


def _build_alert_html(
    garage_name:  str,
    caller_phone: str,
    summary:      str,
    urgency:      str,
) -> str:
    """Génère le HTML d'une alerte email pour le garage."""

    color = "#e53935" if urgency in ["critique", "elevee"] else "#ff9800"
    emoji = "🚨" if urgency == "critique" else "⚠️"

    return f"""
<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"><title>Alerte — {garage_name}</title></head>
<body style="margin:0;padding:20px;font-family:Arial,sans-serif;background:#f5f5f5;">
    <div style="max-width:500px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden;border-top:4px solid {color};">
        <div style="padding:20px;background:{color};color:#fff;">
            <h2 style="margin:0;">{emoji} Alerte {urgency.upper()} — {garage_name}</h2>
        </div>
        <div style="padding:20px;">
            <p><strong>📞 Appelant :</strong> {caller_phone}</p>
            <p><strong>📝 Résumé :</strong> {summary}</p>
            <hr style="border:none;border-top:1px solid #eee;">
            <p style="color:#999;font-size:12px;">
                Alerte générée automatiquement par AgentLumy
            </p>
        </div>
    </div>
</body>
</html>"""


# ============================================================
# CLIENT RESEND
# ============================================================

class ResendEmailClient:
    """
    Client Resend pour l'envoi d'emails transactionnels.
    """

    def __init__(self):
        self.api_key    = settings.RESEND_API_KEY
        self.from_email = settings.RESEND_FROM_EMAIL
        self._client    = None

    def _get_client(self):
        """Initialisation lazy du client Resend."""
        if self._client is None:
            import resend
            resend.api_key = self.api_key
            self._client   = resend
        return self._client

    async def send_email(
        self,
        to:      str | list[str],
        subject: str,
        html:    str,
        text:    Optional[str] = None,
    ) -> bool:
        """
        Envoie un email via Resend.

        Args:
            to      : Destinataire(s)
            subject : Objet de l'email
            html    : Corps HTML
            text    : Corps texte (fallback)

        Returns:
            bool : True si envoyé avec succès
        """
        if not self.api_key:
            logger.warning("⚠️ Resend non configuré — email non envoyé")
            return False

        if isinstance(to, str):
            to = [to]

        try:
            resend = self._get_client()

            params = {
                "from":    self.from_email,
                "to":      to,
                "subject": subject,
                "html":    html,
            }
            if text:
                params["text"] = text

            response = resend.Emails.send(params)
            email_id = response.get("id", "unknown")

            logger.info(
                f"✅ Email envoyé | to={to} | "
                f"subject='{subject}' | id={email_id}"
            )
            return True

        except Exception as e:
            logger.error(f"❌ Erreur Resend send_email to={to} : {e}")
            return False

    async def send_appointment_confirmation(
        self,
        to:              str,
        appointment:     dict,
    ) -> bool:
        """
        Envoie l'email de confirmation de RDV au client.

        Args:
            to          : Email du client
            appointment : Dict avec les données du RDV (depuis Supabase)
        """
        if not to or "@" not in to:
            logger.warning(f"⚠️ Email invalide : {to}")
            return False

        # Récupérer les infos du garage
        garage_name    = appointment.get("garage_name", "le garage")
        garage_address = appointment.get("garage_address", "")
        garage_phone   = appointment.get("garage_phone", "")
        client_name    = appointment.get("client_name", "Client")
        service_type   = appointment.get("service_type", "intervention")
        scheduled_fr   = appointment.get("scheduled_at_fr", appointment.get("scheduled_at", ""))
        vehicle_info   = " ".join(filter(None, [
            appointment.get("vehicle_brand", ""),
            appointment.get("vehicle_model", ""),
        ]))

        html = _build_confirmation_html(
            client_name=client_name,
            service_type=service_type,
            scheduled_at_fr=scheduled_fr,
            garage_name=garage_name,
            garage_address=garage_address,
            garage_phone=garage_phone,
            vehicle_info=vehicle_info,
        )

        text = (
            f"Rendez-vous confirmé !\n"
            f"Intervention : {service_type}\n"
            f"Date : {scheduled_fr}\n"
            f"Garage : {garage_name}\n"
            f"Adresse : {garage_address}\n"
            f"Tél : {garage_phone}"
        )

        return await self.send_email(
            to=to,
            subject=f"✅ RDV confirmé — {garage_name}",
            html=html,
            text=text,
        )

    async def send_alert_to_garage(
        self,
        to:           str,
        garage_name:  str,
        caller_phone: str,
        summary:      str,
        urgency:      str = "normale",
    ) -> bool:
        """Envoie une alerte email au propriétaire du garage."""

        if not to or "@" not in to:
            return False

        html = _build_alert_html(
            garage_name=garage_name,
            caller_phone=caller_phone,
            summary=summary,
            urgency=urgency,
        )

        emoji   = "🚨" if urgency in ["critique", "elevee"] else "📝"
        subject = f"{emoji} [{urgency.upper()}] Alerte appel — {garage_name}"

        return await self.send_email(to=to, subject=subject, html=html)


# Instance globale
resend_client = ResendEmailClient()