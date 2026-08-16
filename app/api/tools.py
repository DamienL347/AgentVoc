"""
Routes FastAPI — Tool calls de l'agent Vapi
Chaque endpoint correspond à une fonction appelable par l'agent
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.security import require_vapi_signature
from app.core.call_handler import call_handler

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/tools",
    tags=["tools"],
    dependencies=[Depends(require_vapi_signature)],
)


async def _get_context(request: Request) -> tuple[str, UUID]:
    """
    Extrait vapi_call_id et garage_id depuis la requête Vapi.
    Commun à tous les tool endpoints.
    """
    payload       = await request.json()
    message       = payload.get("message", payload)
    vapi_call_id  = message.get("call", {}).get("id", "unknown")
    garage_id_str = (
        message.get("call", {})
        .get("assistant", {})
        .get("metadata", {})
        .get("garage_id", "")
    )

    try:
        garage_id = UUID(garage_id_str)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="garage_id invalide ou manquant",
        )

    return vapi_call_id, garage_id


@router.post("/check_availability")
async def check_availability(request: Request):
    payload      = await request.json()
    call_id, gid = await _get_context(request)
    params       = payload.get("parameters", payload.get("function", {}).get("arguments", {}))

    return await call_handler.handle_tool_call(
        tool_name="check_availability",
        parameters=params,
        vapi_call_id=call_id,
        garage_id=gid,
    )


@router.post("/create_appointment")
async def create_appointment(request: Request):
    payload      = await request.json()
    call_id, gid = await _get_context(request)
    params       = payload.get("parameters", payload.get("function", {}).get("arguments", {}))

    return await call_handler.handle_tool_call(
        tool_name="create_appointment",
        parameters=params,
        vapi_call_id=call_id,
        garage_id=gid,
    )


@router.post("/get_appointment_by_phone")
async def get_appointment_by_phone(request: Request):
    payload      = await request.json()
    call_id, gid = await _get_context(request)
    params       = payload.get("parameters", payload.get("function", {}).get("arguments", {}))

    return await call_handler.handle_tool_call(
        tool_name="get_appointment_by_phone",
        parameters=params,
        vapi_call_id=call_id,
        garage_id=gid,
    )


@router.post("/update_appointment")
async def update_appointment(request: Request):
    payload      = await request.json()
    call_id, gid = await _get_context(request)
    params       = payload.get("parameters", payload.get("function", {}).get("arguments", {}))

    return await call_handler.handle_tool_call(
        tool_name="update_appointment",
        parameters=params,
        vapi_call_id=call_id,
        garage_id=gid,
    )


@router.post("/cancel_appointment")
async def cancel_appointment(request: Request):
    payload      = await request.json()
    call_id, gid = await _get_context(request)
    params       = payload.get("parameters", payload.get("function", {}).get("arguments", {}))

    return await call_handler.handle_tool_call(
        tool_name="cancel_appointment",
        parameters=params,
        vapi_call_id=call_id,
        garage_id=gid,
    )


@router.post("/send_confirmation")
async def send_confirmation(request: Request):
    payload      = await request.json()
    call_id, gid = await _get_context(request)
    params       = payload.get("parameters", payload.get("function", {}).get("arguments", {}))

    return await call_handler.handle_tool_call(
        tool_name="send_confirmation",
        parameters=params,
        vapi_call_id=call_id,
        garage_id=gid,
    )


@router.post("/transfer_call")
async def transfer_call(request: Request):
    payload      = await request.json()
    call_id, gid = await _get_context(request)
    params       = payload.get("parameters", payload.get("function", {}).get("arguments", {}))

    return await call_handler.handle_tool_call(
        tool_name="transfer_call",
        parameters=params,
        vapi_call_id=call_id,
        garage_id=gid,
    )


@router.post("/send_sms_alert")
async def send_sms_alert(request: Request):
    payload      = await request.json()
    call_id, gid = await _get_context(request)
    params       = payload.get("parameters", payload.get("function", {}).get("arguments", {}))

    return await call_handler.handle_tool_call(
        tool_name="send_sms_alert",
        parameters=params,
        vapi_call_id=call_id,
        garage_id=gid,
    )


@router.post("/take_message")
async def take_message(request: Request):
    payload      = await request.json()
    call_id, gid = await _get_context(request)
    params       = payload.get("parameters", payload.get("function", {}).get("arguments", {}))

    return await call_handler.handle_tool_call(
        tool_name="take_message",
        parameters=params,
        vapi_call_id=call_id,
        garage_id=gid,
    )


@router.post("/check_vehicle_status")
async def check_vehicle_status(request: Request):
    """« Ma voiture est-elle prête ? » — route vers le garage ou prend un message."""
    payload      = await request.json()
    call_id, gid = await _get_context(request)
    params       = payload.get("parameters", payload.get("function", {}).get("arguments", {}))

    return await call_handler.handle_tool_call(
        tool_name="check_vehicle_status",
        parameters=params,
        vapi_call_id=call_id,
        garage_id=gid,
    )