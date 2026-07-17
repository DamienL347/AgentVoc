"""
Routes FastAPI — Webhooks Vapi
Reçoit et traite tous les événements d'appel
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.security import require_vapi_signature
from app.core.call_handler import call_handler
from app.models.schemas import CallStatus

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/webhooks",
    tags=["webhooks"],
    dependencies=[Depends(require_vapi_signature)],
)


# ============================================================
# WEBHOOK PRINCIPAL VAPI
# ============================================================

@router.post("/vapi")
async def vapi_webhook(request: Request):
    """
    Point d'entrée unique pour tous les événements Vapi.
    Vapi envoie ici : call.started, call.ended, function-call, etc.
    La signature HMAC est exigée par le router (require_vapi_signature).
    """

    # ── Parser le JSON ───────────────────────────────────────
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payload JSON invalide",
        )

    event_type = payload.get("message", {}).get("type") or payload.get("type", "")
    logger.info(f"📨 Webhook Vapi reçu : {event_type}")

    # ── Router vers le bon handler ───────────────────────────
    if event_type == "call.started" or event_type == "call-started":
        return await _handle_call_started(payload)

    elif event_type == "call.ended" or event_type == "end-of-call-report":
        return await _handle_call_ended(payload)

    elif event_type == "function-call" or event_type == "tool-calls":
        return await _handle_function_call(payload)

    elif event_type == "transcript":
        # Transcription temps réel (on log mais on ne bloque pas)
        logger.debug(f"📝 Transcript : {payload.get('transcript', {})}")
        return {"status": "ok"}

    else:
        logger.warning(f"⚠️ Event Vapi non géré : {event_type}")
        return {"status": "ignored", "event": event_type}


# ============================================================
# HANDLERS D'ÉVÉNEMENTS
# ============================================================

async def _handle_call_started(payload: dict) -> dict:
    """Traite le début d'un appel."""

    call    = payload.get("call", {})
    message = payload.get("message", {})

    vapi_call_id = call.get("id") or message.get("call", {}).get("id", "")
    caller_phone = (
        call.get("customer", {}).get("number")
        or message.get("call", {}).get("customer", {}).get("number", "unknown")
    )

    # Identifier le garage via les métadonnées de l'assistant
    assistant_metadata = (
        call.get("assistant", {}).get("metadata", {})
        or message.get("call", {}).get("assistant", {}).get("metadata", {})
    )
    garage_id_str = assistant_metadata.get("garage_id")

    if not garage_id_str:
        logger.error("❌ garage_id manquant dans les métadonnées de l'assistant")
        return {"status": "error", "detail": "garage_id manquant"}

    try:
        garage_id = UUID(garage_id_str)
    except ValueError:
        return {"status": "error", "detail": "garage_id invalide"}

    result = await call_handler.on_call_started(
        vapi_call_id=vapi_call_id,
        caller_phone=caller_phone,
        garage_id=garage_id,
    )

    return {"status": "ok", **result}


async def _handle_call_ended(payload: dict) -> dict:
    """Traite la fin d'un appel (rapport final)."""

    message = payload.get("message", payload)

    vapi_call_id     = message.get("call", {}).get("id", "")
    transcript       = message.get("transcript")
    summary          = message.get("summary")
    duration_seconds = message.get("durationSeconds")
    recording_url    = message.get("recordingUrl")
    ended_reason     = message.get("endedReason", "")

    # Mapper la raison de fin vers un CallStatus
    status_map = {
        "customer-ended-call":    CallStatus.ABANDONNE,
        "assistant-ended-call":   CallStatus.INFORMATION_DONNEE,
        "max-duration-exceeded":  CallStatus.ABANDONNE,
        "silence-timed-out":      CallStatus.ABANDONNE,
        "pipeline-error":         CallStatus.ERREUR,
    }
    call_status = status_map.get(ended_reason, CallStatus.INFORMATION_DONNEE)

    result = await call_handler.on_call_ended(
        vapi_call_id=vapi_call_id,
        transcript=transcript,
        summary=summary,
        duration_seconds=duration_seconds,
        recording_url=recording_url,
        call_status=call_status,
    )

    return {"status": "ok", **result}


async def _handle_function_call(payload: dict) -> dict:
    """
    Traite les appels de fonctions (tool calls) de l'agent.
    Retourne le résultat au format attendu par Vapi.
    """

    message = payload.get("message", payload)

    # Extraire les données du tool call
    tool_call_list = (
        message.get("toolCallList")
        or message.get("functionCall")
        or []
    )

    # Gérer le format liste (plusieurs tools en même temps)
    if isinstance(tool_call_list, dict):
        tool_call_list = [tool_call_list]

    if not tool_call_list:
        return {"results": []}

    # Identifier le garage
    vapi_call_id   = message.get("call", {}).get("id", "")
    garage_id_str  = (
        message.get("call", {})
        .get("assistant", {})
        .get("metadata", {})
        .get("garage_id", "")
    )

    try:
        garage_id = UUID(garage_id_str)
    except (ValueError, AttributeError):
        logger.error(f"❌ garage_id invalide pour tool call : {garage_id_str}")
        return {
            "results": [{
                "toolCallId": tool_call_list[0].get("id", ""),
                "result":     "Erreur technique, je vous transfère.",
            }]
        }

    # Traiter chaque tool call
    results = []
    for tool_call in tool_call_list:
        tool_name   = tool_call.get("function", {}).get("name") or tool_call.get("name", "")
        parameters  = tool_call.get("function", {}).get("arguments") or tool_call.get("parameters", {})
        tool_call_id = tool_call.get("id", "")

        # Si arguments est une string JSON, parser
        if isinstance(parameters, str):
            import json
            try:
                parameters = json.loads(parameters)
            except json.JSONDecodeError:
                parameters = {}

        result = await call_handler.handle_tool_call(
            tool_name=tool_name,
            parameters=parameters,
            vapi_call_id=vapi_call_id,
            garage_id=garage_id,
        )

        # Formater la réponse pour Vapi
        result_text = result.get("message", "Action effectuée.")
        results.append({
            "toolCallId": tool_call_id,
            "result":     result_text,
        })

    return {"results": results}