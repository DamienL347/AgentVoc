"""
Gestionnaire des webhooks Vapi
Reçoit et dispatche tous les événements d'appel
"""
import logging
from typing import Optional
from uuid import UUID

from app.config import settings
from app.models.schemas import (
    CallStatus,
    DemandType,
    UrgencyLevel,
    VapiCallData,
)

logger = logging.getLogger(__name__)

# ============================================================
# MOTS-CLÉS D'URGENCE
# ============================================================

URGENCY_KEYWORDS_CRITIQUE = [
    "accident", "collision", "blessé", "blessure",
    "feu", "incendie", "fumée", "brûlé",
    "danger", "secours", "urgence absolue",
]

URGENCY_KEYWORDS_ELEVEE = [
    "panne", "en panne", "ne démarre pas", "ne démarre plus",
    "bloqué", "coincé", "sur la route", "sur l'autoroute",
    "sur la nationale", "sur la rocade",
    "remorquage", "remorquer", "dépannage urgent",
    "voiture morte", "moteur cassé",
]

SENTIMENT_NEGATIVE_KEYWORDS = [
    "mécontent", "scandaleux", "inadmissible", "honteux",
    "remboursement", "avocat", "procès", "plainte",
    "nul", "incompétent", "arnaque", "voleur",
    "jamais revenir", "très déçu", "catastrophique",
]


# ============================================================
# CALL HANDLER
# ============================================================

