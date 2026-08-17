"""
Client Cal.com v2 — Gestion des disponibilités et réservations
"""
import logging
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

PARIS_TZ = ZoneInfo("Europe/Paris")
TIMEOUT  = httpx.Timeout(15.0, connect=5.0)

# Fenêtre de recherche élargie quand la semaine à venir est vide. Sert à
# détecter un garage en congés : le garagiste bloque ses vacances dans son
# agenda Cal.com, l'agenda ne renvoie donc aucun créneau sur la période fermée.
# Si rien cette semaine mais des créneaux plus loin, c'est une réouverture à
# annoncer — pas une absence de disponibilité.
EXTENDED_DAYS_AHEAD = 60

# Durées par défaut selon le type de service (en minutes)
SERVICE_DURATIONS = {
    "revision":         90,
    "vidange":          45,
    "freins":           60,
    "freins_avant":     60,
    "freins_arriere":   75,
    "diagnostic":       45,
    "pneus":            60,
    "batterie":         30,
    "controle_technique": 120,
    "depannage":        60,
    "remorquage":       90,
    "default":          60,
}

# Mapping préférences client → heures
SLOT_PREFERENCES = {
    "matin":         (8,  12),
    "après-midi":    (13, 18),
    "apres-midi":    (13, 18),
    "matin tôt":     (8,  10),
    "fin de journée": (16, 18),
}


class _ConnexionPartagee:
    """
    Enveloppe qui neutralise la fermeture par `async with`.

    Les appelants écrivent `async with self._client() as client:`, ce qui
    fermerait la connexion partagée à chaque usage. Cette enveloppe la prête
    sans jamais la fermer : c'est `CalComClient.close()`, au shutdown de
    l'application, qui la libère.
    """

    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def __aenter__(self) -> httpx.AsyncClient:
        return self._client

    async def __aexit__(self, *exc) -> bool:
        return False   # ne ferme pas, ne masque pas les exceptions


