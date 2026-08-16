"""
Les cas d'usage du context.md, rejoués de bout en bout contre le backend réel.

Aucun téléphone, aucun crédit consommé : PROVIDER_MODE=fake simule le réseau
vers Twilio, Cal.com, Vapi et Resend. Le reste — FastAPI, signature HMAC,
middlewares, logique métier, base Supabase — est le vrai code.

Chaque test travaille sur un garage jetable, supprimé à la fin (ON DELETE
CASCADE nettoie appels, RDV et notifications). Aucune donnée réelle n'est touchée.

Lancer : venv\\Scripts\\python.exe -m pytest tests/integration/test_scenarios_usage.py -v
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
def sim():
    with CallSimulator() as s:
        yield s


@pytest.fixture
def sim_sans_agenda():
    """Garage dont l'agenda Cal.com n'est pas rattaché."""
    with CallSimulator(calcom_ready=False) as s:
        yield s


# ═════════════════════════════════════════════════════════════════════════════
# CAS 1 — Prise de rendez-vous
# ═════════════════════════════════════════════════════════════════════════════

def test_cas1_prise_de_rdv_complete(sim):
    """Le parcours qui porte toute la valeur : appel → créneau → RDV → confirmation."""
    call = sim.new_call(caller=CLIENT)
    call.start()

    dispo = call.tool("check_availability", service_type="revision",
                      preferred_slot="matin")
    assert dispo.ok
    slots = dispo.body["slots"]
    assert slots, "Aucun créneau proposé"
    assert not any(s.get("is_fallback") for s in slots), (
        "Créneaux de repli alors que l'agenda est rattaché : ils n'existent "
        "dans aucun agenda réel"
    )

    rdv = call.tool(
        "create_appointment",
        scheduled_at=slots[0]["start"],
        client_name="Pierre Moreau",
        client_phone=CLIENT,
        service_type="revision",
        vehicle_brand="Renault",
        vehicle_model="Clio",
    )
    assert rdv.ok, f"Création du RDV refusée : {rdv.message}"

    # Le RDV doit exister dans l'agenda, pas seulement en base locale
    assert rdv.body.get("calcom_uid"), (
        "calcom_uid vide : le RDV n'est pas dans l'agenda du garage, "
        "alors que l'agent annonce une confirmation au client"
    )

    appts = call.db_appointments()
    assert len(appts) == 1
    assert appts[0]["client_phone"] == CLIENT

    # L'appel doit être marqué comme ayant abouti
    assert call.db_call()["call_status"] == "rdv_pris"

    conf = call.tool("send_confirmation",
                     client_phone=CLIENT, appointment_id=appts[0]["id"])
    assert conf.ok
    assert call.sms_sent(), "Aucun SMS de confirmation"
    assert call.db_notifications(), "SMS envoyé mais non tracé en base"

    call.end(reason="assistant-ended-call", duration=95)

    # La fin d'appel ne doit pas effacer le résultat métier : sinon les RDV sont
    # recomptés en « information donnée » et le taux de conversion est faux.
    assert call.db_call()["call_status"] == "rdv_pris", (
        "Le statut « rdv_pris » a été écrasé par la raison de fin d'appel"
    )


def test_cas1_sans_agenda_rattache_ne_ment_pas_au_client(sim_sans_agenda):
    """
    Sans agenda rattaché, le RDV n'atterrit nulle part. L'agent doit rester
    prudent — pas annoncer une confirmation ferme que rien ne garantit.
    """
    call = sim_sans_agenda.new_call(caller=CLIENT)
    call.start()

    dispo = call.tool("check_availability", service_type="revision")
    assert all(s.get("is_fallback") for s in dispo.body["slots"]), (
        "Sans agenda, les créneaux proposés sont forcément des replis"
    )

    rdv = call.tool(
        "create_appointment",
        scheduled_at=dispo.body["slots"][0]["start"],
        client_name="Pierre Moreau", client_phone=CLIENT, service_type="revision",
    )

    assert rdv.body.get("calcom_uid", "") == ""
    assert "confirmé" not in rdv.message.lower(), (
        f"Message trompeur alors que le RDV n'est dans aucun agenda : {rdv.message}"
    )


# ═════════════════════════════════════════════════════════════════════════════
# CAS 4 — Modification et annulation
# ═════════════════════════════════════════════════════════════════════════════

def _prendre_rdv(call) -> dict:
    dispo = call.tool("check_availability", service_type="vidange")
    rdv   = call.tool(
        "create_appointment",
        scheduled_at=dispo.body["slots"][0]["start"],
        client_name="Marie Dupont", client_phone=CLIENT, service_type="vidange",
    )
    return rdv.body


def test_cas4_retrouver_son_rdv_par_telephone(sim):
    """Le client rappelle : l'agent doit retrouver son RDV avec son numéro."""
    call = sim.new_call(caller=CLIENT)
    call.start()
    _prendre_rdv(call)

    retrouve = call.tool("get_appointment_by_phone", client_phone=CLIENT)
    assert retrouve.ok, f"RDV introuvable : {retrouve.message}"