class CallHandler:
    """
    Gère la logique métier des événements d'appel.
    Appelé par les routes webhook FastAPI.
    """

    def __init__(self):
        self.db     = None  # Initialisé au runtime
        self.twilio = None
        self.calcom = None
        self.resend = None

    def _lazy_init(self):
        """Import tardif pour éviter les imports circulaires."""
        if self.db is None:
            from app.db.supabase_client import get_supabase_client
            self.db = get_supabase_client()

    # ── Événements d'appel ───────────────────────────────────

    async def on_call_started(
        self,
        vapi_call_id:  str,
        caller_phone:  str,
        garage_id:     UUID,
    ) -> dict:
        """
        Déclenché au début de chaque appel entrant.
        Crée l'entrée en BDD et identifie le client.
        """
        self._lazy_init()

        logger.info(
            f"📞 Appel entrant | "
            f"vapi_id={vapi_call_id} | "
            f"caller={caller_phone} | "
            f"garage={garage_id}"
        )

        # Rechercher si client existant
        existing_client = self._find_client_by_phone(
            garage_id, caller_phone
        )

        # Créer l'entrée d'appel en BDD
        call_data = {
            "garage_id":    str(garage_id),
            "vapi_call_id": vapi_call_id,
            "caller_phone": caller_phone,
            "end_client_id": (
                existing_client["id"] if existing_client else None
            ),
        }

        result = (
            self.db.table("calls")
            .insert(call_data)
            .execute()
        )

        call_id = result.data[0]["id"] if result.data else None
        logger.info(f"✅ Appel enregistré en BDD : {call_id}")

        return {
            "call_id":         call_id,
            "is_known_client": existing_client is not None,
            "client_name":     (
                existing_client.get("full_name") if existing_client else None
            ),
        }

    async def on_call_ended(
        self,
        vapi_call_id:    str,
        transcript:      Optional[str],
        summary:         Optional[str],
        duration_seconds: Optional[int],
        recording_url:   Optional[str],
        call_status:     CallStatus,
    ) -> dict:
        """
        Déclenché à la fin de chaque appel.
        Met à jour la BDD avec les données finales.
        """
        self._lazy_init()

        logger.info(
            f"📴 Fin d'appel | "
            f"vapi_id={vapi_call_id} | "
            f"status={call_status} | "
            f"duration={duration_seconds}s"
        )

        # Analyser le transcript pour détecter urgence/sentiment
        urgency_level = UrgencyLevel.FAIBLE
        keywords      = []

        if transcript:
            urgency_level, keywords = self._analyze_transcript(transcript)

        # Mettre à jour l'appel en BDD
        update_data = {
            "call_status":      call_status.value,
            "transcription":    transcript,
            "summary":          summary,
            "duration_seconds": duration_seconds,
            "recording_url":    recording_url,
            "urgency_level":    urgency_level.value,
            "detected_keywords": keywords,
        }

        self.db.table("calls").update(update_data).eq(
            "vapi_call_id", vapi_call_id
        ).execute()

        logger.info(
            f"✅ Appel {vapi_call_id} mis à jour | "
            f"urgency={urgency_level}"
        )

        return {"updated": True, "urgency_level": urgency_level}

    # ── Tool calls ───────────────────────────────────────────

    async def handle_tool_call(
        self,
        tool_name:   str,
        parameters:  dict,
        vapi_call_id: str,
        garage_id:   UUID,
    ) -> dict:
        """
        Route les tool calls vers les bons handlers.
        Appelé quand l'agent Vapi appelle une fonction.
        """
        logger.info(
            f"🔧 Tool call | "
            f"tool={tool_name} | "
            f"params={parameters} | "
            f"call={vapi_call_id}"
        )

        handlers = {
            "check_availability":       self._handle_check_availability,
            "create_appointment":       self._handle_create_appointment,
            "get_appointment_by_phone": self._handle_get_appointment,
            "update_appointment":       self._handle_update_appointment,
            "cancel_appointment":       self._handle_cancel_appointment,
            "send_confirmation":        self._handle_send_confirmation,
            "transfer_call":            self._handle_transfer_call,
            "send_sms_alert":           self._handle_send_sms_alert,
            "take_message":             self._handle_take_message,
        }

        handler = handlers.get(tool_name)
        if not handler:
            logger.error(f"❌ Tool inconnu : {tool_name}")
            return {
                "success": False,
                "message": f"Outil '{tool_name}' non reconnu.",
            }

        try:
            return await handler(
                parameters=parameters,
                vapi_call_id=vapi_call_id,
                garage_id=garage_id,
            )
        except Exception as e:
            logger.error(f"❌ Erreur tool {tool_name} : {e}", exc_info=True)
            return {
                "success": False,
                "message": "Une erreur technique est survenue. Je transmets votre demande.",
            }

    # ── Handlers individuels ─────────────────────────────────

    async def _handle_check_availability(
        self,
        parameters:  dict,
        vapi_call_id: str,
        garage_id:   UUID,
    ) -> dict:
        """Vérifie les disponibilités dans Cal.com."""
        from app.integrations.calcom_client import calcom_client

        service_type   = parameters.get("service_type", "revision")
        preferred_slot = parameters.get("preferred_slot")

        slots = await calcom_client.get_available_slots(
            garage_id=garage_id,
            service_type=service_type,
            preferred_slot=preferred_slot,
        )

        if not slots:
            return {
                "success": True,
                "message": (
                    "Je n'ai pas trouvé de créneau disponible cette semaine. "
                    "Souhaitez-vous que je regarde la semaine prochaine ?"
                ),
                "slots": [],
            }

        # Formater les 3 premiers créneaux pour l'agent
        formatted = [s["formatted_fr"] for s in slots[:3]]
        slots_text = ", ".join(formatted)

        return {
            "success": True,
            "message": f"J'ai ces créneaux disponibles : {slots_text}. Lequel vous convient ?",
            "slots":   slots[:3],
        }

    async def _handle_create_appointment(
        self,
        parameters:  dict,
        vapi_call_id: str,
        garage_id:   UUID,
    ) -> dict:
        """Crée un RDV dans Cal.com et Supabase."""
        from app.integrations.calcom_client import calcom_client

        result = await calcom_client.create_booking(
            garage_id=garage_id,
            params=parameters,
        )

        if result.get("success"):
            # Lier le RDV à l'appel en BDD
            self.db.table("calls").update({
                "appointment_id": result.get("appointment_id"),
                "call_status":    CallStatus.RDV_PRIS.value,
                "collected_data": parameters,
            }).eq("vapi_call_id", vapi_call_id).execute()

        return result

    async def _handle_get_appointment(
        self,
        parameters:  dict,
        vapi_call_id: str,
        garage_id:   UUID,
    ) -> dict:
        """Recherche un RDV existant par téléphone."""
        self._lazy_init()

        phone  = parameters.get("phone_number", "")
        result = (
            self.db.table("appointments")
            .select("id, scheduled_at, title, status, client_name")
            .eq("garage_id", str(garage_id))
            .eq("client_phone", phone)
            .eq("status", "confirme")
            .order("scheduled_at", desc=False)
            .limit(1)
            .execute()
        )

        if not result.data:
            return {
                "success": False,
                "message": (
                    "Je ne trouve pas de rendez-vous associé à ce numéro. "
                    "Souhaitez-vous en prendre un nouveau ?"
                ),
            }

        appt = result.data[0]
        return {
            "success":        True,
            "appointment_id": appt["id"],
            "scheduled_at":   appt["scheduled_at"],
            "title":          appt["title"],
            "message": (
                f"J'ai trouvé votre rendez-vous : {appt['title']} "
                f"prévu le {appt['scheduled_at']}. "
                f"Que souhaitez-vous faire ?"
            ),
        }

    async def _handle_update_appointment(
        self,
        parameters:  dict,
        vapi_call_id: str,
        garage_id:   UUID,
    ) -> dict:
        """Modifie un RDV existant."""
        from app.integrations.calcom_client import calcom_client

        appointment_id  = parameters.get("appointment_id")
        new_scheduled_at = parameters.get("new_scheduled_at")

        result = await calcom_client.reschedule_booking(
            appointment_id=appointment_id,
            new_scheduled_at=new_scheduled_at,
        )

        if result.get("success"):
            self.db.table("calls").update({
                "call_status": CallStatus.RDV_MODIFIE.value,
            }).eq("vapi_call_id", vapi_call_id).execute()

        return result

    async def _handle_cancel_appointment(
        self,
        parameters:  dict,
        vapi_call_id: str,
        garage_id:   UUID,
    ) -> dict:
        """Annule un RDV."""
        from app.integrations.calcom_client import calcom_client

        appointment_id = parameters.get("appointment_id")
        reason         = parameters.get("reason", "Annulation client")

        result = await calcom_client.cancel_booking(
            appointment_id=appointment_id,
            reason=reason,
        )

        if result.get("success"):
            self.db.table("calls").update({
                "call_status": CallStatus.RDV_ANNULE.value,
            }).eq("vapi_call_id", vapi_call_id).execute()

        return result

    async def _handle_send_confirmation(
        self,
        parameters:  dict,
        vapi_call_id: str,
        garage_id:   UUID,
    ) -> dict:
        """Envoie SMS + email de confirmation."""
        from app.integrations.twilio_sms  import twilio_client
        from app.integrations.resend_email import resend_client

        client_phone   = parameters.get("client_phone")
        client_email   = parameters.get("client_email")
        appointment_id = parameters.get("appointment_id")

        # Récupérer les détails du RDV
        self._lazy_init()
        appt_result = (
            self.db.table("appointments")
            .select("*")
            .eq("id", appointment_id)
            .single()
            .execute()
        )

        if not appt_result.data:
            return {"success": False, "message": "RDV introuvable"}

        appt      = appt_result.data
        sms_sent  = False
        mail_sent = False

        # Envoyer SMS
        if client_phone:
            sms_body = (
                f"✅ RDV confirmé !\n"
                f"{appt.get('title', 'Rendez-vous')}\n"
                f"📅 {appt.get('scheduled_at', '')}\n"
                f"📍 Garage\n"
                f"À bientôt !"
            )
            sms_sent = await twilio_client.send_sms(
                to=client_phone,
                body=sms_body,
            )

        # Envoyer email
        if client_email:
            mail_sent = await resend_client.send_appointment_confirmation(
                to=client_email,
                appointment=appt,
            )

        return {
            "success":  True,
            "sms_sent": sms_sent,
            "mail_sent": mail_sent,
            "message":  "Confirmation envoyée avec succès.",
        }

    async def _handle_transfer_call(
        self,
        parameters:  dict,
        vapi_call_id: str,
        garage_id:   UUID,
    ) -> dict:
        """
        Transfère l'appel vers le patron.
        Note : Le transfert réel est géré par Vapi nativement.
        Ici on log et on envoie une alerte SMS.
        """
        self._lazy_init()

        reason  = parameters.get("reason", "hors_perimetre")
        summary = parameters.get("summary", "")

        # Récupérer le numéro de transfert du garage
        garage = (
            self.db.table("garages")
            .select("transfer_phone_number, transfer_sms_number, name")
            .eq("id", str(garage_id))
            .single()
            .execute()
        )

        transfer_phone = None
        if garage.data:
            transfer_phone = garage.data.get("transfer_phone_number")

        # Mettre à jour l'appel en BDD
        self.db.table("calls").update({
            "transfer_triggered": True,
            "transfer_reason":    reason,
            "call_status":        CallStatus.TRANSFERE_HUMAIN.value,
        }).eq("vapi_call_id", vapi_call_id).execute()

        # Envoyer alerte SMS si urgence ou réclamation
        if reason in ["urgence", "reclamation"] and garage.data:
            from app.integrations.twilio_sms import twilio_client
            sms_number = garage.data.get("transfer_sms_number")
            if sms_number:
                await twilio_client.send_sms(
                    to=sms_number,
                    body=(
                        f"🚨 TRANSFERT [{reason.upper()}]\n"
                        f"Appel transféré vers vous.\n"
                        f"Résumé : {summary[:100]}"
                    ),
                )

        logger.info(
            f"🔀 Transfert | reason={reason} | "
            f"to={transfer_phone} | call={vapi_call_id}"
        )

        return {
            "success":        True,
            "transfer_phone": transfer_phone,
            "message":        "Je vous transfère maintenant. Un instant.",
        }

    async def _handle_send_sms_alert(
        self,
        parameters:  dict,
        vapi_call_id: str,
        garage_id:   UUID,
    ) -> dict:
        """Envoie une alerte SMS urgente au patron."""
        from app.integrations.twilio_sms import twilio_client
        self._lazy_init()

        priority = parameters.get("priority", "normale")
        message  = parameters.get("message", "")

        # Récupérer le numéro d'alerte du garage
        garage = (
            self.db.table("garages")
            .select("transfer_sms_number, name")
            .eq("id", str(garage_id))
            .single()
            .execute()
        )

        if not garage.data or not garage.data.get("transfer_sms_number"):
            logger.warning(f"⚠️ Pas de numéro SMS configuré pour garage {garage_id}")
            return {"success": False, "message": "Numéro d'alerte non configuré"}

        emoji = {"critique": "🚨", "elevee": "⚠️", "normale": "📱"}.get(priority, "📱")

        await twilio_client.send_sms(
            to=garage.data["transfer_sms_number"],
            body=f"{emoji} [{priority.upper()}] {garage.data['name']}\n{message}",
        )

        return {"success": True, "message": "Alerte envoyée."}

    async def _handle_take_message(
        self,
        parameters:  dict,
        vapi_call_id: str,
        garage_id:   UUID,
    ) -> dict:
        """Enregistre un message pour rappel."""
        from app.integrations.twilio_sms import twilio_client
        self._lazy_init()

        client_name  = parameters.get("client_name", "Client")
        client_phone = parameters.get("client_phone", "")
        message      = parameters.get("message", "")

        # Mettre à jour l'appel
        self.db.table("calls").update({
            "call_status":  CallStatus.MESSAGE_LAISSE.value,
            "collected_data": {
                "client_name":  client_name,
                "client_phone": client_phone,
                "message":      message,
            },
        }).eq("vapi_call_id", vapi_call_id).execute()

        # Alerter le patron par SMS
        garage = (
            self.db.table("garages")
            .select("transfer_sms_number")
            .eq("id", str(garage_id))
            .single()
            .execute()
        )

        if garage.data and garage.data.get("transfer_sms_number"):
            await twilio_client.send_sms(
                to=garage.data["transfer_sms_number"],
                body=(
                    f"📝 MESSAGE\n"
                    f"De : {client_name} - {client_phone}\n"
                    f"Message : {message[:150]}\n"
                    f"→ À rappeler dès que possible"
                ),
            )

        return {
            "success": True,
            "message": (
                f"Très bien {client_name}, votre message est bien transmis. "
                f"Le garage vous rappellera dans les meilleurs délais. "
                f"Bonne journée !"
            ),
        }

    # ── Utilitaires ──────────────────────────────────────────

    def _find_client_by_phone(
        self,
        garage_id: UUID,
        phone:     str,
    ) -> Optional[dict]:
        """Recherche un client existant par téléphone."""
        try:
            result = (
                self.db.table("end_clients")
                .select("id, full_name, total_calls")
                .eq("garage_id", str(garage_id))
                .eq("phone_number", phone)
                .single()
                .execute()
            )
            return result.data
        except Exception:
            return None

    def _analyze_transcript(
        self,
        transcript: str,
    ) -> tuple[UrgencyLevel, list[str]]:
        """
        Analyse le transcript pour détecter le niveau d'urgence
        et les mots-clés importants.
        """
        text     = transcript.lower()
        keywords = []

        # Détecter mots-clés critiques
        for kw in URGENCY_KEYWORDS_CRITIQUE:
            if kw in text:
                keywords.append(kw)

        if keywords:
            return UrgencyLevel.CRITIQUE, keywords

        # Détecter mots-clés urgents
        for kw in URGENCY_KEYWORDS_ELEVEE:
            if kw in text:
                keywords.append(kw)

        if keywords:
            return UrgencyLevel.ELEVEE, keywords

        # Détecter sentiment négatif
        for kw in SENTIMENT_NEGATIVE_KEYWORDS:
            if kw in text:
                keywords.append(kw)

        return UrgencyLevel.FAIBLE, keywords


# ── Instance globale ─────────────────────────────────────────
call_handler = CallHandler()