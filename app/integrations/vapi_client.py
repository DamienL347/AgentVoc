"""
Client Vapi — Intégration complète de l'orchestration vocale
Gère : création d'assistants, configuration dynamique,
       appels sortants, et récupération des données d'appel
"""
import hashlib
import hmac
import logging
from typing import Optional

from uuid import UUID

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# ============================================================
# CONSTANTES
# ============================================================

VAPI_BASE_URL   = settings.VAPI_API_BASE_URL
DEFAULT_HEADERS = {
    "Authorization": f"Bearer {settings.VAPI_PRIVATE_KEY}",
    "Content-Type":  "application/json",
}

# Timeout httpx (en secondes)
TIMEOUT = httpx.Timeout(30.0, connect=10.0)


# ============================================================
# CLIENT VAPI
# ============================================================

class VapiClient:
    """
    Client HTTP pour l'API Vapi.
    Gère la création et la configuration des assistants vocaux.
    """

    def __init__(self):
        self.base_url = VAPI_BASE_URL
        self.headers  = DEFAULT_HEADERS

        # En PROVIDER_MODE=fake : ni assistant ni numéro réellement créés chez Vapi
        # (l'achat d'un numéro est l'appel qui coûte de l'argent).
        transport = None
        if settings.use_fake_providers:
            from app.integrations.fake_transport import vapi_transport
            logger.warning("⚠️ Vapi SIMULÉ (PROVIDER_MODE=fake) — aucun assistant ni numéro réel")
            transport = vapi_transport()

        self._client  = httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.headers,
            timeout=TIMEOUT,
            transport=transport,
        )

    async def close(self):
        """Ferme le client HTTP proprement."""
        await self._client.aclose()

    # ── Assistants ───────────────────────────────────────────

    async def create_assistant(
        self,
        garage_id:     UUID,
        garage_name:   str,
        system_prompt: str,
        first_message: str,
        voice_id:      Optional[str] = None,
    ) -> dict:
        """
        Crée un assistant Vapi pour un garage.
        À appeler lors de l'onboarding d'un nouveau client.

        Returns:
            dict : Données de l'assistant créé (contient l'ID)
        """
        payload = {
            "name": f"agent-{garage_name.lower().replace(' ', '-')}",

            # ── LLM : Claude Haiku ──────────────────────────
            "model": {
                "provider":    "anthropic",
                "model":       "claude-haiku-4-5-20251001",
                "temperature": 0.3,
                "maxTokens":   250,
                "messages": [
                    {
                        "role":    "system",
                        "content": system_prompt,
                    }
                ],
            },

            # ── Voix : Cartesia Sonic ───────────────────────
            "voice": {
                "provider": "cartesia",
                "voiceId":  voice_id or settings.CARTESIA_VOICE_ID_FR,
                "model":    settings.CARTESIA_MODEL,
                "language": "fr",
            },

            # ── Transcription : Deepgram Nova-2 ────────────
            "transcriber": {
                "provider": "deepgram",
                "model":    "nova-2",
                "language": "fr",
            },

            # ── Premier message ─────────────────────────────
            "firstMessage": first_message,

            # ── Paramètres de l'appel ───────────────────────
            "maxDurationSeconds":      settings.MAX_CALL_DURATION_SECONDS,
            "backgroundDenoisingEnabled": True,
            "recordingEnabled":        settings.ENABLE_CALL_RECORDING,
            "responseDelaySeconds":    0.5,

            # ── Fin d'appel automatique ─────────────────────
            "endCallPhrases": [
                "au revoir",
                "bonne journée",
                "bonne soirée",
                "à bientôt",
                "merci au revoir",
            ],

            # ── Métadonnées ─────────────────────────────────
            # C'est par ici que le backend identifie le tenant à chaque webhook
            # et chaque appel d'outil : ne jamais retirer garage_id.
            "metadata": {
                "garage_id":   str(garage_id),
                "garage_name": garage_name,
            },
        }

        # ── Outils ──────────────────────────────────────────
        # Vapi n'accepte pas les définitions en ligne : on crée (ou réutilise)
        # les outils, puis on référence leurs ids dans model.toolIds.
        tool_ids = await self.ensure_tools()
        if tool_ids:
            payload["model"]["toolIds"] = tool_ids
        else:
            logger.error(
                "🚨 Aucun outil attaché à l'assistant : l'agent pourra parler "
                "mais ne pourra ni consulter l'agenda, ni prendre de RDV, "
                "ni transférer l'appel."
            )

        response = await self._client.post("/assistant", json=payload)
        if response.status_code >= 400:
            logger.error(f"Vapi 400 response : {response.text}")
        response.raise_for_status()


        data = response.json()
        logger.info(
            f"✅ Assistant Vapi créé : {data['id']} "
            f"pour garage {garage_name}"
        )
        return data

    async def update_assistant(
        self,
        assistant_id:  str,
        system_prompt: str,
        first_message: str,
    ) -> dict:
        """
        Met à jour le prompt d'un assistant existant.
        À appeler quand le garage modifie ses infos/services.
        """
        payload = {
            "model": {
                "messages": [
                    {
                        "role":    "system",
                        "content": system_prompt,
                    }
                ],
            },
            "firstMessage": first_message,
        }

        response = await self._client.patch(
            f"/assistant/{assistant_id}",
            json=payload,
        )
        response.raise_for_status()

        logger.info(f"✅ Assistant {assistant_id} mis à jour")
        return response.json()

    async def get_assistant(self, assistant_id: str) -> dict:
        """Récupère les détails d'un assistant."""
        response = await self._client.get(f"/assistant/{assistant_id}")
        response.raise_for_status()
        return response.json()

    async def delete_assistant(self, assistant_id: str) -> bool:
        """Supprime un assistant (churn client)."""
        response = await self._client.delete(f"/assistant/{assistant_id}")
        response.raise_for_status()
        logger.info(f"🗑️ Assistant {assistant_id} supprimé")
        return True

    # ── Numéros de téléphone ─────────────────────────────────

    async def list_phone_numbers(self) -> list[dict]:
        """Liste tous les numéros configurés dans Vapi."""
        response = await self._client.get("/phone-number")
        response.raise_for_status()
        return response.json()

    async def assign_phone_number(
        self,
        phone_number_id: str,
        assistant_id:    str,
    ) -> dict:
        """
        Assigne un numéro de téléphone à un assistant.
        Quand ce numéro est appelé, l'assistant répond.
        """
        payload = {
            "assistantId": assistant_id,
        }

        response = await self._client.patch(
            f"/phone-number/{phone_number_id}",
            json=payload,
        )
        response.raise_for_status()

        logger.info(
            f"✅ Numéro {phone_number_id} → "
            f"Assistant {assistant_id}"
        )
        return response.json()
    async def create_phone_number(
        self,
        twilio_number:      str,
        twilio_account_sid: str,
        twilio_auth_token:  str,
        assistant_id:       str,
        label:              str = "",
    ) -> dict:
        """Importe un numéro Twilio dans Vapi et l'assigne à un assistant."""
        payload = {
            "provider":          "twilio",
            "number":            twilio_number,
            "twilioAccountSid":  twilio_account_sid,
            "twilioAuthToken":   twilio_auth_token,
            "assistantId":       assistant_id,
            "name":              label,
        }
        response = await self._client.post("/phone-number", json=payload)
        if response.status_code >= 400:
            logger.error(f"Vapi create_phone_number error : {response.text}")
        response.raise_for_status()
        return response.json()

    # ── Appels ───────────────────────────────────────────────

    async def get_call(self, call_id: str) -> dict:
        """Récupère les détails d'un appel terminé."""
        response = await self._client.get(f"/call/{call_id}")
        response.raise_for_status()
        return response.json()

    async def list_calls(
        self,
        assistant_id: Optional[str] = None,
        limit:        int = 50,
    ) -> list[dict]:
        """Liste les appels avec filtre optionnel par assistant."""
        params = {"limit": limit}
        if assistant_id:
            params["assistantId"] = assistant_id

        response = await self._client.get("/call", params=params)
        response.raise_for_status()
        return response.json()

    # ── Outils (Tools) ───────────────────────────────────────

    async def ensure_tools(self) -> list[str]:
        """
        Garantit que les outils existent chez Vapi et retourne leurs identifiants.

        Vapi ne prend pas les définitions d'outils en ligne dans l'assistant : il
        faut les créer via `POST /tool`, puis référencer leurs ids dans
        `model.toolIds`. C'est cette étape qui manquait — l'attachement était
        commenté dans `create_assistant`, donc **les assistants créés par
        l'onboarding n'avaient aucun outil** : l'agent pouvait parler, mais ni
        consulter l'agenda, ni prendre un RDV, ni transférer.

        Les outils sont **partagés entre tous les garages** : leur définition ne
        contient rien de spécifique à un garage (le tenant est identifié par
        `assistant.metadata.garage_id`). On les réutilise donc au lieu d'en
        recréer un jeu par onboarding.
        """
        definitions = self._build_tools_config()
        voulus = {d["function"]["name"]: d for d in definitions}

        # Outils déjà présents chez Vapi, indexés par nom
        existants: dict[str, str] = {}
        try:
            reponse = await self._client.get("/tool")
            reponse.raise_for_status()
            for outil in reponse.json() or []:
                nom = (outil.get("function") or {}).get("name")
                if nom:
                    existants[nom] = outil["id"]
        except Exception as e:
            logger.warning(f"⚠️ Impossible de lister les outils Vapi : {e}")

        ids: list[str] = []
        for nom, definition in voulus.items():
            if nom in existants:
                ids.append(existants[nom])
                continue
            try:
                creation = await self._client.post("/tool", json=definition)
                if creation.status_code >= 400:
                    logger.error(f"❌ Création de l'outil {nom} refusée : {creation.text}")
                    continue
                ids.append(creation.json()["id"])
                logger.info(f"🔧 Outil Vapi créé : {nom}")
            except Exception as e:
                logger.error(f"❌ Création de l'outil {nom} impossible : {e}")

        logger.info(f"🔧 {len(ids)}/{len(voulus)} outils disponibles pour l'assistant")
        return ids

    def _build_tools_config(self) -> list[dict]:
        """
        Construit la configuration des tools disponibles
        pour l'agent. Ces tools sont appelés via webhook
        vers notre backend FastAPI.
        """
        webhook_base = f"{settings.APP_BASE_URL}/api/tools"

        return [
            # ── Vérifier disponibilités ──────────────────
            {
                "type": "function",
                "function": {
                    "name":        "check_availability",
                    "description": (
                        "Vérifie les créneaux disponibles dans l'agenda "
                        "pour un type d'intervention donné. "
                        "Retourne une liste de créneaux disponibles."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "service_type": {
                                "type":        "string",
                                "description": "Type d'intervention (revision, vidange, freins, diagnostic, etc.)",
                            },
                            "preferred_slot": {
                                "type":        "string",
                                "description": "Préférence du client (matin, après-midi, un jour de la semaine)",
                            },
                        },
                        "required": ["service_type"],
                    },
                },
                "server": {"url": f"{webhook_base}/check_availability"},
            },

            # ── Créer un RDV ──────────────────────────────
            {
                "type": "function",
                "function": {
                    "name":        "create_appointment",
                    "description": (
                        "Crée un rendez-vous confirmé dans l'agenda "
                        "après accord du client sur un créneau."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "client_name": {
                                "type":        "string",
                                "description": "Nom complet du client",
                            },
                            "client_phone": {
                                "type":        "string",
                                "description": "Numéro de téléphone du client",
                            },
                            "client_email": {
                                "type":        "string",
                                "description": "Email du client (optionnel)",
                            },
                            "vehicle_brand": {
                                "type":        "string",
                                "description": "Marque du véhicule",
                            },
                            "vehicle_model": {
                                "type":        "string",
                                "description": "Modèle du véhicule",
                            },
                            "vehicle_registration": {
                                "type":        "string",
                                "description": "Immatriculation (optionnel)",
                            },
                            "service_type": {
                                "type":        "string",
                                "description": "Type d'intervention",
                            },
                            "scheduled_at": {
                                "type":        "string",
                                "description": "Créneau choisi au format ISO 8601 (ex: 2024-03-15T09:00:00)",
                            },
                        },
                        "required": [
                            "client_name",
                            "client_phone",
                            "service_type",
                            "scheduled_at",
                        ],
                    },
                },
                "server": {"url": f"{webhook_base}/create_appointment"},
            },

            # ── Récupérer un RDV existant ─────────────────
            {
                "type": "function",
                "function": {
                    "name":        "get_appointment_by_phone",
                    "description": (
                        "Recherche un rendez-vous existant "
                        "par numéro de téléphone du client."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "phone_number": {
                                "type":        "string",
                                "description": "Numéro de téléphone du client",
                            },
                        },
                        "required": ["phone_number"],
                    },
                },
                "server": {"url": f"{webhook_base}/get_appointment_by_phone"},
            },

            # ── Modifier un RDV ───────────────────────────
            {
                "type": "function",
                "function": {
                    "name":        "update_appointment",
                    "description": "Modifie le créneau d'un rendez-vous existant.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "appointment_id": {
                                "type":        "string",
                                "description": "ID du rendez-vous à modifier",
                            },
                            "new_scheduled_at": {
                                "type":        "string",
                                "description": "Nouveau créneau au format ISO 8601",
                            },
                        },
                        "required": ["appointment_id", "new_scheduled_at"],
                    },
                },
                "server": {"url": f"{webhook_base}/update_appointment"},
            },

            # ── Annuler un RDV ────────────────────────────
            {
                "type": "function",
                "function": {
                    "name":        "cancel_appointment",
                    "description": "Annule un rendez-vous existant.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "appointment_id": {
                                "type":        "string",
                                "description": "ID du rendez-vous à annuler",
                            },
                            "reason": {
                                "type":        "string",
                                "description": "Raison de l'annulation",
                            },
                        },
                        "required": ["appointment_id"],
                    },
                },
                "server": {"url": f"{webhook_base}/cancel_appointment"},
            },

            # ── Envoyer confirmation ──────────────────────
            {
                "type": "function",
                "function": {
                    "name":        "send_confirmation",
                    "description": (
                        "Envoie un SMS et/ou email de confirmation "
                        "de rendez-vous au client."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "client_phone":    {"type": "string"},
                            "client_email":    {"type": "string"},
                            "appointment_id":  {"type": "string"},
                        },
                        "required": ["client_phone"],
                    },
                },
                "server": {"url": f"{webhook_base}/send_confirmation"},
            },

            # ── Transférer l'appel ────────────────────────
            {
                "type": "function",
                "function": {
                    "name":        "transfer_call",
                    "description": (
                        "Transfère l'appel vers le propriétaire du garage. "
                        "À utiliser pour les urgences, réclamations "
                        "ou situations hors périmètre."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "reason": {
                                "type":        "string",
                                "description": "Raison du transfert (urgence, reclamation, hors_perimetre)",
                                "enum": ["urgence", "reclamation", "hors_perimetre", "demande_client"],
                            },
                            "summary": {
                                "type":        "string",
                                "description": "Résumé de la conversation pour le patron",
                            },
                        },
                        "required": ["reason"],
                    },
                },
                "server": {"url": f"{webhook_base}/transfer_call"},
            },

            # ── Alerte SMS urgence ────────────────────────
            {
                "type": "function",
                "function": {
                    "name":        "send_sms_alert",
                    "description": (
                        "Envoie une alerte SMS urgente au patron du garage. "
                        "Pour les urgences ou réclamations."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "priority": {
                                "type": "string",
                                "enum": ["critique", "elevee", "normale"],
                            },
                            "message": {
                                "type":        "string",
                                "description": "Message d'alerte à envoyer",
                            },
                        },
                        "required": ["priority", "message"],
                    },
                },
                "server": {"url": f"{webhook_base}/send_sms_alert"},
            },

            # ── Prendre un message ────────────────────────
            {
                "type": "function",
                "function": {
                    "name":        "take_message",
                    "description": (
                        "Enregistre un message pour que le garage "
                        "rappelle le client ultérieurement."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "client_name":  {"type": "string"},
                            "client_phone": {"type": "string"},
                            "message":      {"type": "string"},
                        },
                        "required": ["client_name", "client_phone", "message"],
                    },
                },
                "server": {"url": f"{webhook_base}/take_message"},
            },

            # ── État d'un véhicule en atelier ─────────────
            {
                "type": "function",
                "function": {
                    "name":        "check_vehicle_status",
                    "description": (
                        "À utiliser quand le client demande si son véhicule est "
                        "prêt, où en est la réparation, ou quand il pourra le "
                        "récupérer. L'agent n'a PAS accès au suivi de l'atelier : "
                        "cet outil route vers le garage ou prend un message. "
                        "Ne jamais inventer un état d'avancement."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "client_phone": {
                                "type":        "string",
                                "description": "Numéro du client, s'il l'a donné",
                            },
                            "vehicle_info": {
                                "type":        "string",
                                "description": "Marque/modèle ou immatriculation si connus",
                            },
                        },
                        "required": [],
                    },
                },
                "server": {"url": f"{webhook_base}/check_vehicle_status"},
            },
        ]


