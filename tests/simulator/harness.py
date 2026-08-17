"""
Harnais de simulation d'appels — rejoue un appel complet contre le backend,
sans téléphone, sans Vapi, sans Twilio et sans consommer de crédits.

Pourquoi : jusqu'ici, vérifier un parcours coûtait un vrai appel. Résultat, des
pannes dures sont restées invisibles pendant des mois (résolveur de tenant cassé,
RDV jamais créés dans l'agenda). Ce harnais rend chaque scénario rejouable en
quelques secondes.

Ce qui est réel ici : le backend FastAPI complet (middlewares, signature HMAC,
handlers, logique métier) et la base Supabase.
Ce qui est simulé : uniquement le réseau vers Twilio, Cal.com, Vapi et Resend
(PROVIDER_MODE=fake).

Isolation : chaque simulation travaille sur un garage éphémère, supprimé à la fin.
Les clés étrangères sont en ON DELETE CASCADE : supprimer le garage nettoie ses
appels, RDV et notifications. Aucune donnée réelle n'est touchée.
"""
import hashlib
import hmac
import json
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

# Le mode simulé doit être actif AVANT le chargement de la configuration
# (settings est un singleton construit à l'import).
os.environ.setdefault("PROVIDER_MODE", "fake")

from tests.simulator import vapi_payloads as payloads   # noqa: E402


@dataclass
class ToolResult:
    """Résultat d'un appel d'outil, tel que l'agent le recevrait."""
    tool:        str
    status_code: int
    body:        dict[str, Any]

    @property
    def ok(self) -> bool:
        return self.status_code == 200 and bool(self.body.get("success", True))

    @property
    def message(self) -> str:
        return str(self.body.get("message", ""))


@dataclass
class SimulatedCall:
    """Un appel en cours de simulation."""
    vapi_call_id: str
    garage_id:    str
    caller_phone: str
    simulator:    "CallSimulator"
    steps:        list[ToolResult] = field(default_factory=list)

    # ── Étapes d'un appel ────────────────────────────────────────────────────

    def start(self) -> dict:
        resp = self.simulator._post(
            "/api/webhooks/vapi",
            payloads.call_started(self.vapi_call_id, self.garage_id, self.caller_phone),
        )
        return resp.json()

    def tool(self, name: str, **parameters) -> ToolResult:
        """Appelle un outil comme le ferait l'agent en cours de conversation."""
        resp = self.simulator._post(
            f"/api/tools/{name}",
            payloads.tool_call(
                self.vapi_call_id, self.garage_id, self.caller_phone, parameters,
            ),
        )
        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.text}

        result = ToolResult(tool=name, status_code=resp.status_code, body=body)
        self.steps.append(result)
        return result

    def end(self, reason: str = "customer-ended-call", duration: int = 90,
            summary: str = "") -> dict:
        resp = self.simulator._post(
            "/api/webhooks/vapi",
            payloads.call_ended(
                self.vapi_call_id, self.garage_id, self.caller_phone,
                ended_reason=reason, duration=duration, summary=summary,
            ),
        )
        return resp.json()

    # ── Vérifications sur l'état réellement enregistré ───────────────────────

    def db_call(self) -> Optional[dict]:
        rows = (self.simulator.db.table("calls").select("*")
                .eq("vapi_call_id", self.vapi_call_id).limit(1).execute().data)
        return rows[0] if rows else None

    def db_appointments(self) -> list[dict]:
        return (self.simulator.db.table("appointments").select("*")
                .eq("garage_id", self.garage_id).execute().data or [])

    def db_notifications(self) -> list[dict]:
        return (self.simulator.db.table("notifications").select("*")
                .eq("garage_id", self.garage_id).execute().data or [])

    def sms_sent(self) -> list[dict]:
        from app.integrations import fake_transport
        return [e for e in fake_transport.SENT_LOG if e["kind"] == "sms"]

    def emails_sent(self) -> list[dict]:
        from app.integrations import fake_transport
        return [e for e in fake_transport.SENT_LOG if e["kind"] == "email"]


