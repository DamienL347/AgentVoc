# app/api/onboarding.py
"""
Routes d'onboarding multi-tenant AgentVoc
POST /onboarding/garage  → Crée un nouveau garage complet
GET  /onboarding/status  → Liste le statut de tous les garages
GET  /onboarding/status/{garage_id} → Statut détaillé d'un garage
"""

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, BackgroundTasks

from app.models.schemas import OnboardingRequest, OnboardingResult
from app.services.onboarding_service import OnboardingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/onboarding", tags=["Onboarding"])


# ── POST /onboarding/garage ───────────────────────────────────────────────────

@router.post(
    "/garage",
    response_model=OnboardingResult,
    summary="Onboarder un nouveau garage",
    description="""
Crée un nouveau garage complet en 5 étapes automatiques :
1. Enregistrement Supabase
2. Achat numéro Twilio FR
3. Configuration Cal.com (utilisateur + créneaux + event type)
4. Génération system prompt
5. Création assistant Vapi

Retourne les IDs de toutes les ressources créées.
    """,
    status_code=201,
)
async def onboard_garage(req: OnboardingRequest) -> OnboardingResult:
    """
    Onboarde un nouveau garage.
    Durée estimée : 10-20 secondes (appels API externes).
    """
    logger.info(f"[ONBOARDING] Démarrage pour '{req.name}' ({req.garage_type})")

    service = OnboardingService()
    result  = await service.run(req)

    if not result.success:
        raise HTTPException(
            status_code=500,
            detail={
                "error":   result.error,
                "steps":   result.steps,
                "message": "Onboarding échoué — voir les logs pour le détail",
            }
        )

    return result


# ── GET /onboarding/status ────────────────────────────────────────────────────

@router.get(
    "/status",
    summary="Statut de tous les garages",
    description="Retourne la vue v_onboarding_status depuis Supabase.",
)
async def get_all_onboarding_status():
    """Liste tous les garages avec leur statut d'onboarding."""
    from app.db.supabase_client import get_supabase_client
    try:
        supabase = get_supabase_client()
        resp = supabase.table("v_onboarding_status").select("*").execute()
        return {"garages": resp.data, "total": len(resp.data)}
    except Exception as e:
        logger.error(f"[ONBOARDING] Erreur statut : {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── GET /onboarding/status/{garage_id} ───────────────────────────────────────

@router.get(
    "/status/{garage_id}",
    summary="Statut détaillé d'un garage",
    description="Retourne le garage + tous ses logs d'onboarding.",
)
async def get_garage_onboarding_status(garage_id: UUID):
    """Détail complet de l'onboarding d'un garage spécifique."""
    from app.db.supabase_client import get_supabase_client
    try:
        supabase = get_supabase_client()

        # Infos garage
        garage_resp = supabase.table("garages").select(
            "id, name, garage_type, onboarding_status, onboarding_completed_at, "
            "onboarding_error, twilio_phone_number, vapi_assistant_id, "
            "calcom_username, is_active, created_at"
        ).eq("id", str(garage_id)).single().execute()

        if not garage_resp.data:
            raise HTTPException(status_code=404, detail="Garage introuvable")

        # Logs d'onboarding
        logs_resp = supabase.table("onboarding_logs").select("*") \
            .eq("garage_id", str(garage_id)) \
            .order("created_at", desc=False) \
            .execute()

        return {
            "garage": garage_resp.data,
            "logs":   logs_resp.data,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ONBOARDING] Erreur statut garage {garage_id} : {e}")
        raise HTTPException(status_code=500, detail=str(e))