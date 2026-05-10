# app/services/onboarding_service.py
"""
Service d'onboarding multi-tenant AgentVoc
Orchestre la création complète d'un nouveau garage :
  1. Supabase (garage + log)
  2. Twilio (achat numéro FR)
  3. Cal.com (utilisateur + créneaux + event type)
  4. System prompt dynamique
  5. Vapi (assistant dédié)
"""

import time
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from app.config import settings
from app.db.supabase_client import get_supabase_client
from app.integrations.vapi_client import VapiClient
from app.integrations.calcom_client import CalComClient
from app.prompts.system_prompt import generate_system_prompt
from app.models.schemas import OnboardingRequest, OnboardingResult, OnboardingStepLog

from twilio.rest import Client as TwilioClient

logger = logging.getLogger(__name__)


# ── Constantes ──────────────────────────────────────────────────────────────

# Préfixe des numéros FR à acheter (mobile professionnel)
TWILIO_FR_AREA_CODE = None          # None = Twilio choisit automatiquement
TWILIO_FR_COUNTRY   = "FR"
TWILIO_NUMBER_TYPE  = "local"       # local | mobile | tollFree

# Horaires par défaut si le garage n'en précise pas
DEFAULT_SCHEDULE = {
    "monday":    [{"start": "08:00", "end": "18:00"}],
    "tuesday":   [{"start": "08:00", "end": "18:00"}],
    "wednesday": [{"start": "08:00", "end": "18:00"}],
    "thursday":  [{"start": "08:00", "end": "18:00"}],
    "friday":    [{"start": "08:00", "end": "17:00"}],
    "saturday":  [{"start": "08:00", "end": "12:00"}],
    "sunday":    [],
}

CALCOM_EVENT_DURATION = 60          # minutes par défaut pour un RDV garage


# ── Classe principale ────────────────────────────────────────────────────────

