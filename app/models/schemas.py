"""
Modèles Pydantic pour la validation des données
"""
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field


# ============================================================
# ENUMS
# ============================================================

class DemandType(str, Enum):
    PRISE_RDV            = "prise_rdv"
    INFORMATION          = "information"
    DEVIS                = "devis"
    MODIFICATION_RDV     = "modification_rdv"
    ANNULATION_RDV       = "annulation_rdv"
    DEPANNAGE_URGENT     = "depannage_urgent"
    DEPANNAGE_NON_URGENT = "depannage_non_urgent"
    RECLAMATION          = "reclamation"
    AUTRE                = "autre"


class UrgencyLevel(str, Enum):
    FAIBLE   = "faible"
    MOYENNE  = "moyenne"
    ELEVEE   = "elevee"
    CRITIQUE = "critique"


class CallStatus(str, Enum):
    RDV_PRIS           = "rdv_pris"
    RDV_MODIFIE        = "rdv_modifie"
    RDV_ANNULE         = "rdv_annule"
    INFORMATION_DONNEE = "information_donnee"
    DEVIS_PROPOSE      = "devis_propose"
    TRANSFERE_HUMAIN   = "transfere_humain"
    URGENCE_SIGNALEE   = "urgence_signalee"
    MESSAGE_LAISSE     = "message_laisse"
    ABANDONNE          = "abandonne"
    ERREUR             = "erreur"


class AppointmentStatus(str, Enum):
    PROPOSE  = "propose"
    CONFIRME = "confirme"
    ANNULE   = "annule"
    MODIFIE  = "modifie"
    COMPLETE = "complete"
    NO_SHOW  = "no_show"


# ============================================================
# MODÈLES VAPI (Webhooks entrants)
# ============================================================

class VapiMessage(BaseModel):
    """Message reçu depuis Vapi via webhook."""
    type:    str
    call:    Optional[dict] = None
    message: Optional[dict] = None


class VapiFunctionCall(BaseModel):
    """Appel de fonction (tool call) depuis l'agent Vapi."""
    name:       str
    parameters: dict = Field(default_factory=dict)


class VapiCallData(BaseModel):
    """Données d'un appel Vapi."""
    id:              str
    status:          str
    phoneNumberId:   Optional[str] = None
    customer:        Optional[dict] = None
    startedAt:       Optional[str] = None
    endedAt:         Optional[str] = None
    transcript:      Optional[str] = None
    recordingUrl:    Optional[str] = None
    summary:         Optional[str] = None
    durationSeconds: Optional[int] = None


# ============================================================
# MODÈLES MÉTIER
# ============================================================

class ClientData(BaseModel):
    """Données client collectées pendant l'appel."""
    full_name:    Optional[str] = None
    first_name:   Optional[str] = None
    last_name:    Optional[str] = None
    phone_number: str
    email:        Optional[str] = None


class VehicleData(BaseModel):
    """Données véhicule collectées pendant l'appel."""
    brand:              Optional[str] = None
    model:              Optional[str] = None
    year:               Optional[int] = None
    registration_plate: Optional[str] = None
    fuel_type:          Optional[str] = None
    mileage:            Optional[int] = None


class AppointmentData(BaseModel):
    """Données de rendez-vous."""
    service_name:     str
    scheduled_at:     datetime
    duration_minutes: int = 60
    client:           ClientData
    vehicle:          Optional[VehicleData] = None
    notes:            Optional[str] = None


class AvailabilitySlot(BaseModel):
    """Créneau disponible retourné à l'agent."""
    start:            datetime
    end:              datetime
    formatted_fr:     str
    duration_minutes: int


# ============================================================
# MODÈLES RÉPONSES TOOLS (retournés à l'agent Vapi)
# ============================================================

class ToolResult(BaseModel):
    """Résultat standard d'un tool call."""
    success: bool
    message: str
    data:    Optional[dict] = None


class AvailabilityResult(ToolResult):
    """Résultat de check_availability."""
    slots: list[AvailabilitySlot] = Field(default_factory=list)


class AppointmentResult(ToolResult):
    """Résultat de create_appointment."""
    appointment_id:    Optional[str] = None
    calcom_uid:        Optional[str] = None
    scheduled_at:      Optional[str] = None
    confirmation_sent: bool = False


