# app/middleware/tenant_resolver.py
"""
Middleware de résolution du tenant (garage) à chaque appel entrant.

Fonctionnement :
  1. Intercepte les requêtes sur /api/webhook/* et /api/tools/*
  2. Extrait le numéro Twilio depuis le body Vapi
  3. Retrouve le garage correspondant en Supabase
  4. Injecte le garage dans request.state.garage
  5. Si garage introuvable → continue sans bloquer (log warning)
"""

import json
import logging
from typing import Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.db.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

# Routes concernées par la résolution du tenant
TENANT_ROUTES = ("/api/webhook", "/api/tools")


class TenantResolverMiddleware(BaseHTTPMiddleware):
    """
    Résout le garage (tenant) à partir du numéro Twilio
    présent dans le payload Vapi entrant.
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.supabase = get_supabase_client()

    async def dispatch(self, request: Request, call_next):
        # Initialiser à None par défaut
        request.state.garage    = None
        request.state.garage_id = None
        request.state.called_number = None

        # Seulement sur les routes Vapi
        if request.url.path.startswith(TENANT_ROUTES):
            try:
                # On extrait le numéro appelé, mais on NE résout PAS le garage ici.
                #
                # Optimisation étape 12 : la résolution coûte un aller-retour
                # Supabase sur CHAQUE webhook et CHAQUE appel d'outil (~50-150 ms),
                # pendant lequel l'agent reste muet au téléphone. Or les handlers
                # identifient le garage par `assistant.metadata.garage_id`, présent
                # dans le payload : personne ne lisait `request.state.garage`.
                #
                # La résolution reste disponible à la demande via
                # `resolve_garage_from_request()` — utile en secours si un jour un
                # assistant arrive sans métadonnées.
                request.state.called_number = await self._extract_phone_number(request)

            except Exception as e:
                # Ne jamais bloquer un appel pour une erreur de résolution
                logger.error(f"[TENANT] ❌ Erreur extraction numéro : {e}")

        response = await call_next(request)
        return response

    # ── Extraction du numéro Twilio ──────────────────────────────────────────

    async def _extract_phone_number(self, request: Request) -> Optional[str]:
        """
        Extrait le numéro Twilio du payload Vapi.
        Le numéro est dans : message.call.phoneNumber.number
        ou dans            : message.phoneNumber.number
        """
        try:
            # Lire et mettre en cache le body (sinon FastAPI ne peut plus le lire)
            body_bytes = await request.body()
            if not body_bytes:
                return None

            # Stocker le body pour que le endpoint puisse le relire
            request.state.body = body_bytes

            body = json.loads(body_bytes)

            # Chercher le numéro dans les différentes structures Vapi possibles
            candidates = [
                # Structure standard webhook
                body.get("message", {}).get("call", {}).get("phoneNumberId"),
                body.get("message", {}).get("phoneNumber", {}).get("number"),
                # Structure tool call
                body.get("call", {}).get("phoneNumber", {}).get("number"),
                body.get("phoneNumber", {}).get("number"),
            ]

            for number in candidates:
                if number and isinstance(number, str) and number.startswith("+"):
                    return number

            return None

        except (json.JSONDecodeError, AttributeError):
            return None

    # ── Résolution du garage via Supabase ────────────────────────────────────

    async def _resolve_garage(self, phone_number: str) -> Optional[dict]:
        """
        Retrouve le garage par son numéro Twilio.
        Utilise la fonction SQL get_garage_by_phone() créée en étape 10.1.
        """
        try:
            resp = self.supabase.rpc(
                "get_garage_by_phone",
                {"p_phone": phone_number}
            ).execute()

            if resp.data and len(resp.data) > 0:
                return resp.data[0]
            return None

        except Exception as e:
            logger.error(f"[TENANT] Erreur Supabase : {e}")
            return None


# ── Helpers : accès au garage ────────────────────────────────────────────────

async def resolve_garage_from_request(request: Request) -> Optional[dict]:
    """
    Résout le garage à partir du numéro appelé — À LA DEMANDE.

    Coûte une requête Supabase : à n'appeler que si le `garage_id` des
    métadonnées de l'assistant est absent. Le résultat est mémorisé sur la
    requête pour qu'un second appel dans le même cycle soit gratuit.
    """
    déjà = getattr(request.state, "garage", None)
    if déjà:
        return déjà

    numero = getattr(request.state, "called_number", None)
    if not numero:
        return None

    middleware = TenantResolverMiddleware.__new__(TenantResolverMiddleware)
    middleware.supabase = get_supabase_client()
    garage = await middleware._resolve_garage(numero)

    if garage:
        request.state.garage    = garage
        request.state.garage_id = garage["id"]
        logger.info(f"[TENANT] Garage résolu à la demande : {garage['name']}")
    else:
        logger.warning(f"[TENANT] Aucun garage pour le numéro {numero}")

    return garage


def get_current_garage(request: Request) -> Optional[dict]:
    """
    Garage déjà résolu, sans requête réseau.

    Retourne None si personne ne l'a résolu : la résolution n'est plus
    automatique (voir `resolve_garage_from_request`).
    """
    return getattr(request.state, "garage", None)


def get_current_garage_id(request: Request) -> Optional[str]:
    """Retourne uniquement l'ID du garage résolu."""
    return getattr(request.state, "garage_id", None)