class OnboardingService:
    """Orchestre l'onboarding complet d'un nouveau garage."""

    def __init__(self):
        self.supabase  = get_supabase_client()
        self.vapi      = VapiClient()
        self.calcom    = CalComClient()
        self.twilio    = TwilioClient(
            settings.TWILIO_ACCOUNT_SID,
            settings.TWILIO_AUTH_TOKEN
        )

    # ── Point d'entrée public ────────────────────────────────────────────────

    async def run(self, req: "OnboardingRequest") -> "OnboardingResult":
        """
        Exécute l'onboarding complet.
        En cas d'erreur sur une étape, loggue et lève une exception
        pour que le endpoint puisse retourner un 500 propre.
        """
        garage_id: Optional[str] = None
        result = OnboardingResult(success=False)

        try:
            # ── Étape 1 : Supabase ──────────────────────────────────────────
            garage_id = await self._step_create_garage(req, result)

            # ── Étape 2 : Twilio ────────────────────────────────────────────
            twilio_number, twilio_sid = await self._step_buy_twilio_number(
                garage_id, req, result
            )

            # ── Étape 3 : Cal.com ───────────────────────────────────────────
            calcom_user_id, calcom_username, calcom_event_type_id = \
                await self._step_setup_calcom(garage_id, req, result)

            # ── Étape 4 : System prompt ─────────────────────────────────────
            system_prompt = await self._step_generate_prompt(
                garage_id, req, calcom_username, twilio_number, result
            )

            # ── Étape 5 : Vapi ──────────────────────────────────────────────
            vapi_assistant_id, vapi_phone_number_id = await self._step_create_vapi(
                garage_id, req, twilio_number, twilio_sid, system_prompt, result
            )

            # ── Finalisation Supabase ───────────────────────────────────────
            await self._finalize_garage(
                garage_id,
                twilio_number, twilio_sid,
                vapi_assistant_id, vapi_phone_number_id,
                calcom_user_id, calcom_username, calcom_event_type_id
            )

            result.success    = True
            result.garage_id  = garage_id
            result.message    = f"Garage '{req.name}' onboardé avec succès ✅"
            logger.info(f"[ONBOARDING] ✅ {req.name} — {garage_id}")

        except OnboardingStepError as e:
            logger.error(f"[ONBOARDING] ❌ Étape '{e.step}' échouée : {e}")
            if garage_id:
                await self._mark_failed(garage_id, str(e))
            result.success = False
            result.error   = str(e)

        return result

    # ── Étape 1 : Créer le garage en Supabase ────────────────────────────────

    async def _step_create_garage(
        self, req: "OnboardingRequest", result: "OnboardingResult"
    ) -> str:
        step = "create_supabase_garage"
        t0 = time.time()
        try:
            slug = self._make_calcom_username(req.name)
            data = {
                "name":             req.name,
                "slug":             slug,
                "garage_type":      req.garage_type,
                "phone_number":     req.owner_phone,
                "email":            req.owner_email,
                "address_street":   req.address,
                "address_city":     req.city,
                "address_country":  "FR",
                "agent_name":       req.agent_name or "Léa",
                "transfer_phone_number": req.transfer_phone or req.owner_phone,
                "plan":             req.subscription_plan or "starter",
                "onboarding_status": "in_progress",
                "status":           "trial",
            }
            resp = self.supabase.table("garages").insert(data).execute()
            garage_id = resp.data[0]["id"]

            await self._log_step(garage_id, step, "success",
                                 {"garage_id": garage_id}, t0)
            result.steps.append(f"✅ Supabase — garage créé ({garage_id})")
            return garage_id

        except Exception as e:
            await self._log_step(None, step, "failed", error=str(e), t0=t0)
            raise OnboardingStepError(step, e)

    # ── Étape 2 : Acheter un numéro Twilio FR ────────────────────────────────

    async def _step_buy_twilio_number(
        self, garage_id: str, req: "OnboardingRequest", result: "OnboardingResult"
    ):
        step = "buy_twilio_number"
        t0 = time.time()
        try:
            # ── Mode DEV : réutilise le numéro trial existant ──────────────
            if settings.APP_ENV != "production":
                twilio_number = settings.TWILIO_PHONE_NUMBER
                twilio_sid    = "TRIAL_SID"
                await self._log_step(garage_id, step, "success",
                                     {"number": twilio_number, "mode": "trial"}, t0)
                result.steps.append(f"✅ Twilio — numéro trial utilisé ({twilio_number})")
                result.twilio_phone_number = twilio_number
                return twilio_number, twilio_sid

            # ── Mode PRODUCTION : achat d'un vrai numéro FR ───────────────
            available = self.twilio.available_phone_numbers(TWILIO_FR_COUNTRY) \
                .local.list(limit=5, voice_enabled=True, sms_enabled=True)

            if not available:
                raise ValueError("Aucun numéro FR disponible chez Twilio")

            chosen = available[0].phone_number

            purchased = self.twilio.incoming_phone_numbers.create(
                phone_number=chosen,
                friendly_name=f"AgentLumy — {req.name}",
                voice_url=f"{settings.APP_BASE_URL}/webhook/vapi",
                voice_method="POST",
                sms_url=f"{settings.APP_BASE_URL}/webhook/sms",
                sms_method="POST",
            )

            twilio_sid    = purchased.sid
            twilio_number = purchased.phone_number

            await self._log_step(garage_id, step, "success",
                                 {"number": twilio_number, "sid": twilio_sid}, t0)
            result.steps.append(f"✅ Twilio — numéro acheté ({twilio_number})")
            result.twilio_phone_number = twilio_number
            return twilio_number, twilio_sid

        except Exception as e:
            await self._log_step(garage_id, step, "failed", error=str(e), t0=t0)
            raise OnboardingStepError(step, e)

    # ── Étape 3 : Configurer Cal.com ─────────────────────────────────────────

    async def _step_setup_calcom(
        self, garage_id: str, req: "OnboardingRequest", result: "OnboardingResult"
    ):
        step = "setup_calcom"
        t0 = time.time()
        try:
            # 3a. Créer l'utilisateur Cal.com
            username = self._make_calcom_username(req.name)
            user_resp = await self.calcom.create_managed_user(
                email=f"{username}@agentlumy.com",
                name=req.name,
                username=username,
                timezone=req.timezone or "Europe/Paris",
                locale="fr",
            )
            calcom_user_id = user_resp["userId"]
            access_token   = user_resp["accessToken"]   # token pour les appels suivants

            # 3b. Créer le schedule (horaires)
            schedule = req.schedule or DEFAULT_SCHEDULE
            await self.calcom.create_schedule(
                access_token=access_token,
                name="Horaires garage",
                timezone=req.timezone or "Europe/Paris",
                availability=schedule,
            )

            # 3c. Créer l'event type "Rendez-vous"
            event_resp = await self.calcom.create_event_type(
                access_token=access_token,
                title="Rendez-vous garage",
                slug=f"rdv-{username}",
                length=req.appointment_duration or CALCOM_EVENT_DURATION,
                description="Réservation en ligne — " + req.name,
            )
            calcom_event_type_id = event_resp["id"]

            await self._log_step(garage_id, step, "success", {
                "calcom_user_id":       calcom_user_id,
                "calcom_username":      username,
                "calcom_event_type_id": calcom_event_type_id,
            }, t0)
            result.steps.append(
                f"✅ Cal.com — utilisateur créé ({username}), event type #{calcom_event_type_id}"
            )
            return calcom_user_id, username, calcom_event_type_id

        except Exception as e:
            await self._log_step(garage_id, step, "failed", error=str(e), t0=t0)
            raise OnboardingStepError(step, e)

    # ── Étape 4 : Générer le system prompt ───────────────────────────────────

    async def _step_generate_prompt(
        self, garage_id: str, req: "OnboardingRequest",
        calcom_username: str, twilio_number: str,
        result: "OnboardingResult"
    ) -> str:
        step = "generate_system_prompt"
        t0 = time.time()
        try:
            prompt = generate_system_prompt(
                garage_type=req.garage_type,
                garage_name=req.name,
                agent_name=req.agent_name or "Léa",
                owner_name=req.owner_name,
                phone=twilio_number,
                address=req.address,
                city=req.city,
                services=req.services or [],
                schedule=req.schedule or DEFAULT_SCHEDULE,
                calcom_username=calcom_username,
                transfer_phone=req.transfer_phone or req.owner_phone,
                timezone=req.timezone or "Europe/Paris",
            )

            # Sauvegarder le prompt versionné en BDD
            self.supabase.table("agent_prompts").insert({
                "garage_id":   garage_id,
                "version":     1,
                "system_prompt": prompt,
                "is_active":   True,
                "created_by":  "onboarding_service",
            }).execute()

            await self._log_step(garage_id, step, "success",
                                 {"prompt_length": len(prompt)}, t0)
            result.steps.append(f"✅ Prompt — généré ({len(prompt)} caractères)")
            return prompt

        except Exception as e:
            await self._log_step(garage_id, step, "failed", error=str(e), t0=t0)
            raise OnboardingStepError(step, e)

    # ── Étape 5 : Créer l'assistant Vapi ─────────────────────────────────────

    async def _step_create_vapi(
        self, garage_id: str, req: "OnboardingRequest",
        twilio_number: str, twilio_sid: str,
        system_prompt: str, result: "OnboardingResult"
    ):
        step = "create_vapi_assistant"
        t0 = time.time()
        try:
            # 5a. Créer l'assistant
            assistant = await self.vapi.create_assistant(
                garage_id=garage_id,
                garage_name=req.name,
                system_prompt=system_prompt,
                first_message=(
                    f"Bonjour, je suis {req.agent_name or 'Léa'} "
                    f"du {req.name}. Comment puis-je vous aider ?"
                ),
            )
            vapi_assistant_id = assistant["id"]

            # 5b. Lier le numéro Twilio à Vapi (skip en mode dev/trial)
            if settings.APP_ENV == "production":
                phone_number = await self.vapi.create_phone_number(
                    twilio_number=twilio_number,
                    twilio_account_sid=settings.TWILIO_ACCOUNT_SID,
                    twilio_auth_token=settings.TWILIO_AUTH_TOKEN,
                    assistant_id=vapi_assistant_id,
                    label=f"AgentLumy — {req.name}",
                )
                vapi_phone_number_id = phone_number["id"]
            else:
                vapi_phone_number_id = "TRIAL_PHONE_ID"
                logger.info("⚠️ Vapi phone number linking skipped (mode dev/trial)")

            await self._log_step(garage_id, step, "success", {
                "vapi_assistant_id":    vapi_assistant_id,
                "vapi_phone_number_id": vapi_phone_number_id,
            }, t0)
            result.steps.append(
                f"✅ Vapi — assistant créé ({vapi_assistant_id})"
            )
            result.vapi_assistant_id = vapi_assistant_id
            return vapi_assistant_id, vapi_phone_number_id

        except Exception as e:
            await self._log_step(garage_id, step, "failed", error=str(e), t0=t0)
            raise OnboardingStepError(step, e)

    # ── Finalisation ─────────────────────────────────────────────────────────

    async def _finalize_garage(
        self, garage_id: str,
        twilio_number: str, twilio_sid: str,
        vapi_assistant_id: str, vapi_phone_number_id: str,
        calcom_user_id: int, calcom_username: str, calcom_event_type_id: int
    ):
        """Met à jour le garage avec tous les IDs externes et l'active."""
        self.supabase.table("garages").update({
            "twilio_phone_number":     twilio_number,
            "twilio_phone_sid":        twilio_sid,
            "vapi_assistant_id":       vapi_assistant_id,
            "vapi_phone_number_id":    vapi_phone_number_id,
            "calcom_user_id":          calcom_user_id,
            "calcom_username":         calcom_username,
            "calcom_event_type_id":    calcom_event_type_id,
            "onboarding_status":       "completed",
            "onboarding_completed_at": datetime.now(timezone.utc).isoformat(),
            "status":                  "active",        }).eq("id", garage_id).execute()

    async def _mark_failed(self, garage_id: str, error: str):
        self.supabase.table("garages").update({
            "onboarding_status": "failed",
            "onboarding_error":  error[:500],
        }).eq("id", garage_id).execute()

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _make_calcom_username(garage_name: str) -> str:
        """'Garage Martin Toulouse' → 'garage-martin-toulouse'"""
        import re
        import unicodedata
        name = unicodedata.normalize("NFD", garage_name.lower())
        name = "".join(c for c in name if unicodedata.category(c) != "Mn")
        name = re.sub(r"[^a-z0-9]+", "-", name).strip("-")
        return name[:30]

    async def _log_step(
        self, garage_id: Optional[str], step: str, status: str,
        details: dict = None, t0: float = None, error: str = None
    ):
        try:
            row = {
                "garage_id":     garage_id,
                "step":          step,
                "status":        status,
                "details":       details or {},
                "error_message": error,
                "duration_ms":   int((time.time() - t0) * 1000) if t0 else None,
            }
            # garage_id peut être None si l'étape 1 a échoué
            if garage_id:
                self.supabase.table("onboarding_logs").insert(row).execute()
        except Exception:
            pass  # ne pas planter le process pour un log raté


# ── Exception métier ─────────────────────────────────────────────────────────

class OnboardingStepError(Exception):
    def __init__(self, step: str, original: Exception):
        self.step = step
        super().__init__(f"[{step}] {original}")