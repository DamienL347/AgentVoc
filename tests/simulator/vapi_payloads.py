"""
Constructeurs de payloads Vapi.

Fidélité : ces structures reproduisent ce que Vapi envoie réellement, y compris
l'emplacement exact de `garage_id` (message.call.assistant.metadata.garage_id) —
c'est par là que le backend identifie le tenant. Un payload approximatif ferait
passer des tests que la réalité ferait échouer.
"""
from typing import Any, Optional


def _call_block(vapi_call_id: str, garage_id: str, caller_phone: str) -> dict:
    return {
        "id": vapi_call_id,
        "customer":  {"number": caller_phone},
        "assistant": {"metadata": {"garage_id": garage_id}},
    }


def call_started(vapi_call_id: str, garage_id: str, caller_phone: str) -> dict:
    """Événement de début d'appel."""
    return {
        "message": {
            "type": "call.started",
            "call": _call_block(vapi_call_id, garage_id, caller_phone),
        }
    }


def tool_call(
    vapi_call_id: str,
    garage_id:    str,
    caller_phone: str,
    parameters:   Optional[dict[str, Any]] = None,
) -> dict:
    """
    Payload d'un appel d'outil (routes /api/tools/*).
    Les endpoints lisent `parameters`, avec repli sur function.arguments.
    """
    return {
        "message": {"call": _call_block(vapi_call_id, garage_id, caller_phone)},
        "parameters": parameters or {},
    }


def call_ended(
    vapi_call_id:  str,
    garage_id:     str,
    caller_phone:  str,
    ended_reason:  str = "customer-ended-call",
    duration:      int = 90,
    summary:       str = "",
    transcript:    str = "",
    recording_url: Optional[str] = None,
) -> dict:
    """Rapport de fin d'appel."""
    return {
        "message": {
            "type": "end-of-call-report",
            "call": _call_block(vapi_call_id, garage_id, caller_phone),
            "endedReason":     ended_reason,
            "durationSeconds": duration,
            "summary":         summary,
            "transcript":      transcript,
            "recordingUrl":    recording_url,
        }
    }
