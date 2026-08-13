"""
Test d'intégration : la résolution du tenant doit fonctionner en base réelle.

Pourquoi ce test existe : `get_garage_by_phone()` a été cassée pendant des mois
(colonnes `g.timezone` / `g.is_active` inexistantes) sans que rien ne le signale —
le middleware avale l'exception pour ne jamais bloquer un appel, donc la panne
ne se voyait que dans les logs. Ce test transforme ce silence en échec visible.

Nécessite SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY (sinon le test est ignoré).
Lancer : venv\\Scripts\\python.exe -m pytest tests/integration -v
"""
import os

import pytest
from dotenv import load_dotenv

load_dotenv()

pytestmark = pytest.mark.skipif(
    not (os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY")),
    reason="Credentials Supabase absents",
)

# Colonnes que le résolveur et les handlers attendent en retour
CHAMPS_ATTENDUS = {
    "id", "name", "garage_type", "status", "vapi_assistant_id",
    "calcom_username", "calcom_event_type_id", "owner_phone", "owner_email",
    "transfer_phone_number", "transfer_sms_number", "business_hours",
}


@pytest.fixture(scope="module")
def db():
    from supabase import create_client
    return create_client(
        os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )


@pytest.fixture(scope="module")
def garage_onboarde(db):
    """Un garage disposant d'un numéro Twilio, sinon rien à résoudre."""
    rows = (db.table("garages")
            .select("id, name, twilio_phone_number, status")
            .not_.is_("twilio_phone_number", "null")
            .in_("status", ["active", "trial"])
            .limit(1).execute().data)
    if not rows:
        pytest.skip("Aucun garage onboardé avec un numéro Twilio")
    return rows[0]


def test_resolution_par_numero_twilio(db, garage_onboarde):
    """Le cœur du multi-tenant : un numéro appelé → le bon garage."""
    res = db.rpc("get_garage_by_phone",
                 {"p_phone": garage_onboarde["twilio_phone_number"]}).execute()

    assert res.data, "Aucun garage résolu — le multi-tenant est cassé"
    assert res.data[0]["id"] == garage_onboarde["id"]
    assert res.data[0]["name"] == garage_onboarde["name"]


def test_retourne_tous_les_champs_attendus(db, garage_onboarde):
    """Garde-fou : une colonne renommée en base doit faire échouer ce test."""
    res = db.rpc("get_garage_by_phone",
                 {"p_phone": garage_onboarde["twilio_phone_number"]}).execute()

    manquants = CHAMPS_ATTENDUS - set(res.data[0])
    assert not manquants, f"Champs absents du résolveur : {manquants}"


def test_numero_inconnu_ne_resout_rien(db):
    """Un numéro qui n'appartient à aucun garage ne doit pas lever, juste rien renvoyer."""
    res = db.rpc("get_garage_by_phone", {"p_phone": "+33000000000"}).execute()
    assert res.data == []
