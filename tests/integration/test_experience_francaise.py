"""
Expérience 100 % française — garde-fou.

Décision produit (18/08/2026) : la V1 vise exclusivement des garages français.
Le multilingue est renvoyé à une V2/V3, quand un besoin réel sera remonté.

Ce test vérifie ce que le client **entend et lit réellement** : les messages
rendus par les outils pendant un appel simulé, les SMS, et les messages fixes
de l'assistant. Un défaut de ce type a déjà été trouvé — l'assistant réglé à la
main terminait ses appels français par « Goodbye. ».

Contrôler les chaînes dans le code source produirait des faux positifs (noms de
champs, valeurs d'API). On contrôle donc les messages produits à l'exécution.
"""
import os
import re

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

# Mots sans ambiguïté : ils n'existent pas en français et trahissent un texte
# laissé en anglais. Volontairement courte — mieux vaut rater un cas que crier
# au loup sur « confirmation » ou « information », identiques dans les deux langues.
MOTS_ANGLAIS = [
    "goodbye", "hello", "please", "sorry", "thank you", "welcome",
    "your appointment", "booking", "schedule", "cancelled", "failed",
    "unavailable", "we are", "you can", "best regards", "click here",
]


def _anglicismes(texte: str) -> list[str]:
    if not texte:
        return []
    minuscule = texte.lower()
    return [m for m in MOTS_ANGLAIS if re.search(rf"\b{re.escape(m)}\b", minuscule)]


def _verifier(texte: str, contexte: str) -> None:
    fautifs = _anglicismes(texte)
    assert not fautifs, f"Texte anglais dans {contexte} : {fautifs} — {texte!r}"


@pytest.fixture
def sim():
    with CallSimulator() as s:
        yield s


# ═════════════════════════════════════════════════════════════════════════════
# Ce que le client entend pendant l'appel
# ═════════════════════════════════════════════════════════════════════════════

def test_parcours_de_prise_de_rdv_entierement_en_francais(sim):
    call = sim.new_call(caller=CLIENT)
    call.start()

    dispo = call.tool("check_availability", service_type="revision")
    _verifier(dispo.message, "check_availability")

    rdv = call.tool("create_appointment",
                    scheduled_at=dispo.body["slots"][0]["start"],
                    client_name="Pierre Moreau", client_phone=CLIENT,
                    service_type="revision")
    _verifier(rdv.message, "create_appointment")

    appts = call.db_appointments()
    conf = call.tool("send_confirmation", client_phone=CLIENT,
                     appointment_id=appts[0]["id"])
    _verifier(conf.message, "send_confirmation")

    # Le SMS effectivement parti
    for sms in call.sms_sent():
        _verifier(sms["body"], "SMS de confirmation")


def test_messages_de_secours_en_francais(sim):
    """Les cas dégradés sont souvent ceux qu'on oublie de traduire."""
    call = sim.new_call(caller=CLIENT)
    call.start()

    for outil, params in [
        ("get_appointment_by_phone", {"client_phone": "+33699999999"}),
        ("cancel_appointment", {"appointment_id": "00000000-0000-0000-0000-000000000000",
                                "reason": "test"}),
        ("check_vehicle_status", {"client_phone": CLIENT}),
        ("take_message", {"client_name": "Paul", "client_phone": CLIENT,
                          "message": "Rappel souhaité"}),
        ("transfer_call", {"reason": "demande_client", "summary": "test"}),
    ]:
        resultat = call.tool(outil, **params)
        _verifier(resultat.message, outil)


def test_creneaux_annonces_en_francais_naturel(sim):
    """
    Les créneaux sont lus à voix haute : ils doivent sonner français
    (« lundi 17 août à 9h »), pas « Monday 17 August at 9 AM ».
    """
    call = sim.new_call(caller=CLIENT)
    call.start()

    dispo = call.tool("check_availability", service_type="revision")
    jours = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")

    for creneau in dispo.body["slots"]:
        libelle = creneau["formatted_fr"].lower()
        assert any(j in libelle for j in jours), (
            f"Créneau non formaté en français : {creneau['formatted_fr']!r}"
        )
        assert "am" not in libelle.split() and "pm" not in libelle.split(), (
            f"Format horaire anglo-saxon : {creneau['formatted_fr']!r}"
        )


def test_rappel_de_rdv_en_francais(sim):
    """Le SMS de rappel est lu par le client, souvent la veille au soir."""
    import asyncio

    from app.db.supabase_client import get_supabase_client
    from app.integrations import fake_transport
    from app.services.reminder_service import ReminderService

    sim.creer_rdv(dans_heures=24, client=CLIENT, nom="Pierre Moreau")

    service = ReminderService()
    service.db = get_supabase_client()
    fake_transport.reset_log()

    asyncio.run(service.run(ignorer_heures=True))

    envoyes = [e for e in fake_transport.SENT_LOG if e["kind"] == "sms"]
    assert envoyes, "Aucun rappel envoyé"
    for sms in envoyes:
        _verifier(sms["body"], "SMS de rappel")


# ═════════════════════════════════════════════════════════════════════════════
# Messages fixes de l'assistant
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_messages_fixes_de_l_assistant_en_francais():
    """
    firstMessage, endCallMessage et voicemailMessage sont prononcés tels quels :
    c'est là qu'un défaut anglais s'entend le plus (cas réel : « Goodbye. »).
    """
    from uuid import uuid4

    from app.integrations.vapi_client import vapi_client

    payload = await vapi_client.create_assistant(
        garage_id=uuid4(), garage_name="Garage Martin",
        system_prompt="Tu es Léa.",
        first_message="Bonjour, je suis Léa du Garage Martin. Cet appel peut être enregistré.",
    )

    for champ in ("firstMessage", "endCallMessage", "voicemailMessage"):
        _verifier(payload.get(champ, ""), f"assistant.{champ}")

    for phrase in payload.get("endCallPhrases", []):
        _verifier(phrase, "endCallPhrases")


@pytest.mark.asyncio
async def test_la_transcription_est_configuree_en_francais():
    """
    Un STT réglé sur l'anglais comprendrait mal les clients : c'est le réglage
    qui compte le plus pour la qualité perçue.
    """
    from uuid import uuid4

    from app.integrations.vapi_client import vapi_client

    payload = await vapi_client.create_assistant(
        garage_id=uuid4(), garage_name="Garage Martin",
        system_prompt="Tu es Léa.", first_message="Bonjour !",
    )

    assert payload["transcriber"]["language"] == "fr"


# ═════════════════════════════════════════════════════════════════════════════
# Prompts
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("garage_type", ["mecanique_generale", "depanneur_remorquage"])
def test_les_prompts_sont_rediges_en_francais(garage_type):
    from app.prompts.system_prompt import PromptGenerator

    prompt = PromptGenerator().generate(
        garage_data={
            "name": "Garage Martin", "agent_name": "Léa",
            "garage_type": garage_type, "phone_number": "+33561000001",
            "business_hours": {"monday": {"open": "08:00", "close": "18:00",
                                          "closed": False}},
        },
        services=[{"name": "Révision", "duration_minutes": 90}],
    )

    # Les noms d'outils sont en anglais par nature : on ne contrôle que la prose.
    prose = re.sub(r"\b[a-z_]+\(\)", "", prompt)
    _verifier(prose, f"prompt {garage_type}")
