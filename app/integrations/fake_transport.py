"""
Mode simulé des fournisseurs externes (PROVIDER_MODE=fake).

Objectif : dérouler et valider tout le produit — prise de RDV, confirmations,
onboarding multi-tenant — SANS compte payant (numéro Twilio FR, plan Cal.com
plateforme) et sans consommer de crédits.

Principe : on simule au niveau du **transport HTTP**, pas au niveau métier.
Le vrai code continue de tourner (normalisation des numéros, construction des
corps de message, parsing et formatage des créneaux, gestion d'erreurs) ; seul
l'aller-retour réseau est feint. Un mock posé plus haut, sur les méthodes
métier, ne testerait plus que le mock.

Bascule vers le réel le mois prochain : PROVIDER_MODE=real dans .env. Aucun
autre changement de code.
"""
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

logger = logging.getLogger(__name__)

PARIS_TZ = ZoneInfo("Europe/Paris")

# Journal en mémoire de tout ce qui aurait été envoyé — le harnais de test s'en sert
# pour vérifier « un SMS est bien parti » sans qu'aucun SMS ne parte.
SENT_LOG: list[dict] = []

# Simule un garage en congés : aucun créneau Cal.com n'est renvoyé avant cette
# date (le garagiste aurait bloqué cette période dans son agenda). None = ouvert.
CLOSURE_UNTIL: "datetime | None" = None

# Outils Vapi « déjà créés », indexés par nom — reproduit la persistance côté
# Vapi, pour que ensure_tools() les réutilise au lieu de les recréer.
_FAKE_TOOLS: dict[str, dict] = {}


def reset_log() -> None:
    SENT_LOG.clear()


def set_closure(until) -> None:
    """Ferme l'agenda simulé jusqu'à `until` (datetime aware) ou l'ouvre (None)."""
    global CLOSURE_UNTIL
    CLOSURE_UNTIL = until


def _record(kind: str, **details) -> None:
    # Le journal conserve le contenu INTÉGRAL : c'est lui que les tests
    # inspectent pour vérifier ce qui serait parti. Un journal tronqué masque
    # les défauts qu'il est censé révéler. Seul l'affichage console est abrégé.
    SENT_LOG.append({"kind": kind, "at": datetime.now(timezone.utc).isoformat(), **details})

    apercu = {k: (v[:80] + "…" if isinstance(v, str) and len(v) > 80 else v)
              for k, v in details.items()}
    logger.info(f"[SIMULÉ] {kind} · {apercu}")


# ─────────────────────────────────────────────────────────────────────────────
# Twilio — client factice imitant la surface utilisée par TwilioSMSClient
# ─────────────────────────────────────────────────────────────────────────────

class _FakeMessage:
    def __init__(self, to: str, body: str):
        self.sid    = f"SM{uuid.uuid4().hex[:30]}"
        self.status = "queued"
        self.to     = to
        self.body   = body


class _FakeMessages:
    def create(self, body: str, from_: str, to: str):
        msg = _FakeMessage(to, body)
        _record("sms", to=to, from_=from_, sid=msg.sid, body=body)
        return msg


class FakeTwilioClient:
    """Reproduit `Client(...).messages.create(...)` de twilio-python."""
    def __init__(self):
        self.messages = _FakeMessages()


# ─────────────────────────────────────────────────────────────────────────────
# Resend — module factice imitant `resend.Emails.send(params)`
# ─────────────────────────────────────────────────────────────────────────────

class _FakeEmails:
    @staticmethod
    def send(params: dict) -> dict:
        email_id = f"re_{uuid.uuid4().hex[:20]}"
        _record("email", to=params.get("to"), subject=params.get("subject"), id=email_id)
        return {"id": email_id}


class FakeResendModule:
    Emails = _FakeEmails
    api_key = "fake"


# ─────────────────────────────────────────────────────────────────────────────
# Cal.com — transport HTTP factice
# ─────────────────────────────────────────────────────────────────────────────

