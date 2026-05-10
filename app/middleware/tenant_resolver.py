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

        # Seulement sur les routes Vapi
        if request.url.path.startswith(TENANT_ROUTES):
            try:
                phone_number = await self._extract_phone_number(request)
                if phone_number:
                    garage = await self._resolve_garage(phone_number)
                    if garage:
                        request.state.garage    = garage
                        request.state.garage_id = garage["id"]
                        logger.debug(
                            f"[TENANT] ✅ Garage résolu : {garage['name']} "
                            f"({garage['id']}) pour le numéro {phone_number}"
                        )
                    else:
                        logger.warning(
                            f"[TENANT] ⚠️ Aucun garage trouvé pour le numéro {phone_number}"
                        )
                else:
                    logger.debug("[TENANT] Pas de numéro Twilio trouvé dans le payload")

            except Exception as e:
                # Ne jamais bloquer un appel pour une erreur de résolution
                logger.error(f"[TENANT] ❌ Erreur résolution tenant : {e}")

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


# ── Helper : récupérer le garage depuis request.state ───────────────────────

def get_current_garage(request: Request) -> Optional[dict]:
    """
    Helper à utiliser dans les endpoints pour accéder au garage résolu.

    Usage dans un endpoint :
        garage = get_current_garage(request)
        if garage:
            garage_id = garage["id"]
    """
    return getattr(request.state, "garage", None)


def get_current_garage_id(request: Request) -> Optional[str]:
    """Retourne uniquement l'ID du garage résolu."""
    return getattr(request.state, "garage_id", None)