"""
Cas d'usage ajoutés au bloc B, rejoués de bout en bout.

Ces situations arrivent tous les jours dans un garage et n'étaient pas gérées :
véhicule prêt, demande d'humain, créneau pris entre-temps, numéro masqué,
garage fermé. Le fil conducteur : l'agent ne doit jamais promettre ce qu'il ne
peut pas tenir.
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


@pytest.fixture
def sim_ouvert():
    with CallSimulator() as s:
        yield s


@pytest.fixture
def sim_ferme():
    with CallSimulator(ouvert=False) as s:
        yield s


# ═════════════════════════════════════════════════════════════════════════════
# CAS 9 — « Ma voiture est-elle prête ? »
# ═════════════════════════════════════════════════════════════════════════════

def test_voiture_prete_garage_ouvert_met_en_relation(sim_ouvert):
    call = sim_ouvert.new_call(caller=CLIENT)
    call.start()

    res = call.tool("check_vehicle_status", client_phone=CLIENT)

    assert res.ok
    assert res.body["action"] == "transfer"
    assert res.body["transfer_phone"] == "+33600000001"
    # L'agent doit dire qu'il ne sait pas, pas inventer un état d'avancement
    assert "pas le suivi" in res.message.lower()


def test_voiture_prete_garage_ferme_prend_un_message(sim_ferme):
    call = sim_ferme.new_call(caller=CLIENT)
    call.start()

    res = call.tool("check_vehicle_status", client_phone=CLIENT)

    assert res.body["action"] == "take_message"
    assert "fermé" in res.message.lower()
    # L'agent annonce QUAND le garage rappellera
    assert "rappelle" in res.message.lower()


def test_voiture_prete_n_invente_jamais_d_avancement(sim_ouvert):
    """Garde-fou explicite : aucune formulation ne doit suggérer un état."""
    call = sim_ouvert.new_call(caller=CLIENT)
    call.start()
    res = call.tool("check_vehicle_status", client_phone=CLIENT)

    interdits = ["est prête", "sera prête", "en cours de réparation", "terminée"]
    assert not any(mot in res.message.lower() for mot in interdits), (
        f"L'agent laisse entendre un état d'avancement : {res.message}"
    )


def test_voiture_prete_remonte_le_dernier_rdv_connu(sim_ouvert):
    """Le contexte véhicule aide la personne qui reprend l'appel."""
    call = sim_ouvert.new_call(caller=CLIENT)
    call.start()

    dispo = call.tool("check_availability", service_type="revision")
    call.tool("create_appointment", scheduled_at=dispo.body["slots"][0]["start"],
              client_name="Pierre Moreau", client_phone=CLIENT,
              service_type="revision", vehicle_brand="Renault", vehicle_model="Clio")

    res = call.tool("check_vehicle_status", client_phone=CLIENT)

    contexte = res.body.get("vehicle_context")
    assert contexte, "Aucun contexte véhicule remonté"
    assert contexte["vehicle_brand"] == "Renault"


# ═════════════════════════════════════════════════════════════════════════════
# CAS 10 — Le client veut un humain
# ═════════════════════════════════════════════════════════════════════════════

def test_demande_humain_transfere_immediatement(sim_ouvert):
    call = sim_ouvert.new_call(caller=CLIENT)
    call.start()

    res = call.tool("transfer_call", reason="demande_client",
                    summary="Le client demande à parler à quelqu'un")

    assert res.ok
    assert res.body.get("transfer_phone"), "Aucun transfert alors que le garage est ouvert"


def test_transfert_hors_horaires_bascule_en_message(sim_ferme):
    """
    Transférer vers un téléphone qui ne décrochera pas est pire que ne pas
    transférer : le client tombe dans le vide.
    """
    call = sim_ferme.new_call(caller=CLIENT)
    call.start()

    res = call.tool("transfer_call", reason="demande_client", summary="Veut un humain")

    assert res.body["action"] == "take_message"
    assert res.body["transfer_phone"] is None
    assert "rappelé" in res.message.lower()
    # L'appel reste tracé comme un transfert demandé
    assert call.db_call()["transfer_triggered"] is True


def test_transfert_sans_numero_configure_ne_promet_rien():
    """Garage sans transfer_phone_number : cas réel, 1 garage sur 3 en base."""
    with CallSimulator(avec_transfert=False) as sim:
        call = sim.new_call(caller=CLIENT)
        call.start()

        res = call.tool("transfer_call", reason="reclamation", summary="Mécontent")

        assert res.body["action"] == "take_message"
        assert res.body["transfer_phone"] is None