class CallSimulator:
    """
    Contexte de simulation : crée un garage jetable, expose le backend, nettoie.

    Usage :
        with CallSimulator() as sim:
            call = sim.new_call(caller="+33612345678")
            call.start()
            res = call.tool("check_availability", service_type="revision")
            call.end()
    """

    # Garage ouvert en permanence : par défaut, les scénarios ne doivent pas
    # dépendre de l'heure à laquelle la suite de tests tourne.
    HORAIRES_24_7 = {
        jour: {"open": "00:00", "close": "23:59", "closed": False}
        for jour in ("monday", "tuesday", "wednesday", "thursday",
                     "friday", "saturday", "sunday")
    }
    HORAIRES_FERME = {
        jour: {"open": None, "close": None, "closed": True}
        for jour in ("monday", "tuesday", "wednesday", "thursday",
                     "friday", "saturday", "sunday")
    }

    def __init__(self, garage_name: str = "SIM Garage", *,
                 calcom_ready: bool = True,
                 ouvert: bool = True,
                 avec_transfert: bool = True,
                 conges_jours: Optional[int] = None):
        self.garage_name    = garage_name
        self.calcom_ready   = calcom_ready
        self.ouvert         = ouvert
        self.avec_transfert = avec_transfert
        # Congés : l'agenda Cal.com simulé ne renvoie aucun créneau avant J+N.
        self.conges_jours   = conges_jours
        self.garage_id: Optional[str] = None
        self._client = None
        self.db      = None

    # ── Cycle de vie ─────────────────────────────────────────────────────────

    def __enter__(self) -> "CallSimulator":
        from fastapi.testclient import TestClient

        from app.config import settings
        from app.db.supabase_client import get_supabase_client
        from app.integrations import fake_transport
        from app.main import app

        if not settings.use_fake_providers:
            raise RuntimeError(
                "PROVIDER_MODE doit valoir 'fake' pour simuler un appel : "
                "sinon des SMS réels partiraient et des numéros seraient facturés."
            )

        self.db      = get_supabase_client()
        self._client = TestClient(app)
        self._secret = settings.VAPI_WEBHOOK_SECRET
        fake_transport.reset_log()

        # Le handler met en cache la configuration des garages (60 s). Sans purge,
        # un test qui modifie son garage lirait une valeur périmée — bug pénible
        # à diagnostiquer car dépendant de l'ordre des tests.
        from app.core.call_handler import call_handler
        call_handler.invalidate_garage_cache()

        # Congés éventuels : l'agenda ne renvoie rien avant la réouverture.
        if self.conges_jours is not None:
            from datetime import datetime, timedelta
            from zoneinfo import ZoneInfo
            reouverture = datetime.now(ZoneInfo("Europe/Paris")) \
                          + timedelta(days=self.conges_jours)
            fake_transport.set_closure(reouverture)
        else:
            fake_transport.set_closure(None)

        self.garage_id = self._create_garage()
        return self

    def __exit__(self, *exc) -> None:
        # Toujours rouvrir l'agenda simulé : sinon la fermeture fuiterait sur le
        # test suivant qui partage l'état global de fake_transport.
        from app.integrations import fake_transport
        fake_transport.set_closure(None)
        # ON DELETE CASCADE : supprime aussi appels, RDV et notifications du garage
        if self.garage_id:
            self.db.table("garages").delete().eq("id", self.garage_id).execute()
        if self._client:
            self._client.close()

    # ── Garage éphémère ──────────────────────────────────────────────────────

    def _create_garage(self) -> str:
        suffix = uuid.uuid4().hex[:8]
        row = {
            "name":         f"{self.garage_name} {suffix}",
            "slug":         f"sim-{suffix}",
            "garage_type":  "mecanique_generale",
            "status":       "trial",
            "phone_number": "+33500000000",
            "email":        f"sim-{suffix}@example.invalid",
            "twilio_phone_number":   f"+3375{uuid.uuid4().int % 10**7:07d}",
            "transfer_sms_number":   "+33600000001",
            "onboarding_status":     "completed",
            "business_hours":        self.HORAIRES_24_7 if self.ouvert
                                     else self.HORAIRES_FERME,
        }
        if self.avec_transfert:
            row["transfer_phone_number"] = "+33600000001"
        # Un garage « prêt » a un agenda rattaché ; sans lui, l'agent ne propose
        # que des créneaux de repli qui n'existent dans aucun agenda.
        if self.calcom_ready:
            row["calcom_event_type_id"] = 123456
            row["calcom_username"]      = f"sim-{suffix}"

        created = self.db.table("garages").insert(row).execute().data
        return created[0]["id"]

    # ── Appels ───────────────────────────────────────────────────────────────

    # ── Fabrication directe de RDV ───────────────────────────────────────────

    def creer_rdv(self, *, dans_heures: float = 24, client: str = "+33612345678",
                  nom: str = "Pierre Moreau", statut: str = "confirme",
                  titre: str = "Révision", duree: int = 90) -> dict:
        """
        Insère un RDV à une échéance précise, sans passer par l'agent.

        Nécessaire pour tester les rappels : les créneaux proposés par l'agent
        tombent au lendemain matin, alors qu'il faut ici viser « dans 24 h » ou
        « dans 2 h » à la minute près.
        """
        from datetime import datetime, timedelta, timezone

        prevu = datetime.now(timezone.utc) + timedelta(hours=dans_heures)
        ligne = {
            "garage_id":        self.garage_id,
            "scheduled_at":     prevu.isoformat(),
            "duration_minutes": duree,
            "title":            titre,
            "status":           statut,
            "client_name":      nom,
            "client_phone":     client,
        }
        return self.db.table("appointments").insert(ligne).execute().data[0]

    # ── État du garage simulé ────────────────────────────────────────────────

    def db_appointments(self) -> list[dict]:
        return (self.db.table("appointments").select("*")
                .eq("garage_id", self.garage_id).execute().data or [])

    def db_calls(self) -> list[dict]:
        return (self.db.table("calls").select("*")
                .eq("garage_id", self.garage_id).execute().data or [])

    # ── Appels ───────────────────────────────────────────────────────────────

    def new_call(self, caller: str = "+33612345678",
                 call_id: Optional[str] = None) -> SimulatedCall:
        return SimulatedCall(
            vapi_call_id=call_id or f"sim_{uuid.uuid4().hex[:16]}",
            garage_id=self.garage_id,
            caller_phone=caller,
            simulator=self,
        )

    # ── Transport HTTP signé ─────────────────────────────────────────────────

    def _post(self, path: str, payload: dict):
        """
        Poste vers le backend en signant comme Vapi le ferait : le harnais
        traverse donc réellement la vérification HMAC, au lieu de la contourner.
        """
        body    = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}

        if self._secret:
            headers["x-vapi-signature"] = hmac.new(
                key=self._secret.encode("utf-8"), msg=body, digestmod=hashlib.sha256,
            ).hexdigest()

        return self._client.post(path, content=body, headers=headers)
