"""
Rappels de rendez-vous — J-1 et H-2.

Les colonnes `reminder_24h_sent` et `reminder_2h_sent` existaient depuis la
création du schéma sans que rien ne les remplisse : aucun rappel n'a jamais été
envoyé. C'est pourtant le meilleur rapport effort/valeur du produit — le no-show
coûte cher à un garage (un créneau d'atelier perdu, non facturable) et le rappel
est l'argument commercial le plus concret à présenter.

Trois garde-fous, chacun pour une raison précise :

1. **Idempotence par réservation optimiste.** On marque le rappel comme envoyé
   AVANT de l'envoyer, avec une condition sur le drapeau encore à false. Si deux
   exécutions se chevauchent, une seule gagne la ligne. En cas d'échec d'envoi,
   le drapeau est remis à false pour retenter au passage suivant.
   Envoyer deux fois le même rappel décrédibilise l'agent auprès du client final.

2. **Heures décentes.** Aucun SMS entre 20h et 8h : réveiller un client à 3h du
   matin annule tout le bénéfice du rappel.

3. **Rien sur un RDV passé, annulé ou sans numéro exploitable.**
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from app.utils.phone import normalize_phone

logger = logging.getLogger(__name__)

PARIS_TZ = ZoneInfo("Europe/Paris")

# Plage pendant laquelle un SMS est acceptable (heure de Paris)
HEURE_MIN, HEURE_MAX = 8, 20

# Statuts de RDV qui méritent un rappel
STATUTS_ACTIFS = ("confirme", "modifie")

JOURS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS_FR  = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
            "août", "septembre", "octobre", "novembre", "décembre"]


def _format_fr(dt: datetime) -> str:
    dt = dt.astimezone(PARIS_TZ)
    heure = f"{dt.hour}h{dt.minute:02d}" if dt.minute else f"{dt.hour}h"
    return f"{JOURS_FR[dt.weekday()]} {dt.day} {MOIS_FR[dt.month - 1]} à {heure}"


class ReminderService:
    """Envoie les rappels de RDV. Conçu pour être appelé par un ordonnanceur."""

    # (clé, colonne, heures avant le RDV, demi-fenêtre de recherche)
    ECHEANCES = (
        ("24h", "reminder_24h_sent", 24, 2),
        ("2h",  "reminder_2h_sent",   2, 1),
    )

    def __init__(self):
        self.db = None

    def _lazy_init(self):
        if self.db is None:
            from app.db.supabase_client import get_supabase_client
            self.db = get_supabase_client()

    # ── Point d'entrée ───────────────────────────────────────────────────────

    async def run(self, *, maintenant: Optional[datetime] = None,
                  ignorer_heures: bool = False) -> dict:
        """
        Envoie tous les rappels dus. Retourne un compte-rendu exploitable par
        l'ordonnanceur et par les logs.
        """
        self._lazy_init()
        maintenant = (maintenant or datetime.now(timezone.utc)).astimezone(timezone.utc)

        heure_locale = maintenant.astimezone(PARIS_TZ).hour
        if not ignorer_heures and not (HEURE_MIN <= heure_locale < HEURE_MAX):
            logger.info(
                f"⏸️ Rappels différés : il est {heure_locale}h à Paris "
                f"(envois autorisés de {HEURE_MIN}h à {HEURE_MAX}h)"
            )
            return {"envoyes": 0, "echecs": 0, "ignores": 0, "differe": True}

        bilan = {"envoyes": 0, "echecs": 0, "ignores": 0, "differe": False}

        for cle, colonne, heures, marge in self.ECHEANCES:
            resultat = await self._traiter_echeance(
                cle=cle, colonne=colonne, heures=heures,
                marge=marge, maintenant=maintenant,
            )
            for champ in ("envoyes", "echecs", "ignores"):
                bilan[champ] += resultat[champ]

        logger.info(
            f"🔔 Rappels : {bilan['envoyes']} envoyés · "
            f"{bilan['echecs']} échecs · {bilan['ignores']} ignorés"
        )
        return bilan

    # ── Traitement d'une échéance ────────────────────────────────────────────

    async def _traiter_echeance(self, *, cle: str, colonne: str, heures: int,
                                marge: int, maintenant: datetime) -> dict:
        debut = maintenant + timedelta(hours=heures - marge)
        fin   = maintenant + timedelta(hours=heures + marge)

        # La fenêtre est volontairement large : si une exécution est manquée, la
        # suivante rattrape. C'est le drapeau, pas la fenêtre, qui évite le doublon.
        candidats = (
            self.db.table("appointments")
            .select("id, garage_id, call_id, client_name, client_phone, "
                    "scheduled_at, title, status")
            .in_("status", list(STATUTS_ACTIFS))
            .eq(colonne, False)
            .gte("scheduled_at", debut.isoformat())
            .lte("scheduled_at", fin.isoformat())
            .limit(200)
            .execute()
        ).data or []

        bilan = {"envoyes": 0, "echecs": 0, "ignores": 0}

        for rdv in candidats:
            issue = await self._rappeler(rdv, cle=cle, colonne=colonne,
                                         maintenant=maintenant)
            bilan[issue] += 1

        return bilan

    async def _rappeler(self, rdv: dict, *, cle: str, colonne: str,
                        maintenant: datetime) -> str:
        """Traite un RDV. Retourne 'envoyes', 'echecs' ou 'ignores'."""
        from app.services.notification_service import notification_service

        telephone = normalize_phone(rdv.get("client_phone"))
        if not telephone:
            logger.warning(
                f"⚠️ Rappel {cle} impossible pour le RDV {rdv['id']} : "
                f"numéro inexploitable ({rdv.get('client_phone')!r})"
            )
            # Marqué pour ne pas réessayer indéfiniment à chaque passage
            self._marquer(rdv["id"], colonne, True)
            return "ignores"

        try:
            prevu = datetime.fromisoformat(str(rdv["scheduled_at"]).replace("Z", "+00:00"))
        except ValueError:
            logger.error(f"❌ scheduled_at illisible sur le RDV {rdv['id']}")
            return "ignores"

        if prevu <= maintenant:
            self._marquer(rdv["id"], colonne, True)
            return "ignores"

        # Réservation optimiste : seule l'exécution qui obtient la ligne envoie.
        if not self._reserver(rdv["id"], colonne):
            logger.info(f"↩️ Rappel {cle} déjà pris en charge pour {rdv['id']}")
            return "ignores"

        garage = self._garage(rdv["garage_id"])
        corps  = self._message(cle, rdv, prevu, garage)

        resultat = await notification_service.send_sms(
            to=telephone,
            body=corps,
            garage_id=rdv["garage_id"],
            recipient_type="client",
            call_id=rdv.get("call_id"),
            appointment_id=rdv["id"],
        )

        if resultat.ok:
            logger.info(f"✅ Rappel {cle} envoyé | RDV {rdv['id']} | {telephone}")
            return "envoyes"

        # L'envoi a échoué : on relâche la réservation pour retenter plus tard.
        self._marquer(rdv["id"], colonne, False)
        logger.error(
            f"❌ Rappel {cle} en échec pour le RDV {rdv['id']} "
            f"({resultat.error}) — sera retenté"
        )
        return "echecs"

    # ── Accès base ───────────────────────────────────────────────────────────

    def _reserver(self, appointment_id: str, colonne: str) -> bool:
        """
        Pose le drapeau à true seulement s'il est encore à false.
        Retourne True si cette exécution a bien obtenu la ligne.
        """
        try:
            maj = (
                self.db.table("appointments")
                .update({colonne: True})
                .eq("id", appointment_id)
                .eq(colonne, False)
                .execute()
            )
            return bool(maj.data)
        except Exception as e:
            logger.error(f"❌ Réservation du rappel impossible ({appointment_id}) : {e}")
            return False

    def _marquer(self, appointment_id: str, colonne: str, valeur: bool) -> None:
        try:
            self.db.table("appointments").update({colonne: valeur}) \
                .eq("id", appointment_id).execute()
        except Exception as e:
            logger.error(f"❌ Mise à jour du drapeau {colonne} impossible : {e}")

    def _garage(self, garage_id: str) -> dict:
        try:
            res = (
                self.db.table("garages")
                .select("name, phone_number")
                .eq("id", str(garage_id))
                .single()
                .execute()
            )
            return res.data or {}
        except Exception:
            return {}

    # ── Rédaction ────────────────────────────────────────────────────────────

    def _message(self, cle: str, rdv: dict, prevu: datetime, garage: dict) -> str:
        nom      = garage.get("name", "votre garage")
        tel      = garage.get("phone_number", "")
        prenom   = (rdv.get("client_name") or "").split(" ")[0]
        salutation = f"Bonjour {prenom}, " if prenom else "Bonjour, "

        if cle == "2h":
            corps = (
                f"{salutation}rappel : votre rendez-vous chez {nom} "
                f"est dans 2 heures, à {prevu.astimezone(PARIS_TZ).hour}h"
                f"{prevu.astimezone(PARIS_TZ).minute:02d}."
            )
        else:
            corps = (
                f"{salutation}rappel de votre rendez-vous chez {nom} "
                f"demain, {_format_fr(prevu)}."
            )

        if rdv.get("title"):
            corps += f"\nPrestation : {rdv['title']}"
        # Toujours donner une porte de sortie : un client qui peut annuler
        # facilement libère le créneau au lieu de ne pas venir.
        if tel:
            corps += f"\nPour modifier ou annuler : {tel}"

        return corps


# Instance globale
reminder_service = ReminderService()