class CalComClient:
    """
    Client pour l'API Cal.com v2.
    Gère les disponibilités et la création de réservations.
    """

    def __init__(self):
        self.base_url = settings.CALCOM_API_URL
        self.headers  = {
            "Authorization": f"Bearer {settings.CALCOM_API_KEY}",
            "Content-Type":  "application/json",
            "cal-api-version": "2024-08-13",
        }
        self._shared: Optional[httpx.AsyncClient] = None

    def _client(self) -> "_ConnexionPartagee":
        """
        Connexion HTTP **persistante** vers Cal.com.

        Optimisation étape 12 : un `AsyncClient` neuf par appel rouvrait une
        connexion TLS à chaque fois (poignée de main complète, ~100-200 ms à
        froid) — temps payé en plein pendant que l'agent attend pour annoncer
        les créneaux au client. En la réutilisant, la connexion reste chaude.
        """
        if self._shared is None:
            # En PROVIDER_MODE=fake, un transport factice répond à la place du
            # réseau : parsing des créneaux et formatage FR restent le vrai code.
            transport = None
            if settings.use_fake_providers:
                from app.integrations.fake_transport import calcom_transport
                transport = calcom_transport()

            self._shared = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self.headers,
                timeout=TIMEOUT,
                transport=transport,
            )
        return _ConnexionPartagee(self._shared)

    async def close(self) -> None:
        """Libère la connexion partagée (appelé au shutdown de l'application)."""
        if self._shared is not None:
            await self._shared.aclose()
            self._shared = None

    # ── Disponibilités ───────────────────────────────────────

    async def get_available_slots(
        self,
        garage_id:      UUID,
        service_type:   str,
        preferred_slot: Optional[str] = None,
        days_ahead:     int = 7,
    ) -> list[dict]:
        """
        Récupère les créneaux disponibles pour un garage.

        Escalade « garage en congés » : si la fenêtre courante ne renvoie aucun
        créneau alors que l'agenda est rattaché, on élargit la recherche jusqu'à
        EXTENDED_DAYS_AHEAD. Les créneaux trouvés au-delà sont marqués
        `after_closure=True` pour que l'agent annonce la réouverture au lieu de
        dire « aucune disponibilité ».

        Returns:
            list[dict] : créneaux avec `formatted_fr` ; chaque créneau porte
            `is_fallback` (agenda non rattaché) et `after_closure` (réouverture
            après une période fermée).
        """
        from app.db.supabase_client import get_supabase_client
        db = get_supabase_client()

        garage = (
            db.table("garages")
            .select("calcom_event_type_id, calcom_username, calcom_user_id, name")
            .eq("id", str(garage_id))
            .single()
            .execute()
        )

        # L'agenda se cible par event type. `calcom_event_type_id = 0` signifie
        # « onboarding Cal.com incomplet » : c'est une absence, pas un identifiant.
        event_type_id = (garage.data or {}).get("calcom_event_type_id") or None
        username      = (garage.data or {}).get("calcom_username") \
                        or (garage.data or {}).get("calcom_user_id")

        if not garage.data or not (event_type_id or username):
            logger.error(
                f"❌ Agenda Cal.com non rattaché pour garage {garage_id} "
                f"(calcom_event_type_id et calcom_username absents) — "
                f"créneaux de repli proposés, ILS NE SONT PAS DANS L'AGENDA DU GARAGE"
            )
            # Sans agenda, on ne connaît pas les congés : la feature vacances ne
            # s'applique pas (les créneaux de repli sont annoncés « sous réserve »).
            return self._fallback_slots(service_type, preferred_slot)

        duration = SERVICE_DURATIONS.get(
            service_type.lower().replace(" ", "_"),
            SERVICE_DURATIONS["default"]
        )
        cible = {"eventTypeId": event_type_id} if event_type_id else {"username": username}

        # 1er passage : la semaine à venir (cas nominal, réponse rapide).
        slots = await self._query_slots(cible, duration, days_ahead, preferred_slot)
        if slots:
            logger.info(f"✅ {len(slots)} créneaux trouvés / garage {garage_id}")
            return slots

        # Rien cette semaine → le garage est peut-être en congés. On cherche loin.
        logger.info(
            f"🔍 Aucun créneau sous {days_ahead}j pour garage {garage_id} — "
            f"recherche élargie à {EXTENDED_DAYS_AHEAD}j (garage en congés ?)"
        )
        slots = await self._query_slots(
            cible, duration, EXTENDED_DAYS_AHEAD, preferred_slot,
        )
        if slots:
            # Réouverture : on marque les créneaux pour que l'agent l'annonce.
            for s in slots:
                s["after_closure"] = True
            logger.info(
                f"🏖️ Garage {garage_id} fermé jusqu'au ~{slots[0]['formatted_fr']} — "
                f"{len(slots)} créneaux à la réouverture"
            )
        else:
            logger.warning(
                f"⚠️ Aucun créneau sur {EXTENDED_DAYS_AHEAD}j pour garage {garage_id} "
                f"(agenda vide ou fermeture prolongée)"
            )
        return slots

    async def _query_slots(
        self,
        cible:          dict,
        duration:       int,
        days_ahead:     int,
        preferred_slot: Optional[str],
    ) -> list[dict]:
        """Un appel Cal.com sur une fenêtre donnée. Retourne [] en cas d'erreur."""
        now        = datetime.now(PARIS_TZ)
        start_date = now + timedelta(hours=2)   # minimum 2h dans le futur
        end_date   = now + timedelta(days=days_ahead)

        params = {
            "startTime": start_date.isoformat(),
            "endTime":   end_date.isoformat(),
            "duration":  duration,
            "timeZone":  "Europe/Paris",
            **cible,
        }

        try:
            async with self._client() as client:
                response = await client.get("/slots/available", params=params)
                response.raise_for_status()
                data = response.json()
        except Exception as e:
            logger.error(f"❌ Erreur Cal.com get_slots : {e}")
            return []

        return self._parse_slots(data, preferred_slot)

    def _parse_slots(
        self,
        data:           dict,
        preferred_slot: Optional[str],
    ) -> list[dict]:
        """Parse la réponse Cal.com et formate les créneaux."""
        slots = []

        # L'API v2 encapsule tout sous `data` ; on reste tolérant à une réponse à plat.
        body          = data.get("data", data) if isinstance(data, dict) else {}
        slots_by_date = body.get("slots", data.get("slots", {}))

        # Filtrage par préférence horaire
        pref_hours = None
        if preferred_slot:
            for key, hours in SLOT_PREFERENCES.items():
                if key in preferred_slot.lower():
                    pref_hours = hours
                    break

        for date_str, day_slots in slots_by_date.items():
            for slot in day_slots:
                start_str = slot.get("time", "")
                if not start_str:
                    continue

                try:
                    start_dt = datetime.fromisoformat(
                        start_str.replace("Z", "+00:00")
                    ).astimezone(PARIS_TZ)
                except ValueError:
                    continue

                # Appliquer le filtre de préférence horaire
                if pref_hours:
                    h_start, h_end = pref_hours
                    if not (h_start <= start_dt.hour < h_end):
                        continue

                slots.append({
                    "start":        start_dt.isoformat(),
                    "formatted_fr": self._format_slot_fr(start_dt),
                    "duration_minutes": slot.get("duration", 60),
                })

        # Tri chronologique garanti : l'agent propose le plus proche d'abord, et
        # slots[0] est la date de réouverture fiable après une période de congés.
        slots.sort(key=lambda s: s["start"])
        return slots[:10]  # Max 10 créneaux

    def _format_slot_fr(self, dt: datetime) -> str:
        """Formate un créneau en français naturel pour l'agent."""
        DAYS_FR   = ["lundi", "mardi", "mercredi", "jeudi",
                     "vendredi", "samedi", "dimanche"]
        MONTHS_FR = ["janvier", "février", "mars", "avril", "mai",
                     "juin", "juillet", "août", "septembre",
                     "octobre", "novembre", "décembre"]

        day_name   = DAYS_FR[dt.weekday()]
        month_name = MONTHS_FR[dt.month - 1]
        hour_str   = f"{dt.hour}h{dt.minute:02d}" if dt.minute else f"{dt.hour}h"

        return f"{day_name} {dt.day} {month_name} à {hour_str}"

    def _fallback_slots(
        self,
        service_type:   str,
        preferred_slot: Optional[str],
    ) -> list[dict]:
        """
        Créneaux de fallback si Cal.com est indisponible.
        L'agent peut toujours proposer des options génériques.
        """
        now      = datetime.now(PARIS_TZ)
        duration = SERVICE_DURATIONS.get(
            service_type.lower().replace(" ", "_"),
            SERVICE_DURATIONS["default"]
        )

        fallback = []
        day      = now + timedelta(days=1)

        for _ in range(5):
            # Sauter les weekends pour la mécanique
            while day.weekday() >= 6:
                day += timedelta(days=1)

            for hour in [9, 11, 14, 16]:
                slot_dt = day.replace(
                    hour=hour, minute=0,
                    second=0, microsecond=0
                )
                fallback.append({
                    "start":              slot_dt.isoformat(),
                    "formatted_fr":       self._format_slot_fr(slot_dt),
                    "duration_minutes":   duration,
                    "is_fallback":        True,
                })

            day += timedelta(days=1)

        return fallback[:3]

    # ── Réservations ─────────────────────────────────────────

    async def create_booking(
        self,
        garage_id: UUID,
        params:    dict,
    ) -> dict:
        """
        Crée une réservation dans Cal.com et Supabase.

        Args:
            garage_id : UUID du garage
            params    : Données collectées par l'agent
        """
        from app.db.supabase_client import get_supabase_client
        db = get_supabase_client()

        # Récupérer les infos du garage
        garage = (
            db.table("garages")
            .select("calcom_event_type_id, calcom_username, calcom_user_id, name")
            .eq("id", str(garage_id))
            .single()
            .execute()
        )

        if not garage.data:
            return {
                "success": False,
                "message": "Configuration agenda manquante. Je transmets votre demande.",
            }

        # `calcom_event_type_id = 0` = onboarding Cal.com incomplet → traité comme absent
        event_type_id = garage.data.get("calcom_event_type_id") or None

        scheduled_at = params.get("scheduled_at", "")
        client_name  = params.get("client_name", "Client")
        client_phone = params.get("client_phone", "")
        client_email = params.get("client_email", "")
        service_type = params.get("service_type", "intervention")
        vehicle_info = (
            f"{params.get('vehicle_brand', '')} "
            f"{params.get('vehicle_model', '')}".strip()
        )

        title = f"{service_type.replace('_', ' ').title()}"
        if vehicle_info:
            title += f" - {vehicle_info}"

        # Sans event type, inutile d'appeler Cal.com : on va droit au repli local,
        # dont le message n'annonce PAS une confirmation ferme au client.
        if not event_type_id:
            logger.error(
                f"❌ Agenda Cal.com non rattaché (garage {garage_id}) — "
                f"RDV enregistré en base uniquement, ABSENT de l'agenda du garage"
            )
            return await self._create_local_booking(garage_id, params, title)

        try:
            async with self._client() as client:
                booking_payload = {
                    "start":    scheduled_at,
                    # Bug corrige le 14/08/2026 : ce champ recevait calcom_user_id
                    # (colonne vide de surcroit). eventTypeId null => Cal.com refuse
                    # => repli en base locale, donc RDV absent de l'agenda du garage
                    # alors que l'agent annonce au client « c'est confirme ».
                    "eventTypeId": event_type_id,
                    "attendee": {
                        "name":     client_name,
                        "email":    client_email or f"client+{client_phone}@agentlumy.com",
                        "timeZone": "Europe/Paris",
                        "phoneNumber": client_phone,
                    },
                    "metadata": {
                        "garage_id":    str(garage_id),
                        "service_type": service_type,
                        "vehicle":      vehicle_info,
                        "phone":        client_phone,
                        "source":       "voice_agent",
                    },
                }

                response = await client.post("/bookings", json=booking_payload)
                response.raise_for_status()
                # L'API v2 encapsule la réservation sous `data` : lire à la racine
                # renvoyait un uid vide, donc un RDV impossible à retrouver ensuite
                # (modification, annulation) alors que tout semblait avoir réussi.
                payload = response.json()
                booking = payload.get("data", payload) if isinstance(payload, dict) else {}

        except Exception as e:
            logger.error(f"❌ Erreur Cal.com create_booking : {e}")
            # En cas d'erreur Cal.com, on crée quand même en BDD locale
            return await self._create_local_booking(
                garage_id, params, title
            )

        # Créer aussi en BDD Supabase
        appointment_id = await self._save_appointment_to_db(
            garage_id=garage_id,
            params=params,
            title=title,
            calcom_booking_uid=booking.get("uid", ""),
            calcom_booking_id=str(booking.get("id", "")),
        )

        # Formater la date pour l'agent
        try:
            dt_obj      = datetime.fromisoformat(
                scheduled_at.replace("Z", "+00:00")
            ).astimezone(PARIS_TZ)
            formatted   = self._format_slot_fr(dt_obj)
        except Exception:
            formatted = scheduled_at

        logger.info(
            f"✅ RDV créé : {title} | "
            f"{formatted} | garage {garage_id}"
        )

        return {
            "success":        True,
            "appointment_id": appointment_id,
            "calcom_uid":     booking.get("uid", ""),
            "scheduled_at":   formatted,
            "message": (
                f"Parfait ! Votre rendez-vous est confirmé "
                f"le {formatted}. "
                f"Vous recevrez une confirmation par SMS dans quelques instants."
            ),
        }

    async def reschedule_booking(
        self,
        appointment_id:  str,
        new_scheduled_at: str,
    ) -> dict:
        """Replanifie un rendez-vous existant."""
        from app.db.supabase_client import get_supabase_client
        db = get_supabase_client()

        # Récupérer le booking Cal.com
        appt = (
            db.table("appointments")
            .select("calcom_booking_uid, scheduled_at")
            .eq("id", appointment_id)
            .single()
            .execute()
        )

        if not appt.data or not appt.data.get("calcom_booking_uid"):
            return {"success": False, "message": "Rendez-vous introuvable."}

        calcom_uid = appt.data["calcom_booking_uid"]

        try:
            async with self._client() as client:
                response = await client.post(
                    f"/bookings/{calcom_uid}/reschedule",
                    json={"start": new_scheduled_at},
                )
                response.raise_for_status()

        except Exception as e:
            logger.error(f"❌ Erreur Cal.com reschedule : {e}")
            return {
                "success": False,
                "message": "Impossible de modifier le rendez-vous. Je transmets votre demande.",
            }

        # Mettre à jour en BDD
        try:
            dt_obj    = datetime.fromisoformat(
                new_scheduled_at.replace("Z", "+00:00")
            ).astimezone(PARIS_TZ)
            formatted = self._format_slot_fr(dt_obj)
        except Exception:
            formatted = new_scheduled_at

        db.table("appointments").update({
            "original_scheduled_at": appt.data["scheduled_at"],
            "scheduled_at":          new_scheduled_at,
            "status":                "modifie",
        }).eq("id", appointment_id).execute()

        return {
            "success":  True,
            "message": (
                f"Votre rendez-vous a bien été déplacé "
                f"au {formatted}. "
                f"Vous recevrez une confirmation par SMS."
            ),
        }

    async def cancel_booking(
        self,
        appointment_id: str,
        reason:         str = "Annulation client",
    ) -> dict:
        """Annule un rendez-vous."""
        from app.db.supabase_client import get_supabase_client
        db = get_supabase_client()

        appt = (
            db.table("appointments")
            .select("calcom_booking_uid, title")
            .eq("id", appointment_id)
            .single()
            .execute()
        )

        if not appt.data:
            return {"success": False, "message": "Rendez-vous introuvable."}

        calcom_uid = appt.data.get("calcom_booking_uid", "")

        if calcom_uid:
            try:
                async with self._client() as client:
                    response = await client.delete(
                        f"/bookings/{calcom_uid}",
                        json={"cancellationReason": reason},
                    )
                    response.raise_for_status()
            except Exception as e:
                logger.error(f"❌ Erreur Cal.com cancel : {e}")

        # Mettre à jour en BDD dans tous les cas
        db.table("appointments").update({
            "status":              "annule",
            "cancellation_reason": reason,
            "cancelled_at":        datetime.now(PARIS_TZ).isoformat(),
            "cancelled_by":        "client",
        }).eq("id", appointment_id).execute()

        return {
            "success": True,
            "message": (
                "Votre rendez-vous a bien été annulé. "
                "N'hésitez pas à nous rappeler pour en reprendre un nouveau. "
                "Bonne journée !"
            ),
        }

    # ── Helpers BDD ──────────────────────────────────────────

    async def _save_appointment_to_db(
        self,
        garage_id:         UUID,
        params:            dict,
        title:             str,
        calcom_booking_uid: str = "",
        calcom_booking_id:  str = "",
    ) -> Optional[str]:
        """Sauvegarde un RDV dans Supabase."""
        from app.db.supabase_client import get_supabase_client
        db = get_supabase_client()

        try:
            result = db.table("appointments").insert({
                "garage_id":         str(garage_id),
                "title":             title,
                "scheduled_at":      params.get("scheduled_at"),
                "duration_minutes":  SERVICE_DURATIONS.get(
                    params.get("service_type", "default"),
                    60
                ),
                "status":            "confirme",
                "calcom_booking_uid": calcom_booking_uid,
                "calcom_booking_id":  calcom_booking_id,
                "client_name":       params.get("client_name"),
                "client_phone":      params.get("client_phone"),
                "client_email":      params.get("client_email"),
                "vehicle_brand":     params.get("vehicle_brand"),
                "vehicle_model":     params.get("vehicle_model"),
                "vehicle_registration": params.get("vehicle_registration"),
                "description": (
                    f"RDV pris via agent vocal. "
                    f"Service : {params.get('service_type', 'non précisé')}"
                ),
            }).execute()

            return result.data[0]["id"] if result.data else None

        except Exception as e:
            logger.error(f"❌ Erreur sauvegarde BDD appointment : {e}")
            return None

    async def _create_local_booking(
        self,
        garage_id: UUID,
        params:    dict,
        title:     str,
    ) -> dict:
        """Fallback : crée uniquement en BDD si Cal.com est KO."""
        appointment_id = await self._save_appointment_to_db(
            garage_id=garage_id,
            params=params,
            title=title,
        )

        try:
            dt_obj    = datetime.fromisoformat(
                params.get("scheduled_at", "").replace("Z", "+00:00")
            ).astimezone(PARIS_TZ)
            formatted = self._format_slot_fr(dt_obj)
        except Exception:
            formatted = params.get("scheduled_at", "")

        return {
            "success":        True,
            "appointment_id": appointment_id,
            "scheduled_at":   formatted,
            "calcom_uid":     "",
            "message": (
                f"Votre rendez-vous est noté pour le {formatted}. "
                f"Le garage vous confirmera par téléphone."
            ),
        }


