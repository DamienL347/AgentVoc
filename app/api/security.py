"""
Sécurité des endpoints exposés à Vapi.
Dépendance FastAPI réutilisable pour exiger une signature HMAC valide.
"""
import logging

from fastapi import Header, HTTPException, Request, status

from app.config import settings
from app.integrations.vapi_client import verify_vapi_signature

logger = logging.getLogger(__name__)


async def require_vapi_signature(
    request: Request,
    x_vapi_signature: str = Header(None, alias="x-vapi-signature"),
) -> None:
    """
    Rejette toute requête dont la signature HMAC Vapi est absente ou invalide.

    Règles :
    - Secret configuré  → signature obligatoire ET valide (fail closed)
    - Secret absent en production → requête refusée (mauvaise config)
    - Secret absent en développement → accepté avec warning
    """
    secret = settings.VAPI_WEBHOOK_SECRET

    if not secret:
        if settings.is_production:
            logger.error("❌ VAPI_WEBHOOK_SECRET manquant en production — requête refusée")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Configuration serveur incomplète",
            )
        logger.warning("⚠️ VAPI_WEBHOOK_SECRET non configuré — signature ignorée (dev uniquement)")
        return

    if not x_vapi_signature:
        logger.error("❌ Requête sans en-tête x-vapi-signature — refusée")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Signature Vapi manquante",
        )

    raw_body = await request.body()
    if not verify_vapi_signature(
        payload=raw_body,
        signature=x_vapi_signature,
        secret=secret,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Signature Vapi invalide",
        )
