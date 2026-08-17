"""
Routes internes — déclenchées par un ordonnanceur, jamais par un client.

Sécurité : ces routes sont exposées publiquement (Cloud Scheduler appelle par
HTTP sans identifiants Google), donc protégées par un secret partagé transmis
en en-tête. Sans secret configuré, l'accès est refusé en production : une route
qui envoie des SMS en masse et que n'importe qui peut déclencher est une porte
ouverte à la facture et au harcèlement de tes clients.
"""
import hmac
import logging

from fastapi import APIRouter, Header, HTTPException, status

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])


def _verifier_secret(recu: str | None) -> None:
    attendu = settings.CRON_SECRET

    if not attendu:
        if settings.is_production:
            logger.error("❌ CRON_SECRET manquant en production — route interne refusée")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Configuration serveur incomplète",
            )
        logger.warning("⚠️ CRON_SECRET non configuré — contrôle ignoré (dev uniquement)")
        return

    # Comparaison en temps constant : une comparaison naïve laisse deviner le
    # secret caractère par caractère.
    if not recu or not hmac.compare_digest(recu, attendu):
        logger.error("❌ Appel de route interne avec un secret invalide")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Secret invalide",
        )


@router.post("/reminders/run")
async def run_reminders(
    x_cron_secret: str | None = Header(None, alias="x-cron-secret"),
    ignorer_heures: bool = False,
):
    """
    Envoie les rappels de RDV dus (J-1 et H-2).

    Appelé par Cloud Scheduler, idéalement toutes les heures : la fenêtre de
    recherche est large et le drapeau en base empêche tout doublon, donc une
    exécution manquée est rattrapée au passage suivant.

    `ignorer_heures=true` force l'envoi hors de la plage 8h-20h — réservé aux
    tests, à ne pas utiliser en production.
    """
    _verifier_secret(x_cron_secret)

    from app.services.reminder_service import reminder_service

    bilan = await reminder_service.run(ignorer_heures=ignorer_heures)
    return {"status": "ok", **bilan}
