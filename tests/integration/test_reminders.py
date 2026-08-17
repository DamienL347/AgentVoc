"""
Rappels de rendez-vous — J-1 et H-2.

Enjeu : le no-show coûte un créneau d'atelier non facturable au garage, et le
rappel est l'argument commercial le plus concret du produit. Mais un rappel
envoyé deux fois, ou à 3h du matin, produit l'effet inverse.

Aucun SMS réel n'est envoyé (PROVIDER_MODE=fake) ; chaque test travaille sur un
garage jetable.
"""
import os
from datetime import datetime, timedelta, timezone

import pytest
from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("PROVIDER_MODE", "fake")

pytestmark = pytest.mark.skipif(
    not (os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY")),
    reason="Credentials Supabase absents",
)

from app.integrations import fake_transport            # noqa: E402
from app.services.reminder_service import ReminderService   # noqa: E402
from tests.simulator import CallSimulator              # noqa: E402


@pytest.fixture
def sim():
    with CallSimulator() as s:
        yield s


@pytest.fixture
def service():
    svc = ReminderService()
    from app.db.supabase_client import get_supabase_client
    svc.db = get_supabase_client()
    fake_transport.reset_log()
    return svc


def _sms_vers(numero: str) -> list[dict]:
    return [e for e in fake_transport.SENT_LOG
            if e["kind"] == "sms" and e.get("to") == numero]


def _relire(sim, appointment_id: str) -> dict:
    return (sim.db.table("appointments").select("*")
            .eq("id", appointment_id).single().execute().data)


# ═════════════════════════════════════════════════════════════════════════════
# Envoi nominal
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_rappel_j1_envoye_et_trace(sim, service):
    rdv = sim.creer_rdv(dans_heures=24, client="+33612345601")

    bilan = await service.run(ignorer_heures=True)

    assert bilan["envoyes"] >= 1
    assert _sms_vers("+33612345601"), "Aucun rappel J-1 envoyé"

    apres = _relire(sim, rdv["id"])
    assert apres["reminder_24h_sent"] is True

    # Le rappel doit être traçable : sans trace, impossible de prouver l'envoi
    tracees = [n for n in sim.db.table("notifications").select("*")
               .eq("appointment_id", rdv["id"]).execute().data]
    assert tracees, "Rappel envoyé mais non tracé en base"


@pytest.mark.asyncio
async def test_rappel_h2_envoye(sim, service):
    rdv = sim.creer_rdv(dans_heures=2, client="+33612345602")

    await service.run(ignorer_heures=True)

    sms = _sms_vers("+33612345602")
    assert sms, "Aucun rappel H-2 envoyé"
    assert "2 heures" in sms[0]["body"]
    assert _relire(sim, rdv["id"])["reminder_2h_sent"] is True


@pytest.mark.asyncio
async def test_le_message_contient_l_essentiel(sim, service):
    sim.creer_rdv(dans_heures=24, client="+33612345603",
                  nom="Marie Dupont", titre="Vidange")

    await service.run(ignorer_heures=True)
    corps = _sms_vers("+33612345603")[0]["body"]

    assert "Marie" in corps                    # personnalisé
    assert "Vidange" in corps                  # prestation rappelée
    assert sim.garage_name.split()[0] in corps or "SIM" in corps
    # Une porte de sortie : un client qui peut annuler libère le créneau
    assert "annuler" in corps.lower()


# ═════════════════════════════════════════════════════════════════════════════
# Idempotence — le point critique
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_deux_executions_n_envoient_qu_un_seul_rappel(sim, service):
    """
    L'ordonnanceur peut passer plusieurs fois dans la fenêtre, ou être rejoué.
    Recevoir deux fois le même rappel décrédibilise l'agent.
    """
    sim.creer_rdv(dans_heures=24, client="+33612345604")

    await service.run(ignorer_heures=True)
    await service.run(ignorer_heures=True)

    assert len(_sms_vers("+33612345604")) == 1, "Rappel envoyé en double"


@pytest.mark.asyncio
async def test_un_rdv_deja_marque_n_est_pas_renvoye(sim, service):
    rdv = sim.creer_rdv(dans_heures=24, client="+33612345605")
    sim.db.table("appointments").update({"reminder_24h_sent": True}) \
        .eq("id", rdv["id"]).execute()

    await service.run(ignorer_heures=True)

    assert not _sms_vers("+33612345605")


# ═════════════════════════════════════════════════════════════════════════════
# Ce qui ne doit PAS déclencher de rappel
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_rdv_annule_ne_recoit_rien(sim, service):
    sim.creer_rdv(dans_heures=24, client="+33612345606", statut="annule")

    await service.run(ignorer_heures=True)

    assert not _sms_vers("+33612345606"), "Rappel envoyé pour un RDV annulé"


@pytest.mark.asyncio
async def test_rdv_passe_ne_recoit_rien(sim, service):
    sim.creer_rdv(dans_heures=-3, client="+33612345607")

    await service.run(ignorer_heures=True)

    assert not _sms_vers("+33612345607")


@pytest.mark.asyncio
async def test_rdv_hors_fenetre_ne_recoit_rien(sim, service):
    """Un RDV dans 5 jours n'est pas encore concerné."""
    sim.creer_rdv(dans_heures=120, client="+33612345608")

    await service.run(ignorer_heures=True)

    assert not _sms_vers("+33612345608")


@pytest.mark.asyncio
async def test_numero_inexploitable_est_ignore_sans_boucler(sim, service):
    """
    Sans numéro valide, on marque quand même le rappel : sinon le service
    réessaierait à chaque passage, indéfiniment.
    """
    rdv = sim.creer_rdv(dans_heures=24, client="numero-invalide")

    bilan = await service.run(ignorer_heures=True)

    assert bilan["ignores"] >= 1
    assert _relire(sim, rdv["id"])["reminder_24h_sent"] is True


# ═════════════════════════════════════════════════════════════════════════════
# Heures décentes
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_aucun_sms_en_pleine_nuit(sim, service):
    """Réveiller un client à 3h du matin annule tout le bénéfice du rappel."""
    sim.creer_rdv(dans_heures=24, client="+33612345609")

    nuit = datetime(2026, 8, 20, 1, 0, tzinfo=timezone.utc)   # 3h à Paris
    bilan = await service.run(maintenant=nuit)

    assert bilan["differe"] is True
    assert bilan["envoyes"] == 0
    assert not _sms_vers("+33612345609")


@pytest.mark.asyncio
async def test_envoi_autorise_en_journee(sim, service):
    quand = datetime.now(timezone.utc).replace(hour=8, minute=30)  # 10h30 à Paris
    bilan = await service.run(maintenant=quand)

    assert bilan["differe"] is False


# ═════════════════════════════════════════════════════════════════════════════
# Route déclenchée par l'ordonnanceur
# ═════════════════════════════════════════════════════════════════════════════

def test_route_interne_refuse_un_mauvais_secret(sim, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "CRON_SECRET", "le-vrai-secret")

    reponse = sim._client.post("/internal/reminders/run",
                               headers={"x-cron-secret": "mauvais"})
    assert reponse.status_code == 401


def test_route_interne_accepte_le_bon_secret(sim, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "CRON_SECRET", "le-vrai-secret")

    reponse = sim._client.post("/internal/reminders/run?ignorer_heures=true",
                               headers={"x-cron-secret": "le-vrai-secret"})
    assert reponse.status_code == 200
    assert reponse.json()["status"] == "ok"
