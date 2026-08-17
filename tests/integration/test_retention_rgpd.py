"""
RGPD — durées de conservation et droit à l'effacement.

Deux risques opposés, aussi graves l'un que l'autre :
  • ne rien purger → données personnelles conservées sans limite ;
  • purger trop → destruction de données récentes encore nécessaires au service.

Ces tests vérifient les deux sens. Garage jetable par test, aucune donnée réelle
touchée.
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

from app.services.retention_service import ANONYME, RetentionService   # noqa: E402
from tests.simulator import CallSimulator                              # noqa: E402

CLIENT = "+33612345678"


@pytest.fixture
def sim():
    with CallSimulator() as s:
        yield s


@pytest.fixture
def service():
    svc = RetentionService()
    from app.db.supabase_client import get_supabase_client
    svc.db = get_supabase_client()
    return svc


def _creer_appel(sim, *, age_jours: int, telephone: str = CLIENT) -> dict:
    """Insère un appel daté, avec toutes les données personnelles renseignées."""
    quand = datetime.now(timezone.utc) - timedelta(days=age_jours)
    ligne = {
        "garage_id":     sim.garage_id,
        "vapi_call_id":  f"ret_{age_jours}_{telephone[-4:]}_{quand.timestamp()}",
        "caller_phone":  telephone,
        "transcription": "Bonjour, je voudrais une révision pour ma Clio.",
        "summary":       "Client souhaite une révision",
        "recording_url": "https://exemple.invalid/enregistrement.mp3",
        "recording_duration_sec": 88,
        "duration_seconds": 88,
        "call_status":   "rdv_pris",
        "created_at":    quand.isoformat(),
        "collected_data": {"nom": "Pierre Moreau"},
    }
    return sim.db.table("calls").insert(ligne).execute().data[0]


def _relire(sim, call_id: str) -> dict:
    return (sim.db.table("calls").select("*")
            .eq("id", call_id).single().execute().data)


# ═════════════════════════════════════════════════════════════════════════════
# Ce qui doit être purgé
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_enregistrement_audio_purge_apres_30_jours(sim, service):
    """L'audio est la donnée la plus sensible : premier palier."""
    appel = _creer_appel(sim, age_jours=45)

    await service.run()

    apres = _relire(sim, appel["id"])
    assert apres["recording_url"] is None
    assert apres["recording_duration_sec"] is None
    # La durée de l'appel reste : c'est une métadonnée, pas une donnée perso
    assert apres["duration_seconds"] == 88


@pytest.mark.asyncio
async def test_transcription_purgee_apres_90_jours(sim, service):
    appel = _creer_appel(sim, age_jours=120)

    await service.run()

    apres = _relire(sim, appel["id"])
    assert apres["transcription"] is None
    assert apres["recording_url"] is None   # palier plus court, déjà dépassé


@pytest.mark.asyncio
async def test_appel_anonymise_apres_un_an(sim, service):
    appel = _creer_appel(sim, age_jours=400)

    await service.run()

    apres = _relire(sim, appel["id"])
    assert apres["caller_phone"] == ANONYME
    assert apres["summary"] is None
    assert apres["collected_data"] in ({}, None)
    # Les métadonnées statistiques survivent : le dashboard garde son historique
    assert apres["call_status"] == "rdv_pris"
    assert apres["duration_seconds"] == 88


# ═════════════════════════════════════════════════════════════════════════════
# Ce qui ne doit PAS être touché
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_appel_recent_intact(sim, service):
    """Un appel d'hier doit rester complet — sinon le service est inutilisable."""
    appel = _creer_appel(sim, age_jours=1)

    await service.run()

    apres = _relire(sim, appel["id"])
    assert apres["recording_url"] is not None
    assert apres["transcription"] is not None
    assert apres["caller_phone"] == CLIENT
    assert apres["summary"] is not None


@pytest.mark.asyncio
async def test_paliers_independants(sim, service):
    """
    À 45 jours : l'audio part, mais la transcription (90 j) et le numéro (365 j)
    restent. Un palier ne doit pas déclencher les autres.
    """
    appel = _creer_appel(sim, age_jours=45)

    await service.run()

    apres = _relire(sim, appel["id"])
    assert apres["recording_url"] is None       # 30 j dépassés
    assert apres["transcription"] is not None   # 90 j non atteints
    assert apres["caller_phone"] == CLIENT      # 365 j non atteints


@pytest.mark.asyncio
async def test_dry_run_ne_modifie_rien(sim, service):
    appel = _creer_appel(sim, age_jours=400)

    bilan = await service.run(dry_run=True)

    assert bilan["dry_run"] is True
    assert bilan["enregistrements"] >= 1
    apres = _relire(sim, appel["id"])
    assert apres["recording_url"] is not None, "dry_run a modifié la base"
    assert apres["caller_phone"] == CLIENT