# ============================================================
# MODÈLES ONBOARDING MULTI-TENANT (Étape 10)
# ============================================================

class ScheduleSlot(BaseModel):
    """Créneau horaire d'une journée."""
    start: str = Field(..., example="08:00")
    end:   str = Field(..., example="18:00")


class OnboardingRequest(BaseModel):
    """Requête d'onboarding d'un nouveau garage."""

    # Obligatoires
    name:        str = Field(..., example="Garage Martin")
    garage_type: str = Field(..., example="garage")   # garage | depanneur
    owner_phone: str = Field(..., example="+33612345678")
    owner_email: str = Field(..., example="martin@garage-martin.fr")

    # Optionnels
    owner_name:    Optional[str] = Field(None,           example="Jean Martin")
    address:       Optional[str] = Field(None,           example="12 rue de la Paix")
    city:          Optional[str] = Field(None,           example="Toulouse")
    timezone:      Optional[str] = Field("Europe/Paris", example="Europe/Paris")
    agent_name:    Optional[str] = Field("Léa",          example="Léa")
    transfer_phone: Optional[str] = Field(None,          example="+33612345678")

    # Abonnement
    subscription_plan: Optional[str] = Field("starter", example="starter")  # starter | pro | enterprise

    # Agenda
    appointment_duration: Optional[int] = Field(60, example=60)  # minutes
    schedule: Optional[Dict[str, List[ScheduleSlot]]] = Field(
        None,
        description="Horaires par jour. Si absent, horaires par défaut 8h-18h lun-ven."
    )

    # Services
    services: Optional[List[str]] = Field(
        None,
        example=["Vidange", "Révision", "Freins", "Pneus", "Climatisation"]
    )

    class Config:
        json_schema_extra = {
            "example": {
                "name":                 "Garage Martin",
                "garage_type":          "garage",
                "owner_phone":          "+33612345678",
                "owner_email":          "martin@garage-martin.fr",
                "owner_name":           "Jean Martin",
                "address":              "12 rue de la Paix",
                "city":                 "Toulouse",
                "agent_name":           "Léa",
                "transfer_phone":       "+33612345678",
                "subscription_plan":    "starter",
                "appointment_duration": 60,
                "services":             ["Vidange", "Révision", "Freins", "Pneus"],
                "schedule": {
                    "monday":    [{"start": "08:00", "end": "18:00"}],
                    "tuesday":   [{"start": "08:00", "end": "18:00"}],
                    "wednesday": [{"start": "08:00", "end": "18:00"}],
                    "thursday":  [{"start": "08:00", "end": "18:00"}],
                    "friday":    [{"start": "08:00", "end": "17:00"}],
                    "saturday":  [{"start": "08:00", "end": "12:00"}],
                    "sunday":    []
                }
            }
        }


class OnboardingStepLog(BaseModel):
    """Log d'une étape d'onboarding."""
    step:        str
    status:      str             # success | failed
    duration_ms: Optional[int]  = None
    details:     Optional[Dict[str, Any]] = None


class OnboardingResult(BaseModel):
    """Résultat complet d'un onboarding."""
    success:             bool = False
    garage_id:           Optional[str] = None
    twilio_phone_number: Optional[str] = None
    vapi_assistant_id:   Optional[str] = None
    calcom_username:     Optional[str] = None
    message:             Optional[str] = None
    error:               Optional[str] = None
    steps:               List[str] = Field(default_factory=list)

    class Config:
        json_schema_extra = {
            "example": {
                "success":             True,
                "garage_id":           "550e8400-e29b-41d4-a716-446655440000",
                "twilio_phone_number": "+33187654321",
                "vapi_assistant_id":   "vapi_ast_xxxxx",
                "calcom_username":     "garage-martin",
                "message":             "Garage 'Garage Martin' onboardé avec succès ✅",
                "steps": [
                    "✅ Supabase — garage créé (550e8400...)",
                    "✅ Twilio — numéro acheté (+33187654321)",
                    "✅ Cal.com — utilisateur créé (garage-martin), event type #42",
                    "✅ Prompt — généré (2847 caractères)",
                    "✅ Vapi — assistant créé (vapi_ast_xxxxx)"
                ]
            }
        }