def _calcom_slots(request: httpx.Request) -> httpx.Response:
    """
    Créneaux ouvrables réalistes : 9h/11h/14h/16h, du lundi au samedi matin,
    à partir du lendemain. Respecte startTime/endTime demandés.
    """
    params   = dict(request.url.params)
    duration = int(params.get("duration", 60))

    try:
        start = datetime.fromisoformat(params["startTime"]).astimezone(PARIS_TZ)
        end   = datetime.fromisoformat(params["endTime"]).astimezone(PARIS_TZ)
    except (KeyError, ValueError):
        start = datetime.now(PARIS_TZ) + timedelta(hours=2)
        end   = start + timedelta(days=7)

    slots: dict[str, list] = {}
    day = (start + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    while day < end:
        if day.weekday() == 6:                      # dimanche fermé
            day += timedelta(days=1)
            continue
        # Congés : le garagiste a bloqué cette période dans son agenda, aucun
        # créneau ne remonte avant la réouverture.
        if CLOSURE_UNTIL is not None and day < CLOSURE_UNTIL:
            day += timedelta(days=1)
            continue
        hours = [9, 11] if day.weekday() == 5 else [9, 11, 14, 16]   # samedi matin
        for h in hours:
            slot = day.replace(hour=h)
            if slot <= start:
                continue
            slots.setdefault(slot.date().isoformat(), []).append({
                "time":     slot.isoformat(),
                "duration": duration,
            })
        day += timedelta(days=1)

    # Structure fidèle à l'API v2 : tout est sous `data`. Ne PAS dupliquer à la
    # racine « pour aider » — un faux plus permissif que le réel masque les bugs.
    return httpx.Response(200, json={"status": "success", "data": {"slots": slots}})


def _calcom_booking(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content or b"{}")
    uid  = f"fake_{uuid.uuid4().hex[:16]}"
    _record("calcom_booking", uid=uid, start=body.get("start"),
            attendee=(body.get("attendee") or {}).get("name"))
    return httpx.Response(200, json={
        "status": "success",
        "data": {
            "id":     abs(hash(uid)) % 10_000_000,
            "uid":    uid,
            "status": "accepted",
            "start":  body.get("start"),
        },
    })


def _calcom_handler(request: httpx.Request) -> httpx.Response:
    path   = request.url.path
    method = request.method

    if "slots" in path:
        return _calcom_slots(request)
    if "bookings" in path and method == "POST":
        if path.rstrip("/").endswith("cancel"):
            _record("calcom_cancel", path=path)
            return httpx.Response(200, json={"status": "success", "data": {"status": "cancelled"}})
        if "reschedule" in path:
            return _calcom_booking(request)
        return _calcom_booking(request)
    if "bookings" in path and method in ("PATCH", "DELETE"):
        _record("calcom_update", path=path, method=method)
        return httpx.Response(200, json={"status": "success", "data": {"status": "accepted"}})

    # Managed users : la partie réellement payante du plan Cal.com
    if "users" in path or "oauth-clients" in path:
        username = f"garage-simule-{uuid.uuid4().hex[:6]}"
        _record("calcom_managed_user", username=username)
        return httpx.Response(200, json={
            "status": "success",
            "data": {
                "user":       {"id": abs(hash(username)) % 100_000, "username": username},
                "eventTypes": [{"id": abs(hash(username)) % 90_000 + 10_000,
                                "slug": "rendez-vous-garage", "length": 60}],
            },
        })

    logger.warning(f"[SIMULÉ] Route Cal.com non couverte : {method} {path}")
    return httpx.Response(200, json={"status": "success", "data": {}})


# ─────────────────────────────────────────────────────────────────────────────
# Vapi — transport HTTP factice
# ─────────────────────────────────────────────────────────────────────────────

def _vapi_handler(request: httpx.Request) -> httpx.Response:
    path   = request.url.path
    method = request.method
    body   = json.loads(request.content) if request.content else {}

    # Outils : créés une fois puis référencés par id dans model.toolIds.
    # On mémorise les outils « déjà créés » pour que ensure_tools() les
    # réutilise, comme le ferait Vapi — sinon le test ne vérifierait pas la
    # réutilisation entre garages.
    if path.rstrip("/").endswith("/tool") or "/tool" == path:
        if method == "GET":
            return httpx.Response(200, json=list(_FAKE_TOOLS.values()))
        if method == "POST":
            nom = (body.get("function") or {}).get("name", "sans-nom")
            if nom not in _FAKE_TOOLS:
                _FAKE_TOOLS[nom] = {"id": f"tool_{uuid.uuid4().hex[:12]}", **body}
                _record("vapi_tool", name=nom, id=_FAKE_TOOLS[nom]["id"])
            return httpx.Response(201, json=_FAKE_TOOLS[nom])

    if "phone-number" in path and method == "POST":
        # C'est ici que part l'argent en réel : achat d'un numéro
        number = body.get("number") or f"+3375{uuid.uuid4().int % 10**7:07d}"
        pid    = str(uuid.uuid4())
        _record("vapi_phone_number", id=pid, number=number)
        return httpx.Response(201, json={"id": pid, "number": number, "provider": "twilio"})

    if "assistant" in path and method == "POST":
        aid = str(uuid.uuid4())
        _record("vapi_assistant", id=aid, name=body.get("name"),
                garage_id=(body.get("metadata") or {}).get("garage_id"))
        return httpx.Response(201, json={"id": aid, **body})

    if "assistant" in path and method in ("PATCH", "PUT"):
        return httpx.Response(200, json={"id": path.rstrip("/").split("/")[-1], **body})

    if "assistant" in path and method == "DELETE":
        return httpx.Response(200, json={"deleted": True})

    if method == "GET":
        return httpx.Response(200, json=[] if path.rstrip("/").endswith("s") else {})

    logger.warning(f"[SIMULÉ] Route Vapi non couverte : {method} {path}")
    return httpx.Response(200, json={})


# ─────────────────────────────────────────────────────────────────────────────
# Fabriques de transports
# ─────────────────────────────────────────────────────────────────────────────

def calcom_transport() -> httpx.MockTransport:
    return httpx.MockTransport(_calcom_handler)


def vapi_transport() -> httpx.MockTransport:
    return httpx.MockTransport(_vapi_handler)
