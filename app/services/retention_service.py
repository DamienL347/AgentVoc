"""
RGPD — application des durées de conservation.

Le produit enregistre et transcrit des conversations téléphoniques : ce sont des
données personnelles. Sans purge, elles s'accumulent indéfiniment, ce qui
contrevient au principe de minimisation et fait grossir l'exposition en cas de
fuite (« on ne perd pas ce qu'on ne détient plus »).

**Choix de conception : on anonymise, on ne supprime pas.**
Les métadonnées non identifiantes — durée, statut, type de demande, urgence —
restent en base pour les statistiques du dashboard, tandis que tout ce qui
permet d'identifier une personne (numéro, transcription, enregistrement, nom,
email) disparaît. Supprimer les lignes ferait perdre l'historique des KPI sans
bénéfice supplémentaire côté conformité.

Paliers (configurables dans .env, voir app/config.py) :
    30 j   → enregistrements audio         (le plus sensible)
    90 j   → transcriptions
    365 j  → n° appelant, résumé d'appel
    365 j  → contenu des SMS/emails
    3 ans  → clients finaux sans contact

⚠️ Ce service applique une politique ; il ne la décide pas. Les durées doivent
être validées avec chaque garage, qui est le responsable de traitement.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

# Valeur de remplacement : `calls.caller_phone` est NOT NULL en base, on ne peut
# donc pas le vider — on le remplace par un marqueur non identifiant.
ANONYME = "ANONYMISE"


class RetentionService:
    """Applique les durées de conservation. Idempotent : rejouable sans risque."""

    def __init__(self):
        self.db = None

    def _lazy_init(self):
        if self.db is None:
            from app.db.supabase_client import get_supabase_client
            self.db = get_supabase_client()

    # ── Point d'entrée ───────────────────────────────────────────────────────

    async def run(self, *, dry_run: bool = False) -> dict:
        """
        Applique tous les paliers. `dry_run=True` compte sans rien modifier.

        Retourne un compte-rendu par palier : c'est la trace qui permettra de
        démontrer que la politique est réellement appliquée (obligation
        d'« accountability »).
        """
        self._lazy_init()
        maintenant = datetime.now(timezone.utc)

        bilan = {
            "enregistrements": self._purger_enregistrements(maintenant, dry_run),
            "transcriptions":  self._purger_transcriptions(maintenant, dry_run),
            "appels":          self._anonymiser_appels(maintenant, dry_run),
            "notifications":   self._purger_notifications(maintenant, dry_run),
            "clients":         self._purger_clients_inactifs(maintenant, dry_run),
            "dry_run":         dry_run,
        }

        total = sum(v for k, v in bilan.items() if isinstance(v, int))
        verbe = "à traiter" if dry_run else "traitées"
        logger.info(f"🔒 RGPD : {total} donnée(s) {verbe} · {bilan}")
        return bilan

    # ── Paliers ──────────────────────────────────────────────────────────────

    def _purger_enregistrements(self, maintenant: datetime, dry_run: bool) -> int:
        """Enregistrements audio : la donnée la plus sensible, purgée en premier."""
        limite = maintenant - timedelta(days=settings.RETENTION_RECORDINGS_DAYS)
        cibles = (
            self.db.table("calls")
            .select("id")
            .not_.is_("recording_url", "null")
            .lt("created_at", limite.isoformat())
            .execute()
        ).data or []

        if cibles and not dry_run:
            for lot in self._lots([c["id"] for c in cibles]):
                self.db.table("calls").update({
                    "recording_url": None,
                    "recording_duration_sec": None,
                }).in_("id", lot).execute()

        return len(cibles)

    def _purger_transcriptions(self, maintenant: datetime, dry_run: bool) -> int:
        """Transcriptions : le verbatim d'une conversation privée."""
        limite = maintenant - timedelta(days=settings.RETENTION_TRANSCRIPTS_DAYS)
        cibles = (
            self.db.table("calls")
            .select("id")
            .not_.is_("transcription", "null")
            .lt("created_at", limite.isoformat())
            .execute()
        ).data or []

        if cibles and not dry_run:
            for lot in self._lots([c["id"] for c in cibles]):
                self.db.table("calls").update({
                    "transcription": None,
                    "detected_keywords": None,
                }).in_("id", lot).execute()

        return len(cibles)

    def _anonymiser_appels(self, maintenant: datetime, dry_run: bool) -> int:
        """
        Dernier palier : le numéro de l'appelant et le résumé.

        On conserve la ligne : durée, statut et type de demande alimentent les
        statistiques, et ne permettent plus d'identifier qui que ce soit.
        """
        limite = maintenant - timedelta(days=settings.RETENTION_CALL_DETAILS_DAYS)
        cibles = (
            self.db.table("calls")
            .select("id")
            .neq("caller_phone", ANONYME)
            .lt("created_at", limite.isoformat())
            .execute()
        ).data or []

        if cibles and not dry_run:
            for lot in self._lots([c["id"] for c in cibles]):
                self.db.table("calls").update({
                    "caller_phone":   ANONYME,
                    "summary":        None,
                    "collected_data": {},
                    "end_client_id":  None,   # coupe le lien vers la personne
                }).in_("id", lot).execute()

        return len(cibles)

    def _purger_notifications(self, maintenant: datetime, dry_run: bool) -> int:
        """
        Contenu des SMS/emails. On garde canal, statut et horodatage : c'est ce
        qui sert de preuve d'envoi, sans conserver le message ni le destinataire.
        """
        limite = maintenant - timedelta(days=settings.RETENTION_NOTIFICATIONS_DAYS)
        cibles = (
            self.db.table("notifications")
            .select("id")
            .lt("created_at", limite.isoformat())
            .neq("body", ANONYME)
            .execute()
        ).data or []

        if cibles and not dry_run:
            for lot in self._lots([n["id"] for n in cibles]):
                self.db.table("notifications").update({
                    "body":            ANONYME,
                    "subject":         None,
                    "recipient_phone": None,
                    "recipient_email": None,
                }).in_("id", lot).execute()

        return len(cibles)

    def _purger_clients_inactifs(self, maintenant: datetime, dry_run: bool) -> int:
        """
        Clients finaux sans contact depuis 3 ans (durée usuelle en relation
        client). Supprimés, pas anonymisés : une fiche client anonyme n'a aucune
        utilité, et les appels/RDV gardent leurs propres métadonnées.
        """
        limite = maintenant - timedelta(days=settings.RETENTION_INACTIVE_CLIENTS_DAYS)

        cibles = (
            self.db.table("end_clients")
            .select("id, last_call_at, created_at")
            .lt("created_at", limite.isoformat())
            .execute()
        ).data or []

        # Un client sans appel récent : on se fie à last_call_at s'il existe,
        # sinon à la date de création.
        a_supprimer = []
        for client in cibles:
            dernier = client.get("last_call_at") or client.get("created_at")
            try:
                quand = datetime.fromisoformat(str(dernier).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
            if quand < limite:
                a_supprimer.append(client["id"])

        if a_supprimer and not dry_run:
            for lot in self._lots(a_supprimer):
                self.db.table("end_clients").delete().in_("id", lot).execute()

        return len(a_supprimer)

    # ── Droit à l'effacement (article 17) ────────────────────────────────────

    async def effacer_personne(
        self,
        telephone: str,
        *,
        garage_id: Optional[str] = None,
        tous_garages: bool = False,
        dry_run: bool = False,
    ) -> dict:
        """
        Efface les données d'une personne sur demande, quel que soit leur âge.

        Le RGPD donne un droit à l'effacement : il faut pouvoir y répondre sans
        attendre l'expiration des durées de conservation. Le numéro sert de clé,
        car c'est l'identifiant que la personne connaît d'elle-même.

        **Cloisonnement obligatoire.** Dans ce produit, le garage est responsable
        de traitement et AgentLumy sous-traitant : une demande arrive TOUJOURS
        par un garage, qui n'a aucun droit sur les données détenues par un autre.
        Le même numéro peut être client de deux garages concurrents.
        `garage_id` est donc requis, sauf `tous_garages=True` — réservé à une
        demande adressée à AgentLumy en tant que plateforme, et à tracer.
        """
        from app.utils.phone import normalize_phone

        self._lazy_init()
        numero = normalize_phone(telephone)
        if not numero:
            return {"erreur": f"Numéro invalide : {telephone!r}"}

        if not garage_id and not tous_garages:
            return {"erreur": (
                "garage_id requis : une demande d'effacement est portée par un "
                "garage, qui n'a pas de droit sur les données des autres. "
                "Utiliser tous_garages=True uniquement pour une demande "
                "adressée à la plateforme."
            )}

        bilan = {
            "telephone": numero,
            "garage_id": garage_id or "TOUS",
            "dry_run":   dry_run,
        }

        def cibler(table: str, colonne: str):
            """Applique le filtre numéro + le cloisonnement par garage."""
            requete = self.db.table(table).select("id").eq(colonne, numero)
            if garage_id:
                requete = requete.eq("garage_id", str(garage_id))
            return requete

        # Appels : anonymisés (on garde les métadonnées statistiques)
        appels = (cibler("calls", "caller_phone").execute()).data or []
        bilan["appels"] = len(appels)
        if appels and not dry_run:
            for lot in self._lots([a["id"] for a in appels]):
                self.db.table("calls").update({
                    "caller_phone": ANONYME, "transcription": None,
                    "summary": None, "recording_url": None,
                    "collected_data": {}, "end_client_id": None,
                }).in_("id", lot).execute()

        # Rendez-vous : anonymisés (le créneau reste pour l'historique du garage)
        rdvs = (cibler("appointments", "client_phone").execute()).data or []
        bilan["rendez_vous"] = len(rdvs)
        if rdvs and not dry_run:
            for lot in self._lots([r["id"] for r in rdvs]):
                self.db.table("appointments").update({
                    "client_name": ANONYME, "client_phone": None,
                    "client_email": None, "description": None,
                    "end_client_id": None,
                }).in_("id", lot).execute()

        # Notifications
        notifs = (cibler("notifications", "recipient_phone").execute()).data or []
        bilan["notifications"] = len(notifs)
        if notifs and not dry_run:
            for lot in self._lots([n["id"] for n in notifs]):
                self.db.table("notifications").update({
                    "body": ANONYME, "subject": None,
                    "recipient_phone": None, "recipient_email": None,
                }).in_("id", lot).execute()

        # Fiche client : supprimée
        clients = (cibler("end_clients", "phone_number").execute()).data or []
        bilan["fiches_client"] = len(clients)
        if clients and not dry_run:
            for lot in self._lots([c["id"] for c in clients]):
                self.db.table("end_clients").delete().in_("id", lot).execute()

        action = "seraient effacées" if dry_run else "effacées"
        # Tracé volontairement : l'article 12 impose de pouvoir justifier la
        # réponse apportée à une demande d'effacement.
        logger.info(
            f"🔒 Droit à l'effacement | {numero} | garage={bilan['garage_id']} | "
            f"données {action} — {bilan}"
        )
        return bilan

    # ── Utilitaire ───────────────────────────────────────────────────────────

    @staticmethod
    def _lots(ids: list[str], taille: int = 50):
        """
        Découpe en lots : une clause `IN` avec des milliers d'identifiants
        dépasse la longueur d'URL acceptée par PostgREST.
        """
        for i in range(0, len(ids), taille):
            yield ids[i:i + taille]


# Instance globale
retention_service = RetentionService()
