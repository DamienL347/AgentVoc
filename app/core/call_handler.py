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
from app.utils.datetime_fr import format_datetime_fr
from app.utils.phone import normalize_phone, phones_match

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

        # Idempotence : si Vapi rejoue le webhook, ne pas dupliquer l'appel
        existing_call = (
            self.db.table("calls")
            .select("id, end_client_id")
            .eq("vapi_call_id", vapi_call_id)
            .limit(1)
            .execute()
        )
        if existing_call.data:
            logger.info(f"♻️ Appel {vapi_call_id} déjà enregistré, webhook ignoré")
            return {
                "call_id":         existing_call.data[0]["id"],
                "is_known_client": existing_call.data[0].get("end_client_id") is not None,
                "client_name":     None,
            }

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
        """
        Recherche un RDV existant.
        Sécurité : on cherche d'abord sur le numéro RÉEL de l'appelant
        (caller ID), pas sur un numéro dicté — sinon n'importe qui peut
        consulter/annuler le RDV d'un tiers.
        """
        self._lazy_init()

        caller_phone = self._get_caller_phone(vapi_call_id)
        dictated     = normalize_phone(parameters.get("phone_number"))

        # Numéro de confiance : le caller ID en priorité
        lookup_phones = []
        if caller_phone:
            lookup_phones.append(caller_phone)
        # Numéro dicté accepté seulement si l'appel est en numéro masqué
        if not caller_phone and dictated:
            lookup_phones.append(dictated)

        appt = None
        for phone in lookup_phones:
            result = (
                self.db.table("appointments")
                .select("id, scheduled_at, title, status, client_name, client_phone")
                .eq("garage_id", str(garage_id))
                .eq("client_phone", phone)
                .eq("status", "confirme")
                .order("scheduled_at", desc=False)
                .limit(1)
                .execute()
            )
            if result.data:
                appt = result.data[0]
                break

        if not appt:
            if caller_phone and dictated and not phones_match(caller_phone, dictated):
                # L'appelant cherche le RDV d'un autre numéro que le sien
                return {
                    "success": False,
                    "message": (
                        "Pour des raisons de sécurité, je ne peux consulter que les "
                        "rendez-vous associés au numéro depuis lequel vous appelez. "
                        "Je peux prendre un message pour que le garage vous rappelle, "
                        "ou vous transférer. Que préférez-vous ?"
                    ),
                }
            return {
                "success": False,
                "message": (
                    "Je ne trouve pas de rendez-vous associé à votre numéro. "
                    "Souhaitez-vous en prendre un nouveau ?"
                ),
            }

        date_fr = format_datetime_fr(appt["scheduled_at"])
        return {
            "success":        True,
            "appointment_id": appt["id"],
            "scheduled_at":   appt["scheduled_at"],
            "title":          appt["title"],
            "message": (
                f"J'ai trouvé votre rendez-vous : {appt['title']} "
                f"prévu le {date_fr}. "
                f"Que souhaitez-vous faire ?"
            ),
        }

    async def _handle_update_appointment(
        self,
        parameters:  dict,
        vapi_call_id: str,
        garage_id:   UUID,
    ) -> dict:
        """Modifie un RDV existant (après vérification de propriété)."""
        from app.integrations.calcom_client import calcom_client

        appointment_id  = parameters.get("appointment_id")
        new_scheduled_at = parameters.get("new_scheduled_at")

        denied = self._check_appointment_ownership(
            appointment_id, garage_id, vapi_call_id
        )
        if denied:
            return denied

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
        """Annule un RDV (après vérification de propriété)."""
        from app.integrations.calcom_client import calcom_client

        appointment_id = parameters.get("appointment_id")
        reason         = parameters.get("reason", "Annulation client")

        denied = self._check_appointment_ownership(
            appointment_id, garage_id, vapi_call_id
        )
        if denied:
            return denied

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
        from app.services.notification_service import notification_service

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
        call_id   = self._get_call_id(vapi_call_id)

        # Envoyer SMS
        if client_phone:
            date_fr = format_datetime_fr(appt.get("scheduled_at", ""))
            sms_body = (
                f"✅ RDV confirmé !\n"
                f"{appt.get('title', 'Rendez-vous')}\n"
                f"📅 {date_fr}\n"
                f"📍 Garage\n"
                f"À bientôt !"
            )
            sms_sent = bool(await notification_service.send_sms(
                to=client_phone,
                body=sms_body,
                garage_id=garage_id,
                recipient_type="client",
                call_id=call_id,
                appointment_id=appointment_id,
            ))

        # Envoyer email
        if client_email:
            mail_sent = bool(await notification_service.send_appointment_confirmation_email(
                to=client_email,
                appointment=appt,
                garage_id=garage_id,
                call_id=call_id,
                appointment_id=appointment_id,
            ))

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
            from app.services.notification_service import notification_service
            sms_number = garage.data.get("transfer_sms_number")
            if sms_number:
                await notification_service.send_sms(
                    to=sms_number,
                    body=(
                        f"🚨 TRANSFERT [{reason.upper()}]\n"
                        f"Appel transféré vers vous.\n"
                        f"Résumé : {summary[:100]}"
                    ),
                    garage_id=garage_id,
                    recipient_type="garage",
                    call_id=self._get_call_id(vapi_call_id),
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
        from app.services.notification_service import notification_service
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

        await notification_service.send_sms(
            to=garage.data["transfer_sms_number"],
            body=f"{emoji} [{priority.upper()}] {garage.data['name']}\n{message}",
            garage_id=garage_id,
            recipient_type="garage",
            call_id=self._get_call_id(vapi_call_id),
        )

        return {"success": True, "message": "Alerte envoyée."}

    async def _handle_take_message(
        self,
        parameters:  dict,
        vapi_call_id: str,
        garage_id:   UUID,
    ) -> dict:
        """Enregistre un message pour rappel."""
        from app.services.notification_service import notification_service
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
            await notification_service.send_sms(
                to=garage.data["transfer_sms_number"],
                body=(
                    f"📝 MESSAGE\n"
                    f"De : {client_name} - {client_phone}\n"
                    f"Message : {message[:150]}\n"
                    f"→ À rappeler dès que possible"
                ),
                garage_id=garage_id,
                recipient_type="garage",
                call_id=self._get_call_id(vapi_call_id),
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

    def _get_call_id(self, vapi_call_id: str) -> Optional[str]:
        """
        Traduit l'id d'appel Vapi en UUID interne (`calls.id`).
        Sert à rattacher les notifications à l'appel qui les a déclenchées.
        """
        self._lazy_init()
        try:
            result = (
                self.db.table("calls")
                .select("id")
                .eq("vapi_call_id", vapi_call_id)
                .limit(1)
                .execute()
            )
            if result.data:
                return result.data[0]["id"]
        except Exception as e:
            logger.warning(f"⚠️ Impossible de résoudre call_id pour {vapi_call_id} : {e}")
        return None

    def _get_caller_phone(self, vapi_call_id: str) -> Optional[str]:
        """Retourne le numéro réel de l'appelant (caller ID), normalisé E.164."""
        self._lazy_init()
        try:
            result = (
                self.db.table("calls")
                .select("caller_phone")
                .eq("vapi_call_id", vapi_call_id)
                .limit(1)
                .execute()
            )
            if result.data:
                return normalize_phone(result.data[0].get("caller_phone"))
        except Exception as e:
            logger.warning(f"⚠️ Impossible de récupérer le caller ID : {e}")
        return None

    def _check_appointment_ownership(
        self,
        appointment_id: Optional[str],
        garage_id:      UUID,
        vapi_call_id:   str,
    ) -> Optional[dict]:
        """
        Vérifie qu'un RDV appartient bien au garage courant ET à l'appelant.
        Retourne None si tout est OK, sinon un dict de refus à renvoyer
        tel quel à l'agent.
        """
        self._lazy_init()

        if not appointment_id:
            return {
                "success": False,
                "message": "Je n'ai pas la référence du rendez-vous. Pouvez-vous me redonner votre numéro ?",
            }

        result = (
            self.db.table("appointments")
            .select("id, garage_id, client_phone")
            .eq("id", appointment_id)
            .limit(1)
            .execute()
        )

        if not result.data:
            return {
                "success": False,
                "message": "Je ne retrouve pas ce rendez-vous. Souhaitez-vous que je prenne un message ?",
            }

        appt = result.data[0]

        # Le RDV doit appartenir au garage courant (isolation multi-tenant)
        if str(appt.get("garage_id")) != str(garage_id):
            logger.error(
                f"🚫 Tentative d'accès cross-tenant : RDV {appointment_id} "
                f"n'appartient pas au garage {garage_id}"
            )
            return {
                "success": False,
                "message": "Je ne retrouve pas ce rendez-vous. Souhaitez-vous que je prenne un message ?",
            }

        # Le RDV doit appartenir à l'appelant (caller ID)
        caller_phone = self._get_caller_phone(vapi_call_id)
        if caller_phone and not phones_match(caller_phone, appt.get("client_phone")):
            logger.warning(
                f"🚫 Caller {caller_phone} tente de modifier le RDV "
                f"{appointment_id} d'un autre numéro"
            )
            return {
                "success": False,
                "message": (
                    "Pour des raisons de sécurité, seul le titulaire du rendez-vous "
                    "peut le modifier depuis son numéro. Je peux prendre un message "
                    "pour le garage, ou vous transférer. Que préférez-vous ?"
                ),
            }

        return None

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