# ═════════════════════════════════════════════════════════════════════════════
# CAS 12 — Créneau pris pendant la conversation
# ═════════════════════════════════════════════════════════════════════════════

def test_creneau_deja_pris_est_refuse(sim_ouvert):
    call = sim_ouvert.new_call(caller=CLIENT)
    call.start()

    dispo   = call.tool("check_availability", service_type="revision")
    creneau = dispo.body["slots"][0]["start"]

    premier = call.tool("create_appointment", scheduled_at=creneau,
                        client_name="Pierre Moreau", client_phone=CLIENT,
                        service_type="revision")
    assert premier.ok

    # Un second client vise le même créneau
    autre = sim_ouvert.new_call(caller="+33622334455")
    autre.start()
    second = autre.tool("create_appointment", scheduled_at=creneau,
                        client_name="Marie Dupont", client_phone="+33622334455",
                        service_type="revision")

    assert not second.ok, "Double réservation acceptée sur le même créneau"
    assert second.body.get("conflict") is True
    assert len(sim_ouvert.db_appointments()) == 1


def test_chevauchement_partiel_detecte(sim_ouvert):
    """
    Une vidange (45 min) posée 30 min après le début d'une révision (90 min)
    chevauche l'atelier, même si les heures de début diffèrent.
    """
    from datetime import datetime, timedelta

    call = sim_ouvert.new_call(caller=CLIENT)
    call.start()

    dispo = call.tool("check_availability", service_type="revision")
    debut = datetime.fromisoformat(dispo.body["slots"][0]["start"])

    call.tool("create_appointment", scheduled_at=debut.isoformat(),
              client_name="Pierre Moreau", client_phone=CLIENT,
              service_type="revision")

    chevauche = call.tool(
        "create_appointment",
        scheduled_at=(debut + timedelta(minutes=30)).isoformat(),
        client_name="Marie Dupont", client_phone="+33622334455",
        service_type="vidange",
    )

    assert chevauche.body.get("conflict") is True


def test_creneau_libere_par_une_annulation_est_reutilisable(sim_ouvert):
    call = sim_ouvert.new_call(caller=CLIENT)
    call.start()

    dispo   = call.tool("check_availability", service_type="revision")
    creneau = dispo.body["slots"][0]["start"]

    premier = call.tool("create_appointment", scheduled_at=creneau,
                        client_name="Pierre Moreau", client_phone=CLIENT,
                        service_type="revision")
    call.tool("cancel_appointment", appointment_id=premier.body["appointment_id"],
              reason="Imprévu")

    reprise = call.tool("create_appointment", scheduled_at=creneau,
                        client_name="Marie Dupont", client_phone="+33622334455",
                        service_type="revision")

    assert reprise.ok, "Un créneau annulé doit redevenir disponible"


# ═════════════════════════════════════════════════════════════════════════════
# CAS 11 — Numéro masqué
# ═════════════════════════════════════════════════════════════════════════════

def test_appel_en_numero_masque_est_enregistre(sim_ouvert):
    """L'appel doit exister en base même sans numéro exploitable."""
    call = sim_ouvert.new_call(caller="unknown")
    call.start()
    call.end(duration=25, summary="Appel en numéro masqué")

    assert call.db_call() is not None


def test_detection_numero_masque():
    from app.utils.phone import is_anonymous

    for masque in ["unknown", "anonymous", "private", "", None, "Restricted"]:
        assert is_anonymous(masque) is True, f"{masque!r} devrait être vu comme masqué"

    for valide in ["+33612345678", "0612345678", "06 12 34 56 78"]:
        assert is_anonymous(valide) is False, f"{valide!r} est un vrai numéro"


# ═════════════════════════════════════════════════════════════════════════════
# Créneaux sous réserve
# ═════════════════════════════════════════════════════════════════════════════

def test_creneaux_de_repli_annonces_sous_reserve():
    """Sans agenda rattaché, l'agent ne doit pas annoncer des créneaux fermes."""
    with CallSimulator(calcom_ready=False) as sim:
        call = sim.new_call(caller=CLIENT)
        call.start()

        res = call.tool("check_availability", service_type="revision")

        assert res.body.get("tentative") is True
        assert "sous réserve" in res.message.lower()
        assert "disponibles" not in res.message.lower()