@pytest.mark.asyncio
async def test_rejouable_sans_effet_de_bord(sim, service):
    """Idempotence : deux passages donnent le même état."""
    appel = _creer_appel(sim, age_jours=400)

    await service.run()
    premier = _relire(sim, appel["id"])
    await service.run()
    second = _relire(sim, appel["id"])

    assert premier["caller_phone"] == second["caller_phone"] == ANONYME


# ═════════════════════════════════════════════════════════════════════════════
# Droit à l'effacement (article 17)
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_effacement_sur_demande_meme_si_recent(sim, service):
    """
    Le droit à l'effacement ne dépend pas de l'âge : un appel d'hier doit
    pouvoir être effacé sur demande de la personne.
    """
    appel = _creer_appel(sim, age_jours=1)
    rdv   = sim.creer_rdv(dans_heures=48, client=CLIENT, nom="Pierre Moreau")

    bilan = await service.effacer_personne(CLIENT, garage_id=sim.garage_id)

    assert bilan["appels"] >= 1
    assert bilan["rendez_vous"] >= 1

    apres = _relire(sim, appel["id"])
    assert apres["caller_phone"] == ANONYME
    assert apres["transcription"] is None
    assert apres["recording_url"] is None

    rdv_apres = (sim.db.table("appointments").select("*")
                 .eq("id", rdv["id"]).single().execute().data)
    assert rdv_apres["client_phone"] is None
    assert rdv_apres["client_name"] == ANONYME
    # Le créneau reste : le garage garde la trace de son activité
    assert rdv_apres["scheduled_at"] is not None


@pytest.mark.asyncio
async def test_effacement_n_touche_pas_les_autres_personnes(sim, service):
    """Un effacement ciblé ne doit pas emporter les données d'un autre client."""
    autre = _creer_appel(sim, age_jours=1, telephone="+33699887766")
    _creer_appel(sim, age_jours=1, telephone=CLIENT)

    await service.effacer_personne(CLIENT, garage_id=sim.garage_id)

    apres = _relire(sim, autre["id"])
    assert apres["caller_phone"] == "+33699887766"
    assert apres["transcription"] is not None


@pytest.mark.asyncio
async def test_effacement_exige_un_garage(service):
    """
    Sans garage_id, l'effacement est refusé : la demande est portée par un
    garage, qui n'a aucun droit sur les données détenues par un autre.
    """
    bilan = await service.effacer_personne(CLIENT)

    assert "erreur" in bilan
    assert "garage_id" in bilan["erreur"]


@pytest.mark.asyncio
async def test_effacement_cloisonne_entre_garages(sim, service):
    """
    Le même numéro peut être client de deux garages concurrents. Une demande
    adressée à l'un ne doit rien effacer chez l'autre.
    """
    chez_a = _creer_appel(sim, age_jours=1)

    with CallSimulator(garage_name="SIM Concurrent") as autre:
        chez_b = _creer_appel(autre, age_jours=1)

        await service.effacer_personne(CLIENT, garage_id=sim.garage_id)

        # Effacé chez le garage demandeur…
        assert _relire(sim, chez_a["id"])["caller_phone"] == ANONYME
        # …mais intact chez le concurrent
        reste = _relire(autre, chez_b["id"])
        assert reste["caller_phone"] == CLIENT, (
            "Effacement propagé à un autre garage : fuite de cloisonnement"
        )
        assert reste["transcription"] is not None


@pytest.mark.asyncio
async def test_effacement_numero_invalide_refuse(service):
    bilan = await service.effacer_personne("pas-un-numero", tous_garages=True)
    assert "erreur" in bilan


@pytest.mark.asyncio
async def test_effacement_dry_run(sim, service):
    appel = _creer_appel(sim, age_jours=1)

    bilan = await service.effacer_personne(CLIENT, garage_id=sim.garage_id, dry_run=True)

    assert bilan["dry_run"] is True
    assert _relire(sim, appel["id"])["caller_phone"] == CLIENT


# ═════════════════════════════════════════════════════════════════════════════
# Routes internes
# ═════════════════════════════════════════════════════════════════════════════

def test_routes_rgpd_protegees_par_le_secret(sim, monkeypatch):
    """
    Ces routes détruisent des données : elles ne doivent jamais être
    déclenchables sans le secret.
    """
    from app.config import settings
    monkeypatch.setattr(settings, "CRON_SECRET", "le-vrai-secret")

    for chemin in ("/internal/retention/run",
                   "/internal/rgpd/effacement?telephone=%2B33612345678"):
        reponse = sim._client.post(chemin, headers={"x-cron-secret": "mauvais"})
        assert reponse.status_code == 401, f"{chemin} accessible sans le bon secret"
