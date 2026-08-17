"""
Garage en congés — l'agenda Cal.com fait foi.

Décision produit : le garagiste bloque ses vacances dans son propre agenda.
L'agent ne « sait » pas qu'il est en congés ; il le déduit du fait que l'agenda
ne renvoie aucun créneau cette semaine mais rouvre plus loin. Il doit alors
annoncer la fermeture et proposer les premières dispos à la réouverture — pas
répondre « aucune disponibilité » et perdre le client.

Aucun SMS réel (PROVIDER_MODE=fake) ; garage jetable par test.
"""
import os

import pytest
from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("PROVIDER_MODE", "fake")

pytestmark = pytest.mark.skipif(
    not (os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY")),
    reason="Credentials Supabase absents",
)

from tests.simulator import CallSimulator   # noqa: E402

CLIENT = "+33612345678"


def test_garage_ouvert_ne_declenche_pas_le_mode_conges():
    """Cas nominal : des créneaux cette semaine, aucune mention de congés."""
    with CallSimulator() as sim:
        call = sim.new_call(caller=CLIENT)
        call.start()
        res = call.tool("check_availability", service_type="revision")

        assert not res.body.get("on_holiday")
        assert not any(s.get("after_closure") for s in res.body["slots"])
        assert "fermé" not in res.body["message"].lower()


def test_garage_en_conges_annonce_la_reouverture():
    """Congés de 15 jours : rien cette semaine, l'agent annonce la réouverture."""
    with CallSimulator(conges_jours=15) as sim:
        call = sim.new_call(caller=CLIENT)
        call.start()
        res = call.tool("check_availability", service_type="revision")

        assert res.body.get("on_holiday") is True
        assert res.body.get("reopening"), "Date de réouverture absente"

        msg = res.body["message"].lower()
        assert "fermé" in msg and "congés" in msg
        # Des créneaux réels sont proposés, pas des créneaux de repli inventés
        assert res.body["slots"], "Aucun créneau proposé à la réouverture"
        assert all(not s.get("is_fallback") for s in res.body["slots"])
        assert all(s.get("after_closure") for s in res.body["slots"])


def test_on_peut_reserver_le_creneau_de_reouverture():
    """
    L'intérêt de la feature : le client repart avec un vrai RDV à la réouverture,
    et il atterrit bien dans l'agenda du garage.
    """
    with CallSimulator(conges_jours=15) as sim:
        call = sim.new_call(caller=CLIENT)
        call.start()

        dispo = call.tool("check_availability", service_type="revision")
        creneau = dispo.body["slots"][0]

        rdv = call.tool(
            "create_appointment",
            scheduled_at=creneau["start"],
            client_name="Pierre Moreau",
            client_phone=CLIENT,
            service_type="revision",
        )

        assert rdv.ok, f"Réservation à la réouverture refusée : {rdv.message}"
        assert rdv.body.get("calcom_uid"), "RDV hors agenda malgré la réouverture"
        assert len(sim.db_appointments()) == 1


def test_conges_courts_restent_dans_la_semaine():
    """
    Congés de 3 jours : des créneaux restent dans la fenêtre normale, donc pas
    d'escalade ni d'annonce de fermeture — le client est servi directement.
    """
    with CallSimulator(conges_jours=3) as sim:
        call = sim.new_call(caller=CLIENT)
        call.start()
        res = call.tool("check_availability", service_type="revision")

        assert not res.body.get("on_holiday")
        assert res.body["slots"]


def test_sans_agenda_la_feature_conges_ne_s_applique_pas():
    """
    Sans agenda rattaché, on ignore les congés : on retombe sur les créneaux de
    repli « sous réserve », jamais sur l'annonce de réouverture (qu'on ne peut
    pas connaître).
    """
    with CallSimulator(calcom_ready=False, conges_jours=15) as sim:
        call = sim.new_call(caller=CLIENT)
        call.start()
        res = call.tool("check_availability", service_type="revision")

        assert not res.body.get("on_holiday")
        assert res.body.get("tentative") is True
        assert all(s.get("is_fallback") for s in res.body["slots"])