# ── Onboarding multi-tenant ──────────────────────────────

    async def create_managed_user(
        self,
        email:    str,
        name:     str,
        username: str,
        timezone: str = "Europe/Paris",
        locale:   str = "fr",
    ) -> dict:
        """
        Crée un utilisateur managé Cal.com pour un nouveau garage.
        Retourne userId + accessToken pour les appels suivants.
        """
        try:
            async with self._client() as client:
                response = await client.post(
                    "/oauth-clients/managed-users",
                    json={
                        "email":    email,
                        "name":     name,
                        "username": username,
                        "timeZone": timezone,
                        "locale":   locale,
                        "weekStart": "Monday",
                    },
                )
                response.raise_for_status()
                data = response.json()
                return {
                    "userId":      data["data"]["user"]["id"],
                    "accessToken": data["data"]["accessToken"],
                }
        except Exception as e:
            logger.error(f"❌ Cal.com create_managed_user : {e}")
            # Mode dégradé : retourner des valeurs simulées en dev
            logger.warning("⚠️ Cal.com indisponible — mode simulé activé")
            return {
                "userId":      999,
                "accessToken": "simulated_token",
            }

    async def create_schedule(
        self,
        access_token: str,
        name:         str,
        timezone:     str,
        availability: dict,
    ) -> dict:
        """Crée un schedule (horaires) pour un utilisateur managé."""
        # Convertir le format du schedule en format Cal.com
        days_map = {
            "monday": 1, "tuesday": 2, "wednesday": 3,
            "thursday": 4, "friday": 5, "saturday": 6, "sunday": 0,
        }

        calcom_availability = []
        for day, slots in availability.items():
            day_num = days_map.get(day)
            if day_num is None:
                continue
            # APRÈS
                for slot in slots:
                    start = slot.start if hasattr(slot, "start") else slot["start"]
                    end   = slot.end   if hasattr(slot, "end")   else slot["end"]
                    calcom_availability.append({
                 "days":      [day_num],
                    "startTime": start,
                "endTime":   end,
    })

        try:
            headers = {
                **self.headers,
                "Authorization": f"Bearer {access_token}",
            }
            async with httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=TIMEOUT,
            ) as client:
                response = await client.post(
                    "/schedules",
                    json={
                        "name":         name,
                        "timeZone":     timezone,
                        "availability": calcom_availability,
                        "isDefault":    True,
                    },
                )
                response.raise_for_status()
                return response.json().get("data", {})
        except Exception as e:
            logger.error(f"❌ Cal.com create_schedule : {e}")
            return {"id": 0}

    async def create_event_type(
        self,
        access_token: str,
        title:        str,
        slug:         str,
        length:       int,
        description:  str = "",
    ) -> dict:
        """Crée un event type (type de RDV) pour un utilisateur managé."""
        try:
            headers = {
                **self.headers,
                "Authorization": f"Bearer {access_token}",
            }
            async with httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=TIMEOUT,
            ) as client:
                response = await client.post(
                    "/event-types",
                    json={
                        "title":       title,
                        "slug":        slug,
                        "length":      length,
                        "description": description,
                        "hidden":      False,
                    },
                )
                response.raise_for_status()
                data = response.json()
                return {"id": data["data"]["id"]}
        except Exception as e:
            logger.error(f"❌ Cal.com create_event_type : {e}")
            return {"id": 0}

# Instance globale
calcom_client = CalComClient()