# ============================================================
# VÉRIFICATION DE SIGNATURE WEBHOOK
# ============================================================

def verify_vapi_signature(
    payload:   bytes,
    signature: str,
    secret:    str,
) -> bool:
    """
    Vérifie la signature HMAC-SHA256 des webhooks Vapi.
    Protège contre les requêtes frauduleuses.

    Args:
        payload   : Corps brut de la requête (bytes)
        signature : Header "x-vapi-signature" de la requête
        secret    : VAPI_WEBHOOK_SECRET de ton .env

    Returns:
        bool : True si la signature est valide
    """
    if not secret:
        logger.warning("⚠️ VAPI_WEBHOOK_SECRET non configuré !")
        return True  # En dev, on accepte tout

    expected = hmac.new(
        key=secret.encode("utf-8"),
        msg=payload,
        digestmod=hashlib.sha256,
    ).hexdigest()

    # Comparaison en temps constant (protection timing attack)
    is_valid = hmac.compare_digest(expected, signature)

    if not is_valid:
        logger.error(
            f"❌ Signature Vapi invalide ! "
            f"Expected: {expected[:20]}... "
            f"Got: {signature[:20]}..."
        )

    return is_valid


# ============================================================
# INSTANCE GLOBALE
# ============================================================
vapi_client = VapiClient()