def test_cas4_annulation(sim):
    call = sim.new_call(caller=CLIENT)
    call.start()
    rdv = _prendre_rdv(call)

    annule = call.tool("cancel_appointment",
                       appointment_id=rdv["appointment_id"],
                       reason="Imprévu")
    assert annule.ok, f"Annulation refusée : {annule.message}"

    statuts = [a["status"] for a in call.db_appointments()]
    assert "annule" in statuts, f"Statut non mis à jour : {statuts}"


def test_cas4_cloisonnement_entre_garages(sim):
    """
    Multi-tenant : un RDV d'un autre garage ne doit jamais être annulable.
    C'est la garantie que deux clients ne se voient pas l'un l'autre.
    """
    call = sim.new_call(caller=CLIENT)
    call.start()
    rdv = _prendre_rdv(call)

    with CallSimulator(garage_name="SIM Voisin") as autre:
        intrus = autre.new_call(caller="+33699999999")
        intrus.start()
        refus = intrus.tool("cancel_appointment",
                            appointment_id=rdv["appointment_id"], reason="test")

        assert not refus.ok, "Un garage a pu annuler le RDV d'un autre garage"
        assert autre.db_appointments() == []


# ═════════════════════════════════════════════════════════════════════════════
# CAS 2, 3, 5 — Information, devis, dépannage non urgent
# ═════════════════════════════════════════════════════════════════════════════

def test_cas2_demande_information_puis_raccroche(sim):
    """Un appel sans RDV doit être enregistré proprement, pas perdu."""
    call = sim.new_call(caller="+33611223344")
    call.start()
    call.end(reason="assistant-ended-call", duration=42,
             summary="Horaires du samedi demandés")

    enregistre = call.db_call()
    assert enregistre is not None, "Appel non enregistré"
    assert enregistre["duration_seconds"] == 42
    assert enregistre["summary"] == "Horaires du samedi demandés"


def test_cas3_devis_message_laisse(sim):
    """Devis hors périmètre de l'agent : prendre un message plutôt qu'inventer."""
    call = sim.new_call(caller=CLIENT)
    call.start()

    msg = call.tool("take_message", client_name="Paul Durand",
                    client_phone=CLIENT,
                    message="Souhaite un devis embrayage sur Golf 2015")
    assert msg.ok
    assert call.db_call()["call_status"] == "message_laisse"
    assert call.sms_sent(), "Le patron n'a pas été alerté du message"


# ═════════════════════════════════════════════════════════════════════════════
# CAS 8 et urgences — Transfert et escalade
# ═════════════════════════════════════════════════════════════════════════════

def test_cas8_mecontentement_transfert_humain(sim):
    call = sim.new_call(caller=CLIENT)
    call.start()

    transfert = call.tool("transfer_call", reason="reclamation",
                          summary="Client mécontent d'une réparation")
    assert transfert.ok
    assert transfert.body.get("transfer_phone"), "Aucun numéro de transfert renvoyé"

    enregistre = call.db_call()
    assert enregistre["transfer_triggered"] is True
    assert enregistre["call_status"] == "transfere_humain"
    assert call.sms_sent(), "Réclamation : le patron doit être alerté par SMS"


def test_urgence_alerte_sms_au_patron(sim):
    call = sim.new_call(caller=CLIENT)
    call.start()

    alerte = call.tool("send_sms_alert", priority="critique",
                       message="Accident A61, véhicule immobilisé")
    assert alerte.ok, f"Alerte non envoyée : {alerte.message}"

    sms = call.sms_sent()
    assert sms, "Aucune alerte SMS émise"
    assert "CRITIQUE" in sms[-1]["body"].upper()

    tracees = call.db_notifications()
    assert tracees, "Alerte d'urgence envoyée mais non tracée"


# ═════════════════════════════════════════════════════════════════════════════
# Robustesse
# ═════════════════════════════════════════════════════════════════════════════

def test_webhook_rejoue_ne_duplique_pas_l_appel(sim):
    """Vapi peut rejouer un webhook : l'appel ne doit pas être compté deux fois."""
    call = sim.new_call(caller=CLIENT)
    premier = call.start()
    second  = call.start()

    assert premier["call_id"] == second["call_id"]


def test_un_appel_abandonne_reste_abandonne(sim):
    """
    Contrepartie du test précédent : sans résultat métier, le statut déduit de
    la fin d'appel doit bien être appliqué.
    """
    call = sim.new_call(caller="+33600112233")
    call.start()
    call.end(reason="customer-ended-call", duration=8)

    assert call.db_call()["call_status"] == "abandonne"


def test_transfert_survit_a_la_fin_d_appel(sim):
    """Un appel transféré ne doit pas être recompté comme simple information."""
    call = sim.new_call(caller=CLIENT)
    call.start()
    call.tool("transfer_call", reason="urgence", summary="Panne autoroute")
    call.end(reason="assistant-ended-call", duration=30)

    assert call.db_call()["call_status"] == "transfere_humain"


def test_outil_inconnu_repond_sans_planter(sim):
    call = sim.new_call(caller=CLIENT)
    call.start()
    res = call.tool("check_availability", service_type="service_inexistant_xyz")
    assert res.status_code == 200
