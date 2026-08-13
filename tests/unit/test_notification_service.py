"""
Tests du service de notifications : l'envoi et sa traçabilité en base.

Le point critique : une notification envoyée DOIT laisser une trace, et un échec
de traçabilité ne doit JAMAIS faire échouer l'envoi.
"""
import pytest

from app.integrations.send_result import SendResult
from app.services.notification_service import NotificationService


# ── Doubles de test ──────────────────────────────────────────────────────────

class FakeTable:
    def __init__(self, store, fail=False):
        self.store = store
        self.fail  = fail

    def insert(self, row):
        if self.fail:
            raise RuntimeError("insert refusé")
        self.store.append(row)
        return self

    def execute(self):
        return self


class FakeDB:
    def __init__(self, fail=False):
        self.rows = []
        self.fail = fail

    def table(self, name):
        assert name == "notifications"
        return FakeTable(self.rows, fail=self.fail)


@pytest.fixture
def service():
    svc    = NotificationService()
    svc.db = FakeDB()
    return svc


GARAGE_ID = "a1b2c3d4-0000-0000-0000-000000000001"


# ── SendResult ───────────────────────────────────────────────────────────────

def test_send_result_reste_compatible_avec_un_booleen():
    """L'ancien contrat `if sms_sent:` doit continuer de fonctionner."""
    assert bool(SendResult.success("SM123")) is True
    assert bool(SendResult.failure("boom")) is False


# ── Traçabilité des SMS ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sms_envoye_est_trace_avec_le_sid(service, monkeypatch):
    import app.integrations.twilio_sms as twilio_mod

    async def fake_send(to, body):
        return SendResult.success(provider_id="SM_abc123")

    monkeypatch.setattr(twilio_mod.twilio_client, "send_sms", fake_send)

    result = await service.send_sms(
        to="+33600000001", body="RDV confirmé", garage_id=GARAGE_ID,
        recipient_type="client", call_id="call-uuid-1",
    )

    assert result.ok
    assert len(service.db.rows) == 1
    row = service.db.rows[0]
    assert row["channel"]            == "sms"
    assert row["status"]             == "sent"
    assert row["twilio_message_sid"] == "SM_abc123"
    assert row["recipient_phone"]    == "+33600000001"
    assert row["recipient_type"]     == "client"
    assert row["call_id"]            == "call-uuid-1"
    assert row["sent_at"] is not None
    assert row["error_message"] is None


@pytest.mark.asyncio
async def test_sms_en_echec_est_trace_en_failed(service, monkeypatch):
    import app.integrations.twilio_sms as twilio_mod

    async def fake_send(to, body):
        return SendResult.failure("Twilio non configuré")

    monkeypatch.setattr(twilio_mod.twilio_client, "send_sms", fake_send)

    result = await service.send_sms(
        to="+33600000002", body="Alerte", garage_id=GARAGE_ID,
        recipient_type="garage",
    )

    assert not result.ok
    row = service.db.rows[0]
    assert row["status"]        == "failed"
    assert row["error_message"] == "Twilio non configuré"
    assert row["sent_at"] is None


@pytest.mark.asyncio
async def test_corps_tres_long_est_tronque(service, monkeypatch):
    """Un email HTML complet ne doit pas faire exploser la colonne `body`."""
    import app.integrations.twilio_sms as twilio_mod

    async def fake_send(to, body):
        return SendResult.success(provider_id="SM_x")

    monkeypatch.setattr(twilio_mod.twilio_client, "send_sms", fake_send)

    await service.send_sms(
        to="+33600000003", body="x" * 5000, garage_id=GARAGE_ID,
    )

    assert len(service.db.rows[0]["body"]) == 2000


@pytest.mark.asyncio
async def test_echec_de_tracabilite_ne_casse_pas_l_envoi(monkeypatch):
    """Si la base refuse l'insert, le SMS reste considéré comme envoyé."""
    import app.integrations.twilio_sms as twilio_mod

    svc    = NotificationService()
    svc.db = FakeDB(fail=True)

    async def fake_send(to, body):
        return SendResult.success(provider_id="SM_ok")

    monkeypatch.setattr(twilio_mod.twilio_client, "send_sms", fake_send)

    result = await svc.send_sms(
        to="+33600000004", body="Coucou", garage_id=GARAGE_ID,
    )

    assert result.ok is True
    assert svc.db.rows == []


# ── Traçabilité des emails ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_email_de_confirmation_est_trace(service, monkeypatch):
    import app.integrations.resend_email as resend_mod

    async def fake_send(to, appointment):
        return SendResult.success(provider_id="re_789")

    monkeypatch.setattr(
        resend_mod.resend_client, "send_appointment_confirmation", fake_send,
    )

    await service.send_appointment_confirmation_email(
        to="client@example.fr",
        appointment={"title": "Révision", "garage_name": "Garage Martin"},
        garage_id=GARAGE_ID,
        appointment_id="appt-uuid-1",
    )

    row = service.db.rows[0]
    assert row["channel"]         == "email"
    assert row["resend_email_id"] == "re_789"
    assert row["recipient_email"] == "client@example.fr"
    assert row["recipient_phone"] is None
    assert row["appointment_id"]  == "appt-uuid-1"
    assert "Garage Martin" in row["subject"]
